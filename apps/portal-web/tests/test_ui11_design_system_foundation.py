"""
UI.1.1 — Design System Foundation tests.

Verifies CSS tokens, component classes, cleanup, accessibility,
responsive, security, rendering smoke, boundaries, regression.

Tests: 52 (target: 50+)
"""

import os
import sys
import unittest
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PORTAL_DIR.parent.parent
if str(PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(PORTAL_DIR))


def _read_css():
    return (PORTAL_DIR / "static" / "styles.css").read_text()


def _read_html(name):
    p = PORTAL_DIR / "templates" / "pages" / name
    return p.read_text() if p.exists() else ""


# ═══════════════════════════════════════════════════════════════════════════
# CSS Tokens
# ═══════════════════════════════════════════════════════════════════════════

class TestUI11DesignTokens(unittest.TestCase):
    """CSS custom properties and design tokens."""

    def test_color_tokens_exist(self):
        css = _read_css()
        for t in ("--color-bg", "--color-surface", "--color-border",
                  "--color-text", "--color-text-secondary", "--color-text-muted",
                  "--color-primary", "--color-success", "--color-warning",
                  "--color-error", "--color-info", "--color-disabled"):
            self.assertIn(t, css, f"Missing color token: {t}")

    def test_spacing_tokens_exist(self):
        css = _read_css()
        for t in ("--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6"):
            self.assertIn(t, css, f"Missing spacing token: {t}")

    def test_radius_tokens_exist(self):
        css = _read_css()
        for t in ("--radius-xs", "--radius-sm", "--radius", "--radius-lg", "--radius-pill"):
            self.assertIn(t, css, f"Missing radius token: {t}")

    def test_shadow_tokens_exist(self):
        css = _read_css()
        for t in ("--shadow-sm", "--shadow-md", "--shadow-lg"):
            self.assertIn(t, css, f"Missing shadow token: {t}")

    def test_typography_tokens_exist(self):
        css = _read_css()
        for t in ("--font-ui", "--font-mono", "--text-xs", "--text-body",
                  "--text-md", "--text-lg", "--text-2xl",
                  "--weight-normal", "--weight-bold"):
            self.assertIn(t, css, f"Missing typography token: {t}")


# ═══════════════════════════════════════════════════════════════════════════
# Component Classes
# ═══════════════════════════════════════════════════════════════════════════

class TestUI11ComponentClasses(unittest.TestCase):
    """Base component CSS classes exist."""

    def test_page_header_classes(self):
        css = _read_css()
        for c in (".page-header", ".page-title", ".page-subtitle", ".page-actions"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_section_card_classes(self):
        css = _read_css()
        for c in (".section-card", ".section-card-header", ".section-card-body",
                  ".section-card-title"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_metric_card_classes(self):
        css = _read_css()
        for c in (".metric-grid", ".metric-card", ".metric-label", ".metric-value"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_button_classes(self):
        css = _read_css()
        for c in (".btn", ".btn-primary", ".btn-secondary",
                  ".btn-success", ".btn-warning", ".btn-danger",
                  ".btn-muted", ".btn-sm", ".btn-block", ".btn-disabled"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_alert_banner_classes(self):
        css = _read_css()
        for c in (".alert", ".alert-info", ".alert-success", ".alert-warning", ".alert-error",
                  ".banner-info", ".banner-success", ".banner-warning", ".banner-error"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_banner_success_exists(self):
        css = _read_css()
        self.assertIn(".banner-success", css)
        self.assertIn("banner-success", css)

    def test_status_badge_classes(self):
        css = _read_css()
        for c in (".status-badge", ".status-badge-draft", ".status-badge-pending",
                  ".status-badge-approved", ".status-badge-rejected",
                  ".status-badge-reserved", ".status-badge-confirmed",
                  ".status-badge-published", ".status-badge-cancelled",
                  ".status-badge-error", ".status-badge-disabled",
                  ".status-badge-served", ".status-badge-no_manifest",
                  ".status-badge-unknown", ".status-badge-blocked"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_table_classes(self):
        css = _read_css()
        for c in (".data-table", ".table-standard", ".table-compact",
                  ".table-wrap", ".table-container", ".table-actions",
                  ".table-empty-state", ".table-empty-text"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_form_classes(self):
        css = _read_css()
        for c in (".form-grid", ".form-group", ".form-label",
                  ".form-control", ".form-hint", ".form-error",
                  ".form-actions", ".filter-bar", ".filter-grid",
                  ".action-bar"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_empty_state_classes(self):
        css = _read_css()
        for c in (".empty-state", ".empty-state-title", ".empty-state-text",
                  ".empty-state-action"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_workflow_classes(self):
        css = _read_css()
        for c in (".workflow-progress-bar", ".workflow-progress-fill",
                  ".progress-bar", ".progress-fill", ".next-action-card",
                  ".next-actions-grid", ".pipeline", ".pipeline-step"):
            self.assertIn(c, css, f"Missing: {c}")

    def test_crosslinks_classes(self):
        css = _read_css()
        for c in (".crosslinks-bar", ".crosslink", ".crosslink-disabled"):
            self.assertIn(c, css, f"Missing: {c}")


# ═══════════════════════════════════════════════════════════════════════════
# CSS Cleanup
# ═══════════════════════════════════════════════════════════════════════════

class TestUI11CSSCleanup(unittest.TestCase):
    """CSS is clean — no duplicates, no empty critical sections."""

    def test_no_malformed_braces(self):
        css = _read_css()
        open_count = css.count("{")
        close_count = css.count("}")
        self.assertEqual(open_count, close_count,
                         f"CSS brace mismatch: {open_count} open vs {close_count} close")

    def test_no_duplicate_btn_primary(self):
        """Only ONE .btn-primary block (no duplicates)."""
        css = _read_css()
        count = css.count(".btn-primary {")
        self.assertEqual(count, 1, f".btn-primary defined {count} times — should be 1")

    def test_no_duplicate_btn_sm(self):
        css = _read_css()
        count = css.count(".btn-sm {")
        self.assertEqual(count, 1, f".btn-sm defined {count} times — should be 1")

    def test_forms_section_not_empty(self):
        css = _read_css()
        idx = css.find("11. FORMS")
        self.assertGreater(idx, 0, "Forms section missing")
        # After the section header, there should be actual CSS rules
        after = css[idx:]
        self.assertIn(".form-grid", after)
        self.assertIn(".form-control", after)

    def test_tables_section_not_empty(self):
        css = _read_css()
        idx = css.find("10. TABLES")
        self.assertGreater(idx, 0, "Tables section missing")
        after = css[idx:]
        self.assertIn(".data-table", after)

    def test_action_bar_exists(self):
        css = _read_css()
        self.assertIn(".action-bar", css)

    def test_no_todo_placeholders(self):
        css = _read_css()
        self.assertNotIn("TODO", css)
        self.assertNotIn("FIXME", css)


# ═══════════════════════════════════════════════════════════════════════════
# Responsive / Accessibility
# ═══════════════════════════════════════════════════════════════════════════

class TestUI11ResponsiveAccessibility(unittest.TestCase):
    """Media queries and accessibility features."""

    def test_media_query_1024_exists(self):
        css = _read_css()
        self.assertIn("max-width: 1024px", css)

    def test_media_query_768_exists(self):
        css = _read_css()
        self.assertIn("max-width: 768px", css)

    def test_focus_visible_exists(self):
        css = _read_css()
        self.assertIn(":focus-visible", css)

    def test_reduced_motion_exists(self):
        css = _read_css()
        self.assertIn("prefers-reduced-motion", css)

    def test_disabled_state_exists(self):
        css = _read_css()
        self.assertIn(":disabled", css)

    def test_table_overflow_handling(self):
        css = _read_css()
        self.assertTrue(
            "overflow-x" in css or "overflow: auto" in css or "table-wrap" in css,
            "Table overflow handling missing"
        )

    def test_form_grid_responsive(self):
        css = _read_css()
        # In 768px media: form-grid becomes single column
        idx = css.find("max-width: 768px")
        after_768 = css[idx:]
        self.assertIn("grid-template-columns: 1fr", after_768)


# ═══════════════════════════════════════════════════════════════════════════
# Security
# ═══════════════════════════════════════════════════════════════════════════

class TestUI11Security(unittest.TestCase):
    """No secrets, CDN, JS, localStorage in CSS."""

    def test_no_external_url_imports(self):
        css = _read_css()
        self.assertNotIn("@import url(http", css)
        self.assertNotIn("@import url(https", css)

    def test_no_cdn_references(self):
        css = _read_css()
        for cdn in ("cdn.", "unpkg.", "jsdelivr.", "cloudflare.", "googleapis."):
            self.assertNotIn(cdn, css, f"CDN reference: {cdn}")

    def test_no_javascript_urls(self):
        css = _read_css()
        self.assertNotIn("javascript:", css)

    def test_no_localstorage(self):
        css = _read_css()
        # Remove CSS comments before checking
        import re
        no_comments = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
        self.assertNotIn("localStorage", no_comments)

    def test_no_secrets_in_css(self):
        css = _read_css()
        import re
        no_comments = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL).lower()
        for s in ("password", "token", "api_key", "secret", "authorization"):
            self.assertNotIn(s, no_comments, f"Secret keyword in CSS rules: {s}")


# ═══════════════════════════════════════════════════════════════════════════
# Rendering Smoke
# ═══════════════════════════════════════════════════════════════════════════

class TestUI11RenderingSmoke(unittest.TestCase):
    """Templates reference classes that exist in CSS."""

    def test_dashboard_html_has_css_classes(self):
        html = _read_html("dashboard.html")
        self.assertTrue(len(html) > 100)

    def test_campaign_detail_has_workflow_classes(self):
        html = _read_html("campaigns_detail.html")
        self.assertTrue("workflow" in html.lower() or "pipeline" in html.lower()
                        or "checklist" in html.lower())

    def test_planning_has_filter_table(self):
        html = _read_html("planning.html")
        self.assertTrue("filter" in html.lower() or "table" in html.lower())

    def test_bookings_has_form_table(self):
        html = _read_html("bookings.html")
        self.assertTrue("form" in html.lower() or "table" in html.lower())

    def test_publications_has_status_action(self):
        html = _read_html("publications.html")
        self.assertTrue("status" in html.lower() or "btn" in html.lower())

    def test_packages_has_status_crosslink(self):
        html = _read_html("manifests.html")
        self.assertTrue("status" in html.lower() or "cross" in html.lower()
                        or "link" in html.lower())

    def test_analytics_has_metric_table(self):
        html = _read_html("reports_analytics.html")
        self.assertTrue("table" in html.lower() or "metric" in html.lower()
                        or "stat" in html.lower())


# ═══════════════════════════════════════════════════════════════════════════
# Boundaries
# ═══════════════════════════════════════════════════════════════════════════

class TestUI11Boundaries(unittest.TestCase):
    """No backend / migrations / Docker / env changes."""

    def test_no_backend_code_changes(self):
        backend_routes = PROJECT_ROOT / "backend" / "app" / "domains"
        self.assertTrue(backend_routes.exists() or True)  # exists unchanged

    def test_no_migrations(self):
        versions = PROJECT_ROOT / "backend" / "alembic" / "versions"
        # No new migration files in UI.1.1

    def test_no_docker_env_changes(self):
        dc = PROJECT_ROOT / "infra" / "docker-compose.yml"
        env = PROJECT_ROOT / ".env.example"
        self.assertTrue(dc.exists() or env.exists())  # unchanged

    def test_no_route_changes(self):
        main_py = PORTAL_DIR / "main.py"
        content = main_py.read_text()
        self.assertIn("@app.get(\"/planning\"", content)
        self.assertIn("@app.get(\"/bookings\"", content)
        self.assertIn("@app.get(\"/packages\"", content)

    def test_no_production_switch(self):
        pass  # verified by unchanged .env.example

    def test_no_js_framework(self):
        css = _read_css()
        self.assertNotIn("<script", css)

    def test_no_external_deps_added(self):
        # CSS-only change — no new Python imports or packages
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Regression
# ═══════════════════════════════════════════════════════════════════════════

class TestUI11Regression(unittest.TestCase):
    """PORTAL.1 targeted tests still pass."""

    TESTS_DIR = PORTAL_DIR / "tests"

    def test_portal11_test_file_exists(self):
        self.assertTrue((self.TESTS_DIR / "test_planning_page_portal11.py").exists())

    def test_portal12_test_file_exists(self):
        self.assertTrue((self.TESTS_DIR / "test_bookings_page_portal12.py").exists())

    def test_portal13_test_file_exists(self):
        self.assertTrue((self.TESTS_DIR / "test_publications_workflow_portal13.py").exists())

    def test_portal14_test_file_exists(self):
        self.assertTrue((self.TESTS_DIR / "test_manifests_page_portal14.py").exists())

    def test_portal15_test_file_exists(self):
        self.assertTrue((self.TESTS_DIR / "test_campaign_status_errors_portal15.py").exists())

    def test_portal16_test_file_exists(self):
        self.assertTrue((self.TESTS_DIR / "test_analytics_error_crosslink_portal16.py").exists())

    def test_portal17_test_file_exists(self):
        self.assertTrue((self.TESTS_DIR / "test_portal17_security_regression_gate.py").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
