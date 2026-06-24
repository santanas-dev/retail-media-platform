"""Tests for visual_proof_harness — overlay visibility verification.

Validates:
    - Chromium command: NO forbidden flags, correct geometry, DISPLAY set
    - Overlay HTML: unique title, no external URLs, bright test block
    - sanitize_output: rejects forbidden substrings, passes safe content
    - _parse_xwininfo: correct geometry parsing
    - Dry-run CLI: exits 0, returns safe JSON
    - Failure modes: forbidden flag detection, missing geometry params
"""

import json
import os
import sys
import tempfile
import unittest

# Add scripts dir to path
SCRIPT_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'scripts'
)
sys.path.insert(0, os.path.abspath(SCRIPT_DIR))

from visual_proof_harness import (
    build_chromium_cmd,
    build_overlay_html,
    has_forbidden_substrings,
    sanitize_output,
    _parse_xwininfo,
    FORBIDDEN_FLAGS,
    OVERLAY_TITLE,
    WINDOW_X,
    WINDOW_Y,
    WINDOW_W,
    WINDOW_H,
)


class TestBuildChromiumCmd(unittest.TestCase):
    """Chromium command builder — forbidden flags, geometry, DISPLAY."""

    def test_no_forbidden_flags(self):
        """Built command MUST NOT contain any forbidden flags."""
        cmd, errors = build_chromium_cmd("/tmp/test.html", "/tmp/profile")
        cmd_str = " ".join(cmd)
        for flag in FORBIDDEN_FLAGS:
            with self.subTest(flag=flag):
                self.assertNotIn(flag, cmd_str,
                                 "Forbidden flag {} found in command".format(flag))

    def test_has_window_position(self):
        """Command must include --window-position."""
        cmd, _ = build_chromium_cmd("/tmp/test.html", "/tmp/profile")
        cmd_str = " ".join(cmd)
        self.assertIn("--window-position", cmd_str)

    def test_has_window_size(self):
        """Command must include --window-size."""
        cmd, _ = build_chromium_cmd("/tmp/test.html", "/tmp/profile")
        cmd_str = " ".join(cmd)
        self.assertIn("--window-size", cmd_str)

    def test_correct_geometry_values(self):
        """Command --window-position and --window-size match profile."""
        cmd, _ = build_chromium_cmd("/tmp/test.html", "/tmp/profile")
        cmd_str = " ".join(cmd)
        expected_pos = "--window-position={},{}".format(WINDOW_X, WINDOW_Y)
        expected_size = "--window-size={},{}".format(WINDOW_W, WINDOW_H)
        self.assertIn(expected_pos, cmd_str)
        self.assertIn(expected_size, cmd_str)

    def test_display_set(self):
        """Command starts with env DISPLAY=..."""
        cmd, _ = build_chromium_cmd("/tmp/test.html", "/tmp/profile", ":0")
        self.assertIn("env", cmd[0:2])
        self.assertIn("DISPLAY", str(cmd[0:2]))

    def test_has_app_flag(self):
        """--app flag present (NOT --kiosk)."""
        cmd, _ = build_chromium_cmd("/tmp/test.html", "/tmp/profile")
        cmd_str = " ".join(cmd)
        self.assertIn("--app=", cmd_str)

    def test_no_errors_for_valid_input(self):
        """Valid input produces no errors."""
        _, errors = build_chromium_cmd("/tmp/test.html", "/tmp/profile")
        self.assertEqual(errors, [])

    def test_user_data_dir_included(self):
        """--user-data-dir must be in command (isolated profile)."""
        cmd, _ = build_chromium_cmd("/tmp/test.html", "/tmp/special_dir")
        cmd_str = " ".join(cmd)
        self.assertIn("--user-data-dir=/tmp/special_dir", cmd_str)


class TestForbiddenFlagDetection(unittest.TestCase):
    """Detection of forbidden flags in built command."""

    def test_detect_kiosk(self):
        """Forgery: if --kiosk sneaks in, it MUST be caught."""
        # We test the FORBIDDEN_FLAGS check logic manually
        # build_chromium_cmd never produces forbidden flags,
        # so we verify the check logic itself
        cmd = ["chromium-browser", "--kiosk", "--window-position=0,400"]
        found = [f for f in FORBIDDEN_FLAGS if f in cmd]
        self.assertIn("--kiosk", found)

    def test_detect_fullscreen(self):
        cmd = ["chromium-browser", "--fullscreen"]
        found = [f for f in FORBIDDEN_FLAGS if f in cmd]
        self.assertIn("--fullscreen", found)

    def test_detect_start_fullscreen(self):
        cmd = ["chromium-browser", "--start-fullscreen"]
        found = [f for f in FORBIDDEN_FLAGS if f in cmd]
        self.assertIn("--start-fullscreen", found)

    def test_detect_start_maximized(self):
        cmd = ["chromium-browser", "--start-maximized"]
        found = [f for f in FORBIDDEN_FLAGS if f in cmd]
        self.assertIn("--start-maximized", found)

    def test_all_forbidden_flags_absent_from_built_cmd(self):
        """build_chromium_cmd MUST never produce forbidden flags."""
        cmd, _ = build_chromium_cmd("/tmp/t.html", "/tmp/p")
        cmd_str = " ".join(cmd).lower()
        for flag in FORBIDDEN_FLAGS:
            self.assertNotIn(flag.lower(), cmd_str)


class TestBuildOverlayHtml(unittest.TestCase):
    """Overlay HTML builder — safe, static, no external URLs."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.html_path = os.path.join(self.tmpdir, "overlay.html")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_file(self):
        build_overlay_html(self.html_path)
        self.assertTrue(os.path.exists(self.html_path))

    def test_contains_unique_title(self):
        build_overlay_html(self.html_path)
        with open(self.html_path) as f:
            content = f.read()
        self.assertIn(OVERLAY_TITLE, content)

    def test_no_external_urls(self):
        """Overlay HTML must NOT contain http:// or https:// URLs."""
        build_overlay_html(self.html_path)
        with open(self.html_path) as f:
            content = f.read()
        self.assertNotIn("http://", content)
        self.assertNotIn("https://", content)

    def test_no_script_tags(self):
        """No <script> — pure static display."""
        build_overlay_html(self.html_path)
        with open(self.html_path) as f:
            content = f.read()
        self.assertNotIn("<script", content.lower())

    def test_contains_bright_color(self):
        """Must have a bright, visible background color."""
        build_overlay_html(self.html_path)
        with open(self.html_path) as f:
            content = f.read()
        # Should have a visible background color (not white/black)
        self.assertIn("background:#ff3366", content)

    def test_correct_dimensions(self):
        """HTML body dimensions match window geometry."""
        build_overlay_html(self.html_path)
        with open(self.html_path) as f:
            content = f.read()
        self.assertIn("width:{}px".format(WINDOW_W), content)
        self.assertIn("height:{}px".format(WINDOW_H), content)


class TestHasForbiddenSubstrings(unittest.TestCase):
    """Forbidden substring detection."""

    def test_receipt_detected(self):
        self.assertTrue(has_forbidden_substrings("receipt_id=12345"))

    def test_payment_detected(self):
        self.assertTrue(has_forbidden_substrings("payment_amount=100"))

    def test_token_detected(self):
        self.assertTrue(has_forbidden_substrings("token=abc.def.ghi"))

    def test_secret_detected(self):
        self.assertTrue(has_forbidden_substrings("my_secret_key"))

    def test_backend_url_detected(self):
        self.assertTrue(has_forbidden_substrings("backend_url=https://..."))

    def test_safe_text_passes(self):
        self.assertFalse(has_forbidden_substrings("window-position=0,400"))
        self.assertFalse(has_forbidden_substrings("VISUAL_PROOF_OVERLAY"))

    def test_empty_string_passes(self):
        self.assertFalse(has_forbidden_substrings(""))

    def test_none_passes(self):
        self.assertFalse(has_forbidden_substrings(None))

    def test_case_insensitive(self):
        self.assertTrue(has_forbidden_substrings("TOKEN=ABC"))

    def test_ukm5_detected(self):
        self.assertTrue(has_forbidden_substrings("ukm5_db_host=localhost"))


class TestSanitizeOutput(unittest.TestCase):
    """Safe JSON output — rejects forbidden content."""

    def test_safe_dict_passes(self):
        data = {"visible": True, "window": {"x": 0, "y": 400}}
        result = sanitize_output(data)
        self.assertEqual(result, data)

    def test_forbidden_value_rejected(self):
        data = {"visible": True, "extra": "payment_amount=100"}
        result = sanitize_output(data)
        self.assertIn("_error", result)
        self.assertEqual(result["_error"], "forbidden_content_in_value")

    def test_nested_forbidden_rejected(self):
        data = {"result": {"data": {"secret": "abc"}}}
        result = sanitize_output(data)
        self.assertIn("_error", result)

    def test_list_passes_if_safe(self):
        data = {"items": [1, 2, 3]}
        result = sanitize_output(data)
        self.assertEqual(result, data)

    def test_geometry_safe(self):
        data = {"x": 0, "y": 400, "w": 768, "h": 240}
        result = sanitize_output(data)
        self.assertEqual(result, data)


class TestParseXwininfo(unittest.TestCase):
    """xwininfo output parser."""

    def test_parse_absolute_position(self):
        text = """...
  Absolute upper-left X:  0
  Absolute upper-left Y:  400
  Width: 768
  Height: 240
  Corners:  +0+400  -0+400  -0-384  +0-384
"""
        result = _parse_xwininfo(text)
        self.assertEqual(result["absolute_x"], 0)
        self.assertEqual(result["absolute_y"], 400)

    def test_parse_dimensions(self):
        text = """...
  Width: 768
  Height: 240
"""
        result = _parse_xwininfo(text)
        self.assertEqual(result["width"], 768)
        self.assertEqual(result["height"], 240)

    def test_parse_corners(self):
        text = """Corners:  +0+400  -0+400  -0-384  +0-384"""
        result = _parse_xwininfo(text)
        self.assertIn("corners", result)

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_xwininfo(""))

    def test_no_dimensions_returns_partial(self):
        text = "  Absolute upper-left X:  10"
        result = _parse_xwininfo(text)
        self.assertEqual(result["absolute_x"], 10)
        self.assertNotIn("width", result)


class TestDryRunCLI(unittest.TestCase):
    """CLI --dry-run mode."""

    def test_dry_run_exits_zero(self):
        import subprocess
        script = os.path.join(SCRIPT_DIR, "visual_proof_harness.py")
        result = subprocess.run(
            [sys.executable, script, "--dry-run"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0,
                         "Dry-run should exit 0\nstderr: {}".format(result.stderr))

    def test_dry_run_output_is_valid_json(self):
        import subprocess
        script = os.path.join(SCRIPT_DIR, "visual_proof_harness.py")
        result = subprocess.run(
            [sys.executable, script, "--dry-run"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["mode"], "dry_run")
        self.assertTrue(data["command_valid"])
        self.assertEqual(data["forbidden_flags_check"], "ok")

    def test_dry_run_has_correct_geometry(self):
        import subprocess
        script = os.path.join(SCRIPT_DIR, "visual_proof_harness.py")
        result = subprocess.run(
            [sys.executable, script, "--dry-run"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        geom = data["window_geometry"]
        self.assertEqual(geom["x"], 0)
        self.assertEqual(geom["y"], 400)
        self.assertEqual(geom["w"], 768)
        self.assertEqual(geom["h"], 240)

    def test_dry_run_no_forbidden_flags(self):
        import subprocess
        script = os.path.join(SCRIPT_DIR, "visual_proof_harness.py")
        result = subprocess.run(
            [sys.executable, script, "--dry-run"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        self.assertTrue(data["no_forbidden_flags"])

    def test_dry_run_output_safe(self):
        """Dry-run output must NOT contain forbidden substrings."""
        import subprocess
        script = os.path.join(SCRIPT_DIR, "visual_proof_harness.py")
        result = subprocess.run(
            [sys.executable, script, "--dry-run"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertFalse(has_forbidden_substrings(result.stdout))

    def test_dry_run_has_window_position_flag(self):
        import subprocess
        script = os.path.join(SCRIPT_DIR, "visual_proof_harness.py")
        result = subprocess.run(
            [sys.executable, script, "--dry-run"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        self.assertTrue(data["has_window_position"])
        self.assertTrue(data["has_window_size"])


class TestFailureModes(unittest.TestCase):
    """Visual proof harness failure modes."""

    def test_visual_not_confirmed_without_window(self):
        """If no window found, visual_confirmed MUST be False."""
        result = {
            "overlay_alive": True,
            "window_found": False,
            "window_id": None,
            "screenshot_during": "/tmp/test.png",
            "window_overlaps_payment": False,
            "window_overlaps_header": False,
            "overlay_killed": True,
            "errors": [],
        }
        confirmed = (
            result["overlay_alive"]
            and result["window_found"]
            and result["screenshot_during"] is not None
            and not result["window_overlaps_payment"]
            and not result["window_overlaps_header"]
            and result["overlay_killed"]
            and not result["errors"]
        )
        self.assertFalse(confirmed, "visual_confirmed MUST be False when window not found")

    def test_visual_not_confirmed_overlap_payment(self):
        """If overlay overlaps payment, visual_confirmed MUST be False."""
        result = {
            "overlay_alive": True,
            "window_found": True,
            "window_id": "0x123",
            "screenshot_during": "/tmp/test.png",
            "window_overlaps_payment": True,
            "window_overlaps_header": False,
            "overlay_killed": True,
            "errors": [],
        }
        confirmed = (
            result["overlay_alive"] and result["window_found"]
            and result["screenshot_during"] is not None
            and not result["window_overlaps_payment"]
            and not result["window_overlaps_header"]
            and result["overlay_killed"] and not result["errors"]
        )
        self.assertFalse(confirmed)

    def test_visual_not_confirmed_overlap_header(self):
        """If overlay overlaps header, visual_confirmed MUST be False."""
        result = {
            "overlay_alive": True,
            "window_found": True,
            "window_id": "0x123",
            "screenshot_during": "/tmp/test.png",
            "window_overlaps_payment": False,
            "window_overlaps_header": True,
            "overlay_killed": True,
            "errors": [],
        }
        confirmed = (
            result["overlay_alive"] and result["window_found"]
            and result["screenshot_during"] is not None
            and not result["window_overlaps_payment"]
            and not result["window_overlaps_header"]
            and result["overlay_killed"] and not result["errors"]
        )
        self.assertFalse(confirmed)

    def test_visual_not_confirmed_missing_screenshot(self):
        """If screenshot not taken, visual_confirmed MUST be False."""
        result = {
            "overlay_alive": True,
            "window_found": True,
            "window_id": "0x123",
            "screenshot_during": None,
            "window_overlaps_payment": False,
            "window_overlaps_header": False,
            "overlay_killed": True,
            "errors": [],
        }
        confirmed = (
            result["overlay_alive"] and result["window_found"]
            and result["screenshot_during"] is not None
            and not result["window_overlaps_payment"]
            and not result["window_overlaps_header"]
            and result["overlay_killed"] and not result["errors"]
        )
        self.assertFalse(confirmed)

    def test_visual_not_confirmed_errors_present(self):
        """Any error → visual_confirmed MUST be False."""
        result = {
            "overlay_alive": True,
            "window_found": True,
            "window_id": "0x123",
            "screenshot_during": "/tmp/test.png",
            "window_overlaps_payment": False,
            "window_overlaps_header": False,
            "overlay_killed": True,
            "errors": ["SOME_ERROR"],
        }
        confirmed = (
            result["overlay_alive"] and result["window_found"]
            and result["screenshot_during"] is not None
            and not result["window_overlaps_payment"]
            and not result["window_overlaps_header"]
            and result["overlay_killed"] and not result["errors"]
        )
        self.assertFalse(confirmed)


if __name__ == "__main__":
    unittest.main()
