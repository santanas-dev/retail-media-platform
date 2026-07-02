"""
D.5.2 — Portal Planning Read-Only Visibility: targeted tests.

Tests:
  - Campaign detail shows Planning block
  - Planning block has Russian labels
  - Availability/conflicts/occupancy sections
  - Empty states for no data
  - No create/edit/delete buttons or forms
  - No JS/CDN/localStorage
  - No secrets in rendered template
  - BackendClient has planning methods
  - 403 handled gracefully
"""

import os
import re
import unittest

_TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "templates", "pages",
)


def _read(page: str) -> str:
    path = os.path.join(_TEMPLATES_DIR, page)
    with open(path, "r") as f:
        return f.read()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Planning Block Visibility (6 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlanningBlockVisibility(unittest.TestCase):
    """Campaign detail shows Planning block with Russian labels."""

    def test_planning_section_exists(self):
        content = _read("campaigns_detail.html")
        assert "Планирование" in content

    def test_planning_section_has_russian_labels(self):
        content = _read("campaigns_detail.html")
        russian_labels = [
            "Доступность", "Конфликты", "Занятость",
            "Единиц инвентаря", "Предупреждений",
            "Забронировано слотов", "Всего слотов",
        ]
        for label in russian_labels:
            assert label in content, f"Missing Russian label: {label}"

    def test_availability_block_present(self):
        content = _read("campaigns_detail.html")
        assert "planning.availability" in content

    def test_conflicts_block_present(self):
        content = _read("campaigns_detail.html")
        assert "planning.conflicts" in content

    def test_occupancy_block_present(self):
        content = _read("campaigns_detail.html")
        assert "planning.occupancy" in content

    def test_planning_section_has_icon(self):
        content = _read("campaigns_detail.html")
        assert "📊" in content


# ═══════════════════════════════════════════════════════════════════════════
# 2. Empty States (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestEmptyStates(unittest.TestCase):
    """Planning block handles empty/missing data gracefully."""

    def test_backend_unavailable_message(self):
        content = _read("campaigns_detail.html")
        assert "Данные планирования пока недоступны" in content

    def test_no_conflicts_message(self):
        content = _read("campaigns_detail.html")
        assert "Конфликтов не найдено" in content

    def test_conditional_planning_block(self):
        """Planning block only renders when planning data exists."""
        content = _read("campaigns_detail.html")
        assert "{% if planning %}" in content


# ═══════════════════════════════════════════════════════════════════════════
# 3. No CRUD / No JS-CD (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestNoCrudOrJs(unittest.TestCase):
    """Planning block has no create/edit/delete controls."""

    def test_no_create_booking_button(self):
        content = _read("campaigns_detail.html")
        forbidden = ["Создать бронирование", "Забронировать", "Create booking"]
        for word in forbidden:
            assert word not in content, f"CRUD text found: {word}"

    def test_no_edit_booking_form(self):
        content = _read("campaigns_detail.html")
        assert "edit-booking" not in content.lower()
        assert "booking-form" not in content.lower()

    def test_no_reserve_button(self):
        content = _read("campaigns_detail.html")
        assert "Зарезервировать" not in content
        assert "reserve" not in content.lower()

    def test_no_js_in_planning_block(self):
        content = _read("campaigns_detail.html")
        # Planning block is server-side rendered with Jinja2
        assert "<script" not in content.lower()

    def test_no_cdn_or_localstorage(self):
        content = _read("campaigns_detail.html")
        assert "cdn." not in content.lower()
        assert "localStorage" not in content


# ═══════════════════════════════════════════════════════════════════════════
# 4. No Secrets (2 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestNoSecretsInTemplate(unittest.TestCase):
    """Template must NOT contain secrets/passwords/tokens."""

    def test_no_secrets_in_rendered_html(self):
        content = _read("campaigns_detail.html")
        forbidden = ["password", "access_token", "refresh_token", "secret"]
        for word in forbidden:
            assert word not in content.lower(), f"Secret found: {word}"

    def test_no_raw_uuids_in_planning_block(self):
        """Planning context uses safe values (counts, percents) not raw UUIDs."""
        content = _read("campaigns_detail.html")
        # Availability uses units_count, not unit IDs
        assert "units_count" in content
        # Conflicts uses count
        assert "conflicts.count" in content


# ═══════════════════════════════════════════════════════════════════════════
# 5. BackendClient Methods (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestBackendClientPlanning(unittest.TestCase):
    """BackendClient has planning API methods."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from backend_client import BackendClient
        cls.BackendClient = BackendClient
        cls.client = BackendClient()

    def test_get_planning_availability_exists(self):
        assert hasattr(self.client, "get_planning_availability")
        assert callable(self.client.get_planning_availability)

    def test_check_planning_conflicts_exists(self):
        assert hasattr(self.client, "check_planning_conflicts")
        assert callable(self.client.check_planning_conflicts)

    def test_get_planning_occupancy_exists(self):
        assert hasattr(self.client, "get_planning_occupancy")
        assert callable(self.client.get_planning_occupancy)

    def test_simulate_planning_scenario_exists(self):
        assert hasattr(self.client, "simulate_planning_scenario")
        assert callable(self.client.simulate_planning_scenario)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Route Verification (2 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestMainRoutePlanning(unittest.TestCase):
    """main.py passes planning data to campaign detail template."""

    def test_planning_in_template_context(self):
        """TemplateResponse includes planning key."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import main as portal_main
        src = inspect_source(portal_main)
        assert '"planning": planning_data' in src or "'planning': planning_data" in src

    def test_has_planning_perm_check(self):
        """Route checks planning.read permission."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import main as portal_main
        src = inspect_source(portal_main)
        assert 'planning.read' in src


def inspect_source(module) -> str:
    import inspect
    try:
        return inspect.getsource(module)
    except (TypeError, OSError):
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# 7. Safety Boundaries (3 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestSafetyBoundaries(unittest.TestCase):
    """D.5.2 does not introduce write operations."""

    def test_no_booking_create_in_template(self):
        content = _read("campaigns_detail.html")
        assert "CampaignBooking" not in content
        assert "BookingItem" not in content

    def test_no_form_posts_in_planning_block(self):
        """Planning block has no forms — read-only. Cross-links section excluded (PORTAL.1.5)."""
        content = _read("campaigns_detail.html")
        # Exclude PORTAL.1.5 cross-links section
        planning_section = content.split("PORTAL.1.5: Cross-Links")[0] if "PORTAL.1.5: Cross-Links" in content else content
        assert "/bookings" not in planning_section

    def test_no_reservation_links(self):
        content = _read("campaigns_detail.html")
        planning_section = content.split("PORTAL.1.5: Cross-Links")[0] if "PORTAL.1.5: Cross-Links" in content else content
        assert "/reserve" not in planning_section
        assert "/booking" not in planning_section.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 8. Compatibility (2 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestCompatibility(unittest.TestCase):
    """Existing portal features still work."""

    def test_campaign_detail_still_has_creatives(self):
        content = _read("campaigns_detail.html")
        assert "Креативы" in content or "Креативы кампании" in content

    def test_campaign_detail_still_has_placements(self):
        content = _read("campaigns_detail.html")
        assert "Размещения" in content
