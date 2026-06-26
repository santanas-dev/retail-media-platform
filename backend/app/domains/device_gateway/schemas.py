"""Device Gateway Foundation: Pydantic schemas."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GatewayDeviceCreate(BaseModel):
    device_code: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=64)
    device_name: Optional[str] = None
    physical_device_id: Optional[UUID] = None
    logical_carrier_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    channel_id: UUID
    store_id: UUID
    status: str = "pending"
    comment: Optional[str] = None


class GatewayDeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    status: Optional[str] = None
    comment: Optional[str] = None
    physical_device_id: Optional[UUID] = None
    logical_carrier_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    channel_id: Optional[UUID] = None
    store_id: Optional[UUID] = None


class GatewayDeviceResponse(BaseModel):
    id: UUID
    device_code: str
    device_name: Optional[str] = None
    physical_device_id: Optional[UUID] = None
    logical_carrier_id: Optional[UUID] = None
    display_surface_id: Optional[UUID] = None
    channel_id: UUID
    store_id: UUID
    status: str
    last_seen_at: Optional[datetime] = None
    registered_at: datetime
    disabled_at: Optional[datetime] = None
    comment: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DeviceCredentialResponse(BaseModel):
    """Credential info WITHOUT secret (for GET/PUT)."""
    id: UUID
    gateway_device_id: UUID
    credential_type: str
    status: str
    issued_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    fingerprint: Optional[str] = None

    model_config = {"from_attributes": True}


class DeviceCredentialCreatedResponse(BaseModel):
    """Credential WITH secret — returned ONLY on creation."""
    id: UUID
    gateway_device_id: UUID
    credential_type: str
    status: str
    device_secret: str  # plaintext — shown ONCE
    issued_at: datetime
    expires_at: Optional[datetime] = None
    fingerprint: Optional[str] = None

    model_config = {"from_attributes": True}


class DeviceHeartbeatRequest(BaseModel):
    status: str = "ok"  # ok / warning / error
    message: Optional[str] = None
    device_time: Optional[datetime] = None
    app_version: Optional[str] = Field(None, max_length=128)
    os_version: Optional[str] = Field(None, max_length=128)
    storage_free_mb: Optional[int] = Field(None, ge=0)
    cache_items_count: Optional[int] = Field(None, ge=0)
    current_manifest_hash: Optional[str] = Field(
        None, min_length=64, max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
    )
    sidecar_status: Optional[str] = Field(
        None, description="Sidecar agent status: stopped/starting/running/warning/error/unknown",
    )
    details_json: dict[str, Any] = Field(default_factory=dict)


class DeviceHeartbeatResponse(BaseModel):
    id: UUID
    gateway_device_id: UUID
    status: Optional[str] = None
    device_time: Optional[datetime] = None
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    storage_free_mb: Optional[int] = None
    cache_items_count: Optional[int] = None
    current_manifest_hash: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceEventResponse(BaseModel):
    id: UUID
    gateway_device_id: Optional[UUID] = None
    event_type: str
    severity: str
    message: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceAuthRequest(BaseModel):
    device_code: str
    device_secret: str


class DeviceAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    device_id: UUID
    device_code: str
    status: str


class DeviceMeResponse(BaseModel):
    device_id: UUID
    device_code: str
    device_name: Optional[str] = None
    status: str
    channel_id: UUID
    store_id: UUID
    last_seen_at: Optional[datetime] = None
    session_id: UUID


class DeviceManifestRequestResponse(BaseModel):
    id: UUID
    gateway_device_id: UUID
    manifest_version_id: Optional[UUID] = None
    publication_target_id: Optional[UUID] = None
    request_status: str
    client_manifest_hash: Optional[str] = None
    response_hash: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    message: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceManifestResponse(BaseModel):
    """Manifest delivered to a device (public)."""
    manifest_version_id: UUID
    manifest_items: list[dict[str, Any]] = Field(default_factory=list)


class DeviceManifestMetadataResponse(BaseModel):
    """Metadata for a manifest request."""


class MediaMetadata(BaseModel):
    sha256: str
    content_type: str
    size_bytes: Optional[int] = None
    duration_ms: Optional[int] = None


class DeviceMediaMetadataResponse(BaseModel):
    status: str = "ok"
    manifest_item_id: UUID
    sha256: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_ms: Optional[int] = None


class DeviceMediaRequestResponse(BaseModel):
    id: UUID
    gateway_device_id: UUID
    manifest_item_id: Optional[UUID] = None
    manifest_version_id: Optional[UUID] = None
    publication_target_id: Optional[UUID] = None
    request_status: str
    media_path: Optional[str] = None
    expected_sha256: Optional[str] = None
    client_cached_sha256: Optional[str] = None
    response_size_bytes: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    message: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceManifestCurrentResponse(BaseModel):
    """Response for /manifest/current — covers all states."""
    status: str  # "served", "not_modified", "no_manifest"
    manifest_version_id: Optional[UUID] = None
    manifest_hash: Optional[str] = None
    published_at: Optional[datetime] = None
    manifest: Optional[dict[str, Any]] = None

class DeviceMediaNotModifiedResponse(BaseModel):
    """Response when client cache is current."""
    status: Literal["not_modified"]


# ═══════════════════════════════════════════════════════════════════
#  Step 13 — PoP Ingest Core
# ═══════════════════════════════════════════════════════════════════


class PoPEventRequest(BaseModel):
    """Payload from a device with a proof-of-play event.

    manifest_item_id is optional for KSO channel events where server-side
    correlation is performed via manifest projection rather than direct ID.
    For KSO events, selected_order and selected_content_type are used
    for server-side correlation with the published manifest.
    """
    device_event_id: UUID
    manifest_item_id: Optional[UUID] = None
    selected_order: Optional[int] = None
    selected_content_type: Optional[str] = None
    played_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    play_status: Optional[str] = None
    media_sha256: Optional[str] = None
    schedule_item_id: Optional[UUID] = None
    player_version: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)


class PoPEventResponse(BaseModel):
    """Response to the device after processing a PoP event."""
    status: str  # accepted / duplicate / rejected
    proof_event_id: Optional[UUID] = None
    reason: Optional[str] = None


class PoPEventRead(BaseModel):
    """Admin-facing read model for a stored PoP event."""
    id: UUID
    gateway_device_id: UUID
    device_event_id: UUID
    manifest_item_id: Optional[UUID] = None
    manifest_version_id: Optional[UUID] = None
    publication_target_id: Optional[UUID] = None
    schedule_item_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None
    campaign_rendition_id: Optional[UUID] = None
    rendition_id: Optional[UUID] = None
    creative_version_id: Optional[UUID] = None
    played_at: Optional[datetime] = None
    received_at: datetime
    duration_ms: Optional[int] = None
    play_status: Optional[str] = None
    validation_status: str
    media_sha256: Optional[str] = None
    expected_sha256: Optional[str] = None
    player_version: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    rejection_reason: Optional[str] = None
    batch_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════
#  Step 14 — PoP Batch / Offline Ingest
# ═══════════════════════════════════════════════════════════════════


class PoPEventBatchItem(BaseModel):
    """Single event inside a batch — same shape as PoPEventRequest.

    manifest_item_id is optional for KSO channel events.
    selected_order and selected_content_type are used for KSO correlation.
    """
    device_event_id: UUID
    manifest_item_id: Optional[UUID] = None
    selected_order: Optional[int] = None
    selected_content_type: Optional[str] = None
    played_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    play_status: Optional[str] = None
    media_sha256: Optional[str] = None
    schedule_item_id: Optional[UUID] = None
    player_version: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)


class PoPBatchRequest(BaseModel):
    """Batch PoP envelope from a device."""
    batch_id: UUID
    sent_at: Optional[datetime] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    events: list[PoPEventBatchItem] = Field(min_length=1)


class PoPEventBatchResult(BaseModel):
    """Per-event result in batch response."""
    device_event_id: UUID
    status: str  # accepted / duplicate / rejected
    proof_event_id: Optional[UUID] = None
    reason: Optional[str] = None


class PoPBatchResponse(BaseModel):
    """Response to a batch PoP request."""
    status: str  # processed / partially_processed / rejected / duplicate_batch
    batch_id: UUID
    proof_batch_id: Optional[UUID] = None
    summary: Optional[dict[str, int]] = None
    results: list[PoPEventBatchResult] = Field(default_factory=list)


class PoPBatchRead(BaseModel):
    """Admin-facing read model for a PoP batch."""
    id: UUID
    gateway_device_id: UUID
    device_batch_id: UUID
    sent_at: Optional[datetime] = None
    received_at: datetime
    total_events: int
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    batch_status: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════
#  Content Sync State (Step 20) — Device Request / Response schemas
# ═══════════════════════════════════════════════════════════════════════


class ManifestApplyRequest(BaseModel):
    """Device reports manifest apply result."""
    manifest_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    status: Literal["applied", "failed"]
    device_reported_at: Optional[datetime] = None
    message: Optional[str] = Field(None, max_length=512)
    error_code: Optional[str] = Field(None, max_length=64)
    details_json: dict[str, Any] = Field(default_factory=dict)


class ManifestApplyResponse(BaseModel):
    status: str  # "ok"
    gateway_device_id: UUID
    manifest_version_id: UUID
    manifest_status: str  # "applied" | "failed"


class CacheReportItem(BaseModel):
    manifest_item_id: UUID
    status: Literal["cached", "missing", "failed", "invalid_hash", "evicted"]
    reported_sha256: Optional[str] = Field(
        None, min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$",
    )
    file_size_bytes: Optional[int] = Field(None, ge=0)
    cached_at: Optional[datetime] = None
    error_code: Optional[str] = Field(None, max_length=64)
    message: Optional[str] = Field(None, max_length=512)
    details_json: dict[str, Any] = Field(default_factory=dict)


class MediaCacheReportRequest(BaseModel):
    manifest_version_id: UUID
    manifest_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    device_reported_at: Optional[datetime] = None
    items: list[CacheReportItem] = Field(min_length=1, max_length=1000)
    details_json: dict[str, Any] = Field(default_factory=dict)


class MediaCacheReportResponse(BaseModel):
    status: str  # "ok"
    gateway_device_id: UUID
    manifest_version_id: UUID
    total_items: int
    cached_count: int
    missing_count: int
    failed_count: int
    invalid_hash_count: int
