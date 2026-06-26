"""Device Dashboard: Pydantic schemas — safe projection for pilot dashboard."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DashboardHeartbeatSummary(BaseModel):
    """Latest heartbeat summary — no secrets, no raw UUIDs."""
    status: Optional[str] = None  # ok / warning / error
    age_seconds: Optional[int] = None
    app_version: Optional[str] = None
    cache_items_count: Optional[int] = None
    current_manifest_hash: Optional[str] = Field(
        None, max_length=64, description="SHA-256 hex — safe for display"
    )


class DashboardCredentialSummary(BaseModel):
    """Credential status summary — no secret_hash, no fingerprint internals."""
    status: Optional[str] = None  # active / expired / revoked / unknown
    credential_type: Optional[str] = None
    expires_at: Optional[datetime] = None


class DashboardSessionSummary(BaseModel):
    """Session summary — no access_token_hash."""
    active_count: int = 0
    last_used_at: Optional[datetime] = None


class DashboardPopSummary(BaseModel):
    """PoP event summary — no raw UUID, no details_json."""
    last_pop_at: Optional[datetime] = None
    events_count: int = 0


class DashboardManifestSummary(BaseModel):
    """Current manifest state summary — safe projection."""
    status: Optional[str] = None  # applied / failed / unknown
    manifest_code: Optional[str] = None
    manifest_hash: Optional[str] = Field(None, max_length=64)
    last_applied_at: Optional[datetime] = None


class DashboardMediaCacheSummary(BaseModel):
    """Media cache summary — no raw UUID, no path/URL."""
    cache_items_count: int = 0
    missing_items: int = 0
    failed_items: int = 0
    cache_health_status: Optional[str] = None  # healthy / warning / critical / unknown


class DeviceDashboardItem(BaseModel):
    """Aggregated device/sidecar status for the pilot dashboard.

    DELIBERATELY OMITTED FROM ALL FIELDS:
      - raw UUIDs (except where already safe and user expects code-based lookup),
        but id is NOT included — device_code is the key.
      - device_secret, secret_hash, access_token_hash, tokens
      - full backend URL, minio keys, presigned URLs, storage refs
      - IP address, MAC, hostname, serial number, filesystem paths
      - password, barcode, receipt, payment, fiscal, customer, card
      - personal/identifiable user data
    """

    # ── Identity ──────────────────────────────────────────────────
    device_code: str
    store_code: Optional[str] = None
    store_name: Optional[str] = None

    # ── Status ────────────────────────────────────────────────────
    kso_status: Optional[str] = None  # active / inactive / blocked / maintenance / lost
    gateway_status: Optional[str] = None  # pending / active / disabled

    # ── Heartbeat ─────────────────────────────────────────────────
    heartbeat: Optional[DashboardHeartbeatSummary] = None
    last_seen_at: Optional[datetime] = None

    # ── Sidecar ───────────────────────────────────────────────────
    sidecar_version: Optional[str] = None
    sidecar_status: Optional[str] = None  # Deferred to 39.4.4
    player_version: Optional[str] = None

    # ── Auth / Sessions ───────────────────────────────────────────
    credential: Optional[DashboardCredentialSummary] = None
    session: Optional[DashboardSessionSummary] = Field(default_factory=DashboardSessionSummary)

    # ── Current Manifest ──────────────────────────────────────────
    manifest: Optional[DashboardManifestSummary] = None

    # ── Media Cache ───────────────────────────────────────────────
    media_cache: Optional[DashboardMediaCacheSummary] = None

    # ── PoP ───────────────────────────────────────────────────────
    pop: Optional[DashboardPopSummary] = None

    # ── Readiness ─────────────────────────────────────────────────
    readiness_badge: str = "unknown"  # ready / warning / blocked / unknown
    readiness_reasons: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}
