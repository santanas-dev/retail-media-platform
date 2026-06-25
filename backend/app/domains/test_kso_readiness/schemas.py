"""Test KSO Readiness — safe control-plane readiness schemas.

All models are read-only. Never expose: backend_url, token, secret,
device_secret, raw UUID, file_path, sha256, storage_ref, minio/s3,
receipt/payment/fiscal/customer/card/barcode.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════
# Readiness Summary
# ══════════════════════════════════════════════════════════════════════

class ReadinessStatus(BaseModel):
    """Safe readiness status — NO secrets, NO UUIDs, NO URLs."""

    # Overall
    overall_ready: bool = False

    # Backend
    backend_healthy: bool = False

    # Device
    device_registered: bool = False
    device_code: Optional[str] = Field(default=None, max_length=64)

    # Manifest
    manifest_published: bool = False
    manifest_code: Optional[str] = Field(default=None, max_length=64)
    manifest_has_creative_code: bool = False
    manifest_has_media_ref: bool = False
    manifest_item_count: int = 0

    # Campaign/Placement chain
    campaign_registered: bool = False
    campaign_code: Optional[str] = Field(default=None, max_length=64)
    placement_registered: bool = False
    placement_code: Optional[str] = Field(default=None, max_length=64)
    creative_registered: bool = False
    creative_code: Optional[str] = Field(default=None, max_length=64)

    # Sidecar config (safe hints only — no actual config values)
    sidecar_config_required: bool = True
    sidecar_config_fields: list[str] = Field(default_factory=list)

    # Media cache (safe booleans only — no paths)
    media_cache_ready: bool = False
    media_cache_items_expected: int = 0

    # PoP
    pop_endpoint_ready: bool = True  # endpoint exists in code
    pop_last_count: int = 0

    # Report
    portal_report_ready: bool = True  # page exists
    portal_report_filter_creative_code: bool = True

    # Phase D gate
    phase_d_requires_approval: bool = True
    phase_d_blocked: bool = True
    phase_d_block_reason: str = "Explicit manual approval required before any physical X11 window"

    # Readiness reasons (human-readable, safe)
    readiness_reasons: list[str] = Field(default_factory=list)

    # Timestamps
    checked_at: datetime = Field(default_factory=lambda: datetime.utcnow())
