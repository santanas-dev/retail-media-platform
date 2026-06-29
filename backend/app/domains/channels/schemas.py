"""
Channels & Devices domain: Pydantic schemas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

CODE_PATTERN = r"^[a-z0-9_-]+$"


# ── Channel ───────────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ChannelResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── DeviceType ────────────────────────────────────────────────────────────

class DeviceTypeCreate(BaseModel):
    channel_id: UUID
    code: str = Field(min_length=1, max_length=50, pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=255)


class DeviceTypeResponse(BaseModel):
    id: UUID
    channel_id: UUID
    code: str
    name: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── CapabilityProfile ────────────────────────────────────────────────────

class CapabilityProfileCreate(BaseModel):
    device_type_id: UUID
    resolution: str | None = Field(None, max_length=20)
    orientation: str = Field(default="landscape", max_length=20)
    proof_type: str = Field(min_length=1, max_length=50)
    interactive: bool = False
    cache_policy: str = Field(default="full", max_length=50)
    max_file_size: int | None = None
    max_duration: int | None = None


class CapabilityProfileResponse(BaseModel):
    id: UUID
    device_type_id: UUID
    resolution: str | None
    orientation: str | None
    proof_type: str
    interactive: bool
    cache_policy: str | None
    max_file_size: int | None
    max_duration: int | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── PhysicalDevice ────────────────────────────────────────────────────────

class PhysicalDeviceCreate(BaseModel):
    store_id: UUID
    device_type_id: UUID
    serial_number: str | None = Field(None, max_length=255)
    hw_fingerprint: str | None = Field(None, max_length=512)
    status: str = Field(default="offline", max_length=50)


class PhysicalDeviceResponse(BaseModel):
    id: UUID
    store_id: UUID
    device_type_id: UUID
    external_code: str | None = None
    serial_number: str | None
    hw_fingerprint: str | None
    status: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── LogicalCarrier ────────────────────────────────────────────────────────

class LogicalCarrierCreate(BaseModel):
    physical_device_id: UUID
    type: str = Field(min_length=1, max_length=50)
    zone: str | None = Field(None, max_length=100)
    position: str | None = Field(None, max_length=100)


class LogicalCarrierResponse(BaseModel):
    id: UUID
    physical_device_id: UUID
    type: str
    zone: str | None
    position: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── DisplaySurface ────────────────────────────────────────────────────────

class DisplaySurfaceCreate(BaseModel):
    logical_carrier_id: UUID
    capability_profile_id: UUID
    resolution: str | None = Field(None, max_length=20)


class DisplaySurfaceResponse(BaseModel):
    id: UUID
    logical_carrier_id: UUID
    capability_profile_id: UUID
    resolution: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════
# B.3.2 — Placement schemas
# ═══════════════════════════════════════════════════════════════════════════

from datetime import date

VALID_PLACEMENT_STATUSES = frozenset({
    "draft", "active", "paused", "completed", "cancelled", "error",
})


class PlacementCreate(BaseModel):
    channel_id: UUID
    name: str = Field(min_length=1, max_length=255)
    priority: int = Field(default=0, ge=0)
    start_date: date | None = None
    end_date: date | None = None


class PlacementUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = Field(None, max_length=20)
    priority: int | None = Field(None, ge=0)
    start_date: date | None = None
    end_date: date | None = None


class PlacementResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    channel_id: UUID
    placement_code: str
    name: str
    status: str
    priority: int
    start_date: date | None
    end_date: date | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class PlacementTargetItem(BaseModel):
    target_type: str = Field(min_length=1, max_length=20)
    store_id: UUID | None = None
    display_surface_id: UUID | None = None
    logical_carrier_id: UUID | None = None


class PlacementTargetsUpdate(BaseModel):
    targets: list[PlacementTargetItem] = Field(default_factory=list)


class PlacementTargetResponse(BaseModel):
    id: UUID
    placement_id: UUID
    target_type: str
    store_id: UUID | None
    display_surface_id: UUID | None
    logical_carrier_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
