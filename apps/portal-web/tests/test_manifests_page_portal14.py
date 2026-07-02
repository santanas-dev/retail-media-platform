"""PORTAL.1.4 — Manifest / KSO Preview Page tests.

Tests: route/RBAC (8), BackendClient (6), rendering list (6),
rendering detail + KSO (8), KSO check (5), publication integration (3),
security (7), boundaries (8), regression (5).
Total: 56 tests.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BASE = REPO_ROOT / "apps/portal-web"

main_text = ""
bc_text = ""
manifests_tpl = ""
detail_tpl = ""
pub_detail_tpl = ""


def _load():
    global main_text, bc_text, manifests_tpl, detail_tpl, pub_detail_tpl
    if not main_text:
        main_text = (BASE / "main.py").read_text()
        bc_text = (BASE / "backend_client.py").read_text()
        manifests_tpl = (BASE / "templates/pages/manifests.html").read_text()
        detail_tpl = (BASE / "templates/pages/manifest_detail.html").read_text()
        pub_detail_tpl = (BASE / "templates/pages/publication_detail.html").read_text()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Route / RBAC — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestsRouteRBAC(unittest.TestCase):

    def test_01_manifests_route_exists(self):
        _load()
        self.assertIn('"/packages"', main_text)

    def test_02_rbac_requires_publications_read(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/packages": "publications.read"', rbac)

    def test_03_route_checks_auth(self):
        _load()
        self.assertIn('require_auth_for_page(request, "/packages")', main_text)

    def test_04_detail_route_exists(self):
        _load()
        self.assertIn("/packages/{manifest_code}", main_text)

    def test_05_check_kso_route_exists(self):
        _load()
        self.assertIn("/packages/check-kso", main_text)

    def test_06_manifests_template_exists(self):
        tpl = BASE / "templates/pages/manifests.html"
        self.assertTrue(tpl.exists())

    def test_07_detail_template_exists(self):
        tpl = BASE / "templates/pages/manifest_detail.html"
        self.assertTrue(tpl.exists())

    def test_08_nav_link_exists(self):
        nav = (BASE / "templates/base.html").read_text()
        self.assertIn("Пакеты показа", nav)


# ═══════════════════════════════════════════════════════════════════════════
# 2. BackendClient — 6 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBackendClientMethods(unittest.TestCase):

    def test_09_list_manifests_exists(self):
        _load()
        self.assertIn("def list_manifests", bc_text)

    def test_10_get_manifest_exists(self):
        _load()
        self.assertIn("def get_manifest", bc_text)

    def test_11_kso_manifest_status_exists(self):
        _load()
        self.assertIn("def get_kso_manifest_status", bc_text)

    def test_12_list_manifests_called(self):
        _load()
        section = main_text.split("async def manifests_page")[-1].split("\n\n@app.")[0]
        self.assertIn("list_manifests", section)

    def test_13_get_manifest_called(self):
        _load()
        section = main_text.split("async def manifest_detail")[-1].split("\n\n@app.")[0]
        self.assertIn("get_manifest", section)

    def test_14_kso_check_called(self):
        _load()
        section = main_text.split("async def manifests_check_kso")[-1].split("\n\n@app.")[0]
        self.assertIn("get_kso_manifest_status", section)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Rendering list — 6 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestListRendering(unittest.TestCase):

    def test_15_list_has_filters(self):
        _load()
        self.assertIn("filter-bar", manifests_tpl)

    def test_16_list_has_kso_check_form(self):
        _load()
        self.assertIn("check-kso", manifests_tpl)

    def test_17_list_has_status_labels(self):
        _load()
        self.assertIn("Опубликован", manifests_tpl)
        self.assertIn("Сгенерирован", manifests_tpl)

    def test_18_list_has_detail_links(self):
        _load()
        self.assertIn('href="/packages/{{ m.manifest_code }}"', manifests_tpl)

    def test_19_list_has_empty_state(self):
        _load()
        self.assertIn("empty-state", manifests_tpl)

    def test_20_list_has_backend_error(self):
        _load()
        self.assertIn("backend_error", manifests_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Rendering detail + KSO — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDetailRendering(unittest.TestCase):

    def test_21_detail_has_summary(self):
        _load()
        self.assertIn("Информация", detail_tpl)

    def test_22_detail_has_device_code(self):
        _load()
        self.assertIn("device_code", detail_tpl)

    def test_23_detail_has_status(self):
        _load()
        self.assertIn("Опубликован", detail_tpl)

    def test_24_detail_has_item_count(self):
        _load()
        self.assertIn("Элементов", detail_tpl)

    def test_25_detail_has_body_summary(self):
        _load()
        self.assertIn("Содержимое манифеста", detail_tpl)

    def test_26_detail_has_kso_check_section(self):
        _load()
        self.assertIn("Доступность на КСО", detail_tpl)

    def test_27_detail_has_creative_list(self):
        _load()
        self.assertIn("Коды креативов", detail_tpl)

    def test_28_detail_has_links_block(self):
        _load()
        self.assertIn("Связанные страницы", detail_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 5. KSO check — 5 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestKSOCheck(unittest.TestCase):

    def test_29_served_state_renders(self):
        _load()
        self.assertIn("served", detail_tpl)

    def test_30_no_manifest_state_renders(self):
        _load()
        self.assertIn("no_manifest", detail_tpl)

    def test_31_kso_check_shows_manifest_code(self):
        _load()
        self.assertIn("manifest_code", detail_tpl)

    def test_32_kso_check_shows_item_count(self):
        _load()
        self.assertIn("item_count", detail_tpl)

    def test_33_kso_check_mentions_legacy_endpoint(self):
        _load()
        self.assertIn("legacy", detail_tpl.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 6. Publication integration — 3 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPublicationIntegration(unittest.TestCase):

    def test_34_pub_detail_links_to_manifests(self):
        _load()
        self.assertIn("/packages", pub_detail_tpl)

    def test_35_pub_detail_shows_manifest_link_when_created(self):
        _load()
        self.assertIn("generated_manifest_details", pub_detail_tpl)

    def test_36_pub_detail_manifest_link_has_condition(self):
        _load()
        self.assertIn("generated_manifest_details", pub_detail_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Security — 7 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurity(unittest.TestCase):
    _SENSITIVE = frozenset({
        "password", "access_token", "refresh_token", "Authorization",
        "api_key", "token", "Cookie", "secret",
    })

    def test_37_no_secrets_in_manifests(self):
        _load()
        for key in self._SENSITIVE:
            self.assertNotIn(key.lower(), manifests_tpl.lower())

    def test_38_no_secrets_in_detail(self):
        _load()
        for key in self._SENSITIVE:
            self.assertNotIn(key.lower(), detail_tpl.lower())

    def test_39_no_traceback(self):
        _load()
        self.assertNotIn("Traceback", manifests_tpl)
        self.assertNotIn("Traceback", detail_tpl)

    def test_40_no_localstorage(self):
        _load()
        self.assertNotIn("localStorage", manifests_tpl)
        self.assertNotIn("localStorage", detail_tpl)

    def test_41_no_cdn(self):
        _load()
        for pat in ("cdn.", "unpkg.com", "jsdelivr"):
            self.assertNotIn(pat, manifests_tpl.lower())
            self.assertNotIn(pat, detail_tpl.lower())

    def test_42_no_inline_js(self):
        _load()
        self.assertNotIn("<script", manifests_tpl.lower())
        self.assertNotIn("<script", detail_tpl.lower())

    def test_43_safe_error_used(self):
        _load()
        self.assertIn("_safe_error", main_text)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Boundaries — 8 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaries(unittest.TestCase):

    def test_44_no_backend_changes(self):
        router = (REPO_ROOT / "backend/app/domains/publications/router.py").read_text()
        self.assertIn("get_manifests", router)

    def test_45_no_migrations(self):
        migrations = list((REPO_ROOT / "migrations" / "versions").glob("*.py"))
        self.assertEqual(len(migrations), 0)

    def test_46_no_docker_changes(self):
        compose = (REPO_ROOT / "infra/docker-compose.yml").read_text()
        self.assertIn("rmp-postgres", compose)

    def test_47_no_env_changes(self):
        env = (REPO_ROOT / ".env.example").read_text()
        self.assertIn("POSTGRES", env)

    def test_48_no_manifest_write(self):
        _load()
        section = bc_text.split("KSO Manifest check")[-1].split("create_publication_batch")[0]
        self.assertNotIn("generate_manifest", section)
        self.assertNotIn("POST", section)

    def test_49_no_kso_gateway_changes(self):
        _load()
        self.assertNotIn("gateway", manifests_tpl.lower())

    def test_50_no_production_switch(self):
        _load()
        self.assertNotIn("production", manifests_tpl.lower())
        self.assertNotIn("prod_mode", detail_tpl.lower())

    def test_51_no_ui_redesign(self):
        _load()
        self.assertIn("data-table", manifests_tpl)


# ═══════════════════════════════════════════════════════════════════════════
# 9. Regression — 5 tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRegression(unittest.TestCase):

    def test_52_planning_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/planning": "planning.read"', rbac)

    def test_53_bookings_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/bookings": "bookings.read"', rbac)

    def test_54_publications_unchanged(self):
        rbac = (BASE / "rbac.py").read_text()
        self.assertIn('"/publications": "publications.read"', rbac)

    def test_55_backend_manifest_list_exists(self):
        router = (REPO_ROOT / "backend/app/domains/publications/router.py").read_text()
        self.assertIn("manifest", router.lower())

    def test_56_device_gateway_kso_endpoint_exists(self):
        router = (REPO_ROOT / "backend/app/domains/device_gateway/router.py").read_text()
        self.assertIn("kso_manifest_by_device", router)
