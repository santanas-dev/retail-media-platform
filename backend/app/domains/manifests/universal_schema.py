"""
B.5.1 — Universal Manifest Schema v1 Contracts.

Channel-agnostic manifest schema. Pydantic models only — no DB writes,
no API routes, no migrations, no signing implementation.

Schema defined in docs/architecture/b5-universal-manifest-schema-design-gate.md.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class ManifestSignatureStatus(str, Enum):
    UNSIGNED = "unsigned"
    SIGNED = "signed"
    INVALID = "invalid"


class ManifestStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    PUBLISHED = "published"
    REVOKED = "revoked"


# ═══════════════════════════════════════════════════════════════════════════
# Manifest blocks
# ═══════════════════════════════════════════════════════════════════════════

class ManifestCampaign(BaseModel):
    """Campaign info in manifest — safe, no internal-only fields."""
    campaign_id: UUID | None = Field(default=None, description="Internal campaign ID (for audit)")
    campaign_code: str | None = Field(default=None, description="Safe campaign code")
    campaign_name: str | None = Field(default=None, description="Human-readable name")
    advertiser_id: UUID | None = Field(default=None, description="Advertiser ID (for RLS/audit)")
    advertiser_code: str | None = Field(default=None, description="Safe advertiser code")


class ManifestPlacement(BaseModel):
    """Placement info in manifest."""
    placement_id: UUID | None = Field(default=None, description="Internal placement ID (for audit)")
    placement_code: str = Field(..., min_length=1, description="Safe placement code")
    placement_name: str | None = Field(default=None, description="Human-readable name")
    channel_code: str = Field(..., min_length=1, description="Channel code this placement belongs to")
    status: str | None = Field(default=None, description="Placement status")
    priority: int = Field(default=0, description="Placement priority")
    start_date: str | None = Field(default=None, description="Start date (YYYY-MM-DD)")
    end_date: str | None = Field(default=None, description="End date (YYYY-MM-DD)")


class ManifestTarget(BaseModel):
    """Target specification — channel-agnostic, no KSO-specific fields."""
    target_type: str = Field(..., min_length=1, description="Target type (store/surface/carrier/region)")
    store_code: str | None = Field(default=None, description="Store code")
    store_name: str | None = Field(default=None, description="Store name")
    display_surface_code: str | None = Field(default=None, description="Display surface code")
    display_surface_name: str | None = Field(default=None, description="Display surface name")
    logical_carrier_code: str | None = Field(default=None, description="Logical carrier code")
    logical_carrier_name: str | None = Field(default=None, description="Logical carrier name")
    physical_device_code: str | None = Field(default=None, description="Physical device code")
    physical_device_name: str | None = Field(default=None, description="Physical device name")
    device_type_code: str | None = Field(default=None, description="Device type code")
    capability_profile_code: str | None = Field(default=None, description="Capability profile code")
    capability_profile_name: str | None = Field(default=None, description="Capability profile name")


class ManifestContentItem(BaseModel):
    """One creative/rendition item in manifest content."""
    creative_code: str | None = Field(default=None, description="Creative code")
    creative_name: str | None = Field(default=None, description="Creative name")
    rendition_ref: str | None = Field(default=None, description="Rendition reference")
    media_type: str = Field(..., min_length=1, description="MIME type (image/png, video/mp4, ...)")
    format: str | None = Field(default=None, description="Format specifier")
    duration_ms: int | None = Field(default=None, description="Duration in milliseconds")
    checksum: str | None = Field(default=None, description="Content checksum (sha256:...)")
    storage_ref: str | None = Field(default=None, description="Safe storage reference — no secrets, tokens, or signed URLs")


class ManifestSchedule(BaseModel):
    """Schedule block."""
    start: str | None = Field(default=None, description="Schedule start (ISO datetime)")
    end: str | None = Field(default=None, description="Schedule end (ISO datetime)")
    timezone: str | None = Field(default=None, description="IANA timezone (e.g. Europe/Moscow)")


class ManifestPlayback(BaseModel):
    """Playback configuration."""
    proof_type: str | None = Field(default=None, description="Proof type from capability profile")
    loop: bool | None = Field(default=None, description="Loop mode")
    order: str | None = Field(default=None, description="Playback order (sequential/random)")
    frequency: str | None = Field(default=None, description="Playback frequency descriptor")


class ManifestAdapterPayload(BaseModel):
    """Channel-specific adapter payload — isolated from universal schema."""
    channel_code: str = Field(..., min_length=1, description="Channel code this payload targets")
    adapter_name: str = Field(..., min_length=1, description="Adapter name that built this payload")
    payload_schema_version: str = Field(default="1.0", description="Version of payload schema")
    payload: dict[str, Any] = Field(default_factory=dict, description="Channel-specific payload data")


class ManifestSecurity(BaseModel):
    """Security metadata — signing info (no actual signature implementation yet)."""
    signature_status: ManifestSignatureStatus = Field(
        default=ManifestSignatureStatus.UNSIGNED,
        description="Signature status",
    )
    signed_at: datetime | None = Field(default=None, description="When signed")
    signature_algorithm: str | None = Field(default=None, description="Algorithm (HS256, RS256, ...)")
    content_hash: str | None = Field(default=None, description="Canonical JSON hash (sha256:...)")


class ManifestCapability(BaseModel):
    """Capability info from device profile — what the device supports."""
    proof_type: str = Field(..., min_length=1, description="Proof type (real_playback, idle_impression, ...)")
    resolution: str | None = Field(default=None, description="Resolution (e.g. 768x1024)")
    orientation: str | None = Field(default=None, description="Orientation (portrait/landscape)")
    supported_formats: list[str] = Field(default_factory=list, description="Supported MIME types")
    max_file_size: int | None = Field(default=None, description="Max file size in bytes")
    max_duration_ms: int | None = Field(default=None, description="Max duration in milliseconds")
    interactive: bool = Field(default=False, description="Interactive device flag")


class ManifestMetadata(BaseModel):
    """Metadata block."""
    dry_run: bool = Field(default=False, description="Dry-run flag")
    source: str | None = Field(default=None, description="Generator source (orchestrator, publication)")
    build_id: str | None = Field(default=None, description="Build identifier")
    warnings: list[str] = Field(default_factory=list, description="Warnings during generation")
    errors: list[str] = Field(default_factory=list, description="Errors during generation")


# ═══════════════════════════════════════════════════════════════════════════
# Universal Manifest v1
# ═══════════════════════════════════════════════════════════════════════════

class UniversalManifestV1(BaseModel):
    """Universal Manifest Schema v1 — channel-agnostic.

    This is a pure schema/contract. No DB writes, no API, no signing.
    Built from OrchestratorContext + adapter payload (future B.5.2).
    """

    manifest_version: str = Field(default="1.0", description="Schema version (SemVer)")
    manifest_id: str | None = Field(default=None, description="Unique deterministic manifest key")
    generated_at: datetime | None = Field(default=None, description="Generation timestamp")
    schema_version: int = Field(default=1, ge=1, description="Integer schema version")
    status: ManifestStatus = Field(default=ManifestStatus.DRAFT, description="Manifest lifecycle status")

    campaign: ManifestCampaign = Field(..., description="Campaign info")
    placement: ManifestPlacement = Field(..., description="Placement info")
    targets: list[ManifestTarget] = Field(default_factory=list, description="Target specifications (min 1)")
    content: list[ManifestContentItem] = Field(default_factory=list, description="Content items (min 1 for final)")

    schedule: ManifestSchedule | None = Field(default=None, description="Schedule info")
    playback: ManifestPlayback | None = Field(default=None, description="Playback config")

    adapter_payload: ManifestAdapterPayload | None = Field(default=None, description="Channel-specific payload")
    security: ManifestSecurity = Field(default_factory=ManifestSecurity, description="Security metadata")
    capability: ManifestCapability | None = Field(default=None, description="Device capability info")

    metadata: ManifestMetadata = Field(default_factory=ManifestMetadata, description="Generation metadata")

    @model_validator(mode="after")
    def _channel_code_consistency(self) -> "UniversalManifestV1":
        """Validate adapter_payload.channel_code matches placement.channel_code."""
        if self.adapter_payload and self.placement:
            if self.adapter_payload.channel_code != self.placement.channel_code:
                raise ValueError(
                    f"adapter_payload.channel_code '{self.adapter_payload.channel_code}' "
                    f"does not match placement.channel_code '{self.placement.channel_code}'"
                )
        return self


# ═══════════════════════════════════════════════════════════════════════════
# Validation helpers
# ═══════════════════════════════════════════════════════════════════════════

FORBIDDEN_SECRET_KEYS: frozenset[str] = frozenset({
    "token", "secret", "password", "credential", "credentials",
    "access_key", "private_key", "public_key", "api_key",
    "authorization", "cookie", "jwt",
    "access_token", "refresh_token",
    "backend_base_url", "backend_url",
    "s3://", "minio", "bucket",
    "device_secret", "signing_key",
    "passwd",
})

FORBIDDEN_SECRET_PATTERNS: tuple[str, ...] = (
    "sk-", "pk-", "sig-",
    "bearer ", "bearer\t",
    "x-amz-signature", "x-amz-credential",
    "sp=rl", "sig=", "se=",  # SAS token patterns
    "?token=", "&token=", "?access_token=", "&access_token=",
)

FORBIDDEN_KSO_REFERENCES: frozenset[str] = frozenset({
    "kso_device_code", "kso_placement_code",
    "generated_manifest_id", "generated_manifest_code",
})


class ManifestIssue(BaseModel):
    """Structured validation issue."""
    code: str = Field(..., description="Error code")
    path: str = Field(default="", description="Field path in manifest")
    message: str = Field(..., description="Human-readable message")
    severity: str = Field(default="error", description="error/warning")


def validate_required_fields(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate required fields are present and non-empty.

    Checks:
      - manifest_version is set
      - campaign is present and has campaign_code
      - placement is present and has placement_code + channel_code
      - targets is non-empty
    """
    issues: list[ManifestIssue] = []

    if not manifest.manifest_version or not manifest.manifest_version.strip():
        issues.append(ManifestIssue(
            code="missing_manifest_version",
            path="manifest_version",
            message="manifest_version is required",
        ))

    if not hasattr(manifest, "campaign") or manifest.campaign is None:
        issues.append(ManifestIssue(
            code="missing_campaign",
            path="campaign",
            message="campaign block is required",
        ))
    elif not manifest.campaign.campaign_code or not manifest.campaign.campaign_code.strip():
        issues.append(ManifestIssue(
            code="missing_campaign_code",
            path="campaign.campaign_code",
            message="campaign.campaign_code is required",
        ))

    if not hasattr(manifest, "placement") or manifest.placement is None:
        issues.append(ManifestIssue(
            code="missing_placement",
            path="placement",
            message="placement block is required",
        ))
    else:
        if not manifest.placement.placement_code or not manifest.placement.placement_code.strip():
            issues.append(ManifestIssue(
                code="missing_placement_code",
                path="placement.placement_code",
                message="placement.placement_code is required",
            ))
        if not manifest.placement.channel_code or not manifest.placement.channel_code.strip():
            issues.append(ManifestIssue(
                code="missing_channel_code",
                path="placement.channel_code",
                message="placement.channel_code is required",
            ))

    if not manifest.targets:
        issues.append(ManifestIssue(
            code="missing_targets",
            path="targets",
            message="at least one target is required",
        ))

    return issues


def _check_value_for_secrets(value: str, path: str) -> list[ManifestIssue]:
    """Check a single string value for secret patterns."""
    issues: list[ManifestIssue] = []
    lower_val = value.lower()

    for fk in FORBIDDEN_SECRET_KEYS:
        if fk in lower_val:
            issues.append(ManifestIssue(
                code="forbidden_value",
                path=path,
                message=f"Value at '{path}' contains forbidden key pattern: '{fk}'",
            ))
            break  # One issue per field is enough

    for pattern in FORBIDDEN_SECRET_PATTERNS:
        if lower_val.startswith(pattern):
            issues.append(ManifestIssue(
                code="forbidden_value",
                path=path,
                message=f"Value at '{path}' starts with forbidden pattern: '{pattern}'",
            ))
            break

    return issues


def _recursive_check(obj: Any, path: str, forbidden_keys: frozenset[str]) -> list[ManifestIssue]:
    """Recursively walk dict/list and check for forbidden keys and secret values."""
    issues: list[ManifestIssue] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            lower_key = key.lower()
            if lower_key in forbidden_keys:
                issues.append(ManifestIssue(
                    code="forbidden_key",
                    path=f"{path}.{key}" if path else key,
                    message=f"Forbidden key '{key}' in manifest",
                ))

            current_path = f"{path}.{key}" if path else key

            if isinstance(value, str):
                issues.extend(_check_value_for_secrets(value, current_path))
            elif isinstance(value, (dict, list)):
                issues.extend(_recursive_check(value, current_path, forbidden_keys))

    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            current_path = f"{path}[{idx}]"
            if isinstance(item, str):
                issues.extend(_check_value_for_secrets(item, current_path))
            elif isinstance(item, (dict, list)):
                issues.extend(_recursive_check(item, current_path, forbidden_keys))

    return issues


def validate_no_secrets(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate manifest dict contains no secrets/forbidden keys.

    Checks recursively through all blocks for forbidden keys (token, secret,
    password, etc.) and forbidden value patterns.
    """
    raw = manifest.model_dump(mode="json", exclude_none=False)
    return _recursive_check(raw, "", FORBIDDEN_SECRET_KEYS)


def validate_manifest_schema(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate universal manifest against all schema rules.

    Combines:
      - validate_required_fields
      - validate_no_secrets
      - channel_code consistency (via model_validator)
      - signature_status check
      - additional structural checks
    """
    issues: list[ManifestIssue] = []

    # Required fields
    issues.extend(validate_required_fields(manifest))

    # No secrets
    issues.extend(validate_no_secrets(manifest))

    # Signature status must be valid enum value
    try:
        valid_signature = manifest.security.signature_status in ManifestSignatureStatus
    except TypeError:
        valid_signature = False
    if not valid_signature:
        issues.append(ManifestIssue(
            code="invalid_signature_status",
            path="security.signature_status",
            message=f"Invalid signature_status: '{manifest.security.signature_status}'",
        ))

    # If adapter_payload exists, payload must not be empty for non-draft
    if manifest.adapter_payload:
        if manifest.status not in (ManifestStatus.DRAFT,) and not manifest.adapter_payload.payload:
            issues.append(ManifestIssue(
                code="empty_adapter_payload",
                path="adapter_payload.payload",
                message="adapter_payload.payload must not be empty for non-draft manifest",
                severity="warning",
            ))

    # KSO-specific fields must not be referenced as required
    for target in manifest.targets:
        target_dict = target.model_dump()
        for fk_ref in FORBIDDEN_KSO_REFERENCES:
            if fk_ref in target_dict:
                issues.append(ManifestIssue(
                    code="kso_specific_field",
                    path=f"targets.{fk_ref}",
                    message=f"KSO-specific field '{fk_ref}' must not be referenced in universal manifest",
                ))

    return issues


# ═══════════════════════════════════════════════════════════════════════════
# Enhanced validators (B.5.3)
# ═══════════════════════════════════════════════════════════════════════════

def validate_campaign(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate campaign block.

    - campaign_code must not equal placement_code (no proxy)
    - campaign_data_incomplete warning for preview manifests
    - campaign_code required for non-draft (final) manifests
    """
    issues: list[ManifestIssue] = []
    campaign = manifest.campaign

    if not campaign:
        return issues

    # Campaign code must not be placement_code proxy
    placement_code = manifest.placement.placement_code if manifest.placement else None
    if campaign.campaign_code and placement_code and campaign.campaign_code == placement_code:
        issues.append(ManifestIssue(
            code="campaign_equals_placement_code",
            path="campaign.campaign_code",
            message="campaign_code must not equal placement_code (proxy detected)",
            severity="error",
        ))

    # Campaign data incomplete
    if not campaign.campaign_code:
        severity = "error" if manifest.status == ManifestStatus.PUBLISHED else "warning"
        issues.append(ManifestIssue(
            code="campaign_data_incomplete",
            path="campaign.campaign_code",
            message="Campaign data is incomplete — campaign_code not available in orchestrator context",
            severity=severity,
        ))

    return issues


def validate_targets(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate targets list.

    - Each playable target must have display_surface_code or physical_device_code
    - target_type must be valid
    - No KSO-specific required fields
    """
    issues: list[ManifestIssue] = []
    valid_target_types = {"store", "surface", "carrier", "region", "placement", "device"}

    for idx, target in enumerate(manifest.targets):
        prefix = f"targets[{idx}]"

        if target.target_type not in valid_target_types:
            issues.append(ManifestIssue(
                code="invalid_target_type",
                path=f"{prefix}.target_type",
                message=f"Invalid target_type '{target.target_type}'",
                severity="error",
            ))

        # Playable target must have at least surface or device
        if target.target_type in ("surface", "device") and not (
            target.display_surface_code or target.physical_device_code
        ):
            issues.append(ManifestIssue(
                code="playable_target_missing_surface_or_device",
                path=prefix,
                message="Playable target must have display_surface_code or physical_device_code",
                severity="error",
            ))

    return issues


def validate_capability(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate capability block.

    - proof_type required
    - supported_formats non-empty if content exists
    - content format must be in supported_formats
    """
    issues: list[ManifestIssue] = []
    cap = manifest.capability

    if not cap:
        return issues

    if not cap.proof_type:
        issues.append(ManifestIssue(
            code="missing_proof_type",
            path="capability.proof_type",
            message="capability.proof_type is required",
            severity="warning",
        ))

    # If content exists, check format compatibility
    if manifest.content:
        if not cap.supported_formats:
            issues.append(ManifestIssue(
                code="empty_supported_formats",
                path="capability.supported_formats",
                message="supported_formats is empty but content exists",
                severity="error",
            ))
        else:
            for idx, item in enumerate(manifest.content):
                if item.format and item.format not in cap.supported_formats:
                    issues.append(ManifestIssue(
                        code="unsupported_content_format",
                        path=f"content[{idx}].format",
                        message=f"Format '{item.format}' not in capability.supported_formats {cap.supported_formats}",
                        severity="error",
                    ))

    # Playback proof_type must match capability
    if manifest.playback and manifest.playback.proof_type:
        if manifest.playback.proof_type != cap.proof_type:
            issues.append(ManifestIssue(
                code="proof_type_mismatch",
                path="playback.proof_type",
                message=f"playback.proof_type '{manifest.playback.proof_type}' != capability.proof_type '{cap.proof_type}'",
                severity="error",
            ))

    return issues


def validate_content(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate content block.

    - For preview: content=[] raises warning
    - For final: content must be non-empty, each item must have media_type
    - storage_ref must be safe (checked by no-secrets)
    """
    issues: list[ManifestIssue] = []
    is_final = manifest.status in (ManifestStatus.PUBLISHED,)

    if not manifest.content:
        if is_final:
            issues.append(ManifestIssue(
                code="missing_content",
                path="content",
                message="Content is required for final manifest",
                severity="error",
            ))
        else:
            issues.append(ManifestIssue(
                code="content_not_available",
                path="content",
                message="Content not available in orchestrator context",
                severity="warning",
            ))
        return issues

    for idx, item in enumerate(manifest.content):
        if not item.media_type:
            issues.append(ManifestIssue(
                code="missing_media_type",
                path=f"content[{idx}].media_type",
                message="content item must have media_type",
                severity="error" if is_final else "warning",
            ))

        if is_final and not item.storage_ref:
            issues.append(ManifestIssue(
                code="missing_storage_ref",
                path=f"content[{idx}].storage_ref",
                message="content item must have storage_ref for final manifest",
                severity="error",
            ))

    return issues


def validate_schedule(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate schedule block.

    - start must be <= end
    """
    issues: list[ManifestIssue] = []
    sched = manifest.schedule

    if not sched:
        return issues

    if sched.start and sched.end and sched.start > sched.end:
        issues.append(ManifestIssue(
            code="schedule_inverted",
            path="schedule",
            message=f"schedule.start '{sched.start}' > schedule.end '{sched.end}'",
            severity="error",
        ))

    return issues


def validate_adapter_payload(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate adapter_payload block.

    - For non-draft: adapter_payload required
    - channel_code must match placement.channel_code (also checked by model_validator)
    """
    issues: list[ManifestIssue] = []
    is_final = manifest.status in (ManifestStatus.PUBLISHED,)

    if not manifest.adapter_payload:
        if is_final:
            issues.append(ManifestIssue(
                code="missing_adapter_payload",
                path="adapter_payload",
                message="adapter_payload is required for final manifest",
                severity="error",
            ))
        return issues

    ap = manifest.adapter_payload
    if not ap.payload and is_final:
        issues.append(ManifestIssue(
            code="empty_adapter_payload",
            path="adapter_payload.payload",
            message="adapter_payload.payload is empty for final manifest",
            severity="warning",
        ))

    return issues


# ═══════════════════════════════════════════════════════════════════════════
# Preview vs Final validation
# ═══════════════════════════════════════════════════════════════════════════

def validate_manifest_for_preview(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate manifest for dry-run preview.

    Lenient: allows missing content, campaign data, etc.
    """
    issues: list[ManifestIssue] = []
    issues.extend(validate_required_fields(manifest))
    issues.extend(validate_no_secrets(manifest))
    issues.extend(validate_targets(manifest))
    issues.extend(validate_campaign(manifest))
    # Content is optional for preview
    return issues


def validate_manifest_for_final_publish(manifest: UniversalManifestV1) -> list[ManifestIssue]:
    """Validate manifest for final publish.

    Strict: all blocks must be complete.
    NOTE: This is a future path — real publish is deferred.
    """
    issues: list[ManifestIssue] = []
    issues.extend(validate_required_fields(manifest))
    issues.extend(validate_no_secrets(manifest))
    issues.extend(validate_campaign(manifest))
    issues.extend(validate_targets(manifest))
    issues.extend(validate_capability(manifest))
    issues.extend(validate_content(manifest))
    issues.extend(validate_schedule(manifest))
    issues.extend(validate_adapter_payload(manifest))
    return issues
