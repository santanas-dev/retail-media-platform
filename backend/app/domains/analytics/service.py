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
    DeliveryBreakdown,
    DeliveryMetricQuery,
    DeliveryMetricResult,
    DeliveryMetricsSummary,
    DeviceHealthItem,
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


# ═══════════════════════════════════════════════════════════════════════════
# Aggregation helpers
# ═══════════════════════════════════════════════════════════════════════════

PLAYBACK_SUCCESS_STATUSES = frozenset({
    "success", "played", "completed", "ok", "accepted",
})
PLAYBACK_FAILURE_STATUSES = frozenset({
    "failure", "failed", "error", "rejected", "timeout",
})
MANIFEST_RECEIVED_EVENT_TYPES = frozenset({
    "manifest_received", "manifest_downloaded", "received",
})


def _count_unique_devices(events: list[PopEventNormalized]) -> int:
    """Count unique devices across all identifier fields."""
    ids: set[str] = set()
    for e in events:
        if e.gateway_device_id:
            ids.add(str(e.gateway_device_id))
        if e.physical_device_id:
            ids.add(str(e.physical_device_id))
        if e.device_code:
            ids.add(e.device_code)
    return len(ids)


def _aggregate_metrics(events: list[PopEventNormalized]) -> DeliveryMetricsSummary:
    """Aggregate DeliveryMetricsSummary from normalized events."""
    delivered = sum(e.delivered_impressions for e in events)
    total = len(events)
    success = sum(1 for e in events
                  if e.playback_status and e.playback_status.lower() in PLAYBACK_SUCCESS_STATUSES)
    failure = sum(1 for e in events
                  if e.playback_status and e.playback_status.lower() in PLAYBACK_FAILURE_STATUSES)
    manifest = sum(1 for e in events
                   if e.event_type and e.event_type.lower() in MANIFEST_RECEIVED_EVENT_TYPES)
    device_count = _count_unique_devices(events)
    active = _count_unique_devices(events)

    return DeliveryMetricsSummary(
        delivered_impressions=delivered,
        proof_events_count=total,
        playback_success_count=success,
        playback_failure_count=failure,
        manifest_received_count=manifest,
        device_count=device_count,
        active_device_count=active,
        silent_device_count=0,  # requires expected device set — F.4+
        expected_impressions=None,  # requires planning integration — F.4+
        delivery_gap_percent=None,
        campaign_delivery_status="unknown",
        placement_delivery_status="unknown",
        store_delivery_status="unknown",
        device_delivery_status="unknown",
    )


def _build_breakdowns(
    events: list[PopEventNormalized],
    granularity: str,
) -> list[DeliveryBreakdown]:
    """Build breakdowns from normalized events."""
    from collections import defaultdict
    from app.domains.analytics.schemas import DeliveryBreakdown

    result: list[DeliveryBreakdown] = []

    # Campaign breakdown
    by_campaign: dict[str, list[PopEventNormalized]] = defaultdict(list)
    for e in events:
        key = str(e.campaign_id) if e.campaign_id else "unknown"
        by_campaign[key].append(e)
    for key, evts in sorted(by_campaign.items()):
        result.append(DeliveryBreakdown(
            breakdown_type="campaign",
            key=key,
            label=key if key != "unknown" else "Unknown Campaign",
            metrics=_aggregate_metrics(evts),
        ))

    # Channel breakdown
    by_channel: dict[str, list[PopEventNormalized]] = defaultdict(list)
    for e in events:
        key = e.channel_code or "unknown"
        by_channel[key].append(e)
    for key, evts in sorted(by_channel.items()):
        result.append(DeliveryBreakdown(
            breakdown_type="channel",
            key=key,
            label=key if key != "unknown" else "Unknown Channel",
            metrics=_aggregate_metrics(evts),
        ))

    # Device breakdown (by device_code or gateway_device_id)
    by_device: dict[str, list[PopEventNormalized]] = defaultdict(list)
    for e in events:
        if e.device_code:
            key = e.device_code
        elif e.gateway_device_id:
            key = str(e.gateway_device_id)
        else:
            key = "unknown"
        by_device[key].append(e)
    for key, evts in sorted(by_device.items()):
        result.append(DeliveryBreakdown(
            breakdown_type="device",
            key=key,
            label=key if key != "unknown" else "Unknown Device",
            metrics=_aggregate_metrics(evts),
        ))

    # Day breakdown (only if granularity supports it)
    if granularity in ("day", "hour") and events:
        by_day: dict[str, list[PopEventNormalized]] = defaultdict(list)
        for e in events:
            if e.event_time:
                day_key = e.event_time.strftime("%Y-%m-%d")
            else:
                day_key = "unknown"
            by_day[day_key].append(e)
        for key, evts in sorted(by_day.items()):
            result.append(DeliveryBreakdown(
                breakdown_type="day",
                key=key,
                label=key if key != "unknown" else "Unknown Day",
                metrics=_aggregate_metrics(evts),
            ))

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Delivery metrics (F.3 implementation)
# ═══════════════════════════════════════════════════════════════════════════

async def calculate_delivery_metrics(
    db: Any,  # AsyncSession
    query: DeliveryMetricQuery,
) -> DeliveryMetricResult:
    """Calculate delivery metrics from normalized PoP events."""
    issues: list[AnalyticsIssue] = []

    # Validate
    if query.time_range.date_from and query.time_range.date_to:
        if query.time_range.date_from > query.time_range.date_to:
            issues.append(build_analytics_issue(
                "invalid_time_range", "error",
                "date_from must be <= date_to", field="time_range",
            ))
    issues.extend(validate_granularity(query.time_range.granularity))

    if not query.include_legacy_kso and not query.include_enterprise_gateway:
        issues.append(build_analytics_issue(
            "no_source_enabled", "warning",
            "No data sources enabled.", field="query",
        ))

    if query.time_range.date_from and not query.time_range.date_to:
        query.time_range.date_to = datetime.now(timezone.utc)

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity != "error"]

    if errors:
        return DeliveryMetricResult(
            ok=False,
            time_range=query.time_range,
            scope=query.scope,
            warnings=warnings,
            errors=errors,
        )

    # Normalize
    events = await normalize_pop_events(db, query)

    # Exclude dry-run again in case normalization didn't
    if query.exclude_dry_run:
        events = exclude_dry_run_events(events)

    # Aggregation
    metrics = _aggregate_metrics(events)

    # Expected impressions unavailable warning
    warnings.append(build_analytics_issue(
        "expected_impressions_unavailable",
        "warning",
        "expected_impressions requires planning data integration (F.4+)",
        field="metrics.expected_impressions",
    ))

    # Silent device count unavailable warning
    warnings.append(build_analytics_issue(
        "silent_device_requires_inventory_or_device_scope",
        "warning",
        "silent_device_count requires expected device set from inventory or scope",
        field="metrics.silent_device_count",
    ))

    # Manifest received limited warning if no manifest events detected
    if metrics.manifest_received_count == 0 and events:
        warnings.append(build_analytics_issue(
            "metric_limited",
            "warning",
            "manifest_received_count is 0 — event_type may not carry manifest delivery info",
            field="metrics.manifest_received_count",
        ))

    # Breakdowns
    breakdowns = _build_breakdowns(events, query.time_range.granularity)

    return DeliveryMetricResult(
        ok=True,
        time_range=query.time_range,
        scope=query.scope,
        metrics=metrics,
        breakdowns=breakdowns,
        warnings=warnings,
        errors=errors,
    )


async def calculate_device_health(
    db: Any,
    query: DeviceHealthQuery,
) -> DeviceHealthResult:
    """Calculate device health — basic implementation over normalized events."""
    # Get events via a delivery query
    dq = DeliveryMetricQuery(
        time_range=AnalyticsTimeRange(
            date_from=query.time_range.date_from,
            date_to=query.time_range.date_to,
        ),
        scope=query.scope,
        include_legacy_kso=True,
        include_enterprise_gateway=True,
        exclude_dry_run=True,
    )
    events = await normalize_pop_events(db, dq)

    # Build device items
    devices_by_id: dict[str, PopEventNormalized] = {}
    for e in events:
        key = e.device_code or str(e.gateway_device_id) if e.gateway_device_id else None
        if key:
            devices_by_id.setdefault(key, e)

    items: list[DeviceHealthItem] = []
    for key, latest in devices_by_id.items():
        is_silent = False
        if query.silent_threshold_minutes and latest.event_time:
            age = (datetime.now(timezone.utc) - latest.event_time).total_seconds() / 60
            is_silent = age > query.silent_threshold_minutes

        status: str = "unknown"
        if is_silent:
            status = "silent"
        elif latest.playback_status and latest.playback_status.lower() in PLAYBACK_SUCCESS_STATUSES:
            status = "ok"
        elif latest.playback_status and latest.playback_status.lower() in PLAYBACK_FAILURE_STATUSES:
            status = "warning"
        else:
            status = "unknown"

        items.append(DeviceHealthItem(
            device_code=latest.device_code,
            gateway_device_id=latest.gateway_device_id,
            physical_device_id=latest.physical_device_id,
            store_id=latest.store_id,
            channel_code=latest.channel_code,
            last_seen_at=latest.event_time,
            last_pop_at=latest.event_time,
            is_silent=is_silent,
            status=status,  # type: ignore[arg-type]
        ))

    return DeviceHealthResult(ok=True, devices=items)


async def calculate_planned_vs_delivered(
    db: Any,
    query: PlannedVsDeliveredQuery,
) -> PlannedVsDeliveredResult:
    """Calculate planned vs delivered — F.3 basic implementation."""
    dq = DeliveryMetricQuery(
        time_range=query.time_range,
        scope=query.scope,
        include_legacy_kso=True,
        include_enterprise_gateway=True,
        exclude_dry_run=query.exclude_dry_run,
    )
    result = await calculate_delivery_metrics(db, dq)

    warnings = list(result.warnings)
    errors = list(result.errors)
    delivered = result.metrics.delivered_impressions
    expected = None
    gap = 0
    gap_pct = None
    status = "unknown"

    if query.include_planning:
        warnings.append(build_analytics_issue(
            "expected_impressions_unavailable",
            "warning",
            "Planning integration not available in F.3 — expected_impressions is None",
            field="expected_impressions",
        ))
        status = "no_plan"
    else:
        status = "no_plan"

    return PlannedVsDeliveredResult(
        ok=result.ok,
        expected_impressions=expected,
        delivered_impressions=delivered,
        delivery_gap=gap,
        delivery_gap_percent=gap_pct,
        status=status,  # type: ignore[arg-type]
        breakdowns=result.breakdowns,
        warnings=warnings,
        errors=errors,
    )
