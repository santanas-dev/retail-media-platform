"""KSO Player Shell Live Snapshot Refresh — Security & Static Tests.

Verifies:
  - Shell JavaScript has NO fetch, XHR, WebSocket, EventSource, eval, innerHTML
  - CSP has connect-src 'none', no unsafe-eval, no unsafe-inline
  - Live snapshot refresh API is present (startLiveSnapshotRefresh, stopLiveSnapshotRefresh)
  - Live refresh uses only local <script> tag injection
  - Bootstrap starts live refresh after initial apply

No Chromium launch, no real HTTP, no backend, no PoP.
"""

import os
import re
import unittest


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _read_shell_file(filename: str) -> str:
    """Read a shell source file from player_shell directory."""
    shell_dir = os.path.join(
        os.path.dirname(__file__), "..", "player_shell",
    )
    path = os.path.join(shell_dir, filename)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _strip_comments(js_code: str) -> str:
    """Remove JS comments (// and /* */) for code-only checks."""
    # Remove block comments
    code = re.sub(r"/\*.*?\*/", "", js_code, flags=re.DOTALL)
    # Remove line comments
    code = re.sub(r"//.*", "", code)
    return code


# ══════════════════════════════════════════════════════════════════════
# Tests — Static Security (no fetch, no XHR, no WebSocket, etc.)
# ══════════════════════════════════════════════════════════════════════


class TestShellStaticSecurity(unittest.TestCase):
    """Verify shell JavaScript has no forbidden APIs."""

    def setUp(self):
        self.player_js = _read_shell_file("player.js")
        self.bootstrap_js = _read_shell_file("bootstrap.js")
        self.index_html = _read_shell_file("index.html")
        self.all_js = self.player_js + "\n" + self.bootstrap_js

    # ── Forbidden APIs ──────────────────────────────────────────

    def test_no_fetch(self):
        """Shell must NOT use fetch()."""
        self.assertNotIn("fetch(", self.all_js,
                        "fetch() is forbidden in shell JS")

    def test_no_xml_http_request(self):
        """Shell must NOT use XMLHttpRequest."""
        self.assertNotIn("XMLHttpRequest", self.all_js,
                        "XMLHttpRequest is forbidden in shell JS")

    def test_no_web_socket(self):
        """Shell must NOT use WebSocket in code."""
        code = _strip_comments(self.player_js)
        self.assertNotIn("WebSocket", code,
                        "WebSocket is forbidden in shell JS")

    def test_no_event_source(self):
        """Shell must NOT use EventSource."""
        self.assertNotIn("EventSource", self.all_js,
                        "EventSource is forbidden in shell JS")

    def test_no_eval(self):
        """Shell must NOT use eval()."""
        self.assertNotIn("eval(", self.all_js,
                        "eval() is forbidden in shell JS")

    def test_no_function_constructor(self):
        """Shell must NOT use Function() constructor."""
        self.assertNotIn("Function(", self.all_js,
                        "Function() constructor is forbidden in shell JS")
        self.assertNotIn("new Function", self.all_js,
                        "new Function is forbidden in shell JS")

    def test_no_inner_html(self):
        """Shell must NOT use innerHTML."""
        self.assertNotIn("innerHTML", self.all_js,
                        "innerHTML is forbidden in shell JS")

    def test_no_document_write(self):
        """Shell must NOT use document.write."""
        self.assertNotIn("document.write", self.all_js,
                        "document.write is forbidden in shell JS")

    def test_no_http_url(self):
        """Shell must NOT contain http:// or https:// URLs."""
        self.assertNotRegex(self.all_js.lower(), r"https?://",
                           "http:// or https:// URLs are forbidden in shell JS")

    # ── CSP checks ──────────────────────────────────────────────

    def test_csp_connect_src_none(self):
        """CSP must have connect-src 'none'."""
        self.assertIn("connect-src 'none'", self.index_html,
                      "CSP must have connect-src 'none'")

    def test_csp_no_unsafe_eval(self):
        """CSP must NOT have unsafe-eval."""
        self.assertNotIn("unsafe-eval", self.index_html,
                        "CSP must NOT have unsafe-eval")

    def test_csp_no_unsafe_inline_scripts(self):
        """CSP must NOT have unsafe-inline for scripts."""
        self.assertNotIn("script-src 'unsafe-inline'", self.index_html,
                        "CSP must NOT have unsafe-inline for scripts")

    def test_csp_script_src_self(self):
        """CSP must have script-src 'self'."""
        self.assertIn("script-src 'self'", self.index_html,
                      "CSP must have script-src 'self'")

    # ── Live snapshot refresh API ──────────────────────────────

    def test_live_refresh_api_present(self):
        """player.js must expose startLiveSnapshotRefresh and stopLiveSnapshotRefresh."""
        self.assertIn("startLiveSnapshotRefresh", self.player_js,
                      "startLiveSnapshotRefresh must be exported")
        self.assertIn("stopLiveSnapshotRefresh", self.player_js,
                      "stopLiveSnapshotRefresh must be exported")

    def test_live_refresh_uses_script_tag(self):
        """Live refresh must use document.createElement('script') — no fetch/XHR."""
        self.assertIn('createElement("script")', self.player_js,
                      "Live refresh must use <script> tag injection")

    def test_live_refresh_cache_busting(self):
        """Live refresh must use cache-busting (ts= parameter)."""
        self.assertIn("bootstrap_snapshot.js?ts=", self.player_js,
                      "Live refresh must use cache-busting query parameter")

    def test_live_refresh_no_unsafe_src(self):
        """Live refresh script.src must be local only — no http/https URLs in code."""
        code = _strip_comments(self.player_js)
        # Check for actual URL usage (src=, href=), not blacklist strings
        url_patterns = [
            "src=\"http:", "src='http:", "src=http:",
            "href=\"http:", "href='http:", "href=http:",
        ]
        for pattern in url_patterns:
            self.assertNotIn(pattern, code,
                            f"player.js must not contain '{pattern}'")

    def test_live_refresh_onload_safe(self):
        """Live refresh onload → applySnapshot, onerror → no crash."""
        self.assertIn("applySnapshot(snap)", self.player_js,
                      "onload must call applySnapshot")
        self.assertIn(".onerror", self.player_js,
                      "onerror handler must exist")

    # ── Bootstrap integration ──────────────────────────────────

    def test_bootstrap_starts_live_refresh(self):
        """bootstrap.js must start live snapshot refresh after initial apply."""
        self.assertIn("startLiveSnapshotRefresh", self.bootstrap_js,
                      "Bootstrap must call startLiveSnapshotRefresh")

    def test_bootstrap_check_interval(self):
        """Bootstrap must use a reasonable refresh interval."""
        self.assertIn("startLiveSnapshotRefresh(5000)", self.bootstrap_js,
                      "Bootstrap must start with 5-second interval")

    # ── Snapshot contract compatibility ────────────────────────

    def test_bootstrap_snapshot_has_schema_version(self):
        """Bootstrap snapshot must have schemaVersion."""
        snap_js = _read_shell_file("bootstrap_snapshot.js")
        self.assertIn("schemaVersion", snap_js,
                      "bootstrap_snapshot.js must have schemaVersion")
        self.assertIn("KSO_PLAYER_BOOTSTRAP_SNAPSHOT", snap_js,
                      "Must set window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT")

    def test_bootstrap_snapshot_no_forbidden(self):
        """Bootstrap snapshot must NOT contain forbidden fields."""
        snap_js = _read_shell_file("bootstrap_snapshot.js")
        forbidden = [
            "manifest_item_id", "campaign_id", "creative_id",
            "sha256", "manifest_hash", "backend_base_url",
            "token", "secret", "password",
            "file_path", "media_path", "filename",
        ]
        for fb in forbidden:
            self.assertNotIn(fb, snap_js.lower(),
                            f"bootstrap_snapshot.js must not contain '{fb}'")

    # ── Index.html integrity ───────────────────────────────────

    def test_index_loads_required_scripts(self):
        """index.html must load player.js, bootstrap_snapshot.js, bootstrap.js in order."""
        html = self.index_html
        # Find script loading order
        scripts = re.findall(r'<script src="([^"]+)"></script>', html)
        self.assertIn("player.js", scripts, "Must load player.js")
        self.assertIn("bootstrap_snapshot.js", scripts, "Must load bootstrap_snapshot.js")
        self.assertIn("bootstrap.js", scripts, "Must load bootstrap.js")
        # Order: player → snapshot → bootstrap
        p_idx = scripts.index("player.js")
        s_idx = scripts.index("bootstrap_snapshot.js")
        b_idx = scripts.index("bootstrap.js")
        self.assertLess(p_idx, s_idx, "player.js must load before bootstrap_snapshot.js")
        self.assertLess(s_idx, b_idx, "bootstrap_snapshot.js must load before bootstrap.js")
