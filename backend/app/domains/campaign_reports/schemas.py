"""Campaign Delivery Reporting Core: request/response schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Shared ────────────────────────────────────────────────────────

class DeliveryMetrics(BaseModel):
    """Common delivery metrics returned in all report responses."""
    planned_stores: int = 0
    planned_devices: int = 0
    published_targets: int = 0
    published_devices: int = 0
    publication_rate: Optional[float] = None

    manifest_available_devices: int = 0
    manifest_applied_devices: int = 0
    manifest_failed_devices: int = 0
    manifest_apply_rate: Optional[float] = None

    cache_ready_devices: int = 0
    cache_missing_devices: int = 0
    cache_failed_devices: int = 0
    cache_invalid_hash_devices: int = 0

    actual_play_count: int = 0
    unique_devices_with_pop: int = 0
    unique_stores_with_pop: int = 0
    last_pop_at: Optional[datetime] = None

    devices_ok: int = 0
    devices_warning: int = 0
    devices_critical: int = 0
    delivery_risk_status: str = "ok"


class CampaignReportBase(DeliveryMetrics):
    """Base fields for all campaign report responses."""
    campaign_id: UUID
    campaign_name: str
    campaign_status: str
    period_from: datetime
    period_to: datetime
    delivery_status: str


# ── Summary ───────────────────────────────────────────────────────

class SummaryResponse(CampaignReportBase):
    """GET /summary"""
    stores_total: int = 0
    stores_with_delivery: int = 0
    stores_with_errors: int = 0
    channels_total: int = 0


# ── By Store ──────────────────────────────────────────────────────

class StoreReportItem(DeliveryMetrics):
    store_id: UUID
    store_code: str
    store_name: str
    delivery_status: str


# ── By Channel ────────────────────────────────────────────────────

class ChannelReportItem(DeliveryMetrics):
    channel_id: UUID
    channel_code: str
    channel_name: str
    delivery_status: str


# ── By Device ─────────────────────────────────────────────────────

class DeviceReportItem(DeliveryMetrics):
    gateway_device_id: UUID
    device_code: str
    device_name: Optional[str] = None
    store_id: UUID
    store_code: str
    channel_id: UUID
    channel_code: str
    device_status: str
    health_status: str
    delivery_status: str
    current_manifest_status: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None
    last_pop_at: Optional[datetime] = None


# ── By Creative ───────────────────────────────────────────────────

class CreativeReportItem(BaseModel):
    campaign_rendition_id: UUID
    rendition_id: UUID
    rendition_name: Optional[str] = None
    creative_name: Optional[str] = None
    format: Optional[str] = None
    published_targets: int = 0
    cache_ready_devices: int = 0
    actual_play_count: int = 0
    unique_devices_with_pop: int = 0
    last_pop_at: Optional[datetime] = None


# ── Snapshot ──────────────────────────────────────────────────────

class SnapshotCreateRequest(BaseModel):
    """POST /snapshots — optionally override period."""
    period_from: Optional[datetime] = None
    period_to: Optional[datetime] = None


class SnapshotResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    generated_at: datetime
    period_from: datetime
    period_to: datetime
    snapshot_status: str
    delivery_status: str
    delivery_risk_status: str
    planned_stores: int
    planned_devices: int
    published_targets: int
    published_devices: int
    manifest_applied_devices: int
    manifest_failed_devices: int
    cache_ready_devices: int
    cache_invalid_hash_devices: int
    actual_play_count: int
    unique_devices_with_pop: int
    unique_stores_with_pop: int
    devices_ok: int
    devices_warning: int
    devices_critical: int
    stores_total: int
    stores_with_delivery: int
    stores_with_errors: int
    generated_by_user_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class SnapshotDetailResponse(SnapshotResponse):
    details_json: dict = Field(default_factory=dict)


# ── Query params model ────────────────────────────────────────────

class ReportQueryParams:
    """Shared query parameter handling (not a Pydantic model — used in router)."""
    def __init__(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        store_id: Optional[UUID] = None,
        channel_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        self.date_from = date_from
        self.date_to = date_to
        self.store_id = store_id
        self.channel_id = channel_id
        self.limit = limit
        self.offset = offset
