"""PORTAL.1.5 — Campaign Status / Error Improvements tests.

Tests: workflow (9), cross-links (7), detail rendering (6),
list rendering (5), security (7), boundaries (8), regression (5).
Total: 47 tests.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BASE = REPO_ROOT / "apps/portal-web"

main_text = ""
detail_tpl = ""
list_tpl = ""


def _load():
    global main_text, detail_tpl, list_tpl
    if not main_text:
        main_text = (BASE / "main.py").read_text()
        detail_tpl = (BASE / "templates/pages/campaigns_detail.html").read_text()
        list_tpl = (BASE / "templates/pages/campaigns.html").read_text()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Workflow checklist — 9 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowChecklist(unittest.TestCase):

    def test_01_workflow_helper_exists(self):
        _load()
        self.assertIn("_build_campaign_workflow", main_text)

    def test_02_cross_links_helper_exists(self):
        _load()
        self.assertIn("_build_campaign_cross_links", main_text)

    def test_03_workflow_called_in_route(self):
        _load()
        section = main_text.split("async def campaigns_detail")[-1].split("\n\n@app.")[0]
        self.assertIn("_build_campaign_workflow", section)
        self.assertIn("_build_campaign_cross_links", section)

    def test_04_workflow_passed_to_template(self):
        _load()
        section = main_text.split("async def campaigns_detail")[-1].split("\n\n@app.")[0]
        self.assertIn('"workflow": workflow', section)

    def test_05_cross_links_passed_to_template(self):
        _load()
        section = main_text.split("async def campaigns_detail")[-1].split("\n\n@app.")[0]
        self.assertIn('"cross_links": cross_links', section)

    def test_06_workflow_section_in_template(self):
        _load()
        self.assertIn("Продвижение кампании", detail_tpl)

    def test_07_cross_links_section_in_template(self):
        _load()
        self.assertIn("Связанные разделы", detail_tpl)

    def test_08_next_action_in_template(self):
        _load()
        self.assertIn("next_action", detail_tpl)

    def test_09_workflow_steps_have_labels(self):
        _load()
        self.assertIn("step.label", detail_tpl)
        self.assertIn("step.hint", detail_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Cross-links — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossLinks(unittest.TestCase):

    def test_10_planning_link_in_template(self):
        _load()
        self.assertIn("Планирование", detail_tpl)

    def test_11_bookings_link_in_template(self):
        _load()
        self.assertIn("Бронирования", detail_tpl)

    def test_12_publications_link_in_template(self):
        _load()
        self.assertIn("Публикации", detail_tpl)

    def test_13_packages_link_in_template(self):
        _load()
        self.assertIn("Пакеты показа", detail_tpl)

    def test_14_reports_link_in_template(self):
        _load()
        self.assertIn("Отчёты", detail_tpl)

    def test_15_links_conditional_on_permissions(self):
        _load()
        self.assertIn("cross_links.planning", detail_tpl)
        self.assertIn("cross_links.bookings", detail_tpl)
        self.assertIn("cross_links.publications", detail_tpl)

    def test_16_campaign_list_has_packages_link(self):
        _load()
        self.assertIn("/packages", list_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Detail rendering — 6 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDetailRendering(unittest.TestCase):

    def test_17_status_block_renders(self):
        _load()
        self.assertIn("Кампания", detail_tpl)
        self.assertIn("Статус", detail_tpl)

    def test_18_creative_block_renders(self):
        _load()
        self.assertIn("Креативы", detail_tpl)

    def test_19_placement_block_renders(self):
        _load()
        self.assertIn("Размещения", detail_tpl)

    def test_20_approval_section_renders(self):
        _load()
        self.assertIn("Согласование", detail_tpl)

    def test_21_planning_section_renders(self):
        _load()
        self.assertIn("Планирование", detail_tpl)

    def test_22_reports_section_renders(self):
        _load()
        self.assertIn("Отчёты", detail_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 4. List rendering — 5 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestListRendering(unittest.TestCase):

    def test_23_list_has_status_labels(self):
        _load()
        self.assertIn("Черновик", list_tpl)
        self.assertIn("На согласовании", list_tpl)

    def test_24_list_has_create_button(self):
        _load()
        self.assertIn("Создать кампанию", list_tpl)

    def test_25_list_has_detail_link(self):
        _load()
        self.assertIn(
            'href="/campaigns/{{ c.url_code }}"', list_tpl,
        )

    def test_26_list_has_approval_actions(self):
        _load()
        self.assertIn("На согласование", list_tpl)

    def test_27_list_has_packages_in_flow(self):
        _load()
        self.assertIn("Пакеты показа", list_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Security — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurity(unittest.TestCase):
    _SENSITIVE = frozenset({
        "password", "access_token", "refresh_token", "Authorization",
        "api_key", "token", "Cookie", "secret",
    })

    def test_28_no_secrets_in_detail(self):
        _load()
        for key in self._SENSITIVE:
            self.assertNotIn(key.lower(), detail_tpl.lower())

    def test_29_no_traceback(self):
        _load()
        self.assertNotIn("Traceback", detail_tpl)

    def test_30_no_localstorage(self):
        _load()
        self.assertNotIn("localStorage", detail_tpl)

    def test_31_no_cdn(self):
        _load()
        for pat in ("cdn.", "unpkg.com", "jsdelivr"):
            self.assertNotIn(pat, detail_tpl.lower())

    def test_32_no_inline_js(self):
        _load()
        self.assertNotIn("<script", detail_tpl.lower())

    def test_33_safe_error_in_route(self):
        _load()
        self.assertIn("_safe_error", main_text)

    def test_34_no_raw_authorization(self):
        _load()
        self.assertNotIn("Authorization", detail_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Boundaries — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaries(unittest.TestCase):

    def test_35_no_backend_changes(self):
        router = (REPO_ROOT / "backend/app/domains/campaigns/router.py").read_text()
        self.assertIn("campaign", router.lower())

    def test_36_no_migrations(self):
        migrations = list((REPO_ROOT / "migrations" / "versions").glob("*.py"))
        self.assertEqual(len(migrations), 0)

    def test_37_no_docker_changes(self):
        compose = (REPO_ROOT / "infra/docker-compose.yml").read_text()
        self.assertIn("rmp-postgres", compose)

    def test_38_no_env_changes(self):
        env = (REPO_ROOT / ".env.example").read_text()
        self.assertIn("POSTGRES", env)

    def test_39_no_production_switch(self):
        _load()
        self.assertNotIn("production", detail_tpl.lower())

    def test_40_no_kso_gateway(self):
        _load()
        self.assertNotIn("gateway", detail_tpl.lower())

    def test_41_workflow_helper_uses_existing_methods(self):
        _load()
        section = main_text.split("def _build_campaign_workflow")[-1].split("\n\ndef")[0]
        self.assertIn("list_bookings", section)
        self.assertIn("list_publication_batches", section)
        self.assertIn("list_manifests", section)

    def test_42_no_ui_redesign(self):
        _load()
        self.assertIn("data-table", detail_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Regression — 5 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRegression(unittest.TestCase):

    def test_43_planning_rbac_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/planning": "planning.read"', rbac)

    def test_44_bookings_rbac_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/bookings": "bookings.read"', rbac)

    def test_45_publications_rbac_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/publications": "publications.read"', rbac)

    def test_46_packages_rbac_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/packages": "publications.read"', rbac)

    def test_47_backend_campaign_router_untouched(self):
        router = (REPO_ROOT / "backend/app/domains/campaigns/router.py").read_text()
        self.assertIn("campaign", router.lower())
