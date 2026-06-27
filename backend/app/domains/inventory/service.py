"""Inventory & Booking domain: business logic."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.inventory import models, schemas
from app.domains.channels.models import (
    DisplaySurface, LogicalCarrier, PhysicalDevice,
)
from app.domains.organization.models import Store, Cluster, Branch
from app.domains.campaigns.models import Campaign, CampaignChannel, CampaignTarget


# ═══════════════════════════════════════════════════════════════════
#  Inventory Units
# ═══════════════════════════════════════════════════════════════════


async def _validate_inventory_unit_store_consistency(
    db: AsyncSession,
    store_id: UUID,
    logical_carrier_id: Optional[UUID],
    display_surface_id: Optional[UUID],
) -> None:
    """Verify store_id matches the store of logical_carrier/display_surface."""
    # If logical_carrier is set, its physical device's store must match
    if logical_carrier_id:
        lc = await db.get(LogicalCarrier, logical_carrier_id)
        if lc is None:
            raise HTTPException(400, f"logical_carrier {logical_carrier_id} not found")
        pd = await db.get(PhysicalDevice, lc.physical_device_id)
        if pd is None:
            raise HTTPException(400, "logical_carrier has no physical_device")
        if pd.store_id != store_id:
            raise HTTPException(
                400,
                f"logical_carrier store ({pd.store_id}) != inventory_unit store ({store_id})",
            )

    # If display_surface is set, trace through logical_carrier → physical_device → store
    if display_surface_id:
        ds = await db.get(DisplaySurface, display_surface_id)
        if ds is None:
            raise HTTPException(400, f"display_surface {display_surface_id} not found")

        # If both set, display_surface must belong to same logical_carrier
        if logical_carrier_id and ds.logical_carrier_id != logical_carrier_id:
            raise HTTPException(
                400,
                "display_surface does not belong to the specified logical_carrier",
            )

        lc = await db.get(LogicalCarrier, ds.logical_carrier_id)
        if lc is None:
            raise HTTPException(400, "display_surface has no logical_carrier")
        pd = await db.get(PhysicalDevice, lc.physical_device_id)
        if pd is None:
            raise HTTPException(400, "display_surface logical_carrier has no physical_device")
        if pd.store_id != store_id:
            raise HTTPException(
                400,
                f"display_surface store ({pd.store_id}) != inventory_unit store ({store_id})",
            )


async def create_inventory_unit(
    db: AsyncSession, data: schemas.InventoryUnitCreate,
) -> models.InventoryUnit:
    # Validate FK existence
    from app.domains.channels.models import Channel as ChannelModel
    ch = await db.get(ChannelModel, data.channel_id)
    if ch is None:
        raise HTTPException(400, f"channel {data.channel_id} not found")
    st = await db.get(Store, data.store_id)
    if st is None:
        raise HTTPException(400, f"store {data.store_id} not found")

    # Validate sellable constraint
    if data.is_sellable and not data.logical_carrier_id and not data.display_surface_id:
        raise HTTPException(
            400,
            "is_sellable=true requires logical_carrier_id or display_surface_id",
        )

    # Validate store consistency
    await _validate_inventory_unit_store_consistency(
        db, data.store_id, data.logical_carrier_id, data.display_surface_id,
    )

    unit = models.InventoryUnit(**data.model_dump())
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return unit


async def list_inventory_units(
    db: AsyncSession,
    channel_id: Optional[UUID] = None,
    store_id: Optional[UUID] = None,
    status: Optional[str] = None,
    is_sellable: Optional[bool] = None,
    logical_carrier_id: Optional[UUID] = None,
    display_surface_id: Optional[UUID] = None,
) -> list[models.InventoryUnit]:
    stmt = select(models.InventoryUnit)
    if channel_id is not None:
        stmt = stmt.where(models.InventoryUnit.channel_id == channel_id)
    if store_id is not None:
        stmt = stmt.where(models.InventoryUnit.store_id == store_id)
    if status is not None:
        stmt = stmt.where(models.InventoryUnit.status == status)
    if is_sellable is not None:
        stmt = stmt.where(models.InventoryUnit.is_sellable == is_sellable)
    if logical_carrier_id is not None:
        stmt = stmt.where(models.InventoryUnit.logical_carrier_id == logical_carrier_id)
    if display_surface_id is not None:
        stmt = stmt.where(models.InventoryUnit.display_surface_id == display_surface_id)
    stmt = stmt.order_by(models.InventoryUnit.code)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_inventory_unit(db: AsyncSession, unit_id: UUID) -> models.InventoryUnit:
    unit = await db.get(models.InventoryUnit, unit_id)
    if unit is None:
        raise HTTPException(404, "Inventory unit not found")
    return unit


async def update_inventory_unit(
    db: AsyncSession, unit_id: UUID, data: schemas.InventoryUnitUpdate,
) -> models.InventoryUnit:
    unit = await get_inventory_unit(db, unit_id)
    update_data = data.model_dump(exclude_unset=True)

    # Validate store consistency if relevant fields changed
    store_id = update_data.get("store_id", unit.store_id)
    lc_id = update_data.get("logical_carrier_id", unit.logical_carrier_id)
    ds_id = update_data.get("display_surface_id", unit.display_surface_id)

    # If is_sellable is being set to true, validate
    is_sellable = update_data.get("is_sellable", unit.is_sellable)
    if is_sellable:
        effective_lc = lc_id if "logical_carrier_id" in update_data else unit.logical_carrier_id
        effective_ds = ds_id if "display_surface_id" in update_data else unit.display_surface_id
        if not effective_lc and not effective_ds:
            raise HTTPException(
                400,
                "is_sellable=true requires logical_carrier_id or display_surface_id",
            )

    # Only validate consistency if lc/ds/store changed
    if "logical_carrier_id" in update_data or "display_surface_id" in update_data or "store_id" in update_data:
        await _validate_inventory_unit_store_consistency(db, store_id, lc_id, ds_id)

    for key, value in update_data.items():
        setattr(unit, key, value)
    unit.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(unit)
    return unit


# ═══════════════════════════════════════════════════════════════════
#  Capacity Rules
# ═══════════════════════════════════════════════════════════════════


async def _check_overlapping_active_rules(
    db: AsyncSession,
    inventory_unit_id: UUID,
    valid_from: date,
    valid_to: date,
    exclude_id: Optional[UUID] = None,
) -> None:
    """Reject if another active rule overlaps with [valid_from, valid_to]."""
    stmt = select(models.CapacityRule).where(
        models.CapacityRule.inventory_unit_id == inventory_unit_id,
        models.CapacityRule.status == "active",
        models.CapacityRule.valid_from <= valid_to,
        models.CapacityRule.valid_to >= valid_from,
    )
    if exclude_id:
        stmt = stmt.where(models.CapacityRule.id != exclude_id)
    result = await db.execute(stmt)
    overlapping = result.scalars().first()
    if overlapping:
        raise HTTPException(
            400,
            f"Overlapping active capacity rule exists: {overlapping.id} "
            f"({overlapping.valid_from} to {overlapping.valid_to})",
        )


async def create_capacity_rule(
    db: AsyncSession, inventory_unit_id: UUID, data: schemas.CapacityRuleCreate,
) -> models.CapacityRule:
    unit = await get_inventory_unit(db, inventory_unit_id)

    await _check_overlapping_active_rules(
        db, inventory_unit_id, data.valid_from, data.valid_to,
    )

    rule = models.CapacityRule(
        inventory_unit_id=inventory_unit_id,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
        days_of_week_json=data.days_of_week_json,
        time_from=datetime.strptime(data.time_from, "%H:%M:%S").time() if isinstance(data.time_from, str) else data.time_from,
        time_to=datetime.strptime(data.time_to, "%H:%M:%S").time() if isinstance(data.time_to, str) else data.time_to,
        loop_duration_seconds=data.loop_duration_seconds,
        spot_duration_seconds=data.spot_duration_seconds,
        max_spots_per_loop=data.max_spots_per_loop,
        max_share_of_voice=data.max_share_of_voice,
        status=data.status,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_capacity_rules(
    db: AsyncSession, inventory_unit_id: UUID,
) -> list[models.CapacityRule]:
    unit = await get_inventory_unit(db, inventory_unit_id)
    stmt = (
        select(models.CapacityRule)
        .where(models.CapacityRule.inventory_unit_id == inventory_unit_id)
        .order_by(models.CapacityRule.valid_from)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_capacity_rule(
    db: AsyncSession, rule_id: UUID, data: schemas.CapacityRuleUpdate,
) -> models.CapacityRule:
    rule = await db.get(models.CapacityRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Capacity rule not found")
    unit = await get_inventory_unit(db, rule.inventory_unit_id)

    update_data = data.model_dump(exclude_unset=True)

    # Determine effective dates for overlap check
    vfrom = update_data.get("valid_from", rule.valid_from)
    vto = update_data.get("valid_to", rule.valid_to)
    new_status = update_data.get("status", rule.status)

    # Only check overlap if staying active (or becoming active)
    if new_status == "active":
        await _check_overlapping_active_rules(
            db, rule.inventory_unit_id, vfrom, vto, exclude_id=rule_id,
        )

    for key, value in update_data.items():
        if key in ("time_from", "time_to"):
            if isinstance(value, str):
                value = datetime.strptime(value, "%H:%M:%S").time()
        setattr(rule, key, value)
    rule.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(rule)
    return rule


# ═══════════════════════════════════════════════════════════════════
#  Availability calculation
# ═══════════════════════════════════════════════════════════════════


def _days_in_range(d_from: date, d_to: date) -> list[date]:
    """Return all dates from d_from to d_to inclusive."""
    return [d_from + timedelta(days=i) for i in range((d_to - d_from).days + 1)]


def _day_capacity(rule: models.CapacityRule, d: date) -> int:
    """Compute total spots for a capacity rule on a given day."""
    iso_dow = d.isoweekday()  # 1=Mon..7=Sun
    if iso_dow not in rule.days_of_week_json:
        return 0
    # Parse time range
    t_from = rule.time_from
    t_to = rule.time_to
    if isinstance(t_from, str):
        t_from = datetime.strptime(t_from, "%H:%M:%S").time()
    if isinstance(t_to, str):
        t_to = datetime.strptime(t_to, "%H:%M:%S").time()
    active_seconds = (
        timedelta(hours=t_to.hour, minutes=t_to.minute, seconds=t_to.second)
        - timedelta(hours=t_from.hour, minutes=t_from.minute, seconds=t_from.second)
    ).total_seconds()
    if active_seconds <= 0:
        return 0
    loops = int(active_seconds // rule.loop_duration_seconds)
    return loops * rule.max_spots_per_loop


async def _get_booked_spots(
    db: AsyncSession,
    inventory_unit_id: Optional[UUID],
    d_from: date,
    d_to: date,
    exclude_booking_id: Optional[UUID] = None,
    statuses: list[str] | None = None,
    reservation_types: list[str] | None = None,
) -> int:
    """Sum booked_spots_per_loop across booking_items in date range."""
    if statuses is None:
        statuses = ["reserved", "confirmed"]

    from app.domains.inventory.models import BookingItem, CampaignBooking

    stmt = (
        select(func.coalesce(func.sum(BookingItem.booked_spots_per_loop), 0))
        .join(CampaignBooking, CampaignBooking.id == BookingItem.booking_id)
        .where(
            BookingItem.date_from <= d_to,
            BookingItem.date_to >= d_from,
            CampaignBooking.status.in_(statuses),
        )
    )
    if inventory_unit_id is not None:
        stmt = stmt.where(BookingItem.inventory_unit_id == inventory_unit_id)
    if exclude_booking_id:
        stmt = stmt.where(BookingItem.booking_id != exclude_booking_id)
    if reservation_types:
        stmt = stmt.where(BookingItem.reservation_type.in_(reservation_types))
    result = await db.execute(stmt)
    return result.scalar() or 0


async def calculate_availability(
    db: AsyncSession, req: schemas.AvailabilityRequest,
) -> schemas.AvailabilityResponse:
    # Build unit filter
    stmt = select(models.InventoryUnit).where(
        models.InventoryUnit.status == "active",
        models.InventoryUnit.is_sellable == True,
    )
    if req.inventory_unit_ids:
        stmt = stmt.where(models.InventoryUnit.id.in_(req.inventory_unit_ids))
    if req.channel_id:
        stmt = stmt.where(models.InventoryUnit.channel_id == req.channel_id)
    if req.store_id:
        stmt = stmt.where(models.InventoryUnit.store_id == req.store_id)

    # Branch/cluster filter: find stores in branch/cluster
    if req.branch_id or req.cluster_id:
        store_stmt = select(Store.id).join(Cluster, Store.cluster_id == Cluster.id)
        if req.branch_id:
            store_stmt = store_stmt.where(Cluster.branch_id == req.branch_id)
        if req.cluster_id:
            store_stmt = store_stmt.where(Store.cluster_id == req.cluster_id)
        store_result = await db.execute(store_stmt)
        store_ids = [r[0] for r in store_result.all()]
        if store_ids:
            stmt = stmt.where(models.InventoryUnit.store_id.in_(store_ids))
        else:
            return schemas.AvailabilityResponse(items=[], summary=schemas.AvailabilitySummary(
                total_units=0, total_capacity=0, total_available=0,
                total_confirmed=0, total_reserved=0, occupancy_pct_avg=0.0,
                sold_out_units=0, limited_units=0,
            ))

    result = await db.execute(stmt)
    units = list(result.scalars().all())

    # Pre-load store names for all units
    store_ids = list({u.store_id for u in units})
    store_map: dict = {}
    if store_ids:
        store_result = await db.execute(select(Store).where(Store.id.in_(store_ids)))
        for s in store_result.scalars().all():
            store_map[str(s.id)] = s

    days = _days_in_range(req.date_from, req.date_to)
    items: list[schemas.AvailabilityItem] = []
    summary_stats = {"total_units": 0, "total_capacity": 0, "total_available": 0,
                     "total_confirmed": 0, "total_reserved": 0, "sold_out_units": 0,
                     "limited_units": 0}

    for unit in units:
        # Find active capacity rules overlapping the request period
        rules_stmt = select(models.CapacityRule).where(
            models.CapacityRule.inventory_unit_id == unit.id,
            models.CapacityRule.status == "active",
            models.CapacityRule.valid_from <= req.date_to,
            models.CapacityRule.valid_to >= req.date_from,
        )
        rules_result = await db.execute(rules_stmt)
        rules = list(rules_result.scalars().all())

        store_info = store_map.get(str(unit.store_id))
        store_code_val = store_info.store_code if store_info else None
        store_name_val = store_info.name if store_info else None

        if not rules:
            items.append(schemas.AvailabilityItem(
                inventory_unit_id=unit.id,
                inventory_unit_code=unit.code,
                store_code=store_code_val,
                store_name=store_name_val,
                capacity_total=0,
                confirmed_booked=0,
                reserved_booked=0,
                available=0,
                occupancy_pct=0.0,
                sold_out=False,
                status="unavailable",
                reasons=["Нет активных правил рекламной нагрузки на этот период"],
            ))
            summary_stats["total_units"] += 1
            continue

        # Total capacity across all days
        capacity_total = 0
        for d in days:
            for rule in rules:
                capacity_total += _day_capacity(rule, d)

        # Booked: confirmed + reserved
        confirmed_booked = await _get_booked_spots(
            db, unit.id, req.date_from, req.date_to,
            statuses=["confirmed"],
        )
        reserved_booked = await _get_booked_spots(
            db, unit.id, req.date_from, req.date_to,
            statuses=["reserved"],
        )
        internal_booked = await _get_booked_spots(
            db, unit.id, req.date_from, req.date_to,
            statuses=["confirmed", "reserved"],
            reservation_types=["internal"],
        )
        emergency_booked = await _get_booked_spots(
            db, unit.id, req.date_from, req.date_to,
            statuses=["confirmed", "reserved"],
            reservation_types=["emergency"],
        )

        available = capacity_total - confirmed_booked - reserved_booked
        occupancy_pct = round((confirmed_booked + reserved_booked) / max(capacity_total, 1) * 100, 1)

        reasons: list[str] = []
        alternatives: list[str] = []
        sold_out = False
        status = "available"

        if capacity_total == 0:
            status = "unavailable"
            reasons.append("Нет рекламного времени в выбранный период")
        elif available <= 0:
            status = "sold_out"
            sold_out = True
            reasons.append("Рекламное время полностью занято")
            alternatives.append("Попробуйте другой период или меньше КСО")
        elif occupancy_pct >= 90:
            status = "limited"
            reasons.append(f"Свободно менее 10% рекламного времени")
            alternatives.append("Доступны отдельные магазины с меньшей занятостью")
        elif occupancy_pct >= 70:
            status = "limited"
            reasons.append(f"Занято {occupancy_pct:.0f}% рекламного времени")

        # Business-language reasons
        if internal_booked > 0:
            reasons.append(f"Зарезервировано для внутренних нужд: {internal_booked} слотов")
        if emergency_booked > 0:
            reasons.append(f"Зарезервировано для экстренных показов: {emergency_booked} слотов")

        # Day-level check
        for d in days:
            day_cap = sum(_day_capacity(r, d) for r in rules)
            day_booked_conf = confirmed_booked // len(days) if days else 0
            day_booked_res = reserved_booked // len(days) if days else 0
            if day_cap > 0 and day_booked_conf + day_booked_res >= day_cap:
                reasons.append(f"Нет свободного времени {d.isoformat()}")
                if not alternatives:
                    alternatives.append(f"Попробуйте другие дни вместо {d.isoformat()}")

        items.append(schemas.AvailabilityItem(
            inventory_unit_id=unit.id,
            inventory_unit_code=unit.code,
            store_code=store_code_val,
            store_name=store_name_val,
            capacity_total=capacity_total,
            confirmed_booked=confirmed_booked,
            reserved_booked=reserved_booked,
            internal_booked=internal_booked,
            emergency_booked=emergency_booked,
            available=max(0, available),
            occupancy_pct=occupancy_pct,
            sold_out=sold_out,
            status=status,
            reasons=reasons[:5],
            alternatives=alternatives[:3],
        ))

        # Summary stats
        summary_stats["total_units"] += 1
        summary_stats["total_capacity"] += capacity_total
        summary_stats["total_available"] += max(0, available)
        summary_stats["total_confirmed"] += confirmed_booked
        summary_stats["total_reserved"] += reserved_booked
        if sold_out:
            summary_stats["sold_out_units"] += 1
        if status == "limited":
            summary_stats["limited_units"] += 1

    occupancy_pct_avg = (
        round(
            (summary_stats["total_confirmed"] + summary_stats["total_reserved"])
            / max(summary_stats["total_capacity"], 1) * 100, 1
        )
    )
    summary = schemas.AvailabilitySummary(
        total_units=summary_stats["total_units"],
        total_capacity=summary_stats["total_capacity"],
        total_available=summary_stats["total_available"],
        total_confirmed=summary_stats["total_confirmed"],
        total_reserved=summary_stats["total_reserved"],
        occupancy_pct_avg=occupancy_pct_avg,
        sold_out_units=summary_stats["sold_out_units"],
        limited_units=summary_stats["limited_units"],
    )

    return schemas.AvailabilityResponse(items=items, summary=summary)


# ═══════════════════════════════════════════════════════════════════
#  Bookings
# ═══════════════════════════════════════════════════════════════════


async def _validate_campaign_for_booking(
    db: AsyncSession, campaign_id: UUID, action: str,
) -> Campaign:
    """Load campaign and validate it's eligible for booking actions."""
    campaign = await db.get(
        Campaign,
        campaign_id,
        options=[selectinload(Campaign.channels), selectinload(Campaign.targets), selectinload(Campaign.renditions)],
    )
    if campaign is None:
        raise HTTPException(404, "Campaign not found")

    if action == "create":
        if campaign.status not in ("in_review", "approved"):
            raise HTTPException(
                400,
                f"Booking can only be created for in_review or approved campaigns (status: {campaign.status})",
            )
    elif action == "reserve":
        if campaign.status not in ("in_review", "approved"):
            raise HTTPException(
                400,
                f"Booking can only be reserved for in_review or approved campaigns (status: {campaign.status})",
            )
    elif action == "confirm":
        if campaign.status != "approved":
            raise HTTPException(
                400,
                f"Booking can only be confirmed for approved campaigns (status: {campaign.status})",
            )

    # Campaign must have channels, targets, renditions
    if not campaign.channels:
        raise HTTPException(400, "Campaign has no channels")
    if not campaign.targets:
        raise HTTPException(400, "Campaign has no targets")
    if not campaign.renditions:
        raise HTTPException(400, "Campaign has no renditions")

    return campaign


def _booking_dates_valid(booking_dates: tuple, campaign: Campaign) -> None:
    """Check booking dates against campaign planned dates."""
    b_from, b_to = booking_dates
    if campaign.planned_start_date and b_from < campaign.planned_start_date:
        raise HTTPException(
            400,
            f"booking date_from ({b_from}) before campaign planned_start_date ({campaign.planned_start_date})",
        )
    if campaign.planned_end_date and b_to > campaign.planned_end_date:
        raise HTTPException(
            400,
            f"booking date_to ({b_to}) after campaign planned_end_date ({campaign.planned_end_date})",
        )


def _target_matches(
    unit: models.InventoryUnit, targets: list[CampaignTarget],
) -> bool:
    """Check if inventory unit matches at least one campaign target."""
    for t in targets:
        if t.target_type == "all_stores":
            return True
        elif t.target_type == "store":
            if unit.store_id == t.store_id:
                return True
        elif t.target_type == "cluster":
            # unit.store.cluster_id == t.cluster_id — checked at DB level below
            if t.cluster_id:
                return True  # Will be verified by cluster_id matching
        elif t.target_type == "branch":
            if t.branch_id:
                return True  # Will be verified by branch_id matching
        elif t.target_type == "logical_carrier":
            if unit.logical_carrier_id == t.logical_carrier_id:
                return True
        elif t.target_type == "display_surface":
            if unit.display_surface_id == t.display_surface_id:
                return True
    return False


async def _validate_target_matching(
    db: AsyncSession,
    unit: models.InventoryUnit,
    targets: list[CampaignTarget],
) -> None:
    """Full target matching with store→cluster→branch chain validation."""
    store = await db.get(Store, unit.store_id)
    if store is None:
        raise HTTPException(400, f"store {unit.store_id} not found")
    cluster = await db.get(Cluster, store.cluster_id)
    if cluster is None:
        raise HTTPException(400, f"cluster {store.cluster_id} not found")

    for t in targets:
        if t.target_type == "all_stores":
            return  # matches everything
        elif t.target_type == "store":
            if unit.store_id == t.store_id:
                return
        elif t.target_type == "cluster":
            if store.cluster_id == t.cluster_id:
                return
        elif t.target_type == "branch":
            if cluster.branch_id == t.branch_id:
                return
        elif t.target_type == "logical_carrier":
            if unit.logical_carrier_id == t.logical_carrier_id:
                return
        elif t.target_type == "display_surface":
            if unit.display_surface_id == t.display_surface_id:
                return

    raise HTTPException(
        400,
        f"inventory unit {unit.id} does not match any campaign target",
    )


async def _validate_capacity(
    db: AsyncSession,
    inventory_unit_id: UUID,
    date_from: date,
    date_to: date,
    booked_spots_per_loop: int,
    exclude_booking_id: Optional[UUID] = None,
) -> None:
    """Check that booked_spots_per_loop doesn't exceed capacity."""
    # Find active capacity rules
    rules_stmt = select(models.CapacityRule).where(
        models.CapacityRule.inventory_unit_id == inventory_unit_id,
        models.CapacityRule.status == "active",
        models.CapacityRule.valid_from <= date_to,
        models.CapacityRule.valid_to >= date_from,
    )
    rules_result = await db.execute(rules_stmt)
    rules = list(rules_result.scalars().all())
    if not rules:
        raise HTTPException(400, "No active capacity rule for this inventory unit in the period")

    # Single rule assumption (no overlapping rules)
    rule = rules[0]

    if booked_spots_per_loop > rule.max_spots_per_loop:
        raise HTTPException(
            400,
            f"booked_spots_per_loop ({booked_spots_per_loop}) exceeds "
            f"max_spots_per_loop ({rule.max_spots_per_loop})",
        )

    # Check share of voice
    if rule.max_share_of_voice < 1.0:
        sov = booked_spots_per_loop / rule.max_spots_per_loop
        # Get existing booked share
        existing_confirmed = await _get_booked_spots(
            db, inventory_unit_id, date_from, date_to,
            exclude_booking_id=exclude_booking_id,
            statuses=["confirmed"],
        )
        existing_reserved = await _get_booked_spots(
            db, inventory_unit_id, date_from, date_to,
            exclude_booking_id=exclude_booking_id,
            statuses=["reserved"],
        )
        total_booked = existing_confirmed + existing_reserved + booked_spots_per_loop
        total_sov = total_booked / rule.max_spots_per_loop
        if total_sov > 1.0:
            raise HTTPException(
                400,
                f"Total share of voice would exceed 100%: "
                f"existing={existing_confirmed + existing_reserved}, "
                f"new={booked_spots_per_loop}, max={rule.max_spots_per_loop}",
            )
        if sov > float(rule.max_share_of_voice):
            raise HTTPException(
                400,
                f"share of voice ({sov:.2f}) exceeds max ({rule.max_share_of_voice})",
            )


async def _validate_channel_in_campaign(
    db: AsyncSession,
    campaign_id: UUID,
    unit_channel_id: UUID,
) -> None:
    """Check inventory_unit.channel_id is in campaign_channels."""
    stmt = select(CampaignChannel).where(
        CampaignChannel.campaign_id == campaign_id,
        CampaignChannel.channel_id == unit_channel_id,
    )
    result = await db.execute(stmt)
    if result.scalars().first() is None:
        raise HTTPException(
            400,
            f"inventory unit channel ({unit_channel_id}) is not in campaign channels",
        )


async def create_booking(
    db: AsyncSession, data: schemas.BookingCreate, user_id: UUID,
) -> models.CampaignBooking:
    campaign = await _validate_campaign_for_booking(db, data.campaign_id, "create")
    _booking_dates_valid((data.date_from, data.date_to), campaign)

    booking = models.CampaignBooking(
        campaign_id=data.campaign_id,
        date_from=data.date_from,
        date_to=data.date_to,
        created_by=user_id,
        comment=data.comment,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


async def list_bookings(
    db: AsyncSession,
    campaign_id: Optional[UUID] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[models.CampaignBooking]:
    stmt = select(models.CampaignBooking)
    if campaign_id is not None:
        stmt = stmt.where(models.CampaignBooking.campaign_id == campaign_id)
    if status is not None:
        stmt = stmt.where(models.CampaignBooking.status == status)
    if date_from is not None:
        stmt = stmt.where(models.CampaignBooking.date_to >= date_from)
    if date_to is not None:
        stmt = stmt.where(models.CampaignBooking.date_from <= date_to)
    stmt = stmt.order_by(models.CampaignBooking.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_booking(db: AsyncSession, booking_id: UUID) -> models.CampaignBooking:
    booking = await db.get(models.CampaignBooking, booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    return booking


async def update_booking(
    db: AsyncSession, booking_id: UUID, data: schemas.BookingUpdate,
) -> models.CampaignBooking:
    booking = await get_booking(db, booking_id)
    if booking.status != "draft":
        raise HTTPException(400, f"Only draft bookings can be edited (status: {booking.status})")

    update_data = data.model_dump(exclude_unset=True)

    # Validate dates against campaign
    if "date_from" in update_data or "date_to" in update_data:
        campaign = await db.get(Campaign, booking.campaign_id)
        if campaign is None:
            raise HTTPException(404, "Campaign not found")
        b_from = update_data.get("date_from", booking.date_from)
        b_to = update_data.get("date_to", booking.date_to)
        _booking_dates_valid((b_from, b_to), campaign)

    for key, value in update_data.items():
        setattr(booking, key, value)
    booking.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(booking)
    return booking


async def reserve_booking(
    db: AsyncSession, booking_id: UUID,
) -> models.CampaignBooking:
    booking = await get_booking(db, booking_id)
    if booking.status != "draft":
        raise HTTPException(400, f"Only draft bookings can be reserved (status: {booking.status})")

    campaign = await _validate_campaign_for_booking(db, booking.campaign_id, "reserve")

    # Must have items
    if not booking.items:
        raise HTTPException(400, "Booking has no items")

    # Validate items against capacity (reserved counts)
    for item in booking.items:
        unit = await db.get(models.InventoryUnit, item.inventory_unit_id)
        if unit is None:
            raise HTTPException(400, f"inventory unit {item.inventory_unit_id} not found")
        await _validate_capacity(
            db, item.inventory_unit_id, item.date_from, item.date_to,
            item.booked_spots_per_loop, exclude_booking_id=booking.id,
        )

    booking.status = "reserved"
    booking.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(booking)
    return booking


async def confirm_booking(
    db: AsyncSession, booking_id: UUID, user_id: UUID,
) -> models.CampaignBooking:
    booking = await get_booking(db, booking_id)
    if booking.status != "reserved":
        raise HTTPException(400, f"Only reserved bookings can be confirmed (status: {booking.status})")

    campaign = await _validate_campaign_for_booking(db, booking.campaign_id, "confirm")

    if not booking.items:
        raise HTTPException(400, "Booking has no items")

    # Re-validate items against capacity (confirmed counts, exclude self same as reserve)
    for item in booking.items:
        unit = await db.get(models.InventoryUnit, item.inventory_unit_id)
        if unit is None:
            raise HTTPException(400, f"inventory unit {item.inventory_unit_id} not found")
        await _validate_capacity(
            db, item.inventory_unit_id, item.date_from, item.date_to,
            item.booked_spots_per_loop, exclude_booking_id=booking.id,
        )

    booking.status = "confirmed"
    booking.approved_by = user_id
    booking.approved_at = datetime.utcnow()
    booking.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(booking)
    return booking


async def cancel_booking(
    db: AsyncSession, booking_id: UUID,
) -> models.CampaignBooking:
    booking = await get_booking(db, booking_id)
    if booking.status not in ("reserved", "confirmed"):
        raise HTTPException(
            400,
            f"Only reserved or confirmed bookings can be cancelled (status: {booking.status})",
        )
    booking.status = "cancelled"
    booking.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(booking)
    return booking


# ═══════════════════════════════════════════════════════════════════
#  Booking Items
# ═══════════════════════════════════════════════════════════════════


async def list_booking_items(
    db: AsyncSession, booking_id: UUID,
) -> list[models.BookingItem]:
    booking = await get_booking(db, booking_id)
    stmt = (
        select(models.BookingItem)
        .where(models.BookingItem.booking_id == booking_id)
        .order_by(models.BookingItem.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_booking_items(
    db: AsyncSession, booking_id: UUID, data: schemas.BookingItemsUpdate,
) -> list[models.BookingItem]:
    booking = await get_booking(db, booking_id)
    if booking.status != "draft":
        raise HTTPException(400, f"Items can only be edited for draft bookings (status: {booking.status})")

    campaign = await _validate_campaign_for_booking(db, booking.campaign_id, "create")

    # Delete existing items
    for item in list(booking.items):
        await db.delete(item)
    await db.flush()

    # Validate and create new items
    new_items: list[models.BookingItem] = []
    seen_unit_ids: set[UUID] = set()

    for item_req in data.items:
        # Deduplicate
        if item_req.inventory_unit_id in seen_unit_ids:
            raise HTTPException(400, f"Duplicate inventory_unit_id: {item_req.inventory_unit_id}")
        seen_unit_ids.add(item_req.inventory_unit_id)

        unit = await db.get(models.InventoryUnit, item_req.inventory_unit_id)
        if unit is None:
            raise HTTPException(400, f"inventory unit {item_req.inventory_unit_id} not found")

        if unit.status != "active":
            raise HTTPException(400, f"inventory unit {item_req.inventory_unit_id} is not active")
        if not unit.is_sellable:
            raise HTTPException(400, f"inventory unit {item_req.inventory_unit_id} is not sellable")

        # Validate channel in campaign
        await _validate_channel_in_campaign(db, booking.campaign_id, unit.channel_id)

        # Validate target matching
        await _validate_target_matching(db, unit, campaign.targets)

        # Validate dates
        if item_req.date_from < booking.date_from or item_req.date_to > booking.date_to:
            raise HTTPException(
                400,
                "booking item dates must be within booking date range",
            )
        if campaign.planned_start_date and item_req.date_from < campaign.planned_start_date:
            raise HTTPException(
                400,
                f"item date_from before campaign planned_start_date",
            )
        if campaign.planned_end_date and item_req.date_to > campaign.planned_end_date:
            raise HTTPException(
                400,
                f"item date_to after campaign planned_end_date",
            )

        bi = models.BookingItem(
            booking_id=booking_id,
            inventory_unit_id=item_req.inventory_unit_id,
            booked_spots_per_loop=item_req.booked_spots_per_loop,
            booked_share_of_voice=item_req.booked_share_of_voice,
            reservation_type=item_req.reservation_type,
            date_from=item_req.date_from,
            date_to=item_req.date_to,
        )
        db.add(bi)
        new_items.append(bi)

    await db.commit()
    # Refresh all items
    stmt = (
        select(models.BookingItem)
        .where(models.BookingItem.booking_id == booking_id)
        .order_by(models.BookingItem.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════
#  Forecast v1
# ═══════════════════════════════════════════════════════════════════


async def _get_active_device_count(
    db: AsyncSession,
    channel_id: Optional[UUID] = None,
    store_id: Optional[UUID] = None,
    branch_id: Optional[UUID] = None,
    cluster_id: Optional[UUID] = None,
) -> tuple[int, int]:
    """Return (total_devices, active_devices) matching scope."""
    from app.domains.hierarchy.models import KsoDevice

    stmt = select(func.count(KsoDevice.id)).where(
        KsoDevice.status != "decommissioned",
    )
    if store_id:
        store_ids = [store_id]
    elif branch_id or cluster_id:
        store_stmt = select(Store.id).join(Cluster, Store.cluster_id == Cluster.id)
        if branch_id:
            store_stmt = store_stmt.where(Cluster.branch_id == branch_id)
        if cluster_id:
            store_stmt = store_stmt.where(Store.cluster_id == cluster_id)
        store_result = await db.execute(store_stmt)
        store_ids = [r[0] for r in store_result.all()]
        if not store_ids:
            return 0, 0
    else:
        store_ids = None

    if store_ids:
        stmt = stmt.where(KsoDevice.store_id.in_(store_ids))

    total_result = await db.execute(stmt)
    total_devices = total_result.scalar() or 0

    active_stmt = stmt.where(KsoDevice.status == "active")
    active_result = await db.execute(active_stmt)
    active_devices = active_result.scalar() or 0

    return total_devices, active_devices


async def calculate_forecast(
    db: AsyncSession, req: schemas.ForecastRequest,
) -> schemas.ForecastResponse:
    """Forecast v1 — estimate expected impressions from schedule and device count.

    Formula: devices × active_capacity_rules × spots_per_loop × days.
    Does NOT use actual traffic/check data — marked as low confidence.
    """
    # Count devices in scope
    total_devices, active_devices = await _get_active_device_count(
        db, req.channel_id, req.store_id, req.branch_id, req.cluster_id,
    )

    # Count sellable inventory units with active capacity rules in period
    unit_stmt = select(func.count(models.InventoryUnit.id)).where(
        models.InventoryUnit.status == "active",
        models.InventoryUnit.is_sellable == True,
    )
    if req.channel_id:
        unit_stmt = unit_stmt.where(models.InventoryUnit.channel_id == req.channel_id)
    if req.store_id:
        unit_stmt = unit_stmt.where(models.InventoryUnit.store_id == req.store_id)
    unit_result = await db.execute(unit_stmt)
    sellable_units = unit_result.scalar() or 0

    # Sum capacity spots from active rules
    rules_stmt = (
        select(func.coalesce(func.sum(models.CapacityRule.max_spots_per_loop), 0))
        .join(models.InventoryUnit, models.CapacityRule.inventory_unit_id == models.InventoryUnit.id)
        .where(
            models.InventoryUnit.status == "active",
            models.InventoryUnit.is_sellable == True,
            models.CapacityRule.status == "active",
            models.CapacityRule.valid_from <= req.date_to,
            models.CapacityRule.valid_to >= req.date_from,
        )
    )
    if req.channel_id:
        rules_stmt = rules_stmt.where(models.InventoryUnit.channel_id == req.channel_id)
    if req.store_id:
        rules_stmt = rules_stmt.where(models.InventoryUnit.store_id == req.store_id)

    rules_result = await db.execute(rules_stmt)
    total_capacity_spots = rules_result.scalar() or 0

    days = (req.date_to - req.date_from).days + 1

    # Simple formula: capacity spots × request spots × days
    expected_impressions = total_capacity_spots * req.spots_per_loop * days

    # Estimate occupancy from confirmed+reserved vs max
    confirmed_booked = await _get_booked_spots(
        db, None, req.date_from, req.date_to,  # None = sum across all
        statuses=["confirmed"],
    )
    reserved_booked = await _get_booked_spots(
        db, None, req.date_from, req.date_to,
        statuses=["reserved"],
    )
    total_max = total_capacity_spots * days
    occupancy_estimate_pct = (
        round((confirmed_booked + reserved_booked) / max(total_max, 1) * 100, 1)
    )

    return schemas.ForecastResponse(
        date_from=req.date_from,
        date_to=req.date_to,
        total_devices=total_devices,
        active_devices=active_devices,
        total_capacity_spots=total_capacity_spots,
        expected_impressions=expected_impressions,
        occupancy_estimate_pct=occupancy_estimate_pct,
    )


# ═══════════════════════════════════════════════════════════════════
#  Inventory Snapshot (scope-level)
# ═══════════════════════════════════════════════════════════════════


async def get_inventory_snapshot(
    db: AsyncSession,
    branch_id: Optional[UUID] = None,
    cluster_id: Optional[UUID] = None,
    store_id: Optional[UUID] = None,
) -> dict:
    """Aggregate inventory snapshot for scope-level dashboard."""
    # Build unit filter
    stmt = select(models.InventoryUnit).where(
        models.InventoryUnit.status == "active",
        models.InventoryUnit.is_sellable == True,
    )

    if store_id:
        stmt = stmt.where(models.InventoryUnit.store_id == store_id)
    elif branch_id or cluster_id:
        store_stmt = select(Store.id).join(Cluster, Store.cluster_id == Cluster.id)
        if branch_id:
            store_stmt = store_stmt.where(Cluster.branch_id == branch_id)
        if cluster_id:
            store_stmt = store_stmt.where(Store.cluster_id == cluster_id)
        store_result = await db.execute(store_stmt)
        store_ids = [r[0] for r in store_result.all()]
        if store_ids:
            stmt = stmt.where(models.InventoryUnit.store_id.in_(store_ids))
        else:
            return {"total_units": 0, "total_kso_devices": 0, "active_kso_devices": 0,
                    "sellable_units": 0, "with_rules": 0, "with_bookings": 0}

    result = await db.execute(stmt)
    units = list(result.scalars().all())

    today = date.today()
    far_future = today + timedelta(days=365)

    unit_ids = [u.id for u in units]
    store_ids = list({u.store_id for u in units})

    # Count units with active capacity rules
    if unit_ids:
        rules_count_stmt = select(func.count(func.distinct(models.CapacityRule.inventory_unit_id))).where(
            models.CapacityRule.inventory_unit_id.in_(unit_ids),
            models.CapacityRule.status == "active",
            models.CapacityRule.valid_from <= far_future,
            models.CapacityRule.valid_to >= today,
        )
        rules_count_result = await db.execute(rules_count_stmt)
        with_rules = rules_count_result.scalar() or 0

        # Count units with active bookings
        bookings_count_stmt = (
            select(func.count(func.distinct(models.BookingItem.inventory_unit_id)))
            .join(models.CampaignBooking, models.CampaignBooking.id == models.BookingItem.booking_id)
            .where(
                models.BookingItem.inventory_unit_id.in_(unit_ids),
                models.BookingItem.date_from <= far_future,
                models.BookingItem.date_to >= today,
                models.CampaignBooking.status.in_(["confirmed", "reserved"]),
            )
        )
        bookings_count_result = await db.execute(bookings_count_stmt)
        with_bookings = bookings_count_result.scalar() or 0
    else:
        with_rules = 0
        with_bookings = 0

    # Count KSO devices
    from app.domains.hierarchy.models import KsoDevice
    device_stmt = select(func.count(KsoDevice.id)).where(
        KsoDevice.status != "decommissioned",
    )
    if store_ids:
        device_stmt = device_stmt.where(KsoDevice.store_id.in_(store_ids))
    device_result = await db.execute(device_stmt)
    total_kso_devices = device_result.scalar() or 0

    active_stmt = device_stmt.where(KsoDevice.status == "active")
    active_result = await db.execute(active_stmt)
    active_kso_devices = active_result.scalar() or 0

    return {
        "total_units": len(units),
        "total_kso_devices": total_kso_devices,
        "active_kso_devices": active_kso_devices,
        "sellable_units": len(units),
        "with_rules": with_rules,
        "with_bookings": with_bookings,
    }
