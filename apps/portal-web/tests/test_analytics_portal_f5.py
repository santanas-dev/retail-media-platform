"""
F.5 — Portal Analytics Read-Only: targeted tests.

Tests: navigation/visibility (4), BackendClient (5), page rendering (13),
empty/error states (7), security (5), read-only (5), regression (5).
Total: 44 tests.
"""

import os
import re
import unittest


_TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "templates", "pages",
)
_BASE_TEMPLATE = os.path.join(
    os.path.dirname(__file__), "..", "templates", "base.html",
)
_MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "main.py")
_RBAC_PY = os.path.join(os.path.dirname(__file__), "..", "rbac.py")
_BC_PY = os.path.join(os.path.dirname(__file__), "..", "backend_client.py")


def _read(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def _read_main() -> str:
    return _read(_MAIN_PY)


def _read_bc() -> str:
    return _read(_BC_PY)


def _read_rbac() -> str:
    return _read(_RBAC_PY)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Navigation / visibility (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestNavigation(unittest.TestCase):
    def test_analytics_route_exists(self):
        src = _read_main()
        assert "/reports/analytics" in src, "Route /reports/analytics missing"

    def test_nav_link_present(self):
        src = _read(_BASE_TEMPLATE)
        assert "/reports/analytics" in src, "Nav link missing in base.html"
        assert "Аналитика показов" in src, "Nav label missing"

    def test_rbac_mapping_exists(self):
        src = _read_rbac()
        assert '"/reports/analytics": "reports.read"' in src, "RBAC mapping missing"

    def test_active_class_logic(self):
        src = _read(_BASE_TEMPLATE)
        assert "reports-analytics" in src, "active class for reports-analytics missing"


# ═══════════════════════════════════════════════════════════════════════════
# 2. BackendClient (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestBackendClient(unittest.TestCase):
    def test_get_analytics_delivery_summary_exists(self):
        src = _read_bc()
        assert "get_analytics_delivery_summary" in src

    def test_get_analytics_planned_vs_delivered_exists(self):
        src = _read_bc()
        assert "get_analytics_planned_vs_delivered" in src

    def test_get_analytics_device_health_exists(self):
        src = _read_bc()
        assert "get_analytics_device_health" in src

    def test_delivery_summary_correct_endpoint(self):
        src = _read_bc()
        assert "/api/analytics/delivery/summary" in src

    def test_planned_vs_delivered_correct_endpoint(self):
        src = _read_bc()
        assert "/api/analytics/planned-vs-delivered" in src


# ═══════════════════════════════════════════════════════════════════════════
# 3. Page rendering (13)
# ═══════════════════════════════════════════════════════════════════════════

class TestPageRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read(os.path.join(_TEMPLATES_DIR, "reports_analytics.html"))

    def test_page_title(self):
        assert "Аналитика показов" in self.content

    def test_extends_base(self):
        assert "{% extends" in self.content

    def test_summary_block_visible(self):
        assert "Сводка доставки" in self.content

    def test_planned_block_visible(self):
        assert "План / факт" in self.content

    def test_device_health_block_visible(self):
        assert "Здоровье устройств" in self.content

    def test_breakdown_block_visible(self):
        assert "Детализация" in self.content

    def test_campaign_breakdown_table(self):
        assert "Кампании" in self.content

    def test_placement_breakdown_table(self):
        assert "Размещения" in self.content

    def test_store_breakdown_table(self):
        assert "Магазины" in self.content

    def test_device_breakdown_table(self):
        assert "Устройства" in self.content

    def test_channel_breakdown_table(self):
        assert "Каналы" in self.content

    def test_day_breakdown_table(self):
        assert "По дням" in self.content

    def test_filter_form_present(self):
        assert '<form method="get"' in self.content
        assert "name=\"date_from\"" in self.content
        assert "name=\"date_to\"" in self.content


# ═══════════════════════════════════════════════════════════════════════════
# 4. Empty / error states (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestEmptyErrorStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read(os.path.join(_TEMPLATES_DIR, "reports_analytics.html"))
        cls.route_src = _read_main()

    def test_no_data_message(self):
        assert "За выбранный период событий показов нет" in self.content

    def test_no_plan_message_in_template(self):
        assert "Плановые показы пока не рассчитаны" in self.content

    def test_unknown_placement_store_displayed(self):
        assert "Не определено" in self.content

    def test_backend_403_message(self):
        assert "Нет доступа к отчёту" in self.content

    def test_backend_error_message_in_route(self):
        assert "Данные аналитики пока недоступны" in self.route_src

    def test_route_has_backend_403_flag(self):
        assert "backend_403" in self.route_src

    def test_route_has_no_data_flag(self):
        assert "no_data" in self.route_src


# ═══════════════════════════════════════════════════════════════════════════
# 5. Security (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read(os.path.join(_TEMPLATES_DIR, "reports_analytics.html"))

    def test_no_secret_words_in_template(self):
        for fw in ("password", "token", "secret", "api_key", "bearer",
                    "cookie", "session", "jwt", "authorization"):
            assert fw not in self.content.lower(), f"'{fw}' in template"

    def test_no_details_json_in_template(self):
        assert "details_json" not in self.content.lower()

    def test_no_traceback_in_template(self):
        assert "traceback" not in self.content.lower()

    def test_no_cdn_in_template(self):
        for kw in ("cdn.", "unpkg", "jsdelivr", "cloudflare", "localstorage",
                    "sessionstorage", "<script"):
            assert kw not in self.content.lower(), f"'{kw}' in template"

    def test_no_localstorage_in_route(self):
        src = _read_main()
        assert "localStorage" not in src.lower()
        assert "sessionStorage" not in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Read-only (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestReadOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read(os.path.join(_TEMPLATES_DIR, "reports_analytics.html"))

    def test_no_create_button(self):
        for btn in ("Создать", "Добавить", "Новый", "Редактировать"):
            assert btn not in self.content, f"'{btn}' button found"

    def test_no_edit_form(self):
        assert "method=\"post\"" not in self.content.lower()

    def test_no_booking_button(self):
        assert "Забронировать" not in self.content
        assert "booking" not in self.content.lower()

    def test_no_delete_action(self):
        assert "Удалить" not in self.content

    def test_no_direct_db_in_route(self):
        src = _read_main()
        # Portal calls backend API, not DB directly
        analytics_section = src[src.index("/reports/analytics"):][:2000]
        assert "AsyncSession" not in analytics_section
        assert "get_db" not in analytics_section


# ═══════════════════════════════════════════════════════════════════════════
# 7. Regression (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestRegression(unittest.TestCase):
    def test_existing_reports_page_intact(self):
        path = os.path.join(_TEMPLATES_DIR, "reports.html")
        assert os.path.exists(path), "Existing reports template missing"

    def test_existing_campaigns_detail_intact(self):
        path = os.path.join(_TEMPLATES_DIR, "campaigns_detail.html")
        assert os.path.exists(path), "Existing campaign detail template missing"

    def test_backend_api_contract_not_changed(self):
        """Backend analytics router has exactly 4 endpoints — no more."""
        backend_router = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "backend",
            "app", "domains", "analytics", "router.py",
        )
        if os.path.exists(backend_router):
            with open(backend_router) as f:
                src = f.read()
            dec = src.count("@router.get") + src.count("@router.post")
            assert dec == 4, f"Backend endpoint count changed: {dec}"

    def test_no_new_backend_migrations(self):
        import glob
        mg_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "backend",
            "migrations", "versions",
        )
        if os.path.exists(mg_path):
            recent = sorted(glob.glob(os.path.join(mg_path, "*.py")))[-5:]
            for mf in recent:
                with open(mf) as f:
                    content = f.read().lower()
                if "analytics" in content and "portal" in content:
                    assert False, f"Portal analytics migration: {mf}"

    def test_no_clickhouse_in_portal(self):
        src = _read_main()
        assert "clickhouse" not in src.lower()
