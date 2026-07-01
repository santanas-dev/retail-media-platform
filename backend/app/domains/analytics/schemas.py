"""Analytics schemas — Pydantic v2 models for delivery metrics and device health.

No migrations. No API. No ClickHouse. No DB writes.
Pure schemas and contracts for F.2+ aggregation services.

Source types:
  - legacy_kso        → KsoProofOfPlayEvent
  - enterprise_gateway → ProofOfPlayEvent

Dry-run exclusion:
  - PopEventNormalized.is_dry_run = True → filtered by exclude_dry_run_events()
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════
# Granularity
# ═══════════════════════════════════════════════════════════════════════════

ANALYTICS_GRANULARITY = frozenset({"total", "day", "hour"})
Granularity = Literal["total", "day", "hour"]


# ═══════════════════════════════════════════════════════════════════════════
# Time range
# ═══════════════════════════════════════════════════════════════════════════

class AnalyticsTimeRange(BaseModel):
    """Time range for analytics queries."""
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    timezone: Optional[str] = Field(default=None, max_length=64)
    granularity: Granularity = "total"

    @model_validator(mode="after")
    def _validate_range(self):
        if self.date_from and self.date_to:
            # Normalize to UTC for comparison
            df = self.date_from
            dt = self.date_to
            if df.tzinfo is None:
                df = df.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if df > dt:
                raise ValueError("date_from must be <= date_to")
        if self.granularity not in ANALYTICS_GRANULARITY:
            raise ValueError(f"granularity must be one of {sorted(ANALYTICS_GRANULARITY)}")
        return self


# ═══════════════════════════════════════════════════════════════════════════
# Scope
# ═══════════════════════════════════════════════════════════════════════════

class AnalyticsScope(BaseModel):
    """Filters for analytics queries.  All fields optional — empty = global scope."""
    advertiser_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None
    placement_id: Optional[UUID] = None
    store_id: Optional[UUID] = None
    device_id: Optional[UUID] = None
    gateway_device_id: Optional[UUID] = None
    physical_device_id: Optional[UUID] = None
    channel_id: Optional[UUID] = None
    channel_code: Optional[str] = Field(default=None, max_length=64)


# ═══════════════════════════════════════════════════════════════════════════
# Analytics issue
# ═══════════════════════════════════════════════════════════════════════════

class AnalyticsIssue(BaseModel):
    """Structured warning/error for analytics results."""
    code: str = Field(min_length=1, max_length=64)
    severity: Literal["info", "warning", "error"] = "warning"
    message: str = Field(min_length=1, max_length=512)
    field: Optional[str] = Field(default=None, max_length=128)
    details: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════════
# Delivery metric query / result
# ═══════════════════════════════════════════════════════════════════════════

class DeliveryMetricQuery(BaseModel):
    """Query for delivery metrics."""
    time_range: AnalyticsTimeRange = Field(default_factory=AnalyticsTimeRange)
    scope: AnalyticsScope = Field(default_factory=AnalyticsScope)
    include_legacy_kso: bool = True
    include_enterprise_gateway: bool = True
    exclude_dry_run: bool = True


class DeliveryMetricsSummary(BaseModel):
    """Aggregated delivery metrics."""
    delivered_impressions: int = 0
    expected_impressions: Optional[int] = None
    proof_events_count: int = 0
    playback_success_count: int = 0
    playback_failure_count: int = 0
    manifest_received_count: int = 0
    device_count: int = 0
    active_device_count: int = 0
    silent_device_count: int = 0
    delivery_gap_percent: Optional[float] = None
    campaign_delivery_status: Optional[str] = None
    placement_delivery_status: Optional[str] = None
    store_delivery_status: Optional[str] = None
    device_delivery_status: Optional[str] = None


class DeliveryBreakdown(BaseModel):
    """Breakdown of metrics by dimension."""
    breakdown_type: Literal["campaign", "placement", "store", "device", "channel", "day", "hour"]
    key: str = Field(min_length=1, max_length=128)
    label: Optional[str] = Field(default=None, max_length=256)
    metrics: DeliveryMetricsSummary = Field(default_factory=DeliveryMetricsSummary)


class DeliveryMetricResult(BaseModel):
    """Result of a delivery metrics query."""
    ok: bool = True
    time_range: AnalyticsTimeRange = Field(default_factory=AnalyticsTimeRange)
    scope: AnalyticsScope = Field(default_factory=AnalyticsScope)
    metrics: DeliveryMetricsSummary = Field(default_factory=DeliveryMetricsSummary)
    breakdowns: list[DeliveryBreakdown] = Field(default_factory=list)
    warnings: list[AnalyticsIssue] = Field(default_factory=list)
    errors: list[AnalyticsIssue] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Device health
# ═══════════════════════════════════════════════════════════════════════════

class DeviceHealthQuery(BaseModel):
    """Query for device health status."""
    time_range: AnalyticsTimeRange = Field(default_factory=AnalyticsTimeRange)
    scope: AnalyticsScope = Field(default_factory=AnalyticsScope)
    silent_threshold_minutes: Optional[int] = Field(default=60, ge=1)


class DeviceHealthItem(BaseModel):
    """Health status for a single device."""
    device_id: Optional[UUID] = None
    gateway_device_id: Optional[UUID] = None
    physical_device_id: Optional[UUID] = None
    device_code: Optional[str] = Field(default=None, max_length=64)
    store_id: Optional[UUID] = None
    channel_code: Optional[str] = Field(default=None, max_length=32)
    last_seen_at: Optional[datetime] = None
    last_pop_at: Optional[datetime] = None
    is_silent: bool = False
    status: Literal["ok", "warning", "error", "silent", "unknown"] = "unknown"
    issues: list[AnalyticsIssue] = Field(default_factory=list)


class DeviceHealthResult(BaseModel):
    """Result of a device health query."""
    ok: bool = True
    devices: list[DeviceHealthItem] = Field(default_factory=list)
    warnings: list[AnalyticsIssue] = Field(default_factory=list)
    errors: list[AnalyticsIssue] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Normalized PoP event
# ═══════════════════════════════════════════════════════════════════════════

class PopEventNormalized(BaseModel):
    """Normalized PoP event from either KSO or Enterprise Gateway."""
    source_type: Literal["legacy_kso", "enterprise_gateway"]
    source_event_id: Optional[str] = Field(default=None, max_length=128)
    event_time: Optional[datetime] = None
    event_type: Optional[str] = Field(default=None, max_length=32)
    device_code: Optional[str] = Field(default=None, max_length=64)
    gateway_device_id: Optional[UUID] = None
    physical_device_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None
    placement_id: Optional[UUID] = None
    manifest_id: Optional[str] = Field(default=None, max_length=128)
    generated_manifest_id: Optional[str] = Field(default=None, max_length=128)
    creative_id: Optional[UUID] = None
    store_id: Optional[UUID] = None
    channel_code: Optional[str] = Field(default=None, max_length=32)
    delivered_impressions: int = 1
    playback_status: Optional[str] = Field(default=None, max_length=32)
    is_dry_run: bool = False
    correlation_status: Literal["matched", "unmatched", "partial", "unknown"] = "unknown"
    warnings: list[AnalyticsIssue] = Field(default_factory=list)
    errors: list[AnalyticsIssue] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Planned vs delivered
# ═══════════════════════════════════════════════════════════════════════════

class PlannedVsDeliveredQuery(BaseModel):
    """Query for planned vs delivered comparison."""
    time_range: AnalyticsTimeRange = Field(default_factory=AnalyticsTimeRange)
    scope: AnalyticsScope = Field(default_factory=AnalyticsScope)
    include_planning: bool = True
    exclude_dry_run: bool = True


class PlannedVsDeliveredResult(BaseModel):
    """Result of planned vs delivered comparison."""
    ok: bool = True
    expected_impressions: Optional[int] = None
    delivered_impressions: int = 0
    delivery_gap: int = 0
    delivery_gap_percent: Optional[float] = None
    status: Literal["on_track", "under_delivery", "over_delivery", "no_plan", "unknown"] = "unknown"
    breakdowns: list[DeliveryBreakdown] = Field(default_factory=list)
    warnings: list[AnalyticsIssue] = Field(default_factory=list)
    errors: list[AnalyticsIssue] = Field(default_factory=list)
