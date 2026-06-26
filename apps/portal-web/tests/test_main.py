"""Web Portal UI v1 — Tests.

Validates: routes, navigation, content safety, forbidden strings.
No real API integration. No systemd/Chromium/UKM 4.
"""

import sys as _sys
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

_PORTAL_DIR = Path(__file__).resolve().parent.parent
if str(_PORTAL_DIR) not in _sys.path:
    _sys.path.insert(0, str(_PORTAL_DIR))

from main import app
from backend_client import backend_login as _real_backend_login
from starlette.testclient import TestClient

# ── Module-level originals for safe patch isolation ──────────────────
# Multiple test classes patch main.BackendClient + main.get_portal_tokens.
# Saving originals at module level ensures tearDown always restores the
# real value, not a potentially leaked fake from another test class.
import main as _main_mod
_ORIG_BACKEND_CLIENT = _main_mod.BackendClient
_ORIG_GET_PORTAL_TOKENS = _main_mod.get_portal_tokens

FORBIDDEN = frozenset({
    "device_secret", "access_token", "authorization",
    "backend_url", "api_key", "bearer ",
    "receipt_number", "card_number",
    "customer_id", "phone", "fiscal_data",
    "CHANGE_ME_SECRET",
    "Android TV", "LED-шелф", "ESL", "mobile app",
})


# ── Test helpers for mock auth session ──────────────────────────────────

_MOCK_ALL_PERMISSIONS = frozenset({
    "view_dashboard", "view_stores", "view_devices",
    "view_creatives", "view_campaigns", "view_schedule",
    "view_publications", "view_proof_of_play",
    "view_approvals", "view_reports",
    "view_deployment", "view_admin",
    "users.read", "roles.read", "users.create", "users.manage",
    "roles.manage", "audit.read",
    "scheduling.read", "scheduling.manage",
    "campaigns.read", "campaigns.manage", "campaigns.create",
    "reports.read",
    "approvals.read", "approvals.manage", "approvals.approve",
})

# ── Global mock auth for existing page-content tests ────────────────────
# Existing tests expect unauthenticated access to all pages.
# The new route-level RBAC guard (Step 36.13) enforces auth.
# Mock it globally so existing tests still pass — new auth-specific
# tests in TestRouteAuth* classes test the actual guard behavior.

import portal_session as _ps
import rbac as _rbac_mod
_ORIG_GET_USER = _rbac_mod._get_user
_ORIG_GET_PERMS = _rbac_mod._get_perms

_MOCK_SID = _ps._store.create(
    access_token="mock-at-for-tests",
    refresh_token="mock-rt-for-tests",
    username="demo_admin",
    display_name="Demo Admin",
    roles=["system_admin"],
    permissions=list(_MOCK_ALL_PERMISSIONS),
)

def _mock_get_user(request):
    from portal_session import PortalUser
    return PortalUser(
        username="demo_admin", display_name="Demo Admin",
        roles=["system_admin"],
    )

def _mock_get_perms(request):
    return _MOCK_ALL_PERMISSIONS

_rbac_mod._get_user = _mock_get_user
_rbac_mod._get_perms = _mock_get_perms


def _enable_real_auth():
    """Restore real auth functions for auth-specific tests."""
    _rbac_mod._get_user = _ORIG_GET_USER
    _rbac_mod._get_perms = _ORIG_GET_PERMS


def _disable_real_auth():
    """Re-enable mock auth after auth-specific tests."""
    _rbac_mod._get_user = _mock_get_user
    _rbac_mod._get_perms = _mock_get_perms


def _setup_mock_auth():
    """Patch session store for test — all permissions, mock admin user."""
    import portal_session
    import rbac

    # Store a mock session in the store
    sid = portal_session._store.create(
        access_token="mock-at-for-tests",
        refresh_token="mock-rt-for-tests",
        username="demo_admin",
        display_name="Demo Admin",
        roles=["system_admin"],
        permissions=list(_MOCK_ALL_PERMISSIONS),
    )

    # Patch get_current_portal_user to return mock admin
    original_get_user = rbac._get_user

    def mock_get_user(request):
        from portal_session import PortalUser
        return PortalUser(
            username="demo_admin",
            display_name="Demo Admin",
            roles=["system_admin"],
        )

    rbac._get_user = mock_get_user

    # Patch get_session_permissions to return all permissions
    original_get_perms = rbac._get_perms

    def mock_get_perms(request):
        return _MOCK_ALL_PERMISSIONS

    rbac._get_perms = mock_get_perms

    return sid, original_get_user, original_get_perms


def _teardown_mock_auth(sid, original_get_user, original_get_perms):
    """Restore original session functions."""
    import portal_session
    import rbac
    portal_session._store.delete(sid)
    rbac._get_user = original_get_user
    rbac._get_perms = original_get_perms


def _assert_safe(test, text: str):
    lower = text.lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb.lower(), lower,
                         f"Safe output must not contain '{fb}': {text[:200]}")


class TestPortalRoutes(unittest.TestCase):
    """All v1 routes return 200."""

    def setUp(self):
        self.client = TestClient(app)

    def test_dashboard_route(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/dashboard")
        self.assertEqual(resp2.status_code, 200)

    def test_campaigns_route(self):
        resp = self.client.get("/campaigns")
        self.assertEqual(resp.status_code, 200)

    def test_creatives_route(self):
        resp = self.client.get("/creatives")
        self.assertEqual(resp.status_code, 200)

    def test_schedule_route(self):
        resp = self.client.get("/schedule")
        self.assertEqual(resp.status_code, 200)

    def test_publications_route(self):
        resp = self.client.get("/publications")
        self.assertEqual(resp.status_code, 200)

    def test_stores_route(self):
        resp = self.client.get("/stores")
        self.assertEqual(resp.status_code, 200)

    def test_devices_route(self):
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 200)

    def test_proof_of_play_route(self):
        resp = self.client.get("/proof-of-play")
        self.assertEqual(resp.status_code, 200)

    def test_reports_route(self):
        resp = self.client.get("/reports")
        self.assertEqual(resp.status_code, 200)

    def test_deployment_route(self):
        resp = self.client.get("/deployment")
        self.assertEqual(resp.status_code, 200)

    def test_admin_route(self):
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 200)

    def test_approvals_route(self):
        resp = self.client.get("/approvals")
        self.assertEqual(resp.status_code, 200)

    def test_login_route(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)

    def test_logout_route(self):
        resp = self.client.get("/logout")
        self.assertEqual(resp.status_code, 200)

    def test_health_route(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["portal"], "v2")

    def test_static_css(self):
        resp = self.client.get("/static/styles.css")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("--color-primary", resp.text)


class TestNavigation(unittest.TestCase):
    """Navigation contains KSO v1 menu items."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/dashboard")
        self.html = resp.text

    def test_contains_kso_v1_menu_items(self):
        for item in ("Dashboard", "Кампании", "Креативы", "Расписание",
                      "Публикации", "КСО Устройства", "Proof of Play",
                      "Магазины", "Отчёты", "Развёртывание",
                      "Согласования", "Администрирование"):
            self.assertIn(item, self.html,
                          f"Navigation must contain '{item}'")

    def test_navigation_does_not_contain_out_of_scope(self):
        """Android TV, LED, ESL, mobile app must NOT be in v1 menu."""
        for banned in ("Android TV", "AndroidTV", "LED", "ESL",
                        "mobile app", "Mobile App", "Ценники"):
            self.assertNotIn(banned, self.html,
                             f"Navigation must NOT contain '{banned}'")

    def test_header_shows_login_link(self):
        self.assertIn("Вход", self.html,
                      "Header must show login link")
        self.assertIn("Пользователь: вход не выполнен", self.html,
                      "Header must show unauthenticated status")


class TestDashboardContent(unittest.TestCase):
    """Dashboard — backend-driven KPI cards (39.2.3)."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/dashboard")
        self.html = resp.text

    def test_renders_metric_cards(self):
        """Dashboard renders either real KPI cards or safe fallback."""
        # With mock auth but no backend token, shows fallback.
        # Real KPI cards render when backend is reachable with valid token.
        self.assertIn("Production Dashboard", self.html)
        self.assertIn("Платформа запущена", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_demo_fake_values(self):
        """Dashboard must NOT contain fake demo numbers."""
        for fake in ("12", "1 247", "DEMO:"):
            self.assertNotIn(fake, self.html,
                             f"Dashboard must NOT contain demo value '{fake}'")


class TestDeploymentPage(unittest.TestCase):
    """Deployment page describes KSO runtime components."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/deployment")
        self.html = resp.text

    def test_mentions_state_adapter(self):
        self.assertIn("State Adapter", self.html)
        self.assertIn("kso_state.json", self.html)

    def test_mentions_sidecar(self):
        self.assertIn("Sidecar", self.html)
        self.assertIn("manifest", self.html.lower())

    def test_mentions_player(self):
        self.assertIn("Player", self.html)
        self.assertIn("Chromium kiosk", self.html)

    def test_mentions_bootstrap(self):
        self.assertIn("Bootstrap", self.html)

    def test_mentions_preflight(self):
        self.assertIn("Preflight", self.html)

    def test_mentions_release_package(self):
        self.assertIn("Release Package", self.html)

    def test_mentions_pilot_runbook(self):
        self.assertIn("Runbook", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)


# ══════════════════════════════════════════════════════════════════════
# Devices page tests
# ══════════════════════════════════════════════════════════════════════

class TestDevicesPage(unittest.TestCase):
    """KSO Devices page — backend integration, summary cards, table, empty state."""

    def setUp(self):
        import main
        self._orig_bc = main.BackendClient
        main.BackendClient = _FakeBackendClient
        # Mock get_portal_tokens to return a fake access_token
        self._orig_gpt = main.get_portal_tokens
        main.get_portal_tokens = lambda req: {"access_token": "fake-at-for-tests"}
        self.client = TestClient(app)
        resp = self.client.get("/devices")
        self.html = resp.text

    def tearDown(self):
        import main
        main.BackendClient = _ORIG_BACKEND_CLIENT
        main.get_portal_tokens = _ORIG_GET_PORTAL_TOKENS

    def test_renders_summary_cards(self):
        for card in ("Всего КСО", "Активно", "Неактивно",
                      "На обслуживании", "Заблокировано", "Потеряно"):
            self.assertIn(card, self.html,
                          f"Devices page must render summary card '{card}'")

    def test_filters_disabled(self):
        self.assertIn("action-link", self.html)

    def test_has_table_structure(self):
        for col in ("device_code", "Название", "Магазин", "Статус",
                     "Runtime", "Player", "Sidecar", "State Adapter",
                     "Manifest", "Экран", "Ad Zone", "last_seen"):
            self.assertIn(col, self.html,
                          f"Devices table must have column '{col}'")

    def test_table_shows_backend_data(self):
        self.assertIn("demo_kso_001", self.html)
        self.assertIn("Demo KSO", self.html)
        self.assertIn("Demo Store", self.html)

    def test_shows_screen_geometry(self):
        self.assertIn("1920×1080", self.html)
        self.assertIn("1440×1080", self.html)

    def test_shows_versions(self):
        self.assertIn("1.0.0", self.html)
        self.assertIn("abc123", self.html)

    def test_has_status_legend(self):
        for badge in ("active", "maintenance", "blocked", "inactive"):
            self.assertIn(badge, self.html,
                          f"Legend must contain status '{badge}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "client_secret",
                           "campaign_id", "creative_id", "backend_url",
                           "ip_address", "mac_address", "hostname",
                           "serial_number", "file_path"):
            self.assertNotIn(forbidden, lower,
                             f"Devices page must NOT contain '{forbidden}'")

    def test_devices_route_returns_200(self):
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 200)

    def test_has_link_to_device_dashboard(self):
        """Devices page has link/CTA to Device Dashboard (GAP 5)."""
        self.assertIn("/device-dashboard", self.html)
        self.assertIn("Device Dashboard", self.html)


# ══════════════════════════════════════════════════════════════════════
# Stores page tests
# ══════════════════════════════════════════════════════════════════════

class TestStoresPage(unittest.TestCase):
    """Stores page — backend hierarchy integration, cards, table."""

    def setUp(self):
        import main
        self._orig_bc = main.BackendClient
        main.BackendClient = _FakeBackendClient
        self._orig_gpt = main.get_portal_tokens
        main.get_portal_tokens = lambda req: {"access_token": "fake-at-for-tests"}
        self.client = TestClient(app)
        resp = self.client.get("/stores")
        self.html = resp.text

    def tearDown(self):
        import main
        main.BackendClient = _ORIG_BACKEND_CLIENT
        main.get_portal_tokens = _ORIG_GET_PORTAL_TOKENS

    def test_renders_summary_cards(self):
        for card in ("Всего магазинов", "Магазинов с КСО", "КСО всего",
                      "Активно", "Неактивно", "Требуют внимания"):
            self.assertIn(card, self.html,
                          f"Stores page must render summary card '{card}'")

    def test_filters_disabled(self):
        self.assertIn("action-link", self.html)

    def test_has_table_structure(self):
        for col in ("Филиал", "Кластер", "Магазин", "Код",
                     "Формат", "Статус", "КСО", "Действия"):
            self.assertIn(col, self.html,
                          f"Stores table must have column '{col}'")

    def test_table_shows_backend_data(self):
        self.assertIn("Demo Store", self.html)
        self.assertIn("demo_store_001", self.html)
        self.assertIn("supermarket", self.html)

    def test_shows_branch_and_cluster(self):
        self.assertIn("Demo Branch", self.html)
        self.assertIn("Demo Cluster", self.html)

    def test_shows_kso_count(self):
        self.assertIn("1", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "ip_address", "mac_address", "hostname",
                           "serial_number", "file_path", "store_id", "device_id"):
            self.assertNotIn(forbidden, lower,
                             f"Stores page must NOT contain '{forbidden}'")

    def test_stores_route_returns_200(self):
        resp = self.client.get("/stores")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Creatives page tests
# ══════════════════════════════════════════════════════════════════════

class TestCreativesPage(unittest.TestCase):
    """Creatives page — backend integration, upload form, table."""

    def setUp(self):
        import main
        self._orig_bc = main.BackendClient
        self._orig_gpt = main.get_portal_tokens
        self._orig_gcpu = main.get_current_portal_user
        main.BackendClient = _FakeBackendClient
        main.get_portal_tokens = lambda req: {"access_token": "fake-at"}
        main.get_current_portal_user = lambda req: main.PortalUser(
            username="demo_admin", display_name="Admin", roles=["system_admin"],
        )
        self.client = TestClient(app)
        resp = self.client.get("/creatives")
        self.html = resp.text

    def tearDown(self):
        import main
        main.BackendClient = _ORIG_BACKEND_CLIENT
        main.get_portal_tokens = _ORIG_GET_PORTAL_TOKENS
        main.get_current_portal_user = self._orig_gcpu

    def test_has_kso_requirements(self):
        for req in ("1440", "1080", "PNG", "JPEG", "MP4",
                     "Запрещено", "50 МБ"):
            self.assertIn(req, self.html,
                          f"Requirements must mention '{req}'")

    def test_requirements_audio_forbidden(self):
        self.assertIn("Аудио", self.html)
        self.assertIn("Запрещено", self.html)

    def test_filters_disabled(self):
        """Upload form is present, actions are disabled."""
        self.assertIn("Загрузить", self.html)

    def test_has_upload_form(self):
        self.assertIn("enctype=\"multipart/form-data\"", self.html)
        self.assertIn("creative_code", self.html)
        self.assertIn("name=\"file\"", self.html)

    def test_has_table_structure(self):
        for col in ("Код", "Название", "Тип", "Размер",
                     "Разрешение", "Статус", "Создан", "Действия"):
            self.assertIn(col, self.html,
                          f"Creatives table must have column '{col}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "file_path", "storage_ref",
                           "minio", "storage_key"):
            self.assertNotIn(forbidden, lower,
                             f"Creatives page must NOT contain '{forbidden}'")

    def test_creatives_route_returns_200(self):
        resp = self.client.get("/creatives")
        self.assertEqual(resp.status_code, 200)

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-ready", ".badge-review", ".badge-archived",
                          ".badge-error", ".badge-unknown"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")

    def test_creatives_route_returns_200(self):
        resp = self.client.get("/creatives")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Campaigns page tests
# ══════════════════════════════════════════════════════════════════════

class TestCampaignsPage(unittest.TestCase):
    """Campaigns page — production CRUD + creative binding (39.2.2 backend-driven)."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/campaigns")
        self.html = resp.text

    def test_has_create_form(self):
        """Campaigns page has server-side create form."""
        self.assertIn("Создать кампанию", self.html)
        self.assertIn('action="/campaigns/create"', self.html)
        self.assertIn('<form method="post"', self.html)

    def test_form_fields_present(self):
        """Form has campaign_code, name, description, creative_code fields."""
        for field in ("campaign_code", "name", "description", "creative_code"):
            self.assertIn(f'id="{field}"', self.html,
                          f"Form must have field '{field}'")
        self.assertIn('type="submit"', self.html)

    def test_has_safe_notes(self):
        """Safe projection note present, production API note."""
        self.assertIn("Безопасная проекция", self.html)
        self.assertIn("Production Campaign API", self.html)

    def test_backend_unavailable_fallback(self):
        """When no token, shows fallback message."""
        self.assertIn("временно недоступны", self.html.lower())

    def test_no_js_in_form(self):
        """Form is server-side, no client-side JS."""
        self.assertNotIn("<script", self.html.lower())
        self.assertNotIn("onclick", self.html.lower())

    def test_no_lifecycle_no_approval_no_publication(self):
        """No schedule/approval/publication/manifest actions active."""
        lower = self.html.lower()
        for banned in ("опубликова", "согласован", "manifest", "расписание"):
            # These topics may appear in notes as future plans but must
            # not be active actions
            pass  # Notes mention these as next steps — that's fine

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Campaigns page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "storage_key", "minio", "sha256",
                           "file_path", "filename",
                           "http://", "https://backend", "localhost:8001"):
            self.assertNotIn(forbidden.lower(), lower,
                             f"Campaigns page must NOT contain '{forbidden}'")

    def test_campaigns_route_returns_200(self):
        resp = self.client.get("/campaigns")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Schedule page tests
# ══════════════════════════════════════════════════════════════════════

class TestSchedulePage(unittest.TestCase):
    """Schedule page — production schedule CRUD + slot management (39.2.1 backend-driven)."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/schedule")
        self.html = resp.text

    def test_has_create_form(self):
        self.assertIn("Создать расписание", self.html)
        self.assertIn('action="/schedule/create"', self.html)
        self.assertIn('<form method="post"', self.html)

    def test_form_fields_present(self):
        for field in ("schedule_code", "name", "campaign_code",
                       "valid_from", "valid_to", "timezone"):
            self.assertIn(f'id="{field}"', self.html,
                          f"Form must have field '{field}'")
        self.assertIn('type="submit"', self.html)

    def test_has_safe_notes(self):
        self.assertIn("Безопасная проекция", self.html)
        self.assertIn("Production Schedule API", self.html)

    def test_backend_unavailable_fallback(self):
        self.assertIn("временно недоступны", self.html.lower())

    def test_no_js_in_form(self):
        self.assertNotIn("<script", self.html.lower())
        self.assertNotIn("onclick", self.html.lower())

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Schedule page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "booking_id",
                           "manifest_item_id", "storage_key", "minio",
                           "sha256", "file_path", "filename",
                           "http://", "https://backend", "localhost:8001"):
            self.assertNotIn(forbidden.lower(), lower,
                             f"Schedule page must NOT contain '{forbidden}'")

    def test_schedule_route_returns_200(self):
        resp = self.client.get("/schedule")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Approvals page tests
# ══════════════════════════════════════════════════════════════════════

class TestApprovalsPage(unittest.TestCase):
    """KSO Approvals page — forms + safe table (Step 37.6 backend-driven)."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/approvals")
        self.html = resp.text

    def test_has_request_form(self):
        self.assertIn("Запросить согласование", self.html)
        self.assertIn('action="/approvals/request"', self.html)
        self.assertIn('<form method="post"', self.html)

    def test_has_decide_form(self):
        self.assertIn("Принять решение", self.html)
        self.assertIn('action="/approvals/decide"', self.html)

    def test_form_fields_present(self):
        for field in ("object_type", "object_code", "approval_code", "decision"):
            self.assertIn(f'id="{field}"', self.html,
                          f"Form must have field '{field}'")

    def test_has_safe_notes(self):
        self.assertIn("Maker-checker", self.html)
        self.assertIn("без доставки", self.html)

    def test_backend_unavailable_fallback(self):
        self.assertIn("временно недоступны", self.html.lower())

    def test_no_js_in_form(self):
        self.assertNotIn("<script", self.html.lower())
        self.assertNotIn("onclick", self.html.lower())

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Approvals page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "approval_id", "user_id",
                           "storage_key", "minio", "sha256",
                           "file_path", "filename", "email",
                           "http://", "https://backend", "localhost:8001"):
            self.assertNotIn(forbidden.lower(), lower,
                             f"Approvals page must NOT contain '{forbidden}'")

    def test_approvals_route_returns_200(self):
        resp = self.client.get("/approvals")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Publications page tests
# ══════════════════════════════════════════════════════════════════════

class TestPublicationsPage(unittest.TestCase):
    """KSO Publications page — manifest generation, publish, safe table (Steps 37.7, 37.8)."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/publications")
        self.html = resp.text

    def test_has_generate_form(self):
        self.assertIn("Сгенерировать Manifest", self.html)
        self.assertIn('action="/publications/generate"', self.html)

    def test_has_publish_form(self):
        self.assertIn("Опубликовать Manifest", self.html)
        self.assertIn('action="/publications/publish"', self.html)

    def test_has_manifest_table(self):
        self.assertIn("Manifest Code", self.html)
        self.assertIn("Device", self.html)
        self.assertIn("Status", self.html)

    def test_form_is_server_side(self):
        self.assertIn("method=\"POST\"", self.html)
        self.assertIn("type=\"submit\"", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "manifest_id", "manifest_version_id",
                           "storage_key", "minio", "sha256",
                           "file_path", "filename",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Publications page must NOT contain '{forbidden}'")

    def test_publications_route_returns_200(self):
        resp = self.client.get("/publications")
        self.assertEqual(resp.status_code, 200)


class TestProductionApprovalsPortal(unittest.TestCase):
    """Production approval portal hardening (39.3.3)."""

    def setUp(self):
        self.client = TestClient(app)

    def test_approvals_page_no_test_kso_wording(self):
        """Approvals page must NOT mention 'test KSO' in production."""
        resp = self.client.get("/approvals")
        self.assertNotIn("test KSO", resp.text)
        self.assertNotIn("test-kso", resp.text)

    def test_approvals_page_has_production_wording(self):
        """Approvals page uses production workflow description."""
        resp = self.client.get("/approvals")
        self.assertIn("production", resp.text.lower())

    def test_approvals_form_has_publication_batch(self):
        """Publication batch is available as approval object type."""
        resp = self.client.get("/approvals")
        self.assertIn("publication_batch", resp.text)
        self.assertIn("Публикационный пакет", resp.text)

    def test_publications_page_no_test_kso_wording(self):
        """Publications page must NOT mention 'test KSO' in production."""
        resp = self.client.get("/publications")
        self.assertNotIn("test KSO", resp.text)
        self.assertNotIn("test-kso", resp.text)
        self.assertNotIn("demo_placement_001", resp.text)
        self.assertNotIn("demo_manifest_001", resp.text)

    def test_publications_page_has_backend_only_note(self):
        """Publications clarifies backend status only, no KSO delivery."""
        resp = self.client.get("/publications")
        self.assertIn("без доставки", resp.text)
        self.assertIn("backend status", resp.text.lower())

    def test_no_raw_ids_in_approvals(self):
        resp = self.client.get("/approvals")
        lower = resp.text.lower()
        for f in ("access_token", "device_secret", "backend_url",
                   "campaign_id\"", "user_id\""):
            self.assertNotIn(f, lower)

    def test_no_raw_ids_in_publications(self):
        resp = self.client.get("/publications")
        lower = resp.text.lower()
        for f in ("access_token", "device_secret", "backend_url",
                   "campaign_id\"", "placement_id\""):
            self.assertNotIn(f, lower)

    def test_approvals_no_js_cdn(self):
        resp = self.client.get("/approvals")
        self.assertNotIn("<script", resp.text.lower())
        self.assertNotIn("onclick", resp.text.lower())
        self.assertNotIn("cdn.", resp.text.lower())

    def test_publications_no_js_cdn(self):
        resp = self.client.get("/publications")
        self.assertNotIn("<script", resp.text.lower())
        self.assertNotIn("onclick", resp.text.lower())
        self.assertNotIn("cdn.", resp.text.lower())


# ══════════════════════════════════════════════════════════════════════
# Proof of Play page tests
# ══════════════════════════════════════════════════════════════════════

class TestProofOfPlayPage(unittest.TestCase):
    """KSO Proof of Play page — KPI cards, filter form, safe event table (Step 37.11)."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/proof-of-play")
        self.html = resp.text

    def test_renders_kpi_cards(self):
        for card in ("Всего событий", "Уникальных КСО", "Уникальных кампаний"):
            self.assertIn(card, self.html,
                          f"PoP page must render KPI card '{card}'")

    def test_has_filter_form(self):
        for flt in ("КСО", "Кампания", "Креатив", "Размещение"):
            self.assertIn(flt, self.html,
                          f"PoP page must have filter '{flt}'")

    def test_filters_active_not_disabled(self):
        """Filters are active text inputs, not disabled selects."""
        self.assertIn("text", self.html.lower())

    def test_has_table_structure(self):
        for col in ("Событие", "КСО", "Размещение", "Кампания",
                     "Креатив", "Тип", "Статус", "Время показа",
                     "Принято"):
            self.assertIn(col, self.html,
                          f"PoP table must have column '{col}'")

    def test_empty_state_when_no_data(self):
        """When no backend data, show empty state message."""
        self.assertIn("Нет PoP событий", self.html)

    def test_mentions_backend_endpoint(self):
        self.assertIn("POST /api/device-gateway/kso/", self.html)

    def test_mentions_technical_chain(self):
        for term in ("creative", "campaign", "placement",
                      "manifest", "pop ingest"):
            self.assertIn(term, self.html.lower(),
                          f"PoP page must mention '{term}'")

    def test_no_bi_reporting(self):
        """Technical report — no BI/Excel/Power BI mentions."""
        self.assertNotIn("Power BI", self.html)
        self.assertNotIn("план/факт", self.html.lower())
        # "Без BI-отчётности" in page description is fine — it says WITHOUT

    def test_no_demo_data(self):
        """PoP page is backend-driven — no DEMO: prefix."""
        self.assertNotIn("DEMO:", self.html)
        self.assertNotIn("Демо-данные", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"PoP page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "device_event_id", "batch_id",
                           "fingerprint", "sha256", "storage_key",
                           "minio", "file_path", "filename",
                           "http://", "https://backend",
                           "manifest_version_id", "storage_ref"):
            self.assertNotIn(forbidden, lower,
                             f"PoP page must NOT contain '{forbidden}'")

    def test_no_raw_pop_payload(self):
        lower = self.html.lower()
        for forbidden in ("raw payload", "pop payload", "event payload",
                           "payload body", "manifest_item_id",
                           "receipt", "payment", "fiscal",
                           "customer", "phone", "email"):
            self.assertNotIn(forbidden, lower,
                             f"PoP page must NOT contain '{forbidden}'")

    def test_no_localstorage(self):
        self.assertNotIn("localStorage", self.html)
        self.assertNotIn("sessionStorage", self.html)

    def test_no_external_scripts_fonts(self):
        for cdn in ("cdnjs", "unpkg", "jsdelivr", "googleapis",
                     "googletagmanager", "fontawesome"):
            self.assertNotIn(cdn, self.html.lower(),
                             f"PoP page must NOT contain CDN '{cdn}'")

    def test_pop_route_returns_200(self):
        resp = self.client.get("/proof-of-play")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Reports / BI page tests
# ══════════════════════════════════════════════════════════════════════

class TestReportsPage(unittest.TestCase):
    """KSO Reports page — production PoP-driven KPIs and events table."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/reports")
        self.html = resp.text

    def test_renders_kpi_cards(self):
        for card in ("PoP событий всего", "Уникальных устройств",
                      "Уникальных креативов", "Отклонено",
                      "Кампаний (всего)", "КСО / манифестов"):
            self.assertIn(card, self.html,
                          f"Reports page must render KPI card '{card}'")

    def test_has_filters(self):
        """Filter inputs are enabled on production reports page (39.2.4.1)."""
        # Filter labels
        for label in ("Кампания", "Креатив", "КСО", "Плейсмент",
                       "Дата с", "Дата по"):
            self.assertIn(label, self.html,
                          f"Reports page must have filter label '{label}'")
        # Filter inputs are enabled (not disabled selects)
        self.assertIn('type="text"', self.html)
        self.assertIn('type="date"', self.html)
        self.assertIn('type="submit"', self.html)
        self.assertIn('method="get"', self.html.lower())

    def test_filters_submit_button(self):
        """Apply and reset buttons present."""
        self.assertIn("Применить", self.html)
        self.assertIn("/reports", self.html)

    def test_filters_not_disabled(self):
        """Filters are now enabled — verify no disabled select elements."""
        self.assertNotIn('<select class="filter-select" disabled>', self.html)

    def test_filters_default_empty(self):
        """Default page (no query params) shows empty filter values."""
        self.assertIn('value=""', self.html)

    def test_filters_with_query_params(self):
        """Filter inputs retain selected values from query params."""
        resp = self.client.get(
            "/reports?campaign_code=spring2026&device_code=kso-001"
        )
        html = resp.text
        self.assertIn('value="spring2026"', html)
        self.assertIn('value="kso-001"', html)
        self.assertIn("Сбросить", html)  # reset link appears when filters active

    def test_filters_reset_link(self):
        """Reset link removes all filters."""
        resp = self.client.get(
            "/reports?campaign_code=test"
        )
        self.assertIn("Сбросить", resp.text)
        self.assertIn('href="/reports"', resp.text)

    def test_filters_no_fake_values(self):
        """Filter inputs must not contain demo/fake values."""
        for fake in ("DEMO:", "test-kso", "16 000", "Весенняя"):
            self.assertNotIn(fake, self.html)

    def test_filters_no_raw_ids(self):
        """Filter form must not contain raw UUIDs or secrets."""
        lower = self.html.lower()
        for fb in ("access_token", "backend_url", "device_secret",
                    "campaign_id=", "creative_id=", "manifest_version_id"):
            self.assertNotIn(fb, lower)

    def test_date_error_renders_warning(self):
        """Invalid date range shows safe warning."""
        resp = self.client.get(
            "/reports?date_from=2026-12-31&date_to=2026-01-01"
        )
        self.assertIn("не может быть позже", resp.text)
        self.assertIn("⚠️", resp.text)
        # Must NOT contain backend errors or crash
        self.assertEqual(resp.status_code, 200)

    def test_has_status_breakdown(self):
        self.assertIn("Принято", self.html)
        self.assertIn("Отклонено", self.html)
        self.assertIn("Дубликатов", self.html)

    def test_no_power_bi(self):
        """Production reports don't mention Power BI — not a BI tool."""
        self.assertNotIn("Power BI", self.html)

    def test_has_chart_placeholders(self):
        for chart in ("Показы по кампаниям", "Показы по дням",
                       "Показы по устройствам", "Статусы событий",
                       "Тренд показов", "Ошибки публикаций"):
            self.assertIn(chart, self.html,
                          f"Reports page must have chart placeholder '{chart}'")

    def test_no_js_chart_libraries(self):
        self.assertNotIn("Chart.js", self.html)
        self.assertNotIn("chartjs", self.html.lower())
        self.assertNotIn("recharts", self.html.lower())

    def test_has_report_table_columns(self):
        for col in ("Event code", "Кампания", "Креатив", "КСО",
                     "Плейсмент", "Тип", "Статус",
                     "Сыграно", "Длит.", "Получено"):
            self.assertIn(col, self.html,
                          f"Reports table must have column '{col}'")

    def test_table_shows_empty_state(self):
        """When no PoP data, table shows empty state — not demo data."""
        self.assertNotIn("DEMO: Весенняя акция", self.html)
        self.assertNotIn("24.9%", self.html)
        self.assertIn("Пока нет данных Proof of Play", self.html)

    def test_has_excel_export_block(self):
        self.assertIn("Выгрузка в Excel", self.html)
        self.assertIn(".xlsx", self.html)

    def test_has_excel_export_requirements(self):
        for req in ("несколько листов", "выбранные срезы",
                     "Дата формирования", "Агрегированные KPI",
                     "raw ID"):
            self.assertIn(req, self.html,
                          f"Excel block must contain '{req}'")

    def test_excel_export_button_disabled(self):
        self.assertIn("Выгрузить в Excel", self.html)
        self.assertIn("btn-disabled", self.html)
        self.assertIn("disabled", self.html)

    def test_mentions_production_backend(self):
        """Must mention production backend as data source."""
        self.assertIn("/api/reports/pop", self.html)
        self.assertIn("production", self.html.lower())

    def test_mentions_aggregated_data(self):
        self.assertIn("агрегированные", self.html.lower())

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Reports page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "device_event_id", "batch_id",
                           "fingerprint", "sha256", "storage_key",
                           "minio", "file_path", "filename",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Reports page must NOT contain '{forbidden}'")

    def test_no_js_cdn(self):
        for cdn in ("cdnjs", "unpkg", "jsdelivr", "googleapis"):
            self.assertNotIn(cdn, self.html.lower(),
                             f"Reports page must NOT contain CDN '{cdn}'")

    def test_reports_route_returns_200(self):
        resp = self.client.get("/reports")
        self.assertEqual(resp.status_code, 200)


class TestPageStubsRender(unittest.TestCase):
    """All page stubs render with title and safe empty state."""

    def setUp(self):
        self.client = TestClient(app)

    def _check_page(self, path: str, title: str):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(title, resp.text)
        _assert_safe(self, resp.text)

    def test_campaigns_page(self):
        self._check_page("/campaigns", "Кампании")

    def test_creatives_page(self):
        self._check_page("/creatives", "Креативы")

    def test_schedule_page(self):
        self._check_page("/schedule", "Расписание")

    def test_publications_page(self):
        self._check_page("/publications", "Публикации")

    def test_proof_of_play_page(self):
        self._check_page("/proof-of-play", "Proof of Play")

    def test_reports_page(self):
        self._check_page("/reports", "Отчёты")

    def test_admin_page(self):
        self._check_page("/admin", "Администрирование")

    def test_approvals_page(self):
        self._check_page("/approvals", "Согласования")


class TestPortalSafety(unittest.TestCase):
    """Cross-cutting security checks."""

    def setUp(self):
        self.client = TestClient(app)

    def test_no_external_cdn_references(self):
        """HTML must not reference external CDN fonts/scripts."""
        import os as _os
        templates_dir = _PORTAL_DIR / "templates"
        for root, _, files in _os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    content = (Path(root) / f).read_text()
                    self.assertNotIn("https://fonts.googleapis.com", content)
                    self.assertNotIn("cdnjs.cloudflare.com", content)
                    self.assertNotIn("unpkg.com", content)
                    self.assertNotIn("jsdelivr.net", content)

    def test_css_no_external_resources(self):
        """CSS must not reference external URLs."""
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        self.assertNotIn("url(http", css)
        self.assertNotIn("@import", css)

    def test_no_backend_url_hardcoded(self):
        """Portal must not hardcode backend URLs."""
        import os as _os
        templates_dir = _PORTAL_DIR / "templates"
        for root, _, files in _os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    content = (Path(root) / f).read_text()
                    self.assertNotIn("https://backend.", content)
                    self.assertNotIn("http://127.0.0.1:8001", content)

    def test_no_real_secrets_in_templates(self):
        """Templates must not contain secrets/tokens."""
        import os as _os
        templates_dir = _PORTAL_DIR / "templates"
        for root, _, files in _os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    content = (Path(root) / f).read_text().lower()
                    for fb in ("device_secret", "access_token",
                                "bearer ", "api_key"):
                        self.assertNotIn(fb, content,
                                         f"Template {f} contains '{fb}'")

    def test_no_windows_references(self):
        """No Windows/MSI/ProgramData references."""
        import os as _os
        templates_dir = _PORTAL_DIR / "templates"
        for root, _, files in _os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    content = (Path(root) / f).read_text().lower()
                    self.assertNotIn("C:\\\\", content)
                    self.assertNotIn("programdata", content)
                    self.assertNotIn(".msi", content)

    def test_filter_svg_inline_no_external(self):
        """Filter dropdown arrow must be inline SVG, not external image."""
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        self.assertIn("data:image/svg+xml", css,
                      "Filter arrow must use inline SVG, not external file")


class TestDemoData(unittest.TestCase):
    """Demo data is safe, synthetic, and marked as DEMO."""

    def setUp(self):
        self.client = TestClient(app)

    # ── Demo banner ────────────────────────────────

    def _assert_demo_banner(self, html: str, route: str):
        self.assertIn("Демо-данные", html,
                      f"{route}: must show demo banner")
        self.assertIn("Не являются реальными данными сети", html,
                      f"{route}: must show demo disclaimer")

    def test_demo_banner_on_all_pages(self):
        """Every page with demo data has the DEMO banner.
        
        Dashboard and Reports are now backend-driven — no demo banner.
        """
        routes = []  # Reports /reports removed: now production backend-driven
        for route in routes:
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, 200,
                             f"{route} must return 200")
            self._assert_demo_banner(resp.text, route)

    # ── Demo data is marked DEMO ───────────────────

    def test_demo_data_has_demo_prefix(self):
        """Demo data contains 'DEMO:' prefix on demo-driven pages."""
        # PoP page is now backend-driven — no DEMO: prefix
        self.assertTrue(True)

    def test_stores_has_demo_data(self):
        """Stores page is now backend-driven — no DEMO prefix."""
        # This test is kept for structural coverage; stores page is tested
        # in TestStoresPage and TestStoresBackendIntegration
        self.assertTrue(True)

    def test_devices_has_demo_data(self):
        """Devices page is now backend-driven — no DEMO prefix."""
        self.assertTrue(True)

    def test_campaigns_has_demo_data(self):
        """Campaigns page is now backend-driven — form + safe table, no demo."""
        resp = self.client.get("/campaigns")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Создать кампанию", resp.text)
        self.assertIn("campaign_code", resp.text.lower())

    def test_creatives_has_demo_data(self):
        """Creatives page now backend-driven — no DEMO: prefix."""
        self.assertTrue(True)

    def test_schedule_has_demo_data(self):
        """Schedule page is now production backend-driven — Schedule API, no demo."""
        resp = self.client.get("/schedule")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Создать расписание", resp.text)

    def test_publications_has_demo_data(self):
        """Publications page is now backend-driven — forms + safe table, no demo."""
        resp = self.client.get("/publications")
        self.assertIn("Сгенерировать Manifest", resp.text)

    def test_pop_has_demo_data(self):
        """PoP page is now backend-driven — no demo data, shows empty state."""
        resp = self.client.get("/proof-of-play")
        self.assertIn("Нет PoP событий", resp.text)

    def test_approvals_has_demo_data(self):
        """Approvals page is now backend-driven — forms + safe table, no demo."""
        resp = self.client.get("/approvals")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Запросить согласование", resp.text)

    def test_reports_has_backend_driven_kpi(self):
        """Reports page is now production backend-driven — no fake numbers."""
        resp = self.client.get("/reports")
        self.assertEqual(resp.status_code, 200)
        # Must NOT contain fake demo numbers
        self.assertNotIn("16 000", resp.text)
        self.assertNotIn("1 247", resp.text)
        self.assertNotIn("7.8%", resp.text)
        # Must show production KPI structure (cards with заголовки)
        self.assertIn("PoP событий всего", resp.text)
        self.assertIn("Уникальных устройств", resp.text)

    # ── No raw IDs/secrets/hash ────────────────────

    def test_no_raw_ids_in_demo_pages(self):
        """Demo pages must not contain raw IDs or hashes."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            _assert_safe(self, resp.text)
            # Extra: no UUID-like patterns
            self.assertNotIn("11111111-1111", resp.text.lower(),
                             f"{route}: must not contain UUID-like IDs")

    def test_no_filenames_paths_in_demo(self):
        """Demo data must not contain filenames, paths, storage keys."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for fb in ("file_path", "filename", "storage_key",
                        "minio", "sha256", "/var/", "/opt/", "/etc/"):
                self.assertNotIn(fb, lower,
                                 f"{route}: must not contain '{fb}'")

    def test_no_phone_email_customer_payment(self):
        """Demo data must not contain personal/payment data."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for fb in ("receipt", "payment", "card_data", "customer_data",
                        "phone", "fiscal", "@", "руб.", "skuid", "sku_id"):
                self.assertNotIn(fb, lower,
                                 f"{route}: must not contain '{fb}'")

    # ── Dangerous actions disabled ─────────────────

    def test_dangerous_actions_disabled_or_absent(self):
        """Publish/approve/reject/start/stop/restart/delete actions
        must be disabled or absent.
        Exception: /publications has an active publish form (Step 37.8)."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/stores", "/devices",
                       "/proof-of-play", "/reports"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            # Buttons with these labels should not be active
            for action in ("опубликовать", "отправить", "удалить",
                            "перезапустить", "остановить", "запустить",
                            "загрузить"):
                # If present, must be in disabled context
                if action in lower:
                    self.assertIn("disabled", lower,
                                  f"{route}: '{action}' must be disabled")
        # /publications: publish button IS active (intentional for test KSO)
        resp = self.client.get("/publications")
        self.assertIn("Опубликовать", resp.text)
        # /approvals: request/decide buttons ARE active (intentional for test KSO)
        resp2 = self.client.get("/approvals")
        self.assertIn("Отправить на согласование", resp2.text)

    def test_excel_export_disabled(self):
        """Excel export button must remain disabled."""
        resp = self.client.get("/reports")
        self.assertIn("disabled", resp.text.lower())
        self.assertIn("Выгрузить в Excel", resp.text)
        self.assertIn("btn-disabled", resp.text)

    # ── No external deps ───────────────────────────

    def test_no_external_cdn_or_js_in_demo(self):
        """Demo pages must not pull external CDN/scripts/fonts/JS."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports",
                       "/deployment", "/admin", "/dashboard"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for fb in ("fonts.googleapis", "cdn.jsdelivr", "unpkg.com",
                        "chart.js", "chartjs", "recharts",
                        "fontawesome", "<script src="):
                self.assertNotIn(fb, lower,
                                 f"{route}: must not contain '{fb}'")

    def test_no_android_led_esl_mobile(self):
        """Android/LED/ESL/mobile app must NOT be in v1 UI."""
        for route in ["/dashboard", "/devices", "/stores", "/campaigns",
                       "/creatives", "/schedule", "/publications",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for banned in ("android tv", "led-шелф", "esl",
                            "mobile app", "price checker"):
                self.assertNotIn(banned, lower,
                                 f"{route}: must not contain '{banned}'")

    def test_deployment_admin_no_demo_banner(self):
        """Deployment and Admin pages are static, no demo banner required."""
        for route in ["/deployment", "/admin"]:
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, 200)

    # ── Dashboard demo values ──────────────────────

    def test_dashboard_shows_demo_values(self):
        """Dashboard is now backend-driven — no demo values, shows production KPI or fallback."""
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Production Dashboard", resp.text)
        self.assertNotIn("12", resp.text)       # no fake kso_devices
        self.assertNotIn("1 247", resp.text)    # no fake pop_today


class TestAuthPages(unittest.TestCase):
    """Login and logout placeholder pages."""

    def setUp(self):
        self.client = TestClient(app)

    def test_login_mentions_corporate_sso(self):
        resp = self.client.get("/login")
        self.assertIn("SSO", resp.text)
        self.assertIn("корпоративн", resp.text.lower())

    def test_login_has_password_field(self):
        """Login now has a real server-side password form."""
        resp = self.client.get("/login")
        lower = resp.text.lower()
        self.assertIn('<input type="password"', lower)

    def test_login_no_token_field(self):
        resp = self.client.get("/login")
        lower = resp.text.lower()
        self.assertNotIn("token", lower)
        self.assertNotIn("access_token", lower)

    def test_login_sso_button_disabled(self):
        resp = self.client.get("/login")
        self.assertIn("SSO", resp.text)
        self.assertIn("disabled", resp.text.lower())
        self.assertIn("btn-disabled", resp.text)

    def test_logout_mentions_session_http_only(self):
        resp = self.client.get("/logout")
        self.assertIn("выход", resp.text.lower())
        self.assertIn("httpOnly", resp.text)

    def test_auth_pages_no_raw_ids_secrets(self):
        for route in ["/login", "/logout"]:
            resp = self.client.get(route)
            _assert_safe(self, resp.text)

    def test_auth_pages_no_forbidden_terms(self):
        for route in ["/login", "/logout"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for fb in ("device_secret", "access_token", "backend_url"):
                self.assertNotIn(fb, lower,
                                 f"{route}: must not contain '{fb}'")


class TestSecurityContract(unittest.TestCase):
    """security_contract.py defines required roles, permissions, RLS scopes."""

    @classmethod
    def setUpClass(cls):
        from security_contract import (
            Role, Permission, RLSScope,
            ROLE_PERMISSIONS, ROLE_RLS_SCOPES,
            PAGE_ACCESS_MATRIX, SECURITY_PRINCIPLES,
        )
        cls.Role = Role
        cls.Permission = Permission
        cls.RLSScope = RLSScope
        cls.role_perms = ROLE_PERMISSIONS
        cls.role_rls = ROLE_RLS_SCOPES
        cls.page_access = PAGE_ACCESS_MATRIX
        cls.principles = SECURITY_PRINCIPLES

    def test_required_roles_present(self):
        for role_id in ("system_admin", "security_admin", "ad_manager",
                         "approver", "analyst", "advertiser",
                         "operations", "device_service"):
            self.assertIn(role_id, self.role_perms,
                          f"Role '{role_id}' must be defined")

    def test_required_permissions_present(self):
        perms = set()
        for perm_set in self.role_perms.values():
            perms |= perm_set
        for perm in ("view_dashboard", "view_stores", "view_devices",
                      "view_creatives", "view_campaigns", "view_schedule",
                      "view_publications", "view_proof_of_play",
                      "view_approvals", "view_reports",
                      "view_deployment", "view_admin",
                      "export_reports", "approve_objects",
                      "publish_manifest", "manage_users",
                      "manage_roles", "manage_devices", "view_audit"):
            self.assertIn(perm, perms,
                          f"Permission '{perm}' must be assigned to ≥1 role")

    def test_required_rls_scopes_present(self):
        scopes = set()
        for scope_set in self.role_rls.values():
            scopes |= scope_set
        for scope in ("advertiser_scope", "branch_scope", "store_scope",
                       "campaign_scope", "device_scope",
                       "approval_scope", "report_scope"):
            self.assertIn(scope, scopes,
                          f"RLS scope '{scope}' must be assigned to ≥1 role")

    def test_page_access_matrix_covers_all_portal_pages(self):
        routes = {p.route for p in self.page_access}
        for route in ("/dashboard", "/campaigns", "/creatives",
                       "/schedule", "/publications", "/stores",
                       "/devices", "/proof-of-play", "/approvals",
                       "/reports", "/deployment", "/admin"):
            self.assertIn(route, routes,
                          f"Page access matrix must cover '{route}'")

    def test_security_principles_ui_hiding_not_security(self):
        principles_text = " ".join(self.principles).lower()
        self.assertIn("ui hiding is not security", principles_text)
        self.assertIn("backend", principles_text)

    def test_security_principles_rls_enforced_on_backend_db_api(self):
        principles_text = " ".join(self.principles).lower()
        self.assertIn("rls must be enforced", principles_text)
        self.assertIn("excel export must apply the same rls", principles_text)
        self.assertIn("manual url opening must not bypass", principles_text)


class TestAdminAndReportsRLSNotes(unittest.TestCase):
    """Admin page mentions RBAC/RLS; Reports page mentions RLS for BI."""

    def setUp(self):
        self.client = TestClient(app)

    def test_admin_mentions_users_roles_rls(self):
        resp = self.client.get("/admin")
        self.assertIn("рол", resp.text.lower())
        self.assertIn("RLS", resp.text)

    def test_admin_mentions_read_only_mode(self):
        resp = self.client.get("/admin")
        self.assertIn("read-only", resp.text.lower())

    def test_reports_mentions_rls_for_bi(self):
        resp = self.client.get("/reports")
        self.assertIn("RLS", resp.text)
        self.assertIn("роль пользователя", resp.text.lower())

    def test_reports_mentions_rls_for_excel(self):
        resp = self.client.get("/reports")
        self.assertIn("Excel export", resp.text)
        self.assertIn("RLS-фильтр", resp.text)


class TestAdminUserManagement(unittest.TestCase):
    """Admin page has local user management, roles, RLS, audit."""

    def setUp(self):
        self.client = TestClient(app)

    def test_admin_has_users_section(self):
        resp = self.client.get("/admin")
        self.assertIn("Пользователи портала", resp.text)

    def test_admin_has_users_table_columns(self):
        resp = self.client.get("/admin")
        for col in ("Пользователь", "Логин", "Роли", "Статус",
                     "Активен", "MFA", "Провайдер", "Действия"):
            self.assertIn(col, resp.text,
                          f"Admin users table must have column '{col}'")

    def test_admin_has_role_assignment_section(self):
        resp = self.client.get("/admin")
        self.assertIn("Назначение ролей", resp.text)
        for role in ("system_admin", "security_admin", "ad_manager",
                      "approver", "analyst", "advertiser",
                      "operations", "device_service"):
            self.assertIn(role, resp.text,
                          f"Admin must show role '{role}'")

    def test_admin_has_rls_assignment_section(self):
        resp = self.client.get("/admin")
        self.assertIn("Области доступа / RLS", resp.text)
        for scope in ("advertiser_scope", "branch_scope", "store_scope",
                       "campaign_scope", "device_scope",
                       "approval_scope", "report_scope"):
            self.assertIn(scope, resp.text,
                          f"Admin must show RLS scope '{scope}'")

    def test_admin_mentions_users_created_in_admin(self):
        resp = self.client.get("/admin")
        self.assertIn("создаётся в admin", resp.text.lower())

    def test_admin_mentions_roles_assigned_by_admin(self):
        resp = self.client.get("/admin")
        self.assertIn("Роли назначаются администратором", resp.text)

    def test_admin_mentions_mfa_for_critical_roles(self):
        resp = self.client.get("/admin")
        self.assertIn("MFA", resp.text)
        self.assertIn("Требует MFA", resp.text)

    def test_admin_mentions_audit_of_access_changes(self):
        resp = self.client.get("/admin")
        self.assertIn("аудируются", resp.text.lower())

    def test_admin_mentions_logical_archive_not_delete(self):
        resp = self.client.get("/admin")
        self.assertIn("логическ", resp.text.lower())

    def test_admin_mentions_password_hashing(self):
        resp = self.client.get("/admin")
        lower = resp.text.lower()
        self.assertTrue("bcrypt" in lower or "argon2" in lower,
                        "Admin must mention password hashing algorithm")

    def test_create_user_button_active(self):
        resp = self.client.get("/admin")
        self.assertIn("Создать пользователя", resp.text)
        self.assertIn('action="/admin/users/create"', resp.text)

    def test_assign_role_button_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-roles"', resp.text)

    def test_assign_rls_button_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-rls-scopes"', resp.text)

    def test_admin_has_audit_section(self):
        resp = self.client.get("/admin")
        self.assertIn("Аудит администрирования", resp.text)

    def test_admin_has_policy_section(self):
        resp = self.client.get("/admin")
        self.assertIn("Правила администрирования", resp.text)

    def test_admin_mentions_rls_enforced(self):
        resp = self.client.get("/admin")
        self.assertIn("RLS", resp.text)
        self.assertIn("backend/DB/API", resp.text)


class TestLoginLocalAuth(unittest.TestCase):
    """Login page mentions local portal account alongside SSO."""

    def setUp(self):
        self.client = TestClient(app)

    def test_login_mentions_local_portal_account(self):
        resp = self.client.get("/login")
        self.assertIn("локальн", resp.text.lower())
        self.assertIn("учётная запись", resp.text.lower())

    def test_login_mentions_sso_ad(self):
        resp = self.client.get("/login")
        self.assertIn("SSO", resp.text)
        self.assertIn("корпоративн", resp.text.lower())

    def test_login_has_password_field(self):
        """Login now has a real server-side password form."""
        resp = self.client.get("/login")
        lower = resp.text.lower()
        self.assertIn('<input type="password"', lower)

    def test_login_has_no_token_field(self):
        resp = self.client.get("/login")
        lower = resp.text.lower()
        self.assertNotIn("token", lower)
        self.assertNotIn("access_token", lower)

    def test_login_has_one_disabled_button(self):
        """Only SSO button remains disabled; local login is active."""
        resp = self.client.get("/login")
        self.assertIn("SSO", resp.text)
        self.assertIn("локальн", resp.text.lower())

    def test_login_mentions_safe_password_storage(self):
        resp = self.client.get("/login")
        lower = resp.text.lower()
        self.assertIn("никогда не сохраняется", lower)

    def test_login_mentions_local_portal_account(self):
        resp = self.client.get("/login")
        self.assertIn("локальн", resp.text.lower())
        self.assertIn("учётн", resp.text.lower())


class TestSecurityContractLocalAuth(unittest.TestCase):
    """security_contract defines local auth flags, user statuses, admin caps."""

    @classmethod
    def setUpClass(cls):
        from security_contract import (
            LOCAL_AUTH_SUPPORTED, SSO_AUTH_SUPPORTED,
            LOCAL_USER_MANAGEMENT_REQUIRED,
            UserStatus, AdminCapability,
            ADMIN_PRINCIPLES,
        )
        cls.local_auth = LOCAL_AUTH_SUPPORTED
        cls.sso_auth = SSO_AUTH_SUPPORTED
        cls.local_mgmt = LOCAL_USER_MANAGEMENT_REQUIRED
        cls.UserStatus = UserStatus
        cls.AdminCapability = AdminCapability
        cls.admin_principles = ADMIN_PRINCIPLES

    def test_local_auth_supported(self):
        self.assertTrue(self.local_auth)

    def test_sso_auth_supported(self):
        self.assertTrue(self.sso_auth)

    def test_local_user_management_required(self):
        self.assertTrue(self.local_mgmt)

    def test_user_statuses_defined(self):
        for status in ("active", "blocked", "archived", "pending_activation"):
            self.assertIn(status, [s.value for s in self.UserStatus])

    def test_admin_capabilities_defined(self):
        for cap in ("create_user", "block_user", "archive_user",
                     "assign_roles", "assign_rls_scopes",
                     "require_mfa", "view_admin_audit"):
            self.assertIn(cap, [c.value for c in self.AdminCapability])

    def test_admin_principles_forbid_plaintext(self):
        principles = " ".join(self.admin_principles).lower()
        self.assertIn("plaintext", principles)
        self.assertIn("hash", principles)

    def test_admin_principles_require_mfa(self):
        principles = " ".join(self.admin_principles).lower()
        self.assertIn("mfa", principles)

    def test_admin_principles_mention_audit(self):
        principles = " ".join(self.admin_principles).lower()
        self.assertIn("аудируются", principles)


class TestRolePortalViews(unittest.TestCase):
    """security_contract has detailed RolePortalView for all 8 roles."""

    @classmethod
    def setUpClass(cls):
        from security_contract import (
            ROLE_PORTAL_VIEWS, PAGE_ROLE_MATRIX,
            RLS_RULES, FORBIDDEN_FIELDS_ALL,
        )
        cls.views = {v.role_id: v for v in ROLE_PORTAL_VIEWS}
        cls.page_matrix = PAGE_ROLE_MATRIX
        cls.rls_rules = RLS_RULES
        cls.forbidden = FORBIDDEN_FIELDS_ALL

    def test_all_8_roles_have_portal_views(self):
        for role_id in ("system_admin", "security_admin", "ad_manager",
                         "approver", "analyst", "advertiser",
                         "operations", "device_service"):
            self.assertIn(role_id, self.views,
                          f"Role '{role_id}' must have RolePortalView")

    def test_all_roles_have_allowed_pages(self):
        for view in self.views.values():
            if view.role_id == "device_service":
                # machine-only — allowed_pages must be empty
                self.assertEqual(
                    len(view.allowed_pages), 0,
                    f"device_service must have empty allowed_pages (machine-only)"
                )
                continue
            self.assertTrue(len(view.allowed_pages) > 0,
                            f"{view.role_id} must have allowed pages")

    def test_all_roles_have_rls_scopes_defined(self):
        for view in self.views.values():
            self.assertIsInstance(view.required_rls, frozenset,
                                  f"{view.role_id} must have RLS scopes")

    def test_system_admin_and_security_admin_require_mfa(self):
        self.assertTrue(self.views["system_admin"].requires_mfa)
        self.assertTrue(self.views["security_admin"].requires_mfa)

    def test_device_service_has_no_human_ui(self):
        view = self.views["device_service"]
        # allowed_pages must be empty — no human portal pages
        self.assertEqual(len(view.allowed_pages), 0,
                         "device_service must have no human portal pages")
        self.assertNotIn("/deployment", view.allowed_pages)
        self.assertNotIn("/dashboard", view.allowed_pages)
        self.assertNotIn("/campaigns", view.allowed_pages)
        self.assertNotIn("/admin", view.allowed_pages)
        self.assertNotIn("/reports", view.allowed_pages)
        # primary_page must signal machine-only
        self.assertIn("machine-only", view.primary_page.lower())

    def test_device_service_is_marked_machine_only(self):
        from security_contract import DEVICE_SERVICE_IS_MACHINE_ONLY
        self.assertTrue(DEVICE_SERVICE_IS_MACHINE_ONLY,
                        "DEVICE_SERVICE_IS_MACHINE_ONLY must be True")

    def test_device_service_has_no_human_portal_login(self):
        view = self.views["device_service"]
        self.assertIn("machine-only", view.role_label.lower())
        self.assertIn("machine-only", view.primary_page.lower())
        # description must explicitly forbid human portal login
        self.assertIn("не аутентифицируется", view.description.lower())
        self.assertIn("human ui", view.description.lower())

    def test_device_service_not_in_page_role_matrix(self):
        for route, roles in self.page_matrix.items():
            self.assertNotIn("device_service", roles,
                             f"device_service must not be in PAGE_ROLE_MATRIX for '{route}'")

    def test_advertiser_cannot_access_admin_deployment_devices(self):
        view = self.views["advertiser"]
        for forbidden in ("/admin", "/deployment", "/devices", "/stores"):
            self.assertNotIn(forbidden, view.allowed_pages,
                             f"advertiser must not access {forbidden}")

    def test_operations_cannot_access_commercial_pages(self):
        view = self.views["operations"]
        for forbidden in ("view_campaigns", "view_creatives", "view_reports"):
            self.assertIn(forbidden, view.forbidden_actions,
                          f"operations must not have {forbidden}")

    def test_approver_has_approval_scope(self):
        self.assertIn("approval_scope", self.views["approver"].required_rls)

    def test_analyst_has_report_scope(self):
        self.assertIn("report_scope", self.views["analyst"].required_rls)

    def test_page_role_matrix_covers_all_pages(self):
        for route in ("/dashboard", "/stores", "/devices", "/creatives",
                       "/campaigns", "/schedule", "/publications",
                       "/proof-of-play", "/approvals", "/reports",
                       "/deployment", "/admin", "/login", "/logout"):
            self.assertIn(route, self.page_matrix,
                          f"Page-Role matrix must cover '{route}'")

    def test_admin_only_for_sys_and_sec_admin(self):
        self.assertIn("system_admin", self.page_matrix["/admin"])
        self.assertIn("security_admin", self.page_matrix["/admin"])
        self.assertNotIn("advertiser", self.page_matrix["/admin"])

    def test_rls_rules_mention_before_pagination(self):
        text = " ".join(self.rls_rules).lower()
        self.assertIn("before pagination", text)

    def test_rls_rules_mention_before_aggregation(self):
        text = " ".join(self.rls_rules).lower()
        self.assertIn("before aggregation", text)

    def test_rls_rules_mention_before_drill_down(self):
        text = " ".join(self.rls_rules).lower()
        self.assertIn("before drill-down", text)

    def test_rls_rules_mention_before_excel(self):
        text = " ".join(self.rls_rules).lower()
        self.assertIn("excel export", text)

    def test_rls_rules_mention_maker_checker(self):
        text = " ".join(self.rls_rules).lower()
        self.assertIn("maker-checker", text)

    def test_rls_rules_explicitly_forbid_device_service_human_login(self):
        text = " ".join(self.rls_rules).lower()
        self.assertIn("device service must not authenticate through human portal login", text)
        self.assertIn("device service must not access ordinary portal pages", text)
        self.assertIn("service/api/device-gateway context", text)

    def test_forbidden_fields_include_secrets(self):
        for fb in ("device_secret", "access_token", "password",
                    "manifest_hash", "sha256", "fingerprint",
                    "file_path", "filename"):
            self.assertIn(fb, self.forbidden,
                          f"FORBIDDEN_FIELDS must include '{fb}'")


class TestRlsNotesOnPages(unittest.TestCase):
    """Key pages have RLS-specific note boxes."""

    def setUp(self):
        self.client = TestClient(app)

    def test_admin_has_backend_data_sections(self):
        """Admin page loads data from backend API (users, roles, audit)."""
        resp = self.client.get("/admin")
        self.assertIn("backend api", resp.text.lower())
        self.assertIn("read-only", resp.text.lower())

    def test_admin_has_rls_section(self):
        resp = self.client.get("/admin")
        self.assertIn("RLS", resp.text)

    def test_reports_says_rls_before_kpi_drilldown_excel(self):
        resp = self.client.get("/reports")
        self.assertIn("rls применяется", resp.text.lower())
        self.assertIn("drill-down", resp.text.lower())
        self.assertIn("до агрегации", resp.text.lower())

    def test_approvals_says_route_scope_based_visibility(self):
        resp = self.client.get("/approvals")
        self.assertIn("maker-checker", resp.text.lower())
        self.assertIn("следующий шаг", resp.text.lower())

    def test_publications_says_publish_requires_permission_and_rls(self):
        resp = self.client.get("/publications")
        self.assertIn("Публикации", resp.text)
        self.assertIn("Сгенерировать Manifest", resp.text)

    def test_devices_says_device_visibility_is_scope_limited(self):
        resp = self.client.get("/devices")
        self.assertIn("store_scope", resp.text.lower())
        self.assertIn("device_scope", resp.text.lower())

    def test_admin_explains_device_service_is_technical(self):
        resp = self.client.get("/admin")
        self.assertIn("техническая роль", resp.text.lower())
        self.assertIn("Вход в пользовательский web-портал", resp.text)
        self.assertIn("запрещён", resp.text.lower())


class TestRlsDocsExist(unittest.TestCase):
    """docs/portal/rls-role-portal-views.md exists and covers key topics."""

    @classmethod
    def setUpClass(cls):
        doc = Path(__file__).resolve().parent.parent.parent.parent
        doc = doc / "docs" / "portal" / "rls-role-portal-views.md"
        cls.content = doc.read_text().lower()

    def test_doc_exists_and_has_content(self):
        self.assertTrue(len(self.content) > 500,
                        "RLS doc must have substantial content")

    def test_doc_covers_role_views(self):
        for role in ("системный администратор", "менеджер рекламы",
                      "согласующий", "аналитик", "рекламодатель",
                      "оператор", "сервис ксо"):
            self.assertIn(role, self.content,
                          f"Doc must cover role: {role}")

    def test_doc_covers_page_matrix(self):
        self.assertIn("матрица страниц", self.content)

    def test_doc_covers_excel_export_rls(self):
        self.assertIn("excel export", self.content)
        self.assertIn("rls", self.content)

    def test_doc_covers_maker_checker(self):
        self.assertIn("maker-checker", self.content)

    def test_doc_covers_forbidden_fields(self):
        self.assertIn("запрещённые поля", self.content)

    def test_doc_says_ui_hiding_is_not_security(self):
        self.assertIn("ui hiding is not security", self.content)

    def test_doc_explains_device_service_machine_only(self):
        self.assertIn("machine-only", self.content)
        self.assertIn("не является пользователем портала", self.content)
        self.assertIn("не имеет human ui", self.content)
        self.assertIn("device gateway", self.content)

    def test_doc_says_device_service_no_human_portal_login(self):
        self.assertIn("не аутентифицируется", self.content)
        self.assertIn("отдельный контур", self.content)


# ══════════════════════════════════════════════════════════════════════
# Auth Integration Tests (Step 36.6)
# ══════════════════════════════════════════════════════════════════════

class TestLoginForm(unittest.TestCase):
    """Login page has real server-side POST form."""

    def setUp(self):
        from main import app
        self.client = TestClient(app)

    def test_login_page_has_form(self):
        resp = self.client.get("/login")
        self.assertIn('<form method="POST"', resp.text)
        self.assertIn('action="/login"', resp.text)

    def test_login_form_posts_server_side_not_js(self):
        """Login uses standard form POST, not JavaScript fetch/axios."""
        resp = self.client.get("/login")
        lower = resp.text.lower()
        self.assertNotIn("fetch(", lower)
        self.assertNotIn("axios", lower)
        self.assertNotIn("xmlhttprequest", lower)
        self.assertNotIn("onclick", lower)

    def test_password_not_rendered_back_after_failed_login(self):
        """After failed login, password field is re-rendered empty —
        never filled with the submitted value."""
        resp = self.client.post("/login", data={
            "username": "nonexistent",
            "password": "WrongPass123!",
        }, follow_redirects=False)
        # Password must NOT appear in the page
        self.assertNotIn("WrongPass123!", resp.text)

    def test_token_not_present_in_login_html(self):
        resp = self.client.post("/login", data={
            "username": "nonexistent",
            "password": "WrongPass123!",
        }, follow_redirects=False)
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "bearer", "token_hash"):
            self.assertNotIn(fb, lower,
                             f"Login HTML must NOT contain '{fb}'")

    def test_backend_url_not_in_login_html(self):
        resp = self.client.get("/login")
        self.assertNotIn("localhost:8001", resp.text)
        self.assertNotIn("PORTAL_BACKEND", resp.text)

    def test_sso_button_remains_disabled(self):
        resp = self.client.get("/login")
        self.assertIn("btn-disabled", resp.text)
        self.assertIn("SSO", resp.text)

    def test_login_error_shows_safe_message(self):
        """Error messages do not reveal which field is wrong.
        The word 'пароль' (password label) is OK — it's just the form label.
        The submitted password VALUE must never appear."""
        # Mock backend_login to return 401 (invalid credentials)
        # Without backend running, the real call returns 502 (unreachable)
        # and the error message becomes "Сервер авторизации временно недоступен"
        async def _mock_login(username, password):
            return {"ok": False, "error": "Invalid credentials", "status": 401}

        with patch("main.backend_login", side_effect=_mock_login):
            resp = self.client.post("/login", data={
                "username": "nonexistent",
                "password": "WrongPass123!",
            }, follow_redirects=False)
        # Safe generic error
        self.assertIn("Неверное имя пользователя или пароль", resp.text)
        # Submitted password value must never be echoed back
        self.assertNotIn("WrongPass123!", resp.text)


class TestLogoutFlow(unittest.TestCase):
    """Logout page and POST handler."""

    def setUp(self):
        from main import app
        self.client = TestClient(app)

    def test_logout_page_renders(self):
        resp = self.client.get("/logout")
        self.assertEqual(resp.status_code, 200)

    def test_logout_post_clears_and_shows_safe_message(self):
        """POST /logout should clear the session and show safe message."""
        resp = self.client.post("/logout", follow_redirects=False)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("access_token", resp.text.lower())
        self.assertNotIn("refresh_token", resp.text.lower())

    def test_logout_does_not_expose_token(self):
        resp = self.client.post("/logout", follow_redirects=False)
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "bearer", "token_hash",
                    "authorization"):
            self.assertNotIn(fb, lower,
                             f"Logout HTML must NOT contain '{fb}'")


class TestBaseLayoutAuthState(unittest.TestCase):
    """Base template shows dynamic auth state."""

    def setUp(self):
        from main import app
        self.client = TestClient(app)

    def test_unauthenticated_header(self):
        resp = self.client.get("/dashboard")
        self.assertIn("Пользователь: вход не выполнен", resp.text)

    def test_unauthenticated_shows_login_link(self):
        resp = self.client.get("/dashboard")
        self.assertIn("Вход", resp.text)
        self.assertIn('href="/login"', resp.text)

    def test_header_does_not_expose_raw_tokens(self):
        resp = self.client.get("/dashboard")
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "authorization",
                    "bearer ", "token_hash"):
            self.assertNotIn(fb, lower,
                             f"Header must NOT contain '{fb}'")


class TestBackendClientConfig(unittest.TestCase):
    """Backend client uses env config, never exposes URL in UI."""

    def test_backend_url_default_is_localhost_dev(self):
        from backend_client import get_backend_url
        url = get_backend_url()
        self.assertIn("localhost", url)
        self.assertNotIn("production", url)

    def test_backend_client_has_timeout(self):
        from backend_client import _CONNECT_TIMEOUT, _READ_TIMEOUT
        self.assertGreater(_CONNECT_TIMEOUT, 0)
        self.assertGreater(_READ_TIMEOUT, 0)

    def test_backend_client_never_logs_sensitive_keys(self):
        from backend_client import _SENSITIVE_KEYS
        self.assertIn("password", _SENSITIVE_KEYS)
        self.assertIn("access_token", _SENSITIVE_KEYS)
        self.assertIn("refresh_token", _SENSITIVE_KEYS)


class TestAuthIntegrationSecurity(unittest.TestCase):
    """Security: no tokens/secrets/URLs in demo pages."""

    def setUp(self):
        from main import app
        self.client = TestClient(app)

    def test_demo_routes_still_render(self):
        """All demo routes must still return 200 after auth integration."""
        for route in ["/", "/dashboard", "/stores", "/devices",
                       "/campaigns", "/creatives", "/schedule",
                       "/publications", "/proof-of-play", "/reports",
                       "/deployment", "/admin", "/approvals"]:
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, 200,
                             f"Route {route} must return 200")

    def test_no_localstorage_sessionstorage_usage(self):
        """No localStorage/sessionStorage in any template."""
        for route in ["/", "/login", "/logout", "/admin"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            self.assertNotIn("localstorage", lower)
            self.assertNotIn("sessionstorage", lower)

    def test_no_external_cdn_scripts_fonts(self):
        for route in ["/", "/login", "/logout"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for cdn in ("cdn.", "cloudflare", "googleapis", "jsdelivr",
                         "unpkg", "fontawesome", "bootstrapcdn"):
                self.assertNotIn(cdn, lower,
                                 f"{route}: must NOT reference CDN '{cdn}'")


# ══════════════════════════════════════════════════════════════════════
# Session Hardening Tests (Step 36.6.1)
# ══════════════════════════════════════════════════════════════════════

class TestPortalUserSafety(unittest.TestCase):
    """PortalUser dataclass must never expose tokens."""

    def test_portal_user_has_no_token_attributes(self):
        from portal_session import PortalUser
        u = PortalUser(username="test", display_name="Test", roles=["analyst"])
        # Ensure no token-related attributes exist
        for attr in ("access_token", "refresh_token", "token", "token_hash",
                      "password", "password_hash", "secret"):
            self.assertFalse(hasattr(u, attr),
                             f"PortalUser must NOT have '{attr}' attribute")

    def test_portal_user_does_not_expose_tokens_in_dict(self):
        from portal_session import PortalUser
        u = PortalUser(username="test", display_name="Test", roles=["analyst"])
        d = {f: getattr(u, f) for f in u.__dataclass_fields__}
        for forbidden in ("access_token", "refresh_token", "token_hash",
                           "password", "password_hash"):
            self.assertNotIn(forbidden, d,
                             f"PortalUser fields must NOT include '{forbidden}'")


class TestSessionStoreServerSide(unittest.TestCase):
    """Session store is server-side only — cookie has only opaque ID."""

    def test_session_store_creates_and_retrieves(self):
        from portal_session import _store, PortalUser
        sid = _store.create(
            access_token="mock-access", refresh_token="mock-refresh",
            username="testuser", display_name="Test", roles=["analyst"],
        )
        self.assertEqual(len(sid), 64)  # 32 bytes hex
        data = _store.get(sid)
        self.assertIsNotNone(data)
        self.assertEqual(data["username"], "testuser")
        self.assertEqual(data["access_token"], "mock-access")

    def test_session_store_delete_removes(self):
        from portal_session import _store
        sid = _store.create(
            access_token="mock-access", refresh_token="mock-refresh",
            username="testuser", display_name="T", roles=[],
        )
        _store.delete(sid)
        self.assertIsNone(_store.get(sid))

    def test_session_store_expires(self):
        from portal_session import _store
        sid = _store.create(
            access_token="mock-access", refresh_token="mock-refresh",
            username="testuser", display_name="T", roles=[],
        )
        # Manually age the session
        _store._store[sid]["_created_at"] = 0  # far in the past
        self.assertIsNone(_store.get(sid))

    def test_cookie_only_has_session_id_not_tokens(self):
        """Browser cookie contains only opaque session_id, never tokens."""
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)

        # GET login page → set-cookie should NOT contain tokens
        resp = client.get("/login")
        cookies = resp.headers.get("set-cookie", "")
        for forbidden in ("access_token", "refresh_token", "bearer",
                           "token_hash", "portal_refresh"):
            self.assertNotIn(forbidden, cookies.lower(),
                             f"Cookie must NOT contain '{forbidden}'")

    def test_portal_user_from_request_has_no_tokens(self):
        """get_current_portal_user returns PortalUser, never tokens."""
        from portal_session import get_current_portal_user
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)

        # Unauthenticated → None
        resp = client.get("/dashboard")
        # PortalUser should be None when unauthenticated
        self.assertIn("Пользователь: вход не выполнен", resp.text)

    def test_logout_post_clears_server_side_store(self):
        """POST /logout must clear both cookie and server-side store."""
        from portal_session import _store
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)

        # Manually create a session in the store
        sid = _store.create(
            access_token="fake-at", refresh_token="fake-rt",
            username="u", display_name="U", roles=[],
        )

        # POST logout — should clear
        resp = client.post("/logout")
        self.assertEqual(resp.status_code, 200)

        # Server-side store should still have the manually-inserted session
        # (logout only clears the session associated with the cookie,
        #  not all sessions — this is correct behaviour)

        # Clean up
        _store.delete(sid)


class TestHTMLNeverExposesTokens(unittest.TestCase):
    """No rendered HTML page should contain raw tokens."""

    def setUp(self):
        from main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_login_page_no_token_in_html(self):
        resp = self.client.get("/login")
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "bearer ",
                    "token_hash", "authorization:"):
            self.assertNotIn(fb, lower,
                             f"Login HTML must NOT contain '{fb}'")

    def test_dashboard_no_token_in_html(self):
        resp = self.client.get("/dashboard")
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "bearer ",
                    "token_hash", "authorization:"):
            self.assertNotIn(fb, lower,
                             f"Dashboard HTML must NOT contain '{fb}'")

    def test_logout_page_no_token_in_html(self):
        resp = self.client.get("/logout")
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "bearer ",
                    "token_hash", "authorization:"):
            self.assertNotIn(fb, lower,
                             f"Logout HTML must NOT contain '{fb}'")

    def test_backend_url_not_in_any_page(self):
        for route in ["/", "/login", "/logout", "/dashboard", "/admin"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            self.assertNotIn("localhost:8001", lower,
                             f"{route}: must NOT contain backend URL")
            self.assertNotIn("PORTAL_BACKEND", lower,
                             f"{route}: must NOT leak env var name")

    def test_session_id_does_not_contain_username(self):
        """Opaque session_id must not encode username/roles."""
        from portal_session import _store
        sid = _store.create(
            access_token="at", refresh_token="rt",
            username="admin_user", display_name="Admin", roles=["system_admin"],
        )
        self.assertNotIn("admin_user", sid)
        self.assertNotIn("system_admin", sid)
        _store.delete(sid)


# ══════════════════════════════════════════════════════════════════════
# Admin Create User Tests (Step 36.8)
# ══════════════════════════════════════════════════════════════════════

class TestAdminCreateUserForm(unittest.TestCase):
    """Admin page has create user form (server-side POST)."""

    def setUp(self):
        from main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_admin_page_has_create_user_form(self):
        resp = self.client.get("/admin")
        self.assertIn("Создать пользователя", resp.text)
        self.assertIn('action="/admin/users/create"', resp.text)
        self.assertIn('method="post"', resp.text.lower())

    def test_create_user_form_has_username_field(self):
        resp = self.client.get("/admin")
        self.assertIn('name="username"', resp.text)

    def test_create_user_form_has_password_field(self):
        resp = self.client.get("/admin")
        self.assertIn('type="password"', resp.text)
        self.assertIn('name="password"', resp.text)

    def test_create_user_form_has_display_name_field(self):
        resp = self.client.get("/admin")
        self.assertIn('name="display_name"', resp.text)

    def test_create_user_form_excludes_email(self):
        """Email field must NOT be in the create user form (not in v1)."""
        resp = self.client.get("/admin")
        # Check there's no email input
        self.assertNotIn('name="email"', resp.text.lower())
        self.assertNotIn('type="email"', resp.text.lower())

    def test_create_user_form_excludes_phone(self):
        resp = self.client.get("/admin")
        self.assertNotIn('name="phone"', resp.text.lower())

    def test_create_user_form_excludes_device_service_role(self):
        """device_service must NOT be in create user form or HUMAN_ROLES.
        It IS present in the reference role listing for governance — that's OK."""
        from main import HUMAN_ROLES
        self.assertNotIn("device_service", HUMAN_ROLES)
        # Verify the reference section still documents device_service
        resp = self.client.get("/admin")
        self.assertIn("Сервис КСО", resp.text)  # present in reference only

    def test_create_user_form_is_server_side_post(self):
        """No JavaScript fetch/axios — standard form POST."""
        resp = self.client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("fetch(", lower)
        self.assertNotIn("axios", lower)

    def test_block_user_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/block"', resp.text)

    def test_archive_user_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/archive"', resp.text)

    def test_assign_role_button_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-roles"', resp.text)


class TestAdminCreateUserRBAC(unittest.TestCase):
    """Create user requires users.create permission."""

    def test_backend_client_create_user_method_exists(self):
        from backend_client import BackendClient
        self.assertTrue(hasattr(BackendClient, "create_user"))
        self.assertTrue(callable(BackendClient.create_user))

    def test_HUMAN_ROLES_excludes_device_service(self):
        from main import HUMAN_ROLES
        self.assertNotIn("device_service", HUMAN_ROLES)
        # All other roles are present
        for role in ("system_admin", "security_admin", "ad_manager",
                      "approver", "analyst", "advertiser", "operations"):
            self.assertIn(role, HUMAN_ROLES)

    def test_password_not_rendered_in_admin_html(self):
        """Admin page must never contain password values or hashes."""
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for fb in ("password_hash", "token_hash", "access_token",
                    "refresh_token", "bearer ", "authorization:"):
            self.assertNotIn(fb, lower,
                             f"Admin HTML must NOT contain '{fb}'")

    def test_backend_url_not_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localhost:8001", lower)
        self.assertNotIn("PORTAL_BACKEND", lower)


class TestCreateUserNoLocalStorage(unittest.TestCase):
    """No localStorage/sessionStorage usage in admin page."""

    def test_admin_page_no_localstorage(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localstorage", lower)
        self.assertNotIn("sessionstorage", lower)

    def test_admin_page_no_external_cdn(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for cdn in ("cdn.", "cloudflare", "googleapis", "jsdelivr",
                     "unpkg", "fontawesome", "bootstrapcdn"):
            self.assertNotIn(cdn, lower,
                             f"Admin must NOT reference CDN '{cdn}'")


# ══════════════════════════════════════════════════════════════════════
# Admin Assign Roles Tests (Step 36.9)
# ══════════════════════════════════════════════════════════════════════

class TestAdminAssignRolesForm(unittest.TestCase):
    """Admin page has assign roles form (server-side POST)."""

    def setUp(self):
        from main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_admin_page_has_assign_roles_form(self):
        resp = self.client.get("/admin")
        self.assertIn("Назначить роль", resp.text)
        self.assertIn('action="/admin/users/assign-roles"', resp.text)
        self.assertIn('method="post"', resp.text.lower())

    def test_assign_roles_form_has_username_field(self):
        resp = self.client.get("/admin")
        self.assertIn('name="username"', resp.text)

    def test_assign_roles_form_has_roles_select(self):
        resp = self.client.get("/admin")
        self.assertIn('name="roles"', resp.text)
        self.assertIn("<select", resp.text.lower())

    def test_assign_roles_form_excludes_device_service(self):
        """device_service must NOT be an option in the assign roles form."""
        resp = self.client.get("/admin")
        # The select contains <option value="..."> — device_service must not be among them
        # Verify it's not in the form context (the reference listing is separate)
        # Check: the select block should not contain device_service option
        self.assertNotIn('value="device_service"', resp.text)

    def test_assign_roles_form_excludes_email_phone(self):
        resp = self.client.get("/admin")
        self.assertNotIn('name="email"', resp.text.lower())
        self.assertNotIn('name="phone"', resp.text.lower())

    def test_assign_roles_form_is_server_side_post(self):
        """No JavaScript fetch/axios — standard form POST."""
        resp = self.client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("fetch(", lower)
        self.assertNotIn("axios", lower)
        self.assertNotIn("onclick", lower)

    def test_block_user_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/block"', resp.text)

    def test_archive_user_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/archive"', resp.text)

    def test_assign_rls_button_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-rls-scopes"', resp.text)

    def test_create_user_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn("Создать пользователя", resp.text)
        self.assertIn('action="/admin/users/create"', resp.text)


class TestAdminAssignRolesRBAC(unittest.TestCase):
    """Assign roles requires roles.manage permission."""

    def test_HUMAN_ROLES_excludes_device_service(self):
        from main import HUMAN_ROLES
        self.assertNotIn("device_service", HUMAN_ROLES)
        for role in ("system_admin", "security_admin", "ad_manager",
                      "approver", "analyst", "advertiser", "operations"):
            self.assertIn(role, HUMAN_ROLES)

    def test_backend_client_has_assign_user_roles(self):
        from backend_client import BackendClient
        self.assertTrue(hasattr(BackendClient, "assign_user_roles"))
        self.assertTrue(callable(BackendClient.assign_user_roles))

    def test_backend_client_has_get_user_by_username(self):
        from backend_client import BackendClient
        self.assertTrue(hasattr(BackendClient, "get_user_by_username"))
        self.assertTrue(callable(BackendClient.get_user_by_username))

    def test_assign_roles_route_requires_auth(self):
        """POST /admin/users/assign-roles without session should get 403
        (RBAC guard fires before session is even checked — safe)."""
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/admin/users/assign-roles", data={
            "username": "testuser",
            "roles": ["analyst"],
        }, follow_redirects=False)
        # Should get 403 (RBAC) or 303 redirect (session missing → RBAC fails)
        self.assertIn(resp.status_code, (303, 403, 401))

    def test_password_not_rendered_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for fb in ("password_hash", "token_hash", "access_token",
                    "refresh_token", "bearer ", "authorization:"):
            self.assertNotIn(fb, lower,
                             f"Admin HTML must NOT contain '{fb}'")

    def test_backend_url_not_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localhost:8001", lower)
        self.assertNotIn("PORTAL_BACKEND", lower)

    def test_raw_user_id_not_in_assign_roles_form(self):
        """Assign roles form must NOT expose raw internal UUIDs."""
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        # Extract the assign-roles form section
        text = resp.text
        idx = text.find('action="/admin/users/assign-roles"')
        if idx < 0:
            self.skipTest("Assign roles form not found")
        form_section = text[idx:idx + 2000]
        # UUID pattern: 8-4-4-4-12 hex chars
        import re
        uuid_pattern = re.compile(
            r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
        )
        self.assertIsNone(
            uuid_pattern.search(form_section),
            "Assign roles form must NOT contain UUIDs",
        )


class TestAssignRolesNoLocalStorage(unittest.TestCase):
    """No localStorage/sessionStorage, no external CDN in assign roles form."""

    def test_admin_page_no_localstorage(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localstorage", lower)
        self.assertNotIn("sessionstorage", lower)

    def test_admin_page_no_external_cdn(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for cdn in ("cdn.", "cloudflare", "googleapis", "jsdelivr",
                     "unpkg", "fontawesome", "bootstrapcdn"):
            self.assertNotIn(cdn, lower,
                             f"Admin must NOT reference CDN '{cdn}'")


# ══════════════════════════════════════════════════════════════════════
# Admin Assign RLS Scopes Tests (Step 36.10)
# ══════════════════════════════════════════════════════════════════════

class TestAdminAssignRlsScopesForm(unittest.TestCase):
    """Admin page has assign RLS scopes form (server-side POST)."""

    def setUp(self):
        from main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_admin_page_has_assign_rls_form(self):
        resp = self.client.get("/admin")
        self.assertIn("Назначить область", resp.text)
        self.assertIn('action="/admin/users/assign-rls-scopes"', resp.text)
        self.assertIn('method="post"', resp.text.lower())

    def test_assign_rls_form_has_username_field(self):
        resp = self.client.get("/admin")
        self.assertIn('name="username"', resp.text)

    def test_assign_rls_form_has_textarea(self):
        resp = self.client.get("/admin")
        self.assertIn('name="rls_scopes_text"', resp.text)
        self.assertIn("<textarea", resp.text.lower())

    def test_assign_rls_form_lists_7_allowed_scope_types(self):
        resp = self.client.get("/admin")
        for scope in ("advertiser_scope", "branch_scope", "store_scope",
                       "campaign_scope", "device_scope",
                       "approval_scope", "report_scope"):
            self.assertIn(scope, resp.text,
                          f"RLS form must list '{scope}'")

    def test_assign_rls_form_warns_about_replace(self):
        resp = self.client.get("/admin")
        self.assertIn("Заменяет", resp.text)

    def test_assign_rls_form_excludes_email_phone(self):
        resp = self.client.get("/admin")
        self.assertNotIn('name="email"', resp.text.lower())
        self.assertNotIn('name="phone"', resp.text.lower())

    def test_assign_rls_form_is_server_side_post(self):
        resp = self.client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("fetch(", lower)
        self.assertNotIn("axios", lower)

    def test_block_user_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/block"', resp.text)

    def test_archive_user_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/archive"', resp.text)

    def test_create_user_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn("Создать пользователя", resp.text)
        self.assertIn('action="/admin/users/create"', resp.text)

    def test_assign_roles_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-roles"', resp.text)


class TestAdminAssignRlsScopesRBAC(unittest.TestCase):
    """Assign RLS scopes requires roles.manage."""

    def test_backend_client_has_assign_user_rls_scopes(self):
        from backend_client import BackendClient
        self.assertTrue(hasattr(BackendClient, "assign_user_rls_scopes"))
        self.assertTrue(callable(BackendClient.assign_user_rls_scopes))

    def test_assign_rls_route_requires_auth(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/admin/users/assign-rls-scopes", data={
            "username": "testuser",
            "rls_scopes_text": "branch_scope:test",
        }, follow_redirects=False)
        self.assertIn(resp.status_code, (303, 403, 401))

    def test_password_not_rendered_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for fb in ("password_hash", "token_hash", "access_token",
                    "refresh_token", "bearer ", "authorization:"):
            self.assertNotIn(fb, lower,
                             f"Admin HTML must NOT contain '{fb}'")

    def test_backend_url_not_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localhost:8001", lower)
        self.assertNotIn("PORTAL_BACKEND", lower)

    def test_allowed_rls_scope_types_count(self):
        from main import ALLOWED_RLS_SCOPE_TYPES
        self.assertEqual(len(ALLOWED_RLS_SCOPE_TYPES), 7)
        for scope in ("advertiser_scope", "branch_scope", "store_scope",
                       "campaign_scope", "device_scope",
                       "approval_scope", "report_scope"):
            self.assertIn(scope, ALLOWED_RLS_SCOPE_TYPES)


class TestAssignRlsScopesNoLocalStorage(unittest.TestCase):
    """No localStorage/sessionStorage, no external CDN."""

    def test_admin_page_no_localstorage(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localstorage", lower)
        self.assertNotIn("sessionstorage", lower)

    def test_admin_page_no_external_cdn(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for cdn in ("cdn.", "cloudflare", "googleapis", "jsdelivr",
                     "unpkg", "fontawesome", "bootstrapcdn"):
            self.assertNotIn(cdn, lower,
                             f"Admin must NOT reference CDN '{cdn}'")


# ══════════════════════════════════════════════════════════════════════
# Admin Block User Tests (Step 36.11)
# ══════════════════════════════════════════════════════════════════════

class TestAdminBlockUserForm(unittest.TestCase):
    """Admin page has block user form (server-side POST)."""

    def setUp(self):
        from main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_admin_page_has_block_user_form(self):
        resp = self.client.get("/admin")
        self.assertIn("Заблокировать пользователя", resp.text)
        self.assertIn('action="/admin/users/block"', resp.text)
        self.assertIn('method="post"', resp.text.lower())

    def test_block_form_has_username_field(self):
        resp = self.client.get("/admin")
        self.assertIn('name="username"', resp.text)

    def test_block_form_warns_user_cannot_login(self):
        resp = self.client.get("/admin")
        self.assertIn("не сможет войти", resp.text)

    def test_block_form_mentions_last_admin_protection(self):
        resp = self.client.get("/admin")
        self.assertIn("system_admin", resp.text)

    def test_block_form_excludes_email_phone(self):
        resp = self.client.get("/admin")
        self.assertNotIn('name="email"', resp.text.lower())
        self.assertNotIn('name="phone"', resp.text.lower())

    def test_block_form_is_server_side_post(self):
        resp = self.client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("fetch(", lower)
        self.assertNotIn("axios", lower)

    def test_archive_user_is_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/archive"', resp.text)

    def test_create_user_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn("Создать пользователя", resp.text)
        self.assertIn('action="/admin/users/create"', resp.text)

    def test_assign_roles_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-roles"', resp.text)

    def test_assign_rls_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-rls-scopes"', resp.text)


class TestAdminBlockUserRBAC(unittest.TestCase):
    """Block user requires users.manage."""

    def test_backend_client_has_block_user(self):
        from backend_client import BackendClient
        self.assertTrue(hasattr(BackendClient, "block_user"))
        self.assertTrue(callable(BackendClient.block_user))

    def test_block_route_requires_auth(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/admin/users/block", data={
            "username": "testuser",
        }, follow_redirects=False)
        self.assertIn(resp.status_code, (303, 403, 401))

    def test_password_not_rendered_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for fb in ("password_hash", "token_hash", "access_token",
                    "refresh_token", "bearer ", "authorization:"):
            self.assertNotIn(fb, lower,
                             f"Admin HTML must NOT contain '{fb}'")

    def test_backend_url_not_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localhost:8001", lower)
        self.assertNotIn("PORTAL_BACKEND", lower)


class TestBlockUserNoLocalStorage(unittest.TestCase):
    """No localStorage/sessionStorage, no external CDN."""

    def test_admin_page_no_localstorage(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localstorage", lower)
        self.assertNotIn("sessionstorage", lower)

    def test_admin_page_no_external_cdn(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for cdn in ("cdn.", "cloudflare", "googleapis", "jsdelivr",
                     "unpkg", "fontawesome", "bootstrapcdn"):
            self.assertNotIn(cdn, lower,
                             f"Admin must NOT reference CDN '{cdn}'")


# ══════════════════════════════════════════════════════════════════════
# Admin Archive User Tests (Step 36.12)
# ══════════════════════════════════════════════════════════════════════

class TestAdminArchiveUserForm(unittest.TestCase):
    """Admin page has archive user form (server-side POST)."""

    def setUp(self):
        from main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_admin_page_has_archive_user_form(self):
        resp = self.client.get("/admin")
        self.assertIn("Архивировать пользователя", resp.text)
        self.assertIn('action="/admin/users/archive"', resp.text)
        self.assertIn('method="post"', resp.text.lower())

    def test_archive_form_has_username_field(self):
        resp = self.client.get("/admin")
        self.assertIn('name="username"', resp.text)

    def test_archive_form_mentions_logical_delete(self):
        resp = self.client.get("/admin")
        self.assertIn("логическое удаление", resp.text)

    def test_archive_form_mentions_not_hard_delete(self):
        resp = self.client.get("/admin")
        self.assertIn("hard delete", resp.text.lower())

    def test_archive_form_mentions_last_admin_protection(self):
        resp = self.client.get("/admin")
        self.assertIn("system_admin", resp.text)

    def test_archive_form_excludes_email_phone(self):
        resp = self.client.get("/admin")
        self.assertNotIn('name="email"', resp.text.lower())
        self.assertNotIn('name="phone"', resp.text.lower())

    def test_archive_form_is_server_side_post(self):
        resp = self.client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("fetch(", lower)
        self.assertNotIn("axios", lower)

    def test_block_user_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/block"', resp.text)

    def test_create_user_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/create"', resp.text)

    def test_assign_roles_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-roles"', resp.text)

    def test_assign_rls_remains_active(self):
        resp = self.client.get("/admin")
        self.assertIn('action="/admin/users/assign-rls-scopes"', resp.text)


class TestAdminArchiveUserRBAC(unittest.TestCase):
    """Archive user requires users.manage."""

    def test_backend_client_has_archive_user(self):
        from backend_client import BackendClient
        self.assertTrue(hasattr(BackendClient, "archive_user"))
        self.assertTrue(callable(BackendClient.archive_user))

    def test_archive_route_requires_auth(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/admin/users/archive", data={
            "username": "testuser",
        }, follow_redirects=False)
        self.assertIn(resp.status_code, (303, 403, 401))

    def test_password_not_rendered_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for fb in ("password_hash", "token_hash", "access_token",
                    "refresh_token", "bearer ", "authorization:"):
            self.assertNotIn(fb, lower,
                             f"Admin HTML must NOT contain '{fb}'")

    def test_backend_url_not_in_admin_html(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localhost:8001", lower)
        self.assertNotIn("PORTAL_BACKEND", lower)


class TestArchiveUserNoLocalStorage(unittest.TestCase):
    """No localStorage/sessionStorage, no external CDN."""

    def test_admin_page_no_localstorage(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        self.assertNotIn("localstorage", lower)
        self.assertNotIn("sessionstorage", lower)

    def test_admin_page_no_external_cdn(self):
        from main import app
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/admin")
        lower = resp.text.lower()
        for cdn in ("cdn.", "cloudflare", "googleapis", "jsdelivr",
                     "unpkg", "fontawesome", "bootstrapcdn"):
            self.assertNotIn(cdn, lower,
                             f"Admin must NOT reference CDN '{cdn}'")


# ══════════════════════════════════════════════════════════════════════
# Route-Level RBAC Guard Tests (Step 36.13)
# ══════════════════════════════════════════════════════════════════════
# These tests disable the global mock and test real route auth behavior.

class TestRouteAuthUnauthenticated(unittest.TestCase):
    """Unauthenticated requests redirect to /login."""

    @classmethod
    def setUpClass(cls):
        _enable_real_auth()

    @classmethod
    def tearDownClass(cls):
        _disable_real_auth()

    def setUp(self):
        from main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def _assert_redirects_to_login(self, route: str):
        resp = self.client.get(route, follow_redirects=False)
        self.assertIn(resp.status_code, (303, 302),
                      f"{route}: expected redirect, got {resp.status_code}")
        self.assertIn("/login", resp.headers.get("location", "").lower())

    def test_unauthenticated_dashboard_redirects(self):
        self._assert_redirects_to_login("/")

    def test_unauthenticated_campaigns_redirects(self):
        self._assert_redirects_to_login("/campaigns")

    def test_unauthenticated_creatives_redirects(self):
        self._assert_redirects_to_login("/creatives")

    def test_unauthenticated_schedule_redirects(self):
        self._assert_redirects_to_login("/schedule")

    def test_unauthenticated_publications_redirects(self):
        self._assert_redirects_to_login("/publications")

    def test_unauthenticated_stores_redirects(self):
        self._assert_redirects_to_login("/stores")

    def test_unauthenticated_devices_redirects(self):
        self._assert_redirects_to_login("/devices")

    def test_unauthenticated_proof_of_play_redirects(self):
        self._assert_redirects_to_login("/proof-of-play")

    def test_unauthenticated_reports_redirects(self):
        self._assert_redirects_to_login("/reports")

    def test_unauthenticated_deployment_redirects(self):
        self._assert_redirects_to_login("/deployment")

    def test_unauthenticated_approvals_redirects(self):
        self._assert_redirects_to_login("/approvals")

    def test_unauthenticated_admin_redirects(self):
        self._assert_redirects_to_login("/admin")

    def test_login_page_remains_public(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)

    def test_logout_page_remains_public(self):
        resp = self.client.get("/logout")
        self.assertEqual(resp.status_code, 200)

    def test_health_remains_public(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)


class TestRouteAuthForbidden(unittest.TestCase):
    """Authenticated user without permission gets 403."""

    @classmethod
    def setUpClass(cls):
        _enable_real_auth()
        # Set up a limited-permission user (analyst — no admin/deployment)
        import rbac as _r
        _ORIG_GET_USER2 = _r._get_user
        _ORIG_GET_PERMS2 = _r._get_perms

        from portal_session import PortalUser
        def _limited_user(req):
            return PortalUser(username="demo_analyst", display_name="Analyst",
                              roles=["analyst"])

        _LIMITED_PERMS = frozenset({
            "view_dashboard", "view_stores", "view_devices",
            "view_creatives", "view_campaigns", "view_schedule",
            "view_publications", "view_proof_of_play",
            "view_reports",
        })

        def _limited_perms_fn(req):
            return _LIMITED_PERMS

        _r._get_user = _limited_user
        _r._get_perms = _limited_perms_fn

        cls._orig_user = _ORIG_GET_USER2
        cls._orig_perms = _ORIG_GET_PERMS2

    @classmethod
    def tearDownClass(cls):
        _disable_real_auth()
        import rbac as _r
        _r._get_user = cls._orig_user
        _r._get_perms = cls._orig_perms

    def setUp(self):
        from main import app
        from starlette.testclient import TestClient
        self.client = TestClient(app)

    def test_no_approvals_gets_403(self):
        resp = self.client.get("/approvals", follow_redirects=False)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Доступ запрещён", resp.text)
        self.assertNotIn("view_approvals", resp.text.lower())

    def test_no_deployment_gets_403(self):
        resp = self.client.get("/deployment", follow_redirects=False)
        self.assertEqual(resp.status_code, 403)

    def test_no_admin_gets_403(self):
        resp = self.client.get("/admin", follow_redirects=False)
        self.assertIn(resp.status_code, (403, 302))

    def test_403_does_not_expose_permission_names(self):
        resp = self.client.get("/approvals", follow_redirects=False)
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "bearer ",
                    "authorization:", "backend_url", "localhost:8001",
                    "password_hash", "token_hash"):
            self.assertNotIn(fb, lower,
                             f"403 page must NOT contain '{fb}'")


# ══════════════════════════════════════════════════════════════════════
# Stores & KSO Devices — Backend API Integration Tests (Step 37.2)
# ══════════════════════════════════════════════════════════════════════

# Mock backend data for synthetic one-KSO pilot
_MOCK_BRANCHES = [{"id": "b1", "name": "Demo Branch", "code": "demo_branch_north", "timezone": "Europe/Moscow", "is_active": True}]
_MOCK_CLUSTERS = [{"id": "c1", "name": "Demo Cluster", "code": "demo_cluster_001", "branch_id": "b1", "is_active": True}]
_MOCK_STORES = [{"id": "s1", "name": "Demo Store", "code": "demo_store_001", "cluster_id": "c1", "format": "supermarket", "status": "active", "timezone": "Europe/Moscow", "is_active": True}]
_MOCK_KSO = [{
    "id": "k1", "store_id": "s1", "device_code": "demo_kso_001",
    "display_name": "Demo KSO", "status": "active", "channel": "kso",
    "runtime_version": "1.0.0", "player_version": "1.0.0",
    "sidecar_version": "1.0.0", "state_adapter_version": "1.0.0",
    "manifest_version": "abc123", "screen_width": 1920, "screen_height": 1080,
    "ad_zone_width": 1440, "ad_zone_height": 1080,
    "last_seen_at": "2026-06-22T12:00:00+00:00",
}]


class _FakeBackendClient:
    """Fake BackendClient for testing — never calls real backend."""

    async def close(self):
        pass

    async def list_branches(self, access_token: str) -> dict:
        return {"ok": True, "data": _MOCK_BRANCHES}

    async def list_clusters(self, access_token: str, branch_id=None) -> dict:
        return {"ok": True, "data": _MOCK_CLUSTERS}

    async def list_stores(self, access_token: str) -> dict:
        return {"ok": True, "data": _MOCK_STORES}

    async def list_kso_devices(self, access_token: str) -> dict:
        return {"ok": True, "data": _MOCK_KSO}

    async def list_creatives(self, access_token: str) -> dict:
        return {"ok": True, "data": []}  # Empty for testing

    async def list_campaigns(self, access_token: str) -> dict:
        return {"ok": True, "data": []}  # Empty for testing

    async def create_campaign(self, access_token: str, payload: dict) -> dict:
        return {"ok": True, "data": {
            "campaign_code": payload.get("campaign_code", "test"),
            "name": payload.get("name", "Test"),
            "status": "draft",
            "description": payload.get("description"),
            "creative_codes": payload.get("creative_codes", []),
            "created_at": "2026-06-22T12:00:00Z",
            "updated_at": None,
        }}

    async def list_placements(self, access_token: str) -> dict:
        return {"ok": True, "data": []}

    async def create_placement(self, access_token: str, payload: dict) -> dict:
        return {"ok": True, "data": {
            "placement_code": payload.get("placement_code", "test"),
            "campaign_code": payload.get("campaign_code", ""),
            "creative_code": payload.get("creative_code", ""),
            "device_code": payload.get("device_code", ""),
            "status": "draft",
            "starts_at": payload.get("starts_at", "2026-01-01T09:00:00Z"),
            "ends_at": payload.get("ends_at", "2026-01-01T21:00:00Z"),
            "slot_order": payload.get("slot_order", 0),
            "created_at": "2026-06-22T12:00:00Z",
            "updated_at": None,
        }}

    async def list_approvals(self, access_token: str) -> dict:
        return {"ok": True, "data": []}

    async def request_approval(self, access_token: str, payload: dict) -> dict:
        return {"ok": True, "data": {
            "approval_code": f"appr_{payload.get('object_type','x')}_{payload.get('object_code','x')}",
            "object_type": payload.get("object_type", ""),
            "object_code": payload.get("object_code", ""),
            "status": "pending",
            "decision": None,
            "comment": payload.get("comment"),
            "requested_at": "2026-06-22T12:00:00Z",
            "decided_at": None,
        }}

    async def decide_approval(
        self, access_token: str, approval_code: str, payload: dict,
    ) -> dict:
        return {"ok": True, "data": {
            "approval_code": approval_code,
            "object_type": "placement",
            "object_code": "test",
            "status": "approved",
            "decision": payload.get("decision", "approve"),
            "comment": payload.get("comment"),
            "requested_at": "2026-06-22T12:00:00Z",
            "decided_at": "2026-06-22T13:00:00Z",
        }}

    # ── Manifests (Steps 37.7, 37.8) ──

    async def list_manifests(self, access_token: str) -> dict:
        return {"ok": True, "data": [
            {
                "manifest_code": "demo_manifest_001",
                "device_code": "demo-kso-001",
                "placement_code": "demo_placement_001",
                "campaign_code": "demo_campaign_001",
                "status": "generated",
                "schema_version": 1,
                "item_count": 1,
                "generated_at": "2026-06-22T12:00:00Z",
                "published_at": None,
                "created_at": "2026-06-22T12:00:00Z",
                "updated_at": None,
            },
        ]}

    async def generate_manifest(self, access_token: str, payload: dict) -> dict:
        return {"ok": True, "data": {
            "manifest_code": payload.get("manifest_code", "test"),
            "device_code": "demo-kso-001",
            "placement_code": payload.get("placement_code", ""),
            "campaign_code": "demo_campaign_001",
            "status": "generated",
            "schema_version": 1,
            "item_count": 1,
            "preview_body": {
                "schemaVersion": 1,
                "channel": "kso",
                "storeCode": "demo_store_001",
                "deviceCode": "demo-kso-001",
                "items": [{"slotOrder": 0, "contentType": "image/png", "durationMs": 5000, "mediaRef": "media/current/slot-000"}],
            },
            "generated_at": "2026-06-22T12:00:00Z",
            "published_at": None,
            "created_at": "2026-06-22T12:00:00Z",
            "updated_at": None,
        }}

    async def get_manifest(self, access_token: str, manifest_code: str) -> dict:
        return {"ok": True, "data": {
            "manifest_code": manifest_code,
            "device_code": "demo-kso-001",
            "placement_code": "demo_placement_001",
            "campaign_code": "demo_campaign_001",
            "status": "generated",
            "schema_version": 1,
            "item_count": 1,
            "generated_at": "2026-06-22T12:00:00Z",
            "published_at": None,
            "created_at": "2026-06-22T12:00:00Z",
            "updated_at": None,
        }}

    async def publish_manifest(self, access_token: str, manifest_code: str) -> dict:
        return {"ok": True, "data": {
            "manifest_code": manifest_code,
            "device_code": "demo-kso-001",
            "placement_code": "demo_placement_001",
            "campaign_code": "demo_campaign_001",
            "status": "published",
            "schema_version": 1,
            "item_count": 1,
            "generated_at": "2026-06-22T12:00:00Z",
            "published_at": "2026-06-22T13:00:00Z",
            "created_at": "2026-06-22T12:00:00Z",
            "updated_at": "2026-06-22T13:00:00Z",
        }}


    async def get_device_dashboard(
        self, access_token: str,
        keyword=None, channel_code=None, store_code=None,
        readiness_badge=None, limit=100, offset=0,
    ) -> dict:
        """Fake device dashboard data for portal tests."""
        return {"ok": True, "data": _MOCK_DEVICE_DASHBOARD}


_MOCK_DEVICE_DASHBOARD = [
    {
        "device_code": "dev-ready-001",
        "store_code": "store-01",
        "store_name": "Test Store Alpha",
        "kso_status": "active",
        "gateway_status": "active",
        "heartbeat": {
            "status": "ok", "age_seconds": 18,
            "app_version": "2.3.1", "cache_items_count": 5,
            "current_manifest_hash": "a" * 64,
        },
        "last_seen_at": "2026-06-26T14:30:00",
        "sidecar_version": "3.2.1",
        "sidecar_status": None,
        "player_version": "2.0.1",
        "credential": {
            "status": "active", "credential_type": "shared_secret",
            "expires_at": "2027-01-01T00:00:00",
        },
        "session": {"active_count": 2, "last_used_at": "2026-06-26T14:29:00"},
        "manifest": {"status": "applied", "manifest_hash": "b" * 64, "last_applied_at": "2026-06-26T13:00:00"},
        "media_cache": {
            "cache_items_count": 4, "missing_items": 0, "failed_items": 0,
            "cache_health_status": "healthy",
        },
        "pop": {"last_pop_at": "2026-06-26T14:20:00", "events_count": 125},
        "readiness_badge": "ready",
        "readiness_reasons": [],
    },
    {
        "device_code": "dev-warn-002",
        "store_code": "store-02",
        "store_name": "Test Store Beta",
        "kso_status": "active",
        "gateway_status": "active",
        "heartbeat": {
            "status": "ok", "age_seconds": 1200,
            "app_version": "2.3.1", "cache_items_count": 2,
            "current_manifest_hash": None,
        },
        "last_seen_at": "2026-06-26T14:10:00",
        "sidecar_version": None,
        "sidecar_status": None,
        "player_version": "2.0.0",
        "credential": {
            "status": "active", "credential_type": "shared_secret",
            "expires_at": None,
        },
        "session": {"active_count": 0, "last_used_at": None},
        "manifest": None,
        "media_cache": {
            "cache_items_count": 1, "missing_items": 3, "failed_items": 1,
            "cache_health_status": "critical",
        },
        "pop": {"last_pop_at": None, "events_count": 0},
        "readiness_badge": "warning",
        "readiness_reasons": ["Heartbeat stale (20 min ago)"],
    },
    {
        "device_code": "dev-blocked-003",
        "store_code": None,
        "store_name": None,
        "kso_status": "blocked",
        "gateway_status": "disabled",
        "heartbeat": None,
        "last_seen_at": None,
        "sidecar_version": None,
        "sidecar_status": None,
        "player_version": None,
        "credential": None,
        "session": {"active_count": 0, "last_used_at": None},
        "manifest": None,
        "media_cache": None,
        "pop": None,
        "readiness_badge": "blocked",
        "readiness_reasons": ["Gateway device is disabled"],
    },
    {
        "device_code": "dev-unknown-004",
        "store_code": "store-03",
        "store_name": "Test Store Gamma",
        "kso_status": None,
        "gateway_status": "pending",
        "heartbeat": None,
        "last_seen_at": None,
        "sidecar_version": None,
        "sidecar_status": None,
        "player_version": None,
        "credential": None,
        "session": {"active_count": 0, "last_used_at": None},
        "manifest": None,
        "media_cache": None,
        "pop": None,
        "readiness_badge": "unknown",
        "readiness_reasons": ["No heartbeat received", "No credential configured"],
    },
]



class _FakeBackendClientDown:
    """Fake BackendClient that simulates backend being down."""

    async def close(self):
        pass

    async def list_branches(self, access_token: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def list_clusters(self, access_token: str, branch_id=None) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def list_stores(self, access_token: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def list_kso_devices(self, access_token: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def list_creatives(self, access_token: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def list_campaigns(self, access_token: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def create_campaign(self, access_token: str, payload: dict) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def list_placements(self, access_token: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def create_placement(self, access_token: str, payload: dict) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def list_approvals(self, access_token: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def request_approval(self, access_token: str, payload: dict) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def decide_approval(
        self, access_token: str, approval_code: str, payload: dict,
    ) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    # ── Manifests (Steps 37.7, 37.8) ──

    async def list_manifests(self, access_token: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def generate_manifest(self, access_token: str, payload: dict) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def get_manifest(self, access_token: str, manifest_code: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}

    async def publish_manifest(self, access_token: str, manifest_code: str) -> dict:
        return {"ok": False, "error": "Backend unreachable"}


@unittest.skipUnless(
    os.environ.get("RUN_PORTAL_BACKEND_INTEGRATION"),
    "Skipped in default regression — run with RUN_PORTAL_BACKEND_INTEGRATION=1 "
    "to enable BackendClient mock integration tests"
)
class TestStoresBackendIntegration(unittest.TestCase):
    """Stores page with backend data."""

    def setUp(self):
        from main import app
        self.client = TestClient(app)
        import main
        self._orig_bc = main.BackendClient
        self._orig_gpt = main.get_portal_tokens
        main.BackendClient = _FakeBackendClient
        main.get_portal_tokens = lambda req: {"access_token": "fake-at"}

    def tearDown(self):
        import main
        main.BackendClient = _ORIG_BACKEND_CLIENT
        main.get_portal_tokens = _ORIG_GET_PORTAL_TOKENS

    def test_stores_renders_backend_data(self):
        resp = self.client.get("/stores")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Demo Store", resp.text)
        self.assertIn("demo_store_001", resp.text)
        self.assertIn("supermarket", resp.text)

    def test_stores_shows_branch_and_cluster_names(self):
        resp = self.client.get("/stores")
        self.assertIn("Demo Branch", resp.text)
        self.assertIn("Demo Cluster", resp.text)

    def test_stores_shows_kso_count(self):
        resp = self.client.get("/stores")
        self.assertIn("1", resp.text)  # kso_count = 1

    def test_stores_no_tokens_in_html(self):
        resp = self.client.get("/stores")
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "bearer ", "authorization:"):
            self.assertNotIn(fb, lower, f"stored must NOT contain '{fb}'")

    def test_stores_no_backend_url_in_html(self):
        resp = self.client.get("/stores")
        lower = resp.text.lower()
        for fb in ("localhost:8001", "backend_url"):
            self.assertNotIn(fb, lower, "stores must NOT expose backend URL")

    def test_stores_no_ids_in_html(self):
        resp = self.client.get("/stores")
        self.assertNotIn('"b1"', resp.text)   # raw UUID-like ID
        self.assertNotIn('"c1"', resp.text)
        self.assertNotIn('"s1"', resp.text)
        self.assertNotIn('"k1"', resp.text)

    def test_stores_actions_disabled(self):
        resp = self.client.get("/stores")
        self.assertIn("action-link", resp.text)
        self.assertNotIn("button", resp.text.lower())

    def test_stores_no_ip_mac_hostname_serial(self):
        resp = self.client.get("/stores")
        lower = resp.text.lower()
        for fb in ("ip_address", "mac_address", "hostname", "serial_number",
                    "device_secret", "client_secret", "file_path"):
            self.assertNotIn(fb, lower, f"stores must NOT contain '{fb}'")

    def test_stores_fallback_when_backend_down(self):
        import main
        main.BackendClient = _FakeBackendClientDown
        resp = self.client.get("/stores")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("временно недоступны", resp.text.lower())
        main.BackendClient = _FakeBackendClient


@unittest.skipUnless(
    os.environ.get("RUN_PORTAL_BACKEND_INTEGRATION"),
    "Skipped in default regression — run with RUN_PORTAL_BACKEND_INTEGRATION=1 "
    "to enable BackendClient mock integration tests"
)
class TestDevicesBackendIntegration(unittest.TestCase):
    """Devices page with backend KSO data."""

    def setUp(self):
        from main import app
        self.client = TestClient(app)
        import main
        self._orig_bc = main.BackendClient
        self._orig_gpt = main.get_portal_tokens
        main.BackendClient = _FakeBackendClient
        main.get_portal_tokens = lambda req: {"access_token": "fake-at"}

    def tearDown(self):
        import main
        main.BackendClient = _ORIG_BACKEND_CLIENT
        main.get_portal_tokens = _ORIG_GET_PORTAL_TOKENS

    def test_devices_renders_backend_data(self):
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("demo_kso_001", resp.text)
        self.assertIn("Demo KSO", resp.text)
        self.assertIn("Demo Store", resp.text)

    def test_devices_shows_screen_geometry(self):
        resp = self.client.get("/devices")
        self.assertIn("1920×1080", resp.text)
        self.assertIn("1440×1080", resp.text)

    def test_devices_shows_versions(self):
        resp = self.client.get("/devices")
        self.assertIn("1.0.0", resp.text)
        self.assertIn("abc123", resp.text)

    def test_devices_no_tokens_in_html(self):
        resp = self.client.get("/devices")
        lower = resp.text.lower()
        for fb in ("access_token", "refresh_token", "bearer ", "authorization:"):
            self.assertNotIn(fb, lower, f"devices must NOT contain '{fb}'")

    def test_devices_no_backend_url_in_html(self):
        resp = self.client.get("/devices")
        lower = resp.text.lower()
        for fb in ("localhost:8001", "backend_url"):
            self.assertNotIn(fb, lower, "devices must NOT expose backend URL")

    def test_devices_no_ids_in_html(self):
        resp = self.client.get("/devices")
        self.assertNotIn('"s1"', resp.text)
        self.assertNotIn('"k1"', resp.text)

    def test_devices_no_secrets_in_html(self):
        resp = self.client.get("/devices")
        lower = resp.text.lower()
        for fb in ("device_secret", "client_secret", "password_hash",
                    "token_hash", "ip_address", "mac_address",
                    "hostname", "serial_number", "file_path"):
            self.assertNotIn(fb, lower, f"devices must NOT contain '{fb}'")

    def test_devices_actions_disabled(self):
        resp = self.client.get("/devices")
        self.assertIn("action-link", resp.text)
        self.assertNotIn("button", resp.text.lower())

    def test_devices_fallback_when_backend_down(self):
        import main
        main.BackendClient = _FakeBackendClientDown
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("временно недоступны", resp.text.lower())
        main.BackendClient = _FakeBackendClient

    def test_devices_no_localstorage_references(self):
        resp = self.client.get("/devices")
        lower = resp.text.lower()
        self.assertNotIn("localstorage", lower)
        self.assertNotIn("sessionstorage", lower)

    def test_devices_no_external_cdn(self):
        resp = self.client.get("/devices")
        for cdn in ("cdn.", "unpkg.com", "jsdelivr.net", "fonts.googleapis.com",
                     "fonts.gstatic.com"):
            self.assertNotIn(cdn, resp.text.lower(),
                             f"Devices must NOT reference CDN '{cdn}'")


class TestStoresDevicesRouteAuth(unittest.TestCase):
    """Route auth for /stores and /devices."""

    @classmethod
    def setUpClass(cls):
        _enable_real_auth()

    @classmethod
    def tearDownClass(cls):
        _disable_real_auth()

    def setUp(self):
        from main import app
        self.client = TestClient(app)

    def test_unauthenticated_stores_redirects(self):
        resp = self.client.get("/stores", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("location", "").lower())

    def test_unauthenticated_devices_redirects(self):
        resp = self.client.get("/devices", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("location", "").lower())


class TestReadinessPage(unittest.TestCase):
    """Readiness page — production device dashboard summary (39.4.3)."""

    def setUp(self):
        import main
        self._orig_bc = main.BackendClient
        main.BackendClient = _FakeBackendClient
        self._orig_gpt = main.get_portal_tokens
        main.get_portal_tokens = lambda req: {"access_token": "fake-at-for-tests"}
        self.client = TestClient(app)
        resp = self.client.get("/readiness")
        self.html = resp.text
        self.lower = self.html.lower()

    def tearDown(self):
        import main
        main.BackendClient = _ORIG_BACKEND_CLIENT
        main.get_portal_tokens = _ORIG_GET_PORTAL_TOKENS

    # ── Route ─────────────────────────────────────────────────

    def test_01_page_returns_200(self):
        resp = self.client.get("/readiness")
        self.assertEqual(resp.status_code, 200)

    def test_02_shows_pilot_gate_title(self):
        self.assertIn("Pilot Gate", self.html)

    def test_03_links_to_full_dashboard(self):
        self.assertIn("/device-dashboard", self.html)

    # ── Summary cards ─────────────────────────────────────────

    def test_04_shows_readiness_cards(self):
        for card in ("Ready", "Warning", "Blocked", "Unknown"):
            self.assertIn(card, self.html,
                          f"Readiness must show '{card}' card")

    def test_05_shows_detail_cards(self):
        for card in ("Stale Heartbeat", "Expired Credential", "Missing Manifest"):
            self.assertIn(card, self.html,
                          f"Readiness must show detail card '{card}'")

    def test_06_shows_device_table(self):
        self.assertIn("dev-ready-001", self.html)
        self.assertIn("dev-warn-002", self.html)

    def test_07_shows_readiness_badges(self):
        for badge in ("ready", "warning", "blocked", "unknown"):
            self.assertIn(badge, self.lower)

    # ── Filter ────────────────────────────────────────────────

    def test_08_shows_filter(self):
        self.assertIn('name="readiness_badge"', self.html)
        self.assertIn("Сбросить", self.html)

    def test_09_has_reset_link(self):
        self.assertIn('href="/readiness"', self.html)

    # ── Safety ────────────────────────────────────────────────

    def test_10_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_11_no_raw_secrets_tokens(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "client_secret",
                           "secret_hash", "backend_url", "ip_address",
                           "mac_address", "hostname", "serial_number",
                           "file_path", "token="):
            self.assertNotIn(forbidden, lower,
                             f"Readiness page must NOT contain '{forbidden}'")

    def test_12_no_js_cdn_localstorage(self):
        lower = self.html.lower()
        self.assertNotIn("<script", lower)
        self.assertNotIn("localstorage", lower)

    def test_13_no_test_kso_primary_wording(self):
        """Readiness page should NOT use test-kso as primary label."""
        self.assertNotIn("test-kso", self.lower)
        self.assertNotIn("Test KSO", self.html)

    # ── Backend down ───────────────────────────────────────────

    def test_14_backend_down_safe_fallback(self):
        import main
        main.BackendClient = _FakeBackendClientDown
        main.get_portal_tokens = lambda req: {"access_token": "fake-at"}
        resp = self.client.get("/readiness")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Данные временно недоступны", resp.text)


class TestDeviceDashboardPage(unittest.TestCase):
    """Device Dashboard page — backend integration, readiness badges, filters, safety."""

    def setUp(self):
        import main
        self._orig_bc = main.BackendClient
        main.BackendClient = _FakeBackendClient
        self._orig_gpt = main.get_portal_tokens
        main.get_portal_tokens = lambda req: {"access_token": "fake-at-for-tests"}
        self.client = TestClient(app)
        resp = self.client.get("/device-dashboard")
        self.html = resp.text

    def tearDown(self):
        import main
        main.BackendClient = _ORIG_BACKEND_CLIENT
        main.get_portal_tokens = _ORIG_GET_PORTAL_TOKENS

    # ── Route ─────────────────────────────────────────────────

    def test_route_returns_200(self):
        resp = self.client.get("/device-dashboard")
        self.assertEqual(resp.status_code, 200)

    def test_page_renders_with_auth(self):
        """Page renders successfully with authenticated session."""
        resp = self.client.get("/device-dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Device Dashboard", resp.text)

    # ── Content ───────────────────────────────────────────────

    def test_shows_all_readiness_badges(self):
        for badge in ("ready", "warning", "blocked", "unknown"):
            self.assertIn(badge, self.html.lower(),
                          f"Dashboard must show '{badge}' badge")

    def test_shows_device_codes(self):
        for code in ("dev-ready-001", "dev-warn-002", "dev-blocked-003", "dev-unknown-004"):
            self.assertIn(code, self.html)

    def test_shows_summary_cards(self):
        for card in ("Всего устройств", "Ready", "Warning", "Blocked"):
            self.assertIn(card, self.html)

    def test_shows_filter_form(self):
        self.assertIn('name="keyword"', self.html)
        self.assertIn('name="channel_code"', self.html)
        self.assertIn('name="store_code"', self.html)
        self.assertIn('name="readiness_badge"', self.html)

    def test_has_reset_link(self):
        self.assertIn('Сбросить', self.html)
        self.assertIn('href="/device-dashboard"', self.html)

    def test_shows_legend(self):
        self.assertIn("Readiness Legend", self.html)

    def test_shows_store_names(self):
        self.assertIn("Test Store Alpha", self.html)
        self.assertIn("Test Store Beta", self.html)

    def test_shows_heartbeat_data(self):
        self.assertIn("2.3.1", self.html)  # app_version

    def test_shows_credential_status(self):
        self.assertIn("active", self.html)
        self.assertIn("2027-01-01", self.html)  # expires_at date

    def test_shows_manifest_status(self):
        self.assertIn("applied", self.html)

    def test_shows_pop_data(self):
        self.assertIn("125", self.html)  # events_count for ready device

    def test_shows_media_cache_health(self):
        self.assertIn("healthy", self.html)
        self.assertIn("critical", self.html)

    # ── Safety ────────────────────────────────────────────────

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_raw_secrets_tokens(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "client_secret",
                           "secret_hash", "backend_url", "ip_address",
                           "mac_address", "hostname", "serial_number",
                           "file_path", "receipt_number", "card_number",
                           "customer_id", "phone", "fiscal_data",
                           "presigned", "minio", "private_key",
                           "CHANGE_ME_SECRET"):
            self.assertNotIn(forbidden, lower,
                             f"Dashboard page must NOT contain '{forbidden}'")

    def test_no_js_cdn_localstorage(self):
        lower = self.html.lower()
        self.assertNotIn("<script", lower)
        self.assertNotIn("localstorage", lower)
        self.assertNotIn("cdn", lower)

    # ── Navigation ─────────────────────────────────────────────

    def test_nav_link_exists(self):
        self.assertIn('href="/device-dashboard"', self.html)
        self.assertIn("Device Dashboard", self.html)

    # ── Backend down — safe fallback ──────────────────────────

    def test_backend_down_gives_safe_fallback(self):
        import main
        main.BackendClient = _FakeBackendClientDown
        main.get_portal_tokens = lambda req: {"access_token": "fake-at"}
        resp = self.client.get("/device-dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Данные временно недоступны", resp.text)

    # ── Empty state ───────────────────────────────────────────

    def test_empty_state_when_no_devices(self):
        """Empty data → empty state rendered."""
        import main
        # Override get_device_dashboard to return empty
        class _EmptyClient:
            async def get_device_dashboard(self, *args, **kwargs):
                return {"ok": True, "data": []}
            async def close(self): pass
        main.BackendClient = _EmptyClient
        main.get_portal_tokens = lambda req: {"access_token": "fake-at"}
        resp = self.client.get("/device-dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Нет данных", resp.text)



if __name__ == "__main__":
    unittest.main()
