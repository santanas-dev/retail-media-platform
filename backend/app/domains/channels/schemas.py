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
