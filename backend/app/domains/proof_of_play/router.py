"""Proof-of-Play KSO router — test KSO technical validation.

TEST_ONLY — no auth on POST.  Production MUST use device gateway auth / mTLS.
GET list endpoint requires reports.read permission.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, func, select as _select
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

# ── Reports PoP summary schema (inline to avoid cross-domain dep) ──

class PoPSummaryResponse(BaseModel):
    """Safe aggregated PoP counts for portal reports."""
    total_events: int = 0
    unique_devices: int = 0
    unique_campaigns: int = 0
    unique_creatives: int = 0
    unique_placements: int = 0
    accepted: int = 0
    rejected: int = 0
    duplicate: int = 0
    unknown_status: int = 0
    last_event_at: Optional[datetime] = None

# ══════════════════════════════════════════════════════════════════════
# Production PoP list endpoint (safe projection, non-test-kso path)
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/reports/pop",
    response_model=list[KsoPoPListResponse],
)
async def list_pop_production(
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
    """Production PoP event list — safe projection for portal reporting.

    Requires ``reports.read`` permission.

    Returns same safe fields as test-kso: event_code, device_code,
    placement_code, campaign_code, creative_code, media_ref, event_type,
    status, played_at, duration_ms, received_at.
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


# ══════════════════════════════════════════════════════════════════════
# Production PoP summary endpoint (aggregated counts for portal reports)
# ══════════════════════════════════════════════════════════════════════

from app.domains.proof_of_play.models import KsoProofOfPlayEvent
from sqlalchemy import distinct as _distinct

@router.get(
    "/reports/pop/summary",
    response_model=PoPSummaryResponse,
)
async def get_pop_summary(
    device_code: Optional[str] = Query(None, max_length=64),
    campaign_code: Optional[str] = Query(None, max_length=64),
    creative_code: Optional[str] = Query(None, max_length=64),
    placement_code: Optional[str] = Query(None, max_length=64),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("reports.read")),
):
    """Aggregated PoP summary — safe counts for portal report KPIs.

    Requires ``reports.read`` permission.
    Never returns: raw UUIDs, tokens, secrets, backend URLs, manifest internals.
    """
    conditions = []
    if device_code:
        conditions.append(KsoProofOfPlayEvent.device_code == device_code)
    if campaign_code:
        conditions.append(KsoProofOfPlayEvent.campaign_code == campaign_code)
    if creative_code:
        conditions.append(KsoProofOfPlayEvent.creative_code == creative_code)
    if placement_code:
        conditions.append(KsoProofOfPlayEvent.placement_code == placement_code)
    if date_from:
        conditions.append(KsoProofOfPlayEvent.received_at >= date_from)
    if date_to:
        conditions.append(KsoProofOfPlayEvent.received_at <= date_to)

    # Total events
    q = _select(func.count()).select_from(KsoProofOfPlayEvent)
    if conditions:
        q = q.where(and_(*conditions))
    total = (await db.execute(q)).scalar() or 0

    # Unique devices
    q = _select(func.count(_distinct(KsoProofOfPlayEvent.device_code)))
    q = q.select_from(KsoProofOfPlayEvent)
    if conditions:
        q = q.where(and_(*conditions))
    unique_devices = (await db.execute(q)).scalar() or 0

    # Unique campaigns
    q = _select(func.count(_distinct(KsoProofOfPlayEvent.campaign_code)))
    q = q.select_from(KsoProofOfPlayEvent)
    if conditions:
        q = q.where(and_(*conditions))
    unique_campaigns = (await db.execute(q)).scalar() or 0

    # Unique creatives
    q = _select(func.count(_distinct(KsoProofOfPlayEvent.creative_code)))
    q = q.select_from(KsoProofOfPlayEvent)
    if conditions:
        q = q.where(and_(*conditions))
    unique_creatives = (await db.execute(q)).scalar() or 0

    # Unique placements
    q = _select(func.count(_distinct(KsoProofOfPlayEvent.placement_code)))
    q = q.select_from(KsoProofOfPlayEvent)
    if conditions:
        q = q.where(and_(*conditions))
    unique_placements = (await db.execute(q)).scalar() or 0

    async def _count_status(status_val: str) -> int:
        s = _select(func.count())
        s = s.select_from(KsoProofOfPlayEvent)
        sc = KsoProofOfPlayEvent.status == status_val
        s = s.where(and_(sc, *conditions) if conditions else sc)
        return (await db.execute(s)).scalar() or 0

    accepted = await _count_status("accepted")
    rejected = await _count_status("rejected")
    duplicate = await _count_status("duplicate")

    # Unknown status (not accepted/rejected/duplicate)
    uq = _select(func.count())
    uq = uq.select_from(KsoProofOfPlayEvent)
    unk = KsoProofOfPlayEvent.status.notin_(["accepted", "rejected", "duplicate"])
    uq = uq.where(and_(unk, *conditions) if conditions else unk)
    unknown_status = (await db.execute(uq)).scalar() or 0

    # Last event
    lq = _select(KsoProofOfPlayEvent.received_at)
    lq = lq.select_from(KsoProofOfPlayEvent)
    if conditions:
        lq = lq.where(and_(*conditions))
    lq = lq.order_by(KsoProofOfPlayEvent.received_at.desc()).limit(1)
    last_row = (await db.execute(lq)).scalar_one_or_none()

    return PoPSummaryResponse(
        total_events=total,
        unique_devices=unique_devices,
        unique_campaigns=unique_campaigns,
        unique_creatives=unique_creatives,
        unique_placements=unique_placements,
        accepted=accepted,
        rejected=rejected,
        duplicate=duplicate,
        unknown_status=unknown_status,
        last_event_at=last_row,
    )


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
