"""
Channels & Devices domain: business logic.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
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
    status: str | None = None,
) -> list[models.PhysicalDevice]:
    stmt = select(models.PhysicalDevice).order_by(models.PhysicalDevice.created_at.desc())
    if store_id:
        stmt = stmt.where(models.PhysicalDevice.store_id == store_id)
    if device_type_id:
        stmt = stmt.where(models.PhysicalDevice.device_type_id == device_type_id)
    if status:
        stmt = stmt.where(models.PhysicalDevice.status == status)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


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
