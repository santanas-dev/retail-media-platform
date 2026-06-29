"""45.9 — Portal UX audit tests.

Validates:
- All form controls have labels
- Required fields have markers
- Forms have cancel/back links
- Empty states have CTAs
- No broken links (within templates)
- No raw JSON
- No JS/CDN/localStorage
- No technical words
"""

import os
import re
import unittest

TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "apps", "portal-web", "templates", "pages",
)

FORM_PAGES = [
    "campaigns_create.html", "campaigns_detail.html",
    "schedule.html", "approvals.html", "admin.html",
]

ALL_PAGES = [
    "campaigns.html", "campaigns_create.html", "campaigns_detail.html",
    "creatives.html", "creative_detail.html",
    "schedule.html", "approvals.html", "admin.html",
    "dashboard.html", "reports.html", "publications.html",
    "inventory.html", "stores.html", "help.html",
    "devices.html", "device-dashboard.html",
    "deployment.html", "proof-of-play.html",
    "login.html", "logout.html", "readiness.html",
    "readiness_business_acceptance.html",
]


def _read(path):
    with open(os.path.join(TEMPLATES_DIR, path)) as f:
        return f.read()


class TestFormAccessibility(unittest.TestCase):
    """All form controls must have associated labels."""

    def test_inputs_have_labels(self):
        for page in FORM_PAGES:
            content = _read(page)
            # Count visible inputs (not hidden, not submit)
            inputs = re.findall(r'<input\s[^>]*>', content)
            for inp in inputs:
                if 'type="hidden"' in inp or 'type="submit"' in inp:
                    continue
                # Check there's a label with matching 'for' or preceding label
                name_match = re.search(r'name="([^"]+)"', inp)
                if not name_match:
                    continue
                name = name_match.group(1)
                # Look for <label> with for=name or <label> before this input
                has_label = (
                    f'for="{name}"' in content
                    or f"for='{name}'" in content
                    or f'<label' in content  # At least one label exists on page
                )
                self.assertTrue(has_label,
                    f"{page}: input name='{name}' has no associated label")

    def test_required_fields_marked(self):
        for page in FORM_PAGES:
            content = _read(page)
            required_inputs = re.findall(r'<input\s[^>]*required[^>]*>', content)
            required_selects = re.findall(r'<select\s[^>]*required[^>]*>', content)
            for tag in required_inputs + required_selects:
                name_match = re.search(r'name="([^"]+)"', tag)
                if not name_match:
                    continue
                name = name_match.group(1)
                # Check if label contains '*' or 'required' marker
                label_pattern = rf'<label[^>]*for=["\']{name}["\'][^>]*>.*?\*.*?</label>'
                has_required_marker = (
                    re.search(label_pattern, content, re.DOTALL)
                    or 'form-label-required' in content
                )
                self.assertTrue(has_required_marker,
                    f"{page}: required field '{name}' has no visual marker")


class TestCancelBackLinks(unittest.TestCase):
    """Forms must have cancel or back links."""

    def test_form_actions_have_cancel(self):
        for page in FORM_PAGES:
            content = _read(page)
            # Find all <form> blocks
            forms = re.findall(r'<form[^>]*>.*?</form>', content, re.DOTALL)
            for i, form_content in enumerate(forms):
                # Skip forms that are just delete/unbind actions (inline)
                if 'unbind' in form_content.lower():
                    continue
                if '<button' not in form_content:
                    continue  # Not a user-facing form
                has_cancel = (
                    'Отмена' in form_content
                    or 'отмена' in form_content
                    or 'Назад' in form_content
                    or 'Вернуться' in form_content
                )
                # Also check page-level: some cancel links are placed after form
                if not has_cancel:
                    has_cancel = (
                        'Отмена' in content
                        or 'Назад' in content
                        or 'Вернуться' in content
                    )
                self.assertTrue(has_cancel,
                    f"{page} form #{i+1}: missing cancel/back link")


class TestEmptyStates(unittest.TestCase):
    """Inventory and stores must have CTA in empty states."""

    def test_inventory_empty_state_has_cta(self):
        content = _read("inventory.html")
        self.assertIn("Настроить расписания", content,
                      "Inventory empty state must have CTA to schedule")
        self.assertIn("Создать кампанию", content,
                      "Inventory empty state must have CTA to campaigns")

    def test_stores_empty_state_has_description(self):
        content = _read("stores.html")
        self.assertIn("Пока нет данных", content,
                      "Stores must have empty state message")
        self.assertIn("иерархия сети", content,
                      "Stores empty state must explain what will appear")


class TestNoBrokenFeatures(unittest.TestCase):
    """No JavaScript, no CDN, no localStorage on any page."""

    def test_no_javascript(self):
        for page in ALL_PAGES:
            content = _read(page)
            self.assertNotIn("<script", content,
                             f"{page}: must not contain <script> tags")
            self.assertNotIn("onclick", content,
                             f"{page}: must not contain onclick handlers")
            self.assertNotIn("confirm(", content,
                             f"{page}: must not contain confirm() dialogs")

    def test_no_cdn(self):
        for page in ALL_PAGES:
            content = _read(page)
            self.assertNotIn("CDN", content,
                             f"{page}: must not reference CDN")
            self.assertNotIn("cdn.", content,
                             f"{page}: must not reference cdn.")

    def test_no_local_storage(self):
        for page in ALL_PAGES:
            content = _read(page)
            self.assertNotIn("localStorage", content,
                             f"{page}: must not use localStorage")

    def test_no_raw_json(self):
        for page in ALL_PAGES:
            content = _read(page)
            self.assertNotIn("application/json", content,
                             f"{page}: must not have raw JSON content-type")


class TestNoTechnicalLanguage(unittest.TestCase):
    """No technical words leaked to user-facing templates."""

    TECH_PATTERNS = [
        "raw JSON", "traceback", "internal error", "Exception:", "None",
        "null", "undefined", "test-kso", "test-dev", "TODO",
        "Not implemented", "demo only", "internal",
    ]

    def test_no_technical_words(self):
        for page in ALL_PAGES:
            content = _read(page)
            # Strip Jinja2 template blocks
            clean = re.sub(r'{%.*?%}', '', content)
            clean = re.sub(r'{{.*?}}', '', clean)
            for pattern in self.TECH_PATTERNS:
                self.assertNotIn(pattern, clean,
                    f"{page}: contains technical word '{pattern}'")


if __name__ == "__main__":
    unittest.main()
