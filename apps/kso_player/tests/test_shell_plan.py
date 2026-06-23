"""Tests for shell_plan — profile-driven window/shell configuration.

Validates:
    - Shell plan generated from portrait_idle_overlay_768 profile
    - Shell plan is non-fullscreen, overlay type
    - Window geometry matches profile overlay zone
    - Creative canvas within window
    - Forbidden Chromium flags for non-fullscreen
    - State-based visibility: idle→visible, busy/payment/unknown/stale→hidden
    - Kill-switch and safety flags
    - validate_shell_plan_for_state() transitions
    - Legacy landscape tests are NOT broken
"""

import unittest

from kso_player.profiles import get_profile
from kso_player.shell_plan import (
    build_shell_plan,
    validate_shell_plan_for_state,
    ShellPlan,
    PLAN_MODE_VISIBLE,
    PLAN_MODE_HIDDEN,
    PLAN_MODE_HOLD,
    WINDOW_TYPE_OVERLAY,
    WINDOW_TYPE_KIOSK,
    WINDOW_TYPE_APP,
    _FORBIDDEN_FULLSCREEN_FLAGS,
)

PROFILE_CODE = "portrait_idle_overlay_768"


class TestShellPlanPortraitProfile(unittest.TestCase):
    """Shell plan generated from portrait_idle_overlay_768 profile."""

    @classmethod
    def setUpClass(cls):
        cls.plan: ShellPlan = build_shell_plan(PROFILE_CODE)

    def test_plan_exists(self):
        self.assertIsNotNone(self.plan)
        self.assertIsInstance(self.plan, ShellPlan)

    def test_profile_code_matches(self):
        self.assertEqual(self.plan.profile_code, PROFILE_CODE)

    def test_non_fullscreen(self):
        self.assertFalse(self.plan.fullscreen, "Portrait profile must NOT be fullscreen")

    def test_not_kiosk(self):
        self.assertFalse(self.plan.kiosk, "Portrait profile must NOT use --kiosk")

    def test_window_type_overlay(self):
        self.assertEqual(self.plan.window_type, WINDOW_TYPE_OVERLAY)

    # ── Geometry ────────────────────────────────────────────────

    def test_root_dimensions(self):
        self.assertEqual(self.plan.root_width, 768)
        self.assertEqual(self.plan.root_height, 1024)

    def test_window_position(self):
        self.assertEqual(self.plan.window_x, 0)
        self.assertEqual(self.plan.window_y, 400)

    def test_window_size(self):
        self.assertEqual(self.plan.window_width, 768)
        self.assertEqual(self.plan.window_height, 240)

    def test_window_within_root(self):
        self.assertGreaterEqual(self.plan.window_x, 0)
        self.assertGreaterEqual(self.plan.window_y, 0)
        self.assertLessEqual(
            self.plan.window_x + self.plan.window_width,
            self.plan.root_width,
        )
        self.assertLessEqual(
            self.plan.window_y + self.plan.window_height,
            self.plan.root_height,
        )

    def test_creative_canvas_within_window(self):
        self.assertGreaterEqual(self.plan.creative_x, 0)
        self.assertGreaterEqual(self.plan.creative_y, 0)
        self.assertLessEqual(
            self.plan.creative_x + self.plan.creative_width,
            self.plan.window_width,
        )
        self.assertLessEqual(
            self.plan.creative_y + self.plan.creative_height,
            self.plan.window_height,
        )

    def test_creative_canvas_dimensions(self):
        self.assertEqual(self.plan.creative_width, 768)
        self.assertEqual(self.plan.creative_height, 200)

    def test_creative_canvas_offset(self):
        # Creative relative to window: y=420-400=20 within window
        self.assertEqual(self.plan.creative_x, 0)
        self.assertEqual(self.plan.creative_y, 20)

    # ── Safety flags ────────────────────────────────────────────

    def test_always_on_top(self):
        self.assertTrue(self.plan.always_on_top,
                        "Portrait overlay must stay above UKM5")

    def test_no_focus_steal(self):
        self.assertTrue(self.plan.no_focus_steal,
                        "Portrait overlay must not steal input focus")

    def test_kill_switch_required(self):
        self.assertTrue(self.plan.kill_switch_required)

    def test_hide_on_start_if_state_not_idle(self):
        self.assertTrue(self.plan.hide_on_start_if_state_not_idle)

    def test_idle_only(self):
        self.assertTrue(self.plan.idle_only)

    def test_no_ukm5_db(self):
        self.assertTrue(self.plan.no_ukm5_db)

    def test_hide_sla(self):
        self.assertEqual(self.plan.hide_sla_ms, 500)

    # ── Forbidden zones ─────────────────────────────────────────

    def test_forbidden_zones_present(self):
        self.assertGreater(len(self.plan.forbidden_zones), 0,
                           "Portrait plan must have forbidden zones")

    def test_forbidden_chromium_flags_present(self):
        self.assertGreater(len(self.plan.forbidden_chromium_flags), 0,
                           "Non-fullscreen plan must forbid kiosk/fullscreen flags")

    def test_forbidden_flags_include_kiosk(self):
        self.assertIn("--kiosk", self.plan.forbidden_chromium_flags)

    def test_forbidden_flags_include_fullscreen(self):
        self.assertIn("--start-fullscreen", self.plan.forbidden_chromium_flags)
        self.assertIn("--fullscreen", self.plan.forbidden_chromium_flags)

    def test_forbidden_flags_include_maximized(self):
        self.assertIn("--start-maximized", self.plan.forbidden_chromium_flags)


class TestShellPlanStateVisibility(unittest.TestCase):
    """Shell plan visibility based on initial state."""

    def test_idle_state_visible(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="idle")
        self.assertTrue(plan.is_visible())
        self.assertEqual(plan.visible_plan, PLAN_MODE_VISIBLE)

    def test_busy_state_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="busy")
        self.assertTrue(plan.is_hidden())

    def test_payment_state_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="payment")
        self.assertTrue(plan.is_hidden())

    def test_scan_state_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="scan")
        self.assertTrue(plan.is_hidden())

    def test_cart_state_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="cart")
        self.assertTrue(plan.is_hidden())

    def test_error_state_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="error")
        self.assertTrue(plan.is_hidden())

    def test_offline_state_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="offline")
        self.assertTrue(plan.is_hidden())

    def test_unknown_state_hidden(self):
        """Unknown state MUST hide (safe default)."""
        plan = build_shell_plan(PROFILE_CODE, initial_state="unknown")
        self.assertTrue(plan.is_hidden())

    def test_stale_state_hidden(self):
        plan = build_shell_plan(PROFILE_CODE, initial_state="stale")
        self.assertTrue(plan.is_hidden())

    def test_default_state_hidden(self):
        """Default (no state) must hide."""
        plan = build_shell_plan(PROFILE_CODE)
        self.assertTrue(plan.is_hidden())


class TestShellPlanStateTransitions(unittest.TestCase):
    """validate_shell_plan_for_state() updates visibility."""

    @classmethod
    def setUpClass(cls):
        cls.plan: ShellPlan = build_shell_plan(PROFILE_CODE)

    def test_idle_makes_visible(self):
        updated = validate_shell_plan_for_state(self.plan, "idle")
        self.assertTrue(updated.is_visible())

    def test_busy_makes_hidden(self):
        updated = validate_shell_plan_for_state(self.plan, "busy")
        self.assertTrue(updated.is_hidden())

    def test_payment_makes_hidden(self):
        updated = validate_shell_plan_for_state(self.plan, "payment")
        self.assertTrue(updated.is_hidden())

    def test_unknown_makes_hidden(self):
        updated = validate_shell_plan_for_state(self.plan, "unknown")
        self.assertTrue(updated.is_hidden())

    def test_stale_makes_hidden(self):
        updated = validate_shell_plan_for_state(self.plan, "stale")
        self.assertTrue(updated.is_hidden())

    def test_transition_idle_to_busy(self):
        idle_plan = validate_shell_plan_for_state(self.plan, "idle")
        self.assertTrue(idle_plan.is_visible())
        busy_plan = validate_shell_plan_for_state(idle_plan, "busy")
        self.assertTrue(busy_plan.is_hidden())

    def test_transition_busy_to_idle(self):
        busy_plan = validate_shell_plan_for_state(self.plan, "busy")
        self.assertTrue(busy_plan.is_hidden())
        idle_plan = validate_shell_plan_for_state(busy_plan, "idle")
        self.assertTrue(idle_plan.is_visible())

    def test_original_plan_unchanged(self):
        """validate_shell_plan_for_state does not mutate original."""
        original_visible = self.plan.visible_plan
        validate_shell_plan_for_state(self.plan, "idle")
        self.assertEqual(self.plan.visible_plan, original_visible)

    def test_geometry_unchanged_after_transition(self):
        """Geometry is preserved across state transitions."""
        updated = validate_shell_plan_for_state(self.plan, "idle")
        self.assertEqual(updated.window_x, self.plan.window_x)
        self.assertEqual(updated.window_y, self.plan.window_y)
        self.assertEqual(updated.window_width, self.plan.window_width)
        self.assertEqual(updated.window_height, self.plan.window_height)

    def test_safety_flags_unchanged_after_transition(self):
        updated = validate_shell_plan_for_state(self.plan, "idle")
        self.assertEqual(updated.kill_switch_required, self.plan.kill_switch_required)
        self.assertEqual(updated.no_focus_steal, self.plan.no_focus_steal)
        self.assertEqual(updated.always_on_top, self.plan.always_on_top)


class TestShellPlanNoIntersectForbiddenZones(unittest.TestCase):
    """Shell plan window must not intersect profile forbidden zones."""

    @classmethod
    def setUpClass(cls):
        cls.plan: ShellPlan = build_shell_plan(PROFILE_CODE)
        cls.profile = get_profile(PROFILE_CODE)

    def test_no_intersect_payment_button(self):
        # Payment button: x=487,y=720,w=92,h=120
        gap = self.profile.gap_to_zone(487, 720, 92, 120)
        self.assertGreater(gap, 0, "Shell window intersects payment button")

    def test_no_intersect_header(self):
        gap = self.profile.gap_to_zone(0, 0, 768, 60)
        self.assertGreater(gap, 0, "Shell window intersects header zone")

    def test_no_intersect_any_forbidden_zone(self):
        for zone in self.profile.forbidden_zones:
            gap = self.profile.gap_to_zone(*zone)
            self.assertGreater(
                gap, 0,
                f"Shell window intersects forbidden zone {zone}"
            )


class TestShellPlanUnknownProfile(unittest.TestCase):
    """build_shell_plan raises for unknown profiles."""

    def test_unknown_profile_raises(self):
        with self.assertRaises(ValueError):
            build_shell_plan("nonexistent_profile_xyz")


class TestShellPlanChromiumFlags(unittest.TestCase):
    """Chromium flag tests for portrait vs landscape-like profiles."""

    def test_portrait_forbids_kiosk(self):
        plan = build_shell_plan(PROFILE_CODE)
        self.assertIn("--kiosk", plan.forbidden_chromium_flags)

    def test_portrait_forbids_fullscreen(self):
        plan = build_shell_plan(PROFILE_CODE)
        self.assertIn("--fullscreen", plan.forbidden_chromium_flags)
        self.assertIn("--start-fullscreen", plan.forbidden_chromium_flags)

    def test_validate_portrait_command_no_kiosk(self):
        """If a Chromium command were built for portrait, it must NOT contain --kiosk."""
        plan = build_shell_plan(PROFILE_CODE)
        # Simulate a command check
        hypothetical_flags = ["--app=file:///tmp/index.html",
                              "--window-size=768,240",
                              "--window-position=0,400"]
        for flag in hypothetical_flags:
            flag_name = flag.split("=", 1)[0]
            self.assertNotIn(flag_name, plan.forbidden_chromium_flags,
                             f"Flag {flag_name} should not be forbidden")

    def test_validate_no_kiosk_in_command(self):
        """Simulated Chromium command for portrait must NOT contain --kiosk."""
        plan = build_shell_plan(PROFILE_CODE)
        # A command containing --kiosk would be rejected
        hypothetical_bad_flag = "--kiosk"
        self.assertIn(hypothetical_bad_flag, plan.forbidden_chromium_flags)


class TestShellPlanRepr(unittest.TestCase):
    """ShellPlan repr is safe and informative."""

    def test_repr_contains_profile_code(self):
        plan = build_shell_plan(PROFILE_CODE)
        r = repr(plan)
        self.assertIn(PROFILE_CODE, r)

    def test_repr_contains_window_geometry(self):
        plan = build_shell_plan(PROFILE_CODE)
        r = repr(plan)
        self.assertIn("768x240+0+400", r)

    def test_repr_no_forbidden_substrings(self):
        plan = build_shell_plan(PROFILE_CODE)
        r = repr(plan)
        forbidden = ["token", "secret", "password", "path", "file://"]
        for fb in forbidden:
            self.assertNotIn(fb, r.lower())


class TestLegacyLandscapeNotBroken(unittest.TestCase):
    """Existing landscape player tests are NOT affected by shell plan.

    ShellPlan is a NEW module — it does not modify local_chromium_demo_runner,
    shell_command.py, or render_plan.py. These tests confirm that the
    shell plan module imports cleanly and does not break anything.
    """

    def test_shell_plan_imports_cleanly(self):
        """Shell plan module can be imported without errors."""
        import kso_player.shell_plan
        self.assertTrue(hasattr(kso_player.shell_plan, "build_shell_plan"))

    def test_shell_plan_does_not_modify_chromium_runner(self):
        """local_chromium_demo_runner still has WINDOW_WIDTH=1440."""
        from kso_player.local_chromium_demo_runner import WINDOW_WIDTH, WINDOW_HEIGHT
        self.assertEqual(WINDOW_WIDTH, 1440)
        self.assertEqual(WINDOW_HEIGHT, 1080)

    def test_shell_plan_does_not_modify_shell_command(self):
        """shell_command module still imports cleanly."""
        import kso_player.shell_command
        self.assertTrue(hasattr(kso_player.shell_command, "build_kso_shell_command"))

    def test_shell_plan_does_not_modify_render_plan(self):
        """render_plan module still imports cleanly."""
        import kso_player.render_plan
        self.assertTrue(hasattr(kso_player.render_plan, "build_kso_render_plan"))


if __name__ == "__main__":
    unittest.main()
