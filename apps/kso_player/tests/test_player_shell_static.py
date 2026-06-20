"""Static analysis tests for KSO Player HTML Shell.

Verifies shell files exist, are fully local, no external URLs,
no forbidden substrings, CSP is strict, layout is 1440×1080.
Pure static checks — NO Chromium, NO browser, NO HTTP.
"""

import os
from pathlib import Path
from unittest import TestCase

# ── Paths ────────────────────────────────────────────────────────────

SHELL_DIR = Path(__file__).resolve().parent.parent / "player_shell"
INDEX_HTML = SHELL_DIR / "index.html"
STYLES_CSS = SHELL_DIR / "styles.css"
PLAYER_JS = SHELL_DIR / "player.js"

# ── Forbidden substrings ────────────────────────────────────────────

FORBIDDEN = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
    "backend_base_url", "127.0.0.1", "device_code",
    "filename", "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes", "stacktrace",
    "boot_id", "pid",
    "Windows Service", "MSI", "ProgramData", "Windows installer",
})


# ══════════════════════════════════════════════════════════════════════
# Tests: file existence
# ══════════════════════════════════════════════════════════════════════

class TestFileExistence(TestCase):
    """All shell files exist and are non-empty."""

    def test_index_html_exists(self):
        self.assertTrue(INDEX_HTML.exists(), f"{INDEX_HTML} missing")
        self.assertGreater(INDEX_HTML.stat().st_size, 100)

    def test_styles_css_exists(self):
        self.assertTrue(STYLES_CSS.exists(), f"{STYLES_CSS} missing")
        self.assertGreater(STYLES_CSS.stat().st_size, 100)

    def test_player_js_exists(self):
        self.assertTrue(PLAYER_JS.exists(), f"{PLAYER_JS} missing")
        self.assertGreater(PLAYER_JS.stat().st_size, 100)

    def test_only_expected_files(self):
        files = sorted(f.name for f in SHELL_DIR.iterdir() if f.is_file())
        self.assertEqual(files, ["index.html", "player.js", "styles.css"])


# ══════════════════════════════════════════════════════════════════════
# Tests: HTML
# ══════════════════════════════════════════════════════════════════════

class TestHTML(TestCase):
    """index.html structure and safety."""

    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text()

    def test_has_doctype(self):
        self.assertIn("<!DOCTYPE html>", self.html)

    def test_csp_meta_present(self):
        self.assertIn("Content-Security-Policy", self.html)
        self.assertIn("default-src 'self'", self.html)
        self.assertIn("connect-src 'none'", self.html)
        self.assertIn("form-action 'none'", self.html)

    def test_no_external_scripts(self):
        # Only local scripts — no protocol in script src
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
        self.assertNotIn("//cdn", self.html)

    def test_no_external_styles(self):
        self.assertNotIn("<link", self.html.replace(
            '<link rel="stylesheet" href="styles.css">', ""))

    def test_only_local_scripts_referenced(self):
        # Only player.js is loaded
        self.assertIn('src="player.js"', self.html)
        self.assertNotIn('src="http', self.html)

    def test_no_iframe(self):
        self.assertNotIn("<iframe", self.html)

    def test_no_form(self):
        self.assertNotIn("<form", self.html)

    def test_hold_div_exists(self):
        self.assertIn('id="kso-hold"', self.html)

    def test_render_div_exists(self):
        self.assertIn('id="kso-render"', self.html)

    def test_media_slot_exists(self):
        self.assertIn('id="kso-media-slot"', self.html)

    def test_no_forbidden_substrings(self):
        lower = self.html.lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, lower,
                f"forbidden '{fb}' found in index.html")

    def test_no_backend_url(self):
        lower = self.html.lower()
        self.assertNotIn("backend", lower)
        self.assertNotIn("api/", lower)

    def test_no_customer_payment_card(self):
        lower = self.html.lower()
        for fb in ("payment", "card", "customer_id", "receipt_number"):
            self.assertNotIn(fb, lower)


# ══════════════════════════════════════════════════════════════════════
# Tests: CSS
# ══════════════════════════════════════════════════════════════════════

class TestCSS(TestCase):
    """styles.css safety and layout."""

    @classmethod
    def setUpClass(cls):
        cls.css = STYLES_CSS.read_text()

    def test_width_is_1440(self):
        self.assertIn("1440px", self.css)

    def test_height_is_1080(self):
        self.assertIn("1080px", self.css)

    def test_no_1920_as_main_width(self):
        # 1920 should not appear as the main container width
        # (it's the full screen, not the shell's responsibility)
        self.assertNotIn("width: 1920px", self.css)
        self.assertNotIn("width:1920px", self.css)

    def test_no_external_urls(self):
        self.assertNotIn("http://", self.css)
        self.assertNotIn("https://", self.css)
        self.assertNotIn("@import url", self.css)

    def test_no_forbidden_substrings(self):
        lower = self.css.lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, lower,
                f"forbidden '{fb}' found in styles.css")


# ══════════════════════════════════════════════════════════════════════
# Tests: JS
# ══════════════════════════════════════════════════════════════════════

class TestJS(TestCase):
    """player.js API and safety."""

    @classmethod
    def setUpClass(cls):
        cls.js = PLAYER_JS.read_text()

    def test_ksoplayershell_exported(self):
        self.assertIn("window.KsoPlayerShell", self.js)

    def test_set_hold_exists(self):
        self.assertIn("setHold", self.js)
        self.assertIn("function setHold", self.js)

    def test_set_render_plan_exists(self):
        self.assertIn("setRenderPlan", self.js)
        self.assertIn("function setRenderPlan", self.js)

    def test_clear_exists(self):
        self.assertIn("clear", self.js)
        self.assertIn("function clear", self.js)

    def test_set_render_plan_validates_media_type(self):
        # Must check for image/video
        self.assertIn('mediaType', self.js)

    def test_no_fetch(self):
        self.assertNotIn("fetch(", self.js)

    def test_no_xml_http_request(self):
        self.assertNotIn("XMLHttpRequest", self.js)

    def test_no_web_socket(self):
        self.assertNotIn("WebSocket", self.js)
        self.assertNotIn("ws://", self.js)
        self.assertNotIn("wss://", self.js)

    def test_no_external_urls(self):
        self.assertNotIn("http://", self.js)
        self.assertNotIn("https://", self.js)
        self.assertNotIn("//cdn", self.js)

    def test_no_eval(self):
        self.assertNotIn("eval(", self.js)

    def test_no_forbidden_substrings(self):
        lower = self.js.lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, lower,
                f"forbidden '{fb}' found in player.js")

    def test_media_type_image_video_only(self):
        # setRenderPlan should check for image/video
        lower = self.js.lower()
        self.assertIn("image", lower)
        self.assertIn("video", lower)

    def test_no_document_write(self):
        self.assertNotIn("document.write", self.js)

    def test_no_inner_html(self):
        # Should use textContent, not innerHTML
        self.assertNotIn("innerHTML", self.js)

    def test_no_new_function(self):
        self.assertNotIn("new Function", self.js)
        self.assertNotIn("new Function(", self.js.replace(" ", ""))

    # ── applySnapshot ─────────────────────────────────────────────

    def test_apply_snapshot_exists(self):
        self.assertIn("applySnapshot", self.js)
        self.assertIn("function applySnapshot", self.js)

    def test_apply_snapshot_exported(self):
        self.assertIn("applySnapshot: applySnapshot", self.js)

    def test_apply_snapshot_validates_schema_version(self):
        self.assertIn("schemaVersion", self.js)

    def test_apply_snapshot_rejects_extra_keys(self):
        # hasExtraKeys check must exist
        self.assertIn("hasExtraKeys", self.js)

    def test_apply_snapshot_only_mediatype_durationbucket(self):
        # allowedKeys must contain only mediaType and durationBucket
        self.assertIn("mediaType: true", self.js)
        self.assertIn("durationBucket: true", self.js)

    def test_apply_snapshot_no_paths_near_apply(self):
        # No paths/filenames/IDs in applySnapshot code
        # Search a window around applySnapshot for forbidden items
        idx = self.js.index("applySnapshot")
        window = self.js[idx:idx + 2000]
        lower = window.lower()
        for fb in ("filename", "manifest_item_id", "campaign_id",
                    "creative_id", "schedule_item_id", "sha256",
                    "token", "backend", "secret"):
            self.assertNotIn(fb, lower,
                f"forbidden '{fb}' found near applySnapshot")


if __name__ == "__main__":
    import unittest
    unittest.main()
