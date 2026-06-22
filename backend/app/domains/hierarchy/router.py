"""
Hierarchy domain: FastAPI router — KSO device registry (Step 37.1).

Endpoints:
  GET  /api/devices/kso             — list KSO devices
  GET  /api/devices/kso/{code}      — get by device_code
  POST /api/devices/kso             — create KSO device
  PUT  /api/devices/kso/{code}      — update KSO device

Permissions:
  read  → devices.read
  write → devices.manage

Future RLS: list_kso_devices will filter by store_scope / device_scope.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.hierarchy import schemas, service

router = APIRouter(prefix="/api/devices", tags=["kso-devices"])


# ── List KSO devices ─────────────────────────────────────────────────────

@router.get("/kso", response_model=list[schemas.KsoDeviceResponse])
async def list_kso_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    store_id: UUID | None = Query(None),
    status: str | None = Query(None, max_length=20),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.read")),
):
    """List KSO devices. Requires devices.read permission.

    Future RLS: results will be filtered by store_scope / device_scope.
    """
    return await service.list_kso_devices(
        db, skip=skip, limit=limit, store_id=store_id, status_filter=status,
    )


# ── Get KSO device by code ────────────────────────────────────────────────

@router.get("/kso/{device_code}", response_model=schemas.KsoDeviceResponse)
async def get_kso_device(
    device_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.read")),
):
    """Get a KSO device by its unique device_code. Requires devices.read.

    Returns safe 404 if not found. Never exposes secrets, IP, MAC,
    hostname, or serial.
    """
    return await service.get_kso_device_by_code(db, device_code)


# ── Create KSO device ────────────────────────────────────────────────────

@router.post(
    "/kso", response_model=schemas.KsoDeviceResponse, status_code=201,
)
async def create_kso_device(
    body: schemas.KsoDeviceCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.manage")),
):
    """Create a KSO device registration. Requires devices.manage.

    Safe: device_code must follow ^[a-z0-9_-]+$.
    Does NOT store secrets, IP, MAC, hostname, or serial.
    """
    return await service.create_kso_device(db, body)


# ── Update KSO device ────────────────────────────────────────────────────

@router.put("/kso/{device_code}", response_model=schemas.KsoDeviceResponse)
async def update_kso_device(
    device_code: str,
    body: schemas.KsoDeviceUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.manage")),
):
    """Update a KSO device. Requires devices.manage."""
    return await service.update_kso_device(db, device_code, body)
