"""
Channels & Devices domain: FastAPI router.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.channels import schemas, service

router = APIRouter(prefix="/api", tags=["channels"])


# ── Channels ──────────────────────────────────────────────────────────────

@router.get("/channels", response_model=list[schemas.ChannelResponse])
async def list_channels(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("channels.read")),
):
    return await service.list_channels(db, skip, limit)


@router.post("/channels", response_model=schemas.ChannelResponse, status_code=201)
async def create_channel(
    body: schemas.ChannelCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("channels.manage")),
):
    return await service.create_channel(db, body)


# ── Device Types ──────────────────────────────────────────────────────────

@router.get("/device-types", response_model=list[schemas.DeviceTypeResponse])
async def list_device_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    channel_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.read")),
):
    return await service.list_device_types(db, skip, limit, channel_id)


@router.post("/device-types", response_model=schemas.DeviceTypeResponse, status_code=201)
async def create_device_type(
    body: schemas.DeviceTypeCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.manage")),
):
    return await service.create_device_type(db, body)


# ── Capability Profiles ───────────────────────────────────────────────────

@router.get("/capability-profiles", response_model=list[schemas.CapabilityProfileResponse])
async def list_capability_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    device_type_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.read")),
):
    return await service.list_capability_profiles(db, skip, limit, device_type_id)


@router.post("/capability-profiles", response_model=schemas.CapabilityProfileResponse, status_code=201)
async def create_capability_profile(
    body: schemas.CapabilityProfileCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.manage")),
):
    return await service.create_capability_profile(db, body)


# ── Physical Devices ──────────────────────────────────────────────────────

@router.get("/physical-devices", response_model=list[schemas.PhysicalDeviceResponse])
async def list_physical_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    store_id: UUID | None = Query(None),
    device_type_id: UUID | None = Query(None),
    channel_code: str | None = Query(None, max_length=50),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.read")),
):
    return await service.list_physical_devices(
        db, skip, limit, store_id, device_type_id, channel_code, status,
    )


@router.post("/physical-devices", response_model=schemas.PhysicalDeviceResponse, status_code=201)
async def create_physical_device(
    body: schemas.PhysicalDeviceCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.manage")),
):
    return await service.create_physical_device(db, body)


@router.get(
    "/physical-devices/by-code/{external_code}",
    response_model=schemas.PhysicalDeviceResponse,
)
async def get_physical_device_by_external_code(
    external_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.read")),
):
    """Get a physical device by its external_code (universal model)."""
    return await service.get_physical_device_by_external_code(db, external_code)


# ── Logical Carriers ──────────────────────────────────────────────────────

@router.get("/logical-carriers", response_model=list[schemas.LogicalCarrierResponse])
async def list_logical_carriers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    physical_device_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.read")),
):
    return await service.list_logical_carriers(db, skip, limit, physical_device_id)


@router.post("/logical-carriers", response_model=schemas.LogicalCarrierResponse, status_code=201)
async def create_logical_carrier(
    body: schemas.LogicalCarrierCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.manage")),
):
    return await service.create_logical_carrier(db, body)


# ── Display Surfaces ──────────────────────────────────────────────────────

@router.get("/display-surfaces", response_model=list[schemas.DisplaySurfaceResponse])
async def list_display_surfaces(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    logical_carrier_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.read")),
):
    return await service.list_display_surfaces(db, skip, limit, logical_carrier_id)


@router.post("/display-surfaces", response_model=schemas.DisplaySurfaceResponse, status_code=201)
async def create_display_surface(
    body: schemas.DisplaySurfaceCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.manage")),
):
    return await service.create_display_surface(db, body)
