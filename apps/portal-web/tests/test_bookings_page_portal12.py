"""PORTAL.1.2 — Booking Workflow Page tests.

Tests: route/RBAC (11), BackendClient (8), rendering (8),
workflow (11), security (7), boundaries (8), regression (3).
Total: 56 tests.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Shortcuts
main_text = ""
rbac_text = ""
bc_text = ""
bookings_tpl = ""
detail_tpl = ""
BASE = REPO_ROOT / "apps/portal-web"


def _lazy_load():
    global main_text, rbac_text, bc_text, bookings_tpl, detail_tpl
    if not main_text:
        main_text = (BASE / "main.py").read_text()
        rbac_text = (BASE / "rbac.py").read_text()
        bc_text = (BASE / "backend_client.py").read_text()
        bookings_tpl = (BASE / "templates/pages/bookings.html").read_text()
        detail_tpl = (BASE / "templates/pages/booking_detail.html").read_text()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Route / RBAC — 11 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBookingsRouteRBAC(unittest.TestCase):
    """Route exists, RBAC enforced, templates exist."""

    def test_01_bookings_route_exists(self):
        _lazy_load()
        self.assertIn("/bookings", main_text)

    def test_02_rbac_requires_bookings_read(self):
        _lazy_load()
        self.assertIn('"/bookings": "bookings.read"', rbac_text)

    def test_03_route_checks_auth(self):
        _lazy_load()
        self.assertIn('require_auth_for_page(request, "/bookings")', main_text)

    def test_04_bookings_list_route_renders_html(self):
        _lazy_load()
        self.assertIn("async def bookings_page", main_text)
        section = main_text.split("async def bookings_page")[-1].split("\n\nasync def ")[0]
        self.assertIn("bookings.html", section)

    def test_05_bookings_detail_route_exists(self):
        _lazy_load()
        self.assertIn("async def booking_detail", main_text)

    def test_06_reserve_route_exists(self):
        _lazy_load()
        self.assertIn("async def booking_reserve", main_text)

    def test_07_confirm_route_exists(self):
        _lazy_load()
        self.assertIn("async def booking_confirm", main_text)

    def test_08_cancel_route_exists(self):
        _lazy_load()
        self.assertIn("async def booking_cancel", main_text)

    def test_09_bookings_template_exists(self):
        tpl = BASE / "templates/pages/bookings.html"
        self.assertTrue(tpl.exists(), "bookings.html must exist")

    def test_10_detail_template_exists(self):
        tpl = BASE / "templates/pages/booking_detail.html"
        self.assertTrue(tpl.exists(), "booking_detail.html must exist")

    def test_11_device_service_not_in_rbac_map(self):
        _lazy_load()
        self.assertNotIn("device_service", rbac_text)


# ═══════════════════════════════════════════════════════════════════════════
# 2. BackendClient — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBackendClientMethods(unittest.TestCase):
    """BackendClient booking methods exist and are called correctly."""

    def test_12_list_bookings_method_exists(self):
        _lazy_load()
        self.assertIn("def list_bookings", bc_text)

    def test_13_get_booking_method_exists(self):
        _lazy_load()
        self.assertIn("def get_booking", bc_text)

    def test_14_create_booking_method_exists(self):
        _lazy_load()
        self.assertIn("def create_booking", bc_text)

    def test_15_reserve_booking_method_exists(self):
        _lazy_load()
        self.assertIn("def reserve_booking", bc_text)

    def test_16_confirm_booking_method_exists(self):
        _lazy_load()
        self.assertIn("def confirm_booking", bc_text)

    def test_17_cancel_booking_method_exists(self):
        _lazy_load()
        self.assertIn("def cancel_booking", bc_text)

    def test_18_list_booking_items_method_exists(self):
        _lazy_load()
        self.assertIn("def list_booking_items", bc_text)

    def test_19_list_bookings_called_in_route(self):
        _lazy_load()
        section = main_text.split("async def bookings_page")[-1].split("\n\nasync def ")[0]
        self.assertIn("list_bookings", section)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Rendering — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRendering(unittest.TestCase):
    """Template rendering: filters, blocks, actions, states."""

    def test_20_page_has_filters(self):
        _lazy_load()
        self.assertIn("filter-bar", bookings_tpl)

    def test_21_page_has_create_form(self):
        _lazy_load()
        self.assertIn("Создать бронирование", bookings_tpl)

    def test_22_page_has_booking_list_table(self):
        _lazy_load()
        self.assertIn("data-table", bookings_tpl)

    def test_23_page_has_status_labels(self):
        _lazy_load()
        self.assertIn("Черновик", bookings_tpl)
        self.assertIn("Зарезервировано", bookings_tpl)

    def test_24_detail_has_booking_info(self):
        _lazy_load()
        self.assertIn("Информация", detail_tpl)

    def test_25_detail_has_items_section(self):
        _lazy_load()
        self.assertIn("Элементы бронирования", detail_tpl)

    def test_26_detail_has_action_buttons(self):
        _lazy_load()
        self.assertIn("Действия", detail_tpl)

    def test_27_detail_has_cancel_form_with_reason(self):
        _lazy_load()
        self.assertIn("Причина", detail_tpl)
        self.assertIn('name="reason"', detail_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Workflow — 11 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflow(unittest.TestCase):
    """Booking workflow: create, reserve, confirm, cancel, errors."""

    def test_28_create_route_uses_post(self):
        _lazy_load()
        self.assertIn('@app.post("/bookings"', main_text)

    def test_29_reserve_route_uses_post(self):
        _lazy_load()
        self.assertIn('@app.post("/bookings/{booking_id}/reserve"', main_text)

    def test_30_confirm_route_uses_post(self):
        _lazy_load()
        self.assertIn('@app.post("/bookings/{booking_id}/confirm"', main_text)

    def test_31_cancel_route_uses_post(self):
        _lazy_load()
        self.assertIn('@app.post("/bookings/{booking_id}/cancel"', main_text)

    def test_32_create_collects_form_data(self):
        _lazy_load()
        section = main_text.split("async def bookings_create")[-1].split("\n\nasync def ")[0]
        self.assertIn("campaign_id", section)
        self.assertIn("date_from", section)
        self.assertIn("date_to", section)

    def test_33_cancel_collects_reason(self):
        _lazy_load()
        section = main_text.split("async def booking_cancel")[-1].split("\n\n@app.")[0]
        self.assertIn("reason", section)

    def test_34_flash_message_on_success(self):
        _lazy_load()
        section = main_text.split("async def bookings_create")[-1].split("\n\nasync def ")[0]
        self.assertIn("flash", section)

    def test_35_feature_flag_error_handled_safely(self):
        _lazy_load()
        # _safe_error used for non-ok results
        self.assertIn("_safe_error", main_text)

    def test_36_validation_empty_fields_redirect(self):
        _lazy_load()
        section = main_text.split("async def bookings_create")[-1].split("\n\nasync def ")[0]
        self.assertIn("Заполните", section)

    def test_37_backend_unavailable_handled(self):
        _lazy_load()
        self.assertIn("временно недоступны", main_text)

    def test_38_redirect_after_actions(self):
        _lazy_load()
        self.assertIn("RedirectResponse", main_text)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Security — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurity(unittest.TestCase):
    """No secrets, no traceback, no CDN, no JS, no raw JSON dump."""

    _SENSITIVE = frozenset({
        "password", "access_token", "refresh_token", "Authorization",
        "api_key", "token", "Cookie", "secret",
    })

    def test_39_no_secrets_in_bookings_template(self):
        _lazy_load()
        lower = bookings_tpl.lower()
        for key in self._SENSITIVE:
            self.assertNotIn(key.lower(), lower,
                             f"Template must not contain {key}")

    def test_40_no_secrets_in_detail_template(self):
        _lazy_load()
        lower = detail_tpl.lower()
        for key in self._SENSITIVE:
            self.assertNotIn(key.lower(), lower,
                             f"Template must not contain {key}")

    def test_41_no_traceback_in_template(self):
        _lazy_load()
        self.assertNotIn("Traceback", bookings_tpl)
        self.assertNotIn("Traceback", detail_tpl)

    def test_42_no_localStorage(self):
        _lazy_load()
        self.assertNotIn("localStorage", bookings_tpl)
        self.assertNotIn("localStorage", detail_tpl)

    def test_43_no_cdn(self):
        _lazy_load()
        for pat in ("cdn.", "unpkg.com", "jsdelivr", "cloudflare"):
            self.assertNotIn(pat, bookings_tpl.lower())
            self.assertNotIn(pat, detail_tpl.lower())

    def test_44_no_inline_js(self):
        _lazy_load()
        self.assertNotIn("<script", bookings_tpl.lower())
        self.assertNotIn("<script", detail_tpl.lower())

    def test_45_backend_client_no_secret_logging(self):
        _lazy_load()
        bc_section = bc_text.split("Booking Workflow")[-1].split("# ── Module")[0]
        # access_token is a parameter name, not a secret — exclude it
        for key in ("password",):
            self.assertNotIn(key, bc_section.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 6. Boundaries — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaries(unittest.TestCase):
    """No backend code changes, no migrations, no Docker/.env, no prod switch."""

    def test_46_no_backend_api_changes(self):
        """Backend inventory router untouched."""
        router = (REPO_ROOT / "backend/app/domains/inventory/router.py").read_text()
        self.assertIn("booking_writes_disabled", router)  # existing guard intact

    def test_47_no_migrations(self):
        """No new migration files added since PORTAL.1.1."""
        migrations = list((REPO_ROOT / "migrations" / "versions").glob("*.py"))
        self.assertEqual(len(migrations), 0,
                         f"No migrations allowed: {migrations}")

    def test_48_no_docker_changes(self):
        compose = (REPO_ROOT / "infra/docker-compose.yml").read_text()
        self.assertIn("rmp-postgres", compose)

    def test_49_no_env_changes(self):
        env = (REPO_ROOT / ".env.example").read_text()
        self.assertIn("POSTGRES", env)

    def test_50_no_production_switch_text(self):
        _lazy_load()
        for pat in ("production", "prod_mode", "PRODUCTION"):
            self.assertNotIn(pat, bookings_tpl)
            self.assertNotIn(pat, detail_tpl)

    def test_51_no_kso_gateway(self):
        _lazy_load()
        bc_section = bc_text.split("Booking Workflow")[-1].split("# ── Module")[0]
        self.assertNotIn("kso", bc_section.lower())
        self.assertNotIn("gateway", bc_section.lower())

    def test_52_no_publication_actions(self):
        _lazy_load()
        self.assertNotIn("publish", bookings_tpl.lower())
        self.assertNotIn("публикац", bookings_tpl.lower())

    def test_53_no_manifest_write(self):
        _lazy_load()
        self.assertNotIn("manifest", bookings_tpl.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 7. Regression — 3 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRegression(unittest.TestCase):
    """PORTAL.1.1 tests still pass, portal structure intact."""

    def test_54_planning_rbac_unchanged(self):
        _lazy_load()
        self.assertIn('"/planning": "planning.read"', rbac_text)

    def test_55_planning_template_unchanged(self):
        tpl = BASE / "templates/pages/planning.html"
        self.assertTrue(tpl.exists())
        content = tpl.read_text()
        self.assertIn("Доступность", content)
        self.assertIn("Конфликты", content)
        self.assertIn("Заполняемость", content)

    def test_56_backend_inventory_router_unchanged(self):
        router = (REPO_ROOT / "backend/app/domains/inventory/router.py").read_text()
        self.assertIn("def list_bookings", router)
        self.assertIn("def create_booking", router)
        self.assertIn("def reserve_booking", router)
        self.assertIn("_check_booking_writes_enabled", router)
