"""
B.5.2 — Universal Manifest Builder from Orchestrator Draft.

Maps OrchestratorContext + AdapterPayloadDraft → UniversalManifestV1.
Dry-run only. No DB writes. No API. No publication/manifest imports.
No generated_manifests. No KsoPlacement.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.manifests.universal_schema import (
    UniversalManifestV1,
    ManifestCampaign,
    ManifestPlacement,
    ManifestTarget,
    ManifestContentItem,
    ManifestSchedule,
    ManifestPlayback,
    ManifestAdapterPayload,
    ManifestSecurity,
    ManifestCapability,
    ManifestMetadata,
    ManifestIssue,
    ManifestSignatureStatus,
    ManifestStatus,
    # Validation helpers
    validate_manifest_schema,
    validate_required_fields,
    validate_no_secrets,
)
from app.domains.orchestrator.contracts import (
    AdapterPayloadDraft,
    OrchestratorContext,
    DeviceInfo,
    SurfaceInfo,
)
from app.domains.orchestrator.service import (
    build_manifest_context,
    check_capability_compatibility,
    select_adapter,
    build_adapter_payload,
    assemble_manifest_draft,
    ManifestDraft,
)


# ═══════════════════════════════════════════════════════════════════════════
# Manifest ID generation
# ═══════════════════════════════════════════════════════════════════════════

def _make_manifest_id(placement_code: str, channel_code: str, ts: datetime | None = None) -> str:
    """Build deterministic manifest key from placement + channel + timestamp."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    date_part = ts.strftime("%Y%m%d-%H%M%S")
    # Simple short hash from placement+channel+timestamp
    import hashlib
    raw = f"{placement_code}:{channel_code}:{ts.isoformat()}"
    short_hash = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"m-{date_part}-{short_hash}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# Manifest caption (display-safe name)
# ═══════════════════════════════════════════════════════════════════════════

def _manifest_caption(context: OrchestratorContext) -> str | None:
    """Build a human-readable caption for the manifest if available."""
    parts = []
    if context.channel_name:
        parts.append(context.channel_name)
    if context.placement_code:
        parts.append(f"#{context.placement_code}")
    return " — ".join(parts) if parts else None


# ═══════════════════════════════════════════════════════════════════════════
# Block builders
# ═══════════════════════════════════════════════════════════════════════════

def _build_campaign(context: OrchestratorContext) -> ManifestCampaign:
    """Build campaign block from context."""
    campaign_id = None
    if context.campaign_id:
        try:
            campaign_id = UUID(context.campaign_id)
        except (ValueError, TypeError):
            pass
    return ManifestCampaign(
        campaign_id=campaign_id,
        campaign_code=context.placement_code,  # proxy — real campaign_code from DB not in context
    )


def _build_placement(context: OrchestratorContext) -> ManifestPlacement:
    """Build placement block from context."""
    placement_id = None
    if context.placement_id:
        try:
            placement_id = UUID(context.placement_id)
        except (ValueError, TypeError):
            pass
    return ManifestPlacement(
        placement_id=placement_id,
        placement_code=context.placement_code,
        channel_code=context.channel_code,
        start_date=context.start_date,
        end_date=context.end_date,
    )


def _build_targets(context: OrchestratorContext) -> list[ManifestTarget]:
    """Build targets list from resolved chain."""
    targets: list[ManifestTarget] = []
    for device in context.devices:
        for surface in device.surfaces:
            t = ManifestTarget(
                target_type="surface",
                physical_device_code=device.device_code,
                display_surface_code=surface.surface_id,
                capability_profile_code=surface.proof_type,  # proxy for profile code
            )
            targets.append(t)
    # If no targets from devices, add a minimal one from placement code
    if not targets and context.placement_code:
        targets.append(ManifestTarget(
            target_type="placement",
            display_surface_code="unknown",
            capability_profile_code="unknown",
        ))
    return targets


def _build_schedule(context: OrchestratorContext) -> ManifestSchedule | None:
    """Build schedule from placement dates."""
    if context.start_date or context.end_date:
        return ManifestSchedule(
            start=context.start_date,
            end=context.end_date,
        )
    return None


def _build_playback(context: OrchestratorContext) -> ManifestPlayback | None:
    """Build playback from first surface's proof_type."""
    for device in context.devices:
        for surface in device.surfaces:
            if surface.proof_type:
                return ManifestPlayback(proof_type=surface.proof_type)
    return None


def _build_capability(context: OrchestratorContext) -> ManifestCapability | None:
    """Build capability block from first surface with data."""
    for device in context.devices:
        for surface in device.surfaces:
            if surface.proof_type:
                return ManifestCapability(
                    proof_type=surface.proof_type,
                    resolution=surface.resolution,
                    orientation=surface.orientation,
                    supported_formats=surface.formats,
                    max_file_size=surface.max_file_size,
                    max_duration_ms=surface.max_duration,
                    interactive=surface.interactive,
                )
    return None


def _build_adapter_payload(payload_draft: AdapterPayloadDraft) -> ManifestAdapterPayload:
    """Build adapter payload block from draft."""
    return ManifestAdapterPayload(
        channel_code=payload_draft.channel_code,
        adapter_name=payload_draft.adapter_name,
        payload_schema_version="1.0",
        payload=payload_draft.payload,
    )


def _build_content_from_context(context: OrchestratorContext) -> tuple[list[ManifestContentItem], list[str]]:
    """Build content block from context + available creative data.

    Returns (content_items, warnings). If no creative data available in context,
    returns empty list with a warning — creative integration is a deferred item
    (content mapping from CampaignCreative/CreativeVersion will come in later phase).
    """
    items: list[ManifestContentItem] = []
    warnings: list[str] = []

    # Try to extract creative codes from context
    if context.creative_codes:
        for cc in context.creative_codes:
            items.append(ManifestContentItem(
                creative_code=cc,
                media_type="application/octet-stream",  # placeholder
            ))
    else:
        # Content not available in orchestrator context — deferred item
        warnings.append("content_not_available_in_orchestrator_context")

    return items, warnings


# ═══════════════════════════════════════════════════════════════════════════
# Main builder
# ═══════════════════════════════════════════════════════════════════════════

def build_universal_manifest_from_draft(
    context: OrchestratorContext,
    payload_draft: AdapterPayloadDraft,
) -> UniversalManifestV1:
    """Build UniversalManifestV1 from OrchestratorContext + AdapterPayloadDraft.

    This is a PURE function — no DB, no HTTP, no side effects.
    Maps the resolved orchestrator context into the universal manifest schema.

    Args:
        context: Resolved OrchestratorContext from build_manifest_context()
        payload_draft: AdapterPayloadDraft from adapter.build_payload()

    Returns:
        UniversalManifestV1 with all mapped blocks.
    """
    now = _now()
    manifest_id = _make_manifest_id(context.placement_code, context.channel_code, now)

    # Build each block
    campaign = _build_campaign(context)
    placement = _build_placement(context)
    targets = _build_targets(context)
    content_items, content_warnings = _build_content_from_context(context)
    schedule = _build_schedule(context)
    playback = _build_playback(context)
    capability = _build_capability(context)
    adapter_payload = _build_adapter_payload(payload_draft)

    # Collect warnings
    warnings = list(payload_draft.warnings)
    warnings.extend(content_warnings)

    # If no devices resolved, warn
    if not context.devices:
        warnings.append("no_devices_resolved_in_context")

    metadata = ManifestMetadata(
        dry_run=True,
        source="orchestrator_draft",
        warnings=warnings,
        errors=[],
    )

    return UniversalManifestV1(
        manifest_version="1.0",
        manifest_id=manifest_id,
        generated_at=now,
        status=ManifestStatus.DRAFT,
        campaign=campaign,
        placement=placement,
        targets=targets,
        content=content_items,
        schedule=schedule,
        playback=playback,
        adapter_payload=adapter_payload,
        security=ManifestSecurity(signature_status=ManifestSignatureStatus.UNSIGNED),
        capability=capability,
        metadata=metadata,
    )


def validate_universal_manifest(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate a universal manifest against all schema rules.

    Uses B.5.1 validation helpers:
      - validate_required_fields()
      - validate_no_secrets()
      - validate_manifest_schema()

    Args:
        manifest: UniversalManifestV1 to validate.

    Returns:
        List of ManifestIssue (empty = valid).
    """
    return validate_manifest_schema(manifest)


# ═══════════════════════════════════════════════════════════════════════════
# Preview builder — orchestrator dry-run integration
# ═══════════════════════════════════════════════════════════════════════════

async def build_universal_manifest_preview(
    db: AsyncSession,
    placement_id: UUID,
    current_user: User | None = None,
) -> UniversalManifestV1:
    """Full dry-run preview: resolve chain → build adapter payload → build manifest.

    Uses B.4 orchestrator service for chain resolution, capability check,
    adapter selection, and payload building. Then maps to UniversalManifestV1.

    Does NOT:
      - Write to DB
      - Generate manifests (generated_manifests)
      - Call publish_batch()
      - Change publication status
      - Use KsoPlacement

    Args:
        db: Database session (read-only usage)
        placement_id: Placement UUID to preview
        current_user: Optional user for RLS enforcement

    Returns:
        UniversalManifestV1 with all resolved data.

    Raises:
        OrchestratorError subclasses for chain resolution failures
        (PlacementNotFound, PlacementHasNoChannel, UnsupportedChannel, etc.)
    """
    from app.domains.orchestrator.service import (
        PlacementNotFound,
        PlacementHasNoChannel,
        PlacementHasNoTargets,
        UnsupportedChannel,
    )

    # Step 1: Build context (resolve chain + RLS)
    context = await build_manifest_context(db, placement_id, current_user)

    # Step 2: Check capability compatibility
    cap_errors = check_capability_compatibility(context)
    if cap_errors:
        # Build partial manifest with errors
        now = _now()
        manifest_id = _make_manifest_id(context.placement_code, context.channel_code, now)
        campaign = _build_campaign(context)
        placement = _build_placement(context)
        targets = _build_targets(context)
        content_items, content_warnings = _build_content_from_context(context)

        metadata = ManifestMetadata(
            dry_run=True,
            source="orchestrator_draft",
            warnings=content_warnings,
            errors=cap_errors,
        )

        return UniversalManifestV1(
            manifest_version="1.0",
            manifest_id=manifest_id,
            generated_at=now,
            status=ManifestStatus.DRAFT,
            campaign=campaign,
            placement=placement,
            targets=targets,
            content=content_items,
            security=ManifestSecurity(signature_status=ManifestSignatureStatus.UNSIGNED),
            metadata=metadata,
        )

    # Step 3: Select adapter
    adapter = select_adapter(context.channel_code)

    # Step 4: Build adapter payload
    payload = await build_adapter_payload(context, adapter)

    # Step 5: Build universal manifest
    return build_universal_manifest_from_draft(context, payload)
