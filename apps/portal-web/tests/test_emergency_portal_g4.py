"""
G.4 — Emergency Portal Read-Only / Dry-Run Control Page: targeted tests.

Tests: navigation/visibility (4), BackendClient (7), page rendering (11),
buttons/forbidden actions (8), forms (5), result states (7),
security (5), read-only (5), regression (5).
Total: 57 tests.
"""

import os
import glob
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
_EMERGENCY_PAGE = os.path.join(_TEMPLATES_DIR, "emergency.html")


def _read(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def _read_main() -> str:
    return _read(_MAIN_PY)


def _read_bc() -> str:
    return _read(_BC_PY)


def _read_rbac() -> str:
    return _read(_RBAC_PY)


def _read_emergency() -> str:
    return _read(_EMERGENCY_PAGE)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Navigation / visibility (4)
# ═══════════════════════════════════════════════════════════════════════════

class TestNavigation(unittest.TestCase):
    def test_emergency_route_exists(self):
        src = _read_main()
        assert "/emergency" in src, "Route /emergency missing in main.py"

    def test_nav_link_present(self):
        src = _read(_BASE_TEMPLATE)
        assert "/emergency" in src, "Nav link missing in base.html"
        assert "Аварийное управление" in src, "Nav label missing"

    def test_rbac_mapping_exists(self):
        src = _read_rbac()
        assert '"/emergency": "emergency.read"' in src, "RBAC mapping missing"

    def test_active_class_logic(self):
        src = _read(_BASE_TEMPLATE)
        assert 'active == \'emergency\'' in src, "Active class for emergency missing"


# ═══════════════════════════════════════════════════════════════════════════
# 2. BackendClient (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestBackendClient(unittest.TestCase):
    def test_get_emergency_capabilities_exists(self):
        src = _read_bc()
        assert "get_emergency_capabilities" in src

    def test_preview_emergency_action_exists(self):
        src = _read_bc()
        assert "preview_emergency_action" in src

    def test_simulate_emergency_stop_exists(self):
        src = _read_bc()
        assert "simulate_emergency_stop" in src

    def test_simulate_emergency_message_exists(self):
        src = _read_bc()
        assert "simulate_emergency_message" in src

    def test_capabilities_correct_endpoint(self):
        src = _read_bc()
        assert "/api/emergency/capabilities" in src

    def test_preview_correct_endpoint(self):
        src = _read_bc()
        assert "/api/emergency/preview" in src

    def test_simulate_stop_correct_endpoint(self):
        src = _read_bc()
        assert "/api/emergency/simulate-stop" in src


# ═══════════════════════════════════════════════════════════════════════════
# 3. Page rendering (11)
# ═══════════════════════════════════════════════════════════════════════════

class TestPageRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read_emergency()

    def test_page_title(self):
        assert "Аварийное управление" in self.content

    def test_extends_base(self):
        assert "{% extends" in self.content

    def test_dry_run_warning_visible(self):
        assert "Это dry-run" in self.content
        assert "Реальное выполнение отключено" in self.content

    def test_capabilities_block_visible(self):
        assert "Доступные возможности" in self.content

    def test_preview_block_visible(self):
        assert "Предварительный просмотр" in self.content

    def test_simulate_stop_block_visible(self):
        assert "Симуляция остановки" in self.content

    def test_simulate_message_block_visible(self):
        assert "Симуляция экстренного сообщения" in self.content

    def test_result_panel_visible(self):
        assert "Результат" in self.content

    def test_form_has_dry_run_hidden(self):
        """dry_run is forced True — no form field for it."""
        assert 'name="dry_run"' not in self.content, "dry_run form field found"

    def test_backend_403_message(self):
        assert "Нет доступа к аварийному управлению" in self.content

    def test_backend_unavailable_message(self):
        assert "Сервис аварийного управления временно недоступен" in self.content


# ═══════════════════════════════════════════════════════════════════════════
# 4. Buttons / forbidden actions (8)
# ═══════════════════════════════════════════════════════════════════════════

class TestButtons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read_emergency()
        cls.main = _read_main()

    def test_button_proverit_exists(self):
        assert "Проверить" in self.content, "Button 'Проверить' missing"

    def test_button_simulate_stop_exists(self):
        assert "Симулировать остановку" in self.content, "Button 'Симулировать остановку' missing"

    def test_button_simulate_message_exists(self):
        assert "Симулировать сообщение" in self.content, "Button 'Симулировать сообщение' missing"

    def test_no_vypolnit_button(self):
        assert "Выполнить" not in self.content, "Forbidden button 'Выполнить' found"

    def test_no_ostanovit_button(self):
        # "Остановить" may appear in dropdown labels (UI.2.1 localization)
        # but must NOT appear as a button that would execute real actions
        import re
        button_texts = re.findall(r'<button[^>]*>(.*?)</button>', self.content, re.DOTALL)
        for txt in button_texts:
            assert "Остановить" not in txt, f"Forbidden button text 'Остановить' found: {txt}"

    def test_no_activate_button(self):
        assert "Активировать" not in self.content, "Forbidden button 'Активировать' found"

    def test_no_approve_button(self):
        assert "Подтвердить" not in self.content, "Forbidden button 'Подтвердить' found"

    def test_no_primenit_button(self):
        assert "Применить" not in self.content, "Forbidden button 'Применить' found"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Forms (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestForms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read_emergency()
        cls.main = _read_main()

    def test_dry_run_not_toggleable(self):
        """dry_run is never exposed as a form field — always True."""
        assert 'name="dry_run"' not in self.content, "dry_run toggle found in template"

    def test_no_execute_form(self):
        assert 'action="execute"' not in self.content.lower()
        assert 'value="execute"' not in self.content.lower()

    def test_no_activate_form(self):
        assert 'value="activate"' not in self.content.lower()

    def test_no_approve_form(self):
        assert 'value="approve"' not in self.content.lower()

    def test_no_cancel_form(self):
        assert 'value="cancel"' not in self.content.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Result states (7)
# ═══════════════════════════════════════════════════════════════════════════

class TestResultStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read_emergency()
        cls.main = _read_main()

    def test_affected_channels_displayed(self):
        assert "Затронутые каналы" in self.content

    def test_affected_devices_displayed(self):
        assert "Затронутые устройства" in self.content

    def test_affected_campaigns_displayed(self):
        assert "Затронутые кампании" in self.content

    def test_warnings_displayed(self):
        assert "Предупреждения" in self.content

    def test_errors_displayed(self):
        assert "Ошибки" in self.content

    def test_validation_errors_handled(self):
        """Route has validation_errors context variable."""
        assert "validation_errors" in self.main

    def test_backend_403_handled(self):
        """Route has backend_403 flag."""
        assert "backend_403" in self.main


# ═══════════════════════════════════════════════════════════════════════════
# 7. Security (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read_emergency()
        cls.main = _read_main()

    def test_no_secrets_in_template(self):
        for fw in ("password", "token", "secret", "api_key", "bearer",
                    "cookie", "session", "jwt", "authorization"):
            assert fw not in self.content.lower(), f"'{fw}' in template"

    def test_no_traceback_in_template(self):
        assert "traceback" not in self.content.lower()
        assert "stack" not in self.content.lower()

    def test_no_raw_credentials(self):
        for kw in ("access_token=", "refresh_token=", "bearer ", "auth_token",
                    "_token", "\"token\""):
            assert kw not in self.content, f"'{kw}' in template"

    def test_no_cdn_in_template(self):
        for kw in ("cdn.", "unpkg", "jsdelivr", "cloudflare", "localstorage",
                    "sessionstorage", "<script"):
            assert kw not in self.content.lower(), f"'{kw}' in template"

    def test_no_localstorage_in_route(self):
        assert "localStorage" not in self.main.lower()
        assert "sessionStorage" not in self.main.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 8. Read-only (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestReadOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = _read_emergency()
        cls.main = _read_main()

    def test_no_js_in_template(self):
        assert "<script" not in self.content.lower()

    def test_no_direct_db_in_route(self):
        """Portal calls backend API, not DB directly."""
        emergency_section = self.main
        idx = emergency_section.find("/emergency")
        if idx > 0:
            section = emergency_section[max(0, idx - 500):idx + 3000]
            assert "AsyncSession" not in section
            assert "get_db" not in section

    def test_no_campaign_mutation_in_route(self):
        """Route handler doesn't reference campaign write operations."""
        for kw in ("campaign.status", "campaign.archived", "db.add",
                    "db.delete", "session.commit"):
            assert kw not in self.main.lower(), f"'{kw}' in route"

    def test_no_emergency_actions_persisted(self):
        """No emergency_actions table or persistence references in emergency route."""
        # Scope to emergency route handler section only
        idx = self.main.find("/emergency")
        if idx >= 0:
            section = self.main[idx:idx + 3000]
            for kw in ("persist", "create_action", "save_action",
                        "db.add(", "db.insert", "session.commit", "emergency_actions"):
                assert kw not in section.lower(), f"'{kw}' in emergency route"

    def test_no_migration_files_added(self):
        """No new migration files related to emergency/portal."""
        mg_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "backend",
            "migrations", "versions",
        )
        if os.path.exists(mg_path):
            recent = sorted(glob.glob(os.path.join(mg_path, "*.py")))[-3:]
            for mf in recent:
                with open(mf) as f:
                    content = f.read().lower()
                if "emergency" in content and ("portal" in content or "g4" in content):
                    assert False, f"Portal emergency migration: {mf}"


# ═══════════════════════════════════════════════════════════════════════════
# 9. Regression (5)
# ═══════════════════════════════════════════════════════════════════════════

class TestRegression(unittest.TestCase):
    def test_existing_reports_page_intact(self):
        path = os.path.join(_TEMPLATES_DIR, "reports.html")
        assert os.path.exists(path), "Existing reports template missing"

    def test_existing_analytics_page_intact(self):
        path = os.path.join(_TEMPLATES_DIR, "reports_analytics.html")
        assert os.path.exists(path), "Existing analytics template missing"

    def test_existing_campaigns_page_intact(self):
        path = os.path.join(_TEMPLATES_DIR, "campaigns.html")
        assert os.path.exists(path), "Existing campaigns template missing"

    def test_backend_emergency_router_intact(self):
        """Backend emergency router has exactly 4 endpoints — unchanged."""
        backend_router = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "backend",
            "app", "domains", "emergency", "router.py",
        )
        if os.path.exists(backend_router):
            with open(backend_router) as f:
                src = f.read()
            dec = src.count("@router.get") + src.count("@router.post")
            assert dec == 4, f"Backend emergency endpoint count changed: {dec}"

    def test_no_clickhouse_in_portal(self):
        src = _read_main()
        assert "clickhouse" not in src.lower()
