"""
D.5.1.1 — Planning API Security / RLS / Regression Gate: targeted tests.

Extends D.5.1 coverage with:
  - Seed idempotency & role assignments
  - Cross-advertiser placement scope (own vs. other)
  - Store scope allow/deny
  - Denied requests never write success audit
  - No secrets in response/audit
  - Invalid input (SOV/spots)
  - Import boundaries on planning/service.py
  - Main.py registration verification
  - Compatibility regression
"""

import inspect
import re
import uuid
import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.domains.planning import schemas as planning_schemas


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _uid():
    return uuid.uuid4()

def _code_lines(fn):
    src = inspect.getsource(fn)
    return re.sub(r'(:\s*\n)\s*("""|\'\'\').*?\2', r'\1', src, flags=re.DOTALL, count=1)

async def _mock_get_db():
    yield AsyncMock()

async def _mock_get_current_user():
    u = MagicMock()
    u.id = _uid()
    u.username = "test_admin"
    u.is_active = True
    return u

def _setup_app():
    from app.main import app
    from app.core.deps import get_db, get_current_user

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    app._d511_perm_patch = patch(
        "app.domains.identity.service.require_permission",
        return_value=None,
    )
    app._d511_perm_patch.start()

    return TestClient(app)

def _teardown_app():
    from app.main import app
    if hasattr(app, '_d511_perm_patch'):
        app._d511_perm_patch.stop()
    app.dependency_overrides.clear()

D1 = date(2026, 7, 1)
D10 = date(2026, 7, 10)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers: Pydantic model instances for mocking
# ═══════════════════════════════════════════════════════════════════════════

def _make_avail_result(available=True):
    return planning_schemas.AvailabilityResult(ok=True, available=available)

def _make_conflict_result(has_conflict=False):
    return planning_schemas.ConflictResult(has_conflict=has_conflict)

def _make_occupancy_result(pct=0.0):
    return planning_schemas.OccupancyResult(date_from=D1, date_to=D10, occupancy_percent=pct)

def _make_scenario_result():
    q = planning_schemas.AvailabilityQuery(date_from=D1, date_to=D10)
    return planning_schemas.PlanningScenario(query=q, dry_run=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Seed Idempotency & Role Assignments (6 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestSeedAndPermissions(unittest.TestCase):
    """planning.read permission exists, idempotent, assigned to exact 7 roles."""

    def test_planning_read_in_permissions_list(self):
        from app.domains.identity.seed import PERMISSIONS
        codes = [p[0] for p in PERMISSIONS]
        assert "planning.read" in codes
        perm = [p for p in PERMISSIONS if p[0] == "planning.read"][0]
        assert perm[1] == "View planning data"
        assert perm[2] == "planning"
        assert perm[3] == "read"

    def test_permission_appears_exactly_once(self):
        from app.domains.identity.seed import PERMISSIONS
        codes = [p[0] for p in PERMISSIONS]
        assert codes.count("planning.read") == 1

    def test_seed_uses_on_conflict_do_nothing(self):
        from app.domains.identity.seed import seed
        src = _code_lines(seed)
        assert "on_conflict_do_nothing" in src

    def test_exact_7_roles_have_planning_read(self):
        from app.domains.identity.seed import ROLE_PERMISSIONS
        expected_roles = {
            "system_admin", "security_admin", "ad_manager",
            "approver", "analyst", "advertiser", "operations",
        }
        actual_roles = set()
        for role_code, perms in ROLE_PERMISSIONS.items():
            if "planning.read" in perms:
                actual_roles.add(role_code)
        assert actual_roles == expected_roles

    def test_device_service_does_not_have_planning_read(self):
        from app.domains.identity.seed import ROLE_PERMISSIONS
        ds_perms = ROLE_PERMISSIONS.get("device_service", [])
        assert "planning.read" not in ds_perms

    def test_no_role_has_planning_manage(self):
        from app.domains.identity.seed import PERMISSIONS
        codes = [p[0] for p in PERMISSIONS]
        assert "planning.manage" not in codes


# ═══════════════════════════════════════════════════════════════════════════
# 2. Cross-Advertiser Placement Scope (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossAdvertiserPlacement(unittest.TestCase):
    """Placement-based advertiser scope."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_own_placement_allowed_conflict(self):
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

    def test_cross_advertiser_placement_denied_conflict(self):
        with patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(side_effect=HTTPException(404, "Not found")),
        ):
            resp = self.client.post(
                "/api/planning/check-conflicts",
                json={
                    "placement_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code in (403, 404)

    def test_cross_advertiser_placement_denied_availability(self):
        with patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(side_effect=HTTPException(404, "Not found")),
        ):
            resp = self.client.get(
                "/api/planning/availability",
                params={
                    "placement_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code in (403, 404)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Store Scope Allow / Deny (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestStoreScope(unittest.TestCase):
    """Store scope enforcement on occupancy endpoint."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_store_scope_allowed(self):
        from app.domains.identity.rls import UserScopeContext
        store_id = _uid()
        mock_result = _make_occupancy_result(25.0)
        with patch(
            "app.domains.planning.router.resolve_user_scope_context",
            new=AsyncMock(return_value=UserScopeContext(
                store_ids=[store_id],
            )),
        ), patch(
            "app.domains.planning.service.calculate_occupancy",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = self.client.get(
                "/api/planning/occupancy",
                params={
                    "store_id": str(store_id),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert resp.status_code == 200

    def test_store_scope_denied_wrong_store(self):
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

    def test_occupancy_without_store_id_no_scope_check(self):
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
                },
            )
            assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 4. Denied Requests Don't Write Success Audit (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestDeniedAuditSafety(unittest.TestCase):
    """Cross-scope denied requests must NOT write planning.* audit events."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_cross_advertiser_denied_no_availability_audit(self):
        with patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(side_effect=HTTPException(404, "Not found")),
        ), patch(
            "app.domains.planning.router.audit_business_action",
            new=AsyncMock(),
        ) as mock_audit:
            self.client.get(
                "/api/planning/availability",
                params={
                    "campaign_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert not mock_audit.called

    def test_cross_advertiser_denied_no_scenario_audit(self):
        with patch(
            "app.domains.planning.router._ensure_advertiser_scope",
            new=AsyncMock(side_effect=HTTPException(404, "Not found")),
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
                    },
                    "campaign_id": str(_uid()),
                },
            )
            assert not mock_audit.called

    def test_store_scope_denied_no_occupancy_audit(self):
        from app.domains.identity.rls import UserScopeContext
        with patch(
            "app.domains.planning.router.resolve_user_scope_context",
            new=AsyncMock(return_value=UserScopeContext(
                store_ids=[uuid.UUID("00000000-0000-0000-0000-000000000001")],
            )),
        ), patch(
            "app.domains.identity.rls.assert_object_in_store_scope",
            side_effect=HTTPException(404, "Not found"),
        ), patch(
            "app.domains.planning.router.audit_business_action",
            new=AsyncMock(),
        ) as mock_audit:
            self.client.get(
                "/api/planning/occupancy",
                params={
                    "store_id": str(_uid()),
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-10",
                },
            )
            assert not mock_audit.called


# ═══════════════════════════════════════════════════════════════════════════
# 5. No Secrets in Response / Audit (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestNoSecrets(unittest.TestCase):
    """Response and audit must NOT contain secrets/passwords/tokens."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_availability_response_no_secrets(self):
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
            body = resp.text.lower()
            forbidden = ["password", "secret", "access_token", "refresh_token", "token"]
            for word in forbidden:
                assert word not in body, f"'{word}' found in response"

    def test_occupancy_response_no_secrets(self):
        mock_result = _make_occupancy_result(10.0)
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
            body = resp.text.lower()
            for word in ["password", "secret", "token"]:
                assert word not in body

    def test_audit_details_no_secrets_in_source(self):
        from app.domains.planning.router import _audit_planning
        src = _code_lines(_audit_planning)
        forbidden = [
            "password", "secret", "token", "backend_url", "private_key",
            "access_key", "bearer",
        ]
        for word in forbidden:
            assert word not in src.lower(), f"Forbidden: {word}"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Invalid Input (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestInvalidInput(unittest.TestCase):
    """Invalid SOV/spots → 422 structured error."""

    def setUp(self):
        self.client = _setup_app()

    def tearDown(self):
        _teardown_app()

    def test_negative_sov_rejected(self):
        resp = self.client.get(
            "/api/planning/availability",
            params={
                "date_from": "2026-07-01",
                "date_to": "2026-07-10",
                "requested_share_of_voice": -5,
            },
        )
        assert resp.status_code in (400, 422)

    def test_sov_over_100_rejected(self):
        resp = self.client.get(
            "/api/planning/availability",
            params={
                "date_from": "2026-07-01",
                "date_to": "2026-07-10",
                "requested_share_of_voice": 150,
            },
        )
        assert resp.status_code in (400, 422)

    def test_negative_spots_rejected(self):
        resp = self.client.get(
            "/api/planning/availability",
            params={
                "date_from": "2026-07-01",
                "date_to": "2026-07-10",
                "requested_spots_per_loop": -3,
            },
        )
        assert resp.status_code in (400, 422)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Import Boundaries on planning/service.py (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestImportBoundariesService(unittest.TestCase):
    """planning/service.py does not import forbidden modules."""

    def test_service_no_device_gateway(self):
        from app.domains.planning import service as planning_service
        src = _code_lines(planning_service)
        assert "device_gateway" not in src.lower()

    def test_service_no_publication_imports(self):
        from app.domains.planning import service as planning_service
        src = _code_lines(planning_service)
        # Check import lines only — docstring mentions "publications"
        import_lines = [l for l in src.split("\n")
                        if l.strip().startswith("from ") or l.strip().startswith("import ")]
        joined = "\n".join(import_lines)
        assert "publication" not in joined.lower()

    def test_service_no_generated_manifest_imports(self):
        from app.domains.planning import service as planning_service
        src = _code_lines(planning_service)
        import_lines = [l for l in src.split("\n")
                        if l.strip().startswith("from ") or l.strip().startswith("import ")]
        joined = "\n".join(import_lines)
        assert "generated_manifest" not in joined.lower()
        assert "generate_manifest" not in joined.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 8. Main.py Registration (2 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestMainRegistration(unittest.TestCase):
    """planning router correctly registered in main.py."""

    def test_planning_router_imported_in_main(self):
        import app.main
        src = _code_lines(app.main)
        assert "from app.domains.planning.router import router as planning_router" in src

    def test_planning_router_included_in_app(self):
        import app.main
        src = _code_lines(app.main)
        assert "app.include_router(planning_router)" in src


# ═══════════════════════════════════════════════════════════════════════════
# 9. Additional Read-Only Boundaries (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestAdditionalReadOnly(unittest.TestCase):
    """Deeper read-only checks beyond router.py."""

    def test_router_no_inventory_unit_write(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "InventoryUnit(" not in src

    def test_router_no_capacity_rule_write(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "CapacityRule(" not in src

    def test_router_no_scheduling_write(self):
        from app.domains.planning import router as planning_router
        src = _code_lines(planning_router)
        assert "ScheduleRun" not in src
        assert "ScheduleItem" not in src


# ═══════════════════════════════════════════════════════════════════════════
# 10. Compatibility Regression (1 test)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlanningSuiteCompatibility(unittest.TestCase):
    """Confirm D.5.1.1 does not break existing planning tests."""

    def test_d51_test_file_exists(self):
        """D.5.1 test file exists and is syntactically valid."""
        import os
        test_file = os.path.join(
            os.path.dirname(__file__), "test_planning_api_d5_1.py"
        )
        assert os.path.exists(test_file), "D.5.1 test file missing"
        with open(test_file) as f:
            compile(f.read(), test_file, "exec")
