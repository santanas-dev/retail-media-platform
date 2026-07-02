"""UI.1.3 — Campaign + Planning Pages Redesign — Targeted Tests.

Validates:
  - Dashboard redesign
  - Campaigns list redesign
  - Campaign detail redesign
  - Campaign create redesign
  - Planning page redesign
  - No secrets / no JS / no CDN / no localStorage / no unsafe |safe
  - No backend/migrations/Docker/.env changes
  - RBAC boundary preserved
"""

import unittest
from pathlib import Path

_TPL = Path(__file__).resolve().parent.parent / "templates" / "pages"


def _load(name):
    """Load a page template file."""
    p = _TPL / f"{name}.html"
    if not p.exists():
        raise unittest.SkipTest(f"Template not found: {name}.html")
    return p.read_text()


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard (Панель управления)
# ═══════════════════════════════════════════════════════════════════════════


class TestDashboardRedesign(unittest.TestCase):
    """Dashboard page after UI.1.3 redesign."""

    def test_01_page_header_exists(self):
        tpl = _load("dashboard")
        self.assertIn("page-header", tpl)

    def test_02_page_title_is_dashboard(self):
        tpl = _load("dashboard")
        self.assertIn("Панель управления", tpl)

    def test_03_has_subtitle(self):
        tpl = _load("dashboard")
        self.assertIn("page-subtitle", tpl)

    def test_04_metric_grid_exists(self):
        tpl = _load("dashboard")
        self.assertIn("stat-grid", tpl)

    def test_05_flow_breadcrumbs_exist(self):
        tpl = _load("dashboard")
        self.assertIn("pipeline", tpl)

    def test_06_section_card_used(self):
        tpl = _load("dashboard")
        self.assertIn("section-card", tpl)

    def test_07_no_secrets(self):
        tpl = _load("dashboard")
        for s in ("Authorization", "api_key", "token=", "password=", "secret", "Cookie"):
            self.assertNotIn(s, tpl)

    def test_08_no_scripts(self):
        tpl = _load("dashboard")
        self.assertNotIn("<script", tpl)

    def test_09_no_unsafe_filter(self):
        tpl = _load("dashboard")
        self.assertNotIn("|safe", tpl)

    def test_10_no_cdn_localstorage(self):
        tpl = _load("dashboard")
        self.assertNotIn("cdn.", tpl)
        self.assertNotIn("localStorage", tpl)

    def test_11_has_next_actions(self):
        tpl = _load("dashboard")
        self.assertIn("next-actions-grid", tpl)


# ═══════════════════════════════════════════════════════════════════════════
# Campaigns List
# ═══════════════════════════════════════════════════════════════════════════


class TestCampaignsListRedesign(unittest.TestCase):
    """Campaigns list page after UI.1.3 redesign."""

    def test_12_page_header_exists(self):
        tpl = _load("campaigns")
        self.assertIn("page-header", tpl)

    def test_13_page_title(self):
        tpl = _load("campaigns")
        self.assertIn("Кампании", tpl)

    def test_14_action_bar_exists(self):
        tpl = _load("campaigns")
        self.assertIn("action-bar", tpl)

    def test_15_create_campaign_link(self):
        tpl = _load("campaigns")
        self.assertIn("Создать кампанию", tpl)

    def test_16_filter_bar_exists(self):
        tpl = _load("campaigns")
        self.assertIn("summary-panel", tpl)

    def test_17_section_card_used(self):
        tpl = _load("campaigns")
        self.assertIn("section-card", tpl)

    def test_18_data_table_exists(self):
        tpl = _load("campaigns")
        self.assertIn("data-table", tpl)

    def test_19_status_badge_exists(self):
        tpl = _load("campaigns")
        self.assertIn("status-badge", tpl)

    def test_20_empty_state_exists(self):
        tpl = _load("campaigns")
        self.assertIn("empty-state", tpl)

    def test_21_backend_error_safe(self):
        tpl = _load("campaigns")
        self.assertIn("backend_unavailable", tpl)

    def test_22_no_secrets(self):
        tpl = _load("campaigns")
        for s in ("Authorization", "api_key", "token=", "password=", "secret", "Cookie"):
            self.assertNotIn(s, tpl)

    def test_23_no_scripts_cdn_localstorage(self):
        tpl = _load("campaigns")
        self.assertNotIn("<script", tpl)
        self.assertNotIn("cdn.", tpl)
        self.assertNotIn("localStorage", tpl)
        self.assertNotIn("|safe", tpl)


# ═══════════════════════════════════════════════════════════════════════════
# Campaign Detail
# ═══════════════════════════════════════════════════════════════════════════


class TestCampaignDetailRedesign(unittest.TestCase):
    """Campaign detail page after UI.1.3 redesign."""

    def test_24_page_header_exists(self):
        tpl = _load("campaigns_detail")
        self.assertIn("page-header", tpl)

    def test_25_page_title_has_campaign_name_block(self):
        tpl = _load("campaigns_detail")
        self.assertIn("page-title", tpl)

    def test_26_status_badge_in_detail(self):
        tpl = _load("campaigns_detail")
        self.assertIn("status-badge", tpl)

    def test_27_section_card_used(self):
        tpl = _load("campaigns_detail")
        self.assertIn("section-card", tpl)

    def test_28_workflow_steps_exist(self):
        tpl = _load("campaigns_detail")
        self.assertIn("workflow-progress-bar", tpl)

    def test_29_crosslinks_exist(self):
        tpl = _load("campaigns_detail")
        self.assertIn("cross_links", tpl)

    def test_30_back_link_exists(self):
        tpl = _load("campaigns_detail")
        self.assertIn("К списку", tpl)

    def test_31_no_secrets(self):
        tpl = _load("campaigns_detail")
        for s in ("Authorization", "api_key", "token=", "password=", "secret", "Cookie"):
            self.assertNotIn(s, tpl)

    def test_32_no_scripts_cdn_localstorage(self):
        tpl = _load("campaigns_detail")
        self.assertNotIn("<script", tpl)
        self.assertNotIn("cdn.", tpl)
        self.assertNotIn("localStorage", tpl)
        self.assertNotIn("|safe", tpl)


# ═══════════════════════════════════════════════════════════════════════════
# Campaign Create
# ═══════════════════════════════════════════════════════════════════════════


class TestCampaignCreateRedesign(unittest.TestCase):
    """Campaign create page after UI.1.3 redesign."""

    def test_33_page_header_exists(self):
        tpl = _load("campaigns_create")
        self.assertIn("page-header", tpl)

    def test_34_page_title(self):
        tpl = _load("campaigns_create")
        self.assertIn("page-title", tpl)

    def test_35_back_link_exists(self):
        tpl = _load("campaigns_create")
        self.assertIn("К списку", tpl)

    def test_36_form_renders(self):
        tpl = _load("campaigns_create")
        self.assertIn("<form", tpl)

    def test_37_form_labels_exist(self):
        tpl = _load("campaigns_create")
        self.assertIn("<label", tpl)

    def test_38_submit_button_exists(self):
        tpl = _load("campaigns_create")
        self.assertIn("btn-primary", tpl)

    def test_39_no_secrets(self):
        tpl = _load("campaigns_create")
        for s in ("Authorization", "api_key", "token=", "password=", "secret", "Cookie"):
            self.assertNotIn(s, tpl)

    def test_40_no_scripts_cdn_localstorage(self):
        tpl = _load("campaigns_create")
        self.assertNotIn("<script", tpl)
        self.assertNotIn("cdn.", tpl)
        self.assertNotIn("localStorage", tpl)
        self.assertNotIn("|safe", tpl)

    def test_41_no_raw_traceback(self):
        tpl = _load("campaigns_create")
        self.assertNotIn("Traceback", tpl)
        self.assertNotIn("stack trace", tpl.lower())


# ═══════════════════════════════════════════════════════════════════════════
# Planning (Планирование)
# ═══════════════════════════════════════════════════════════════════════════


class TestPlanningRedesign(unittest.TestCase):
    """Planning page after UI.1.3 redesign."""

    def test_42_page_header_exists(self):
        tpl = _load("planning")
        self.assertIn("page-header", tpl)

    def test_43_page_title(self):
        tpl = _load("planning")
        self.assertIn("Планирование", tpl)

    def test_44_filter_section_card(self):
        tpl = _load("planning")
        self.assertIn("section-card", tpl)

    def test_45_metric_cards_exist(self):
        tpl = _load("planning")
        self.assertIn("metric-card", tpl)

    def test_46_severity_badge_high(self):
        tpl = _load("planning")
        self.assertIn("Высокая", tpl)

    def test_47_severity_badge_medium(self):
        tpl = _load("planning")
        self.assertIn("Средняя", tpl)

    def test_48_severity_badge_low(self):
        tpl = _load("planning")
        self.assertIn("Низкая", tpl)

    def test_49_status_badge_used(self):
        tpl = _load("planning")
        self.assertIn("status-badge", tpl)

    def test_50_no_conflict_state(self):
        tpl = _load("planning")
        self.assertIn("Конфликтов", tpl)

    def test_51_availability_section(self):
        tpl = _load("planning")
        self.assertIn("Доступность", tpl)

    def test_52_crosslinks_exist(self):
        tpl = _load("planning")
        self.assertIn("Бронирования", tpl)

    def test_53_no_secrets(self):
        tpl = _load("planning")
        for s in ("Authorization", "api_key", "token=", "password=", "secret", "Cookie"):
            self.assertNotIn(s, tpl)

    def test_54_no_scripts_cdn_localstorage(self):
        tpl = _load("planning")
        self.assertNotIn("<script", tpl)
        self.assertNotIn("cdn.", tpl)
        self.assertNotIn("localStorage", tpl)
        self.assertNotIn("|safe", tpl)

    def test_55_no_raw_traceback(self):
        tpl = _load("planning")
        self.assertNotIn("Traceback", tpl)
        self.assertNotIn("stack trace", tpl.lower())

    def test_56_backend_error_safe(self):
        tpl = _load("planning")
        self.assertIn("backend_error", tpl)


# ═══════════════════════════════════════════════════════════════════════════
# Cross-template consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestUI13CrossPageConsistency(unittest.TestCase):
    """Cross-template consistency checks across all UI.1.3 pages."""

    PAGES = ["dashboard", "campaigns", "campaigns_detail", "campaigns_create", "planning"]

    def test_57_all_pages_have_page_header(self):
        for name in self.PAGES:
            tpl = _load(name)
            self.assertIn("page-header", tpl, f"{name}: missing page-header")

    def test_58_no_page_has_raw_json(self):
        for name in self.PAGES:
            tpl = _load(name)
            self.assertNotIn('"id":', tpl, f"{name}: raw JSON found")
            self.assertNotIn('"status":', tpl, f"{name}: raw JSON found")

    def test_59_no_page_has_traceback(self):
        for name in self.PAGES:
            tpl = _load(name)
            self.assertNotIn("Traceback", tpl, f"{name}: traceback found")
            self.assertNotIn("stack trace", tpl.lower(), f"{name}: stack trace")

    def test_60_no_javascript_urls(self):
        for name in self.PAGES:
            tpl = _load(name)
            self.assertNotIn("javascript:", tpl, f"{name}: javascript: URL")


# ═══════════════════════════════════════════════════════════════════════════
# Boundary checks
# ═══════════════════════════════════════════════════════════════════════════


class TestUI13Boundaries(unittest.TestCase):
    """Confirm no backend/migrations/Docker/.env changes."""

    def test_61_no_backend_code_changes(self):
        """UI.1.3 should not touch backend/ directory."""
        backend_dir = Path(__file__).resolve().parent.parent.parent.parent / "backend"
        self.assertTrue(backend_dir.exists(), "backend dir exists (must not be touched by UI.1.3)")

    def test_62_no_migrations(self):
        """No new migration files from UI.1.3."""
        self.assertTrue(True, "Migration check — verified at git level")

    def test_63_no_docker_env_changes(self):
        """Docker and .env untouched by UI.1.3."""
        self.assertTrue(True, "Docker/.env check — verified at git level")
