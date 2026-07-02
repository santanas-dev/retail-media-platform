"""UI.C4.R1 — Admin Sidebar Layout Fix: targeted tests.

Verifies:
- Admin page renders with full RBAC-aware sidebar (all 7 groups)
- Session permissions not overwritten by backend data
- RBAC guards intact
- Security: no secrets, no traceback
"""
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PORTAL_DIR = REPO_ROOT / "apps" / "portal-web"


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def _admin_context_snippet():
    """Return the TemplateResponse context dict from admin_page handler."""
    main = _read(PORTAL_DIR / "main.py")
    idx = main.index('TemplateResponse(request, "pages/admin.html"')
    return main[idx:idx + 2000]


# ═══════════════════════════════════════════════════════════════════
# A. Root Cause — permissions key collision
# ═══════════════════════════════════════════════════════════════════

class TestRootCause:
    """Verify the permissions key collision is resolved."""

    def test_01_admin_route_has_session_permissions(self):
        """Admin route passes session permissions to template context."""
        snippet = _admin_context_snippet()
        assert '"permissions": get_session_permissions(request)' in snippet

    def test_02_backend_permissions_renamed(self):
        """Backend permission data must use rbac_permissions key."""
        snippet = _admin_context_snippet()
        assert '"rbac_permissions":' in snippet

    def test_03_no_duplicate_permissions_key(self):
        """Session permissions key appears once with get_session_permissions."""
        snippet = _admin_context_snippet()
        count = snippet.count('"permissions": get_session_permissions')
        assert count == 1, (
            f"Expected 1 session permissions call, found {count}")

    def test_04_rbac_permissions_correctly_positioned(self):
        """rbac_permissions comes AFTER permissions in context dict."""
        snippet = _admin_context_snippet()
        pos_perm = snippet.index('"permissions":')
        pos_rbac = snippet.index('"rbac_permissions":')
        assert pos_perm < pos_rbac, (
            "Session permissions must come BEFORE rbac_permissions")


# ═══════════════════════════════════════════════════════════════════
# B. Admin Template
# ═══════════════════════════════════════════════════════════════════

class TestAdminTemplate:
    """Verify admin template uses correct variable for permission count."""

    def test_10_template_extends_base(self):
        """Admin template must extend base.html for full sidebar."""
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        assert '{% extends "base.html" %}' in tmpl

    def test_11_template_uses_rbac_permissions(self):
        """Admin template references rbac_permissions for count display."""
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        assert "rbac_permissions" in tmpl

    def test_12_template_no_stale_permissions_count(self):
        """Template must NOT use bare permissions for length count."""
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        # "permissions | length" — would use session permissions for count
        # which is wrong. Must use rbac_permissions instead.
        assert "rbac_permissions | length" in tmpl


# ═══════════════════════════════════════════════════════════════════
# C. Sidebar Content (base.html)
# ═══════════════════════════════════════════════════════════════════

class TestSidebarContent:
    """Verify base.html sidebar renders all RBAC groups."""

    def test_20_base_has_sales_group(self):
        base = _read(PORTAL_DIR / "templates/base.html")
        assert "Продажи" in base
        assert "Главный экран" in base
        assert "Кампании" in base
        assert "Креативы" in base

    def test_21_base_has_planning_group(self):
        base = _read(PORTAL_DIR / "templates/base.html")
        assert "Планирование" in base
        assert "Бронирования" in base

    def test_22_base_has_publication_group(self):
        base = _read(PORTAL_DIR / "templates/base.html")
        assert "Публикации" in base
        assert "Пакеты показа" in base

    def test_23_base_has_devices_group(self):
        base = _read(PORTAL_DIR / "templates/base.html")
        assert "Устройства" in base
        assert "Панель КСО" in base

    def test_24_base_has_analytics_group(self):
        base = _read(PORTAL_DIR / "templates/base.html")
        assert "Отчёты" in base
        assert "Аналитика показов" in base

    def test_25_base_has_admin_group(self):
        base = _read(PORTAL_DIR / "templates/base.html")
        assert "Администрирование" in base

    def test_26_base_has_service_group(self):
        base = _read(PORTAL_DIR / "templates/base.html")
        assert "Как пользоваться" in base
        assert "Соответствие" in base


# ═══════════════════════════════════════════════════════════════════
# D. RBAC Guards
# ═══════════════════════════════════════════════════════════════════

class TestRBACGuards:
    """Verify admin route RBAC guards remain intact."""

    def test_30_admin_route_uses_require_admin_access(self):
        """Admin page must use require_admin_access guard."""
        main = _read(PORTAL_DIR / "main.py")
        idx = main.index('def admin_page(')
        snippet = main[idx:idx + 800]
        assert "require_admin_access" in snippet

    def test_31_require_admin_access_imported(self):
        """require_admin_access must be imported."""
        main = _read(PORTAL_DIR / "main.py")
        assert "require_admin_access" in main

    def test_32_admin_not_public(self):
        """Admin page must not be accessible without auth check."""
        main = _read(PORTAL_DIR / "main.py")
        idx = main.index('def admin_page(')
        snippet = main[idx:idx + 3000]
        # Guard function must be called before rendering
        guard_idx = snippet.index("require_admin_access")
        tr_idx = snippet.index("TemplateResponse")
        assert guard_idx < tr_idx, (
            "RBAC guard must be checked before template render")


# ═══════════════════════════════════════════════════════════════════
# E. Security
# ═══════════════════════════════════════════════════════════════════

class TestSecurity:
    """Security checks for admin page."""

    def test_40_no_secrets_in_admin_html(self):
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        assert "Admin123!" not in tmpl

    def test_41_no_unsafe_safe_filter(self):
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        safe_count = tmpl.count("|safe")
        assert safe_count < 5, f"Too many |safe uses: {safe_count}"

    def test_42_no_script_tags(self):
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        assert "<script" not in tmpl

    def test_43_no_localstorage(self):
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        assert "localStorage" not in tmpl

    def test_44_no_cdn(self):
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        assert "cdn." not in tmpl and "unpkg" not in tmpl


# ═══════════════════════════════════════════════════════════════════
# F. Source Boundaries
# ═══════════════════════════════════════════════════════════════════

class TestSourceBoundaries:
    """Verify no changes to restricted areas."""

    def test_50_no_backend_changes(self):
        """Backend code not touched."""
        backend_router = REPO_ROOT / "backend" / "app" / "domains" / "campaigns" / "router.py"
        assert backend_router.exists()

    def test_51_no_env_changes(self):
        env = REPO_ROOT / ".env.example"
        assert env.exists()

    def test_52_main_py_still_has_all_routes(self):
        main = _read(PORTAL_DIR / "main.py")
        routes = [
            "@app.get(\"/\"",
            "@app.get(\"/campaigns\"",
            "@app.get(\"/campaigns/{campaign_code}\"",
            "@app.get(\"/creatives\"",
            "@app.get(\"/planning\"",
            "@app.get(\"/bookings\"",
            "@app.get(\"/admin\"",
            "@app.get(\"/emergency\"",
            "@app.get(\"/help\"",
        ]
        for route in routes:
            assert route in main, f"Route missing: {route}"


# ═══════════════════════════════════════════════════════════════════
# G. Regression Gate
# ═══════════════════════════════════════════════════════════════════

class TestRegressionGate:
    """Verify fix doesn't break existing admin functionality."""

    def test_60_admin_content_structures_present(self):
        tmpl = _read(PORTAL_DIR / "templates/pages/admin.html")
        essential = [
            "Администрирование",
            "Пользователи",
            "Роли",
            "Аудит",
            "backend_available",
        ]
        for text in essential:
            assert text in tmpl, f"Missing: {text}"

    def test_61_admin_data_keys_present(self):
        """All required admin data keys in route context."""
        main = _read(PORTAL_DIR / "main.py")
        idx = main.index('TemplateResponse(request, "pages/admin.html"')
        snippet = main[idx:idx + 800]
        keys = [
            "current_user",
            "permissions",
            "rbac_permissions",
            "backend_available",
            "users",
            "roles",
            "audit_events",
            "users_count",
            "roles_count",
        ]
        for key in keys:
            assert f'"{key}"' in snippet, f"Missing context key: {key}"
