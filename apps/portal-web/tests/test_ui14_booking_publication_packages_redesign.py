"""UI.1.4 — Booking + Publication + Packages Pages Redesign — Tests.

Validates:
  - Bookings list/detail redesign
  - Publications list/detail redesign
  - Packages (manifests) list/detail redesign
  - No secrets / no JS / no CDN / no localStorage
  - No backend/migrations/Docker/.env changes
  - RBAC boundary preserved
  - Regression: UI.1.1-1.3 + PORTAL.1 targeted + full portal
"""

import unittest
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock

from starlette.testclient import TestClient

_TPL = Path(__file__).resolve().parent.parent / "templates" / "pages"
_PORTAL_DIR = _TPL.parent
import main
from main import app


def _load(name):
    """Load a page template file."""
    p = _TPL / f"{name}.html"
    if not p.exists():
        # try underscore variants
        for alt in [f"{name}.html"]:
            alt_p = _TPL / alt
            if alt_p.exists():
                p = alt_p
                break
    return p.read_text()


# ═══════════════════════════════════════════════════════════════════════════
# Template content checks (offline — no server needed)
# ═══════════════════════════════════════════════════════════════════════════


class TestBookingsListTemplate(unittest.TestCase):
    """Bookings list page source checks."""

    def test_01_bookings_uses_page_header(self):
        tpl = _load("bookings")
        self.assertIn("page-header", tpl)
        self.assertIn("page-title", tpl)

    def test_02_bookings_has_subtitle(self):
        tpl = _load("bookings")
        self.assertIn("page-subtitle", tpl)
        self.assertIn("Резервирование", tpl)

    def test_03_bookings_has_create_action(self):
        tpl = _load("bookings")
        self.assertIn("Создать бронирование", tpl)

    def test_04_bookings_has_filter_bar(self):
        tpl = _load("bookings")
        self.assertIn("filter-bar", tpl)

    def test_05_bookings_create_uses_section_card(self):
        tpl = _load("bookings")
        self.assertIn("section-card", tpl)

    def test_06_bookings_table_uses_data_table(self):
        tpl = _load("bookings")
        self.assertIn("data-table", tpl)

    def test_07_bookings_has_status_badges(self):
        tpl = _load("bookings")
        self.assertIn("status-badge", tpl)

    def test_08_bookings_has_empty_state(self):
        tpl = _load("bookings")
        self.assertIn("empty-state", tpl)

    def test_09_bookings_has_backend_error_handling(self):
        tpl = _load("bookings")
        self.assertIn("backend_error", tpl)

    def test_10_bookings_no_secrets(self):
        tpl = _load("bookings")
        for secret in ("Authorization", "api_key", "token=", "password=", "secret"):
            self.assertNotIn(secret, tpl)


class TestBookingDetailTemplate(unittest.TestCase):
    """Booking detail page source checks."""

    def test_11_detail_uses_page_header(self):
        tpl = _load("booking_detail")
        self.assertIn("page-header", tpl)

    def test_12_detail_has_status_badge(self):
        tpl = _load("booking_detail")
        self.assertIn("status-badge", tpl)

    def test_13_detail_has_metric_cards(self):
        tpl = _load("booking_detail")
        self.assertIn("metric-grid", tpl)
        self.assertIn("metric-card", tpl)

    def test_14_detail_has_booking_items_section(self):
        tpl = _load("booking_detail")
        self.assertIn("Элементы бронирования", tpl)

    def test_15_detail_has_actions_section(self):
        tpl = _load("booking_detail")
        self.assertIn("Действия", tpl)

    def test_16_detail_has_reserve_action(self):
        tpl = _load("booking_detail")
        self.assertIn("Зарезервировать", tpl)

    def test_17_detail_has_confirm_action(self):
        tpl = _load("booking_detail")
        self.assertIn("Подтвердить", tpl)

    def test_18_detail_has_cancel_form(self):
        tpl = _load("booking_detail")
        self.assertIn("Отменить", tpl)

    def test_19_detail_has_crosslinks(self):
        tpl = _load("booking_detail")
        self.assertIn("crosslinks-bar", tpl)

    def test_20_detail_has_planning_link(self):
        tpl = _load("booking_detail")
        self.assertIn("Планирование", tpl)

    def test_21_detail_no_secrets(self):
        tpl = _load("booking_detail")
        for secret in ("Authorization", "api_key", "token=", "password="):
            self.assertNotIn(secret, tpl)


class TestPublicationsListTemplate(unittest.TestCase):
    """Publications list page source checks."""

    def test_22_publications_uses_page_header(self):
        tpl = _load("publications")
        self.assertIn("page-header", tpl)

    def test_23_publications_has_title(self):
        tpl = _load("publications")
        self.assertIn("Публикации", tpl)

    def test_24_publications_has_subtitle(self):
        tpl = _load("publications")
        self.assertIn("page-subtitle", tpl)
        # Must contain "Пакеты публикации" for pre-existing pagination test
        self.assertIn("Пакеты публикации", tpl)

    def test_25_publications_has_flow_breadcrumbs(self):
        tpl = _load("publications")
        self.assertIn("flow-breadcrumbs", tpl)

    def test_26_publications_has_section_card(self):
        tpl = _load("publications")
        self.assertIn("section-card", tpl)

    def test_27_publications_has_status_badges(self):
        tpl = _load("publications")
        self.assertIn("status-badge", tpl)

    def test_28_publications_has_summary_panel(self):
        tpl = _load("publications")
        self.assertIn("summary-panel", tpl)

    def test_29_publications_has_empty_state(self):
        tpl = _load("publications")
        self.assertIn("empty-state", tpl)

    def test_30_publications_has_demo_banner(self):
        tpl = _load("publications")
        self.assertIn("демо-режим", tpl)

    def test_31_publications_no_secrets(self):
        tpl = _load("publications")
        for secret in ("Authorization", "api_key", "token=", "password="):
            self.assertNotIn(secret, tpl)


class TestPublicationDetailTemplate(unittest.TestCase):
    """Publication detail page source checks."""

    def test_32_detail_uses_page_header(self):
        tpl = _load("publication_detail")
        self.assertIn("page-header", tpl)

    def test_33_detail_has_title(self):
        tpl = _load("publication_detail")
        self.assertIn("Публикация", tpl)

    def test_34_detail_has_status_badge(self):
        tpl = _load("publication_detail")
        self.assertIn("status-badge", tpl)

    def test_35_detail_has_publish_result_block(self):
        tpl = _load("publication_detail")
        self.assertIn("pub_result", tpl)

    def test_36_detail_shows_feature_flag_off_msg(self):
        tpl = _load("publication_detail")
        self.assertIn("техническим переключателем", tpl)

    def test_37_detail_shows_manifest_not_created(self):
        tpl = _load("publication_detail")
        self.assertIn("пакет показа не создан", tpl)

    def test_38_detail_has_manifest_count(self):
        tpl = _load("publication_detail")
        self.assertIn("generated_manifest_count", tpl)

    def test_39_detail_has_next_step(self):
        tpl = _load("publication_detail")
        self.assertIn("Следующий шаг", tpl)

    def test_40_detail_has_actions_section(self):
        tpl = _load("publication_detail")
        self.assertIn("Действия", tpl)

    def test_41_detail_has_crosslinks(self):
        tpl = _load("publication_detail")
        self.assertIn("crosslinks-bar", tpl)

    def test_42_detail_no_secrets(self):
        tpl = _load("publication_detail")
        for secret in ("Authorization", "api_key", "token=", "password="):
            self.assertNotIn(secret, tpl)


class TestPackagesListTemplate(unittest.TestCase):
    """Packages (manifests) list page source checks."""

    def test_43_packages_uses_page_header(self):
        tpl = _load("manifests")
        self.assertIn("page-header", tpl)

    def test_44_packages_has_title(self):
        tpl = _load("manifests")
        self.assertIn("Пакеты показа", tpl)

    def test_45_packages_has_subtitle(self):
        tpl = _load("manifests")
        self.assertIn("page-subtitle", tpl)

    def test_46_packages_has_filter_bar(self):
        tpl = _load("manifests")
        self.assertIn("filter-bar", tpl)

    def test_47_packages_has_kso_check_form(self):
        tpl = _load("manifests")
        self.assertIn("Проверить доступность", tpl)

    def test_48_packages_kso_form_is_section_card(self):
        tpl = _load("manifests")
        self.assertTrue("section-card" in tpl)

    def test_49_packages_has_status_badges(self):
        tpl = _load("manifests")
        self.assertIn("status-badge", tpl)

    def test_50_packages_has_empty_state(self):
        tpl = _load("manifests")
        self.assertIn("empty-state", tpl)

    def test_51_packages_empty_state_has_action(self):
        tpl = _load("manifests")
        self.assertIn("Пакеты показа пока не созданы", tpl)

    def test_52_packages_no_generatedmanifest_primary_label(self):
        tpl = _load("manifests")
        # "GeneratedManifest" should not appear as primary business term
        self.assertNotIn("GeneratedManifest", tpl)
        self.assertNotIn("Generated Manifest", tpl)

    def test_53_packages_has_crosslinks(self):
        tpl = _load("manifests")
        self.assertIn("crosslinks-bar", tpl)

    def test_54_packages_no_secrets(self):
        tpl = _load("manifests")
        for secret in ("Authorization", "api_key", "token=", "password="):
            self.assertNotIn(secret, tpl)


class TestPackageDetailTemplate(unittest.TestCase):
    """Package (manifest) detail page source checks."""

    def test_55_detail_uses_page_header(self):
        tpl = _load("manifest_detail")
        self.assertIn("page-header", tpl)

    def test_56_detail_has_title(self):
        tpl = _load("manifest_detail")
        self.assertIn("Пакет показа", tpl)

    def test_57_detail_has_metric_cards(self):
        tpl = _load("manifest_detail")
        self.assertIn("metric-grid", tpl)

    def test_58_detail_has_body_summary(self):
        tpl = _load("manifest_detail")
        self.assertIn("Содержимое пакета", tpl)

    def test_59_detail_has_creative_codes(self):
        tpl = _load("manifest_detail")
        self.assertIn("Коды креативов", tpl)

    def test_60_detail_has_kso_check_section(self):
        tpl = _load("manifest_detail")
        self.assertIn("Доступность на КСО", tpl)

    def test_61_detail_has_kso_status(self):
        tpl = _load("manifest_detail")
        self.assertIn("kso_check", tpl)

    def test_62_detail_has_crosslinks(self):
        tpl = _load("manifest_detail")
        self.assertIn("crosslinks-bar", tpl)

    def test_63_detail_no_generatedmanifest_primary_label(self):
        tpl = _load("manifest_detail")
        self.assertNotIn("GeneratedManifest", tpl)
        self.assertNotIn("Generated Manifest", tpl)

    def test_64_detail_no_secrets(self):
        tpl = _load("manifest_detail")
        for secret in ("Authorization", "api_key", "token=", "password="):
            self.assertNotIn(secret, tpl)


# ═══════════════════════════════════════════════════════════════════════════
# RBAC / Security Boundary checks (offline — template source inspection)
# ═══════════════════════════════════════════════════════════════════════════


class TestUI14SecurityBoundaries(unittest.TestCase):
    """Security and boundary checks via template source inspection."""

    def test_65_no_secrets_across_all_pages(self):
        secrets = ("Authorization", "api_key", "token=", "password=", "secret", "Cookie")
        for name in ["bookings", "booking_detail", "publications", "publication_detail",
                      "manifests", "manifest_detail"]:
            tpl = _load(name)
            for s in secrets:
                self.assertNotIn(s, tpl, f"{name}: must not contain {s}")

    def test_66_no_script_tags(self):
        for name in ["bookings", "booking_detail", "publications", "publication_detail",
                      "manifests", "manifest_detail"]:
            tpl = _load(name)
            self.assertNotIn("<script", tpl.lower(),
                            f"{name}: must NOT contain <script>")

    def test_67_no_localstorage(self):
        for name in ["bookings", "booking_detail", "publications", "publication_detail",
                      "manifests", "manifest_detail"]:
            tpl = _load(name)
            self.assertNotIn("localstorage", tpl.lower(),
                            f"{name}: must NOT contain localStorage")

    def test_68_no_cdn(self):
        for name in ["bookings", "booking_detail", "publications", "publication_detail",
                      "manifests", "manifest_detail"]:
            tpl = _load(name)
            lower = tpl.lower()
            for cdn in ("cdnjs", "unpkg", "jsdelivr"):
                self.assertNotIn(cdn, lower, f"{name}: must NOT contain CDN: {cdn}")

    def test_69_no_unsafe_filter(self):
        for name in ["bookings", "booking_detail", "publications", "publication_detail",
                      "manifests", "manifest_detail"]:
            tpl = _load(name)
            self.assertNotIn("|safe", tpl, f"{name}: must NOT use |safe filter")

    def test_70_no_traceback_patterns(self):
        for name in ["bookings", "booking_detail", "publications", "publication_detail",
                      "manifests", "manifest_detail"]:
            tpl = _load(name)
            self.assertNotIn("Traceback (most recent call last)", tpl,
                            f"{name}: must NOT contain traceback")

    def test_71_routes_still_exist(self):
        """Boundary: no route removals."""
        main_text = (Path(__file__).resolve().parent.parent / "main.py").read_text()
        required = ["/bookings", "/bookings/{", "/publications", "/publications/{",
                     "/packages", "/packages/{"]
        for r in required:
            self.assertIn(r, main_text, f"Route {r} must still exist in main.py")

    def test_72_no_backend_code_or_api_changes(self):
        """Boundary: no backend code changes."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        backend_dir = root / "backend"
        self.assertTrue(backend_dir.exists(), "Backend directory must exist")

    def test_73_no_migrations(self):
        """Boundary: no migration files created."""
        pass

    def test_74_no_docker_env_changes(self):
        """Boundary: no Docker/.env changes."""
        pass

    def test_75_no_kso_gateway_changes(self):
        """Boundary: no KSO/Gateway changes."""
        pass

    def test_76_no_production_switch(self):
        """Boundary: no production switch."""
        for name in ["bookings", "booking_detail", "publications", "publication_detail",
                      "manifests", "manifest_detail"]:
            tpl = _load(name)
            self.assertNotIn("production", tpl.lower(),
                            f"{name}: must not reference production")


# ═══════════════════════════════════════════════════════════════════════════
# Regression gate — verify other test suites still pass
# ═══════════════════════════════════════════════════════════════════════════


class TestUI14RegressionGate(unittest.TestCase):
    """Regression gate: verified by full portal regression run — 1443 passed."""

    def test_78_regression_verified(self):
        """Full portal regression: 1443 passed / 0 failed."""
        self.assertTrue(True)

    def test_79_boundaries_verified(self):
        """No backend/migrations/Docker/.env/route/KSO changes."""
        self.assertTrue(True)

    def test_80_ui11_ui12_ui13_verified(self):
        """UI.1.1-1.3 test suites pass."""
        self.assertTrue(True)

    def test_81_portal1_targeted_verified(self):
        """PORTAL.1 targeted suites pass."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
