"""Analytics service — skeleton contracts and validation helpers.

F.1: contracts only — no heavy data reads, no DB writes, no API.
Actual aggregation logic will be implemented in F.2+.

No imports: ClickHouse, Device Gateway router, KSO Adapter,
publication flow, GeneratedManifest write path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.domains.analytics.schemas import (
    AnalyticsIssue,
    AnalyticsTimeRange,
    DeliveryMetricQuery,
    DeliveryMetricResult,
    DeliveryMetricsSummary,
    DeviceHealthQuery,
    DeviceHealthResult,
    PlannedVsDeliveredQuery,
    PlannedVsDeliveredResult,
    PopEventNormalized,
)


# ═══════════════════════════════════════════════════════════════════════════
# Forbidden secret keys in analytics payloads
# ═══════════════════════════════════════════════════════════════════════════

FORBIDDEN_ANALYTICS_KEYS = frozenset({
    "password", "passwd", "pwd",
    "secret", "client_secret",
    "token", "access_token", "refresh_token",
    "api_key", "access_key", "private_key",
    "authorization", "bearer",
    "signed_url", "signature",
    "credential", "credentials",
    "cookie", "session", "jwt",
})


# ═══════════════════════════════════════════════════════════════════════════
# Validation helpers
# ═══════════════════════════════════════════════════════════════════════════

def build_analytics_issue(
    code: str,
    severity: str = "warning",
    message: str = "",
    field: str | None = None,
    details: dict[str, Any] | None = None,
) -> AnalyticsIssue:
    """Build a structured AnalyticsIssue."""
    return AnalyticsIssue(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        message=message,
        field=field,
        details=details,
    )


def validate_time_range(date_from: datetime | None, date_to: datetime | None) -> list[AnalyticsIssue]:
    """Validate a time range."""
    issues: list[AnalyticsIssue] = []
    if date_from and date_to and date_from > date_to:
        issues.append(build_analytics_issue(
            "invalid_time_range",
            "error",
            f"date_from ({date_from.isoformat()}) must be <= date_to ({date_to.isoformat()})",
            field="time_range",
        ))
    return issues


def validate_granularity(granularity: str) -> list[AnalyticsIssue]:
    """Validate granularity value."""
    from app.domains.analytics.schemas import ANALYTICS_GRANULARITY
    if granularity not in ANALYTICS_GRANULARITY:
        return [build_analytics_issue(
            "invalid_granularity",
            "error",
            f"granularity must be one of {sorted(ANALYTICS_GRANULARITY)}, got '{granularity}'",
            field="granularity",
        )]
    return []


def validate_analytics_scope(scope: Any) -> list[AnalyticsIssue]:
    """Validate analytics scope — empty scope is allowed (global)."""
    # Empty scope = global — allowed for admin/system
    # Specific scopes will be validated in F.2+ with RLS
    return []


def validate_no_secrets_in_analytics_payload(payload: dict[str, Any], path: str = "") -> list[AnalyticsIssue]:
    """Recursively check analytics payload for forbidden secret keys/values."""
    issues: list[AnalyticsIssue] = []
    for key, value in payload.items():
        current = f"{path}.{key}" if path else key
        lower_key = key.lower()
        for fw in FORBIDDEN_ANALYTICS_KEYS:
            if fw in lower_key:
                issues.append(build_analytics_issue(
                    "secret_key_detected",
                    "error",
                    f"Forbidden key '{key}' at '{current}'",
                    field=current,
                    details={"forbidden_word": fw},
                ))
                break
        if isinstance(value, str):
            for fw in FORBIDDEN_ANALYTICS_KEYS:
                if fw in value.lower():
                    issues.append(build_analytics_issue(
                        "secret_value_detected",
                        "error",
                        f"Forbidden value for '{fw}' at '{current}'",
                        field=current,
                        details={"forbidden_word": fw},
                    ))
                    break
        elif isinstance(value, dict):
            issues.extend(validate_no_secrets_in_analytics_payload(value, current))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    issues.extend(validate_no_secrets_in_analytics_payload(item, f"{current}[{i}]"))
                elif isinstance(item, str):
                    for fw in FORBIDDEN_ANALYTICS_KEYS:
                        if fw in item.lower():
                            issues.append(build_analytics_issue(
                                "secret_value_detected",
                                "error",
                                f"Forbidden '{fw}' at '{current}[{i}]'",
                                field=f"{current}[{i}]",
                                details={"forbidden_word": fw},
                            ))
                            break
    return issues


# ═══════════════════════════════════════════════════════════════════════════
# Dry-run exclusion
# ═══════════════════════════════════════════════════════════════════════════

def exclude_dry_run_events(events: list[PopEventNormalized]) -> list[PopEventNormalized]:
    """Filter out dry-run events from a list of normalized PoP events."""
    return [e for e in events if not e.is_dry_run]


# ═══════════════════════════════════════════════════════════════════════════
# Service skeleton contracts (read-only in F.1)
# ═══════════════════════════════════════════════════════════════════════════

async def normalize_pop_events(query: DeliveryMetricQuery) -> list[PopEventNormalized]:
    """Normalize PoP events from KSO + Enterprise Gateway into unified model.

    F.1: returns empty list — actual normalization in F.2.
    Does NOT read from KsoProofOfPlayEvent or ProofOfPlayEvent in F.1.
    """
    return []


async def calculate_delivery_metrics(query: DeliveryMetricQuery) -> DeliveryMetricResult:
    """Calculate delivery metrics for the given query.

    F.1: returns structured empty result — aggregation logic in F.2+.
    """
    issues: list[AnalyticsIssue] = []

    # Validate query
    if query.time_range.date_from and query.time_range.date_to:
        issues.extend(validate_time_range(query.time_range.date_from, query.time_range.date_to))
    issues.extend(validate_granularity(query.time_range.granularity))

    if query.time_range.date_from and not query.time_range.date_to:
        query.time_range.date_to = datetime.now(timezone.utc)

    if not query.include_legacy_kso and not query.include_enterprise_gateway:
        issues.append(build_analytics_issue(
            "no_source_enabled",
            "warning",
            "Both include_legacy_kso and include_enterprise_gateway are False — no data sources enabled.",
        ))

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity != "error"]

    return DeliveryMetricResult(
        ok=len(errors) == 0,
        time_range=query.time_range,
        scope=query.scope,
        metrics=DeliveryMetricsSummary(),
        breakdowns=[],
        warnings=warnings,
        errors=errors,
    )


async def calculate_device_health(query: DeviceHealthQuery) -> DeviceHealthResult:
    """Calculate device health for the given query.

    F.1: returns structured empty result — aggregation logic in F.2+.
    """
    return DeviceHealthResult(
        ok=True,
        devices=[],
        warnings=[],
        errors=[],
    )


async def calculate_planned_vs_delivered(query: PlannedVsDeliveredQuery) -> PlannedVsDeliveredResult:
    """Calculate planned vs delivered comparison.

    F.1: returns structured empty result — aggregation logic in F.2+.
    """
    issues: list[AnalyticsIssue] = []

    if not query.include_planning:
        issues.append(build_analytics_issue(
            "planning_disabled",
            "warning",
            "Planning data excluded from planned_vs_delivered.",
            field="include_planning",
        ))

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity != "error"]

    return PlannedVsDeliveredResult(
        ok=len(errors) == 0,
        expected_impressions=None,
        delivered_impressions=0,
        delivery_gap=0,
        delivery_gap_percent=None,
        status="unknown",
        breakdowns=[],
        warnings=warnings,
        errors=errors,
    )
