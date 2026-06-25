"""Test KSO Readiness service — read-only, safe, no secrets.

Checks readiness of backend components for a one-KSO E2E dry run.
All return values are safe — no UUIDs, no paths, no secrets, no URLs.
"""

from datetime import datetime, timezone

from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.test_kso_readiness.schemas import ReadinessStatus
from app.domains.manifests.models import GeneratedManifest
from app.domains.hierarchy.models import KsoDevice
from app.domains.scheduling.models import KsoPlacement
from app.domains.campaigns.models import Campaign, CampaignCreative
from app.domains.media.models import Creative
from app.domains.proof_of_play.models import KsoProofOfPlayEvent


# Fields that sidecar MUST have configured (safe hint names only)
SIDECAR_REQUIRED_FIELDS = [
    "backend_base_url",
    "device_code",
    "device_secret",
    "agent_root",
]


async def build_readiness_summary(
    db: AsyncSession,
    device_code: str,
) -> ReadinessStatus:
    """Build a safe readiness summary for a test KSO device.

    All checks are read-only. Never exposes:
      - backend_url, token, secret, device_secret
      - raw UUID, file_path, sha256, storage_ref, minio/s3
      - receipt, payment, fiscal, customer, card, barcode
    """
    status = ReadinessStatus()
    reasons: list[str] = []
    now = datetime.now(timezone.utc)

    # ── 1. Device check ──────────────────────────────────────────
    device_result = await db.execute(
        _select(KsoDevice).where(KsoDevice.device_code == device_code)
    )
    device = device_result.scalar_one_or_none()
    if device:
        status.device_registered = True
        status.device_code = device.device_code
    else:
        reasons.append(f"Device '{device_code}' not registered in backend")

    # ── 2. Manifest check ────────────────────────────────────────
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

    if manifest:
        status.manifest_published = True
        status.manifest_code = manifest.manifest_code

        body = manifest.manifest_body_json or {}
        items = body.get("items", [])
        status.manifest_item_count = len(items) if isinstance(items, list) else 0

        # Check for creativeCode and mediaRef in items
        has_cc = False
        has_mr = False
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    if item.get("creativeCode"):
                        has_cc = True
                    if item.get("mediaRef"):
                        has_mr = True
        status.manifest_has_creative_code = has_cc
        status.manifest_has_media_ref = has_mr

        if not has_cc:
            reasons.append("Manifest items missing creativeCode")
        if not has_mr:
            reasons.append("Manifest items missing mediaRef")

        # Placement check (from manifest)
        if manifest.placement_code:
            placement_result = await db.execute(
                _select(KsoPlacement).where(
                    KsoPlacement.placement_code == manifest.placement_code
                )
            )
            placement = placement_result.scalar_one_or_none()
            if placement:
                status.placement_registered = True
                status.placement_code = placement.placement_code
                status.campaign_code = placement.campaign_code
                status.creative_code = placement.creative_code

                # Campaign check
                campaign_result = await db.execute(
                    _select(Campaign).where(
                        Campaign.campaign_code == placement.campaign_code
                    )
                )
                campaign = campaign_result.scalar_one_or_none()
                if campaign:
                    status.campaign_registered = True

                # Creative check
                creative_result = await db.execute(
                    _select(Creative).where(
                        Creative.creative_code == placement.creative_code
                    )
                )
                creative = creative_result.scalar_one_or_none()
                if creative:
                    status.creative_registered = True

                # CampaignCreative link
                cc_result = await db.execute(
                    _select(CampaignCreative).where(
                        CampaignCreative.creative_code == placement.creative_code
                    )
                )
                cc = cc_result.scalar_one_or_none()
                if not cc:
                    reasons.append("Creative not linked to campaign (CampaignCreative missing)")
            else:
                reasons.append(f"Placement '{manifest.placement_code}' not found")
        else:
            reasons.append("Manifest has no placement_code")
    else:
        reasons.append(f"No published manifest for device '{device_code}'")

    # ── 3. PoP check ─────────────────────────────────────────────
    pop_result = await db.execute(
        _select(KsoProofOfPlayEvent).where(
            KsoProofOfPlayEvent.device_code == device_code,
        ).limit(10)
    )
    pop_events = pop_result.scalars().all()
    status.pop_last_count = len(pop_events) if pop_events else 0

    # ── 4. Sidecar config (hints only) ───────────────────────────
    status.sidecar_config_required = True
    status.sidecar_config_fields = list(SIDECAR_REQUIRED_FIELDS)

    # ── 5. Media cache (always requires check on KSO) ────────────
    status.media_cache_ready = False
    status.media_cache_items_expected = status.manifest_item_count

    # ── 6. Overall readiness ─────────────────────────────────────
    status.overall_ready = all([
        status.device_registered,
        status.manifest_published,
        status.manifest_has_creative_code,
        status.manifest_has_media_ref,
        status.campaign_registered,
        status.placement_registered,
        status.creative_registered,
    ])

    if not status.overall_ready:
        reasons.append("Not all backend prerequisites met")

    status.readiness_reasons = reasons
    status.checked_at = now

    return status
