"""Device Gateway Foundation: Pydantic schemas."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Admin schemas ─────────────────────────────────────────────────

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
    fingerprint: Optional[str] = None

    model_config = {"from_attributes": True}


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


# ── Device API schemas ────────────────────────────────────────────

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


class DeviceHeartbeatRequest(BaseModel):
    status: Optional[str] = "ok"
    device_time: Optional[datetime] = None
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    storage_free_mb: Optional[int] = None
    cache_items_count: Optional[int] = None
    current_manifest_hash: Optional[str] = None
    details_json: dict[str, Any] = Field(default_factory=dict)
