"""Tests for kill_switch — local file-flag based safety mechanism.

Validates:
    - is_kill_switch_active() file existence rules
    - Safety-first: errors → active, bad paths → active
    - Integration with shell plan: kill-switch overrides state visibility
    - No network/UKM5/DB references
    - Immutability of original plan
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from kso_player.kill_switch import (
    DEFAULT_KILL_SWITCH_PATH,
    is_kill_switch_active,
)
from kso_player.shell_plan import (
    build_shell_plan,
    validate_shell_plan_with_kill_switch,
    ShellPlan,
    PLAN_MODE_VISIBLE,
    PLAN_MODE_HIDDEN,
    PLAN_MODE_HOLD,
)

PROFILE_CODE = "portrait_idle_overlay_768"


# ══════════════════════════════════════════════════════════════════════
# Core kill-switch function tests
# ══════════════════════════════════════════════════════════════════════


class TestKillSwitchFileExists(unittest.TestCase):
    """Test is_kill_switch_active based on file existence."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp_path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_file_exists_active(self):
        """When file exists, kill-switch is active."""
        self.assertTrue(is_kill_switch_active(self.tmp_path))

    def test_file_not_exists_inactive(self):
        """When file does NOT exist, kill-switch is inactive."""
        os.unlink(self.tmp_path)
        self.assertFalse(is_kill_switch_active(self.tmp_path))

    def test_nonexistent_path_inactive(self):
        """Path that never existed is inactive."""
        result = is_kill_switch_active("/tmp/__hermes_test_nonexistent_xyz_12345__")
        self.assertFalse(result)


class TestKillSwitchErrorsActive(unittest.TestCase):
    """Test that any error yields ACTIVE (fail-safe)."""

    @patch("os.path.isfile", side_effect=PermissionError("denied"))
    def test_permission_error_active(self, mock_isfile):
        self.assertTrue(is_kill_switch_active("/root/forbidden"))

    @patch("os.path.isfile", side_effect=OSError("I/O error"))
    def test_oserror_active(self, mock_isfile):
        self.assertTrue(is_kill_switch_active("/some/path"))

    @patch("os.path.isfile", side_effect=IOError("generic IO"))
    def test_ioerror_active(self, mock_isfile):
        self.assertTrue(is_kill_switch_active("/some/path"))


class TestKillSwitchBadPaths(unittest.TestCase):
    """Test safe defaults for invalid paths."""

    def test_none_path_active(self):
        """None path → active (bad config — fail safe)."""
        self.assertTrue(is_kill_switch_active(None))

    def test_empty_string_active(self):
        """Empty string path → active (bad config — fail safe)."""
        self.assertTrue(is_kill_switch_active(""))

    def test_whitespace_only_active(self):
        """Whitespace-only path → active (bad config — fail safe)."""
        self.assertTrue(is_kill_switch_active("   "))


class TestKillSwitchCustomPath(unittest.TestCase):
    """Test custom path support."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp_path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_custom_path_file_exists_active(self):
        self.assertTrue(is_kill_switch_active(self.tmp_path))

    def test_custom_path_file_missing_inactive(self):
        os.unlink(self.tmp_path)
        self.assertFalse(is_kill_switch_active(self.tmp_path))


class TestKillSwitchDefaultPath(unittest.TestCase):
    """Test default path behavior."""

    def test_default_path_is_defined(self):
        self.assertEqual(DEFAULT_KILL_SWITCH_PATH, "/run/verny/kso/kill_switch")

    def test_default_path_does_not_throw(self):
        """Default path check should not throw when file doesn't exist."""
        try:
            result = is_kill_switch_active()
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"is_kill_switch_active() raised {type(e).__name__}: {e}")


# ══════════════════════════════════════════════════════════════════════
# Integration: shell plan + kill-switch via build_shell_plan
# ══════════════════════════════════════════════════════════════════════


class TestShellPlanWithKillSwitchActive(unittest.TestCase):
    """When kill_switch_active=True, shell plan is always hidden."""

    def test_idle_plus_kill_switch_active_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="idle",
                                kill_switch_active=True)
        self.assertTrue(plan.is_hidden())
        self.assertEqual(plan.visible_plan, PLAN_MODE_HIDDEN)

    def test_idle_plus_kill_switch_inactive_visible(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="idle",
                                kill_switch_active=False)
        self.assertTrue(plan.is_visible())
        self.assertEqual(plan.visible_plan, PLAN_MODE_VISIBLE)

    def test_payment_plus_kill_switch_inactive_hidden(self):
        """Payment + no kill-switch → still hidden (state override)."""
        plan = build_shell_plan(PROFILE_CODE, initial_state="payment",
                                kill_switch_active=False)
        self.assertTrue(plan.is_hidden())

    def test_unknown_plus_kill_switch_inactive_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="unknown",
                                kill_switch_active=False)
        self.assertTrue(plan.is_hidden())

    def test_stale_plus_kill_switch_inactive_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="stale",
                                kill_switch_active=False)
        self.assertTrue(plan.is_hidden())

    def test_busy_plus_kill_switch_active_hidden(self):
        """Kill-switch overrides: busy + active → hidden (already hidden, safe)."""
        plan = build_shell_plan(PROFILE_CODE, initial_state="busy",
                                kill_switch_active=True)
        self.assertTrue(plan.is_hidden())

    def test_payment_plus_kill_switch_active_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="payment",
                                kill_switch_active=True)
        self.assertTrue(plan.is_hidden())

    def test_unknown_plus_kill_switch_active_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="unknown",
                                kill_switch_active=True)
        self.assertTrue(plan.is_hidden())

    def test_stale_plus_kill_switch_active_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="stale",
                                kill_switch_active=True)
        self.assertTrue(plan.is_hidden())


class TestShellPlanKillSwitchGeometryPreserved(unittest.TestCase):
    """Kill-switch does NOT affect geometry or safety flags."""

    def test_geometry_preserved_when_active(self):
        idle_plan = build_shell_plan(PROFILE_CODE, initial_state="idle",
                                     kill_switch_active=False)
        ks_plan = build_shell_plan(PROFILE_CODE, initial_state="idle",
                                   kill_switch_active=True)
        self.assertEqual(ks_plan.window_x, idle_plan.window_x)
        self.assertEqual(ks_plan.window_y, idle_plan.window_y)
        self.assertEqual(ks_plan.window_width, idle_plan.window_width)
        self.assertEqual(ks_plan.window_height, idle_plan.window_height)
        self.assertEqual(ks_plan.creative_x, idle_plan.creative_x)
        self.assertEqual(ks_plan.creative_y, idle_plan.creative_y)
        self.assertEqual(ks_plan.creative_width, idle_plan.creative_width)
        self.assertEqual(ks_plan.creative_height, idle_plan.creative_height)

    def test_safety_flags_preserved_when_active(self):
        idle_plan = build_shell_plan(PROFILE_CODE, initial_state="idle",
                                     kill_switch_active=False)
        ks_plan = build_shell_plan(PROFILE_CODE, initial_state="idle",
                                   kill_switch_active=True)
        self.assertEqual(ks_plan.kill_switch_required, idle_plan.kill_switch_required)
        self.assertEqual(ks_plan.always_on_top, idle_plan.always_on_top)
        self.assertEqual(ks_plan.no_focus_steal, idle_plan.no_focus_steal)
        self.assertEqual(ks_plan.idle_only, idle_plan.idle_only)
        self.assertEqual(ks_plan.no_ukm5_db, idle_plan.no_ukm5_db)
        self.assertEqual(ks_plan.forbidden_zones, idle_plan.forbidden_zones)
        self.assertEqual(ks_plan.forbidden_chromium_flags, idle_plan.forbidden_chromium_flags)

    def test_window_type_preserved_when_active(self):
        idle_plan = build_shell_plan(PROFILE_CODE, initial_state="idle",
                                     kill_switch_active=False)
        ks_plan = build_shell_plan(PROFILE_CODE, initial_state="idle",
                                   kill_switch_active=True)
        self.assertEqual(ks_plan.window_type, idle_plan.window_type)
        self.assertEqual(ks_plan.fullscreen, idle_plan.fullscreen)
        self.assertEqual(ks_plan.kiosk, idle_plan.kiosk)


# ══════════════════════════════════════════════════════════════════════
# Integration: validate_shell_plan_with_kill_switch
# ══════════════════════════════════════════════════════════════════════


class TestValidateShellPlanWithKillSwitch(unittest.TestCase):
    """validate_shell_plan_with_kill_switch overrides visibility."""

    @classmethod
    def setUpClass(cls):
        cls.plan: ShellPlan = build_shell_plan(
            PROFILE_CODE, initial_state="idle", kill_switch_active=False
        )

    def test_kill_switch_active_overrides_idle_to_hidden(self):
        """Even with idle visible plan, kill-switch forces hidden."""
        self.assertTrue(self.plan.is_visible(),
                        "Baseline: idle + no kill-switch must be visible")
        updated = validate_shell_plan_with_kill_switch(self.plan,
                                                       kill_switch_active=True)
        self.assertTrue(updated.is_hidden())

    def test_kill_switch_inactive_preserves_idle_visible(self):
        updated = validate_shell_plan_with_kill_switch(self.plan,
                                                       kill_switch_active=False)
        self.assertTrue(updated.is_visible())

    def test_kill_switch_active_preserves_hidden(self):
        """Hidden plan + kill_switch_active → still hidden."""
        hidden_plan = build_shell_plan(
            PROFILE_CODE, initial_state="busy", kill_switch_active=False
        )
        self.assertTrue(hidden_plan.is_hidden(), "Baseline: busy must be hidden")
        updated = validate_shell_plan_with_kill_switch(hidden_plan,
                                                       kill_switch_active=True)
        self.assertTrue(updated.is_hidden())

    def test_original_plan_not_mutated(self):
        original_visibility = self.plan.visible_plan
        validate_shell_plan_with_kill_switch(self.plan,
                                             kill_switch_active=True)
        self.assertEqual(self.plan.visible_plan, original_visibility,
                         "Original plan must not be mutated")

    def test_geometry_preserved(self):
        updated = validate_shell_plan_with_kill_switch(self.plan,
                                                       kill_switch_active=True)
        self.assertEqual(updated.window_x, self.plan.window_x)
        self.assertEqual(updated.window_y, self.plan.window_y)
        self.assertEqual(updated.window_width, self.plan.window_width)
        self.assertEqual(updated.window_height, self.plan.window_height)

    def test_safety_flags_preserved(self):
        updated = validate_shell_plan_with_kill_switch(self.plan,
                                                       kill_switch_active=True)
        self.assertEqual(updated.kill_switch_required, self.plan.kill_switch_required)
        self.assertEqual(updated.always_on_top, self.plan.always_on_top)
        self.assertEqual(updated.no_focus_steal, self.plan.no_focus_steal)
        self.assertEqual(updated.forbidden_zones, self.plan.forbidden_zones)


# ══════════════════════════════════════════════════════════════════════
# Safety assertions — no network/UKM5/DB references
# ══════════════════════════════════════════════════════════════════════


class TestKillSwitchNoLeaks(unittest.TestCase):
    """Kill-switch module must NOT reference network, UKM5, DB, or secrets."""

    def test_module_has_no_network_imports(self):
        import kso_player.kill_switch as ks
        source = ks.__dict__
        network_modules = ["http", "urllib", "socket", "requests", "aiohttp",
                           "httpx", "urllib3", "websocket"]
        for mod_name in network_modules:
            self.assertNotIn(mod_name, source,
                             f"kill_switch must not import {mod_name}")

    def test_module_has_no_db_imports(self):
        import kso_player.kill_switch as ks
        source = ks.__dict__
        db_modules = ["sqlite3", "psycopg2", "sqlalchemy", "mysql",
                      "redis", "pymongo", "clickhouse"]
        for mod_name in db_modules:
            self.assertNotIn(mod_name, source,
                             f"kill_switch must not import {mod_name}")

    def test_module_has_no_subprocess(self):
        import kso_player.kill_switch as ks
        source = ks.__dict__
        self.assertNotIn("subprocess", source,
                         "kill_switch must not import subprocess")

    def test_no_references_to_ukm5(self):
        """Functional code must not contain 'ukm5' references (docstrings/comments ok)."""
        import inspect
        import kso_player.kill_switch as ks

        # Strip docstrings and comments — only check actual code
        source_lines = []
        in_triple_quote = False
        for line in inspect.getsource(ks).split("\n"):
            stripped = line.strip()
            # Track triple-quoted docstrings
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_triple_quote = not in_triple_quote
                continue
            if in_triple_quote:
                continue
            # Skip comments
            if stripped.startswith("#"):
                continue
            # Skip empty lines
            if not stripped:
                continue
            source_lines.append(stripped.lower())

        functional_code = "\n".join(source_lines)
        self.assertNotIn("ukm5", functional_code,
                         "kill_switch functional code must not reference UKM5")

    def test_no_references_to_kso_state_json(self):
        import inspect
        import kso_player.kill_switch as ks
        source = inspect.getsource(ks)
        self.assertNotIn("kso_state", source.lower(),
                         "kill_switch must not reference kso_state.json")

    def test_default_path_is_under_run(self):
        """Default path must be under /run/verny/kso/."""
        self.assertTrue(
            DEFAULT_KILL_SWITCH_PATH.startswith("/run/verny/kso/"),
            f"Kill-switch path {DEFAULT_KILL_SWITCH_PATH} must be under /run/verny/kso/"
        )


# ══════════════════════════════════════════════════════════════════════
# Legacy landscape compatibility
# ══════════════════════════════════════════════════════════════════════


class TestKillSwitchLegacyLandscapeNotBroken(unittest.TestCase):
    """Legacy landscape player tests are NOT affected by kill_switch additions."""

    def test_shell_plan_imports_cleanly(self):
        import kso_player.shell_plan
        self.assertTrue(hasattr(kso_player.shell_plan, "build_shell_plan"))

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


if __name__ == "__main__":
    unittest.main()
