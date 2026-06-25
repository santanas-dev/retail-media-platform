"""Scheduling domain: business logic (Step 37.5).

Test KSO vertical slice — minimal placement with conflict guard.
No inventory planning, airtime booking, or commercial scheduling.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.scheduling import models, schemas
from app.domains.campaigns.models import Campaign, CampaignCreative
from app.domains.media.models import Creative
from app.domains.hierarchy.models import KsoDevice

# Statuses that allow time-window overlap (ended / rejected)
_NON_CONFLICT_STATUSES = frozenset({"cancelled", "rejected"})


async def _get_campaign_or_404(db: AsyncSession, campaign_code: str) -> Campaign:
    result = await db.execute(
        select(Campaign).where(Campaign.campaign_code == campaign_code)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign '{campaign_code}' not found",
        )
    return campaign


async def _get_creative_or_404(db: AsyncSession, creative_code: str) -> Creative:
    result = await db.execute(
        select(Creative).where(Creative.creative_code == creative_code)
    )
    creative = result.scalar_one_or_none()
    if not creative:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Creative '{creative_code}' not found",
        )
    return creative


async def _get_device_or_404(db: AsyncSession, device_code: str) -> KsoDevice:
    result = await db.execute(
        select(KsoDevice).where(KsoDevice.device_code == device_code)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_code}' not found",
        )
    return device


async def _check_creative_belongs_to_campaign(
    db: AsyncSession, campaign_code: str, creative_code: str,
) -> None:
    """Verify creative_code is linked to campaign_code via CampaignCreative."""
    result = await db.execute(
        select(CampaignCreative.id).where(
            CampaignCreative.campaign.has(Campaign.campaign_code == campaign_code),
            CampaignCreative.creative_code == creative_code,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Creative '{creative_code}' is not linked to campaign '{campaign_code}'",
        )


async def _check_conflict(
    db: AsyncSession,
    device_code: str,
    starts_at: datetime,
    ends_at: datetime,
    exclude_placement_code: str | None = None,
) -> None:
    """Verify no active placement overlaps on the same device."""
    stmt = select(models.KsoPlacement).where(
        models.KsoPlacement.device_code == device_code,
        models.KsoPlacement.status.notin_(_NON_CONFLICT_STATUSES),
        models.KsoPlacement.starts_at < ends_at,
        models.KsoPlacement.ends_at > starts_at,
    )
    result = await db.execute(stmt)
    overlaps = result.scalars().all()
    for overlap in overlaps:
        if exclude_placement_code and overlap.placement_code == exclude_placement_code:
            continue
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Time overlap with placement '{overlap.placement_code}' on device '{device_code}'",
        )


async def list_placements(
    db: AsyncSession, skip: int = 0, limit: int = 100,
) -> list[dict]:
    result = await db.execute(
        select(models.KsoPlacement)
        .order_by(models.KsoPlacement.created_at.desc())
        .offset(skip).limit(limit)
    )
    placements = result.scalars().all()
    return [
        {
            "placement_code": p.placement_code,
            "campaign_code": p.campaign_code,
            "creative_code": p.creative_code,
            "device_code": p.device_code,
            "status": p.status,
            "starts_at": p.starts_at,
            "ends_at": p.ends_at,
            "slot_order": p.slot_order,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in placements
    ]


async def get_placement(
    db: AsyncSession, placement_code: str,
) -> dict:
    result = await db.execute(
        select(models.KsoPlacement).where(
            models.KsoPlacement.placement_code == placement_code,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placement '{placement_code}' not found",
        )
    return {
        "placement_code": p.placement_code,
        "campaign_code": p.campaign_code,
        "creative_code": p.creative_code,
        "device_code": p.device_code,
        "status": p.status,
        "starts_at": p.starts_at,
        "ends_at": p.ends_at,
        "slot_order": p.slot_order,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


async def create_placement(
    db: AsyncSession,
    data: schemas.KsoPlacementCreate,
    user_id,
) -> dict:
    """Create a KsoPlacement with full validation chain."""
    # 1. Validate campaign exists
    await _get_campaign_or_404(db, data.campaign_code)

    # 2. Validate creative exists
    await _get_creative_or_404(db, data.creative_code)

    # 3. Validate creative belongs to campaign
    await _check_creative_belongs_to_campaign(
        db, data.campaign_code, data.creative_code,
    )

    # 4. Validate device exists
    await _get_device_or_404(db, data.device_code)

    # 5. Check placement_code uniqueness
    existing = await db.execute(
        select(models.KsoPlacement.id).where(
            models.KsoPlacement.placement_code == data.placement_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Placement code '{data.placement_code}' already exists",
        )

    # 6. Conflict guard — overlapping placements on same device
    await _check_conflict(
        db, data.device_code, data.starts_at, data.ends_at,
    )

    # 7. Create
    placement = models.KsoPlacement(
        placement_code=data.placement_code,
        campaign_code=data.campaign_code,
        creative_code=data.creative_code,
        device_code=data.device_code,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        status="draft",
        slot_order=data.slot_order,
        created_by=user_id,
    )
    db.add(placement)
    await db.commit()
    await db.refresh(placement)

    return {
        "placement_code": placement.placement_code,
        "campaign_code": placement.campaign_code,
        "creative_code": placement.creative_code,
        "device_code": placement.device_code,
        "status": placement.status,
        "starts_at": placement.starts_at,
        "ends_at": placement.ends_at,
        "slot_order": placement.slot_order,
        "created_at": placement.created_at,
        "updated_at": placement.updated_at,
    }


async def update_placement(
    db: AsyncSession, placement_code: str, data: schemas.KsoPlacementUpdate,
) -> dict:
    """Update placement mutable fields."""
    result = await db.execute(
        select(models.KsoPlacement).where(
            models.KsoPlacement.placement_code == placement_code,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Placement not found")
    if p.status == "archived":
        raise HTTPException(status_code=400, detail="Placement is archived")

    if data.starts_at is not None:
        p.starts_at = data.starts_at
    if data.ends_at is not None:
        p.ends_at = data.ends_at
    if data.slot_order is not None:
        p.slot_order = data.slot_order
    p.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(p)
    return {
        "placement_code": p.placement_code,
        "campaign_code": p.campaign_code,
        "creative_code": p.creative_code,
        "device_code": p.device_code,
        "status": p.status,
        "starts_at": p.starts_at,
        "ends_at": p.ends_at,
        "slot_order": p.slot_order,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


async def archive_placement(
    db: AsyncSession, placement_code: str,
) -> dict:
    """Archive a placement (status → archived)."""
    result = await db.execute(
        select(models.KsoPlacement).where(
            models.KsoPlacement.placement_code == placement_code,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Placement not found")
    if p.status == "archived":
        raise HTTPException(status_code=400, detail="Placement already archived")
    p.status = "archived"
    p.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(p)
    return {
        "placement_code": p.placement_code,
        "campaign_code": p.campaign_code,
        "creative_code": p.creative_code,
        "device_code": p.device_code,
        "status": p.status,
        "starts_at": p.starts_at,
        "ends_at": p.ends_at,
        "slot_order": p.slot_order,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Schedule + ScheduleSlot production API (39.1.3)
# ═══════════════════════════════════════════════════════════════════════════

def _schedule_to_dict(s: models.Schedule) -> dict:
    return {
        "schedule_code": s.schedule_code, "name": s.name,
        "status": s.status, "campaign_code": s.campaign_code,
        "valid_from": s.valid_from, "valid_to": s.valid_to,
        "timezone": s.timezone,
        "slot_count": len(s.slots) if s.slots else 0,
        "created_at": s.created_at, "updated_at": s.updated_at,
    }


def _slot_to_dict(sl: models.ScheduleSlot, schedule_code: str) -> dict:
    return {
        "slot_code": sl.slot_code, "schedule_code": schedule_code,
        "placement_code": sl.placement_code,
        "day_of_week": sl.day_of_week,
        "start_time": sl.start_time, "end_time": sl.end_time,
        "slot_order": sl.slot_order, "is_active": sl.is_active,
        "created_at": sl.created_at, "updated_at": sl.updated_at,
    }


async def _get_schedule_or_404(
    db: AsyncSession, schedule_code: str,
) -> models.Schedule:
    result = await db.execute(
        select(models.Schedule)
        .options(selectinload(models.Schedule.slots))
        .where(models.Schedule.schedule_code == schedule_code)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return s


async def list_schedules(
    db: AsyncSession, skip: int = 0, limit: int = 100,
) -> list[dict]:
    result = await db.execute(
        select(models.Schedule)
        .options(selectinload(models.Schedule.slots))
        .order_by(models.Schedule.created_at.desc())
        .offset(skip).limit(limit)
    )
    return [_schedule_to_dict(s) for s in result.scalars().all()]


async def create_schedule(
    db: AsyncSession, data: schemas.ScheduleCreate, user_id,
) -> dict:
    existing = await db.execute(
        select(models.Schedule.id).where(
            models.Schedule.schedule_code == data.schedule_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Schedule code already exists")

    if data.campaign_code:
        camp = await db.execute(
            select(Campaign.id).where(Campaign.campaign_code == data.campaign_code)
        )
        if not camp.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Campaign not found")

    s = models.Schedule(
        schedule_code=data.schedule_code, name=data.name,
        campaign_code=data.campaign_code,
        valid_from=data.valid_from, valid_to=data.valid_to,
        timezone=data.timezone, created_by=user_id,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _schedule_to_dict(s)


async def get_schedule(db: AsyncSession, schedule_code: str) -> dict:
    return _schedule_to_dict(await _get_schedule_or_404(db, schedule_code))


async def update_schedule(
    db: AsyncSession, schedule_code: str, data: schemas.ScheduleUpdate,
) -> dict:
    s = await _get_schedule_or_404(db, schedule_code)
    if s.status == "archived":
        raise HTTPException(status_code=400, detail="Schedule is archived")
    if data.name is not None: s.name = data.name
    if data.valid_from is not None: s.valid_from = data.valid_from
    if data.valid_to is not None: s.valid_to = data.valid_to
    if data.timezone is not None: s.timezone = data.timezone
    s.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(s)
    return _schedule_to_dict(s)


async def archive_schedule(db: AsyncSession, schedule_code: str) -> dict:
    s = await _get_schedule_or_404(db, schedule_code)
    if s.status == "archived":
        raise HTTPException(status_code=400, detail="Schedule already archived")
    s.status = "archived"
    s.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(s)
    return _schedule_to_dict(s)


# ── Schedule Slots ────────────────────────────────────────────────────────

async def list_schedule_slots(
    db: AsyncSession, schedule_code: str,
) -> list[dict]:
    await _get_schedule_or_404(db, schedule_code)
    result = await db.execute(
        select(models.ScheduleSlot)
        .join(models.Schedule)
        .where(models.Schedule.schedule_code == schedule_code)
        .order_by(models.ScheduleSlot.slot_order)
    )
    return [_slot_to_dict(sl, schedule_code) for sl in result.scalars().all()]


async def create_schedule_slot(
    db: AsyncSession, schedule_code: str, data: schemas.ScheduleSlotCreate,
) -> dict:
    s = await _get_schedule_or_404(db, schedule_code)
    existing = await db.execute(
        select(models.ScheduleSlot.id).where(
            models.ScheduleSlot.slot_code == data.slot_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slot code already exists")
    if data.placement_code:
        p_result = await db.execute(
            select(models.KsoPlacement.id).where(
                models.KsoPlacement.placement_code == data.placement_code,
            )
        )
        if not p_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Placement not found")
    sl = models.ScheduleSlot(
        slot_code=data.slot_code, schedule_id=s.id,
        placement_code=data.placement_code,
        day_of_week=data.day_of_week,
        start_time=data.start_time, end_time=data.end_time,
        slot_order=data.slot_order,
    )
    db.add(sl)
    await db.commit()
    await db.refresh(sl)
    return _slot_to_dict(sl, schedule_code)


async def update_schedule_slot(
    db: AsyncSession, schedule_code: str, slot_code: str,
    data: schemas.ScheduleSlotUpdate,
) -> dict:
    result = await db.execute(
        select(models.ScheduleSlot)
        .join(models.Schedule)
        .where(
            models.Schedule.schedule_code == schedule_code,
            models.ScheduleSlot.slot_code == slot_code,
        )
    )
    sl = result.scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="Slot not found")
    if data.placement_code is not None: sl.placement_code = data.placement_code
    if data.day_of_week is not None: sl.day_of_week = data.day_of_week
    if data.start_time is not None: sl.start_time = data.start_time
    if data.end_time is not None: sl.end_time = data.end_time
    if data.slot_order is not None: sl.slot_order = data.slot_order
    sl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sl)
    return _slot_to_dict(sl, schedule_code)


async def disable_schedule_slot(
    db: AsyncSession, schedule_code: str, slot_code: str,
) -> dict:
    result = await db.execute(
        select(models.ScheduleSlot)
        .join(models.Schedule)
        .where(
            models.Schedule.schedule_code == schedule_code,
            models.ScheduleSlot.slot_code == slot_code,
        )
    )
    sl = result.scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="Slot not found")
    sl.is_active = False
    sl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sl)
    return _slot_to_dict(sl, schedule_code)
