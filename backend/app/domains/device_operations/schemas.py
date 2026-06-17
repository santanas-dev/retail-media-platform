"""Device Operations: Pydantic schemas for delivery health."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class HealthPeriod(BaseModel):
    date_from: datetime
    date_to: datetime


class OverviewSummary(BaseModel):
    total_devices: int = 0
    healthy: int = 0
    warning: int = 0
    critical: int = 0
    offline: int = 0
    disabled: int = 0


class PipelineCounts(BaseModel):
    heartbeat_devices: int = 0
    manifest_devices: int = 0
    media_devices: int = 0
    pop_devices: int = 0


class ErrorCounts(BaseModel):
    manifest_validation_failed: int = 0
    media_storage_error: int = 0
    pop_rejected: int = 0
    batch_rejected: int = 0


class OverviewResponse(BaseModel):
    status: str = "ok"
    period: HealthPeriod
    summary: OverviewSummary
    pipeline: PipelineCounts
    errors: ErrorCounts


class DeviceHealthItem(BaseModel):
    gateway_device_id: UUID
    device_code: str
    device_name: Optional[str] = None
    store_id: Optional[UUID] = None
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    channel_id: Optional[UUID] = None
    channel_code: Optional[str] = None
    channel_name: Optional[str] = None
    device_status: str
    health_status: str  # healthy/warning/critical/offline/disabled
    last_activity_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    last_manifest_request_at: Optional[datetime] = None
    last_media_request_at: Optional[datetime] = None
    last_pop_event_at: Optional[datetime] = None
    manifest_requests_count: int = 0
    media_requests_count: int = 0
    pop_events_count: int = 0
    error_count: int = 0
    problem_types: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SafeHeartbeatItem(BaseModel):
    id: UUID
    status: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SafeManifestRequestItem(BaseModel):
    id: UUID
    request_status: str
    message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SafeMediaRequestItem(BaseModel):
    id: UUID
    request_status: str
    message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SafePoPEventItem(BaseModel):
    id: UUID
    validation_status: str
    play_status: Optional[str] = None
    rejection_reason: Optional[str] = None
    played_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SafePoPBatchItem(BaseModel):
    id: UUID
    batch_status: str
    total_events: int = 0
    accepted_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class SafeDeviceEventItem(BaseModel):
    id: UUID
    event_type: str
    severity: str
    message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceHealthDetail(BaseModel):
    device: DeviceHealthItem
    recent_heartbeats: list[SafeHeartbeatItem] = Field(default_factory=list)
    recent_manifest_requests: list[SafeManifestRequestItem] = Field(default_factory=list)
    recent_media_requests: list[SafeMediaRequestItem] = Field(default_factory=list)
    recent_pop_events: list[SafePoPEventItem] = Field(default_factory=list)
    recent_pop_batches: list[SafePoPBatchItem] = Field(default_factory=list)
    recent_device_events: list[SafeDeviceEventItem] = Field(default_factory=list)


class StoreHealthItem(BaseModel):
    store_id: UUID
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    total_devices: int = 0
    healthy: int = 0
    warning: int = 0
    critical: int = 0
    offline: int = 0
    disabled: int = 0
    devices_with_manifest: int = 0
    devices_with_media: int = 0
    devices_with_pop: int = 0
    error_count: int = 0
    top_problem_types: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChannelHealthItem(BaseModel):
    channel_id: UUID
    channel_code: Optional[str] = None
    channel_name: Optional[str] = None
    total_devices: int = 0
    healthy: int = 0
    warning: int = 0
    critical: int = 0
    offline: int = 0
    disabled: int = 0
    devices_with_manifest: int = 0
    devices_with_media: int = 0
    devices_with_pop: int = 0
    error_count: int = 0
    top_problem_types: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}
