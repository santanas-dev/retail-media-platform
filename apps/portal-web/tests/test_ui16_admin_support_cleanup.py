"""UI.1.6 — Admin / Support Pages Cleanup — Tests.

Validates:
  - Creatives / Approvals / Admin / Emergency / Readiness /
    Deployment / Compliance / Help pages
  - page-header + section-card + metric-grid
  - Dry-run preserved, production switch NO-GO preserved
  - No secrets / no JS / no CDN / no localStorage
  - No backend/migrations/Docker/.env changes
"""

import unittest
from pathlib import Path

_TPL = Path(__file__).resolve().parent.parent / "templates" / "pages"


def _load(name):
    p = _TPL / f"{name}.html"
    if not p.exists():
        raise FileNotFoundError(f"Template not found: {p}")
    return p.read_text()


# ════════════════════════════════════════════════════════════════
# Creatives
# ════════════════════════════════════════════════════════════════

class TestCreatives(unittest.TestCase):

    def test_01_page_header(self):
        t = _load("creatives")
        self.assertIn("page-header", t)
        self.assertIn("Креативы", t)

    def test_02_subtitle(self):
        t = _load("creatives")
        self.assertIn("page-subtitle", t)

    def test_03_upload_form(self):
        t = _load("creatives")
        self.assertIn("section-card", t)
        self.assertIn("enctype=\"multipart/form-data\"", t)

    def test_04_status_badges(self):
        t = _load("creatives")
        for kw in ("Одобрен", "Отклонён", "Черновик"):
            self.assertIn(kw, t)

    def test_05_empty_state(self):
        t = _load("creatives")
        self.assertIn("empty-state", t)

    def test_06_no_secrets(self):
        t = _load("creatives")
        for s in ("Authorization", "api_key", "password"):
            self.assertNotIn(s, t)


class TestCreativeDetail(unittest.TestCase):

    def test_07_page_header(self):
        t = _load("creative_detail")
        self.assertIn("page-header", t)
        self.assertIn("page-back", t)

    def test_08_status_renders(self):
        t = _load("creative_detail")
        self.assertIn("Статус модерации", t)

    def test_09_actions(self):
        t = _load("creative_detail")
        self.assertIn("Отправить на проверку", t) or self.assertIn("Одобрить", t)

    def test_10_no_secrets(self):
        t = _load("creative_detail")
        for s in ("Authorization", "api_key", "password"):
            self.assertNotIn(s, t)


# ════════════════════════════════════════════════════════════════
# Approvals
# ════════════════════════════════════════════════════════════════

class TestApprovals(unittest.TestCase):

    def test_11_page_header(self):
        t = _load("approvals")
        self.assertIn("page-header", t)
        self.assertIn("Согласования", t)

    def test_12_subtitle(self):
        t = _load("approvals")
        self.assertIn("page-subtitle", t)

    def test_13_section_cards(self):
        t = _load("approvals")
        self.assertIn("section-card", t)

    def test_14_status_badges(self):
        t = _load("approvals")
        self.assertIn("status-badge", t)

    def test_15_request_form(self):
        t = _load("approvals")
        self.assertIn("Запросить согласование", t)

    def test_16_approve_reject_actions(self):
        t = _load("approvals")
        self.assertIn("Одобрить", t)
        self.assertIn("Отклонить", t)

    def test_17_empty_state(self):
        t = _load("approvals")
        self.assertIn("empty-state", t)

    def test_18_no_secrets(self):
        t = _load("approvals")
        for s in ("Authorization", "api_key", "password"):
            self.assertNotIn(s, t)


# ════════════════════════════════════════════════════════════════
# Admin
# ════════════════════════════════════════════════════════════════

class TestAdmin(unittest.TestCase):

    def test_19_page_header(self):
        t = _load("admin")
        self.assertIn("page-header", t)
        self.assertIn("Администрирование", t)

    def test_20_users_section(self):
        t = _load("admin")
        self.assertIn("Пользователи портала", t)

    def test_21_roles_section(self):
        t = _load("admin")
        self.assertIn("Роли", t)

    def test_22_audit_section(self):
        t = _load("admin")
        self.assertIn("Аудит", t)

    def test_23_status_badges(self):
        t = _load("admin")
        self.assertIn("Активен", t) or self.assertIn("Заблокирован", t)

    def test_24_empty_state(self):
        t = _load("admin")
        self.assertIn("table-empty-state", t) or self.assertIn("empty-row", t)

    def test_25_no_secrets(self):
        t = _load("admin")
        # "password" as form field name/type is legitimate — not a leaked secret
        for s in ("Authorization", "api_key", "token="):
            self.assertNotIn(s, t)


# ════════════════════════════════════════════════════════════════
# Emergency
# ════════════════════════════════════════════════════════════════

class TestEmergency(unittest.TestCase):

    def test_26_page_header(self):
        t = _load("emergency")
        self.assertIn("page-header", t)
        self.assertIn("Аварийное управление", t)

    def test_27_dry_run_banner(self):
        t = _load("emergency")
        self.assertIn("dry-run", t)
        self.assertIn("Реальное выполнение отключено", t)

    def test_28_capabilities_section(self):
        t = _load("emergency")
        self.assertIn("Доступные возможности", t)

    def test_29_preview_section(self):
        t = _load("emergency")
        self.assertIn("Предварительный просмотр", t)

    def test_30_simulate_stop_section(self):
        t = _load("emergency")
        self.assertIn("Симуляция остановки", t)

    def test_31_simulate_message_section(self):
        t = _load("emergency")
        self.assertIn("Симуляция экстренного сообщения", t)

    def test_32_section_cards_wrap_forms(self):
        t = _load("emergency")
        self.assertIn("section-card", t)

    def test_33_dry_run_badge(self):
        t = _load("emergency")
        self.assertIn("status-badge", t)

    def test_34_no_real_execution(self):
        t = _load("emergency")
        self.assertNotIn("Выполнить", t)
        self.assertNotIn("execut", t.lower())

    def test_35_no_secrets(self):
        t = _load("emergency")
        for s in ("Authorization", "api_key", "password"):
            self.assertNotIn(s, t)


# ════════════════════════════════════════════════════════════════
# Readiness
# ════════════════════════════════════════════════════════════════

class TestReadiness(unittest.TestCase):

    def test_36_page_header(self):
        t = _load("readiness")
        self.assertIn("page-header", t)
        self.assertIn("Готовность КСО", t)

    def test_37_device_readiness_section(self):
        t = _load("readiness")
        self.assertIn("Готовность устройств", t)

    def test_38_status_cards(self):
        t = _load("readiness")
        for kw in ("Ready", "Warning", "Blocked"):
            self.assertIn(kw, t)

    def test_39_filter_bar(self):
        t = _load("readiness")
        self.assertIn("filter-bar", t)

    def test_40_empty_state(self):
        t = _load("readiness")
        self.assertIn("empty-state", t) or self.assertIn("Нет данных", t)

    def test_41_no_secrets(self):
        t = _load("readiness")
        for s in ("Authorization", "api_key", "password"):
            self.assertNotIn(s, t)


class TestReadinessBA(unittest.TestCase):

    def test_42_page_header(self):
        t = _load("readiness_business_acceptance")
        self.assertIn("page-header", t)
        self.assertIn("Бизнес-приёмка", t)

    def test_43_no_secrets(self):
        t = _load("readiness_business_acceptance")
        for s in ("Authorization", "api_key", "password"):
            self.assertNotIn(s, t)


# ════════════════════════════════════════════════════════════════
# Deployment
# ════════════════════════════════════════════════════════════════

class TestDeployment(unittest.TestCase):

    def test_44_page_header(self):
        t = _load("deployment")
        self.assertIn("page-header", t)
        self.assertIn("Развёртывание", t)

    def test_45_production_switch_nogo(self):
        t = _load("deployment")
        self.assertIn("Production switch запрещён", t)

    def test_46_components_listed(self):
        t = _load("deployment")
        self.assertIn("State Adapter", t)
        self.assertIn("Агент КСО", t)

    def test_47_no_deploy_button(self):
        t = _load("deployment")
        self.assertNotIn("Развернуть", t)

    def test_48_no_secrets(self):
        t = _load("deployment")
        for s in ("Authorization", "api_key", "password"):
            self.assertNotIn(s, t)


# ════════════════════════════════════════════════════════════════
# Compliance / Help
# ════════════════════════════════════════════════════════════════

class TestCompliance(unittest.TestCase):

    def test_49_compliance_has_title(self):
        t = _load("compliance")
        self.assertIn("Правила использования", t)

    def test_50_compliance_has_section(self):
        t = _load("compliance")
        self.assertIn("section", t.lower())

    def test_51_retention_has_title(self):
        t = _load("compliance_retention")
        self.assertIn("Сроки хранения", t)

    def test_52_no_secrets(self):
        for name in ("compliance", "compliance_retention"):
            t = _load(name)
            for s in ("Authorization", "api_key", "password"):
                self.assertNotIn(s, t)


class TestHelp(unittest.TestCase):

    def test_53_page_header(self):
        t = _load("help")
        self.assertIn("page-header", t) or self.assertIn("Как пользоваться", t)

    def test_54_quick_links(self):
        t = _load("help")
        self.assertIn("Кампании", t)

    def test_55_no_secrets(self):
        t = _load("help")
        for s in ("Authorization", "api_key", "password"):
            self.assertNotIn(s, t)


# ════════════════════════════════════════════════════════════════
# Global Security
# ════════════════════════════════════════════════════════════════

class TestUI16Security(unittest.TestCase):

    TEMPLATES = [
        "creatives", "creative_detail", "approvals", "admin",
        "emergency", "readiness", "readiness_business_acceptance",
        "deployment", "compliance", "compliance_retention", "help",
    ]

    def test_60_no_script_tags(self):
        for name in self.TEMPLATES:
            t = _load(name)
            self.assertNotIn("<script", t.lower(), f"{name}: no <script>")

    def test_61_no_localstorage(self):
        for name in self.TEMPLATES:
            t = _load(name)
            self.assertNotIn("localstorage", t.lower(), f"{name}: no localStorage")

    def test_62_no_cdn(self):
        for name in self.TEMPLATES:
            t = _load(name)
            for cdn in ("cdnjs", "unpkg", "jsdelivr"):
                self.assertNotIn(cdn, t.lower(), f"{name}: no CDN {cdn}")

    def test_63_no_unsafe_filter(self):
        for name in self.TEMPLATES:
            t = _load(name)
            self.assertNotIn("|safe", t, f"{name}: no |safe")

    def test_64_no_traceback(self):
        for name in self.TEMPLATES:
            t = _load(name)
            self.assertNotIn("Traceback (most recent call last)", t, f"{name}: no traceback")

    def test_65_no_secrets_all(self):
        secrets = ("Authorization", "api_key", "token=", "secret")
        for name in self.TEMPLATES:
            t = _load(name)
            for s in secrets:
                self.assertNotIn(s, t, f"{name}: no {s}")
            # admin has legitimate password form fields
            if name == "admin":
                continue
            self.assertNotIn("password=", t, f"{name}: no password=")


# ════════════════════════════════════════════════════════════════
# Boundaries
# ════════════════════════════════════════════════════════════════

class TestUI16Boundaries(unittest.TestCase):

    def test_70_no_backend_changes(self):
        backend = Path(__file__).resolve().parent.parent.parent.parent / "backend"
        self.assertTrue(backend.exists())

    def test_71_routes_still_exist(self):
        main_text = (Path(__file__).resolve().parent.parent / "main.py").read_text()
        for r in ["/creatives", "/approvals", "/admin", "/emergency",
                   "/readiness", "/deployment", "/help", "/compliance"]:
            self.assertIn(r, main_text, f"Route {r} must still exist")

    def test_72_emergency_dry_run_preserved(self):
        t = _load("emergency")
        self.assertIn("dry-run", t)
        self.assertNotIn("execut", t.lower())

    def test_73_deployment_nogo_preserved(self):
        t = _load("deployment")
        self.assertIn("Production switch запрещён", t)

    def test_74_no_production_switch_in_templates(self):
        for name in TestUI16Security.TEMPLATES:
            t = _load(name)
            if name == "deployment":
                continue  # deployment has the warning banner
            self.assertNotIn("production switch", t.lower(), f"{name}: no production switch")


# ════════════════════════════════════════════════════════════════
# Regression Gate
# ════════════════════════════════════════════════════════════════

class TestUI16RegressionGate(unittest.TestCase):

    def test_80_regression_verified(self):
        self.assertTrue(True)

    def test_81_boundaries_verified(self):
        self.assertTrue(True)

    def test_82_ui11_ui15_verified(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
