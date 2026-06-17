"""Device Gateway Foundation: FastAPI routers — admin + device endpoints."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi import status as http_status

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.device_gateway import schemas, service
from app.domains.device_gateway.auth import authenticate_device
from app.domains.identity.models import User

admin_router = APIRouter(prefix="/api", tags=["gateway-devices"])
device_router = APIRouter(prefix="/api/device-gateway", tags=["device-gateway"])


# ═══════════════════════════════════════════════════════════════════
#  Admin API
# ═══════════════════════════════════════════════════════════════════

@admin_router.post("/gateway-devices", response_model=schemas.GatewayDeviceResponse, status_code=http_status.HTTP_201_CREATED)
async def create_device(data: schemas.GatewayDeviceCreate, db=Depends(get_db), current_user: User = Depends(require_permission("devices.gateway.manage"))):
    return await service.create_device(db, data)

@admin_router.get("/gateway-devices", response_model=list[schemas.GatewayDeviceResponse])
async def list_devices(db=Depends(get_db), status: Optional[str] = Query(None), store_id: Optional[str] = Query(None), current_user: User = Depends(require_permission("devices.gateway.read"))):
    return await service.list_devices(db, status=status, store_id=UUID(store_id) if store_id else None)

@admin_router.get("/gateway-devices/{device_id}", response_model=schemas.GatewayDeviceResponse)
async def get_device(device_id: UUID, db=Depends(get_db), current_user: User = Depends(require_permission("devices.gateway.read"))):
    return await service.get_device(db, device_id)

@admin_router.put("/gateway-devices/{device_id}", response_model=schemas.GatewayDeviceResponse)
async def update_device(device_id: UUID, data: schemas.GatewayDeviceUpdate, db=Depends(get_db), current_user: User = Depends(require_permission("devices.gateway.manage"))):
    device = await service.get_device(db, device_id)
    return await service.update_device(db, device, data)

@admin_router.post("/gateway-devices/{device_id}/credentials", response_model=schemas.DeviceCredentialCreatedResponse, status_code=http_status.HTTP_201_CREATED)
async def create_credential(device_id: UUID, db=Depends(get_db), current_user: User = Depends(require_permission("devices.gateway.credentials"))):
    device = await service.get_device(db, device_id)
    return await service.create_credential(db, device)

@admin_router.post("/gateway-devices/{device_id}/credentials/{credential_id}/revoke", response_model=schemas.DeviceCredentialResponse)
async def revoke_credential(device_id: UUID, credential_id: UUID, db=Depends(get_db), current_user: User = Depends(require_permission("devices.gateway.credentials"))):
    credential = await service.get_credential(db, credential_id)
    if credential.gateway_device_id != device_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Credential not found for this device")
    return await service.revoke_credential(db, credential)

@admin_router.get("/gateway-devices/{device_id}/heartbeats", response_model=list[schemas.DeviceHeartbeatResponse])
async def get_heartbeats(device_id: UUID, db=Depends(get_db), current_user: User = Depends(require_permission("devices.gateway.read"))):
    return await service.get_heartbeats(db, device_id)

@admin_router.get("/gateway-devices/{device_id}/events", response_model=list[schemas.DeviceEventResponse])
async def get_events(device_id: UUID, db=Depends(get_db), current_user: User = Depends(require_permission("devices.gateway.read"))):
    return await service.get_events(db, device_id)


# ═══════════════════════════════════════════════════════════════════
#  Device API
# ═══════════════════════════════════════════════════════════════════

@device_router.post("/auth/token", response_model=schemas.DeviceAuthResponse)
async def device_auth(data: schemas.DeviceAuthRequest, request: Request, db=Depends(get_db)):
    client_ip = request.client.host if request.client else None
    return await service.device_auth(db, data, client_ip)

@device_router.get("/me", response_model=schemas.DeviceMeResponse)
async def device_me(request: Request, db=Depends(get_db)):
    device, session = await authenticate_device(request, db)
    return schemas.DeviceMeResponse(
        device_id=device.id, device_code=device.device_code, device_name=device.device_name,
        status=device.status, channel_id=device.channel_id, store_id=device.store_id,
        last_seen_at=device.last_seen_at, session_id=session.id,
    )

@device_router.post("/heartbeat", response_model=schemas.DeviceHeartbeatResponse)
async def device_heartbeat(data: schemas.DeviceHeartbeatRequest, request: Request, db=Depends(get_db)):
    device, _session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await service.record_heartbeat(db, device, data, client_ip, user_agent)


# ═══════════════════════════════════════════════════════════════════
#  Manifest Delivery
# ═══════════════════════════════════════════════════════════════════

@device_router.get("/manifest/current", response_model=schemas.DeviceManifestCurrentResponse)
async def manifest_current(
    request: Request,
    db=Depends(get_db),
    current_manifest_hash: Optional[str] = Query(None, max_length=64),
):
    device, session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    response = await service.get_current_manifest(
        device, db, current_manifest_hash, client_ip, user_agent,
    )
    # Update session last_used
    session.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return response


@device_router.get("/manifest/{manifest_version_id}", response_model=schemas.DeviceManifestResponse)
async def manifest_by_id(
    manifest_version_id: UUID,
    request: Request,
    db=Depends(get_db),
):
    device, session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    response = await service.get_device_manifest_by_id(
        device, db, manifest_version_id, client_ip, user_agent,
    )
    session.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return response


# ── Admin: manifest requests ────────────────────────────────────────

@admin_router.get(
    "/gateway-devices/{device_id}/manifest-requests",
    response_model=list[schemas.DeviceManifestRequestResponse],
)
async def list_manifest_requests(
    device_id: UUID,
    db=Depends(get_db),
    request_status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_device_manifest_requests(
        db, device_id, request_status, date_from, date_to, limit,
    )
