"""Analytics service — normalization, contracts and validation helpers.

F.2: normalize_pop_events implemented — read-only normalization from
KsoProofOfPlayEvent and ProofOfPlayEvent into unified PopEventNormalized.

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

# ═══════════════════════════════════════════════════════════════════════════
# Normalization — legacy KSO PoP
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_legacy_kso_pop_event(
    event: Any,  # KsoProofOfPlayEvent
    campaign_lookup: dict[str, Any] | None = None,
) -> PopEventNormalized:
    """Normalize a KsoProofOfPlayEvent into PopEventNormalized.

    Real fields (from proof_of_play/models.py):
      id, event_code, device_code, placement_code, campaign_code,
      creative_code, manifest_code, media_ref, event_type, status,
      played_at, duration_ms, received_at, created_at
    """
    warnings: list[AnalyticsIssue] = []
    errors: list[AnalyticsIssue] = []

    # Timestamp: prefer played_at, fallback received_at, fallback created_at
    event_time = event.played_at or event.received_at or event.created_at

    # Correlation: campaign_code/placement_code/creative_code are direct fields
    correlation = "matched" if event.campaign_code and event.placement_code else "partial"
    if not event.campaign_code and not event.placement_code:
        correlation = "unmatched"
        warnings.append(build_analytics_issue(
            "correlation_unmatched",
            "warning",
            f"KSO PoP event {event.event_code}: no campaign/placement codes",
            field="correlation_status",
        ))
    elif not event.campaign_code or not event.placement_code:
        correlation = "partial"
        warnings.append(build_analytics_issue(
            "correlation_partial",
            "warning",
            f"KSO PoP event {event.event_code}: partial correlation",
            field="correlation_status",
        ))

    # playback_status from event.status
    playback_status = None
    if event.status:
        if event.status == "accepted":
            playback_status = "success"
        elif event.status == "rejected":
            playback_status = "failure"
        elif event.status == "duplicate":
            playback_status = "duplicate"
        else:
            playback_status = event.status

    # Legacy KSO events are production, not dry-run
    is_dry_run = False

    return PopEventNormalized(
        source_type="legacy_kso",
        source_event_id=event.event_code,
        event_time=event_time,
        event_type=event.event_type,
        device_code=event.device_code,
        campaign_id=None,  # code-based, no UUID FK
        placement_id=None,  # code-based
        generated_manifest_id=event.manifest_code,
        store_id=None,  # not in KsoProofOfPlayEvent
        channel_code="kso",
        delivered_impressions=1,
        playback_status=playback_status,
        is_dry_run=is_dry_run,
        correlation_status=correlation,  # type: ignore[arg-type]
        warnings=warnings,
        errors=errors,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Normalization — enterprise Gateway PoP
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_enterprise_gateway_pop_event(
    event: Any,  # ProofOfPlayEvent
) -> PopEventNormalized:
    """Normalize a ProofOfPlayEvent into PopEventNormalized.

    Real fields (from device_gateway/models.py):
      id, device_event_id, gateway_device_id, manifest_item_id,
      manifest_version_id, publication_target_id, schedule_item_id,
      campaign_id, campaign_rendition_id, rendition_id,
      creative_version_id, played_at, received_at, duration_ms,
      play_status, validation_status, media_sha256, expected_sha256,
      player_version, ip_address, user_agent, details_json,
      rejection_reason, batch_id, created_at
    """
    warnings: list[AnalyticsIssue] = []
    errors: list[AnalyticsIssue] = []

    # Timestamp
    event_time = event.played_at or event.received_at or event.created_at

    # Correlation status
    correlation = "unknown"
    if event.campaign_id and event.manifest_item_id and event.gateway_device_id:
        correlation = "matched"
    elif event.gateway_device_id:
        correlation = "partial"
        warnings.append(build_analytics_issue(
            "correlation_partial",
            "warning",
            f"Enterprise PoP event has device but no campaign/manifest",
            field="correlation_status",
        ))
    else:
        correlation = "unmatched"
        warnings.append(build_analytics_issue(
            "correlation_unmatched",
            "warning",
            "Enterprise PoP event has no gateway_device_id",
            field="correlation_status",
        ))

    # playback_status from play_status
    playback_status = None
    if event.play_status:
        # play_status is a free-form string like "completed", "failed", etc.
        playback_status = event.play_status

    # Dry-run: enterprise events are production unless tagged otherwise
    # (manifest metadata check would be in F.3+)
    is_dry_run = False
    # Check details_json for dry_run marker if available
    if event.details_json and isinstance(event.details_json, dict):
        if event.details_json.get("dry_run"):
            is_dry_run = True

    return PopEventNormalized(
        source_type="enterprise_gateway",
        source_event_id=str(event.device_event_id) if event.device_event_id else str(event.id),
        event_time=event_time,
        event_type=None,  # ProofOfPlayEvent has no event_type field
        gateway_device_id=event.gateway_device_id,
        physical_device_id=None,  # would need GatewayDevice join
        campaign_id=event.campaign_id,
        placement_id=None,  # would need manifest_version join
        manifest_id=str(event.manifest_version_id) if event.manifest_version_id else None,
        creative_id=event.creative_version_id,
        store_id=None,  # would need GatewayDevice.store_id join
        channel_code=None,  # would need GatewayDevice.channel join
        delivered_impressions=1,
        playback_status=playback_status,
        is_dry_run=is_dry_run,
        correlation_status=correlation,  # type: ignore[arg-type]
        warnings=warnings,
        errors=errors,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scope filtering
# ═══════════════════════════════════════════════════════════════════════════

def _apply_scope_filter(
    events: list[PopEventNormalized],
    scope: Any,  # AnalyticsScope
) -> tuple[list[PopEventNormalized], list[AnalyticsIssue]]:
    """Filter normalized events by AnalyticsScope.

    Applies filters post-normalization. Fields not available in the
    normalized event produce a scope_filter_partial warning.
    """
    warnings: list[AnalyticsIssue] = []
    filtered = events

    if scope.campaign_id:
        cid = scope.campaign_id
        filtered = [e for e in filtered if e.campaign_id == cid]
        if not filtered:
            warnings.append(build_analytics_issue(
                "scope_filter_empty",
                "warning",
                f"No events match campaign_id={cid}",
                field="scope.campaign_id",
            ))

    if scope.placement_id:
        pid = scope.placement_id
        filtered = [e for e in filtered if e.placement_id == pid]

    if scope.store_id:
        sid = scope.store_id
        if not any(e.store_id is not None for e in filtered):
            warnings.append(build_analytics_issue(
                "scope_filter_partial",
                "warning",
                "store_id scope applied but no events carry store_id",
                field="scope.store_id",
            ))
        filtered = [e for e in filtered if e.store_id == sid]

    if scope.gateway_device_id:
        gid = scope.gateway_device_id
        filtered = [e for e in filtered if e.gateway_device_id == gid]

    if scope.physical_device_id:
        pdid = scope.physical_device_id
        if not any(e.physical_device_id is not None for e in filtered):
            warnings.append(build_analytics_issue(
                "scope_filter_partial",
                "warning",
                "physical_device_id scope applied but no events carry it",
                field="scope.physical_device_id",
            ))
        filtered = [e for e in filtered if e.physical_device_id == pdid]

    if scope.channel_code:
        cc = scope.channel_code
        filtered = [e for e in filtered if e.channel_code == cc]

    if scope.channel_id:
        warnings.append(build_analytics_issue(
            "scope_filter_partial",
            "warning",
            "channel_id scope not supported in normalized events (use channel_code)",
            field="scope.channel_id",
        ))

    return filtered, warnings


# ═══════════════════════════════════════════════════════════════════════════
# Main normalization service (F.2 implementation)
# ═══════════════════════════════════════════════════════════════════════════

async def normalize_pop_events(
    db: Any,  # AsyncSession
    query: DeliveryMetricQuery,
) -> list[PopEventNormalized]:
    """Normalize PoP events from KSO + Enterprise Gateway into unified model.

    Reads from:
      - KsoProofOfPlayEvent (legacy_kso)
      - ProofOfPlayEvent (enterprise_gateway)

    Does NOT write to DB. Does NOT change ingestion endpoints.
    """
    from sqlalchemy import select as _select
    from app.domains.proof_of_play.models import KsoProofOfPlayEvent
    from app.domains.device_gateway.models import ProofOfPlayEvent as GWPopEvent

    events: list[PopEventNormalized] = []

    # ── Legacy KSO PoP ──────────────────────────────────────────
    if query.include_legacy_kso:
        stmt = _select(KsoProofOfPlayEvent).order_by(
            KsoProofOfPlayEvent.received_at.desc()
        )

        # Time filter
        if query.time_range.date_from:
            stmt = stmt.where(
                KsoProofOfPlayEvent.received_at >= query.time_range.date_from
            )
        if query.time_range.date_to:
            stmt = stmt.where(
                KsoProofOfPlayEvent.received_at <= query.time_range.date_to
            )

        result = await db.execute(stmt)
        kso_events = result.scalars().all()

        for e in kso_events:
            events.append(_normalize_legacy_kso_pop_event(e))

    # ── Enterprise Gateway PoP ──────────────────────────────────
    if query.include_enterprise_gateway:
        stmt = _select(GWPopEvent).order_by(GWPopEvent.received_at.desc().nullslast())

        # Time filter
        if query.time_range.date_from:
            stmt = stmt.where(GWPopEvent.received_at >= query.time_range.date_from)
        if query.time_range.date_to:
            stmt = stmt.where(GWPopEvent.received_at <= query.time_range.date_to)

        result = await db.execute(stmt)
        gw_events = result.scalars().all()

        for e in gw_events:
            events.append(_normalize_enterprise_gateway_pop_event(e))

    # ── Scope filtering ─────────────────────────────────────────
    filtered, scope_warnings = _apply_scope_filter(events, query.scope)

    # ── Dry-run exclusion ───────────────────────────────────────
    if query.exclude_dry_run:
        filtered = exclude_dry_run_events(filtered)

    return filtered


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
