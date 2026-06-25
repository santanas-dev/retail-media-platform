"""Proof-of-Play KSO service — test KSO technical validation ingest.

Implements minimal PoP ingest with safe-code correlation:
  device_code → latest published GeneratedManifest
  → placement_code → KsoPlacement
  → campaign_code, creative_code

Enterprise PoP (device_gateway ProofOfPlayEvent) is NOT affected.
"""

import hashlib
import json as _json
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.proof_of_play.models import KsoProofOfPlayEvent
from app.domains.proof_of_play.schemas import (
    KsoPoPIngestRequest,
    KsoPoPIngestResponse,
    KsoPoPListResponse,
)
from app.domains.manifests.models import GeneratedManifest
from app.domains.scheduling.models import KsoPlacement
from app.domains.hierarchy.models import KsoDevice
from app.domains.campaigns.models import CampaignCreative
from app.domains.media.models import Creative  # FK resolution for PoP event commit
from app.domains.identity.models import User  # FK resolution for GeneratedManifest relationships


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _compute_manifest_hash(body: dict) -> str:
    """SHA-256 of canonical JSON manifest body."""
    canonical = _json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _media_ref_in_manifest(body: dict, media_ref: str) -> bool:
    """Check if media_ref exists in manifest body items."""
    items = body.get("items", [])
    if not isinstance(items, list):
        return False
    for item in items:
        if isinstance(item, dict) and item.get("mediaRef") == media_ref:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════
# Ingest
# ══════════════════════════════════════════════════════════════════════

async def ingest_kso_pop(
    db: AsyncSession,
    device_code: str,
    data: KsoPoPIngestRequest,
) -> Tuple[Optional[KsoPoPIngestResponse], Optional[str]]:
    """Ingest a test KSO PoP event with safe-code correlation.

    Returns (response, error_detail).  Response is None on error.
    """

    # ── 1. Device must exist ────────────────────────────────────────
    device_result = await db.execute(
        _select(KsoDevice).where(KsoDevice.device_code == device_code)
    )
    device = device_result.scalar_one_or_none()
    if not device:
        return None, "device_not_found"

    # ── 2. Latest published manifest for device ─────────────────────
    manifest_result = await db.execute(
        _select(GeneratedManifest)
        .where(
            GeneratedManifest.device_code == device_code,
            GeneratedManifest.status == "published",
        )
        .order_by(GeneratedManifest.published_at.desc().nullslast())
        .limit(1)
    )
    manifest = manifest_result.scalar_one_or_none()
    if not manifest or not manifest.manifest_body_json:
        return None, "no_published_manifest"

    body = manifest.manifest_body_json

    # ── 3. Optional hash/version verification ───────────────────────
    if data.manifest_version_id:
        if data.manifest_version_id != str(manifest.id):
            return None, "manifest_version_mismatch"

    if data.manifest_hash:
        computed = _compute_manifest_hash(body)
        if data.manifest_hash != computed:
            return None, "manifest_hash_mismatch"

    # ── 4. media_ref must exist in manifest items ───────────────────
    if not _media_ref_in_manifest(body, data.media_ref):
        return None, "unknown_media_ref"

    # ── 5. Correlation: placement → campaign + creative ─────────────
    placement = None
    if manifest.placement_code:
        placement_result = await db.execute(
            _select(KsoPlacement).where(
                KsoPlacement.placement_code == manifest.placement_code
            )
        )
        placement = placement_result.scalar_one_or_none()

    if not placement:
        return None, "placement_not_found"

    campaign_code = placement.campaign_code
    creative_code = placement.creative_code

    # Verify creative_code belongs to campaign via CampaignCreative + Campaign join
    from app.domains.campaigns.models import Campaign as _Campaign
    from sqlalchemy import and_

    cc_result = await db.execute(
        _select(CampaignCreative)
        .join(_Campaign, _Campaign.id == CampaignCreative.campaign_id)
        .where(
            and_(
                CampaignCreative.creative_code == creative_code,
                _Campaign.campaign_code == campaign_code,
            )
        )
    )
    campaign_creative = cc_result.scalar_one_or_none()
    if not campaign_creative:
        return None, "creative_not_in_campaign"

    # ── 6. Duplicate check (idempotent accepted) ────────────────────
    existing_result = await db.execute(
        _select(KsoProofOfPlayEvent).where(
            KsoProofOfPlayEvent.event_code == data.event_code,
        )
    )
    existing = existing_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing:
        # Idempotent: return existing as accepted
        return KsoPoPIngestResponse(
            status="accepted",
            event_code=existing.event_code,
            device_code=existing.device_code,
            placement_code=existing.placement_code,
            campaign_code=existing.campaign_code,
            creative_code=existing.creative_code,
            received_at=existing.received_at,
        ), None

    # ── 7. Store ────────────────────────────────────────────────────
    event = KsoProofOfPlayEvent(
        event_code=data.event_code,
        device_code=device_code,
        placement_code=manifest.placement_code,
        campaign_code=campaign_code,
        creative_code=creative_code,
        manifest_code=manifest.manifest_code,
        media_ref=data.media_ref,
        event_type=data.event_type,
        status="accepted",
        played_at=data.played_at,
        duration_ms=data.duration_ms,
        received_at=now,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    return KsoPoPIngestResponse(
        status="accepted",
        event_code=event.event_code,
        device_code=event.device_code,
        placement_code=event.placement_code,
        campaign_code=event.campaign_code,
        creative_code=event.creative_code,
        received_at=event.received_at,
    ), None


# ══════════════════════════════════════════════════════════════════════
# List (read-only, safe projection)
# ══════════════════════════════════════════════════════════════════════

async def list_kso_pop_events(
    db: AsyncSession,
    *,
    device_code: Optional[str] = None,
    campaign_code: Optional[str] = None,
    creative_code: Optional[str] = None,
    placement_code: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[KsoPoPListResponse]:
    """List KSO PoP events with optional filters (safe projection).

    Never returns: id (raw UUID), manifest_version_id, manifest_hash,
    backend_url, tokens, file_path, sha256, storage_ref, minio,
    device_secret, client_secret.
    """

    stmt = _select(KsoProofOfPlayEvent)

    if device_code:
        stmt = stmt.where(KsoProofOfPlayEvent.device_code == device_code)
    if campaign_code:
        stmt = stmt.where(KsoProofOfPlayEvent.campaign_code == campaign_code)
    if creative_code:
        stmt = stmt.where(KsoProofOfPlayEvent.creative_code == creative_code)
    if placement_code:
        stmt = stmt.where(KsoProofOfPlayEvent.placement_code == placement_code)
    if date_from:
        stmt = stmt.where(KsoProofOfPlayEvent.received_at >= date_from)
    if date_to:
        stmt = stmt.where(KsoProofOfPlayEvent.received_at <= date_to)

    stmt = stmt.order_by(KsoProofOfPlayEvent.received_at.desc())
    stmt = stmt.offset(offset).limit(min(limit, 500))

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        KsoPoPListResponse(
            event_code=r.event_code,
            device_code=r.device_code,
            placement_code=r.placement_code,
            campaign_code=r.campaign_code,
            creative_code=r.creative_code,
            media_ref=r.media_ref,
            event_type=r.event_type,
            status=r.status,
            played_at=r.played_at,
            duration_ms=r.duration_ms,
            received_at=r.received_at,
        )
        for r in rows
    ]
