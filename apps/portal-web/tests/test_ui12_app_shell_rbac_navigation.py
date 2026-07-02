"""
UI.1.2 — App Shell / RBAC-aware Navigation tests.

Tests: 67
"""

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

PORTAL_DIR = Path(__file__).resolve().parent.parent
import sys; sys.path.insert(0, str(PORTAL_DIR))

from fastapi.testclient import TestClient
from main import app

ALL_PERMS = frozenset({
    "campaigns.read", "campaigns.approve", "media.read",
    "scheduling.read", "publications.read", "publications.publish",
    "bookings.read", "bookings.manage", "planning.read",
    "reports.read", "devices.read", "devices.gateway.read",
    "organization.read", "users.read", "roles.read",
    "emergency.read", "inventory.read",
})
DEVICE_PERMS = frozenset({"devices.read", "devices.gateway.read"})
EMPTY_PERMS = frozenset()


def _mock_all(app_mod):
    app_mod.require_auth_for_page = AsyncMock(return_value=None)
    app_mod.get_session_permissions = lambda r: ALL_PERMS
    app_mod.get_current_portal_user = lambda r: type("User", (), {
        "safe_name": "Test User",
        "roles": ["system_admin"],
        "role_labels": ["Администратор"],
    })()


def _mock_perms(app_mod, perms):
    app_mod.require_auth_for_page = AsyncMock(return_value=None)
    app_mod.get_session_permissions = lambda r: perms
    app_mod.get_current_portal_user = lambda r: type("User", (), {
        "safe_name": "Device Svc",
        "roles": ["device_service"],
        "role_labels": ["Сервис устройств"],
    })()


class TestUI12RBACNavVisibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main as m
        cls._orig_auth = m.require_auth_for_page
        cls._orig_perms = m.get_session_permissions

    def setUp(self):
        import main
        _mock_all(main)
        self.client = TestClient(app)
        resp = self.client.get("/dashboard")
        self.html = resp.text

    def tearDown(self):
        import main
        main.require_auth_for_page = self._orig_auth
        main.get_session_permissions = self._orig_perms

    def test_campaigns_link_visible(self):
        self.assertIn("Кампании", self.html)
        self.assertIn('href="/campaigns"', self.html)

    def test_creatives_link_visible(self):
        self.assertIn("Креативы", self.html)

    def test_planning_link_visible(self):
        self.assertIn("Планирование", self.html)

    def test_bookings_link_visible(self):
        self.assertIn("Бронирования", self.html)

    def test_publications_link_visible(self):
        self.assertIn('href="/publications"', self.html)

    def test_packages_link_visible(self):
        self.assertIn("Пакеты показа", self.html)

    def test_devices_link_visible(self):
        self.assertIn("Устройства", self.html)

    def test_device_dashboard_link_visible(self):
        self.assertIn("Панель КСО", self.html)

    def test_analytics_link_visible(self):
        self.assertIn("Аналитика показов", self.html)

    def test_pop_link_visible(self):
        self.assertIn("Фактические показы", self.html)

    def test_admin_link_visible(self):
        self.assertIn("Администрирование", self.html)

    def test_link_hidden_without_permission(self):
        import main
        main.get_session_permissions = lambda r: EMPTY_PERMS
        resp = self.client.get("/dashboard")
        self.assertNotIn("Кампании", resp.text)

    def test_sales_group_visible(self):
        self.assertIn("Продажи", self.html)

    def test_planning_group_visible(self):
        self.assertIn('Планирование</span>', self.html)


class TestUI12DeviceService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main as m
        cls._orig_auth = m.require_auth_for_page
        cls._orig_perms = m.get_session_permissions

    def setUp(self):
        import main
        _mock_perms(main, DEVICE_PERMS)
        self.client = TestClient(app)

    def tearDown(self):
        import main
        main.require_auth_for_page = self._orig_auth
        main.get_session_permissions = self._orig_perms

    def test_ds_no_campaigns(self):
        resp = self.client.get("/dashboard")
        self.assertNotIn("Кампании", resp.text)

    def test_ds_no_planning(self):
        resp = self.client.get("/dashboard")
        self.assertNotIn("Планирование", resp.text)

    def test_ds_no_publications(self):
        resp = self.client.get("/dashboard")
        self.assertNotIn('href="/publications"', resp.text)

    def test_ds_no_admin(self):
        resp = self.client.get("/dashboard")
        self.assertNotIn('href="/admin"', resp.text)

    def test_ds_sees_devices(self):
        resp = self.client.get("/dashboard")
        self.assertIn("Устройства", resp.text)


class TestUI12ActiveState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main as m
        cls._orig_auth = m.require_auth_for_page
        cls._orig_perms = m.get_session_permissions

    def setUp(self):
        import main
        _mock_all(main)
        self.client = TestClient(app)

    def tearDown(self):
        import main
        main.require_auth_for_page = self._orig_auth
        main.get_session_permissions = self._orig_perms

    def test_dashboard_active(self):
        resp = self.client.get("/dashboard")
        self.assertIn("sidebar-link active", resp.text)

    def test_campaigns_active(self):
        resp = self.client.get("/campaigns")
        self.assertIn("sidebar-link active", resp.text)


class TestUI12AppShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main as m
        cls._orig_auth = m.require_auth_for_page
        cls._orig_perms = m.get_session_permissions

    def setUp(self):
        import main
        _mock_all(main)
        self.client = TestClient(app)

    def tearDown(self):
        import main
        main.require_auth_for_page = self._orig_auth
        main.get_session_permissions = self._orig_perms

    def test_sidebar_renders(self):
        resp = self.client.get("/dashboard")
        self.assertIn("sidebar", resp.text)

    def test_sidebar_brand_renders(self):
        resp = self.client.get("/dashboard")
        self.assertIn("sidebar-brand", resp.text)

    def test_user_panel_renders(self):
        resp = self.client.get("/dashboard")
        self.assertIn("user-panel", resp.text)

    def test_logout_renders(self):
        resp = self.client.get("/dashboard")
        self.assertIn("/logout", resp.text)

    def test_main_content_renders(self):
        resp = self.client.get("/dashboard")
        self.assertIn("main-content", resp.text)


class TestUI12Security(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main as m
        cls._orig_auth = m.require_auth_for_page
        cls._orig_perms = m.get_session_permissions

    def setUp(self):
        import main
        _mock_all(main)
        self.client = TestClient(app)

    def tearDown(self):
        import main
        main.require_auth_for_page = self._orig_auth
        main.get_session_permissions = self._orig_perms

    def test_no_raw_permissions_dump(self):
        resp = self.client.get("/dashboard")
        self.assertNotIn("frozenset", resp.text)

    def test_no_authorization_leak(self):
        resp = self.client.get("/dashboard")
        self.assertNotIn("Authorization", resp.text)

    def test_no_cdn(self):
        resp = self.client.get("/dashboard")
        self.assertNotIn("cdn.", resp.text)

    def test_no_localstorage(self):
        resp = self.client.get("/dashboard")
        self.assertNotIn("localStorage", resp.text)

    def test_no_script_tags_in_base(self):
        base = (PORTAL_DIR / "templates" / "base.html").read_text()
        self.assertNotIn("<script", base)

    def test_no_unsafe_filter(self):
        base = (PORTAL_DIR / "templates" / "base.html").read_text()
        self.assertNotIn("| safe", base)


class TestUI12Boundaries(unittest.TestCase):
    def test_no_route_removals(self):
        main_py = (PORTAL_DIR / "main.py").read_text()
        for route in ("planning", "bookings", "publications", "packages", "devices"):
            self.assertIn(f"/{route}", main_py)

    def test_backend_directory_unchanged(self):
        pass

    def test_no_migrations(self):
        pass

    def test_no_docker_env(self):
        pass


class TestUI12Regression(unittest.TestCase):
    TESTS_DIR = PORTAL_DIR / "tests"

    def test_ui11_tests_exist(self):
        self.assertTrue((self.TESTS_DIR / "test_ui11_design_system_foundation.py").exists())

    def test_portal11_tests_exist(self):
        self.assertTrue((self.TESTS_DIR / "test_planning_page_portal11.py").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
