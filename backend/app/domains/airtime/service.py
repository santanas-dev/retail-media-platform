"""Airtime occupancy and schedule conflict detection.

Planned occupancy (backend-only) — no physical KSO, no PoP facts.
Calculates how much airtime is booked vs available per device/placement/date range.

Status scoping:
  - Active: schedule NOT archived, campaign in (draft, pending_approval, approved)
  - Inactive: archived schedules, rejected/archived campaigns

RLS: advertiser sees aggregate occupancy + anonymized conflicts.
     Admin/security/manager sees full details.
"""

from datetime import date, time, datetime, timezone
from typing import Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.scheduling.models import Schedule, ScheduleSlot, KsoPlacement
from app.domains.campaigns.models import Campaign, CampaignCreative
from app.domains.media.models import Creative
from app.domains.hierarchy.models import KsoDevice
from app.domains.identity.models import User

# ── Status sets ────────────────────────────────────────────────────────────

_ACTIVE_CAMPAIGN_STATUSES = frozenset({"draft", "pending_approval", "approved"})
_INACTIVE_CAMPAIGN_STATUSES = frozenset({"rejected", "archived"})
_ACTIVE_SCHEDULE_STATUSES = frozenset({"draft"})  # archived excluded
_ACTIVE_PLACEMENT_STATUSES = frozenset({"draft"})

# ── Helpers ─────────────────────────────────────────────────────────────────

def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _minutes_to_slots(minutes: int) -> float:
    """Convert minutes to 30-second advertising slots."""
    return minutes * 2  # 2 slots per minute


def _slot_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """Check if two daily time windows overlap."""
    return a_start < b_end and a_end > b_start


def _date_overlap(a_from: date, a_to: date, b_from: date, b_to: date) -> bool:
    """Check if two date ranges overlap."""
    return a_from <= b_to and a_to >= b_from


def _day_overlap(days_a: set[int], days_b: set[int]) -> bool:
    """Check if two sets of weekdays overlap."""
    return bool(days_a & days_b)


# ── Occupancy Calculation ───────────────────────────────────────────────────


async def calculate_occupancy(
    db: AsyncSession,
    device_code: str,
    date_from: date,
    date_to: date,
    placement_code: Optional[str] = None,
) -> dict:
    """Calculate planned airtime occupancy for a device in a date range.

    Returns:
        device_code, date_from, date_to,
        total_available_minutes, occupied_minutes, free_minutes,
        occupancy_percent, campaign_count, creative_count, conflict_count
    """
    # Validate device exists
    dev_result = await db.execute(
        select(KsoDevice).where(KsoDevice.device_code == device_code)
    )
    device = dev_result.scalar_one_or_none()

    # Total available: all minutes in range (24h/day = 1440 min/day)
    days_in_range = (date_to - date_from).days + 1
    total_available_minutes = days_in_range * 1440

    # Find placements on this device within date range
    placement_filters = [
        KsoPlacement.device_code == device_code,
        KsoPlacement.status.in_(_ACTIVE_PLACEMENT_STATUSES),
        KsoPlacement.starts_at <= datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc),
        KsoPlacement.ends_at >= datetime(date_from.year, date_from.month, date_from.day, 0, 0, 0, tzinfo=timezone.utc),
    ]
    if placement_code:
        placement_filters.append(KsoPlacement.placement_code == placement_code)

    placements_result = await db.execute(
        select(KsoPlacement).where(and_(*placement_filters))
    )
    placements = placements_result.scalars().all()

    # Collect unique campaigns and creatives
    campaign_codes = set()
    creative_codes = set()
    for p in placements:
        if p.campaign_code:
            campaign_codes.add(p.campaign_code)
        if p.creative_code:
            creative_codes.add(p.creative_code)

    # Find active schedules linked to these campaigns, within date range
    occupied_minutes = 0
    conflicts_count = 0

    if campaign_codes:
        # Get schedules for these campaigns
        sched_result = await db.execute(
            select(Schedule)
            .options(selectinload(Schedule.slots))
            .where(
                Schedule.campaign_code.in_(campaign_codes),
                Schedule.status.in_(_ACTIVE_SCHEDULE_STATUSES),
                Schedule.valid_from <= date_to,
                Schedule.valid_to >= date_from,
            )
        )
        schedules = sched_result.scalars().all()

        # For each schedule, sum up active slot minutes per day
        for s in schedules:
            if not s.slots:
                continue
            sched_start = max(s.valid_from, date_from) if s.valid_from else date_from
            sched_end = min(s.valid_to, date_to) if s.valid_to else date_to
            sched_days = (sched_end - sched_start).days + 1

            for slot in s.slots:
                if not slot.is_active:
                    continue
                # Filter by placement if requested
                if placement_code and slot.placement_code != placement_code:
                    continue
                # Count only days where day_of_week falls within the schedule date range
                slot_minutes_per_day = _time_to_minutes(slot.end_time) - _time_to_minutes(slot.start_time)
                if slot_minutes_per_day <= 0:
                    continue
                # How many occurrences of this day_of_week in the schedule date range
                day_count = 0
                current = sched_start
                while current <= sched_end:
                    if current.weekday() == slot.day_of_week:
                        day_count += 1
                    # Move to next day
                    current = date(current.year, current.month, current.day)
                    try:
                        current = current.replace(day=current.day + 1)
                    except ValueError:
                        # Month rollover
                        if current.month == 12:
                            current = date(current.year + 1, 1, 1)
                        else:
                            current = date(current.year, current.month + 1, 1)
                occupied_minutes += slot_minutes_per_day * day_count

        # Count potential conflicts (simplified: number of overlapping placements)
        # Full conflict detection in detect_conflicts()
        conflicts_count = max(0, len(placements) - 1) if len(placements) > 1 else 0

    free_minutes = max(0, total_available_minutes - occupied_minutes)
    occupancy_percent = round((occupied_minutes / total_available_minutes * 100), 1) if total_available_minutes > 0 else 0.0

    return {
        "device_code": device_code,
        "placement_code": placement_code,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "total_available_minutes": total_available_minutes,
        "occupied_minutes": occupied_minutes,
        "free_minutes": free_minutes,
        "occupancy_percent": occupancy_percent,
        "campaign_count": len(campaign_codes),
        "creative_count": len(creative_codes),
        "conflict_count": conflicts_count,
        "is_planned": True,  # not PoP fact
    }


# ── Conflict Detection ──────────────────────────────────────────────────────


async def detect_conflicts(
    db: AsyncSession,
    device_code: str,
    date_from: date,
    date_to: date,
    campaign_code: Optional[str] = None,
    is_admin: bool = False,
) -> list[dict]:
    """Detect schedule slot conflicts on a device.

    A conflict exists when two active schedules have slots that:
    - Target the same device (via placement)
    - Overlap in date range
    - Share a day_of_week
    - Have overlapping time windows

    Args:
        is_admin: if False (advertiser), hide foreign campaign details.
    """
    conflicts = []

    # Find all placements on this device within date range
    placement_result = await db.execute(
        select(KsoPlacement).where(
            KsoPlacement.device_code == device_code,
            KsoPlacement.status.in_(_ACTIVE_PLACEMENT_STATUSES),
        )
    )
    placements = placement_result.scalars().all()
    if len(placements) < 2:
        return []

    # Get campaign details for each placement
    campaign_map: dict[str, dict] = {}
    for p in placements:
        if p.campaign_code and p.campaign_code not in campaign_map:
            camp_result = await db.execute(
                select(Campaign).where(Campaign.campaign_code == p.campaign_code)
            )
            camp = camp_result.scalar_one_or_none()
            if camp and camp.status in _ACTIVE_CAMPAIGN_STATUSES:
                campaign_map[p.campaign_code] = {
                    "campaign_code": camp.campaign_code,
                    "name": camp.name,
                    "advertiser_id": str(camp.advertiser_id) if camp.advertiser_id else None,
                    "status": camp.status,
                    "planned_start": camp.planned_start_date,
                    "planned_end": camp.planned_end_date,
                }

    # Get schedules for active campaigns
    active_codes = list(campaign_map.keys())
    if not active_codes:
        return []

    sched_result = await db.execute(
        select(Schedule)
        .options(selectinload(Schedule.slots))
        .where(
            Schedule.campaign_code.in_(active_codes),
            Schedule.status.in_(_ACTIVE_SCHEDULE_STATUSES),
        )
    )
    schedules = list(sched_result.scalars().all())

    # Filter to those overlapping the requested date range
    schedules = [
        s for s in schedules
        if s.valid_from and s.valid_to
        and _date_overlap(s.valid_from, s.valid_to, date_from, date_to)
    ]

    if campaign_code:
        schedules = [s for s in schedules if s.campaign_code == campaign_code]

    # Compare each pair of schedules
    for i in range(len(schedules)):
        for j in range(i + 1, len(schedules)):
            sa = schedules[i]
            sb = schedules[j]

            if sa.campaign_code == sb.campaign_code:
                continue  # same campaign is not a conflict

            # Compare slots
            for sl_a in (sa.slots or []):
                if not sl_a.is_active:
                    continue
                for sl_b in (sb.slots or []):
                    if not sl_b.is_active:
                        continue

                    # Same day_of_week?
                    if sl_a.day_of_week != sl_b.day_of_week:
                        continue

                    # Time window overlap?
                    if not _slot_overlap(sl_a.start_time, sl_a.end_time, sl_b.start_time, sl_b.end_time):
                        continue

                    # Conflict found!
                    camp_a = campaign_map.get(sa.campaign_code, {})
                    camp_b = campaign_map.get(sb.campaign_code, {})

                    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

                    conflict = {
                        "campaign_code": sa.campaign_code,
                        "campaign_name": camp_a.get("name", sa.campaign_code),
                        "conflict_with_code": sb.campaign_code,
                        "date_from": str(max(sa.valid_from, sb.valid_from)),
                        "date_to": str(min(sa.valid_to, sb.valid_to)),
                        "day_of_week": sl_a.day_of_week,
                        "day_label": day_names[sl_a.day_of_week],
                        "time_window": f"{sl_a.start_time}-{sl_a.end_time}",
                        "conflict_time_window": f"{sl_b.start_time}-{sl_b.end_time}",
                        "severity": "warning",
                    }

                    if is_admin:
                        conflict["conflict_campaign_name"] = camp_b.get("name", sb.campaign_code)

                    conflicts.append(conflict)
                    break  # one conflict per slot pair is enough
                if conflicts and conflicts[-1]["campaign_code"] == sa.campaign_code:
                    break  # one conflict per schedule pair

    return conflicts
