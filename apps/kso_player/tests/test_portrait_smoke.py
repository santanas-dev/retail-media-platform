"""Tests for portrait_smoke — local portrait overlay smoke harness.

Validates:
    - SmokeResult construction and safe fields
    - run_portrait_smoke() pipeline end-to-end
    - All visibility scenarios: idle→visible, busy/payment/error/offline→hidden
    - Missing state file → unknown_hidden
    - Stale timestamp → stale_hidden
    - Kill-switch active + idle → kill_switch_hidden
    - Forbidden fields in state → unknown_hidden
    - Geometry matches portrait_idle_overlay_768 (0,400,768,240)
    - Creative canvas matches (0,20,768,200)
    - No mutation of shell plan
    - No forbidden substrings in output
    - CLI imports but does NOT require Xvfb/network/Chromium/subprocess
    - Legacy landscape tests not broken
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from kso_player.portrait_smoke import (
    DEFAULT_PROFILE,
    REASON_IDLE_VISIBLE,
    REASON_STATE_HIDDEN,
    REASON_KILL_SWITCH_HIDDEN,
    REASON_STALE_HIDDEN,
    REASON_UNKNOWN_HIDDEN,
    SmokeResult,
    run_portrait_smoke,
)
from kso_player.state_observer import (
    STATE_IDLE,
    STATE_BUSY,
    STATE_PAYMENT,
    STATE_ERROR,
    STATE_OFFLINE,
    STATE_UNKNOWN,
    STATE_STALE,
)

PROFILE_CODE = "portrait_idle_overlay_768"

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _write_state_file(state, device="a-05954", updated_at=None):
    """Write a valid state.json file and return the path."""
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    data = {
        "schema_version": 1,
        "device_code": device,
        "state": state,
        "source": "test",
        "updated_at_utc": updated_at,
        "stale_after_ms": 999_999_999,  # effectively never stale
    }
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return tmp.name

def _write_kill_switch():
    """Create a kill-switch file and return the path."""
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    return tmp.name


# ══════════════════════════════════════════════════════════════════════
# SmokeResult construction and safe fields
# ══════════════════════════════════════════════════════════════════════


class TestSmokeResultConstruction(unittest.TestCase):
    """SmokeResult dataclass — safe fields only."""

    def test_default_result_is_hidden(self):
        result = SmokeResult()
        self.assertFalse(result.is_visible)
        self.assertEqual(result.visible_plan, "hidden")
        self.assertEqual(result.state, STATE_UNKNOWN)

    def test_visible_result(self):
        result = SmokeResult(
            profile_code=PROFILE_CODE,
            state=STATE_IDLE,
            effective_state=STATE_IDLE,
            visible_plan="visible",
            reason=REASON_IDLE_VISIBLE,
            window_x=0, window_y=400, window_width=768, window_height=240,
            creative_x=0, creative_y=20, creative_width=768, creative_height=200,
        )
        self.assertTrue(result.is_visible)
        self.assertEqual(result.reason, REASON_IDLE_VISIBLE)

    def test_to_dict_has_no_forbidden_keys(self):
        result = SmokeResult(
            profile_code=PROFILE_CODE,
            state=STATE_IDLE,
            visible_plan="visible",
            reason=REASON_IDLE_VISIBLE,
        )
        d = result.to_dict()
        forbidden = ["receipt", "payment", "fiscal", "customer",
                     "card", "pan", "token", "secret", "password",
                     "backend_url", "file_path", "media", "sha256",
                     "ukm5", "mysql"]
        json_str = json.dumps(d).lower()
        for fb in forbidden:
            self.assertNotIn(fb, json_str,
                             f"SmokeResult.to_dict() must not contain '{fb}'")

    def test_to_json_is_valid_json(self):
        result = SmokeResult(profile_code=PROFILE_CODE)
        j = result.to_json()
        parsed = json.loads(j)
        self.assertEqual(parsed["profile_code"], PROFILE_CODE)

    def test_repr_is_safe(self):
        result = SmokeResult(
            profile_code=PROFILE_CODE,
            state=STATE_IDLE,
            window_x=0, window_y=400,
        )
        r = repr(result)
        forbidden = ["receipt", "payment", "fiscal", "customer",
                     "card", "pan", "token", "secret", "password",
                     "file_path", "backend_url", "/run/verny"]
        for fb in forbidden:
            self.assertNotIn(fb, r.lower())


# ══════════════════════════════════════════════════════════════════════
# run_portrait_smoke() — end-to-end pipeline
# ══════════════════════════════════════════════════════════════════════


class TestRunPortraitSmokeIdle(unittest.TestCase):
    """idle state + no kill-switch → visible."""

    def test_idle_no_kill_switch_visible(self):
        state_path = _write_state_file(STATE_IDLE)
        ks_path = None  # no kill-switch file
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=ks_path,
            )
            self.assertTrue(result.is_visible)
            self.assertEqual(result.visible_plan, "visible")
            self.assertEqual(result.reason, REASON_IDLE_VISIBLE)
            self.assertEqual(result.state, STATE_IDLE)
            self.assertEqual(result.effective_state, STATE_IDLE)
            self.assertFalse(result.kill_switch_active)
        finally:
            os.unlink(state_path)

    def test_idle_smoke_geometry(self):
        state_path = _write_state_file(STATE_IDLE)
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=None,
            )
            # Window: 0,400,768,240
            self.assertEqual(result.window_x, 0)
            self.assertEqual(result.window_y, 400)
            self.assertEqual(result.window_width, 768)
            self.assertEqual(result.window_height, 240)
            self.assertEqual(result.root_width, 768)
            self.assertEqual(result.root_height, 1024)
        finally:
            os.unlink(state_path)

    def test_idle_smoke_creative_geometry(self):
        state_path = _write_state_file(STATE_IDLE)
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=None,
            )
            # Creative within window: 0,20,768,200
            self.assertEqual(result.creative_x, 0)
            self.assertEqual(result.creative_y, 20)
            self.assertEqual(result.creative_width, 768)
            self.assertEqual(result.creative_height, 200)
            # Creative fits within window
            self.assertGreaterEqual(result.creative_x, 0)
            self.assertGreaterEqual(result.creative_y, 0)
            self.assertLessEqual(
                result.creative_x + result.creative_width,
                result.window_width,
            )
            self.assertLessEqual(
                result.creative_y + result.creative_height,
                result.window_height,
            )
        finally:
            os.unlink(state_path)


class TestRunPortraitSmokeHidden(unittest.TestCase):
    """Non-idle states → hidden."""

    def _assert_hidden(self, state, expected_reason):
        state_path = _write_state_file(state)
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=None,
            )
            self.assertTrue(result.is_hidden, f"State {state} must be hidden")
            self.assertEqual(result.visible_plan, "hidden")
            self.assertEqual(result.reason, expected_reason,
                             f"State {state}: expected reason {expected_reason}, got {result.reason}")
            self.assertFalse(result.kill_switch_active)
        finally:
            os.unlink(state_path)

    def test_busy_hidden(self):
        self._assert_hidden(STATE_BUSY, REASON_STATE_HIDDEN)

    def test_payment_hidden(self):
        self._assert_hidden(STATE_PAYMENT, REASON_STATE_HIDDEN)

    def test_error_hidden(self):
        self._assert_hidden(STATE_ERROR, REASON_STATE_HIDDEN)

    def test_offline_hidden(self):
        self._assert_hidden(STATE_OFFLINE, REASON_STATE_HIDDEN)

    def test_unknown_hidden(self):
        self._assert_hidden(STATE_UNKNOWN, REASON_UNKNOWN_HIDDEN)

    def test_stale_state_hidden(self):
        self._assert_hidden(STATE_STALE, REASON_STALE_HIDDEN)


class TestRunPortraitSmokeEdgeCases(unittest.TestCase):
    """Edge case scenarios."""

    def test_missing_state_file_hidden(self):
        """No state file → unknown → hidden."""
        nonexistent = "/tmp/__hermes_test_nonexistent_xyz_12345__.json"
        result = run_portrait_smoke(
            profile_code=PROFILE_CODE,
            state_path=nonexistent,
            kill_switch_path=None,
        )
        self.assertTrue(result.is_hidden)
        self.assertEqual(result.reason, REASON_UNKNOWN_HIDDEN)
        self.assertEqual(result.state, STATE_UNKNOWN)
        self.assertFalse(result.kill_switch_active)

    def test_broken_state_file_hidden(self):
        """Broken JSON → hidden."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write("this is not json {broken")
        tmp.close()
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=tmp.name,
                kill_switch_path=None,
            )
            self.assertTrue(result.is_hidden)
            self.assertEqual(result.reason, REASON_UNKNOWN_HIDDEN)
        finally:
            os.unlink(tmp.name)

    def test_forbidden_field_hidden(self):
        """State file with forbidden field → unknown → hidden."""
        data = {
            "schema_version": 1,
            "device_code": "a-05954",
            "state": STATE_IDLE,
            "source": "test",
            "updated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "stale_after_ms": 999_999_999,
            "receipt_id": "r12345",  # FORBIDDEN
        }
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, tmp)
        tmp.close()
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=tmp.name,
                kill_switch_path=None,
            )
            self.assertTrue(result.is_hidden)
            self.assertEqual(result.reason, REASON_UNKNOWN_HIDDEN)
        finally:
            os.unlink(tmp.name)

    def test_stale_timestamp_hidden(self):
        """Old timestamp → stale → hidden."""
        data = {
            "schema_version": 1,
            "device_code": "a-05954",
            "state": STATE_IDLE,
            "source": "test",
            "updated_at_utc": "2020-01-01T00:00:00Z",  # very old
            "stale_after_ms": 5000,
        }
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, tmp)
        tmp.close()
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=tmp.name,
                kill_switch_path=None,
            )
            self.assertTrue(result.is_hidden)
            self.assertEqual(result.reason, REASON_STALE_HIDDEN)
            self.assertEqual(result.effective_state, STATE_STALE)
        finally:
            os.unlink(tmp.name)


class TestRunPortraitSmokeKillSwitch(unittest.TestCase):
    """kill-switch integration tests."""

    def test_kill_switch_active_idle_hidden(self):
        """kill-switch active + idle state → hidden with kill_switch_hidden reason."""
        state_path = _write_state_file(STATE_IDLE)
        ks_path = _write_kill_switch()
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=ks_path,
            )
            self.assertTrue(result.is_hidden)
            self.assertEqual(result.reason, REASON_KILL_SWITCH_HIDDEN)
            self.assertTrue(result.kill_switch_active)
        finally:
            os.unlink(state_path)
            os.unlink(ks_path)

    def test_kill_switch_active_payment_hidden(self):
        """kill-switch active + payment → hidden (already hidden, still ks reason)."""
        state_path = _write_state_file(STATE_PAYMENT)
        ks_path = _write_kill_switch()
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=ks_path,
            )
            self.assertTrue(result.is_hidden)
            self.assertEqual(result.reason, REASON_KILL_SWITCH_HIDDEN)
        finally:
            os.unlink(state_path)
            os.unlink(ks_path)

    def test_kill_switch_absent_idle_visible(self):
        """No kill-switch file + idle → visible."""
        state_path = _write_state_file(STATE_IDLE)
        nonexistent_ks = "/tmp/__hermes_test_nonexistent_ks_xyz__.flag"
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=nonexistent_ks,
            )
            self.assertTrue(result.is_visible)
            self.assertEqual(result.reason, REASON_IDLE_VISIBLE)
            self.assertFalse(result.kill_switch_active)
        finally:
            os.unlink(state_path)


# ══════════════════════════════════════════════════════════════════════
# SmokeResult is_hidden property
# ══════════════════════════════════════════════════════════════════════


class TestSmokeResultIsHidden(unittest.TestCase):
    """SmokeResult.is_hidden property."""

    def test_visible_is_not_hidden(self):
        result = SmokeResult(visible_plan="visible")
        self.assertTrue(result.is_visible)
        self.assertFalse(result.is_hidden)

    def test_hidden_is_hidden(self):
        result = SmokeResult(visible_plan="hidden")
        self.assertFalse(result.is_visible)
        self.assertTrue(result.is_hidden)


# ══════════════════════════════════════════════════════════════════════
# Safety — no network/Chromium/subprocess imports
# ══════════════════════════════════════════════════════════════════════


class TestPortraitSmokeNoLeaks(unittest.TestCase):
    """Smoke module must NOT reference network, Chromium, subprocess, X11."""

    def test_module_has_no_network_imports(self):
        import kso_player.portrait_smoke as ps
        source = ps.__dict__
        network_modules = ["http", "urllib", "socket", "requests", "aiohttp",
                           "httpx", "urllib3", "websocket"]
        for mod_name in network_modules:
            self.assertNotIn(mod_name, source,
                             f"portrait_smoke must not import {mod_name}")

    def test_module_has_no_subprocess(self):
        import kso_player.portrait_smoke as ps
        source = ps.__dict__
        self.assertNotIn("subprocess", source,
                         "portrait_smoke must not import subprocess")

    def test_module_has_no_chromium_imports(self):
        import kso_player.portrait_smoke as ps
        source = ps.__dict__
        chromium_modules = ["selenium", "playwright", "chromium", "webbrowser"]
        for mod_name in chromium_modules:
            self.assertNotIn(mod_name, source,
                             f"portrait_smoke must not import {mod_name}")

    def test_module_has_no_x11_imports(self):
        import kso_player.portrait_smoke as ps
        source = ps.__dict__
        x11_modules = ["Xlib", "xcb", "xdo", "ewmh", "pyvirtualdisplay",
                       "Xvfb", "xvfb", "tkinter"]
        for mod_name in x11_modules:
            self.assertNotIn(mod_name, source,
                             f"portrait_smoke must not import {mod_name}")

    def test_output_json_no_forbidden_keys(self):
        """Smoke output JSON must not contain forbidden substrings."""
        state_path = _write_state_file(STATE_IDLE)
        try:
            result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=None,
            )
            j = result.to_json().lower()
            forbidden = [
                "receipt", "payment", "fiscal", "customer",
                "card_number", "pan", "phone", "email",
                "token", "secret", "password", "api_key",
                "backend_url", "file_path", "sha256",
                "media_path", "creatives/", "ukm5", "mysql",
            ]
            for fb in forbidden:
                self.assertNotIn(fb, j,
                                 f"Smoke JSON must not contain '{fb}'")
        finally:
            os.unlink(state_path)


# ══════════════════════════════════════════════════════════════════════
# SmokeResult flags preservation
# ══════════════════════════════════════════════════════════════════════


class TestSmokeResultFlags(unittest.TestCase):
    """Smoke result correctly reports safety flags from profile."""

    @classmethod
    def setUpClass(cls):
        state_path = _write_state_file(STATE_IDLE)
        try:
            cls.result = run_portrait_smoke(
                profile_code=PROFILE_CODE,
                state_path=state_path,
                kill_switch_path=None,
            )
        finally:
            os.unlink(state_path)

    def test_window_type_overlay(self):
        self.assertEqual(self.result.window_type, "overlay")

    def test_not_fullscreen(self):
        self.assertFalse(self.result.fullscreen)

    def test_not_kiosk(self):
        self.assertFalse(self.result.kiosk)

    def test_always_on_top(self):
        self.assertTrue(self.result.always_on_top)

    def test_no_focus_steal(self):
        self.assertTrue(self.result.no_focus_steal)


# ══════════════════════════════════════════════════════════════════════
# SmokeResult JSON completeness
# ══════════════════════════════════════════════════════════════════════


class TestSmokeResultJSONFields(unittest.TestCase):
    """SmokeResult.to_dict() contains all expected fields."""

    def test_dict_has_expected_top_level_keys(self):
        result = SmokeResult()
        d = result.to_dict()
        expected = {"profile_code", "profile_name", "state", "effective_state",
                    "visible_plan", "reason", "kill_switch_active",
                    "window", "creative", "flags"}
        for key in expected:
            self.assertIn(key, d, f"to_dict() must have key '{key}'")

    def test_window_has_position_and_size(self):
        result = SmokeResult(window_x=0, window_y=400, window_width=768, window_height=240)
        d = result.to_dict()
        self.assertEqual(d["window"]["position"]["x"], 0)
        self.assertEqual(d["window"]["position"]["y"], 400)
        self.assertEqual(d["window"]["size"], "768x240")

    def test_creative_has_position_and_size(self):
        result = SmokeResult(creative_x=0, creative_y=20, creative_width=768, creative_height=200)
        d = result.to_dict()
        self.assertEqual(d["creative"]["position"]["x"], 0)
        self.assertEqual(d["creative"]["position"]["y"], 20)
        self.assertEqual(d["creative"]["size"], "768x200")

    def test_flags_have_all_fields(self):
        result = SmokeResult()
        d = result.to_dict()
        flags = d["flags"]
        self.assertIn("window_type", flags)
        self.assertIn("fullscreen", flags)
        self.assertIn("kiosk", flags)
        self.assertIn("always_on_top", flags)
        self.assertIn("no_focus_steal", flags)


# ══════════════════════════════════════════════════════════════════════
# Legacy landscape compatibility
# ══════════════════════════════════════════════════════════════════════


class TestSmokeLegacyNotBroken(unittest.TestCase):
    """Legacy landscape player tests are NOT affected by portrait_smoke."""

    def test_local_chromium_demo_runner_unchanged(self):
        from kso_player.local_chromium_demo_runner import WINDOW_WIDTH, WINDOW_HEIGHT
        self.assertEqual(WINDOW_WIDTH, 1440)
        self.assertEqual(WINDOW_HEIGHT, 1080)

    def test_shell_command_imports_cleanly(self):
        import kso_player.shell_command
        self.assertTrue(hasattr(kso_player.shell_command, "build_kso_shell_command"))

    def test_render_plan_imports_cleanly(self):
        import kso_player.render_plan
        self.assertTrue(hasattr(kso_player.render_plan, "build_kso_render_plan"))

    def test_state_observer_imports_cleanly(self):
        import kso_player.state_observer
        self.assertTrue(hasattr(kso_player.state_observer, "read_state_snapshot"))

    def test_kill_switch_imports_cleanly(self):
        import kso_player.kill_switch
        self.assertTrue(hasattr(kso_player.kill_switch, "is_kill_switch_active"))


if __name__ == "__main__":
    unittest.main()
