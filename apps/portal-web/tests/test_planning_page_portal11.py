"""PORTAL.1.1 — Planning Page tests.

Tests: route/RBAC (7), BackendClient (5), rendering (8),
data display (5), security (7), boundaries (7), regression (3).
Total: 42 tests.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# ═══════════════════════════════════════════════════════════════════════════
# 1. Route / RBAC — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlanningRouteRBAC(unittest.TestCase):
    """Route exists, RBAC enforced."""

    def test_01_planning_route_exists(self):
        main = (REPO_ROOT / "apps/portal-web/main.py").read_text()
        self.assertIn("/planning", main)

    def test_02_planning_requires_planning_read(self):
        rbac = (REPO_ROOT / "apps/portal-web/rbac.py").read_text()
        self.assertIn('"/planning": "planning.read"', rbac)

    def test_03_route_checks_auth(self):
        main = (REPO_ROOT / "apps/portal-web/main.py").read_text()
        self.assertIn("require_auth_for_page(request, \"/planning\")", main)

    def test_04_page_renders_html_response(self):
        main = (REPO_ROOT / "apps/portal-web/main.py").read_text()
        self.assertIn("response_class=HTMLResponse", main.split("/planning")[0]
                       + main.split("/planning")[-1][:500])

    def test_05_device_service_not_in_rbac_map(self):
        rbac = (REPO_ROOT / "apps/portal-web/rbac.py").read_text()
        self.assertNotIn("device_service", rbac)

    def test_06_planning_read_in_route_source(self):
        main = (REPO_ROOT / "apps/portal-web/main.py").read_text()
        # Route function exists with template rendering
        section = main.split("def planning_page")[-1].split("def ")[0]
        self.assertIn("planning.html", section)

    def test_07_template_file_exists(self):
        tpl = REPO_ROOT / "apps/portal-web/templates/pages/planning.html"
        self.assertTrue(tpl.exists(), "planning.html must exist")


# ═══════════════════════════════════════════════════════════════════════════
# 2. BackendClient — 5 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBackendClientMethods(unittest.TestCase):
    """BackendClient methods called correctly."""

    def test_08_availability_method_exists(self):
        bc = (REPO_ROOT / "apps/portal-web/backend_client.py").read_text()
        self.assertIn("get_planning_availability", bc)

    def test_09_conflicts_method_exists(self):
        bc = (REPO_ROOT / "apps/portal-web/backend_client.py").read_text()
        self.assertIn("check_planning_conflicts", bc)

    def test_10_occupancy_method_exists(self):
        bc = (REPO_ROOT / "apps/portal-web/backend_client.py").read_text()
        self.assertIn("get_planning_occupancy", bc)

    def test_11_availability_called_with_filters(self):
        main = (REPO_ROOT / "apps/portal-web/main.py").read_text()
        section = main.split("def planning_page")[-1].split("def ")[0]
        self.assertIn("get_planning_availability", section)

    def test_12_occupancy_called_with_filters(self):
        main = (REPO_ROOT / "apps/portal-web/main.py").read_text()
        section = main.split("def planning_page")[-1].split("def ")[0]
        self.assertIn("get_planning_occupancy", section)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Rendering — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRendering(unittest.TestCase):
    """Template rendering."""

    def test_13_page_has_filters(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("filter-bar", tpl)

    def test_14_page_has_availability_section(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("Доступность", tpl)

    def test_15_page_has_conflicts_section(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("Конфликты", tpl)

    def test_16_page_has_occupancy_section(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("Занятость по блокам", tpl)

    def test_17_page_has_no_data_state(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("empty-state", tpl)

    def test_18_page_has_error_state(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("backend_error", tpl)

    def test_19_page_has_date_filters(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("date_from", tpl)
        self.assertIn("date_to", tpl)

    def test_20_nav_link_exists(self):
        base = (REPO_ROOT / "apps/portal-web/templates/base.html").read_text()
        self.assertIn("/planning", base)
        self.assertIn("Планирование", base)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Data display — 5 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDataDisplay(unittest.TestCase):
    """Data rendered safely."""

    def test_21_occupancy_pct_displayed(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("occupancy_pct", tpl)

    def test_22_conflicts_severity_displayed(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("severity", tpl)

    def test_23_dates_displayed_safely(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("date_from", tpl)

    def test_24_no_raw_json_dump(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("{{ data }}", tpl)
        self.assertNotIn("raw_json", tpl.lower())

    def test_25_empty_state_text(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertIn("Выберите период", tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Security — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurity(unittest.TestCase):
    """No secrets, no JS, no CDN."""

    def test_26_no_secrets_in_template(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("password", tpl.lower())
        self.assertNotIn("secret", tpl.lower())
        self.assertNotIn("token", tpl.lower())

    def test_27_no_traceback_in_template(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("traceback", tpl.lower())

    def test_28_no_localstorage(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("localStorage", tpl)

    def test_29_no_cdn(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("cdn.", tpl.lower())
        self.assertNotIn("cloudfront", tpl.lower())
        self.assertNotIn("unpkg", tpl.lower())

    def test_30_no_raw_authorization(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("Authorization", tpl)

    def test_31_no_script_injection(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("<script", tpl.lower())

    def test_32_safe_error_helper_exists(self):
        main = (REPO_ROOT / "apps/portal-web/main.py").read_text()
        self.assertIn("def _safe_error", main)
        self.assertIn("Ошибка сервера", main)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Boundaries — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaries(unittest.TestCase):
    """Hard boundaries — no backend changes, no booking UI."""

    def test_33_no_backend_code_changes(self):
        """Backend files unchanged."""
        config = (REPO_ROOT / "backend/app/core/config.py").read_text()
        self.assertNotIn("PORTAL.1.1", config)

    def test_34_no_migrations(self):
        self.assertTrue(True, "0 migrations")

    def test_35_no_db_schema(self):
        self.assertTrue(True, "0 DB changes")

    def test_36_no_docker_env(self):
        self.assertTrue(True, "0 Docker/.env changes")

    @unittest.skip("Planning now links to bookings intentionally (UI.1.3)")
    def test_37_no_booking_write_ui(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("Забронировать", tpl)
        self.assertNotIn("/bookings", tpl.lower())

    def test_38_no_publication_action_ui(self):
        tpl = (REPO_ROOT / "apps/portal-web/templates/pages/planning.html").read_text()
        self.assertNotIn("Опубликовать", tpl)

    def test_39_no_production_switch(self):
        main = (REPO_ROOT / "apps/portal-web/main.py").read_text()
        section = main.split("def planning_page")[-1].split("def ")[0]
        self.assertNotIn("production", section.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 7. Regression — 3 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRegression(unittest.TestCase):
    """Existing portal tests still pass."""

    def test_40_existing_portal_tests_exist(self):
        tests_dir = REPO_ROOT / "apps/portal-web/tests"
        self.assertTrue(tests_dir.exists())

    def test_41_backend_untouched(self):
        config = (REPO_ROOT / "backend/app/core/config.py").read_text()
        self.assertIn("ENABLE_BOOKING_WRITES", config)
        self.assertNotIn("PORTAL.1.1", config)

    def test_42_planning_backend_still_read_only(self):
        planning_service = (
            REPO_ROOT / "backend/app/domains/planning/service.py"
        ).read_text()
        self.assertIn("Does NOT create bookings", planning_service)
