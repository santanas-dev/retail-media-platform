"""
Hierarchy domain: business logic for KSO device registry (Step 37.1).
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.hierarchy import models, schemas


# ── KSO Devices ──────────────────────────────────────────────────────────

async def list_kso_devices(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    store_id: UUID | None = None,
    status_filter: str | None = None,
) -> list[models.KsoDevice]:
    """List KSO devices, optionally filtered by store or status."""
    stmt = select(models.KsoDevice).order_by(models.KsoDevice.device_code)
    if store_id:
        stmt = stmt.where(models.KsoDevice.store_id == store_id)
    if status_filter:
        stmt = stmt.where(models.KsoDevice.status == status_filter)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_kso_device_by_code(
    db: AsyncSession, device_code: str
) -> models.KsoDevice:
    """Get a KSO device by its unique device_code."""
    result = await db.execute(
        select(models.KsoDevice).where(
            models.KsoDevice.device_code == device_code
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KSO device not found",
        )
    return device


async def create_kso_device(
    db: AsyncSession, data: schemas.KsoDeviceCreate
) -> models.KsoDevice:
    """Create a new KSO device registration."""
    # Validate status
    if data.status not in models.DEVICE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status: {data.status}. "
                   f"Allowed: {', '.join(sorted(models.DEVICE_STATUSES))}",
        )

    # Verify store exists
    from app.domains.organization.models import Store
    result = await db.execute(
        select(Store).where(Store.id == data.store_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        )

    # Check device_code uniqueness
    existing = await db.execute(
        select(models.KsoDevice).where(
            models.KsoDevice.device_code == data.device_code
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"KSO device with code '{data.device_code}' already exists",
        )

    device = models.KsoDevice(**data.model_dump())
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def update_kso_device(
    db: AsyncSession, device_code: str, data: schemas.KsoDeviceUpdate
) -> models.KsoDevice:
    """Update a KSO device registration."""
    device = await get_kso_device_by_code(db, device_code)

    update_data = data.model_dump(exclude_unset=True)

    # Validate status if provided
    if "status" in update_data:
        if update_data["status"] not in models.DEVICE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status: {update_data['status']}",
            )

    for key, value in update_data.items():
        setattr(device, key, value)
    device.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(device)
    return device
