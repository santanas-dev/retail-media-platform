"""
Hierarchy domain: Pydantic schemas for KSO device registry (Step 37.1).

Safe: never exposes device_secret, IP, MAC, hostname, serial, filesystem paths.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

CODE_PATTERN = r"^[a-z0-9_-]+$"

# Valid device statuses
DEVICE_STATUS_VALUES = {"active", "inactive", "blocked", "maintenance", "lost"}


class KsoDeviceCreate(BaseModel):
    """Create a KSO device registration."""
    store_id: UUID
    device_code: str = Field(
        min_length=1, max_length=64, pattern=CODE_PATTERN,
    )
    display_name: str | None = Field(None, max_length=255)
    status: str = Field(default="inactive", max_length=20)
    runtime_version: str | None = Field(None, max_length=32)
    player_version: str | None = Field(None, max_length=32)
    sidecar_version: str | None = Field(None, max_length=32)
    state_adapter_version: str | None = Field(None, max_length=32)
    manifest_version: str | None = Field(None, max_length=64)
    screen_width: int = Field(default=1920, ge=1, le=7680)
    screen_height: int = Field(default=1080, ge=1, le=4320)
    ad_zone_width: int = Field(default=1440, ge=1, le=7680)
    ad_zone_height: int = Field(default=1080, ge=1, le=4320)
    comment: str | None = Field(None, max_length=1000)


class KsoDeviceUpdate(BaseModel):
    """Update a KSO device registration."""
    display_name: str | None = Field(None, max_length=255)
    status: str | None = Field(None, max_length=20)
    runtime_version: str | None = Field(None, max_length=32)
    player_version: str | None = Field(None, max_length=32)
    sidecar_version: str | None = Field(None, max_length=32)
    state_adapter_version: str | None = Field(None, max_length=32)
    manifest_version: str | None = Field(None, max_length=64)
    screen_width: int | None = Field(None, ge=1, le=7680)
    screen_height: int | None = Field(None, ge=1, le=4320)
    ad_zone_width: int | None = Field(None, ge=1, le=7680)
    ad_zone_height: int | None = Field(None, ge=1, le=4320)
    comment: str | None = Field(None, max_length=1000)


class KsoDeviceResponse(BaseModel):
    """Safe KSO device response — no secrets, IP, MAC, hostname, serial."""
    id: UUID
    store_id: UUID
    device_code: str
    display_name: str | None
    status: str
    channel: str
    runtime_version: str | None
    player_version: str | None
    sidecar_version: str | None
    state_adapter_version: str | None
    manifest_version: str | None
    screen_width: int
    screen_height: int
    ad_zone_width: int
    ad_zone_height: int
    last_seen_at: datetime | None
    comment: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
