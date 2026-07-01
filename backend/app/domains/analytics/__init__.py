"""Analytics domain — schemas, contracts, validation.

No migrations. No API. No ClickHouse. No DB writes.
Read-only contracts for F.2+ aggregation services.
"""

from .schemas import (
    AnalyticsTimeRange,
    AnalyticsScope,
    DeliveryMetricQuery,
    DeliveryMetricResult,
    DeliveryMetricsSummary,
    DeliveryBreakdown,
    DeviceHealthQuery,
    DeviceHealthResult,
    DeviceHealthItem,
    PopEventNormalized,
    PlannedVsDeliveredQuery,
    PlannedVsDeliveredResult,
    AnalyticsIssue,
)
from .service import (
    normalize_pop_events,
    calculate_delivery_metrics,
    calculate_device_health,
    calculate_planned_vs_delivered,
    exclude_dry_run_events,
    build_analytics_issue,
)

__all__ = [
    "AnalyticsTimeRange",
    "AnalyticsScope",
    "DeliveryMetricQuery",
    "DeliveryMetricResult",
    "DeliveryMetricsSummary",
    "DeliveryBreakdown",
    "DeviceHealthQuery",
    "DeviceHealthResult",
    "DeviceHealthItem",
    "PopEventNormalized",
    "PlannedVsDeliveredQuery",
    "PlannedVsDeliveredResult",
    "AnalyticsIssue",
    "normalize_pop_events",
    "calculate_delivery_metrics",
    "calculate_device_health",
    "calculate_planned_vs_delivered",
    "exclude_dry_run_events",
    "build_analytics_issue",
]
