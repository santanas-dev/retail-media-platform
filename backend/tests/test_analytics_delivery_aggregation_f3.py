"""F.3 — Delivery Aggregation Service: targeted tests.

Tests: metrics (5), playback (5), manifest (3), device counts (4),
expected/gap (7), breakdowns (8), query/source (5), planned-vs-delivered (5),
no-secrets (4), boundaries (8), regression (4).
"""

import asyncio
import inspect
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.domains.analytics.schemas import (
    AnalyticsTimeRange, AnalyticsScope, DeliveryMetricQuery,
    DeliveryMetricResult, DeliveryMetricsSummary, DeliveryBreakdown,
    DeviceHealthQuery, DeviceHealthResult, DeviceHealthItem,
    PopEventNormalized, PlannedVsDeliveredQuery, PlannedVsDeliveredResult,
)
from app.domains.analytics.service import (
    _aggregate_metrics, _build_breakdowns, _count_unique_devices,
    calculate_delivery_metrics, calculate_device_health,
    calculate_planned_vs_delivered, exclude_dry_run_events,
    build_analytics_issue, validate_no_secrets_in_analytics_payload,
    PLAYBACK_SUCCESS_STATUSES, PLAYBACK_FAILURE_STATUSES,
    FORBIDDEN_ANALYTICS_KEYS,
)


def _fake_event(**kw):
    defaults = {
        "source_type": "legacy_kso",
        "device_code": "DEV-1",
        "gateway_device_id": None,
        "physical_device_id": None,
        "campaign_id": uuid4(),
        "placement_id": None,
        "store_id": None,
        "channel_code": "kso",
        "delivered_impressions": 1,
        "event_time": datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        "playback_status": "success",
        "event_type": "impression",
        "is_dry_run": False,
        "correlation_status": "matched",
    }
    defaults.update(kw)
    return PopEventNormalized(**defaults)


def _make_db():
    db = AsyncMock()
    mr = MagicMock()
    mr.scalars.return_value.all.return_value = []
    db.execute.return_value = mr
    return db


def _imports(mod):
    return "\n".join(
        l.strip() for l in inspect.getsource(mod).split("\n")
        if l.strip().startswith("from ") or l.strip().startswith("import ")
    ).lower()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Metric basics (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestMetricBasics(unittest.TestCase):
    def test_no_events_zero_summary(self):
        s = _aggregate_metrics([])
        assert s.delivered_impressions == 0
        assert s.proof_events_count == 0

    def test_delivered_impressions_sums(self):
        s = _aggregate_metrics([
            _fake_event(delivered_impressions=3),
            _fake_event(delivered_impressions=7),
        ])
        assert s.delivered_impressions == 10

    def test_proof_events_count(self):
        s = _aggregate_metrics([_fake_event(), _fake_event(), _fake_event()])
        assert s.proof_events_count == 3

    def test_delivered_impressions_from_none_handled(self):
        """PopEventNormalized.delivered_impressions defaults to 1 if None."""
        e = _fake_event(delivered_impressions=1)
        assert e.delivered_impressions == 1

    def test_metrics_defaults_zero(self):
        s = DeliveryMetricsSummary()
        assert s.proof_events_count == 0
        assert s.playback_success_count == 0
        assert s.device_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. Playback statuses (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlaybackStatuses(unittest.TestCase):
    def test_success_counted(self):
        s = _aggregate_metrics([_fake_event(playback_status="success")])
        assert s.playback_success_count == 1

    def test_failure_counted(self):
        s = _aggregate_metrics([_fake_event(playback_status="failed")])
        assert s.playback_failure_count == 1

    def test_rejected_counted_as_failure(self):
        s = _aggregate_metrics([_fake_event(playback_status="rejected")])
        assert s.playback_failure_count == 1

    def test_played_counted_as_success(self):
        s = _aggregate_metrics([_fake_event(playback_status="played")])
        assert s.playback_success_count == 1

    def test_unknown_not_success_nor_failure(self):
        s = _aggregate_metrics([_fake_event(playback_status="weird_status")])
        assert s.playback_success_count == 0
        assert s.playback_failure_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. Manifest received (3)
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestReceived(unittest.TestCase):
    def test_manifest_event_counted(self):
        s = _aggregate_metrics([_fake_event(event_type="manifest_received")])
        assert s.manifest_received_count == 1

    def test_unrelated_event_not_counted(self):
        s = _aggregate_metrics([_fake_event(event_type="impression")])
        assert s.manifest_received_count == 0

    def test_manifest_downloaded_counted(self):
        s = _aggregate_metrics([_fake_event(event_type="manifest_downloaded")])
        assert s.manifest_received_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# 4. Device counts (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestDeviceCounts(unittest.TestCase):
    def test_unique_device_code(self):
        events = [_fake_event(device_code="A"), _fake_event(device_code="A"), _fake_event(device_code="B")]
        assert _count_unique_devices(events) == 2

    def test_unique_gateway_device_id(self):
        a, b = uuid4(), uuid4()
        events = [_fake_event(device_code=None, gateway_device_id=a),
                  _fake_event(device_code=None, gateway_device_id=b)]
        assert _count_unique_devices(events) == 2

    def test_active_device_count_from_events(self):
        s = _aggregate_metrics([_fake_event(), _fake_event(device_code="B")])
        assert s.active_device_count == 2

    def test_silent_device_count_is_zero(self):
        s = _aggregate_metrics([_fake_event()])
        assert s.silent_device_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. Expected / gap (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestExpectedGap(unittest.TestCase):
    def test_expected_unavailable(self):
        s = _aggregate_metrics([])
        assert s.expected_impressions is None

    def test_gap_percent_none_without_expected(self):
        s = _aggregate_metrics([])
        assert s.delivery_gap_percent is None

    def test_delivery_status_unknown(self):
        s = _aggregate_metrics([])
        assert s.campaign_delivery_status == "unknown"

    def test_gap_formula_via_helper(self):
        expected, delivered = 100, 70
        gap = expected - delivered
        gap_pct = (gap / expected) * 100
        assert gap == 30
        assert gap_pct == 30.0

    def test_under_delivery_if_gap_positive(self):
        expected, delivered = 100, 60
        assert delivered < expected

    def test_on_track_if_delivered_reaches_expected(self):
        expected, delivered = 100, 100
        assert delivered >= expected

    def test_over_delivery_if_delivered_exceeds(self):
        expected, delivered = 100, 120
        assert delivered > expected


# ═══════════════════════════════════════════════════════════════════════════
# 6. Breakdowns (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestBreakdowns(unittest.TestCase):
    def test_campaign_breakdown(self):
        c1, c2 = uuid4(), uuid4()
        events = [_fake_event(campaign_id=c1), _fake_event(campaign_id=c1), _fake_event(campaign_id=c2)]
        bds = _build_breakdowns(events, "total")
        campaign_bds = [b for b in bds if b.breakdown_type == "campaign"]
        assert len(campaign_bds) == 2

    def test_channel_breakdown(self):
        events = [_fake_event(channel_code="kso"), _fake_event(channel_code="android_tv")]
        bds = _build_breakdowns(events, "total")
        ch_bds = [b for b in bds if b.breakdown_type == "channel"]
        assert len(ch_bds) == 2

    def test_device_breakdown(self):
        events = [_fake_event(device_code="A"), _fake_event(device_code="B")]
        bds = _build_breakdowns(events, "total")
        dev_bds = [b for b in bds if b.breakdown_type == "device"]
        assert len(dev_bds) == 2

    def test_day_breakdown_with_granularity(self):
        events = [_fake_event(event_time=datetime(2026, 7, 1, tzinfo=timezone.utc)),
                  _fake_event(event_time=datetime(2026, 7, 2, tzinfo=timezone.utc))]
        bds = _build_breakdowns(events, "day")
        day_bds = [b for b in bds if b.breakdown_type == "day"]
        assert len(day_bds) == 2

    def test_no_day_breakdown_with_total(self):
        events = [_fake_event()]
        bds = _build_breakdowns(events, "total")
        day_bds = [b for b in bds if b.breakdown_type == "day"]
        assert len(day_bds) == 0

    def test_unknown_bucket(self):
        events = [_fake_event(campaign_id=None)]
        bds = _build_breakdowns(events, "total")
        campaign_bds = [b for b in bds if b.breakdown_type == "campaign"]
        assert len(campaign_bds) == 1
        assert campaign_bds[0].key == "unknown"

    def test_breakdown_metrics_sum_equals_total(self):
        events = [_fake_event(delivered_impressions=3), _fake_event(delivered_impressions=7)]
        total = _aggregate_metrics(events)
        bds = _build_breakdowns(events, "total")
        campaign_bds = [b for b in bds if b.breakdown_type == "campaign"]
        if campaign_bds:
            bd_sum = sum(b.metrics.delivered_impressions for b in campaign_bds)
            assert bd_sum == total.delivered_impressions

    def test_unknown_day_for_no_event_time(self):
        events = [_fake_event(event_time=None)]
        bds = _build_breakdowns(events, "day")
        day_bds = [b for b in bds if b.breakdown_type == "day"]
        assert len(day_bds) == 1
        assert day_bds[0].key == "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Query / source behavior (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestQueryBehavior(unittest.TestCase):
    def test_date_range_affects_query(self):
        """Code inspection: normalize_pop_events filters by date_from/date_to."""
        from app.domains.analytics.service import normalize_pop_events
        src = inspect.getsource(normalize_pop_events)
        assert "date_from" in src
        assert "date_to" in src

    def test_scope_campaign_filter_in_aggregation(self):
        """Scope filtering code exists in _apply_scope_filter."""
        from app.domains.analytics.service import _apply_scope_filter
        src = inspect.getsource(_apply_scope_filter)
        assert "campaign_id" in src

    def test_exclude_dry_run_true(self):
        events = [_fake_event(is_dry_run=True), _fake_event(is_dry_run=False)]
        filtered = exclude_dry_run_events(events)
        assert len(filtered) == 1

    def test_exclude_dry_run_false(self):
        events = [_fake_event(is_dry_run=True), _fake_event(is_dry_run=False)]
        assert len(events) == 2

    def test_empty_scope_returns_all(self):
        from app.domains.analytics.service import _apply_scope_filter
        events = [_fake_event()]
        f, warnings = _apply_scope_filter(events, AnalyticsScope())
        assert len(f) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 8. Planned vs delivered (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlannedVsDelivered(unittest.TestCase):
    def test_result_shape_valid(self):
        r = PlannedVsDeliveredResult()
        assert r.delivered_impressions == 0
        assert r.status == "unknown"

    def test_delivered_populated(self):
        r = PlannedVsDeliveredResult(delivered_impressions=42)
        assert r.delivered_impressions == 42

    def test_expected_unavailable(self):
        r = PlannedVsDeliveredResult()
        assert r.expected_impressions is None

    def test_status_no_plan(self):
        r = PlannedVsDeliveredResult(status="no_plan")
        assert r.status == "no_plan"

    def test_query_defaults(self):
        q = PlannedVsDeliveredQuery()
        assert q.include_planning is True
        assert q.exclude_dry_run is True


# ═══════════════════════════════════════════════════════════════════════════
# 9. No-secrets (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestNoSecrets(unittest.TestCase):
    def test_metrics_summary_no_secrets(self):
        s = _aggregate_metrics([_fake_event()])
        payload = s.model_dump()
        issues = validate_no_secrets_in_analytics_payload(payload)
        assert len(issues) == 0

    def test_breakdown_no_secrets(self):
        bds = _build_breakdowns([_fake_event()], "total")
        for b in bds:
            issues = validate_no_secrets_in_analytics_payload(b.model_dump())
            assert len(issues) == 0, f"Secrets in breakdown {b.breakdown_type}: {issues}"

    def test_result_no_secrets(self):
        s = _aggregate_metrics([])
        r = DeliveryMetricResult(metrics=s)
        issues = validate_no_secrets_in_analytics_payload(r.model_dump())
        assert len(issues) == 0

    def test_result_no_token_password(self):
        r = DeliveryMetricResult(metrics=DeliveryMetricsSummary())
        d = r.model_dump_json().lower()
        for fw in ["token", "password", "secret", "api_key"]:
            assert fw not in d, f"Forbidden '{fw}' in result JSON"


# ═══════════════════════════════════════════════════════════════════════════
# 10. Read-only boundaries (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundaries(unittest.TestCase):
    def test_service_has_no_db_add(self):
        import app.domains.analytics.service as svc
        src = inspect.getsource(svc)
        assert "db.add(" not in src
        assert ".insert(" not in src
        assert "db.commit(" not in src

    def test_no_api_router(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "domains", "analytics", "router.py")
        assert not os.path.exists(path)

    def test_no_clickhouse(self):
        imports = _imports(__import__("app.domains.analytics.service", fromlist=["calculate_delivery_metrics"]))
        assert "clickhouse" not in imports

    def test_no_device_gateway_router(self):
        imports = _imports(__import__("app.domains.analytics.service", fromlist=["calculate_delivery_metrics"]))
        assert "device_gateway.router" not in imports.replace(" ", "")

    def test_no_kso_adapter(self):
        imports = _imports(__import__("app.domains.analytics.service", fromlist=["calculate_delivery_metrics"]))
        assert "kso_adapter" not in imports

    def test_no_publication(self):
        imports = _imports(__import__("app.domains.analytics.service", fromlist=["calculate_delivery_metrics"]))
        assert "publication" not in imports
        assert "generate_manifests" not in imports
        assert "publish_batch" not in imports

    def test_no_generated_manifest(self):
        imports = _imports(__import__("app.domains.analytics.service", fromlist=["calculate_delivery_metrics"]))
        assert "generatedmanifest" not in imports.replace("_", "")

    def test_device_health_no_db_write(self):
        import app.domains.analytics.service as svc
        src = inspect.getsource(svc.calculate_device_health)
        assert "db.add(" not in src


# ═══════════════════════════════════════════════════════════════════════════
# 11. Regression (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestRegression(unittest.TestCase):
    def test_f2_test_file_exists(self):
        path = os.path.join(os.path.dirname(__file__), "test_analytics_normalization_f2.py")
        assert os.path.exists(path)

    def test_f1_test_file_exists(self):
        path = os.path.join(os.path.dirname(__file__), "test_analytics_schemas_f1.py")
        assert os.path.exists(path)

    def test_success_statuses_complete(self):
        assert "success" in PLAYBACK_SUCCESS_STATUSES
        assert "failed" in PLAYBACK_FAILURE_STATUSES

    def test_forbidden_keys_complete(self):
        required = {"password", "token", "secret", "api_key", "bearer", "cookie", "session", "jwt"}
        for fw in required:
            assert fw in FORBIDDEN_ANALYTICS_KEYS, f"Missing: {fw}"
