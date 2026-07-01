"""F.1 — Analytics Schemas / Contracts: targeted tests.

Tests:
  - Schema validation (22 tests)
  - Service contracts (7 tests)
  - No-secrets (6 tests)
  - Boundaries (6 tests)
  - Compatibility (1 test)
"""

import asyncio
import inspect
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.domains.analytics.schemas import (
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
    ANALYTICS_GRANULARITY,
)
from app.domains.analytics.service import (
    normalize_pop_events,
    calculate_delivery_metrics,
    calculate_device_health,
    calculate_planned_vs_delivered,
    exclude_dry_run_events,
    build_analytics_issue,
    validate_time_range,
    validate_granularity,
    validate_analytics_scope,
    validate_no_secrets_in_analytics_payload,
    FORBIDDEN_ANALYTICS_KEYS,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _imports_from_module(module):
    src = inspect.getsource(module)
    return "\n".join(
        l.strip() for l in src.split("\n")
        if l.strip().startswith("from ") or l.strip().startswith("import ")
    ).lower()

def _now():
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Schema validation — time range (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestTimeRange(unittest.TestCase):

    def test_valid_range(self):
        tr = AnalyticsTimeRange(date_from=_now(), date_to=_now(), granularity="day")
        assert tr.granularity == "day"

    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):
            AnalyticsTimeRange(date_from=_now(), date_to=datetime(2020, 1, 1, tzinfo=timezone.utc))

    def test_total_granularity_valid(self):
        tr = AnalyticsTimeRange(granularity="total")
        assert tr.granularity == "total"

    def test_invalid_granularity_rejected(self):
        with self.assertRaises(ValueError):
            AnalyticsTimeRange(granularity="invalid_gran")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Schema validation — scope (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestScope(unittest.TestCase):

    def test_empty_scope_allowed(self):
        scope = AnalyticsScope()
        assert scope.advertiser_id is None

    def test_campaign_scope_valid(self):
        cid = uuid4()
        scope = AnalyticsScope(campaign_id=cid)
        assert scope.campaign_id == cid

    def test_multi_field_scope_valid(self):
        scope = AnalyticsScope(
            campaign_id=uuid4(),
            store_id=uuid4(),
            channel_code="kso",
        )
        assert scope.channel_code == "kso"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Schema validation — delivery metrics (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestDeliveryMetricSchemas(unittest.TestCase):

    def test_query_defaults_include_both_sources(self):
        q = DeliveryMetricQuery()
        assert q.include_legacy_kso is True
        assert q.include_enterprise_gateway is True

    def test_query_exclude_dry_run_default_true(self):
        q = DeliveryMetricQuery()
        assert q.exclude_dry_run is True

    def test_result_shape_valid(self):
        result = DeliveryMetricResult(
            ok=True,
            metrics=DeliveryMetricsSummary(delivered_impressions=100),
        )
        assert result.ok is True
        assert result.metrics.delivered_impressions == 100

    def test_summary_defaults_zero(self):
        s = DeliveryMetricsSummary()
        assert s.delivered_impressions == 0
        assert s.proof_events_count == 0
        assert s.device_count == 0

    def test_breakdown_valid(self):
        b = DeliveryBreakdown(
            breakdown_type="campaign",
            key="camp-1",
            label="Test Campaign",
            metrics=DeliveryMetricsSummary(delivered_impressions=50),
        )
        assert b.breakdown_type == "campaign"
        assert b.metrics.delivered_impressions == 50


# ═══════════════════════════════════════════════════════════════════════════
# 4. Schema validation — device health (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestDeviceHealthSchemas(unittest.TestCase):

    def test_query_valid(self):
        q = DeviceHealthQuery(silent_threshold_minutes=120)
        assert q.silent_threshold_minutes == 120

    def test_result_valid(self):
        r = DeviceHealthResult(
            ok=True,
            devices=[
                DeviceHealthItem(device_code="DEV-1", status="ok"),
                DeviceHealthItem(device_code="DEV-2", is_silent=True, status="silent"),
            ],
        )
        assert len(r.devices) == 2
        assert r.devices[1].is_silent is True

    def test_item_defaults(self):
        item = DeviceHealthItem()
        assert item.status == "unknown"
        assert item.is_silent is False


# ═══════════════════════════════════════════════════════════════════════════
# 5. Schema validation — normalized events (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestPopEventNormalized(unittest.TestCase):

    def test_legacy_kso_valid(self):
        e = PopEventNormalized(
            source_type="legacy_kso",
            device_code="KSO-001",
            campaign_id=uuid4(),
            correlation_status="matched",
        )
        assert e.source_type == "legacy_kso"
        assert e.correlation_status == "matched"

    def test_enterprise_gateway_valid(self):
        e = PopEventNormalized(
            source_type="enterprise_gateway",
            gateway_device_id=uuid4(),
            correlation_status="unknown",
        )
        assert e.source_type == "enterprise_gateway"

    def test_is_dry_run_default_false(self):
        e = PopEventNormalized(source_type="legacy_kso")
        assert e.is_dry_run is False

    def test_invalid_source_type_rejected(self):
        with self.assertRaises(ValueError):
            PopEventNormalized(source_type="invalid_source")  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Schema validation — planned vs delivered (2 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlannedVsDeliveredSchemas(unittest.TestCase):

    def test_query_valid(self):
        q = PlannedVsDeliveredQuery(include_planning=True, exclude_dry_run=True)
        assert q.include_planning is True

    def test_result_valid(self):
        r = PlannedVsDeliveredResult(
            ok=True,
            delivered_impressions=42,
            expected_impressions=100,
            delivery_gap=58,
            status="under_delivery",
        )
        assert r.status == "under_delivery"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Validation helpers — AnalyticsIssue (1 test)
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalyticsIssue(unittest.TestCase):

    def test_build_issue(self):
        issue = build_analytics_issue(
            "test_code", "error", "Test message", field="test_field",
            details={"reason": "validation_failed"},
        )
        assert issue.code == "test_code"
        assert issue.severity == "error"
        assert issue.message == "Test message"
        assert issue.field == "test_field"
        assert issue.details == {"reason": "validation_failed"}


# ═══════════════════════════════════════════════════════════════════════════
# 8. Service contracts (7 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestServiceContracts(unittest.TestCase):

    def test_normalize_pop_events_returns_list(self):
        """normalize_pop_events requires db + query (F.2 signature).
        with properly mocked DB that returns empty results."""
        # Mock execute → scalars → all chain
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute.return_value = mock_result

        q = DeliveryMetricQuery()
        result = asyncio.run(normalize_pop_events(db, q))
        assert isinstance(result, list)
        assert len(result) == 0

    def test_calculate_delivery_metrics_returns_result(self):
        q = DeliveryMetricQuery()
        result = asyncio.run(calculate_delivery_metrics(q))
        assert isinstance(result, DeliveryMetricResult)
        assert result.ok is True

    def test_calculate_delivery_metrics_no_source_warning(self):
        q = DeliveryMetricQuery(include_legacy_kso=False, include_enterprise_gateway=False)
        result = asyncio.run(calculate_delivery_metrics(q))
        assert any("no_source_enabled" in w.code for w in result.warnings)

    def test_calculate_device_health_returns_result(self):
        q = DeviceHealthQuery()
        result = asyncio.run(calculate_device_health(q))
        assert isinstance(result, DeviceHealthResult)
        assert result.ok is True

    def test_calculate_planned_vs_delivered_returns_result(self):
        q = PlannedVsDeliveredQuery()
        result = asyncio.run(calculate_planned_vs_delivered(q))
        assert isinstance(result, PlannedVsDeliveredResult)

    def test_exclude_dry_run_removes_dry_run(self):
        events = [
            PopEventNormalized(source_type="legacy_kso", is_dry_run=True),
            PopEventNormalized(source_type="enterprise_gateway", is_dry_run=False),
            PopEventNormalized(source_type="legacy_kso", is_dry_run=True),
        ]
        filtered = exclude_dry_run_events(events)
        assert len(filtered) == 1
        assert filtered[0].source_type == "enterprise_gateway"

    def test_exclude_dry_run_keeps_production(self):
        events = [
            PopEventNormalized(source_type="enterprise_gateway", is_dry_run=False),
            PopEventNormalized(source_type="legacy_kso", is_dry_run=False),
        ]
        filtered = exclude_dry_run_events(events)
        assert len(filtered) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 9. No-secrets validation (6 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestNoSecrets(unittest.TestCase):

    def test_rejects_token(self):
        issues = validate_no_secrets_in_analytics_payload({"token": "abc123"})
        assert any("secret_key_detected" in i.code for i in issues)

    def test_rejects_password(self):
        issues = validate_no_secrets_in_analytics_payload({"password": "hunter2"})
        assert any("secret_key_detected" in i.code for i in issues)

    def test_rejects_api_key(self):
        issues = validate_no_secrets_in_analytics_payload({"api_key": "key-123"})
        assert any("secret_key_detected" in i.code for i in issues)

    def test_rejects_bearer_value(self):
        issues = validate_no_secrets_in_analytics_payload({"auth": "Bearer xyz"})
        assert any("secret_value_detected" in i.code for i in issues)

    def test_allows_safe_fields(self):
        issues = validate_no_secrets_in_analytics_payload({
            "device_code": "DEV-1",
            "campaign_id": str(uuid4()),
            "delivered_impressions": 100,
        })
        assert len(issues) == 0

    def test_rejects_nested_secret(self):
        issues = validate_no_secrets_in_analytics_payload({
            "items": [{"meta": {"api_key": "hidden"}}],
        })
        assert any("secret_key_detected" in i.code for i in issues)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Boundaries (6 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundaries(unittest.TestCase):

    def test_service_has_no_db_add(self):
        import app.domains.analytics.service as svc
        src = inspect.getsource(svc)
        assert "db.add(" not in src
        assert ".insert(" not in src
        assert ".update(" not in src
        assert ".delete(" not in src

    def test_service_no_clickhouse_import(self):
        imports = _imports_from_module(
            __import__("app.domains.analytics.service", fromlist=["normalize_pop_events"])
        )
        assert "clickhouse" not in imports

    def test_service_no_device_gateway_router_import(self):
        imports = _imports_from_module(
            __import__("app.domains.analytics.service", fromlist=["normalize_pop_events"])
        )
        assert "device_gateway.router" not in imports.replace(" ", "")

    def test_service_no_kso_adapter_import(self):
        imports = _imports_from_module(
            __import__("app.domains.analytics.service", fromlist=["normalize_pop_events"])
        )
        assert "kso_adapter" not in imports

    def test_service_no_publication_import(self):
        imports = _imports_from_module(
            __import__("app.domains.analytics.service", fromlist=["normalize_pop_events"])
        )
        assert "publication" not in imports

    def test_no_api_router_created(self):
        """Analytics domain has no router.py file."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "app", "domains", "analytics", "router.py"
        )
        assert not os.path.exists(path), f"API router found at {path}"


# ═══════════════════════════════════════════════════════════════════════════
# 11. Compatibility (1 test)
# ═══════════════════════════════════════════════════════════════════════════

class TestCompatibility(unittest.TestCase):

    def test_forbidden_keys_constant_is_complete(self):
        required = {
            "password", "passwd", "pwd", "secret", "client_secret",
            "token", "access_token", "refresh_token",
            "api_key", "access_key", "private_key",
            "authorization", "bearer", "signed_url", "signature",
            "credential", "credentials", "cookie", "session", "jwt",
        }
        missing = required - FORBIDDEN_ANALYTICS_KEYS
        assert not missing, f"Missing forbidden keys: {missing}"
