"""
Channels & Devices domain: business logic.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.channels import models, schemas


# ── Channels ──────────────────────────────────────────────────────────────

async def list_channels(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> list[models.Channel]:
    result = await db.execute(
        select(models.Channel)
        .order_by(models.Channel.code)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_channel(
    db: AsyncSession, data: schemas.ChannelCreate
) -> models.Channel:
    channel = models.Channel(**data.model_dump())
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


# ── Device Types ──────────────────────────────────────────────────────────

async def list_device_types(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    channel_id: UUID | None = None,
) -> list[models.DeviceType]:
    stmt = select(models.DeviceType).order_by(models.DeviceType.name)
    if channel_id:
        stmt = stmt.where(models.DeviceType.channel_id == channel_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def create_device_type(
    db: AsyncSession, data: schemas.DeviceTypeCreate
) -> models.DeviceType:
    result = await db.execute(
        select(models.Channel).where(models.Channel.id == data.channel_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    device_type = models.DeviceType(**data.model_dump())
    db.add(device_type)
    await db.commit()
    await db.refresh(device_type)
    return device_type


# ── Capability Profiles ───────────────────────────────────────────────────

async def list_capability_profiles(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    device_type_id: UUID | None = None,
) -> list[models.CapabilityProfile]:
    stmt = select(models.CapabilityProfile).order_by(models.CapabilityProfile.created_at.desc())
    if device_type_id:
        stmt = stmt.where(models.CapabilityProfile.device_type_id == device_type_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def create_capability_profile(
    db: AsyncSession, data: schemas.CapabilityProfileCreate
) -> models.CapabilityProfile:
    result = await db.execute(
        select(models.DeviceType).where(models.DeviceType.id == data.device_type_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device type not found")
    profile = models.CapabilityProfile(**data.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


# ── Physical Devices ──────────────────────────────────────────────────────

async def list_physical_devices(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    store_id: UUID | None = None,
    device_type_id: UUID | None = None,
    channel_code: str | None = None,
    status: str | None = None,
) -> list[models.PhysicalDevice]:
    stmt = select(models.PhysicalDevice).order_by(models.PhysicalDevice.created_at.desc())
    if store_id:
        stmt = stmt.where(models.PhysicalDevice.store_id == store_id)
    if device_type_id:
        stmt = stmt.where(models.PhysicalDevice.device_type_id == device_type_id)
    if channel_code:
        stmt = (
            stmt.join(models.DeviceType, models.PhysicalDevice.device_type_id == models.DeviceType.id)
            .join(models.Channel, models.DeviceType.channel_id == models.Channel.id)
            .where(models.Channel.code == channel_code)
        )
    if status:
        stmt = stmt.where(models.PhysicalDevice.status == status)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_physical_device_by_external_code(
    db: AsyncSession, external_code: str,
) -> models.PhysicalDevice:
    result = await db.execute(
        select(models.PhysicalDevice).where(
            models.PhysicalDevice.external_code == external_code
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with external_code '{external_code}' not found",
        )
    return device


async def create_physical_device(
    db: AsyncSession, data: schemas.PhysicalDeviceCreate
) -> models.PhysicalDevice:
    # Verify store exists
    result = await db.execute(
        select(models.DeviceType).where(models.DeviceType.id == data.device_type_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device type not found")
    device = models.PhysicalDevice(**data.model_dump())
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


# ── Logical Carriers ──────────────────────────────────────────────────────

async def list_logical_carriers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    physical_device_id: UUID | None = None,
) -> list[models.LogicalCarrier]:
    stmt = select(models.LogicalCarrier).order_by(models.LogicalCarrier.created_at)
    if physical_device_id:
        stmt = stmt.where(models.LogicalCarrier.physical_device_id == physical_device_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def create_logical_carrier(
    db: AsyncSession, data: schemas.LogicalCarrierCreate
) -> models.LogicalCarrier:
    result = await db.execute(
        select(models.PhysicalDevice).where(
            models.PhysicalDevice.id == data.physical_device_id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Physical device not found"
        )
    carrier = models.LogicalCarrier(**data.model_dump())
    db.add(carrier)
    await db.commit()
    await db.refresh(carrier)
    return carrier


# ── Display Surfaces ──────────────────────────────────────────────────────

async def list_display_surfaces(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    logical_carrier_id: UUID | None = None,
) -> list[models.DisplaySurface]:
    stmt = select(models.DisplaySurface).order_by(models.DisplaySurface.created_at)
    if logical_carrier_id:
        stmt = stmt.where(models.DisplaySurface.logical_carrier_id == logical_carrier_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def create_display_surface(
    db: AsyncSession, data: schemas.DisplaySurfaceCreate
) -> models.DisplaySurface:
    result = await db.execute(
        select(models.LogicalCarrier).where(
            models.LogicalCarrier.id == data.logical_carrier_id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Logical carrier not found"
        )
    result = await db.execute(
        select(models.CapabilityProfile).where(
            models.CapabilityProfile.id == data.capability_profile_id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Capability profile not found"
        )
    surface = models.DisplaySurface(**data.model_dump())
    db.add(surface)
    await db.commit()
    await db.refresh(surface)
    return surface


# ── Device Chain Helpers (B.2) ──────────────────────────────────────────


async def get_device_surfaces(
    db: AsyncSession, device_id: UUID,
) -> list[models.DisplaySurface]:
    """Get all display surfaces for a physical device through the chain."""
    result = await db.execute(
        select(models.DisplaySurface)
        .join(models.LogicalCarrier, models.DisplaySurface.logical_carrier_id == models.LogicalCarrier.id)
        .where(models.LogicalCarrier.physical_device_id == device_id)
        .order_by(models.DisplaySurface.created_at)
    )
    return list(result.scalars().all())


async def get_device_capabilities(
    db: AsyncSession, device_id: UUID,
) -> list[models.CapabilityProfile]:
    """Get all capability profiles for a physical device through the chain."""
    result = await db.execute(
        select(models.CapabilityProfile)
        .join(models.DisplaySurface, models.DisplaySurface.capability_profile_id == models.CapabilityProfile.id)
        .join(models.LogicalCarrier, models.DisplaySurface.logical_carrier_id == models.LogicalCarrier.id)
        .where(models.LogicalCarrier.physical_device_id == device_id)
        .order_by(models.CapabilityProfile.orientation)
    )
    return list(result.scalars().all())


async def get_device_surface_readiness(
    db: AsyncSession, surface_id: UUID,
) -> dict:
    """Check if a display surface is ready for content delivery."""
    result = await db.execute(
        select(models.DisplaySurface).where(models.DisplaySurface.id == surface_id)
    )
    surface = result.scalar_one_or_none()
    if not surface:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Surface not found")
    result = await db.execute(
        select(models.CapabilityProfile).where(
            models.CapabilityProfile.id == surface.capability_profile_id
        )
    )
    profile = result.scalar_one_or_none()
    return {
        "surface_id": str(surface.id),
        "is_active": surface.is_active,
        "resolution": surface.resolution,
        "orientation": profile.orientation if profile else None,
        "proof_type": profile.proof_type if profile else None,
        "formats": profile.formats_json if profile else None,
        "max_duration": profile.max_duration if profile else None,
        "max_file_size": profile.max_file_size if profile else None,
        "interactive": profile.interactive if profile else False,
    }


# ═══════════════════════════════════════════════════════════════════════════
# B.3.2 — Placement service
# ═══════════════════════════════════════════════════════════════════════════

from datetime import date as date_type
from app.domains.campaigns.models import Campaign
from app.domains.identity.rls import resolve_user_scope_context, assert_object_in_advertiser_scope
from app.domains.identity.models import User

_EDITABLE_CAMPAIGN_STATUSES = frozenset({"draft", "rejected"})


async def _get_placement_or_404(db: AsyncSession, placement_id: UUID) -> models.Placement:
    result = await db.execute(
        select(models.Placement).where(models.Placement.id == placement_id)
    )
    placement = result.scalar_one_or_none()
    if not placement:
        raise HTTPException(status_code=404, detail="Placement not found")
    return placement


async def _get_campaign_for_placement(
    db: AsyncSession, placement: models.Placement, current_user: User,
) -> Campaign:
    """Load campaign and enforce advertiser scope (read or write)."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == placement.campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "access placement")
    return campaign


# ── Placement CRUD ──────────────────────────────────────────────────────────


async def list_campaign_placements(
    db: AsyncSession, campaign_id: UUID, current_user: User,
) -> list[models.Placement]:
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "list placements")
    result = await db.execute(
        select(models.Placement)
        .where(models.Placement.campaign_id == campaign_id)
        .order_by(models.Placement.created_at.desc())
    )
    return list(result.scalars().all())


async def create_campaign_placement(
    db: AsyncSession, campaign_id: UUID, data: schemas.PlacementCreate, current_user: User,
) -> models.Placement:
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "create placement")

    # Validate channel exists
    ch_result = await db.execute(
        select(models.Channel).where(models.Channel.id == data.channel_id)
    )
    channel = ch_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{data.channel_id}' not found")

    # If campaign has campaign_channels, channel must be in allowed list
    if campaign.channels:
        allowed_ids = {cc.channel_id for cc in campaign.channels}
        if data.channel_id not in allowed_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Channel not in campaign's allowed channels",
            )

    # Validate dates
    if data.start_date and data.end_date and data.start_date > data.end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    placement = models.Placement(
        campaign_id=campaign_id,
        channel_id=data.channel_id,
        name=data.name,
        priority=data.priority,
        start_date=data.start_date,
        end_date=data.end_date,
        status="draft",
        created_by=current_user.id,
    )
    db.add(placement)
    await db.commit()
    await db.refresh(placement)
    return placement


async def get_placement(
    db: AsyncSession, placement_id: UUID, current_user: User,
) -> models.Placement:
    placement = await _get_placement_or_404(db, placement_id)
    await _get_campaign_for_placement(db, placement, current_user)
    return placement


async def update_placement(
    db: AsyncSession, placement_id: UUID, data: schemas.PlacementUpdate, current_user: User,
) -> models.Placement:
    placement = await _get_placement_or_404(db, placement_id)
    await _get_campaign_for_placement(db, placement, current_user)

    # Validate status
    if data.status is not None:
        if data.status not in schemas.VALID_PLACEMENT_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{data.status}'. Valid: {sorted(schemas.VALID_PLACEMENT_STATUSES)}",
            )

    # Validate dates
    start = data.start_date if data.start_date is not None else placement.start_date
    end = data.end_date if data.end_date is not None else placement.end_date
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    # Apply updates
    if data.name is not None:
        placement.name = data.name
    if data.status is not None:
        placement.status = data.status
    if data.priority is not None:
        placement.priority = data.priority
    if data.start_date is not None:
        placement.start_date = data.start_date
    if data.end_date is not None:
        placement.end_date = data.end_date

    placement.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(placement)
    return placement


async def cancel_placement(
    db: AsyncSession, placement_id: UUID, current_user: User,
) -> models.Placement:
    placement = await _get_placement_or_404(db, placement_id)
    await _get_campaign_for_placement(db, placement, current_user)
    placement.status = "cancelled"
    placement.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(placement)
    return placement


# ── Placement Targets ───────────────────────────────────────────────────────


async def get_placement_targets(
    db: AsyncSession, placement_id: UUID, current_user: User,
) -> list[models.PlacementTarget]:
    placement = await _get_placement_or_404(db, placement_id)
    await _get_campaign_for_placement(db, placement, current_user)
    result = await db.execute(
        select(models.PlacementTarget)
        .where(models.PlacementTarget.placement_id == placement_id)
        .order_by(models.PlacementTarget.created_at)
    )
    return list(result.scalars().all())


async def set_placement_targets(
    db: AsyncSession, placement_id: UUID, data: schemas.PlacementTargetsUpdate, current_user: User,
) -> list[models.PlacementTarget]:
    placement = await _get_placement_or_404(db, placement_id)
    await _get_campaign_for_placement(db, placement, current_user)

    # Validate each target
    for idx, item in enumerate(data.targets):
        if item.target_type not in ("store", "surface", "carrier"):
            raise HTTPException(
                status_code=400,
                detail=f"targets[{idx}]: invalid target_type '{item.target_type}'",
            )
        if item.target_type == "store" and item.store_id is None:
            raise HTTPException(
                status_code=400,
                detail=f"targets[{idx}]: target_type='store' requires store_id",
            )
        if item.target_type == "surface" and item.display_surface_id is None:
            raise HTTPException(
                status_code=400,
                detail=f"targets[{idx}]: target_type='surface' requires display_surface_id",
            )
        if item.target_type == "carrier" and item.logical_carrier_id is None:
            raise HTTPException(
                status_code=400,
                detail=f"targets[{idx}]: target_type='carrier' requires logical_carrier_id",
            )

    # Delete old targets
    await db.execute(
        sa_delete(models.PlacementTarget).where(
            models.PlacementTarget.placement_id == placement_id
        )
    )

    # Insert new targets
    new_targets = []
    for item in data.targets:
        target = models.PlacementTarget(
            placement_id=placement_id,
            target_type=item.target_type,
            store_id=item.store_id,
            display_surface_id=item.display_surface_id,
            logical_carrier_id=item.logical_carrier_id,
        )
        db.add(target)
        new_targets.append(target)

    await db.commit()
    return new_targets
