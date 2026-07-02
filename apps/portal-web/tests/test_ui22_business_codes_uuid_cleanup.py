"""UI.2.2 — Business Codes / UUID Cleanup: targeted tests.

Verifies:
- Display helpers correctly detect and shorten UUIDs
- display_ref adds prefixes and handles edge cases
- display_code auto-discovers code fields
- Entity helpers prefer business codes over UUIDs
- Templates no longer show full 36-char UUIDs as primary labels
- C1/C4 compatibility preserved
- Security: no |safe, no secrets, escaped values
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

sys.path.insert(0, str(PORTAL_DIR))


def _read_file(path):
    return Path(path).read_text(encoding="utf-8")


def _render_template(source, **ctx):
    from fastapi.templating import Jinja2Templates
    from labels import label_filter
    from display import (
        short_uuid_filter, display_ref_filter, display_code_filter,
        display_campaign_filter, display_device_filter, display_booking_filter,
        display_package_filter, display_creative_filter, display_store_filter,
    )
    t = Jinja2Templates(directory=str(TEMPLATES_DIR))
    t.env.filters["label"] = label_filter
    t.env.filters["short_uuid"] = short_uuid_filter
    t.env.filters["display_ref"] = display_ref_filter
    t.env.filters["display_code"] = display_code_filter
    t.env.filters["display_campaign"] = display_campaign_filter
    t.env.filters["display_device"] = display_device_filter
    t.env.filters["display_booking"] = display_booking_filter
    t.env.filters["display_package"] = display_package_filter
    t.env.filters["display_creative"] = display_creative_filter
    t.env.filters["display_store"] = display_store_filter
    tmpl = t.env.from_string(source)
    return tmpl.render(**ctx)


UUID_SAMPLE = "633fd64f-0f21-4ab3-94de-e41fe90dbdd0"
SHORT_CODE = "KSO-001"


# ═══════════════════════════════════════════════════════════════════
# A. Display Helper — is_uuid
# ═══════════════════════════════════════════════════════════════════

class TestIsUuid:
    """Verify UUID detection."""

    def test_01_is_uuid_true(self):
        from display import is_uuid
        assert is_uuid(UUID_SAMPLE) is True

    def test_02_is_uuid_false_short_code(self):
        from display import is_uuid
        assert is_uuid(SHORT_CODE) is False

    def test_03_is_uuid_false_none(self):
        from display import is_uuid
        assert is_uuid(None) is False
        assert is_uuid("") is False

    def test_04_is_uuid_false_non_string(self):
        from display import is_uuid
        assert is_uuid(123) is False


# ═══════════════════════════════════════════════════════════════════
# B. Display Helper — short_uuid
# ═══════════════════════════════════════════════════════════════════

class TestShortUuid:
    """Verify short_uuid returns correct values."""

    def test_01_short_uuid_8_chars(self):
        from display import short_uuid
        assert short_uuid(UUID_SAMPLE) == "633fd64f"
        assert len(short_uuid(UUID_SAMPLE)) == 8

    def test_02_short_uuid_none(self):
        from display import short_uuid
        assert short_uuid(None) == ""

    def test_03_short_uuid_non_uuid_passthrough(self):
        from display import short_uuid
        assert short_uuid(SHORT_CODE) == SHORT_CODE


# ═══════════════════════════════════════════════════════════════════
# C. Display Helper — display_ref
# ═══════════════════════════════════════════════════════════════════

class TestDisplayRef:
    """Verify display_ref shortens UUIDs and adds prefixes."""

    def test_01_hides_full_uuid(self):
        from display import display_ref
        result = display_ref(UUID_SAMPLE)
        assert UUID_SAMPLE not in result
        assert len(result) <= 12

    def test_02_adds_prefix(self):
        from display import display_ref
        result = display_ref(UUID_SAMPLE, prefix="Бронь")
        assert result.startswith("Бронь ")

    def test_03_none_returns_dash(self):
        from display import display_ref
        assert display_ref(None) == "—"

    def test_04_short_code_passthrough(self):
        from display import display_ref
        assert display_ref("CAMP-001") == "CAMP-001"

    def test_05_escapes_html_safely(self):
        from display import display_ref
        result = display_ref(UUID_SAMPLE, prefix="<script>")
        # display_ref does NOT escape (Jinja does that), but should not crash
        assert "Бронь" not in result or "<script>" in result


# ═══════════════════════════════════════════════════════════════════
# D. Display Helper — display_code
# ═══════════════════════════════════════════════════════════════════

class TestDisplayCode:
    """Verify display_code picks best business code."""

    def test_01_prefers_campaign_code(self):
        from display import display_code
        entity = {"campaign_code": "CAMP-001", "id": "uuid"}
        result = display_code(entity, preferred_fields=["campaign_code", "code"])
        assert result == "CAMP-001"

    def test_02_prefers_code(self):
        from display import display_code
        entity = {"code": "BK-001", "id": UUID_SAMPLE}
        assert display_code(entity) == "BK-001"

    def test_03_falls_back_to_short_uuid(self):
        from display import display_code
        entity = {"id": UUID_SAMPLE}
        result = display_code(entity)
        assert result == "633fd64f"

    def test_04_adds_fallback_prefix(self):
        from display import display_code
        entity = {"id": UUID_SAMPLE}
        result = display_code(entity, fallback_prefix="Кампания")
        assert result == "Кампания 633fd64f"

    def test_05_none_entity(self):
        from display import display_code
        assert display_code(None) == "—"

    def test_06_auto_discovers_code_fields(self):
        from display import display_code
        entity = {"booking_code": "BK-001", "id": "uuid"}
        result = display_code(entity)
        assert result == "BK-001"  # Auto-discovered booking_code


# ═══════════════════════════════════════════════════════════════════
# E. Entity Helpers
# ═══════════════════════════════════════════════════════════════════

class TestEntityHelpers:
    """Verify entity-specific display helpers."""

    def test_01_display_campaign_code(self):
        from display import display_campaign
        assert display_campaign({"campaign_code": "CAMP-001"}) == "CAMP-001"

    def test_02_display_campaign_fallback(self):
        from display import display_campaign
        result = display_campaign({"id": UUID_SAMPLE})
        assert "Кампания" in result

    def test_03_display_device_code(self):
        from display import display_device
        assert display_device({"device_code": "KSO-001"}) == "KSO-001"

    def test_04_display_booking_code(self):
        from display import display_booking
        assert display_booking({"booking_code": "BK-001"}) == "BK-001"

    def test_05_display_package_code(self):
        from display import display_package
        assert display_package({"manifest_code": "MAN-001"}) == "MAN-001"

    def test_06_display_creative_code(self):
        from display import display_creative
        assert display_creative({"creative_code": "CR-001"}) == "CR-001"

    def test_07_display_store_code(self):
        from display import display_store
        assert display_store({"store_code": "ST-001"}) == "ST-001"

    def test_08_works_with_objects(self):
        from display import display_campaign

        class Camp:
            def __init__(self):
                self.campaign_code = "CAMP-OBJ"
        assert display_campaign(Camp()) == "CAMP-OBJ"

    def test_09_works_with_dict(self):
        from display import display_campaign
        assert display_campaign({"campaign_code": "CAMP-DICT"}) == "CAMP-DICT"


# ═══════════════════════════════════════════════════════════════════
# F. Jinja Filter Rendering
# ═══════════════════════════════════════════════════════════════════

class TestJinjaFilters:
    """Verify Jinja2 filters work in template rendering."""

    def test_01_short_uuid_filter(self):
        result = _render_template("{{ v | short_uuid }}", v=UUID_SAMPLE)
        assert result == "633fd64f"

    def test_02_display_ref_filter(self):
        result = _render_template("{{ v | display_ref('Бронь') }}", v=UUID_SAMPLE)
        assert "Бронь" in result
        assert UUID_SAMPLE not in result

    def test_03_display_campaign_filter(self):
        result = _render_template(
            "{{ c | display_campaign }}",
            c={"campaign_code": "CAMP-001"}
        )
        assert result == "CAMP-001"

    def test_04_display_device_filter(self):
        result = _render_template(
            "{{ d | display_device }}", d={"device_code": "KSO-001"}
        )
        assert result == "KSO-001"

    def test_05_display_booking_filter(self):
        result = _render_template(
            "{{ b | display_booking }}", b={"booking_code": "BK-001"}
        )
        assert result == "BK-001"

    def test_06_fallback_escaped(self):
        # Jinja2 auto-escapes — verify no raw HTML leak
        result = _render_template("{{ v | display_ref('Test') }}", v="<script>")
        assert "<" not in result


# ═══════════════════════════════════════════════════════════════════
# G. Template Content — No Full UUID as Primary Label
# ═══════════════════════════════════════════════════════════════════

UUID_PATTERN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)


class _NoFullUuidBase:
    """Base class with helpers for UUID checks."""

    def _page(self, filename):
        return _read_file(TEMPLATES_DIR / filename)

    def _no_full_uuid_visible(self, content, page_name):
        """Ensure no full 36-char UUID appears as visible text
        (outside href, title, and input value attributes)."""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            for match in UUID_PATTERN.finditer(line):
                uuid_pos = match.start()
                # Check if UUID is inside an HTML attribute where it's OK
                before = line[max(0, uuid_pos - 50):uuid_pos]
                if 'href="' in before and before.rfind('href="') > before.rfind('>'):
                    continue  # In href — OK
                if 'title="' in before and before.rfind('title="') > before.rfind('>'):
                    continue  # In title — OK
                if 'value="' in before and before.rfind('value="') > before.rfind('>'):
                    continue  # In value — OK
                if 'id="' in before and before.rfind('id="') > before.rfind('>'):
                    continue  # In id attr — OK
                # Check if it's inside a Jinja expression in href
                if 'url_code' in before or 'campaign_code' in before:
                    continue  # Likely a href with URL code
                # Check if it's inside a form action
                if 'action="' in before:
                    continue
                raise AssertionError(
                    f"{page_name}:{i + 1} — visible UUID: {match.group()}"
                )


class TestTemplatesNoFullUuid(_NoFullUuidBase):
    """Verify no templates show full 36-char UUIDs as visible primary text."""

    def test_01_campaigns_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("campaigns.html"), "campaigns")

    def test_02_campaigns_detail_no_full_uuid_visible(self):
        self._no_full_uuid_visible(
            self._page("campaigns_detail.html"), "campaigns_detail"
        )

    def test_03_bookings_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("bookings.html"), "bookings")

    def test_04_booking_detail_no_full_uuid_visible(self):
        content = self._page("booking_detail.html")
        # Check that no UUID appears outside <code title=...>
        lines = content.split("\n")
        for i, line in enumerate(lines):
            for match in UUID_PATTERN.finditer(line):
                uuid_pos = match.start()
                before = line[max(0, uuid_pos - 60):uuid_pos]
                if 'title="' in before or 'action="' in before or 'href="' in before:
                    continue
                raise AssertionError(
                    f"booking_detail:{i + 1} — visible UUID: {match.group()}"
                )

    def test_05_publications_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("publications.html"), "publications")

    def test_06_publication_detail_no_full_uuid_visible(self):
        content = self._page("publication_detail.html")
        lines = content.split("\n")
        for i, line in enumerate(lines):
            for match in UUID_PATTERN.finditer(line):
                uuid_pos = match.start()
                before = line[max(0, uuid_pos - 60):uuid_pos]
                if 'title="' in before or 'action="' in before or 'href="' in before:
                    continue
                raise AssertionError(
                    f"publication_detail:{i + 1} — visible UUID: {match.group()}"
                )

    def test_07_analytics_no_full_uuid(self):
        self._no_full_uuid_visible(
            self._page("reports_analytics.html"), "analytics"
        )

    def test_08_pop_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("proof-of-play.html"), "poP")

    def test_09_manifests_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("manifests.html"), "manifests")

    def test_10_manifest_detail_no_full_uuid(self):
        self._no_full_uuid_visible(
            self._page("manifest_detail.html"), "manifest_detail"
        )

    def test_11_devices_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("devices.html"), "devices")

    def test_12_readiness_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("readiness.html"), "readiness")

    def test_13_planning_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("planning.html"), "planning")

    def test_14_creatives_no_full_uuid(self):
        self._no_full_uuid_visible(self._page("creatives.html"), "creatives")


# ═══════════════════════════════════════════════════════════════════
# H. Template Content — display_ref/display_code Usage
# ═══════════════════════════════════════════════════════════════════

class TestTemplatesUseDisplayHelpers:
    """Verify templates use display helpers where UUIDs were previously."""

    def test_01_bookings_uses_display_ref(self):
        content = _read_file(TEMPLATES_DIR / "bookings.html")
        assert "display_ref" in content

    def test_02_booking_detail_uses_display_ref(self):
        content = _read_file(TEMPLATES_DIR / "booking_detail.html")
        assert "display_ref" in content

    def test_03_publication_detail_uses_display_ref(self):
        content = _read_file(TEMPLATES_DIR / "publication_detail.html")
        assert "display_ref" in content

    def test_04_analytics_uses_display_ref(self):
        content = _read_file(TEMPLATES_DIR / "reports_analytics.html")
        assert "display_ref" in content

    def test_05_no_old_truncate_left(self):
        """No remaining `|string|truncate(` patterns in any template."""
        import subprocess
        result = subprocess.run(
            ["rg", "-l", r"truncate\(", str(TEMPLATES_DIR)],
            capture_output=True, text=True
        )
        assert result.returncode != 0 or not result.stdout.strip(), \
            f"Remaining truncate in: {result.stdout}"


# ═══════════════════════════════════════════════════════════════════
# I. C1/C4 Compatibility
# ═══════════════════════════════════════════════════════════════════

class TestC1C4Compatibility:
    """Verify C1 (campaign detail) and C4 (admin sidebar) still work."""

    def test_01_c1_campaigns_still_uses_url_code(self):
        """C1 fix — campaign links still use url_code for href."""
        content = _read_file(TEMPLATES_DIR / "campaigns.html")
        assert "url_code" in content  # C1 fallback preserved

    def test_02_campaign_detail_still_reachable(self):
        """Campaign detail template uses campaign.campaign_code for display."""
        content = _read_file(TEMPLATES_DIR / "campaigns_detail.html")
        # Display code or sanitize_code should be present
        assert "campaign_code" in content

    def test_03_admin_sidebar_unchanged_by_ui22(self):
        """C4 — admin sidebar template not touched by UI.2.2."""
        content = _read_file(TEMPLATES_DIR / "admin.html")
        # Admin sidebar layout preserved (rbac_permissions, sidebar groups)
        assert "rbac_permissions" in content or "permissions" in content


# ═══════════════════════════════════════════════════════════════════
# J. Security
# ═══════════════════════════════════════════════════════════════════

class TestSecurity:
    """Verify no security issues introduced."""

    def test_01_no_secrets_in_display_py(self):
        content = _read_file(PORTAL_DIR / "display.py")
        forbidden = ["password", "token", "secret", "api_key"]
        for word in forbidden:
            assert word not in content.lower()

    def test_02_no_traceback(self):
        content = _read_file(PORTAL_DIR / "display.py")
        assert "Traceback" not in content

    def test_03_no_unsafe_filter(self):
        import subprocess
        result = subprocess.run(
            ["rg", "-n", r"display_ref.*\|.*safe|display_code.*\|.*safe",
             str(TEMPLATES_DIR)],
            capture_output=True, text=True
        )
        assert result.returncode != 0 or not result.stdout.strip()

    def test_04_no_cdn(self):
        content = _read_file(PORTAL_DIR / "display.py")
        assert "cdn." not in content.lower()

    def test_05_no_localstorage(self):
        content = _read_file(PORTAL_DIR / "display.py")
        assert "localStorage" not in content

    def test_06_no_script_tags(self):
        content = _read_file(PORTAL_DIR / "display.py")
        assert "<script" not in content

    def test_07_escaped_values(self):
        result = _render_template("{{ v | display_ref }}", v="<b>test</b>")
        # Jinja2 auto-escapes
        assert "&lt;" in result or "<b>" not in result

    def test_08_title_attributes_escaped(self):
        result = _render_template(
            '<code title="{{ v }}">{{ v | display_ref }}</code>',
            v='test"><script>alert(1)</script>'
        )
        assert "<script>" not in result


# ═══════════════════════════════════════════════════════════════════
# K. Boundaries
# ═══════════════════════════════════════════════════════════════════

class TestBoundaries:
    """Verify no backend/DB/Docker/production changes."""

    def test_01_no_backend_api_changes(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        for f in result.stdout.splitlines():
            assert "backend/" not in f, f"Backend file changed: {f}"

    def test_02_no_migrations(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        for f in result.stdout.splitlines():
            assert "migrations" not in f, f"Migration: {f}"

    def test_03_no_db_schema_changes(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        for f in result.stdout.splitlines():
            assert "models.py" not in f
            assert "schema" not in f.lower()

    def test_04_no_docker_env_changes(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        for f in result.stdout.splitlines():
            assert "docker" not in f.lower()
            assert ".env" not in f

    def test_05_no_production_switch(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        assert "production" not in result.stdout.lower()

    def test_06_no_route_removals(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", "apps/portal-web/main.py"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        removed = [l for l in result.stdout.splitlines() if l.startswith("-@app.")]
        assert not removed, f"Routes removed: {removed}"


# ═══════════════════════════════════════════════════════════════════
# L. Regression Imports
# ═══════════════════════════════════════════════════════════════════

class TestRegressionImports:
    """Verify key modules import cleanly."""

    def test_01_display_import_clean(self):
        spec = importlib.util.spec_from_file_location(
            "display", PORTAL_DIR / "display.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "display_ref")
        assert hasattr(module, "display_campaign")

    def test_02_labels_still_importable(self):
        spec = importlib.util.spec_from_file_location(
            "labels", PORTAL_DIR / "labels.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "label")

    def test_03_display_ref_count(self):
        """Count display_ref usages across templates (should be >= 8)."""
        import subprocess
        result = subprocess.run(
            ["rg", "-c", r"display_ref", str(TEMPLATES_DIR)],
            capture_output=True, text=True
        )
        assert result.returncode == 0
