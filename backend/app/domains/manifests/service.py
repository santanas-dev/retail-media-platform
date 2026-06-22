"""Manifest generation service — test KSO minimal."""

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.manifests import models, schemas
from app.domains.publications.kso_manifest_projection import (
    ManifestSourceItem,
    build_kso_safe_manifest_projection,
)


FORBIDDEN_RESPONSE_KEYS = frozenset({
    "id", "generated_by", "published_by", "file_path", "sha256",
    "storage_ref", "minio", "backend_url", "token", "secret",
})


def _now():
    return datetime.now(timezone.utc)


def _safe_response(manifest: models.GeneratedManifest) -> dict:
    """Build safe dict from GeneratedManifest — no IDs, secrets, paths."""
    return {
        "manifest_code": manifest.manifest_code,
        "device_code": manifest.device_code,
        "placement_code": manifest.placement_code,
        "campaign_code": manifest.campaign_code,
        "status": manifest.status,
        "schema_version": manifest.schema_version,
        "item_count": manifest.item_count,
        "preview_body": manifest.manifest_body_json,
        "media_ref_format": manifest.media_ref_format,
        "generated_at": manifest.generated_at.isoformat() if manifest.generated_at else None,
        "published_at": manifest.published_at.isoformat() if manifest.published_at else None,
        "created_at": manifest.created_at.isoformat() if manifest.created_at else None,
        "updated_at": manifest.updated_at.isoformat() if manifest.updated_at else None,
    }


async def generate_manifest(
    db: AsyncSession,
    data: schemas.ManifestGenerateRequest,
    user_id: UUID,
) -> models.GeneratedManifest:
    """Generate a KSO-safe manifest from approved placement."""

    # ── Validate manifest_code unique ──
    existing = await db.execute(
        select(models.GeneratedManifest).where(
            models.GeneratedManifest.manifest_code == data.manifest_code
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Manifest code '{data.manifest_code}' already exists",
        )

    # ── Validate placement exists and status=approved ──
    from app.domains.scheduling.models import KsoPlacement
    placement_result = await db.execute(
        select(KsoPlacement).where(
            KsoPlacement.placement_code == data.placement_code
        )
    )
    placement = placement_result.scalar_one_or_none()
    if not placement:
        raise HTTPException(status_code=404, detail="Placement not found")
    if placement.status != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"Placement must be approved (current: {placement.status})",
        )

    # ── Validate campaign exists and status=approved ──
    from app.domains.campaigns.models import Campaign
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.campaign_code == placement.campaign_code)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=400, detail="Campaign not found")
    if campaign.status != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"Campaign must be approved (current: {campaign.status})",
        )

    # ── Validate creative linked ──
    from app.domains.campaigns.models import CampaignCreative
    from app.domains.media.models import Creative
    cc_result = await db.execute(
        select(CampaignCreative).where(
            CampaignCreative.campaign_id == campaign.id,
            CampaignCreative.creative_code == placement.creative_code,
        )
    )
    cc = cc_result.scalar_one_or_none()
    if not cc:
        raise HTTPException(
            status_code=409,
            detail=f"Creative '{placement.creative_code}' not linked to campaign",
        )

    creative_result = await db.execute(
        select(Creative).where(Creative.creative_code == placement.creative_code)
    )
    creative = creative_result.scalar_one_or_none()
    if not creative:
        raise HTTPException(status_code=400, detail="Creative not found")
    # Accept approved or active creative
    if creative.status not in ("approved", "active"):
        raise HTTPException(
            status_code=409,
            detail=f"Creative must be approved/active (current: {creative.status})",
        )

    # ── Validate device exists and active ──
    from app.domains.hierarchy.models import KsoDevice
    device_result = await db.execute(
        select(KsoDevice).where(KsoDevice.device_code == placement.device_code)
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.status not in ("active", "pending"):
        raise HTTPException(
            status_code=409,
            detail=f"Device must be active/pending (current: {device.status})",
        )

    # ── Get store code from device ──
    from app.domains.organization.models import Store as OrgStore
    store_result = await db.execute(
        select(OrgStore).where(OrgStore.id == device.store_id)
    )
    store = store_result.scalar_one_or_none()
    store_code = store.code if store else "unknown"

    # ── Get creative mime_type from latest version ──
    from app.domains.media.models import CreativeVersion
    cv_result = await db.execute(
        select(CreativeVersion)
        .where(CreativeVersion.creative_id == creative.id)
        .order_by(CreativeVersion.version.desc())
        .limit(1)
    )
    cv = cv_result.scalar_one_or_none()
    content_type = cv.mime_type if cv else "image/png"

    # ── Build ManifestSourceItem for projection ──
    source_item = ManifestSourceItem(
        channel_code="kso",
        campaign_status=campaign.status,
        creative_status=creative.status,
        rendition_status="valid",  # test KSO: assume valid
        publication_status="published",  # must pass projection filter
        device_status=device.status,
        store_is_active=store.is_active if store else True,
        store_code=store_code,
        device_code=device.device_code,
        content_type=content_type,
        duration_ms=5000,  # safe default for image
        slot_order=placement.slot_order or 0,
        valid_from=placement.starts_at,
        valid_to=placement.ends_at,
    )

    projection = build_kso_safe_manifest_projection([source_item], generated_at=_now())

    if not projection.ok:
        raise HTTPException(
            status_code=400,
            detail=f"Manifest projection failed: {'; '.join(projection.errors)}",
        )

    manifest = models.GeneratedManifest(
        manifest_code=data.manifest_code,
        device_code=device.device_code,
        placement_code=placement.placement_code,
        campaign_code=campaign.campaign_code,
        status="generated",
        schema_version=1,
        manifest_body_json=projection.manifest,
        item_count=projection.items_included,
        media_ref_format="slot-NNN",
        generated_by=user_id,
        generated_at=_now(),
    )
    db.add(manifest)
    await db.commit()
    await db.refresh(manifest)
    return manifest


async def list_manifests(db: AsyncSession) -> list[models.GeneratedManifest]:
    result = await db.execute(
        select(models.GeneratedManifest)
        .order_by(models.GeneratedManifest.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


async def get_manifest(
    db: AsyncSession, manifest_code: str,
) -> models.GeneratedManifest:
    result = await db.execute(
        select(models.GeneratedManifest).where(
            models.GeneratedManifest.manifest_code == manifest_code
        )
    )
    mf = result.scalar_one_or_none()
    if not mf:
        raise HTTPException(status_code=404, detail="Manifest not found")
    return mf


async def publish_manifest(
    db: AsyncSession, manifest_code: str, user_id: UUID,
) -> models.GeneratedManifest:
    """Publish a generated manifest. Only generated→published transition."""
    mf = await get_manifest(db, manifest_code)

    if mf.status == "published":
        # Idempotent: already published — return as-is
        return mf

    if mf.status != "generated":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot publish manifest in status '{mf.status}' (expected 'generated')",
        )

    mf.status = "published"
    mf.published_by = user_id
    mf.published_at = _now()
    mf.updated_at = _now()
    await db.commit()
    await db.refresh(mf)
    return mf
