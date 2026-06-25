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
    """Minimal conflict guard: overlapping placements on same device.

    Checks for any placement on the same device_code whose time window
    overlaps with [starts_at, ends_at) and whose status is NOT in
    {cancelled, rejected}.  If found, raises 409 Conflict.
    """
    stmt = select(models.KsoPlacement.placement_code).where(
        models.KsoPlacement.device_code == device_code,
        models.KsoPlacement.status.notin_(_NON_CONFLICT_STATUSES),
        models.KsoPlacement.starts_at < ends_at,
        models.KsoPlacement.ends_at > starts_at,
    )
    if exclude_placement_code:
        stmt = stmt.where(
            models.KsoPlacement.placement_code != exclude_placement_code,
        )

    result = await db.execute(stmt.limit(1))
    conflicting = result.scalar_one_or_none()
    if conflicting:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Device '{device_code}' already has placement "
                f"'{conflicting}' overlapping the requested time window"
            ),
        )


# ── Public API ──────────────────────────────────────────────────────────


async def list_placements(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[dict]:
    """List placements with safe projection — no raw UUIDs."""
    stmt = (
        select(models.KsoPlacement)
        .order_by(models.KsoPlacement.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
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
    """Get single placement by code — safe projection."""
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
