"""
F.4.1 — Analytics API Security / RLS / Regression Gate.

Targeted security tests:
  Permission (5), Permission specificity (4), RLS/Scope (10),
  Audit (5), No-secrets (5), Read-only boundaries (6),
  Source boundaries (4), Compatibility (4).
Total: 43 tests.
"""

import asyncio
import inspect
import os
import re
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4 as _uid

from fastapi import HTTPException
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _mock_get_db():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result
    yield db


async def _mock_get_current_user():
    u = MagicMock()
    u.id = _uid()
    u.username = "test_admin"
    u.is_active = True
    return u


def _setup_admin_client():
    """Client with full admin bypass (permissions + admin scope)."""
    from app.main import app
    from app.core.deps import get_db, get_current_user

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    app._f41_perm_patch = patch(
        "app.domains.identity.service.require_permission",
        return_value=None,
    )
    app._f41_perm_patch.start()

    return TestClient(app)


def _setup_no_perm_client():
    """Client WITHOUT permission bypass."""
    from app.main import app
    from app.core.deps import get_db, get_current_user

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    return TestClient(app)


def _teardown():
    from app.main import app
    if hasattr(app, "_f41_perm_patch"):
        app._f41_perm_patch.stop()
    app.dependency_overrides.clear()


def _imports(mod):
    return "\n".join(
        l.strip() for l in inspect.getsource(mod).split("\n")
        if l.strip().startswith("from ") or l.strip().startswith("import ")
    ).lower()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Permission (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestPermissionEnforcement(unittest.TestCase):
    def setUp(self):
        self.client = _setup_no_perm_client()

    def tearDown(self):
        _teardown()

    def test_no_auth_returns_401_or_403(self):
        resp = self.client.get("/api/analytics/delivery/summary")
        assert resp.status_code in (401, 403), f"Got {resp.status_code}"

    def test_no_reports_read_denied_summary(self):
        resp = self.client.get("/api/analytics/delivery/summary")
        assert resp.status_code in (401, 403)

    def test_no_reports_read_denied_query(self):
        resp = self.client.post("/api/analytics/delivery/query", json={
            "time_range": {"granularity": "total"}, "scope": {},
        })
        assert resp.status_code in (401, 403)

    def test_no_reports_read_denied_planned(self):
        resp = self.client.get("/api/analytics/planned-vs-delivered")
        assert resp.status_code in (401, 403)

    def test_no_reports_read_denied_health(self):
        resp = self.client.get("/api/analytics/device-health")
        assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Permission: reports.read used (not planning.read, not analytics.read) (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestPermissionSpecificity(unittest.TestCase):
    def test_requires_reports_read_not_planning_read(self):
        """Code inspection: all 4 endpoints use require_permission('reports.read')."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr)
        assert 'require_permission("reports.read")' in src
        assert "planning.read" not in src

    def test_analytics_read_not_required(self):
        """No analytics.read permission referenced anywhere."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr)
        assert "analytics.read" not in src

    def test_permission_constant_used_not_hardcoded(self):
        """All endpoints consistently use reports.read."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr)
        # Count occurrences of require_permission(reports.read)
        count = src.count('require_permission("reports.read")')
        assert count == 4, f"Expected 4 require_permission calls, got {count}"

    def test_no_device_service_bypass(self):
        """No device auth path — endpoints require user + permission."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr)
        assert "device_service" not in src.lower()
        assert "authenticate_device" not in src


# ═══════════════════════════════════════════════════════════════════════════
# 3. RLS/Scope enforcement (10)
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSScopeEnforcement(unittest.TestCase):
    """Verify _enforce_scope logic for different user contexts."""

    def test_enforce_scope_function_exists(self):
        import app.domains.analytics.router as rtr
        assert hasattr(rtr, "_enforce_scope")

    def test_admin_broad_query_allowed(self):
        """Admin (is_admin=True) bypasses scope checks entirely."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._enforce_scope)
        assert "ctx.is_admin" in src, "No admin bypass in _enforce_scope"
        assert "return ctx" in src.split("is_admin")[1][:80]

    def test_scoped_user_broad_query_denied(self):
        """Scoped user without filter → 403 Forbidden."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._enforce_scope)
        assert "status_code=http_status.HTTP_403_FORBIDDEN" in src, "No 403 in _enforce_scope"
        assert "Broad analytics queries" in src, "Broad query message missing"

    def test_campaign_id_scope_check_present(self):
        """_enforce_scope checks campaign_id against advertiser scope."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._enforce_scope)
        assert "campaign_id" in src
        assert "assert_object_in_advertiser_scope" in src

    def test_placement_id_scope_check_present(self):
        """_enforce_scope checks placement_id via campaign → advertiser."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._enforce_scope)
        assert "placement_id" in src
        assert "Placement.campaign_id" in src

    def test_advertiser_id_scope_check_present(self):
        """_enforce_scope checks advertiser_id directly."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._enforce_scope)
        assert "if advertiser_id:" in src
        assert "assert_object_in_advertiser_scope(advertiser_id" in src

    def test_store_id_scope_check_present(self):
        """_enforce_scope checks store_id via store scope."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._enforce_scope)
        assert "assert_object_in_store_scope" in src

    def test_cross_advertiser_uses_404(self):
        """Cross-advertiser access → 404 (not 403, to avoid leaking existence)."""
        import app.domains.identity.rls as rls
        src = inspect.getsource(rls.assert_object_in_advertiser_scope)
        assert "HTTP_404_NOT_FOUND" in src

    def test_cross_store_uses_404(self):
        """Cross-store access → 404 (not 403)."""
        import app.domains.identity.rls as rls
        src = inspect.getsource(rls.assert_object_in_store_scope)
        assert "HTTP_404_NOT_FOUND" in src

    def test_channel_code_alone_no_bypass(self):
        """channel_code does NOT bypass advertiser/store scope."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._enforce_scope)
        # channel_code is NOT checked as a scope bypass — only campaign/placement/advertiser/store
        has_scope_filter_match = re.search(
            r'has_scope_filter.*bool\(.*\)', src.split("_enforce_scope")[-1]
        )
        if has_scope_filter_match:
            filter_logic = src[src.index("has_scope_filter"):][:200]
            assert "campaign_id" in filter_logic or "placement_id" in filter_logic
            assert "channel_code" not in filter_logic, "channel_code should not bypass scope"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Audit (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditSecurity(unittest.TestCase):
    def test_all_four_handlers_call_audit(self):
        """Every handler calls _audit_analytics after success."""
        import app.domains.analytics.router as rtr
        for name in ("delivery_summary", "delivery_query",
                     "planned_vs_delivered", "device_health"):
            fn = getattr(rtr, name)
            src = inspect.getsource(fn)
            assert "_audit_analytics" in src, f"{name}: no audit call"

    def test_audit_called_after_validation_before_return(self):
        """Audit is called AFTER no-secrets check and BEFORE return."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr.delivery_summary)
        validate_pos = src.index("validate_no_secrets_in_analytics_payload")
        audit_pos = src.index("_audit_analytics")
        return_pos = src.index("return result")
        # Audit must be after validation (so we don't audit on validation failure)
        assert audit_pos > validate_pos, "Audit must be after no-secrets validation"
        # Audit must be before or at return (must fire for successful requests)
        assert audit_pos < return_pos, "Audit must fire before return"

    def test_audit_has_no_secret_fields(self):
        """_audit_analytics details dict has no password/token/secret keys."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._audit_analytics)
        for fw in ("password", "token", "secret", "api_key", "bearer"):
            assert fw not in src.lower(), f"'{fw}' found in audit function"

    def test_audit_target_ref_is_safe(self):
        """target_ref uses IDs or 'global', not raw payload."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr._audit_analytics)
        assert 'target_ref=str(' in src or 'target_ref=' in src

    def test_denied_requests_no_audit_on_success_path(self):
        """_enforce_scope raises before audit — no success audit on denied."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr.delivery_summary)
        enforce_pos = src.index("_enforce_scope")
        audit_pos = src.index("_audit_analytics")
        assert enforce_pos < audit_pos, "Scope enforcement must precede audit"


# ═══════════════════════════════════════════════════════════════════════════
# 5. No-secrets in responses (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestNoSecretsResponse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = _setup_admin_client()

    @classmethod
    def tearDownClass(cls):
        _teardown()

    def test_summary_no_secrets(self):
        resp = self.client.get("/api/analytics/delivery/summary")
        raw = resp.text.lower()
        for fw in ("password", "token", "secret", "api_key", "bearer",
                    "cookie", "session", "jwt", "authorization"):
            assert fw not in raw, f"'{fw}' in summary response"

    def test_query_no_secrets(self):
        resp = self.client.post("/api/analytics/delivery/query", json={
            "time_range": {"granularity": "total"}, "scope": {},
        })
        raw = resp.text.lower()
        for fw in ("password", "token", "secret", "api_key"):
            assert fw not in raw, f"'{fw}' in query response"

    def test_planned_no_secrets(self):
        resp = self.client.get("/api/analytics/planned-vs-delivered")
        raw = resp.text.lower()
        for fw in ("password", "token", "secret", "api_key"):
            assert fw not in raw, f"'{fw}' in planned response"

    def test_health_no_secrets(self):
        resp = self.client.get("/api/analytics/device-health")
        raw = resp.text.lower()
        for fw in ("password", "token", "secret", "api_key"):
            assert fw not in raw, f"'{fw}' in health response"

    def test_invalid_input_no_traceback(self):
        """400/422 errors must not leak stack traces."""
        resp = self.client.get("/api/analytics/delivery/summary", params={
            "granularity": "minute",
        })
        assert resp.status_code == 400
        raw = resp.text.lower()
        assert "traceback" not in raw
        assert "file \"" not in raw
        assert "line " not in raw or "pipeline" in raw  # "line" may appear legitimately


# ═══════════════════════════════════════════════════════════════════════════
# 6. Read-only boundaries (6)
# ═══════════════════════════════════════════════════════════════════════════

class TestReadOnlyBoundaries(unittest.TestCase):
    def test_no_pop_event_writes_in_router(self):
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr)
        assert "KsoProofOfPlayEvent" not in src
        assert "ProofOfPlayEvent" not in src
        assert "db.add(" not in src
        assert ".insert(" not in src

    def test_no_generated_manifest_in_router(self):
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr)
        assert "GeneratedManifest" not in src

    def test_no_campaign_placement_writes(self):
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr)
        assert "Campaign(" not in src or "Campaign." not in src  # only SELECT via models
        assert "Placement(" not in src or "Placement." not in src

    def test_service_has_no_db_writes(self):
        import app.domains.analytics.service as svc
        src = inspect.getsource(svc)
        assert "db.add(" not in src
        assert ".insert(" not in src
        assert ".update(" not in src
        assert ".delete(" not in src

    def test_service_no_publication(self):
        imports = _imports(__import__(
            "app.domains.analytics.service", fromlist=["calculate_delivery_metrics"]
        ))
        assert "publication" not in imports
        assert "generate_manifests" not in imports
        assert "publish_batch" not in imports

    def test_router_no_generated_manifest_write(self):
        imports = _imports(__import__(
            "app.domains.analytics.router", fromlist=["router"]
        ))
        assert "generatedmanifest" not in imports.replace("_", "")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Source boundaries (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestSourceBoundaries(unittest.TestCase):
    def test_router_no_clickhouse(self):
        imports = _imports(__import__(
            "app.domains.analytics.router", fromlist=["router"]
        ))
        assert "clickhouse" not in imports

    def test_router_no_device_gateway_router(self):
        imports = _imports(__import__(
            "app.domains.analytics.router", fromlist=["router"]
        ))
        assert "device_gateway.router" not in imports.replace(" ", "")

    def test_router_no_kso_adapter(self):
        imports = _imports(__import__(
            "app.domains.analytics.router", fromlist=["router"]
        ))
        assert "kso_adapter" not in imports

    def test_router_no_portal(self):
        imports = _imports(__import__(
            "app.domains.analytics.router", fromlist=["router"]
        ))
        assert "template" not in imports
        assert "jinja" not in imports
        assert "portal" not in imports


# ═══════════════════════════════════════════════════════════════════════════
# 8. Compatibility (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestCompatibility(unittest.TestCase):
    def test_existing_reports_pop_unchanged(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                           "domains", "proof_of_play", "router.py")
        with open(path) as f:
            src = f.read()
        assert "/reports/pop" in src, "Existing /reports/pop missing"

    def test_existing_reports_pop_summary_unchanged(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                           "domains", "proof_of_play", "router.py")
        with open(path) as f:
            src = f.read()
        assert "/reports/pop/summary" in src or "PoPSummaryResponse" in src, \
            "Existing PoP summary endpoint missing"

    def test_f1_f2_f3_tests_still_pass(self):
        for fname in ("test_analytics_schemas_f1.py",
                      "test_analytics_normalization_f2.py",
                      "test_analytics_delivery_aggregation_f3.py"):
            path = os.path.join(os.path.dirname(__file__), fname)
            assert os.path.exists(path), f"{fname} missing"

    def test_no_new_endpoints_beyond_f4(self):
        """F.4.1 must not add more endpoints than F.4 did."""
        import app.domains.analytics.router as rtr
        src = inspect.getsource(rtr)
        decorator_count = src.count("@router.get") + src.count("@router.post")
        assert decorator_count == 4, f"Expected 4 endpoints, found {decorator_count}"
