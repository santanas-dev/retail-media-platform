"""Device Operations: read-only health API router."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_db, require_permission
from app.domains.device_operations import schemas, service
from app.domains.identity.models import User

router = APIRouter(prefix="/api/device-operations", tags=["device-operations"])


@router.get("/overview", response_model=schemas.OverviewResponse)
async def get_overview(
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_overview(
        db,
        date_from=date_from,
        date_to=date_to,
        channel_id=channel_id,
        store_id=store_id,
    )


@router.get("/devices", response_model=list[schemas.DeviceHealthItem])
async def get_devices(
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    device_status: Optional[str] = Query(None),
    health_status: Optional[str] = Query(None),
    problem_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_devices(
        db,
        date_from=date_from,
        date_to=date_to,
        channel_id=channel_id,
        store_id=store_id,
        device_status=device_status,
        health_status=health_status,
        problem_type=problem_type,
        limit=limit,
        offset=offset,
    )


@router.get("/devices/{device_id}", response_model=schemas.DeviceHealthDetail)
async def get_device_detail(
    device_id: UUID,
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    result = await service.get_device_detail(
        db, device_id,
        date_from=date_from,
        date_to=date_to,
    )
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Device not found")
    return result


@router.get("/stores", response_model=list[schemas.StoreHealthItem])
async def get_stores_health(
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_stores_health(
        db,
        date_from=date_from,
        date_to=date_to,
        channel_id=channel_id,
        store_id=store_id,
    )


@router.get("/channels", response_model=list[schemas.ChannelHealthItem])
async def get_channels_health(
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_channels_health(
        db,
        date_from=date_from,
        date_to=date_to,
        channel_id=channel_id,
        store_id=store_id,
    )
