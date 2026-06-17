"""Scheduling Core: business logic — run management, generation, conflict detection."""

from datetime import date, datetime, time, timedelta
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.domains.scheduling import models, schemas
from app.domains.inventory.models import InventoryUnit, CapacityRule
from app.domains.campaigns.models import Campaign, CampaignChannel, CampaignTarget, CampaignRendition
from app.domains.channels.models import Channel as ChannelModel
from app.domains.media.models import Creative, CreativeVersion, Rendition
from app.domains.organization.models import Store, Cluster

# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

CONFLICT_TYPES = [
    "capacity_exceeded", "missing_capacity_rule", "invalid_rendition",
    "channel_mismatch", "target_mismatch", "date_out_of_range",
    "no_available_slot", "invalid_capacity_rule",
    "too_many_schedule_items", "slot_conflict",
]

SEVERITIES = ["warning", "error", "blocker"]

MAX_SCHEDULE_ITEMS_PER_RUN: int = 100_000


def _add_conflict(
    run: models.ScheduleRun,
    conflict_type: str,
    severity: str,
    message: str,
    inventory_unit_id: Optional[UUID] = None,
    booking_item_id: Optional[UUID] = None,
    details: Optional[dict] = None,
) -> models.ScheduleConflict:
    """Create a conflict record attached to a run (in-memory, not flushed)."""
    return models.ScheduleConflict(
        schedule_run_id=run.id,
        inventory_unit_id=inventory_unit_id,
        booking_item_id=booking_item_id,
        conflict_type=conflict_type,
        severity=severity,
        message=message,
        details_json=details or {},
    )


def _has_error_or_blocker(conflicts: list[models.ScheduleConflict]) -> bool:
    """Check if any conflict has severity error or blocker."""
    return any(c.severity in ("error", "blocker") for c in conflicts)


def _days_in_range(d_from: date, d_to: date) -> list[date]:
    return [d_from + timedelta(days=i) for i in range((d_to - d_from).days + 1)]


def _parse_time(t: time | str | None) -> time:
    if t is None:
        raise ValueError("time is None")
    if isinstance(t, time):
        return t
    if isinstance(t, str):
        return datetime.strptime(t, "%H:%M:%S").time()
    raise ValueError(f"unexpected time type: {type(t)}")


def _time_to_seconds(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


# ═══════════════════════════════════════════════════════════════════
#  Schedule Run CRUD
# ═══════════════════════════════════════════════════════════════════


async def _get_booking(db: AsyncSession, booking_id: UUID):
    """Load a confirmed booking with campaign + items."""
    from app.domains.inventory.models import CampaignBooking
    booking = await db.get(
        CampaignBooking, booking_id,
        options=[selectinload(CampaignBooking.items)],
    )
    if booking is None:
        raise HTTPException(404, "Booking not found")
    if booking.status != "confirmed":
        raise HTTPException(400, f"Booking must be confirmed (status: {booking.status})")
    return booking


async def _get_booking_campaign(db: AsyncSession, booking):
    """Load campaign and validate it's approved with channels/targets/renditions."""
    campaign = await db.get(
        Campaign, booking.campaign_id,
        options=[
            selectinload(Campaign.channels),
            selectinload(Campaign.targets),
            selectinload(Campaign.renditions),
        ],
    )
    if campaign is None:
        raise HTTPException(404, "Campaign not found")
    if campaign.status != "approved":
        raise HTTPException(400, f"Campaign must be approved (status: {campaign.status})")
    return campaign


async def create_schedule_run(
    db: AsyncSession, data: schemas.ScheduleRunCreate, user_id: UUID,
) -> models.ScheduleRun:
    booking = await _get_booking(db, data.booking_id)
    campaign = await _get_booking_campaign(db, booking)

    if not booking.items:
        raise HTTPException(400, "Booking has no items")

    # Check: no approved run exists for this booking
    existing = await db.execute(
        select(models.ScheduleRun).where(
            models.ScheduleRun.booking_id == data.booking_id,
            models.ScheduleRun.status == "approved",
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            400, "Booking already has an approved schedule run. Cancel it first.",
        )

    # Check: no active non-draft run
    existing_active = await db.execute(
        select(models.ScheduleRun).where(
            models.ScheduleRun.booking_id == data.booking_id,
            models.ScheduleRun.status.in_(("generated", "has_conflicts")),
        )
    )
    if existing_active.scalars().first():
        raise HTTPException(
            400, "Booking has an active schedule run. Cancel it first.",
        )

    run = models.ScheduleRun(
        booking_id=data.booking_id,
        campaign_id=booking.campaign_id,
        created_by=user_id,
        comment=data.comment,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def list_schedule_runs(
    db: AsyncSession,
    booking_id: Optional[UUID] = None,
    campaign_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> list[models.ScheduleRun]:
    stmt = select(models.ScheduleRun)
    if booking_id:
        stmt = stmt.where(models.ScheduleRun.booking_id == booking_id)
    if campaign_id:
        stmt = stmt.where(models.ScheduleRun.campaign_id == campaign_id)
    if status:
        stmt = stmt.where(models.ScheduleRun.status == status)
    stmt = stmt.order_by(models.ScheduleRun.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_schedule_run(db: AsyncSession, run_id: UUID) -> models.ScheduleRun:
    run = await db.get(models.ScheduleRun, run_id)
    if run is None:
        raise HTTPException(404, "Schedule run not found")
    return run


# ═══════════════════════════════════════════════════════════════════
#  Generation Algorithm
# ═══════════════════════════════════════════════════════════════════


async def _get_active_capacity_rule_for_day(
    db: AsyncSession, inventory_unit_id: UUID, d: date,
) -> Optional[CapacityRule]:
    """Find an active capacity rule covering the given day."""
    stmt = select(CapacityRule).where(
        CapacityRule.inventory_unit_id == inventory_unit_id,
        CapacityRule.status == "active",
        CapacityRule.valid_from <= d,
        CapacityRule.valid_to >= d,
    )
    result = await db.execute(stmt)
    rules = list(result.scalars().all())
    if not rules:
        return None
    # No overlapping rules guaranteed; return the first (only) one
    return rules[0]


def _validate_capacity_rule(rule: CapacityRule) -> Optional[str]:
    """Return error message if rule is invalid, None if OK."""
    if not rule.time_from or not rule.time_to:
        return "time_from or time_to is null"
    tf = _parse_time(rule.time_from)
    tt = _parse_time(rule.time_to)
    if tf >= tt:
        return f"time_from ({tf}) >= time_to ({tt})"
    if rule.loop_duration_seconds <= 0:
        return f"loop_duration_seconds={rule.loop_duration_seconds} <= 0"
    if rule.spot_duration_seconds <= 0:
        return f"spot_duration_seconds={rule.spot_duration_seconds} <= 0"
    if rule.max_spots_per_loop <= 0:
        return f"max_spots_per_loop={rule.max_spots_per_loop} <= 0"
    max_possible = (rule.loop_duration_seconds // rule.spot_duration_seconds)
    if rule.max_spots_per_loop > max_possible:
        return (
            f"max_spots_per_loop ({rule.max_spots_per_loop}) exceeds "
            f"loop_duration // spot_duration ({max_possible})"
        )
    return None


async def _get_approved_slots(
    db: AsyncSession,
    inventory_unit_id: UUID,
    d: date,
    loop_position: int,
    exclude_run_id: UUID,
) -> set[int]:
    """Return occupied spot_positions from approved schedule_runs."""
    stmt = select(models.ScheduleItem.spot_position).where(
        models.ScheduleItem.inventory_unit_id == inventory_unit_id,
        models.ScheduleItem.date == d,
        models.ScheduleItem.loop_position == loop_position,
        models.ScheduleItem.status == "active",
        models.ScheduleItem.schedule_run_id != exclude_run_id,
    ).join(
        models.ScheduleRun,
        models.ScheduleRun.id == models.ScheduleItem.schedule_run_id,
    ).where(
        models.ScheduleRun.status.in_(("approved", "generated")),
    )
    result = await db.execute(stmt)
    return {r[0] for r in result.all()}


async def _get_valid_renditions(
    db: AsyncSession, campaign: Campaign, unit_channel_id: UUID,
) -> list[CampaignRendition]:
    """Filter campaign renditions that are valid for scheduling."""
    valid = []
    for cr in campaign.renditions:
        if not cr.is_active:
            continue

        # Load rendition
        rend = await db.get(Rendition, cr.rendition_id)
        if rend is None or rend.status != "valid":
            continue

        if rend.channel_id != unit_channel_id:
            continue

        # Load creative_version + creative
        cv = await db.get(CreativeVersion, rend.creative_version_id)
        if cv is None or cv.status == "archived":
            continue

        creative = await db.get(Creative, cv.creative_id)
        if creative is None or creative.status != "approved":
            continue

        valid.append(cr)
    return valid


async def _validate_target_matching(
    db: AsyncSession, unit: InventoryUnit, campaign: Campaign,
) -> Optional[str]:
    """Return error if unit doesn't match campaign targets, None if OK."""
    store = await db.get(Store, unit.store_id)
    if store is None:
        return f"store {unit.store_id} not found"
    cluster = await db.get(Cluster, store.cluster_id)
    if cluster is None:
        return f"cluster {store.cluster_id} not found"

    for t in campaign.targets:
        if t.target_type == "all_stores":
            return None
        elif t.target_type == "store" and unit.store_id == t.store_id:
            return None
        elif t.target_type == "cluster" and store.cluster_id == t.cluster_id:
            return None
        elif t.target_type == "branch" and cluster.branch_id == t.branch_id:
            return None
        elif t.target_type == "logical_carrier" and unit.logical_carrier_id == t.logical_carrier_id:
            return None
        elif t.target_type == "display_surface" and unit.display_surface_id == t.display_surface_id:
            return None
    return f"inventory unit {unit.id} does not match any campaign target"


async def generate_schedule(
    db: AsyncSession, run_id: UUID, user_id: UUID,
) -> models.ScheduleRun:
    run = await get_schedule_run(db, run_id)
    if run.status == "approved":
        raise HTTPException(400, "Cannot regenerate approved run")
    if run.status == "cancelled":
        raise HTTPException(400, "Cannot regenerate cancelled run")

    booking = await _get_booking(db, run.booking_id)
    campaign = await _get_booking_campaign(db, booking)

    # Clear previous items and conflicts
    for item in list(run.items) if run.items else []:
        await db.delete(item)
    for conflict in list(run.conflicts) if run.conflicts else []:
        await db.delete(conflict)
    await db.flush()

    conflicts: list[models.ScheduleConflict] = []
    new_items: list[models.ScheduleItem] = []

    # Estimate total items
    estimated = 0
    for bi in booking.items:
        unit = await db.get(InventoryUnit, bi.inventory_unit_id)
        if unit is None or not unit.is_sellable or unit.status != "active":
            continue
        days = _days_in_range(bi.date_from, bi.date_to)
        for d in days:
            rule = await _get_active_capacity_rule_for_day(db, bi.inventory_unit_id, d)
            if rule:
                tf = _parse_time(rule.time_from)
                tt = _parse_time(rule.time_to)
                active_sec = _time_to_seconds(tt) - _time_to_seconds(tf)
                loops = int(active_sec // rule.loop_duration_seconds) if rule.loop_duration_seconds > 0 else 0
                estimated += loops * bi.booked_spots_per_loop

    max_items = MAX_SCHEDULE_ITEMS_PER_RUN
    settings = get_settings()
    if hasattr(settings, 'MAX_SCHEDULE_ITEMS_PER_RUN'):
        max_items = settings.MAX_SCHEDULE_ITEMS_PER_RUN
    if estimated > max_items:
        conflicts.append(_add_conflict(
            run, "too_many_schedule_items", "blocker",
            f"Estimated {estimated} schedule items exceeds limit of {max_items}",
            details={"estimated": estimated, "limit": max_items},
        ))
        run.status = "has_conflicts"
        run.generated_by = user_id
        run.generated_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.add_all(conflicts)
        await db.commit()
        await db.refresh(run)
        return run

    # ── Per booking item ──────────────────────────────────────────
    for bi in booking.items:
        unit = await db.get(InventoryUnit, bi.inventory_unit_id)
        if unit is None:
            conflicts.append(_add_conflict(
                run, "no_available_slot", "error",
                f"inventory unit {bi.inventory_unit_id} not found",
                inventory_unit_id=bi.inventory_unit_id,
                booking_item_id=bi.id,
            ))
            continue

        if unit.status != "active" or not unit.is_sellable:
            conflicts.append(_add_conflict(
                run, "no_available_slot", "error",
                f"inventory unit {unit.id} not active or not sellable",
                inventory_unit_id=unit.id, booking_item_id=bi.id,
            ))
            continue

        # Channel check
        unit_ch_in_campaign = any(
            cc.channel_id == unit.channel_id for cc in campaign.channels
        )
        if not unit_ch_in_campaign:
            conflicts.append(_add_conflict(
                run, "channel_mismatch", "error",
                f"inventory unit channel {unit.channel_id} not in campaign channels",
                inventory_unit_id=unit.id, booking_item_id=bi.id,
            ))
            continue

        # Target matching
        tm_err = await _validate_target_matching(db, unit, campaign)
        if tm_err:
            conflicts.append(_add_conflict(
                run, "target_mismatch", "error", tm_err,
                inventory_unit_id=unit.id, booking_item_id=bi.id,
            ))
            continue

        # Valid renditions
        renditions = await _get_valid_renditions(db, campaign, unit.channel_id)
        if not renditions:
            conflicts.append(_add_conflict(
                run, "invalid_rendition", "error",
                f"no valid renditions for channel {unit.channel_id}",
                inventory_unit_id=unit.id, booking_item_id=bi.id,
            ))
            continue

        days = _days_in_range(bi.date_from, bi.date_to)

        for d in days:
            rule = await _get_active_capacity_rule_for_day(db, bi.inventory_unit_id, d)

            if rule is None:
                conflicts.append(_add_conflict(
                    run, "missing_capacity_rule", "error",
                    f"no active capacity rule for unit {unit.id} on {d.isoformat()}",
                    inventory_unit_id=unit.id, booking_item_id=bi.id,
                ))
                continue

            # Check days_of_week
            if d.isoweekday() not in (rule.days_of_week_json or []):
                continue  # Not an error, just skip this day

            # Validate rule
            rule_err = _validate_capacity_rule(rule)
            if rule_err:
                conflicts.append(_add_conflict(
                    run, "invalid_capacity_rule", "error",
                    f"invalid capacity rule {rule.id}: {rule_err}",
                    inventory_unit_id=unit.id, booking_item_id=bi.id,
                ))
                continue

            tf = _parse_time(rule.time_from)
            tt = _parse_time(rule.time_to)
            active_seconds = _time_to_seconds(tt) - _time_to_seconds(tf)
            loops = int(active_seconds // rule.loop_duration_seconds)

            # Rendition duration check
            valid_for_day = []
            for cr in renditions:
                rend = await db.get(Rendition, cr.rendition_id)
                if rend and rend.duration_seconds and rend.duration_seconds > rule.spot_duration_seconds:
                    continue  # Rendition too long for this slot
                valid_for_day.append(cr)
            if not valid_for_day:
                conflicts.append(_add_conflict(
                    run, "invalid_rendition", "error",
                    f"all renditions exceed spot_duration_seconds={rule.spot_duration_seconds}",
                    inventory_unit_id=unit.id, booking_item_id=bi.id,
                ))
                continue

            spots = min(bi.booked_spots_per_loop, rule.max_spots_per_loop)

            # Weighted round-robin through valid renditions
            rendition_index = 0
            weighted_renditions = []
            for cr in valid_for_day:
                weight = cr.weight if cr.weight and cr.weight > 0 else 1
                weighted_renditions.extend([cr] * weight)

            for loop_pos in range(loops):
                # Check approved slots for this loop_position
                occupied = await _get_approved_slots(
                    db, unit.id, d, loop_pos, exclude_run_id=run.id,
                )

                available_slots = sorted(
                    set(range(rule.max_spots_per_loop)) - occupied
                )

                if len(available_slots) < spots:
                    conflicts.append(_add_conflict(
                        run, "slot_conflict", "error",
                        f"only {len(available_slots)} free spots, need {spots} "
                        f"for unit {unit.id} on {d.isoformat()} loop {loop_pos}",
                        inventory_unit_id=unit.id, booking_item_id=bi.id,
                        details={
                            "date": d.isoformat(),
                            "loop_position": loop_pos,
                            "available": len(available_slots),
                            "required": spots,
                            "max_spots": rule.max_spots_per_loop,
                        },
                    ))
                    continue

                for spot_idx in range(spots):
                    spot = available_slots[spot_idx]
                    loop_start_sec = _time_to_seconds(tf) + loop_pos * rule.loop_duration_seconds
                    slot_start = loop_start_sec + spot * rule.spot_duration_seconds

                    t_from = (
                        datetime.min + timedelta(seconds=slot_start)
                    ).time()
                    t_to = (
                        datetime.min + timedelta(seconds=slot_start + rule.spot_duration_seconds)
                    ).time()

                    cr = weighted_renditions[rendition_index % len(weighted_renditions)] if weighted_renditions else valid_for_day[0]
                    rendition_index += 1

                    item = models.ScheduleItem(
                        schedule_run_id=run.id,
                        booking_item_id=bi.id,
                        inventory_unit_id=unit.id,
                        campaign_id=campaign.id,
                        campaign_rendition_id=cr.id,
                        rendition_id=cr.rendition_id,
                        date=d,
                        time_from=t_from,
                        time_to=t_to,
                        loop_position=loop_pos,
                        spot_position=spot,
                        spot_duration_seconds=rule.spot_duration_seconds,
                        priority=campaign.priority or 0,
                        weight=cr.weight if cr.weight and cr.weight > 0 else 1,
                    )
                    new_items.append(item)

    # ── Determine final status ────────────────────────────────────
    if new_items:
        db.add_all(new_items)
    if conflicts:
        db.add_all(conflicts)
        run.status = "has_conflicts"
    else:
        run.status = "generated"

    run.generated_by = user_id
    run.generated_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(run)
    return run


# ═══════════════════════════════════════════════════════════════════
#  Lifecycle
# ═══════════════════════════════════════════════════════════════════


async def approve_schedule_run(
    db: AsyncSession, run_id: UUID, user_id: UUID,
) -> models.ScheduleRun:
    run = await get_schedule_run(db, run_id)
    if run.status != "generated":
        raise HTTPException(
            400, f"Cannot approve schedule run in status '{run.status}' (must be 'generated')",
        )

    # Reload with items/conflicts
    run_with_data = await db.get(
        models.ScheduleRun, run_id,
        options=[
            selectinload(models.ScheduleRun.items),
            selectinload(models.ScheduleRun.conflicts),
        ],
    )
    if not run_with_data.items:
        raise HTTPException(400, "Cannot approve schedule run with no items")

    if _has_error_or_blocker(run_with_data.conflicts):
        raise HTTPException(
            400, "Cannot approve schedule run with error or blocker conflicts",
        )

    run.status = "approved"
    run.approved_by = user_id
    run.approved_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(run)
    return run


async def cancel_schedule_run(
    db: AsyncSession, run_id: UUID, user_id: UUID, user_perms: set[str],
) -> models.ScheduleRun:
    run = await get_schedule_run(db, run_id)
    if run.status == "cancelled":
        raise HTTPException(400, "Schedule run is already cancelled")

    if run.status == "approved":
        if "scheduling.approve" not in user_perms:
            raise HTTPException(
                403, "Cancelling approved schedule run requires scheduling.approve",
            )
    else:
        if "scheduling.manage" not in user_perms:
            raise HTTPException(
                403, "Cancelling schedule run requires scheduling.manage",
            )

    # Mark items as cancelled
    stmt = select(models.ScheduleItem).where(
        models.ScheduleItem.schedule_run_id == run_id,
    )
    result = await db.execute(stmt)
    for item in result.scalars().all():
        item.status = "cancelled"

    run.status = "cancelled"
    run.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(run)
    return run


# ═══════════════════════════════════════════════════════════════════
#  Items / Conflicts listing
# ═══════════════════════════════════════════════════════════════════


async def list_schedule_items(
    db: AsyncSession,
    run_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    inventory_unit_id: Optional[UUID] = None,
    campaign_id: Optional[UUID] = None,
) -> list[models.ScheduleItem]:
    stmt = select(models.ScheduleItem)
    if run_id:
        stmt = stmt.where(models.ScheduleItem.schedule_run_id == run_id)
    if date_from:
        stmt = stmt.where(models.ScheduleItem.date >= date_from)
    if date_to:
        stmt = stmt.where(models.ScheduleItem.date <= date_to)
    if inventory_unit_id:
        stmt = stmt.where(
            models.ScheduleItem.inventory_unit_id == inventory_unit_id,
        )
    if campaign_id:
        stmt = stmt.where(models.ScheduleItem.campaign_id == campaign_id)
    stmt = stmt.order_by(
        models.ScheduleItem.date,
        models.ScheduleItem.loop_position,
        models.ScheduleItem.spot_position,
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_schedule_conflicts(
    db: AsyncSession, run_id: UUID,
) -> list[models.ScheduleConflict]:
    run = await get_schedule_run(db, run_id)
    stmt = (
        select(models.ScheduleConflict)
        .where(models.ScheduleConflict.schedule_run_id == run_id)
        .order_by(models.ScheduleConflict.severity, models.ScheduleConflict.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
