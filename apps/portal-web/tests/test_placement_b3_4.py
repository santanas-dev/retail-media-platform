"""
B.3.4 — Portal Placement Read-Only Tests.

Tests:
  - campaign_detail template has placements block
  - campaign_detail empty state for placements
  - placement_detail template exists with Russian labels
  - placement_detail shows status labels
  - no CRUD buttons/forms in placement_detail
  - no JS/CDN/localStorage in placement templates
  - placement_detail template doesn't show raw UUID
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


class TestCampaignDetailPlacements(unittest.TestCase):
    """Campaign detail shows placements block."""

    def test_placements_section_exists(self):
        content = _read("campaigns_detail.html")
        self.assertIn("Размещения", content)
        self.assertIn("placements", content)

    def test_placements_empty_state_has_russian_text(self):
        content = _read("campaigns_detail.html")
        self.assertIn("Размещения пока не созданы", content)

    def test_placements_has_status_badges(self):
        content = _read("campaigns_detail.html")
        self.assertIn("status-badge-{{ p.status }}", content)

    def test_placements_has_table_headers(self):
        content = _read("campaigns_detail.html")
        self.assertIn("<th>Код</th>", content)
        self.assertIn("<th>Название</th>", content)
        self.assertIn("<th>Статус</th>", content)
        self.assertIn("<th>Приоритет</th>", content)
        self.assertIn("<th>Период</th>", content)

    def test_placements_links_to_detail(self):
        content = _read("campaigns_detail.html")
        self.assertIn('href="/placements/{{ p.id }}"', content)

    def test_placements_no_raw_english(self):
        content = _read("campaigns_detail.html")
        # Russian labels only
        self.assertNotIn(">Placements<", content)
        # No raw English status in visible text
        for raw in ["draft", "active", "paused", "completed", "cancelled"]:
            visible_re = re.compile(rf">\s*{raw}\s*<")
            self.assertFalse(
                visible_re.search(content),
                f"Raw English status '{raw}' visible in placements block",
            )


class TestPlacementDetailPage(unittest.TestCase):
    """Placement detail page — read-only."""

    def test_template_exists(self):
        content = _read("placement_detail.html")
        self.assertIn("Размещение не найдено", content)
        self.assertIn("Код размещения", content)

    def test_russian_labels(self):
        content = _read("placement_detail.html")
        for label in [
            "Код размещения", "Статус", "Приоритет",
            "Дата начала", "Дата окончания",
            "Цели размещения", "Тип цели",
        ]:
            self.assertIn(label, content, f"Missing Russian label: {label}")

    def test_status_labels_from_server(self):
        """Status labels use placement.status_label from handler."""
        content = _read("placement_detail.html")
        self.assertIn("placement.status_label", content)

    def test_target_types_russian(self):
        content = _read("placement_detail.html")
        self.assertIn("Магазин", content)
        self.assertIn("Экран", content)
        self.assertIn("Носитель", content)

    def test_empty_targets_has_russian_text(self):
        content = _read("placement_detail.html")
        self.assertIn("Цели не заданы", content)

    def test_no_crud_buttons(self):
        """No create/update/delete buttons in placement detail."""
        content = _read("placement_detail.html")
        self.assertNotIn('method="post"', content)
        self.assertNotIn('type="submit"', content)
        self.assertNotIn("Создать", content)
        self.assertNotIn("Редактировать", content)
        self.assertNotIn("Удалить", content)

    def test_no_crud_forms(self):
        content = _read("placement_detail.html")
        self.assertNotIn("<form", content)

    def test_read_only_note(self):
        content = _read("placement_detail.html")
        self.assertIn("режиме чтения", content.lower())

    def test_no_raw_uuid_exposed(self):
        """Placement detail hides UUIDs in user-facing display."""
        content = _read("placement_detail.html")
        # UUID pattern: 8-4-4-4-12 hex digits
        uuid_re = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        )
        # Should not show raw UUIDs in visible text (not in template variables)
        # Template variables like {{ placement.id }} are fine — they're server-rendered
        visible_text = re.sub(r"\{\{.*?\}\}", "", content)
        self.assertFalse(
            uuid_re.search(visible_text),
            "Raw UUID leaked in visible placement detail text",
        )


class TestPlacementTemplatesSecurity(unittest.TestCase):
    """No JS/CDN/localStorage in placement templates."""

    def test_no_js_in_placement_detail(self):
        content = _read("placement_detail.html")
        self.assertNotIn("<script", content)
        self.assertNotIn("onclick", content)
        self.assertNotIn("onload", content)
        self.assertNotIn("javascript:", content)

    def test_no_cdn_in_placement_detail(self):
        content = _read("placement_detail.html")
        self.assertNotIn("cdn.", content)
        self.assertNotIn("unpkg", content)
        self.assertNotIn("jsdelivr", content)

    def test_no_localstorage_in_placement_detail(self):
        content = _read("placement_detail.html")
        self.assertNotIn("localStorage", content)
        self.assertNotIn("sessionStorage", content)

    def test_no_js_in_campaign_detail_placements_block(self):
        content = _read("campaigns_detail.html")
        self.assertNotIn("<script", content)
        self.assertNotIn("onclick", content)


class TestPlacementDetailNotFound(unittest.TestCase):
    """Placement detail handles missing placement gracefully."""

    def test_not_found_message_russian(self):
        content = _read("placement_detail.html")
        self.assertIn("Размещение не найдено", content)

    def test_not_found_back_link(self):
        content = _read("placement_detail.html")
        self.assertIn("Назад к кампаниям", content)
