"""Proof-of-Play KSO router — test KSO technical validation.

TEST_ONLY — no auth on POST.  Production MUST use device gateway auth / mTLS.
GET list endpoint requires reports.read permission.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.device_gateway.auth import authenticate_device
from app.domains.identity import models as identity_models
from app.domains.proof_of_play.schemas import (
    KsoPoPIngestRequest,
    KsoPoPIngestResponse,
    KsoPoPListResponse,
)
from app.domains.proof_of_play.service import ingest_kso_pop, list_kso_pop_events

router = APIRouter(prefix="/api", tags=["proof-of-play-kso"])


# ══════════════════════════════════════════════════════════════════════
# KSO PoP ingest — device auth required (production path).
# Production device gateway uses JWT bearer token from /device-auth.
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/device-gateway/kso/{device_code}/pop",
    response_model=KsoPoPIngestResponse,
)
async def kso_pop_ingest(
    device_code: str,
    data: KsoPoPIngestRequest,
    request: Request,
    db=Depends(get_db),
):
    """Ingest PoP event for KSO — authenticated device gateway path.

    Requires valid device JWT from /device-auth.
    Device in URL must match authenticated device.
    """
    device, _session = await authenticate_device(request, db)
    if device.device_code != device_code:
        raise HTTPException(status_code=403, detail="Device code mismatch")
    response, error = await ingest_kso_pop(db, device_code, data)
    if error:
        status_map: dict[str, int] = {
            "device_not_found": 404,
            "no_published_manifest": 404,
            "manifest_version_mismatch": 422,
            "manifest_hash_mismatch": 422,
            "unknown_media_ref": 422,
            "placement_not_found": 404,
            "creative_not_in_campaign": 422,
        }
        code = status_map.get(error, 400)
        raise HTTPException(status_code=code, detail=error)

    return response


# ══════════════════════════════════════════════════════════════════════
# Read-only PoP list — safe projection for portal reporting
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/proof-of-play/test-kso",
    response_model=list[KsoPoPListResponse],
)
async def list_kso_pop(
    device_code: Optional[str] = Query(None, max_length=64),
    campaign_code: Optional[str] = Query(None, max_length=64),
    creative_code: Optional[str] = Query(None, max_length=64),
    placement_code: Optional[str] = Query(None, max_length=64),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("reports.read")),
):
    """List PoP events for test KSO technical validation (safe projection).

    Requires ``reports.read`` permission.

    Response contains ONLY safe fields: event_code, device_code,
    placement_code, campaign_code, creative_code, media_ref, event_type,
    status, played_at, duration_ms, received_at.

    Never returns: id (raw UUID), manifest_version_id, manifest_hash,
    backend_url, tokens, file_path, sha256, storage_ref, minio,
    device_secret, client_secret, receipt, payment, fiscal, customer.
    """
    return await list_kso_pop_events(
        db,
        device_code=device_code,
        campaign_code=campaign_code,
        creative_code=creative_code,
        placement_code=placement_code,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
