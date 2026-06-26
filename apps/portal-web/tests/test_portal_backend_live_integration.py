"""Portal ↔ Backend Live Integration Tests (40.2.2).

Requires: RUN_PORTAL_BACKEND_LIVE_INTEGRATION=1 + running backend + running portal.

Tests backend seed data visibility through portal pages.
Uses real HTTP to portal — no mocks.
"""
import os
import sys
import unittest
import inspect

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_PORTAL_BACKEND_LIVE_INTEGRATION"),
    reason="RUN_PORTAL_BACKEND_LIVE_INTEGRATION=1 required"
)


# ── BackendClient endpoint mapping checks ───────────────────────────

class TestBackendClientEndpointMapping(unittest.TestCase):
    """Verify BackendClient methods use production (not test-kso) endpoints."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from backend_client import BackendClient
        cls._bc = BackendClient

    def _assert_production(self, method, expected_path, forbidden="test-kso"):
        src = inspect.getsource(method)
        self.assertIn(expected_path, src,
            f"{method.__name__}: expected endpoint '{expected_path}' not found")
        self.assertNotIn(forbidden, src,
            f"{method.__name__}: uses '{forbidden}' (should be production)")

    def test_campaigns_list_is_production(self):
        self._assert_production(self._bc.list_campaigns_prod, "/api/campaigns")

    def test_approvals_list_is_production(self):
        self._assert_production(self._bc.list_approvals_prod, "/api/approvals")

    def test_pop_report_is_production(self):
        self._assert_production(self._bc.get_pop_report, "/api/reports/pop")

    def test_pop_summary_is_production(self):
        self._assert_production(self._bc.get_pop_summary, "/api/reports/pop/summary")

    def test_manifests_is_production(self):
        self._assert_production(self._bc.list_manifests, "/api/manifests")

    def test_schedules_is_production(self):
        self._assert_production(self._bc.list_schedules, "/api/schedules")

    def test_creatives_is_production(self):
        self._assert_production(self._bc.list_creatives, "/api/creatives")

    def test_device_dashboard_is_production(self):
        self._assert_production(self._bc.get_device_dashboard, "/api/device-dashboard")

    def test_branches_is_production(self):
        self._assert_production(self._bc.list_branches, "/api/branches")

    def test_stores_is_production(self):
        self._assert_production(self._bc.list_stores, "/api/stores")

    def test_kso_devices_is_production(self):
        src = inspect.getsource(self._bc.list_kso_devices)
        self.assertIn("/api/devices/kso", src)
        self.assertNotIn("test-kso", src)

    def test_admin_methods_are_production(self):
        for method in (self._bc.list_users, self._bc.list_roles,
                       self._bc.list_permissions, self._bc.list_admin_audit):
            src = inspect.getsource(method)
            self.assertNotIn("test-kso", src,
                f"{method.__name__} uses test-kso!")


# ── PAGE_PERMISSION_MAP consistency ────────────────────────────────

class TestPermissionMapConsistency(unittest.TestCase):
    """PAGE_PERMISSION_MAP must only use permissions from backend seed."""

    @classmethod
    def setUpClass(cls):
        _backend = os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")
        if _backend not in sys.path:
            sys.path.insert(0, _backend)
        from app.domains.identity.seed import PERMISSIONS, ROLE_PERMISSIONS
        cls.all_perms = {p[0] for p in PERMISSIONS}
        cls.role_perms = ROLE_PERMISSIONS

    def setUp(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from rbac import PAGE_PERMISSION_MAP
        self.page_map = PAGE_PERMISSION_MAP

    def test_all_page_permissions_exist_in_seed(self):
        for route, perm in self.page_map.items():
            self.assertIn(perm, self.all_perms,
                f"PAGE_PERMISSION_MAP[{route}]='{perm}' NOT in backend PERMISSIONS")

    def test_system_admin_has_all_page_permissions(self):
        sys_perms = set(self.role_perms.get("system_admin", []))
        for route, perm in self.page_map.items():
            self.assertIn(perm, sys_perms,
                f"system_admin missing '{perm}' for {route}")

    def test_security_admin_has_security_permissions(self):
        """security_admin must have audit, users, roles, device gateway, reports."""
        sec_perms = set(self.role_perms.get("security_admin", []))
        required = {"audit.read", "users.read", "users.manage", "roles.read",
                     "roles.manage", "devices.gateway.read", "publications.read",
                     "campaigns.read", "campaign_reports.read", "organization.read",
                     "permissions.read"}
        missing = required - sec_perms
        self.assertFalse(missing, f"security_admin missing: {missing}")

    def test_approvals_requires_campaigns_approve(self):
        self.assertEqual(self.page_map.get("/approvals"), "campaigns.approve")

    def test_admin_requires_users_read(self):
        self.assertEqual(self.page_map.get("/admin"), "users.read")

    def test_device_dashboard_requires_gateway_read(self):
        self.assertEqual(self.page_map.get("/device-dashboard"), "devices.gateway.read")

    def test_readiness_requires_gateway_read(self):
        self.assertEqual(self.page_map.get("/readiness"), "devices.gateway.read")

    def test_creatives_requires_media_read(self):
        self.assertEqual(self.page_map.get("/creatives"), "media.read")


# ── Portal page live integration (requires running portal) ──────────

class TestPortalBackendLiveIntegration(unittest.TestCase):
    """End-to-end: admin can access all protected portal pages via real HTTP.

    Requires RUN_PORTAL_BACKEND_LIVE_INTEGRATION=1 AND running portal.
    """

    PORTAL = os.environ.get("PORTAL_LIVE_URL", "http://127.0.0.1:8422")

    @classmethod
    def setUpClass(cls):
        import subprocess, urllib.request, urllib.parse, http.cookiejar

        # Read admin password from backend .env via subprocess
        _backend = os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")
        env_path = os.path.join(_backend, ".env")
        if not os.path.exists(env_path):
            raise unittest.SkipTest("backend/.env not found")
        result = subprocess.run(
            ["bash", "-c",
             "grep '^INITIAL_ADMIN_PASSWORD=*** '" + env_path + "' | cut -d= -f2-"],
            capture_output=True, text=True
        )
        password = result.stdout.strip()
        if not password:
            raise unittest.SkipTest("Cannot read admin password")

        # Login via portal
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        data = urllib.parse.urlencode({"username": "admin", "password": password}).encode()
        try:
            resp = opener.open(urllib.request.Request(
                cls.PORTAL + "/login", data=data, method="POST"
            ), timeout=15)
        except Exception as e:
            raise unittest.SkipTest("Cannot reach portal: " + str(e))

        if resp.status not in (200, 302, 303):
            raise unittest.SkipTest("Portal login failed: " + str(resp.status))

        cls._opener = opener

    def _get(self, path):
        try:
            resp = self._opener.open(self.PORTAL + path, timeout=15)
            return resp.status, resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return None, str(e)

    def test_admin_accesses_dashboard(self):
        status, body = self._get("/dashboard")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_admin_page(self):
        status, body = self._get("/admin")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_device_dashboard(self):
        status, body = self._get("/device-dashboard")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_reports(self):
        status, body = self._get("/reports")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_campaigns(self):
        status, body = self._get("/campaigns")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_creatives(self):
        status, body = self._get("/creatives")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_approvals(self):
        status, body = self._get("/approvals")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_schedule(self):
        status, body = self._get("/schedule")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_publications(self):
        status, body = self._get("/publications")
        self.assertEqual(status, 200, "Got " + str(status))

    def test_admin_accesses_readiness(self):
        status, body = self._get("/readiness")
        self.assertEqual(status, 200, "Got " + str(status))

    # ── Safety ──────────────────────────────────────────────────

    def test_no_secrets_in_html(self):
        for path in ["/dashboard", "/admin", "/reports", "/device-dashboard"]:
            status, body = self._get(path)
            if status != 200:
                continue
            lower = body.lower()
            for fb in ("access_token", "refresh_token", "bearer ",
                        "password_hash", "token_hash", "device_secret",
                        "authorization:", "backend_url"):
                self.assertNotIn(fb, lower,
                    "FORBIDDEN '" + fb + "' found in " + path)

    def test_no_js_cdn_in_html(self):
        for path in ["/dashboard", "/admin", "/reports"]:
            status, body = self._get(path)
            if status != 200:
                continue
            lower = body.lower()
            self.assertNotIn("cdn.", lower, "CDN found in " + path)
            self.assertNotIn("localstorage", lower, "localStorage found in " + path)


if __name__ == "__main__":
    unittest.main()
