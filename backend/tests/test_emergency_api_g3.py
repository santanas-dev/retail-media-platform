"""G.3 — Emergency API Read-Only: targeted tests.

Tests: route reg (7), permission (8), capabilities (4),
preview (7), simulate stop (8), simulate message (5),
audit (7), read-only (8), source boundaries (5), compatibility (4).
Total: 63 tests.
"""

import inspect
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _mock_get_db():
    db = AsyncMock()
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = None
    mr.scalars.return_value.all.return_value = []
    db.execute.return_value = mr
    yield db


async def _mock_get_user():
    u = MagicMock()
    u.id = "00000000-0000-0000-0000-000000000001"
    u.username = "test_admin"
    u.is_active = True
    return u


def _setup_admin():
    from app.main import app
    from app.core.deps import get_db, get_current_user
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_user
    app._g3_perm = patch("app.domains.identity.service.require_permission", return_value=None)
    app._g3_perm.start()
    return TestClient(app)


def _setup_no_perm():
    from app.main import app
    from app.core.deps import get_db, get_current_user
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_user
    return TestClient(app)


def _teardown():
    from app.main import app
    if hasattr(app, "_g3_perm"):
        app._g3_perm.stop()
    app.dependency_overrides.clear()


def body(**kw):
    from app.domains.emergency.schemas import EmergencyActionCreate, EmergencyActionType, EmergencyTarget
    defaults = {
        "action_type": EmergencyActionType.STOP_CAMPAIGN.value,
        "reason": "test",
        "target": {"campaign_code": "X"},
    }
    defaults.update(kw)
    return EmergencyActionCreate(**defaults).model_dump()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Route registration (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestRouteRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _setup_admin()

    @classmethod
    def tearDownClass(cls):
        _teardown()

    def test_router_file_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "domains", "emergency", "router.py")
        assert os.path.exists(path)

    def test_capabilities_endpoint(self):
        resp = self.client.get("/api/emergency/capabilities")
        assert resp.status_code != 404

    def test_preview_endpoint(self):
        resp = self.client.post("/api/emergency/preview", json=body())
        assert resp.status_code != 404

    def test_simulate_stop_endpoint(self):
        resp = self.client.post("/api/emergency/simulate-stop", json=body())
        assert resp.status_code != 404

    def test_simulate_message_endpoint(self):
        from app.domains.emergency.schemas import EmergencyActionType
        resp = self.client.post("/api/emergency/simulate-message", json=body(
            action_type=EmergencyActionType.EMERGENCY_MESSAGE.value,
            message={"title": "T", "body": "B"},
        ))
        assert resp.status_code != 404

    def test_no_execute_endpoint(self):
        resp = self.client.post("/api/emergency/execute", json=body())
        assert resp.status_code == 404

    def test_no_activate_endpoint(self):
        resp = self.client.post("/api/emergency/activate", json=body())
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 2. Permission (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestPermission(unittest.TestCase):
    def setUp(self):
        self.client = _setup_no_perm()

    def tearDown(self):
        _teardown()

    def test_capabilities_no_auth_denied(self):
        resp = self.client.get("/api/emergency/capabilities")
        assert resp.status_code in (401, 403)

    def test_preview_no_auth_denied(self):
        resp = self.client.post("/api/emergency/preview", json=body())
        assert resp.status_code in (401, 403)

    def test_simulate_stop_no_auth_denied(self):
        resp = self.client.post("/api/emergency/simulate-stop", json=body())
        assert resp.status_code in (401, 403)

    def test_simulate_message_no_auth_denied(self):
        resp = self.client.post("/api/emergency/simulate-message", json=body())
        assert resp.status_code in (401, 403)

    def test_no_execute_permission(self):
        """emergency.execute permission does not exist."""
        import app.domains.identity.seed as seed
        perms = [p[0] for p in seed.PERMISSIONS]
        assert "emergency.execute" not in perms

    def test_no_approve_permission(self):
        import app.domains.identity.seed as seed
        perms = [p[0] for p in seed.PERMISSIONS]
        assert "emergency.approve" not in perms

    def test_emergency_read_exists(self):
        import app.domains.identity.seed as seed
        perms = [p[0] for p in seed.PERMISSIONS]
        assert "emergency.read" in perms

    def test_device_service_no_emergency_read(self):
        import app.domains.identity.seed as seed
        ds_perms = seed.ROLE_PERMISSIONS.get("device_service", [])
        assert "emergency.read" not in ds_perms


# ═══════════════════════════════════════════════════════════════════════════
# 3. Capabilities (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestCapabilities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _setup_admin()

    @classmethod
    def tearDownClass(cls):
        _teardown()

    def test_returns_ok(self):
        resp = self.client.get("/api/emergency/capabilities")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_returns_action_types(self):
        resp = self.client.get("/api/emergency/capabilities")
        data = resp.json()
        assert "action_types" in data
        assert "stop_campaign" in data["action_types"]

    def test_dry_run_only_true(self):
        resp = self.client.get("/api/emergency/capabilities")
        assert resp.json()["dry_run_only"] is True

    def test_returns_statuses(self):
        resp = self.client.get("/api/emergency/capabilities")
        assert "statuses" in resp.json()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Preview (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _setup_admin()

    @classmethod
    def tearDownClass(cls):
        _teardown()

    def test_stop_preview_dry_run(self):
        resp = self.client.post("/api/emergency/preview", json=body())
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True

    def test_message_preview_dry_run(self):
        from app.domains.emergency.schemas import EmergencyActionType
        resp = self.client.post("/api/emergency/preview", json=body(
            action_type=EmergencyActionType.EMERGENCY_MESSAGE.value,
            message={"title": "T", "body": "B"},
        ))
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True

    def test_invalid_body_returns_422(self):
        resp = self.client.post("/api/emergency/preview", json={"bad": "data"})
        assert resp.status_code == 422

    def test_broad_scope_warning(self):
        resp = self.client.post("/api/emergency/preview", json=body(
            target={"channel_code": "kso"},
        ))
        data = resp.json()
        assert len(data.get("warnings", [])) > 0

    def test_no_secrets_in_response(self):
        resp = self.client.post("/api/emergency/preview", json=body())
        raw = resp.text.lower()
        for fw in ("password", "token", "secret", "api_key"):
            assert fw not in raw, f"'{fw}' in response"

    def test_dry_run_false_rejected(self):
        """dry_run=False raises ValueError at Pydantic model level → 422."""
        resp = self.client.post("/api/emergency/preview", json={
            "action_type": "stop_campaign",
            "reason": "test",
            "target": {"campaign_code": "X"},
            "dry_run": False,
        })
        assert resp.status_code == 422

    def test_preview_no_execution_side_effects(self):
        """Code inspection: preview function does not call db.add."""
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr.emergency_preview)
        assert "db.add(" not in src


# ═══════════════════════════════════════════════════════════════════════════
# 5. Simulate Stop (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestSimulateStop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _setup_admin()

    @classmethod
    def tearDownClass(cls):
        _teardown()

    def _sim_stop(self, atype: str, **kw):
        return self.client.post("/api/emergency/simulate-stop", json=body(
            action_type=atype, **kw,
        ))

    def test_stop_campaign_dry_run(self):
        resp = self._sim_stop("stop_campaign")
        assert resp.json()["dry_run"] is True

    def test_stop_device_dry_run(self):
        resp = self.client.post("/api/emergency/simulate-stop", json=body(
            action_type="stop_device", target={"device_code": "D1"},
        ))
        assert resp.json()["dry_run"] is True

    def test_resume_dry_run(self):
        resp = self._sim_stop("resume", target={"campaign_code": "X"})
        assert resp.json()["dry_run"] is True

    def test_message_rejected_by_stop(self):
        from app.domains.emergency.schemas import EmergencyActionType
        resp = self.client.post("/api/emergency/simulate-stop", json=body(
            action_type=EmergencyActionType.EMERGENCY_MESSAGE.value,
            message={"title": "T", "body": "B"},
        ))
        assert resp.json()["ok"] is False

    def test_real_execution_disabled(self):
        resp = self._sim_stop("stop_campaign")
        data = resp.json()
        warnings = [w["code"] for w in data.get("warnings", [])]
        assert "real_execution_disabled" in warnings

    def test_no_secrets_in_response(self):
        resp = self._sim_stop("stop_campaign")
        raw = resp.text.lower()
        for fw in ("password", "token", "secret", "api_key"):
            assert fw not in raw

    def test_simulate_stop_no_db_write(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr.emergency_simulate_stop)
        assert "db.add(" not in src

    def test_simulate_stop_no_campaign_change(self):
        """simulate_stop router handler has no Campaign write code."""
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr.emergency_simulate_stop)
        assert "Campaign." not in src


# ═══════════════════════════════════════════════════════════════════════════
# 6. Simulate Message (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestSimulateMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _setup_admin()

    @classmethod
    def tearDownClass(cls):
        _teardown()

    def test_message_dry_run(self):
        from app.domains.emergency.schemas import EmergencyActionType
        resp = self.client.post("/api/emergency/simulate-message", json=body(
            action_type=EmergencyActionType.EMERGENCY_MESSAGE.value,
            message={"title": "T", "body": "B"},
        ))
        assert resp.json()["dry_run"] is True

    def test_missing_message_rejected(self):
        from app.domains.emergency.schemas import EmergencyActionType
        resp = self.client.post("/api/emergency/simulate-message", json={
            "action_type": EmergencyActionType.EMERGENCY_MESSAGE.value,
            "reason": "test",
            "target": {"channel_code": "kso"},
        })
        assert resp.status_code == 422

    def test_stop_rejected_by_message(self):
        resp = self.client.post("/api/emergency/simulate-message", json=body(
            action_type="stop_campaign",
        ))
        data = resp.json()
        assert data["ok"] is False

    def test_no_secrets(self):
        from app.domains.emergency.schemas import EmergencyActionType
        resp = self.client.post("/api/emergency/simulate-message", json=body(
            action_type=EmergencyActionType.EMERGENCY_MESSAGE.value,
            message={"title": "T", "body": "B"},
        ))
        raw = resp.text.lower()
        for fw in ("password", "secret", "api_key"):
            assert fw not in raw

    def test_no_manifest_import(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "GeneratedManifest" not in src
        assert "manifest" not in " ".join(
            l.strip() for l in inspect.getsource(rtr).split("\n")
            if l.strip().startswith("from ") or l.strip().startswith("import ")
        ).lower()


# ═══════════════════════════════════════════════════════════════════════════
# 7. Audit (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestAudit(unittest.TestCase):
    def test_capabilities_has_audit(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr.emergency_capabilities)
        assert "_audit" in src

    def test_preview_has_audit(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr.emergency_preview)
        assert "_audit" in src

    def test_simulate_stop_has_audit(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr.emergency_simulate_stop)
        assert "_audit" in src

    def test_simulate_message_has_audit(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr.emergency_simulate_message)
        assert "_audit" in src

    def test_audit_no_secrets(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr._audit)
        for fw in ("password", "token", "secret", "api_key", "bearer"):
            assert fw not in src.lower(), f"'{fw}' in _audit"

    def test_audit_target_ref_dry_run(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr._audit)
        assert "dry-run" in src

    def test_audit_calls_business_action(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "audit_business_action" in src


# ═══════════════════════════════════════════════════════════════════════════
# 8. Read-only (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestReadOnly(unittest.TestCase):
    def test_router_no_db_add(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "db.add(" not in src
        assert ".insert(" not in src

    def test_no_execute_route(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "/execute" not in src

    def test_no_activate_route(self):
        """No @router.post('/...activate...') decorator."""
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert '@router.post("/api/emergency/activate' not in src
        assert '@router.get("/api/emergency/activate' not in src

    def test_no_approve_route(self):
        """No @router.post('/...approve...') decorator."""
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert '@router.post("/api/emergency/approve' not in src
        assert '@router.get("/api/emergency/approve' not in src

    def test_no_cancel_route(self):
        """No @router.post('/...cancel...') decorator."""
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert '@router.post("/api/emergency/cancel' not in src
        assert '@router.get("/api/emergency/cancel' not in src

    def test_no_migrations(self):
        import glob
        mg_path = os.path.join(os.path.dirname(__file__), "..", "..", "migrations", "versions")
        if os.path.exists(mg_path):
            for mf in sorted(glob.glob(os.path.join(mg_path, "*.py")))[-5:]:
                with open(mf) as f:
                    if "emergency" in f.read().lower():
                        assert False, f"Emergency migration: {mf}"

    def test_no_portal(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "template" not in src.lower()

    def test_no_campaign_placement_mutation(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "Campaign." not in src
        assert "Placement." not in src


# ═══════════════════════════════════════════════════════════════════════════
# 9. Source boundaries (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestSourceBoundaries(unittest.TestCase):
    def test_no_clickhouse(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "clickhouse" not in src.lower()

    def test_no_device_gateway(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "device_gateway" not in src.lower()

    def test_no_kso_adapter(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "kso_adapter" not in src.lower()

    def test_no_publication(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "publication" not in src.lower()

    def test_no_generated_manifest(self):
        import app.domains.emergency.router as rtr
        src = inspect.getsource(rtr)
        assert "generated_manifest" not in src.lower().replace(" ", "")


# ═══════════════════════════════════════════════════════════════════════════
# 10. Compatibility (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestCompatibility(unittest.TestCase):
    def test_g2_tests_exist(self):
        path = os.path.join(os.path.dirname(__file__), "test_emergency_service_g2.py")
        assert os.path.exists(path)

    def test_g1_tests_exist(self):
        path = os.path.join(os.path.dirname(__file__), "test_emergency_schemas_g1.py")
        assert os.path.exists(path)

    def test_seed_idempotent(self):
        import app.domains.identity.seed as seed
        perms = [p[0] for p in seed.PERMISSIONS]
        assert perms.count("emergency.read") == 1, "emergency.read must appear exactly once"

    def test_roles_assigned(self):
        import app.domains.identity.seed as seed
        for role in ("system_admin", "security_admin", "operations"):
            perms = seed.ROLE_PERMISSIONS.get(role, [])
            assert "emergency.read" in perms, f"{role} missing emergency.read"
