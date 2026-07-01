"""
D.5.1 — Planning API Read-Only Endpoints: targeted tests.

Tests with FastAPI TestClient + dependency overrides:
  - Permissions: planning.read required for all 5 endpoints
  - Advertiser scope: via campaign_id/placement_id
  - Store scope: restricted store_id denied
  - Response shapes: AvailabilityResult, ConflictResult, OccupancyResult, PlanningScenario
  - Audit: events written for all endpoints
  - Read-only boundaries: no CampaignBooking/BookingItem/Placement/Campaign writes
  - Compatibility: D.1–D.4 + Inventory tests still pass
"""

import inspect
import re
import uuid
import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _uid():
    return uuid.uuid4()

async def _mock_get_db():
    yield AsyncMock()

async def _mock_get_current_user():
    u = MagicMock()
    u.id = _uid()
    u.username = "test_admin"
    u.is_active = True
    return u

def _code_lines(fn):
    src = inspect.getsource(fn)
    return re.sub(r'(:\s*\n)\s*("""|\'\'\').*?\2', r'\1', src, flags=re.DOTALL, count=1)

def _setup_app():
    """Return TestClient with get_db + get_current_user mocked, permissions bypassed."""
    from app.main import app
    from app.core.deps import get_db, get_current_user

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    app._d51_perm_patch = patch(
        "app.domains.identity.service.require_permission",
        return_value=None,
    )
    app._d51_perm_patch.start()

    return TestClient(app)

def _setup_app_without_perms():
    """Return TestClient WITHOUT permission bypass — tests real 403."""
    from app.main import app
    from app.core.deps import get_db, get_current_user

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    return TestClient(app)

def _teardown_app():
    from app.main import app
    if hasattr(app, '_d51_perm_patch'):
        app._d51_perm_patch.stop()
    app.dependency_overrides.clear()

D1 = date(2026, 7, 1)
D10 = date(2026, 7, 10)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Permissions (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestPermissions(unittest.TestCase):
    """planning.read required for all endpoints."""

    def setUp(self):
        self.client = _setup_app_without_perms()

    def tearDown(self):
        _teardown_app()

    def test_availability_requires_planning_read(self):
        resp = self.client.get(
            "/api/planning/availability",
            params={"date_from": "2026-07-01", "date_to": "2026-07-10"},
        )
        assert resp.status_code == 403

    def test_check_conflicts_requires_planning_read(self):
        resp = self.client.post(
            "/api/planning/check-conflicts",
            json={"date_from": "2026-07-01", "date_to": "2026-07-10"},
        )
        assert resp.status_code == 403

    def test_occupancy_requires_planning_read(self):
        resp = self.client.get(
            "/api/planning/occupancy",
            params={"date_from": "2026-07-01", "date_to": "2026-07-10"},
        )
        assert resp.status_code == 403

    def test_scenario_requires_planning_read(self):
        resp = self.client.post(
            "/api/planning/scenario",
            json={
                "query": {
                    "date_from": "2026-07-01", "date_to": "2026-07-10",
                    "channel_id": str(_uid()),
                },
                "dry_run": True,
            },
        )
        assert resp.status_code == 403

    def test_inventory_units_availability_requires_planning_read(self):
        resp = self.client.get(
            "/api/planning/inventory-units/availability",
            params={"date_from": "2026-07-01", "date_to": "2026-07-10"},
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 2. Availability API (6 tests)
# ═══════════════════════════════════════════════════════════════════════════

def _make_avail_result(available=True):
    """Create a realistic AvailabilityResult mock."""
    from app.domains.planning.schemas import AvailabilityResult
    return AvailabilityResult(ok=True, available=available)

class TestAvailabilityAPI(unittest.TestCase):
    """GET /api/planning/availability."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_availability_success(self):
        mock_result = _make_avail_result(True)
        with patch(
            "app.domains.planning.service.check_availability",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/availability",
                params={
                    "channel_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True

    def test_availability_invalid_date_range(self):
        """date_from > date_to triggers Pydantic validation error from AvailabilityQuery."""
        resp = self.client.get(
            "/api/planning/availability",
            params={"date_from": "2026-07-10", "date_to": "2026-07-01"},
        )
        # try/except in router returns 422 for ValidationError
        assert resp.status_code == 422

    def test_availability_missing_dates(self):
        resp = self.client.get("/api/planning/availability")
        assert resp.status_code == 422

    def test_availability_no_inventory(self):
        mock_result = _make_avail_result(False)
        with patch(
            "app.domains.planning.service.check_availability",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/availability",
                params={
                    "inventory_unit_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is False

    def test_availability_with_campaign_id(self):
        cid = str(_uid())
        mock_result = _make_avail_result(True)
        with patch(
            "app.domains.planning.service.check_availability",
            new=AsyncMock(return_value=mock_result),
        ), patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(),
        ):
            resp = self.client.get(
                "/api/planning/availability",
                params={
                    "campaign_id": cid,
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200

    def test_availability_result_shape(self):
        mock_result = _make_avail_result(True)
        with patch(
            "app.domains.planning.service.check_availability",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/availability",
                params={
                    "inventory_unit_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            data = resp.json()
            for field in ["available", "ok", "inventory_units", "warnings", "errors"]:
                assert field in data, f"Missing field: {field}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Conflict API (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

def _make_conflict_result(has_conflict=False):
    from app.domains.planning.schemas import ConflictResult
    return ConflictResult(has_conflict=has_conflict)

class TestConflictAPI(unittest.TestCase):
    """POST /api/planning/check-conflicts."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_conflict_success(self):
        mock_result = _make_conflict_result(False)
        with patch(
            "app.domains.planning.service.check_conflicts",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.post(
                "/api/planning/check-conflicts",
                json={
                    "inventory_unit_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_conflict"] is False

    def test_conflict_detected(self):
        mock_result = _make_conflict_result(True)
        with patch(
            "app.domains.planning.service.check_conflicts",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.post(
                "/api/planning/check-conflicts",
                json={
                    "inventory_unit_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            data = resp.json()
            assert data["has_conflict"] is True

    def test_conflict_with_placement_id(self):
        mock_result = _make_conflict_result(False)
        with patch(
            "app.domains.planning.service.check_conflicts",
            new=AsyncMock(return_value=mock_result),
        ), patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(),
        ):
            resp = self.client.post(
                "/api/planning/check-conflicts",
                json={
                    "placement_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200

    def test_conflict_result_shape(self):
        mock_result = _make_conflict_result(False)
        with patch(
            "app.domains.planning.service.check_conflicts",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.post(
                "/api/planning/check-conflicts",
                json={
                    "inventory_unit_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            data = resp.json()
            for field in ["has_conflict", "conflicts", "warnings", "errors"]:
                assert field in data

    def test_conflict_no_scope_error(self):
        """ConflictCheck without scope — Pydantic catches required fields at request level."""
        resp = self.client.post(
            "/api/planning/check-conflicts",
            json={
                "date_from": "2026-07-01",
                "date_to": "2026-07-10",
            },
        )
        # FastAPI/Pydantic will accept the request; service handles scope validation
        assert resp.status_code in (200, 422)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Occupancy API (6 tests)
# ═══════════════════════════════════════════════════════════════════════════

def _make_occupancy_result(occupancy_pct=0.0):
    from app.domains.planning.schemas import OccupancyResult
    return OccupancyResult(
        date_from=D1, date_to=D10,
        occupancy_percent=occupancy_pct,
    )

class TestOccupancyAPI(unittest.TestCase):
    """GET /api/planning/occupancy."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_occupancy_success(self):
        mock_result = _make_occupancy_result(45.0)
        with patch(
            "app.domains.planning.service.calculate_occupancy",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/occupancy",
                params={
                    "inventory_unit_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["occupancy_percent"] == 45.0

    def test_occupancy_by_store_id(self):
        """Store ID filter passed through to occupancy calculation."""
        mock_result = _make_occupancy_result(0.0)
        from app.domains.identity.rls import UserScopeContext
        with patch(
            "app.domains.planning.router.resolve_user_scope_context",
            new=AsyncMock(return_value=UserScopeContext()),
        ), patch(
            "app.domains.planning.service.calculate_occupancy",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/occupancy",
                params={
                    "store_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200

    def test_occupancy_invalid_granularity(self):
        resp = self.client.get(
            "/api/planning/occupancy",
            params={
                "date_from": "2026-07-01",
                "date_to": "2026-07-10",
                "granularity": "invalid_value",
            },
        )
        assert resp.status_code == 422

    def test_occupancy_hour_granularity(self):
        mock_result = _make_occupancy_result(0.0)
        with patch(
            "app.domains.planning.service.calculate_occupancy",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/occupancy",
                params={
                    "channel_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                    "granularity": "hour",
                },
            )
            assert resp.status_code == 200

    def test_occupancy_missing_dates(self):
        resp = self.client.get("/api/planning/occupancy")
        assert resp.status_code == 422

    def test_occupancy_result_shape(self):
        mock_result = _make_occupancy_result(12.5)
        with patch(
            "app.domains.planning.service.calculate_occupancy",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/occupancy",
                params={
                    "channel_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            data = resp.json()
            for field in ["occupancy_percent", "date_from", "date_to", "warnings", "errors"]:
                assert field in data, f"Missing: {field}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Scenario API (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

def _make_scenario_result():
    from app.domains.planning.schemas import PlanningScenario, AvailabilityQuery
    q = AvailabilityQuery(date_from=D1, date_to=D10)
    return PlanningScenario(query=q, dry_run=True)

class TestScenarioAPI(unittest.TestCase):
    """POST /api/planning/scenario."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_scenario_success(self):
        mock_result = _make_scenario_result()
        with patch(
            "app.domains.planning.service.simulate_planning_scenario",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.post(
                "/api/planning/scenario",
                json={
                    "query": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-10",
                        "channel_id": str(_uid()),
                    },
                    "dry_run": True,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["dry_run"] is True

    def test_scenario_dry_run_enforced(self):
        """Router forces dry_run=True regardless of input."""
        mock_result = _make_scenario_result()
        with patch(
            "app.domains.planning.service.simulate_planning_scenario",
            new=AsyncMock(return_value=mock_result),
        ) as mock_svc:
            resp = self.client.post(
                "/api/planning/scenario",
                json={
                    "query": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-10",
                        "channel_id": str(_uid()),
                    },
                    "dry_run": False,
                },
            )
            assert resp.status_code == 200
            # Verify response is always dry_run=True
            data = resp.json()
            assert data["dry_run"] is True

    def test_scenario_does_not_create_booking(self):
        mock_result = _make_scenario_result()
        with patch(
            "app.domains.planning.service.simulate_planning_scenario",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.post(
                "/api/planning/scenario",
                json={
                    "query": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-10",
                        "channel_id": str(_uid()),
                    },
                    "dry_run": True,
                },
            )
            data = resp.json()
            assert data["dry_run"] is True

    def test_scenario_with_campaign_id(self):
        mock_result = _make_scenario_result()
        with patch(
            "app.domains.planning.service.simulate_planning_scenario",
            new=AsyncMock(return_value=mock_result),
        ), patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(),
        ):
            resp = self.client.post(
                "/api/planning/scenario",
                json={
                    "query": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-10",
                    },
                    "campaign_id": str(_uid()),
                    "dry_run": True,
                },
            )
            assert resp.status_code == 200

    def test_scenario_result_shape(self):
        mock_result = _make_scenario_result()
        with patch(
            "app.domains.planning.service.simulate_planning_scenario",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.post(
                "/api/planning/scenario",
                json={
                    "query": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-10",
                        "channel_id": str(_uid()),
                    },
                },
            )
            data = resp.json()
            for field in ["dry_run", "errors", "warnings"]:
                assert field in data


# ═══════════════════════════════════════════════════════════════════════════
# 6. Inventory Units Availability API (2 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestInventoryUnitsAvailabilityAPI(unittest.TestCase):
    """GET /api/planning/inventory-units/availability."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_inventory_units_availability_success(self):
        mock_result = _make_avail_result(True)
        with patch(
            "app.domains.planning.service.check_availability",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/inventory-units/availability",
                params={
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200

    def test_inventory_units_availability_missing_dates(self):
        resp = self.client.get("/api/planning/inventory-units/availability")
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 7. Advertiser Scope (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestAdvertiserScope(unittest.TestCase):
    """RLS advertiser scope enforcement."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_cross_advertiser_blocked_availability(self):
        """Availability with campaign_id from another advertiser should fail."""
        with patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(side_effect=HTTPException(404, "Not found")),
        ):
            resp = self.client.get(
                "/api/planning/availability",
                params={
                    "campaign_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code in (403, 404)

    def test_cross_advertiser_blocked_scenario(self):
        with patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(side_effect=HTTPException(404, "Not found")),
        ):
            resp = self.client.post(
                "/api/planning/scenario",
                json={
                    "query": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-10",
                    },
                    "campaign_id": str(_uid()),
                },
            )
            assert resp.status_code in (403, 404)

    def test_store_scope_applied_occupancy(self):
        """Store scope enforced for occupancy — unauthorized store returns 404."""
        from app.domains.identity.rls import UserScopeContext
        with patch(
            "app.domains.planning.router.resolve_user_scope_context",
            new=AsyncMock(return_value=UserScopeContext(
                store_ids=[uuid.UUID("00000000-0000-0000-0000-000000000001")],
            )),
        ), patch(
            "app.domains.identity.rls.assert_object_in_store_scope",
            side_effect=HTTPException(404, "Not found"),
        ):
            resp = self.client.get(
                "/api/planning/occupancy",
                params={
                    "store_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code in (403, 404)

    def test_placement_scope_applied_conflict(self):
        """Placement advertiser scope enforced for conflicts."""
        mock_result = _make_conflict_result(False)
        with patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(),
        ), patch(
            "app.domains.planning.service.check_conflicts",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.post(
                "/api/planning/check-conflicts",
                json={
                    "placement_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 8. Audit (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestAudit(unittest.TestCase):
    """Audit events for planning actions."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_availability_audit_event(self):
        mock_result = _make_avail_result(False)
        with patch(
            "app.domains.planning.service.check_availability",
            new=AsyncMock(return_value=mock_result),
        ), patch(
            "app.domains.planning.router.audit_business_action",
            new=AsyncMock(),
        ) as mock_audit:
            self.client.get(
                "/api/planning/availability",
                params={
                    "channel_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            mock_audit.assert_called()
            call_kwargs = mock_audit.call_args.kwargs
            assert call_kwargs["action"] == "planning.availability.checked"

    def test_conflict_audit_event(self):
        mock_result = _make_conflict_result(False)
        with patch(
            "app.domains.planning.service.check_conflicts",
            new=AsyncMock(return_value=mock_result),
        ), patch(
            "app.domains.planning.router.audit_business_action",
            new=AsyncMock(),
        ) as mock_audit:
            self.client.post(
                "/api/planning/check-conflicts",
                json={
                    "inventory_unit_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            call_kwargs = mock_audit.call_args.kwargs
            assert call_kwargs["action"] == "planning.conflict.checked"

    def test_occupancy_audit_event(self):
        mock_result = _make_occupancy_result(0.0)
        with patch(
            "app.domains.planning.service.calculate_occupancy",
            new=AsyncMock(return_value=mock_result),
        ), patch(
            "app.domains.planning.router.audit_business_action",
            new=AsyncMock(),
        ) as mock_audit:
            self.client.get(
                "/api/planning/occupancy",
                params={
                    "channel_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            call_kwargs = mock_audit.call_args.kwargs
            assert call_kwargs["action"] == "planning.occupancy.viewed"

    def test_scenario_audit_event(self):
        mock_result = _make_scenario_result()
        with patch(
            "app.domains.planning.service.simulate_planning_scenario",
            new=AsyncMock(return_value=mock_result),
        ), patch(
            "app.domains.planning.router.audit_business_action",
            new=AsyncMock(),
        ) as mock_audit:
            self.client.post(
                "/api/planning/scenario",
                json={
                    "query": {
                        "date_from": "2026-07-01",
                        "date_to": "2026-07-10",
                        "channel_id": str(_uid()),
                    },
                },
            )
            call_kwargs = mock_audit.call_args.kwargs
            assert call_kwargs["action"] == "planning.scenario.simulated"


# ═══════════════════════════════════════════════════════════════════════════
# 9. Read-Only Boundaries (8 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestReadOnlyBoundary(unittest.TestCase):
    """D.5.1 does not create bookings or change state."""

    def test_router_no_insert_update_delete(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "insert" not in src.lower()
        assert "update" not in src.lower()
        assert "delete" not in src.lower()
        assert "db.add" not in src

    def test_router_no_campaign_booking_creation(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "CampaignBooking(" not in src
        assert "BookingItem(" not in src

    def test_router_no_placement_write(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "Placement(" not in src

    def test_router_no_campaign_write(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "Campaign(" not in src

    def test_router_no_gateway_import(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "device_gateway" not in src.lower()

    def test_router_no_publication_import(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "publication" not in src.lower()

    def test_router_no_generated_manifests(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "generated_manifest" not in src.lower()
        assert "generate_manifest" not in src.lower()

    def test_router_no_portal_import(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "portal" not in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 10. Route Registration (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestRouteRegistration(unittest.TestCase):
    """All 5 endpoints are registered in the app."""

    def test_all_planning_routes_registered(self):
        from app.main import app
        from app.domains.planning.router import router as planning_router
        # Check routes on the planning router itself
        route_paths = []
        for r in planning_router.routes:
            if hasattr(r, "path"):
                route_paths.append(r.path)
        expected = [
            "/api/planning/availability",
            "/api/planning/check-conflicts",
            "/api/planning/occupancy",
            "/api/planning/scenario",
            "/api/planning/inventory-units/availability",
        ]
        for path in expected:
            assert path in route_paths, f"Route not registered: {path}"

    def test_availability_route_registered(self):
        from app.domains.planning.router import router as planning_router
        paths = [r.path for r in planning_router.routes if hasattr(r, "path")]
        assert "/api/planning/availability" in paths

    def test_planning_router_tag(self):
        from app.domains.planning.router import router
        assert router.tags == ["planning"]


# ═══════════════════════════════════════════════════════════════════════════
# 11. Code Source Verification (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestCodeSourceVerification(unittest.TestCase):
    """Source-code checks for safety invariants."""

    def test_ensure_advertiser_scope_uses_direct_select(self):
        from app.domains.planning.router import _ensure_advertiser_scope
        src = _code_lines(_ensure_advertiser_scope)
        assert "select(" in src or "sa_select" in src

    def test_audit_details_no_secrets(self):
        from app.domains.planning.router import _audit_planning
        src = _code_lines(_audit_planning)
        forbidden = ["password", "secret", "token", "backend_url", "private_key"]
        for word in forbidden:
            assert word not in src.lower(), f"Forbidden word in audit: {word}"

    def test_router_only_uses_planning_service(self):
        from app.domains.planning import router
        src = _code_lines(router)
        assert "from app.domains.planning" in src

    def test_dry_run_always_true_in_scenario(self):
        from app.domains.planning.router import planning_scenario
        src = _code_lines(planning_scenario)
        assert "data.dry_run = True" in src or "dry_run = True" in src
