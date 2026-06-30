"""Device Gateway Foundation: FastAPI routers — admin + device endpoints."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse as _StreamingResponse

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db, require_permission
from app.domains.device_gateway import schemas, service
from app.domains.device_gateway.auth import authenticate_device
from app.domains.identity.models import User
from app.domains.device_operations import schemas as rt_schemas, service as rt_service

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


# ═══════════════════════════════════════════════════════════════════
#  KSO Manifest from GeneratedManifest — device auth required.
#  Production device gateway uses JWT bearer token from /device-auth.
# ═══════════════════════════════════════════════════════════════════

@device_router.get("/kso/{device_code}/manifest")
async def kso_manifest_by_device(
    device_code: str,
    request: Request,
    db=Depends(get_db),
):
    """Return latest published KSO manifest for a device_code.

    Reads from GeneratedManifest (test KSO pipeline), not the
    enterprise PublicationBatch → ManifestVersion pipeline.
    Returns sidecar-compatible body: {status, manifest, ...}

    Requires valid device JWT from /device-auth.
    Device in URL must match authenticated device.
    """
    device, _session = await authenticate_device(request, db)
    if device.device_code != device_code:
        raise HTTPException(status_code=403, detail="Device code mismatch")
    from app.domains.manifests.models import GeneratedManifest
    from sqlalchemy import select as _select

    result = await db.execute(
        _select(GeneratedManifest)
        .where(
            GeneratedManifest.device_code == device_code,
            GeneratedManifest.status == "published",
        )
        .order_by(GeneratedManifest.published_at.desc().nullslast())
        .limit(1)
    )
    mf = result.scalar_one_or_none()

    if not mf:
        return {"status": "no_manifest"}

    import hashlib
    import json as _json

    body = mf.manifest_body_json or {}
    canonical = _json.dumps(body, sort_keys=True, separators=(",", ":"))
    mhash = hashlib.sha256(canonical.encode()).hexdigest()

    return {
        "status": "served",
        "manifest_version_id": str(mf.id),
        "manifest_hash": mhash,
        "published_at": mf.published_at.isoformat() if mf.published_at else None,
        "manifest": body,
    }


# ═══════════════════════════════════════════════════════════════════
#  C.1 — Universal Manifest Delivery
# ═══════════════════════════════════════════════════════════════════

@device_router.get(
    "/manifest/universal/current",
    response_model=schemas.UniversalManifestCurrentResponse,
)
async def universal_manifest_current(
    request: Request,
    db=Depends(get_db),
    current_manifest_hash: Optional[str] = Query(None, max_length=64),
):
    """Return UniversalManifestV1 for authenticated device.

    Uses B.5 universal builder via B.4 orchestrator chain.
    Device must authenticate via JWT (existing /auth/token).
    Does NOT use KsoPlacement, GeneratedManifest, or publication flow.
    """
    device, _session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await service.get_universal_manifest_for_device(
        device, db, current_manifest_hash, client_ip, user_agent,
    )


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


# ═══════════════════════════════════════════════════════════════════
#  Device: Media Delivery
# ═══════════════════════════════════════════════════════════════════

@device_router.get(
    "/media/{manifest_item_id}/metadata",
    response_model=schemas.DeviceMediaMetadataResponse,
    responses={304: {"description": "Not modified"}},
)
async def media_metadata(
    manifest_item_id: UUID,
    request: Request,
    db=Depends(get_db),
    client_cached_sha256: Optional[str] = Query(None, max_length=64),
):
    device, _session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await service.get_media_metadata(
        device, manifest_item_id, client_cached_sha256, client_ip, user_agent, db,
    )


@device_router.get(
    "/media/{manifest_item_id}",
    responses={
        200: {"description": "Media file stream"},
        304: {"description": "Not modified"},
    },
)
async def media_download(
    manifest_item_id: UUID,
    request: Request,
    db=Depends(get_db),
    client_cached_sha256: Optional[str] = Query(None, max_length=64),
):
    device, _session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await service.get_media_download(
        device, manifest_item_id, client_cached_sha256, client_ip, user_agent,
        request, db,
    )


@device_router.get(
    "/media/kso/{media_ref:path}",
    responses={
        200: {"description": "KSO media file stream by safe mediaRef"},
        404: {"description": "Media not found"},
        403: {"description": "Device not authorized for KSO"},
    },
)
async def media_download_kso(
    media_ref: str,
    request: Request,
    db=Depends(get_db),
):
    """Stream a media file for a KSO device using safe mediaRef.

    Accepts only: media/current/slot-000 through slot-999.
    Device must be KSO-channel.
    Never exposes internal IDs, paths, or storage keys.
    """
    device, _session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await service.get_kso_media_download(
        device, media_ref, client_ip, user_agent, request, db,
    )


# ── Admin: media requests ───────────────────────────────────────────

@admin_router.get(
    "/gateway-devices/{device_id}/media-requests",
    response_model=list[schemas.DeviceMediaRequestResponse],
)
async def list_media_requests(
    device_id: UUID,
    db=Depends(get_db),
    request_status: Optional[str] = Query(None),
    manifest_item_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_media_requests(
        db, device_id,
        request_status=request_status,
        manifest_item_id=manifest_item_id,
        limit=limit,
        offset=offset,
    )


# ═══════════════════════════════════════════════════════════════════
#  Step 13 — PoP Ingest Core
# ═══════════════════════════════════════════════════════════════════

# ── Device: submit PoP event ───────────────────────────────────────

@device_router.post(
    "/pop/events",
    response_model=schemas.PoPEventResponse,
)
async def submit_pop_event(
    data: schemas.PoPEventRequest,
    request: Request,
    db=Depends(get_db),
):
    device, _session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await service.ingest_pop_event(
        db, device, data, client_ip=client_ip, user_agent=user_agent,
    )


# ── Admin: list PoP events ─────────────────────────────────────────

@admin_router.get(
    "/gateway-devices/{device_id}/pop-events",
    response_model=list[schemas.PoPEventRead],
)
async def list_pop_events(
    device_id: UUID,
    db=Depends(get_db),
    validation_status: Optional[str] = Query(None),
    play_status: Optional[str] = Query(None),
    manifest_item_id: Optional[UUID] = Query(None),
    batch_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_pop_events(
        db, device_id,
        validation_status=validation_status,
        play_status=play_status,
        manifest_item_id=manifest_item_id,
        batch_id=batch_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


# ═══════════════════════════════════════════════════════════════════
#  Step 14 — PoP Batch / Offline Ingest
# ═══════════════════════════════════════════════════════════════════

# ── Device: submit PoP batch ───────────────────────────────────────

@device_router.post(
    "/pop/events/batch",
    response_model=schemas.PoPBatchResponse,
)
async def submit_pop_batch(
    request: Request,
    db=Depends(get_db),
):
    device, _session = await authenticate_device(request, db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Size check
    max_bytes = get_settings().POP_BATCH_MAX_BYTES
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail="Request body too large")

    # Parse
    import json as _json
    from pydantic import ValidationError
    try:
        raw = _json.loads(body)
        data = schemas.PoPBatchRequest(**raw)
    except (_json.JSONDecodeError, ValidationError) as e:
        detail = "Invalid JSON" if isinstance(e, _json.JSONDecodeError) else str(e)
        raise HTTPException(status_code=400 if isinstance(e, _json.JSONDecodeError) else 422, detail=detail)

    return await service.ingest_pop_batch(
        db, device, data,
        client_ip=client_ip, user_agent=user_agent,
    )


# ── Admin: list PoP batches ────────────────────────────────────────

@admin_router.get(
    "/gateway-devices/{device_id}/pop-batches",
    response_model=list[schemas.PoPBatchRead],
)
async def list_pop_batches(
    device_id: UUID,
    db=Depends(get_db),
    batch_status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_pop_batches(
        db, device_id,
        batch_status=batch_status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Runtime Config (Step 18) — Device endpoint
# ═══════════════════════════════════════════════════════════════════════

from fastapi import Request, Response



@device_router.get(
    "/config/current",
    response_model=rt_schemas.DeviceConfigResponse,
)
async def get_device_runtime_config(
    request: Request,
    db=Depends(get_db),
):
    """Serve effective runtime config to authenticated devices. Supports ETag/304."""
    current_device, _session = await authenticate_device(request, db)
    config, config_hash, profile_ids, _ = await rt_service.compute_effective_config(
        db, current_device,
    )

    # Record audit
    await rt_service.record_config_request(
        db,
        gateway_device_id=current_device.id,
        profile_ids=profile_ids,
        effective_hash=config_hash,
        response_status="ok",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # Check If-None-Match
    if_none_match = request.headers.get("If-None-Match", "").strip('"').strip("'")
    if if_none_match and if_none_match == config_hash:
        # Record not_modified audit
        await rt_service.record_config_request(
            db,
            gateway_device_id=current_device.id,
            profile_ids=profile_ids,
            effective_hash=config_hash,
            response_status="not_modified",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return Response(status_code=304)

    response_data = {
        "status": "ok",
        "gateway_device_id": current_device.id,
        "config_hash": config_hash,
        "config": config,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    resp = JSONResponse(content=jsonable_encoder(response_data))
    resp.headers["ETag"] = f'"{config_hash}"'
    return resp


# ═══════════════════════════════════════════════════════════════════════
#  Content Sync State (Step 20) — Device endpoints
# ═══════════════════════════════════════════════════════════════════════


@device_router.post(
    "/manifest/{manifest_version_id}/apply",
    response_model=schemas.ManifestApplyResponse,
)
async def manifest_apply(
    manifest_version_id: UUID,
    data: schemas.ManifestApplyRequest,
    request: Request,
    db=Depends(get_db),
):
    """Device reports manifest apply result (applied or failed)."""
    current_device, _ = await authenticate_device(request, db)
    event = await service.apply_manifest(
        db, current_device, manifest_version_id, data,
    )
    return {
        "status": "ok",
        "gateway_device_id": current_device.id,
        "manifest_version_id": manifest_version_id,
        "manifest_status": data.status,
    }


@device_router.post(
    "/media/cache/report",
    response_model=schemas.MediaCacheReportResponse,
)
async def media_cache_report(
    data: schemas.MediaCacheReportRequest,
    request: Request,
    db=Depends(get_db),
):
    """Device submits a batch media cache report."""
    current_device, _ = await authenticate_device(request, db)
    report = await service.submit_cache_report(db, current_device, data)
    return {
        "status": "ok",
        "gateway_device_id": current_device.id,
        "manifest_version_id": data.manifest_version_id,
        "total_items": report.total_items,
        "cached_count": report.cached_count,
        "missing_count": report.missing_count,
        "failed_count": report.failed_count,
        "invalid_hash_count": report.invalid_hash_count,
    }
