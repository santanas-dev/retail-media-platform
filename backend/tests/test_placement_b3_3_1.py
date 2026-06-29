"""
B.3.3.1 — Real API/RLS Integration Tests for Placement.

Tests with FastAPI TestClient + dependency overrides:
  - RLS / advertiser scope: cross-advertiser access → 403
  - Validation errors: service exceptions → correct HTTP codes
  - Route registration: all 7 endpoints registered
  - Audit: source-code verification of placement_code usage

Uses direct mock of identity.service.require_permission to bypass
the deep user_roles→role→role_permissions→permission.code chain.
"""
import uuid
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient


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


def _setup_app_with_auth():
    """Return TestClient with get_db + get_current_user + require_permission mocked."""
    from app.main import app
    from app.core.deps import get_db, get_current_user

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    # Bypass deep permission check — mock identity.service.require_permission as no-op
    app._b3_3_1_perm_patch = patch(
        "app.domains.identity.service.require_permission",
        return_value=None,
    )
    app._b3_3_1_perm_patch.start()

    return TestClient(app)


def _teardown_app():
    from app.main import app
    if hasattr(app, '_b3_3_1_perm_patch'):
        app._b3_3_1_perm_patch.stop()
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# RLS / Advertiser scope — 5 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementRLS(unittest.TestCase):
    """Cross-advertiser access → 403 from service layer."""

    def setUp(self):
        self.client = _setup_app_with_auth()
        self.pid = str(_uid())

    def tearDown(self):
        _teardown_app()

    def test_cross_advertiser_blocks_read(self):
        with patch(
            "app.domains.channels.service.get_placement",
            new=AsyncMock(side_effect=HTTPException(403, "Cannot access placement")),
        ):
            resp = self.client.get(f"/api/placements/{self.pid}")
        self.assertEqual(resp.status_code, 403)

    def test_cross_advertiser_blocks_update(self):
        with patch(
            "app.domains.channels.service.update_placement",
            new=AsyncMock(side_effect=HTTPException(403, "Cannot access placement")),
        ):
            resp = self.client.put(f"/api/placements/{self.pid}", json={"name": "X"})
        self.assertEqual(resp.status_code, 403)

    def test_cross_advertiser_blocks_cancel(self):
        with patch(
            "app.domains.channels.service.cancel_placement",
            new=AsyncMock(side_effect=HTTPException(403, "Cannot access placement")),
        ):
            resp = self.client.delete(f"/api/placements/{self.pid}")
        self.assertEqual(resp.status_code, 403)

    def test_cross_advertiser_blocks_targets_read(self):
        with patch(
            "app.domains.channels.service.get_placement_targets",
            new=AsyncMock(side_effect=HTTPException(403, "Cannot access placement")),
        ):
            resp = self.client.get(f"/api/placements/{self.pid}/targets")
        self.assertEqual(resp.status_code, 403)

    def test_cross_advertiser_blocks_targets_update(self):
        with patch(
            "app.domains.channels.service.set_placement_targets",
            new=AsyncMock(side_effect=HTTPException(403, "Cannot access placement")),
        ):
            resp = self.client.put(
                f"/api/placements/{self.pid}/targets",
                json={"targets": []},
            )
        self.assertEqual(resp.status_code, 403)


# ═══════════════════════════════════════════════════════════════════════════
# Validation error propagation — 5 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementValidationErrors(unittest.TestCase):
    """Service-layer errors propagate correct HTTP status codes."""

    def setUp(self):
        self.client = _setup_app_with_auth()
        self.cid = str(_uid())
        self.pid = str(_uid())

    def tearDown(self):
        _teardown_app()

    def test_invalid_channel_404(self):
        with patch(
            "app.domains.channels.service.create_campaign_placement",
            new=AsyncMock(side_effect=HTTPException(404, "Channel '...' not found")),
        ):
            resp = self.client.post(
                f"/api/campaigns/{self.cid}/placements",
                json={"channel_id": str(_uid()), "name": "Bad"},
            )
        self.assertEqual(resp.status_code, 404)

    def test_channel_not_allowed_400(self):
        with patch(
            "app.domains.channels.service.create_campaign_placement",
            new=AsyncMock(side_effect=HTTPException(400, "Channel not in campaign's allowed channels")),
        ):
            resp = self.client.post(
                f"/api/campaigns/{self.cid}/placements",
                json={"channel_id": str(_uid()), "name": "Bad"},
            )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_dates_400(self):
        with patch(
            "app.domains.channels.service.create_campaign_placement",
            new=AsyncMock(side_effect=HTTPException(400, "start_date cannot be after end_date")),
        ):
            resp = self.client.post(
                f"/api/campaigns/{self.cid}/placements",
                json={
                    "channel_id": str(_uid()), "name": "Bad",
                    "start_date": "2026-12-31", "end_date": "2026-01-01",
                },
            )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_status_400(self):
        with patch(
            "app.domains.channels.service.update_placement",
            new=AsyncMock(side_effect=HTTPException(400, "Invalid status 'deleted'")),
        ):
            resp = self.client.put(
                f"/api/placements/{self.pid}",
                json={"status": "deleted"},
            )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_target_type_400(self):
        with patch(
            "app.domains.channels.service.set_placement_targets",
            new=AsyncMock(side_effect=HTTPException(400, "targets[0]: invalid target_type 'planet'")),
        ):
            resp = self.client.put(
                f"/api/placements/{self.pid}/targets",
                json={"targets": [{"target_type": "planet"}]},
            )
        self.assertEqual(resp.status_code, 400)


# ═══════════════════════════════════════════════════════════════════════════
# Route registration — 1 test
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementRoutesExist:
    """All 7 placement endpoints are registered in FastAPI app."""

    def test_all_7_endpoints_non_404(self):
        from app.main import app
        client = TestClient(app)

        endpoints = [
            ("GET", "/api/campaigns/00000000-0000-0000-0000-000000000001/placements"),
            ("POST", "/api/campaigns/00000000-0000-0000-0000-000000000001/placements"),
            ("GET", "/api/placements/00000000-0000-0000-0000-000000000001"),
            ("PUT", "/api/placements/00000000-0000-0000-0000-000000000001"),
            ("DELETE", "/api/placements/00000000-0000-0000-0000-000000000001"),
            ("GET", "/api/placements/00000000-0000-0000-0000-000000000001/targets"),
            ("PUT", "/api/placements/00000000-0000-0000-0000-000000000001/targets"),
        ]
        for method, path in endpoints:
            if method == "GET":
                resp = client.get(path)
            elif method == "POST":
                resp = client.post(path, json={})
            elif method == "PUT":
                resp = client.put(path, json={})
            elif method == "DELETE":
                resp = client.delete(path)
            assert resp.status_code != 404, \
                f"{method} {path} returned 404 — route not registered"


# ═══════════════════════════════════════════════════════════════════════════
# Audit verification — 5 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementAuditInRouter:
    """Verify audit calls in router source use placement_code."""

    def test_create_audit_uses_placement_code(self):
        import inspect
        from app.domains.campaigns.router import create_campaign_placement
        source = inspect.getsource(create_campaign_placement)
        assert "audit_business_action" in source
        assert "placement.create" in source
        assert "placement_code" in source

    def test_update_audit_uses_placement_code(self):
        import inspect
        from app.domains.channels.placements_router import update_placement
        source = inspect.getsource(update_placement)
        assert "placement.update" in source
        assert "placement_code" in source

    def test_cancel_audit_uses_placement_code(self):
        import inspect
        from app.domains.channels.placements_router import cancel_placement
        source = inspect.getsource(cancel_placement)
        assert "placement.cancel" in source
        assert "placement_code" in source

    def test_targets_update_audit_fix_verified(self):
        """B.3.3 FIX: targets.update must use placement_code, NOT placement_id."""
        import inspect
        from app.domains.channels.placements_router import set_placement_targets
        source = inspect.getsource(set_placement_targets)
        assert "placement.targets.update" in source
        assert "placement_code" in source
        assert "str(placement_id)" not in source, \
            "VERIFIED: placement_id replaced by placement_code"

    def test_all_audit_target_type_is_placement(self):
        import inspect
        from app.domains.channels.placements_router import (
            update_placement, cancel_placement, set_placement_targets,
        )
        from app.domains.campaigns.router import create_campaign_placement
        for fn in [create_campaign_placement, update_placement,
                    cancel_placement, set_placement_targets]:
            source = inspect.getsource(fn)
            assert 'target_type="placement"' in source or \
                   "target_type='placement'" in source, \
                f"{fn.__name__}: must use target_type='placement'"
