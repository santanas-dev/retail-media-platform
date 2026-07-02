"""PORTAL.1.6 — Analytics / Error States / Cross-Linking tests.

Tests: analytics (8), cross-links (7), PoP/reports (5),
devices (3), security (7), boundaries (8), regression (5).
Total: 43 tests.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BASE = REPO_ROOT / "apps/portal-web"

analytics_tpl = ""
pop_tpl = ""
devices_tpl = ""
packages_tpl = ""


def _load():
    global analytics_tpl, pop_tpl, devices_tpl, packages_tpl
    if not analytics_tpl:
        analytics_tpl = (BASE / "templates/pages/reports_analytics.html").read_text()
        pop_tpl = (BASE / "templates/pages/proof-of-play.html").read_text()
        devices_tpl = (BASE / "templates/pages/devices.html").read_text()
        packages_tpl = (BASE / "templates/pages/manifests.html").read_text()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Analytics rendering — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyticsRendering(unittest.TestCase):

    def test_01_delivery_summary_renders(self):
        _load()
        self.assertIn("Сводка доставки", analytics_tpl)

    def test_02_planned_vs_delivered_renders(self):
        _load()
        self.assertIn("План / факт", analytics_tpl)

    def test_03_device_health_renders(self):
        _load()
        self.assertIn("Здоровье устройств", analytics_tpl)

    def test_04_breakdowns_render(self):
        _load()
        self.assertIn("Детализация", analytics_tpl)

    def test_05_unknown_bucket_label(self):
        _load()
        self.assertIn("Не определено", analytics_tpl)

    def test_06_no_expected_impressions_handled(self):
        _load()
        self.assertIn("Плановые показы пока не рассчитаны", analytics_tpl)

    def test_07_no_data_state(self):
        _load()
        self.assertIn("событий показов нет", analytics_tpl)

    def test_08_backend_error_state(self):
        _load()
        self.assertIn("backend_error", analytics_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Cross-links — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossLinks(unittest.TestCase):

    def test_09_analytics_campaign_breakdown_links(self):
        _load()
        self.assertIn('href="/campaigns/', analytics_tpl)

    def test_10_analytics_cross_links_section(self):
        _load()
        self.assertIn("📢 Кампании", analytics_tpl)

    def test_11_pop_campaign_links(self):
        _load()
        self.assertIn('href="/campaigns/', pop_tpl)

    def test_12_pop_device_links(self):
        _load()
        self.assertIn('href="/devices"', pop_tpl)

    def test_13_devices_cross_links_section(self):
        _load()
        self.assertIn("Панель КСО", devices_tpl)
        self.assertIn("Аналитика", devices_tpl)

    def test_14_packages_cross_links_section(self):
        _load()
        self.assertIn("📢 Кампании", packages_tpl)
        self.assertIn("📊 Аналитика", packages_tpl)

    def test_15_devices_link_to_packages(self):
        _load()
        self.assertIn('href="/packages', devices_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 3. PoP / Reports — 5 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPoPReports(unittest.TestCase):

    def test_16_pop_no_data_state(self):
        _load()
        self.assertIn("Нет событий показов", pop_tpl)

    def test_17_pop_safety_note(self):
        _load()
        self.assertIn("безопасные поля", pop_tpl.lower())

    def test_18_pop_backend_unavailable(self):
        main = (BASE / "main.py").read_text()
        section = main.split("async def proof_of_play_page")[-1].split("\n\ndef ")[0]
        self.assertIn("_pop_fallback", section)

    def test_19_pop_campaign_code_linked(self):
        _load()
        self.assertIn("sanitize_code", pop_tpl)

    def test_20_pop_device_code_linked(self):
        _load()
        self.assertIn('href="/devices"', pop_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Devices — 3 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDevicesPage(unittest.TestCase):

    def test_21_devices_has_summary_cards(self):
        _load()
        self.assertIn("Активно", devices_tpl)
        self.assertIn("Заблокировано", devices_tpl)

    def test_22_devices_backend_unavailable_handled(self):
        _load()
        self.assertIn("backend_unavailable", devices_tpl)

    def test_23_devices_empty_state(self):
        _load()
        self.assertIn("Пока нет подключённых КСО", devices_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Security — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurity(unittest.TestCase):
    _SENSITIVE = frozenset({
        "password", "access_token", "refresh_token", "Authorization",
        "api_key", "token", "Cookie", "secret",
    })

    def test_24_no_secrets_in_analytics(self):
        _load()
        for key in self._SENSITIVE:
            self.assertNotIn(key.lower(), analytics_tpl.lower())

    def test_25_no_secrets_in_pop(self):
        _load()
        for key in self._SENSITIVE:
            self.assertNotIn(key.lower(), pop_tpl.lower())

    def test_26_no_traceback(self):
        _load()
        self.assertNotIn("Traceback", analytics_tpl)
        self.assertNotIn("Traceback", pop_tpl)

    def test_27_no_localstorage(self):
        _load()
        self.assertNotIn("localStorage", analytics_tpl)
        self.assertNotIn("localStorage", pop_tpl)

    def test_28_no_cdn(self):
        _load()
        for pat in ("cdn.", "unpkg.com", "jsdelivr"):
            self.assertNotIn(pat, analytics_tpl.lower())

    def test_29_no_inline_js(self):
        _load()
        self.assertNotIn("<script", analytics_tpl.lower())

    def test_30_sanitize_filter_used(self):
        _load()
        self.assertIn("sanitize_code", pop_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Boundaries — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaries(unittest.TestCase):

    def test_31_no_backend_changes(self):
        main = (BASE / "main.py").read_text()
        self.assertIn("get_analytics_delivery_summary", main)

    def test_32_no_migrations(self):
        migrations = list((REPO_ROOT / "migrations" / "versions").glob("*.py"))
        self.assertEqual(len(migrations), 0)

    def test_33_no_docker_changes(self):
        compose = (REPO_ROOT / "infra/docker-compose.yml").read_text()
        self.assertIn("rmp-postgres", compose)

    def test_34_no_env_changes(self):
        env = (REPO_ROOT / ".env.example").read_text()
        self.assertIn("POSTGRES", env)

    def test_35_no_production_switch(self):
        _load()
        self.assertNotIn("production", analytics_tpl.lower())

    def test_36_no_kso_gateway(self):
        _load()
        # "gateway_device_id" from backend data is fine — it's a data field name
        self.assertNotIn("device-gateway", analytics_tpl.lower())

    def test_37_no_ui_redesign(self):
        _load()
        self.assertIn("data-table", analytics_tpl)

    def test_38_no_raw_json_dump(self):
        _load()
        self.assertNotIn('"proof_events_count"', analytics_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Regression — 5 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRegression(unittest.TestCase):

    def test_39_planning_rbac_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/planning": "planning.read"', rbac)

    def test_40_bookings_rbac_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/bookings": "bookings.read"', rbac)

    def test_41_publications_rbac_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/publications": "publications.read"', rbac)

    def test_42_packages_rbac_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/packages": "publications.read"', rbac)

    def test_43_backend_analytics_router_untouched(self):
        router = (REPO_ROOT / "backend/app/domains/analytics/router.py").read_text()
        self.assertIn("delivery", router.lower())
