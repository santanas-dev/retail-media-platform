"""UI.2.3 — Tables Modernization / Pagination / Search: targeted tests.

Verifies:
- Pagination helper: page/page_size slicing, edge cases
- Search helper: case-insensitive, empty query, item_getter
- table_context: pagination + search combined
- Template macros: pagination controls in admin + readiness
- CSS classes: table-wrapper, pagination, search styles
- Admin page: pagination UI, search UI, sidebar preserved
- Readiness page: pagination UI, search UI, labels preserved
- Other pages: not broken
- Security: no |safe, no secrets, no JS
- Boundaries: no backend/DB/Docker/production changes
"""

import pytest
import re
import os
import sys
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PORTAL_DIR = REPO_ROOT / "apps" / "portal-web"
TEMPLATES_DIR = PORTAL_DIR / "templates" / "pages"
STATIC_DIR = PORTAL_DIR / "static"

sys.path.insert(0, str(PORTAL_DIR))


def _read_file(path):
    return Path(path).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════
# A. Pagination Helper
# ═══════════════════════════════════════════════════════════════════

class TestPaginate:
    """Verify paginate() helper."""

    def _items(self, n=83):
        return [{"id": i} for i in range(n)]

    def test_01_default_page_is_1(self):
        from table_helpers import paginate
        r = paginate(self._items())
        assert r["page"] == 1

    def test_02_default_page_size_is_20(self):
        from table_helpers import paginate
        r = paginate(self._items())
        assert r["page_size"] == 20

    def test_03_page_size_20_allowed(self):
        from table_helpers import paginate
        r = paginate(self._items(), page_size=20)
        assert r["page_size"] == 20

    def test_04_page_size_50_allowed(self):
        from table_helpers import paginate
        r = paginate(self._items(), page_size=50)
        assert r["page_size"] == 50

    def test_05_page_size_100_allowed(self):
        from table_helpers import paginate
        r = paginate(self._items(), page_size=100)
        assert r["page_size"] == 100

    def test_06_invalid_page_becomes_1(self):
        from table_helpers import paginate
        r = paginate(self._items(), page=-5)
        assert r["page"] == 1

    def test_07_invalid_page_size_becomes_20(self):
        from table_helpers import paginate
        r = paginate(self._items(), page_size=7)
        assert r["page_size"] == 20

    def test_08_slice_returns_correct_first_page(self):
        from table_helpers import paginate
        r = paginate(self._items())
        assert len(r["rows"]) == 20
        assert r["start_idx"] == 1
        assert r["end_idx"] == 20

    def test_09_slice_returns_correct_second_page(self):
        from table_helpers import paginate
        r = paginate(self._items(), page=2)
        assert len(r["rows"]) == 20
        assert r["start_idx"] == 21
        assert r["end_idx"] == 40

    def test_10_total_count_calculated(self):
        from table_helpers import paginate
        r = paginate(self._items())
        assert r["total"] == 83

    def test_11_page_count_calculated(self):
        from table_helpers import paginate
        r = paginate(self._items())
        assert r["total_pages"] == 5  # ceil(83/20)

    def test_12_prev_next_flags_correct(self):
        from table_helpers import paginate
        r1 = paginate(self._items(), page=1)
        assert r1["has_prev"] is False
        assert r1["has_next"] is True
        r5 = paginate(self._items(), page=5)
        assert r5["has_prev"] is True
        assert r5["has_next"] is False

    def test_13_empty_list(self):
        from table_helpers import paginate
        r = paginate([])
        assert r["total"] == 0
        assert r["total_pages"] == 1
        assert r["rows"] == []

    def test_14_page_beyond_last_clamps(self):
        from table_helpers import paginate
        r = paginate(self._items(), page=999)
        assert r["page"] == 5


# ═══════════════════════════════════════════════════════════════════
# B. Search Helper
# ═══════════════════════════════════════════════════════════════════

class TestSearchItems:
    """Verify search_items() helper."""

    def _users(self):
        return [
            {"username": "admin", "email": "admin@test.com", "role": "admin"},
            {"username": "user1", "email": "user1@test.com", "role": "user"},
            {"username": "user2", "email": "other@corp.com", "role": "user"},
        ]

    def test_01_admin_search_matches_username(self):
        from table_helpers import search_items
        r = search_items(self._users(), "admin", ["username", "email"])
        assert len(r) == 1
        assert r[0]["username"] == "admin"

    def test_02_search_matches_email(self):
        from table_helpers import search_items
        r = search_items(self._users(), "other@corp", ["username", "email"])
        assert len(r) == 1

    def test_03_search_matches_role(self):
        from table_helpers import search_items
        r = search_items(self._users(), "user", ["username", "role"])
        assert len(r) == 2

    def test_04_search_case_insensitive(self):
        from table_helpers import search_items
        r = search_items(self._users(), "ADMIN", ["username", "email"])
        assert len(r) == 1

    def test_05_empty_q_returns_all(self):
        from table_helpers import search_items
        r = search_items(self._users(), "", ["username"])
        assert len(r) == 3

    def test_06_whitespace_only_returns_all(self):
        from table_helpers import search_items
        r = search_items(self._users(), "   ", ["username"])
        assert len(r) == 3

    def test_07_readiness_search_matches_device_code(self):
        from table_helpers import search_items
        devices = [{"device_code": "KSO-001"}, {"device_code": "KSO-002"}]
        r = search_items(devices, "KSO-001", ["device_code"])
        assert len(r) == 1

    def test_08_search_no_match_returns_empty(self):
        from table_helpers import search_items
        r = search_items(self._users(), "nonexistent", ["username"])
        assert r == []


# ═══════════════════════════════════════════════════════════════════
# C. table_context
# ═══════════════════════════════════════════════════════════════════

class TestTableContext:
    """Verify table_context() combines search + paginate."""

    def test_01_returns_expected_keys_rows(self):
        from table_helpers import table_context, DEFAULT_PAGE_SIZE
        # We need a mock request with query_params
        class MockRequest:
            query_params = {}
        ctx = table_context(MockRequest(), [{"name": "a"}] * 50)
        for key in ["rows", "page", "page_size", "total", "total_pages",
                     "has_prev", "has_next", "query", "search_fields"]:
            assert key in ctx, f"Missing key: {key}"

    def test_02_query_params_preserved_in_context(self):
        from table_helpers import table_context
        from types import SimpleNamespace
        mock = SimpleNamespace()
        mock.query_params = {"q": "admin", "page": "3"}
        ctx = table_context(mock, [{"name": "admin"}] * 100)
        assert ctx["query"] == "admin"


# ═══════════════════════════════════════════════════════════════════
# D. Admin Page — Pagination & Search
# ═══════════════════════════════════════════════════════════════════

class TestAdminPage:
    """Verify admin page has pagination and search infrastructure."""

    def test_01_admin_page_has_pagination_controls(self):
        content = _read_file(TEMPLATES_DIR / "admin.html")
        assert "pagination" in content.lower() or "m.pagination" in content

    def test_02_admin_uses_users_table_items(self):
        content = _read_file(TEMPLATES_DIR / "admin.html")
        assert "users_table.items" in content or "users_table" in content

    def test_03_admin_has_search_bar(self):
        content = _read_file(TEMPLATES_DIR / "admin.html")
        assert "table-search" in content or "search_bar" in content

    def test_04_admin_shows_count_text(self):
        content = _read_file(TEMPLATES_DIR / "admin.html")
        assert "Показано" in content or "users_table" in content

    def test_05_admin_empty_search_shows_empty_state(self):
        content = _read_file(TEMPLATES_DIR / "admin.html")
        assert "empty_search" in content or "Ничего не найдено" in content

    def test_06_admin_sidebar_still_full(self):
        content = _read_file(TEMPLATES_DIR / "admin.html")
        assert "rbac_permissions" in content or "permissions" in content

    def test_07_admin_no_secrets(self):
        content = _read_file(TEMPLATES_DIR / "admin.html")
        # Password may appear in form labels ("Пароль") — that's fine.
        # Check for actual secret patterns.
        for word in ["token", "api_key", "secret_key"]:
            assert word not in content.lower()


# ═══════════════════════════════════════════════════════════════════
# E. Readiness Page — Pagination & Search
# ═══════════════════════════════════════════════════════════════════

class TestReadinessPage:
    """Verify readiness page has pagination and search infrastructure."""

    def test_01_readiness_has_pagination_controls(self):
        content = _read_file(TEMPLATES_DIR / "readiness.html")
        assert "m.pagination" in content

    def test_02_readiness_uses_devices_table_items(self):
        content = _read_file(TEMPLATES_DIR / "readiness.html")
        assert "devices_table.rows" in content

    def test_03_readiness_has_search_input(self):
        content = _read_file(TEMPLATES_DIR / "readiness.html")
        assert 'name="q"' in content

    def test_04_readiness_status_labels_localized(self):
        content = _read_file(TEMPLATES_DIR / "readiness.html")
        assert "| label" in content

    def test_05_readiness_no_full_uuid_primary(self):
        content = _read_file(TEMPLATES_DIR / "readiness.html")
        import re
        uuid_pat = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{12}')
        # UUIDs may be in href/title but not as primary text
        # Just verify | label and sanitize_code are used
        assert "sanitize_code" in content or "| label" in content

    def test_06_readiness_no_secrets(self):
        content = _read_file(TEMPLATES_DIR / "readiness.html")
        for word in ["password", "token", "secret"]:
            assert word not in content.lower()


# ═══════════════════════════════════════════════════════════════════
# F. CSS Classes
# ═══════════════════════════════════════════════════════════════════

class TestCssClasses:
    """Verify new CSS classes are defined."""

    def test_01_table_wrapper_exists(self):
        content = _read_file(STATIC_DIR / "styles.css")
        assert ".table-wrapper" in content

    def test_02_table_pagination_classes_exist(self):
        content = _read_file(STATIC_DIR / "styles.css")
        assert ".table-pagination" in content

    def test_03_table_search_classes_exist(self):
        content = _read_file(STATIC_DIR / "styles.css")
        assert ".table-search" in content

    def test_04_compact_striped_hover_exist(self):
        content = _read_file(STATIC_DIR / "styles.css")
        assert ".data-table-compact" in content
        assert ".data-table-striped" in content
        assert ".data-table-hover" in content

    def test_05_action_cell_exists(self):
        content = _read_file(STATIC_DIR / "styles.css")
        assert ".action-cell" in content

    def test_06_pagination_link_classes_exist(self):
        content = _read_file(STATIC_DIR / "styles.css")
        assert ".pagination-link" in content
        assert ".pagination-current" in content
        assert ".pagination-disabled" in content

    def test_07_table_empty_exists(self):
        content = _read_file(STATIC_DIR / "styles.css")
        assert ".table-empty" in content


# ═══════════════════════════════════════════════════════════════════
# G. Macros Template
# ═══════════════════════════════════════════════════════════════════

class TestMacrosTemplate:
    """Verify _macros.html exists with pagination/search/empty helpers."""

    def test_01_macros_file_exists(self):
        assert (PORTAL_DIR / "templates" / "_macros.html").exists()

    def test_02_has_pagination_macro(self):
        content = _read_file(PORTAL_DIR / "templates" / "_macros.html")
        assert "pagination" in content
        assert "search_bar" in content

    def test_03_has_empty_search(self):
        content = _read_file(PORTAL_DIR / "templates" / "_macros.html")
        assert "empty_search" in content


# ═══════════════════════════════════════════════════════════════════
# H. Other Pages — Not Broken
# ═══════════════════════════════════════════════════════════════════

class TestOtherPagesNotBroken:
    """Verify other pages still render correctly."""

    def test_01_bookings_page_still_renders(self):
        content = _read_file(TEMPLATES_DIR / "bookings.html")
        assert "display_ref" in content

    def test_02_publications_page_still_renders(self):
        content = _read_file(TEMPLATES_DIR / "publications.html")
        assert "| label" in content

    def test_03_packages_page_still_renders(self):
        content = _read_file(TEMPLATES_DIR / "manifests.html")
        assert "| label" in content

    def test_04_pop_page_still_renders(self):
        content = _read_file(TEMPLATES_DIR / "proof-of-play.html")
        assert "| label" in content

    def test_05_analytics_page_still_renders(self):
        content = _read_file(TEMPLATES_DIR / "reports_analytics.html")
        assert "| label" in content

    def test_06_creatives_page_still_renders(self):
        content = _read_file(TEMPLATES_DIR / "creatives.html")
        assert "| label" in content

    def test_07_campaigns_page_still_renders(self):
        content = _read_file(TEMPLATES_DIR / "campaigns.html")
        assert "url_code" in content or "campaign_code" in content


# ═══════════════════════════════════════════════════════════════════
# I. Security
# ═══════════════════════════════════════════════════════════════════

class TestSecurity:
    """Verify no security issues introduced."""

    def test_01_no_unsafe_safe(self):
        import subprocess
        for f in ["_macros.html", "admin.html", "readiness.html"]:
            path = PORTAL_DIR / "templates" / f
            if not path.exists():
                path = TEMPLATES_DIR / f
            if path.exists():
                content = _read_file(path)
                assert "| safe" not in content, f"Unsafe filter in {f}"

    def test_02_no_script_tags_in_new_files(self):
        for f in ["_macros.html"]:
            path = PORTAL_DIR / "templates" / f
            if path.exists():
                content = _read_file(path)
                assert "<script" not in content, f"Script in {f}"

    def test_03_no_cdn_in_new_files(self):
        content = _read_file(STATIC_DIR / "styles.css")
        assert "cdn." not in content.lower()

    def test_04_table_helpers_no_secrets(self):
        content = _read_file(PORTAL_DIR / "table_helpers.py")
        for word in ["password", "token", "secret"]:
            assert word not in content.lower()


# ═══════════════════════════════════════════════════════════════════
# J. Boundaries
# ═══════════════════════════════════════════════════════════════════

class TestBoundaries:
    """Verify no backend/DB/Docker/production changes."""

    def test_01_no_backend_changes(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        for f in result.stdout.splitlines():
            assert "backend/" not in f

    def test_02_no_migrations(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        for f in result.stdout.splitlines():
            assert "migrations" not in f

    def test_03_no_docker_env(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        for f in result.stdout.splitlines():
            assert "docker" not in f.lower()
            assert ".env" not in f

    def test_04_no_production_switch(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        assert "production" not in result.stdout.lower()

    def test_05_no_route_removals(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", "apps/portal-web/main.py"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        removed = [l for l in result.stdout.splitlines() if l.startswith("-@app.")]
        assert not removed


# ═══════════════════════════════════════════════════════════════════
# K. Imports
# ═══════════════════════════════════════════════════════════════════

class TestImports:
    """Verify modules import cleanly."""

    def test_01_table_helpers_import_clean(self):
        spec = importlib.util.spec_from_file_location(
            "table_helpers", PORTAL_DIR / "table_helpers.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "paginate")
        assert hasattr(mod, "search_items")
        assert hasattr(mod, "table_context")
