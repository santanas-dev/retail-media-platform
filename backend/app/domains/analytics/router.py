"""F.4 — Analytics API Read-Only.

4 endpoints on top of analytics service (F.2/F.3):
  GET  /api/analytics/delivery/summary       — delivery metrics summary
  POST /api/analytics/delivery/query          — delivery metrics full query
  GET  /api/analytics/planned-vs-delivered    — planned vs delivered
  GET  /api/analytics/device-health           — device health

All require ``reports.read`` permission.
RLS: advertiser scope via campaign_id/placement_id/advertiser_id;
     store scope via store_id.
     Broad queries (no scope filter) for scoped users → constrained or 403.

Audit: analytics.delivery.(summary|query).viewed,
       analytics.planned_vs_delivered.viewed,
       analytics.device_health.viewed.

No API writes. No migrations. No ClickHouse. No portal changes.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.analytics.schemas import (
    AnalyticsScope,
    AnalyticsTimeRange,
    DeliveryMetricQuery,
    DeliveryMetricResult,
    PlannedVsDeliveredQuery,
    PlannedVsDeliveredResult,
    DeviceHealthQuery,
    DeviceHealthResult,
)
from app.domains.analytics.service import (
    calculate_delivery_metrics,
    calculate_planned_vs_delivered,
    calculate_device_health,
    build_analytics_issue,
    validate_no_secrets_in_analytics_payload,
    validate_granularity,
)
from app.domains.audit.service import audit_business_action
from app.domains.identity import models as identity_models
from app.domains.identity.rls import (
    resolve_user_scope_context,
    assert_object_in_advertiser_scope,
    assert_object_in_store_scope,
    UserScopeContext,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _parse_optional_uuid(value: str | None) -> UUID | None:
    """Parse optional UUID query param, raising 422 on invalid format."""
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format: {value}",
        )


def _parse_optional_datetime(value: str | None) -> datetime | None:
    """Parse optional ISO datetime query param, raising 400 on invalid format."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid datetime format: {value}. Use ISO 8601.",
        )


def _build_scope_from_params(
    advertiser_id: str | None = None,
    campaign_id: str | None = None,
    placement_id: str | None = None,
    store_id: str | None = None,
    device_id: str | None = None,
    gateway_device_id: str | None = None,
    physical_device_id: str | None = None,
    channel_id: str | None = None,
    channel_code: str | None = None,
) -> AnalyticsScope:
    """Build AnalyticsScope from query params."""
    return AnalyticsScope(
        advertiser_id=_parse_optional_uuid(advertiser_id),
        campaign_id=_parse_optional_uuid(campaign_id),
        placement_id=_parse_optional_uuid(placement_id),
        store_id=_parse_optional_uuid(store_id),
        device_id=_parse_optional_uuid(device_id),
        gateway_device_id=_parse_optional_uuid(gateway_device_id),
        physical_device_id=_parse_optional_uuid(physical_device_id),
        channel_id=_parse_optional_uuid(channel_id),
        channel_code=channel_code[:64] if channel_code else None,
    )


def _build_time_range_from_params(
    date_from: str | None = None,
    date_to: str | None = None,
    granularity: str = "total",
) -> AnalyticsTimeRange:
    """Build AnalyticsTimeRange from query params.

    Raises 400 on invalid granularity or date range.
    """
    df = _parse_optional_datetime(date_from)
    dt = _parse_optional_datetime(date_to)

    if df and dt and df > dt:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="date_from must be <= date_to",
        )

    gran_issues = validate_granularity(granularity)
    if gran_issues:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=gran_issues[0].message,
        )

    return AnalyticsTimeRange(
        date_from=df,
        date_to=dt,
        granularity=granularity,  # type: ignore[arg-type]
    )


async def _enforce_scope(
    db: AsyncSession,
    current_user: identity_models.User,
    campaign_id: UUID | None = None,
    placement_id: UUID | None = None,
    advertiser_id: UUID | None = None,
    store_id: UUID | None = None,
) -> UserScopeContext:
    """Resolve RLS scope and enforce advertiser/store boundaries.

    - If the user has advertiser scope and a specific object is requested
      (campaign_id/placement_id/advertiser_id) → verify it's in scope.
    - If store_id is requested → verify store scope.
    - If a scoped user makes a broad query without specifying their scope →
      reject with 403 (to prevent accidental cross-advertiser queries).

    Returns the resolved scope context for downstream use.
    """
    ctx = await resolve_user_scope_context(db, current_user)

    # Admin bypass
    if ctx.is_admin:
        return ctx

    # Enforce advertiser scope on specific objects
    if campaign_id:
        from app.domains.campaigns.models import Campaign
        from sqlalchemy import select as sa_select
        result = await db.execute(
            sa_select(Campaign.advertiser_id).where(Campaign.id == campaign_id)
        )
        adv_id = result.scalar_one_or_none()
        if adv_id is not None:
            assert_object_in_advertiser_scope(adv_id, ctx, "view analytics")

    if placement_id:
        from app.domains.channels.models import Placement
        from app.domains.campaigns.models import Campaign
        from sqlalchemy import select as sa_select
        result = await db.execute(
            sa_select(Placement.campaign_id).where(Placement.id == placement_id)
        )
        camp_id = result.scalar_one_or_none()
        if camp_id:
            camp_result = await db.execute(
                sa_select(Campaign.advertiser_id).where(Campaign.id == camp_id)
            )
            adv_id = camp_result.scalar_one_or_none()
            if adv_id is not None:
                assert_object_in_advertiser_scope(adv_id, ctx, "view analytics")

    if advertiser_id:
        assert_object_in_advertiser_scope(advertiser_id, ctx, "view analytics")

    if store_id:
        assert_object_in_store_scope(store_id, ctx, "view analytics")

    # Broad query by scoped user without scope filter → reject
    # Scoped users must specify at least one scope parameter that matches their RLS
    has_scope_filter = bool(
        campaign_id or placement_id or advertiser_id or store_id
    )
    if not has_scope_filter:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Broad analytics queries are not permitted for scoped users. "
                   "Specify at least one scope filter: advertiser_id, campaign_id, placement_id, or store_id.",
        )

    return ctx


async def _audit_analytics(
    db: AsyncSession,
    current_user: identity_models.User,
    action: str,
    campaign_id: UUID | None = None,
    placement_id: UUID | None = None,
    advertiser_id: UUID | None = None,
    store_id: UUID | None = None,
    result_summary: str = "",
) -> None:
    """Fire-and-forget audit for analytics views."""
    details: dict = {"result_summary": result_summary}
    if campaign_id:
        details["campaign_id"] = str(campaign_id)
    if placement_id:
        details["placement_id"] = str(placement_id)
    if advertiser_id:
        details["advertiser_id"] = str(advertiser_id)
    if store_id:
        details["store_id"] = str(store_id)

    await audit_business_action(
        db,
        actor_user_id=str(current_user.id),
        action=action,
        target_type="analytics",
        target_ref=str(campaign_id or placement_id or advertiser_id or store_id or "global"),
        details=details,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Delivery Summary (GET)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/delivery/summary", response_model=DeliveryMetricResult)
async def delivery_summary(
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
    date_from: Optional[str] = Query(None, description="ISO 8601 start date"),
    date_to: Optional[str] = Query(None, description="ISO 8601 end date"),
    granularity: str = Query("total", description="total | day | hour"),
    advertiser_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    placement_id: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    gateway_device_id: Optional[str] = Query(None),
    physical_device_id: Optional[str] = Query(None),
    channel_id: Optional[str] = Query(None),
    channel_code: Optional[str] = Query(None, max_length=64),
    include_legacy_kso: bool = Query(True),
    include_enterprise_gateway: bool = Query(True),
    exclude_dry_run: bool = Query(True),
) -> DeliveryMetricResult:
    """Delivery metrics summary — aggregated view.

    Requires ``reports.read`` permission.
    RLS: advertiser scope enforced on campaign_id/placement_id/advertiser_id.
    """
    scope = _build_scope_from_params(
        advertiser_id=advertiser_id,
        campaign_id=campaign_id,
        placement_id=placement_id,
        store_id=store_id,
        device_id=device_id,
        gateway_device_id=gateway_device_id,
        physical_device_id=physical_device_id,
        channel_id=channel_id,
        channel_code=channel_code,
    )
    time_range = _build_time_range_from_params(date_from, date_to, granularity)

    # RLS enforcement
    await _enforce_scope(
        db, current_user,
        campaign_id=_parse_optional_uuid(campaign_id),
        placement_id=_parse_optional_uuid(placement_id),
        advertiser_id=_parse_optional_uuid(advertiser_id),
        store_id=_parse_optional_uuid(store_id),
    )

    query = DeliveryMetricQuery(
        time_range=time_range,
        scope=scope,
        include_legacy_kso=include_legacy_kso,
        include_enterprise_gateway=include_enterprise_gateway,
        exclude_dry_run=exclude_dry_run,
    )

    result = await calculate_delivery_metrics(db, query)

    # No-secrets safety check
    no_secrets_issues = validate_no_secrets_in_analytics_payload(result.model_dump())
    if no_secrets_issues:
        result.errors.extend(no_secrets_issues)
        result.ok = False

    # Audit
    await _audit_analytics(
        db, current_user,
        action="analytics.delivery.summary.viewed",
        campaign_id=_parse_optional_uuid(campaign_id),
        placement_id=_parse_optional_uuid(placement_id),
        advertiser_id=_parse_optional_uuid(advertiser_id),
        store_id=_parse_optional_uuid(store_id),
        result_summary=f"delivered={result.metrics.delivered_impressions}, events={result.metrics.proof_events_count}",
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. Delivery Query (POST)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/delivery/query", response_model=DeliveryMetricResult)
async def delivery_query(
    body: DeliveryMetricQuery,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
) -> DeliveryMetricResult:
    """Delivery metrics full query — accepts DeliveryMetricQuery body.

    Requires ``reports.read`` permission.
    RLS: advertiser scope enforced on body.scope.
    """
    # RLS enforcement
    await _enforce_scope(
        db, current_user,
        campaign_id=body.scope.campaign_id,
        placement_id=body.scope.placement_id,
        advertiser_id=body.scope.advertiser_id,
        store_id=body.scope.store_id,
    )

    # Build query — time_range already on body
    result = await calculate_delivery_metrics(db, body)

    # No-secrets safety check
    no_secrets_issues = validate_no_secrets_in_analytics_payload(result.model_dump())
    if no_secrets_issues:
        result.errors.extend(no_secrets_issues)
        result.ok = False

    # Audit
    await _audit_analytics(
        db, current_user,
        action="analytics.delivery.query.viewed",
        campaign_id=body.scope.campaign_id,
        placement_id=body.scope.placement_id,
        advertiser_id=body.scope.advertiser_id,
        store_id=body.scope.store_id,
        result_summary=f"delivered={result.metrics.delivered_impressions}, events={result.metrics.proof_events_count}",
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 3. Planned vs Delivered (GET)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/planned-vs-delivered", response_model=PlannedVsDeliveredResult)
async def planned_vs_delivered(
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
    date_from: Optional[str] = Query(None, description="ISO 8601 start date"),
    date_to: Optional[str] = Query(None, description="ISO 8601 end date"),
    granularity: str = Query("total", description="total | day | hour"),
    advertiser_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    placement_id: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    exclude_dry_run: bool = Query(True),
) -> PlannedVsDeliveredResult:
    """Planned vs delivered comparison.

    Requires ``reports.read`` permission.
    RLS: advertiser scope enforced.

    Note: expected_impressions is None in F.4 (requires planning integration in F.5+).
    Status is "no_plan".
    """
    scope = _build_scope_from_params(
        advertiser_id=advertiser_id,
        campaign_id=campaign_id,
        placement_id=placement_id,
        store_id=store_id,
    )
    time_range = _build_time_range_from_params(date_from, date_to, granularity)

    # RLS enforcement
    await _enforce_scope(
        db, current_user,
        campaign_id=_parse_optional_uuid(campaign_id),
        placement_id=_parse_optional_uuid(placement_id),
        advertiser_id=_parse_optional_uuid(advertiser_id),
        store_id=_parse_optional_uuid(store_id),
    )

    query = PlannedVsDeliveredQuery(
        time_range=time_range,
        scope=scope,
        include_planning=True,
        exclude_dry_run=exclude_dry_run,
    )

    result = await calculate_planned_vs_delivered(db, query)

    # No-secrets
    no_secrets_issues = validate_no_secrets_in_analytics_payload(result.model_dump())
    if no_secrets_issues:
        result.errors.extend(no_secrets_issues)
        result.ok = False

    # Audit
    await _audit_analytics(
        db, current_user,
        action="analytics.planned_vs_delivered.viewed",
        campaign_id=_parse_optional_uuid(campaign_id),
        placement_id=_parse_optional_uuid(placement_id),
        advertiser_id=_parse_optional_uuid(advertiser_id),
        store_id=_parse_optional_uuid(store_id),
        result_summary=f"delivered={result.delivered_impressions}, expected={result.expected_impressions}, status={result.status}",
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 4. Device Health (GET)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/device-health", response_model=DeviceHealthResult)
async def device_health(
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
    date_from: Optional[str] = Query(None, description="ISO 8601 start date"),
    date_to: Optional[str] = Query(None, description="ISO 8601 end date"),
    store_id: Optional[str] = Query(None),
    channel_code: Optional[str] = Query(None, max_length=64),
    gateway_device_id: Optional[str] = Query(None),
    physical_device_id: Optional[str] = Query(None),
    silent_threshold_minutes: int = Query(60, ge=1, description="Minutes of silence to flag as silent"),
) -> DeviceHealthResult:
    """Device health report.

    Requires ``reports.read`` permission.
    RLS: store scope enforced.

    Note: silent device detection requires expected device set from inventory (F.5+).
    Currently returns active devices with ok/warning/silent status based on
    last event age and playback status.
    """
    # RLS enforcement
    await _enforce_scope(
        db, current_user,
        store_id=_parse_optional_uuid(store_id),
    )

    time_range = AnalyticsTimeRange(
        date_from=_parse_optional_datetime(date_from),
        date_to=_parse_optional_datetime(date_to),
        granularity="total",
    )

    scope = AnalyticsScope(
        store_id=_parse_optional_uuid(store_id),
        channel_code=channel_code[:64] if channel_code else None,
        gateway_device_id=_parse_optional_uuid(gateway_device_id),
        physical_device_id=_parse_optional_uuid(physical_device_id),
    )

    query = DeviceHealthQuery(
        time_range=time_range,
        scope=scope,
        silent_threshold_minutes=silent_threshold_minutes,
    )

    result = await calculate_device_health(db, query)

    # No-secrets
    no_secrets_issues = validate_no_secrets_in_analytics_payload(result.model_dump())
    if no_secrets_issues:
        result.errors.extend(no_secrets_issues)
        result.ok = False

    # Audit
    await _audit_analytics(
        db, current_user,
        action="analytics.device_health.viewed",
        store_id=_parse_optional_uuid(store_id),
        result_summary=f"devices={len(result.devices)}",
    )

    return result
