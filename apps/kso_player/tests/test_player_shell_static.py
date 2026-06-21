"""Static analysis tests for KSO Player HTML Shell.

Verifies shell files exist, are fully local, no external URLs,
no forbidden substrings, CSP is strict, layout is 1440×1080.
Pure static checks — NO Chromium, NO browser, NO HTTP.
"""

import os
import re
from pathlib import Path
from unittest import TestCase

# ── Paths ────────────────────────────────────────────────────────────

SHELL_DIR = Path(__file__).resolve().parent.parent / "player_shell"
INDEX_HTML = SHELL_DIR / "index.html"
STYLES_CSS = SHELL_DIR / "styles.css"
PLAYER_JS = SHELL_DIR / "player.js"
BOOTSTRAP_JS = SHELL_DIR / "bootstrap.js"
BOOTSTRAP_SNAPSHOT_JS = SHELL_DIR / "bootstrap_snapshot.js"

# ── Helpers ──────────────────────────────────────────────────────────


def _strip_js_comments(code: str) -> str:
    """Remove JS comments so static checks don't flag documented concepts."""
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    code = re.sub(r"//.*", "", code)
    return code


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

    def test_bootstrap_js_exists(self):
        self.assertTrue(BOOTSTRAP_JS.exists(), f"{BOOTSTRAP_JS} missing")
        self.assertGreater(BOOTSTRAP_JS.stat().st_size, 50)

    def test_bootstrap_snapshot_js_exists(self):
        self.assertTrue(BOOTSTRAP_SNAPSHOT_JS.exists(),
            f"{BOOTSTRAP_SNAPSHOT_JS} missing")
        self.assertGreater(BOOTSTRAP_SNAPSHOT_JS.stat().st_size, 50)

    def test_only_expected_files(self):
        files = sorted(f.name for f in SHELL_DIR.iterdir() if f.is_file())
        self.assertEqual(files, ["bootstrap.js", "bootstrap_snapshot.js",
            "index.html", "player.js", "styles.css"])


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
        # player.js, bootstrap_snapshot.js, bootstrap.js loaded locally
        self.assertIn('src="player.js"', self.html)
        self.assertIn('src="bootstrap_snapshot.js"', self.html)
        self.assertIn('src="bootstrap.js"', self.html)
        self.assertNotIn('src="http', self.html)

    def test_script_order(self):
        # Order: player.js → bootstrap_snapshot.js → bootstrap.js
        pidx = self.html.index('src="player.js"')
        sidx = self.html.index('src="bootstrap_snapshot.js"')
        bidx = self.html.index('src="bootstrap.js"')
        self.assertLess(pidx, sidx, "player.js must be before bootstrap_snapshot.js")
        self.assertLess(sidx, bidx, "bootstrap_snapshot.js must be before bootstrap.js")

    def test_bootstrap_after_player(self):
        # bootstrap.js must be loaded AFTER player.js
        pidx = self.html.index('src="player.js"')
        bidx = self.html.index('src="bootstrap.js"')
        self.assertGreater(bidx, pidx, "bootstrap.js must be after player.js")

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

    def test_media_slot_img_video_styles_exist(self):
        self.assertIn(".kso-media-slot img", self.css)
        self.assertIn(".kso-media-slot video", self.css)

    def test_object_fit_contain(self):
        self.assertIn("object-fit: contain", self.css)

    def test_media_slot_background_black(self):
        self.assertIn("background:#000", self.css.replace(" ", ""))


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
        code = _strip_js_comments(self.js)
        self.assertNotIn("WebSocket", code)
        self.assertNotIn("ws://", code)
        self.assertNotIn("wss://", code)

    def test_no_external_urls(self):
        code = _strip_js_comments(self.js)
        self.assertNotIn("http://", code)
        self.assertNotIn("https://", code)
        self.assertNotIn("//cdn", code)

    def test_no_eval(self):
        code = _strip_js_comments(self.js)
        self.assertNotIn("eval(", code)

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

    def test_apply_snapshot_allowed_keys_include_media_ref(self):
        # allowedKeys now includes mediaRef
        self.assertIn("mediaType: true", self.js)
        self.assertIn("durationBucket: true", self.js)
        self.assertIn("mediaRef: true", self.js)

    def test_apply_snapshot_media_ref_whitelist_pattern(self):
        # applySnapshot must have regex whitelist for mediaRef
        self.assertIn("/^[a-z0-9", self.js)

    def test_apply_snapshot_media_ref_unsafe_rejected(self):
        # unsafeInRef array must exist in applySnapshot
        self.assertIn("unsafeInRef", self.js)

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

    # ── Safe media renderer ───────────────────────────────────────

    def test_document_create_element_used(self):
        """Shell creates elements via document.createElement, not innerHTML."""
        self.assertIn("document.createElement", self.js)

    def test_replace_children_used(self):
        """replaceChildren() used for clearing — NOT innerHTML."""
        self.assertIn("replaceChildren", self.js)

    def test_no_outer_html(self):
        self.assertNotIn("outerHTML", self.js)

    def test_no_insert_adjacent_html(self):
        self.assertNotIn("insertAdjacentHTML", self.js)

    def test_set_attribute_used(self):
        """Attributes set via setAttribute(), not direct assignment."""
        self.assertIn("setAttribute", self.js)

    def test_img_created_for_image(self):
        """image mediaType → document.createElement('img')."""
        self.assertIn('createElement("img")', self.js)

    def test_video_created_for_video(self):
        """video mediaType → document.createElement('video')."""
        self.assertIn('createElement("video")', self.js)

    def test_video_has_muted_autoplay_loop_playsinline(self):
        """video gets muted, autoplay, loop, playsinline attributes."""
        self.assertIn('"muted"', self.js)
        self.assertIn('"autoplay"', self.js)
        self.assertIn('"loop"', self.js)
        self.assertIn('"playsinline"', self.js)

    def test_src_set_from_media_ref_only(self):
        """src is only set from already-validated mediaRef."""
        self.assertIn('"src"', self.js)

    def test_media_ref_revalidated_in_set_render_plan(self):
        """setRenderPlan re-validates mediaRef before creating element."""
        # _isMediaRefSafe must be called in setRenderPlan
        self.assertIn("_isMediaRefSafe", self.js)

    def test_clear_media_slot_in_clear(self):
        """clear() must call _clearMediaSlot."""
        idx = self.js.index("function clear()")
        window = self.js[idx:idx + 300]
        self.assertIn("_clearMediaSlot", window)

    def test_no_forbidden_near_render(self):
        """No forbidden substrings near setRenderPlan."""
        idx = self.js.index("function setRenderPlan")
        window = self.js[idx:idx + 2000]
        lower = window.lower()
        for fb in ("innerhtml", "outerhtml", "insertadjacenthtml",
                    "fetch", "xmlhttprequest", "websocket",
                    "eval(", "new function",
                    "http://", "https://", "file://",
                    "backend", "token", "secret",
                    "campaign_id", "creative_id", "sha256"):
            self.assertNotIn(fb, lower,
                f"forbidden '{fb}' found near setRenderPlan")


# ══════════════════════════════════════════════════════════════════════
# Tests: bootstrap.js
# ══════════════════════════════════════════════════════════════════════

class TestBootstrapJS(TestCase):
    """bootstrap.js content and safety."""

    @classmethod
    def setUpClass(cls):
        cls.js = BOOTSTRAP_JS.read_text()

    def test_uses_ksoplayershell(self):
        self.assertIn("KsoPlayerShell", self.js)

    def test_uses_apply_snapshot(self):
        self.assertIn("applySnapshot", self.js)

    def test_uses_set_hold(self):
        self.assertIn("setHold", self.js)

    def test_checks_bootstrap_snapshot(self):
        self.assertIn("KSO_PLAYER_BOOTSTRAP_SNAPSHOT", self.js)

    def test_no_fetch(self):
        self.assertNotIn("fetch(", self.js)

    def test_no_xml_http_request(self):
        self.assertNotIn("XMLHttpRequest", self.js)

    def test_no_web_socket(self):
        code = _strip_js_comments(self.js)
        self.assertNotIn("WebSocket", code)
        self.assertNotIn("ws://", code)
        self.assertNotIn("wss://", code)

    def test_no_eval(self):
        self.assertNotIn("eval(", self.js)

    def test_no_new_function(self):
        self.assertNotIn("new Function", self.js)

    def test_no_inner_html(self):
        self.assertNotIn("innerHTML", self.js)
        self.assertNotIn("outerHTML", self.js)
        self.assertNotIn("insertAdjacentHTML", self.js)

    def test_no_external_urls(self):
        code = _strip_js_comments(self.js)
        self.assertNotIn("http://", code)
        self.assertNotIn("https://", code)
        self.assertNotIn("file://", self.js)

    def test_no_forbidden_substrings(self):
        lower = self.js.lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, lower,
                f"forbidden '{fb}' found in bootstrap.js")


# ══════════════════════════════════════════════════════════════════════
# Tests: bootstrap_snapshot.js
# ══════════════════════════════════════════════════════════════════════

class TestBootstrapSnapshotJS(TestCase):
    """bootstrap_snapshot.js content and safety."""

    @classmethod
    def setUpClass(cls):
        cls.js = BOOTSTRAP_SNAPSHOT_JS.read_text()

    def test_sets_bootstrap_snapshot(self):
        self.assertIn("KSO_PLAYER_BOOTSTRAP_SNAPSHOT", self.js)

    def test_default_snapshot_is_hold(self):
        self.assertIn('"hold"', self.js)
        self.assertIn('"setHold"', self.js)

    def test_default_snapshot_no_media_ref(self):
        self.assertNotIn("mediaRef", self.js)
        self.assertNotIn("media/current/slot-", self.js)

    def test_schema_version_is_1(self):
        self.assertIn("schemaVersion", self.js)

    def test_strict_mode(self):
        self.assertIn('"use strict"', self.js)

    def test_no_fetch(self):
        self.assertNotIn("fetch(", self.js)

    def test_no_xml_http_request(self):
        self.assertNotIn("XMLHttpRequest", self.js)

    def test_no_web_socket(self):
        code = _strip_js_comments(self.js)
        self.assertNotIn("WebSocket", code)
        self.assertNotIn("ws://", code)
        self.assertNotIn("wss://", code)

    def test_no_eval(self):
        self.assertNotIn("eval(", self.js)

    def test_no_new_function(self):
        self.assertNotIn("new Function", self.js)

    def test_no_inner_html(self):
        self.assertNotIn("innerHTML", self.js)
        self.assertNotIn("outerHTML", self.js)
        self.assertNotIn("insertAdjacentHTML", self.js)

    def test_no_external_urls(self):
        code = _strip_js_comments(self.js)
        self.assertNotIn("http://", code)
        self.assertNotIn("https://", code)
        self.assertNotIn("file://", self.js)

    def test_no_paths(self):
        self.assertNotIn("/opt", self.js)
        self.assertNotIn("/var", self.js)

    def test_no_ids(self):
        for fb in ("manifest_item_id", "campaign_id", "creative_id",
                    "schedule_item_id"):
            self.assertNotIn(fb, self.js)

    def test_no_hash(self):
        self.assertNotIn("sha256", self.js)

    def test_no_forbidden_substrings(self):
        lower = self.js.lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, lower,
                f"forbidden '{fb}' found in bootstrap_snapshot.js")


if __name__ == "__main__":
    import unittest
    unittest.main()
