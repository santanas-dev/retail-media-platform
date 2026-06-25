"""Test KSO Readiness service — read-only, safe, no secrets.

Checks readiness of backend components for a one-KSO E2E dry run.
All return values are safe — no UUIDs, no paths, no secrets, no URLs.
"""

from datetime import datetime, timezone

from sqlalchemy import select as _select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.test_kso_readiness.schemas import ReadinessStatus, SidecarConfigField
from app.domains.manifests.models import GeneratedManifest
from app.domains.hierarchy.models import KsoDevice
from app.domains.scheduling.models import KsoPlacement
from app.domains.campaigns.models import Campaign, CampaignCreative
from app.domains.media.models import Creative
from app.domains.proof_of_play.models import KsoProofOfPlayEvent


# ── Sidecar config checklist ────────────────────────────────────────────
# Full field list for one-KSO E2E dry run. Values MUST be filled by operator.
# These are field NAMES only — NEVER the actual values.
# Format: (name, required, description)

SIDECAR_CONFIG_CHECKLIST: list[dict] = [
    {"name": "backend_base_url",    "required": True,
     "description": "HTTPS URL of the Retail Media backend API (e.g. https://api.example.com)"},
    {"name": "device_code",        "required": True,
     "description": "KSO device code registered in backend"},
    {"name": "device_secret",      "required": True,
     "description": "Device authentication secret (set via secret-store-set, stored in dev_secret file)"},
    {"name": "agent_root",         "required": True,
     "description": "Absolute path to agent root directory (contains config/, state/, manifest/, media/, pop/)"},
    {"name": "manifest_poll_interval_sec", "required": False,
     "description": "Seconds between manifest sync attempts (default: 60)"},
    {"name": "media_cache_path",   "required": False,
     "description": "Path to media cache directory (default: $AGENT_ROOT/media)"},
    {"name": "pop_queue_path",     "required": False,
     "description": "Path to PoP pending queue (default: $AGENT_ROOT/pop/pending)"},
    {"name": "pop_upload_endpoint", "required": False,
     "description": "API path for PoP batch upload (default: /api/device-gateway/pop/batch)"},
    {"name": "state_file_path",    "required": False,
     "description": "Path to KSO state adapter JSON file (default: $AGENT_ROOT/state/kso_state.json)"},
    {"name": "kill_switch_path",   "required": False,
     "description": "Path to kill-switch marker file (default: $AGENT_ROOT/kill-switch)"},
    {"name": "runner_mode",        "required": False,
     "description": "Runner execution mode — 'daemon' (continuous) or 'once' (single cycle)"},
    {"name": "display_screen",     "required": False,
     "description": "X11 DISPLAY string for player window (e.g. ':0') — for Phase D only"},
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
    remaining: list[str] = []
    now = datetime.now(timezone.utc)

    # ── 1. Device check ──────────────────────────────────────────
    device_result = await db.execute(
        _select(KsoDevice).where(KsoDevice.device_code == device_code)
    )
    device = device_result.scalar_one_or_none()
    if device:
        status.device_registered = True
        status.device_code = device.device_code
        status.device_status = device.status
        if device.status != "active":
            reasons.append(f"Device status is '{device.status}', not 'active'")
    else:
        reasons.append(f"Device '{device_code}' not registered in backend")
        remaining.append("Register device in backend")

    # ── 2. Manifest (publication) check ──────────────────────────
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
        status.manifest_status = manifest.status
        status.publication_exists = True
        status.publication_status = manifest.status
        status.manifest_generated_at = manifest.generated_at
        status.manifest_published_at = manifest.published_at

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
            remaining.append("Regenerate manifest with creativeCode")
        if not has_mr:
            reasons.append("Manifest items missing mediaRef")
            remaining.append("Regenerate manifest with mediaRef")

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
                status.placement_status = placement.status

                if placement.campaign_code:
                    status.campaign_code = placement.campaign_code

                if placement.creative_code:
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
                    status.campaign_status = campaign.status
                    if campaign.status != "active":
                        reasons.append(f"Campaign status is '{campaign.status}', not 'active'")
                else:
                    reasons.append(f"Campaign '{placement.campaign_code}' not found")
                    remaining.append("Create campaign")

                # Creative check
                creative_result = await db.execute(
                    _select(Creative).where(
                        Creative.creative_code == placement.creative_code
                    )
                )
                creative = creative_result.scalar_one_or_none()
                if creative:
                    status.creative_registered = True
                    status.creative_status = creative.status
                    if creative.status != "active":
                        reasons.append(f"Creative status is '{creative.status}', not 'active'")

                    # Check creative_versions for content readiness
                    cv_result = await db.execute(sa_text(
                        "SELECT mime_type, width, height, file_size "
                        "FROM creative_versions "
                        "WHERE creative_id = :cid AND status = 'uploaded' "
                        "ORDER BY version DESC LIMIT 1"
                    ), {"cid": creative.id})
                    cv_row = cv_result.fetchone()
                    if cv_row:
                        status.creative_ready = True
                        status.creative_content_type = cv_row[0]
                    else:
                        reasons.append("Creative has no uploaded version")
                        remaining.append("Upload creative content")
                else:
                    reasons.append(f"Creative '{placement.creative_code}' not found")
                    remaining.append("Create creative")

                # CampaignCreative link
                cc_result = await db.execute(
                    _select(CampaignCreative).where(
                        CampaignCreative.creative_code == placement.creative_code
                    )
                )
                cc = cc_result.scalar_one_or_none()
                if cc:
                    status.campaign_creative_linked = True
                else:
                    reasons.append("Creative not linked to campaign (CampaignCreative missing)")
                    remaining.append("Link creative to campaign")
            else:
                reasons.append(f"Placement '{manifest.placement_code}' not found")
                remaining.append("Create placement")
        else:
            reasons.append("Manifest has no placement_code")
    else:
        reasons.append(f"No published manifest for device '{device_code}'")
        remaining.append("Generate and publish manifest")

    # ── 3. PoP check ─────────────────────────────────────────────
    pop_result = await db.execute(
        _select(KsoProofOfPlayEvent).where(
            KsoProofOfPlayEvent.device_code == device_code,
        ).limit(10)
    )
    pop_events = pop_result.scalars().all()
    status.pop_last_count = len(pop_events) if pop_events else 0

    # Check if PoP events have creative_code (real reporting readiness)
    if pop_events:
        has_cc_events = any(
            getattr(e, "creative_code", None) for e in pop_events
        )
        status.pop_report_ready = has_cc_events
        if not has_cc_events:
            reasons.append("PoP events exist but none have creative_code")
            remaining.append("Ensure PoP ingest includes creative_code")
    else:
        status.pop_report_ready = False

    # ── 4. Sidecar config checklist ────────────────────────────────
    checklist: list[SidecarConfigField] = []
    missing: list[str] = []
    required_names: list[str] = []

    for field_def in SIDECAR_CONFIG_CHECKLIST:
        field = SidecarConfigField(
            name=field_def["name"],
            required=field_def["required"],
            present=False,              # always false — operator must configure
            filled_by="operator",
            description=field_def["description"],
        )
        checklist.append(field)
        if field_def["required"]:
            required_names.append(field_def["name"])
            missing.append(field_def["name"])

    status.sidecar_config_required_fields = required_names
    status.sidecar_config_missing_fields = missing
    status.sidecar_config_checklist = checklist
    status.sidecar_config_ready = False  # always false until operator confirms

    if missing:
        remaining.append("Configure sidecar required fields: " + ", ".join(missing[:4]) + ("…" if len(missing) > 4 else ""))

    # ── 5. Media cache (always requires check on KSO) ────────────
    status.media_cache_ready = False
    status.media_cache_items_expected = status.manifest_item_count
    if status.media_cache_items_expected > 0:
        remaining.append(f"Ensure {status.media_cache_items_expected} media files cached on KSO")

    # ── 6. Phase D ───────────────────────────────────────────────
    remaining.append("Get manual approval for Phase D (controlled physical window)")

    # ── 7. Operator preflight steps (Phase A/B/C) ─────────────────
    operator_steps: list[str] = []

    # A: Backend
    operator_steps.append("Phase A1: Verify backend health at /health")
    if not status.overall_ready:
        operator_steps.append("Phase A2: Run seed — POST /api/test-kso/seed")
    else:
        operator_steps.append("Phase A2: Seed already complete ✅")
    operator_steps.append("Phase A3: Verify /api/test-kso/readiness → overall_ready: true")
    operator_steps.append("Phase A4: Verify Phase D is blocked (gate check)")

    # B: Sidecar config
    operator_steps.append("Phase B1: Fill local sidecar config on KSO — write-config + secret-store-set")
    operator_steps.append("Phase B2: Verify with sidecar config-status + secret-store-check (no values visible)")
    operator_steps.append("Phase B3: Confirm no real values committed to git/chat/docs")

    # C: Dry preflight
    operator_steps.append("Phase C1: Check portal /readiness page — all backend ✅, config checklist visible")
    operator_steps.append("Phase C2: Sync manifest on KSO — sidecar sync-manifest")
    operator_steps.append("Phase C3: Check media cache — sidecar doctor → cache_missing == 0")
    operator_steps.append("Phase C4: Verify PoP endpoint readiness")
    operator_steps.append("Phase C5: Verify kill-switch and state paths exist (checklist only, no X11)")

    status.required_operator_steps = operator_steps

    # ── 7. Overall readiness ─────────────────────────────────────
    status.overall_ready = all([
        status.device_registered and status.device_status == "active",
        status.manifest_published,
        status.manifest_has_creative_code,
        status.manifest_has_media_ref,
        status.campaign_registered and status.campaign_status == "active",
        status.placement_registered,
        status.creative_registered and status.creative_status == "active",
        status.creative_ready,
        status.campaign_creative_linked,
        status.sidecar_config_ready,
        status.media_cache_ready,
    ])

    if not status.overall_ready:
        reasons.append("Not all backend prerequisites met")

    status.readiness_reasons = reasons
    status.remaining_steps = remaining
    status.checked_at = now

    return status
