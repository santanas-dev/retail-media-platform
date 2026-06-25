"""Test KSO Readiness — safe control-plane readiness schemas.

All models are read-only. Never expose: backend_url, token, secret,
device_secret, raw UUID, file_path, sha256, storage_ref, minio/s3,
receipt/payment/fiscal/customer/card/barcode.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════
# Seed
# ══════════════════════════════════════════════════════════════════════

class SeedRequest(BaseModel):
    """Request to seed a synthetic test KSO chain. All fields optional — defaults used."""
    device_code: str = Field(default="test-dev-seed", min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    creative_code: str = Field(default="test-creative-seed", min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    campaign_code: str = Field(default="test-camp-seed", min_length=1, max_length=64)
    placement_code: str = Field(default="test-place-seed", min_length=3, max_length=64, pattern=r"^[a-z0-9_-]+$")
    manifest_code: str = Field(default="test-manifest-seed", min_length=1, max_length=64)


class SeedSummary(BaseModel):
    """Safe summary after seeding — NO UUIDs, NO secrets, NO paths."""
    # Idempotency
    was_already_seeded: bool = False

    # What was created/idempotently verified
    device_seeded: bool = False
    device_code: Optional[str] = None

    campaign_seeded: bool = False
    campaign_code: Optional[str] = None

    creative_seeded: bool = False
    creative_code: Optional[str] = None

    campaign_creative_linked: bool = False

    placement_seeded: bool = False
    placement_code: Optional[str] = None

    manifest_generated: bool = False
    manifest_code: Optional[str] = None
    manifest_published: bool = False
    manifest_item_count: int = 0
    manifest_has_creative_code: bool = False
    manifest_has_media_ref: bool = False

    # Timing
    seeded_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    # Human-readable summary
    summary: str = ""


# ══════════════════════════════════════════════════════════════════════
# Readiness Summary
# ══════════════════════════════════════════════════════════════════════

class SidecarConfigField(BaseModel):
    """One sidecar config field — name, status, description. NEVER the value."""
    name: str = Field(max_length=64)
    required: bool = True
    present: bool = False
    filled_by: str = "operator"           # always "operator" — no automation
    description: str = Field(default="", max_length=200)


class ReadinessStatus(BaseModel):
    """Safe readiness status — NO secrets, NO UUIDs, NO URLs."""

    # Overall
    overall_ready: bool = False

    # Backend
    backend_healthy: bool = False

    # Device
    device_registered: bool = False
    device_code: Optional[str] = Field(default=None, max_length=64)
    device_status: Optional[str] = Field(default=None, max_length=20)

    # Campaign / Creative / Placement chain
    campaign_registered: bool = False
    campaign_code: Optional[str] = Field(default=None, max_length=64)
    campaign_status: Optional[str] = Field(default=None, max_length=20)

    creative_registered: bool = False
    creative_code: Optional[str] = Field(default=None, max_length=64)
    creative_status: Optional[str] = Field(default=None, max_length=20)
    creative_ready: bool = False          # has version with content_type + dimensions
    creative_content_type: Optional[str] = Field(default=None, max_length=100)

    placement_registered: bool = False
    placement_code: Optional[str] = Field(default=None, max_length=64)
    placement_status: Optional[str] = Field(default=None, max_length=20)

    campaign_creative_linked: bool = False

    # Manifest
    manifest_published: bool = False
    manifest_code: Optional[str] = Field(default=None, max_length=64)
    manifest_status: Optional[str] = Field(default=None, max_length=30)
    manifest_item_count: int = 0
    manifest_has_creative_code: bool = False
    manifest_has_media_ref: bool = False
    manifest_generated_at: Optional[datetime] = None
    manifest_published_at: Optional[datetime] = None

    # Publication (for one-KSO, GeneratedManifest is the publication)
    publication_exists: bool = False      # same as manifest_published for one-KSO
    publication_status: Optional[str] = Field(default=None, max_length=30)

    # Sidecar config readiness (names + status only — NEVER values, URLs, tokens)
    sidecar_config_ready: bool = False
    sidecar_config_required_fields: list[str] = Field(default_factory=list)
    sidecar_config_missing_fields: list[str] = Field(default_factory=list)
    sidecar_config_checklist: list[SidecarConfigField] = Field(default_factory=list)

    # Media cache (safe booleans only — no paths)
    media_cache_ready: bool = False
    media_cache_items_expected: int = 0

    # PoP
    pop_endpoint_ready: bool = True       # endpoint exists in code
    pop_last_count: int = 0
    pop_report_ready: bool = False        # has actual events with creative_code

    # Report
    portal_report_ready: bool = True      # page exists
    portal_report_filter_creative_code: bool = True

    # Phase D gate
    phase_d_requires_approval: bool = True
    phase_d_blocked: bool = True
    phase_d_block_reason: str = "Explicit manual approval required before any physical X11 window"

    # Readiness reasons (human-readable, safe)
    readiness_reasons: list[str] = Field(default_factory=list)

    # Что осталось сделать (human-readable next steps)
    remaining_steps: list[str] = Field(default_factory=list)

    # Timestamps
    checked_at: datetime = Field(default_factory=lambda: datetime.utcnow())
