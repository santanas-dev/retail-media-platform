"""Tests for X11 click-through renderer contract.

Covers:
    - X11ClickThroughCapabilities: defaults, production_ready conditions
    - X11RendererPlan: construction, validation, safe output
    - X11RendererValidationResult: valid/invalid states
    - Geometry: 768×1024 required
    - Input pass-through: empty region, no grabs, no focus steal
    - Override-redirect required
    - Hide SLA enforcement
    - Forbidden fields in output
    - No backend URL/token/secrets in output
    - Production-ready: true only if all pass-through enabled
    - Wake-only plan: NOT production-ready
    - Immutability of all dataclasses
    - Legacy Zone C profile not affected
"""

import unittest

from kso_player.x11_click_through_renderer import (
    X11ClickThroughCapabilities,
    X11RendererPlan,
    X11RendererValidationResult,
    validate_renderer_plan,
    validate_safe_output,
    create_default_renderer_plan,
    create_wake_only_renderer_plan,
    RENDERER_TYPE,
    ROOT_WIDTH,
    ROOT_HEIGHT,
    FORBIDDEN_FIELDS,
)


# ══════════════════════════════════════════════════════════════════════
# Capabilities
# ══════════════════════════════════════════════════════════════════════

class TestCapabilitiesDefaults(unittest.TestCase):
    """Default capabilities must be production-ready."""

    def test_default_renderer_type(self):
        c = X11ClickThroughCapabilities()
        self.assertEqual(c.renderer_type, RENDERER_TYPE)

    def test_default_geometry(self):
        c = X11ClickThroughCapabilities()
        self.assertEqual(c.root_width, 768)
        self.assertEqual(c.root_height, 1024)
        self.assertEqual(c.window_x, 0)
        self.assertEqual(c.window_y, 0)
        self.assertEqual(c.window_width, 768)
        self.assertEqual(c.window_height, 1024)

    def test_default_override_redirect(self):
        self.assertTrue(X11ClickThroughCapabilities().override_redirect)

    def test_default_always_on_top(self):
        self.assertTrue(X11ClickThroughCapabilities().always_on_top)

    def test_default_input_region_empty(self):
        self.assertTrue(X11ClickThroughCapabilities().input_region_empty)

    def test_default_no_focus_steal(self):
        self.assertTrue(X11ClickThroughCapabilities().no_focus_steal)

    def test_default_no_keyboard_grab(self):
        self.assertTrue(X11ClickThroughCapabilities().no_keyboard_grab)

    def test_default_no_pointer_grab(self):
        self.assertTrue(X11ClickThroughCapabilities().no_pointer_grab)

    def test_default_hide_sla(self):
        c = X11ClickThroughCapabilities()
        self.assertEqual(c.hide_sla_ms, 500)
        self.assertEqual(c.target_hide_ms, 200)

    def test_default_kill_switch_required(self):
        self.assertTrue(X11ClickThroughCapabilities().kill_switch_required)

    def test_default_state_only_visibility(self):
        self.assertTrue(X11ClickThroughCapabilities().state_only_visibility_required)

    def test_default_no_chromium(self):
        self.assertTrue(X11ClickThroughCapabilities().no_chromium)

    def test_default_no_ukm5_db(self):
        self.assertTrue(X11ClickThroughCapabilities().no_ukm5_db)

    def test_default_scanner_loss_free(self):
        self.assertTrue(X11ClickThroughCapabilities().scanner_loss_free)

    def test_default_touch_loss_free(self):
        self.assertTrue(X11ClickThroughCapabilities().touch_loss_free)

    def test_default_keyboard_loss_free(self):
        self.assertTrue(X11ClickThroughCapabilities().keyboard_loss_free)


class TestCapabilitiesProductionReady(unittest.TestCase):
    """Production-ready requires all pass-through properties enabled."""

    def test_default_is_production_ready(self):
        self.assertTrue(X11ClickThroughCapabilities().is_production_ready())

    def test_not_ready_if_input_region_not_empty(self):
        c = X11ClickThroughCapabilities(input_region_empty=False)
        self.assertFalse(c.is_production_ready())

    def test_not_ready_if_keyboard_grab(self):
        c = X11ClickThroughCapabilities(no_keyboard_grab=False)
        self.assertFalse(c.is_production_ready())

    def test_not_ready_if_pointer_grab(self):
        c = X11ClickThroughCapabilities(no_pointer_grab=False)
        self.assertFalse(c.is_production_ready())

    def test_not_ready_if_focus_steal(self):
        c = X11ClickThroughCapabilities(no_focus_steal=False)
        self.assertFalse(c.is_production_ready())

    def test_not_ready_if_override_redirect_false(self):
        c = X11ClickThroughCapabilities(override_redirect=False)
        self.assertFalse(c.is_production_ready())

    def test_not_ready_if_scanner_loss(self):
        c = X11ClickThroughCapabilities(scanner_loss_free=False)
        self.assertFalse(c.is_production_ready())

    def test_not_ready_if_touch_loss(self):
        c = X11ClickThroughCapabilities(touch_loss_free=False)
        self.assertFalse(c.is_production_ready())

    def test_ready_if_all_properties_correct(self):
        c = X11ClickThroughCapabilities(
            input_region_empty=True,
            no_keyboard_grab=True,
            no_pointer_grab=True,
            no_focus_steal=True,
            override_redirect=True,
            scanner_loss_free=True,
            touch_loss_free=True,
        )
        self.assertTrue(c.is_production_ready())


class TestCapabilitiesImmutability(unittest.TestCase):
    """X11ClickThroughCapabilities is frozen."""

    def test_cannot_mutate(self):
        c = X11ClickThroughCapabilities()
        with self.assertRaises(Exception):
            c.input_region_empty = False


# ══════════════════════════════════════════════════════════════════════
# Renderer Plan
# ══════════════════════════════════════════════════════════════════════

class TestRendererPlanDefaults(unittest.TestCase):
    """Default renderer plan is valid and production-ready."""

    def test_default_plan_valid(self):
        plan = create_default_renderer_plan()
        self.assertEqual(plan.display, ":0")
        self.assertFalse(plan.validated)

    def test_plan_immutable(self):
        plan = create_default_renderer_plan()
        with self.assertRaises(Exception):
            plan.display = ":1"

    def test_plan_no_display_raises(self):
        with self.assertRaises(ValueError):
            X11RendererPlan(display="")

    def test_plan_to_safe_dict(self):
        plan = create_default_renderer_plan()
        d = plan.to_safe_dict()
        self.assertIsInstance(d, dict)
        self.assertIn("renderer_type", d)
        self.assertIn("production_ready", d)
        self.assertTrue(d["production_ready"])

    def test_safe_dict_no_forbidden_fields(self):
        plan = create_default_renderer_plan()
        d = plan.to_safe_dict()
        for key in d:
            self.assertNotIn(key.lower(), FORBIDDEN_FIELDS,
                             f"forbidden field {key} in safe dict")
        for key in d:
            key_lower = key.lower()
            for forbidden in ["receipt", "payment", "fiscal", "customer",
                              "token", "secret", "api_key", "backend_url"]:
                self.assertNotIn(forbidden, key_lower,
                                 f"forbidden-like field {key} in safe dict")

    def test_safe_dict_no_scanner_values(self):
        plan = create_default_renderer_plan()
        d = plan.to_safe_dict()
        text = str(d).lower()
        self.assertNotIn("barcode", text)
        self.assertNotIn("scanner_value", text)
        self.assertNotIn("event_key", text)


class TestRendererPlanValidation(unittest.TestCase):
    """validate_renderer_plan() checks all production requirements."""

    def test_default_plan_validates(self):
        plan = create_default_renderer_plan()
        result = validate_renderer_plan(plan)
        self.assertTrue(result.valid)
        self.assertTrue(result.production_ready)
        self.assertEqual(len(result.errors), 0)

    def test_invalid_geometry_fails(self):
        caps = X11ClickThroughCapabilities(root_width=640, root_height=480,
                                           window_width=640, window_height=480)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("768" in e for e in result.errors))

    def test_input_region_not_empty_fails(self):
        caps = X11ClickThroughCapabilities(input_region_empty=False)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("input_region" in e for e in result.errors))

    def test_keyboard_grab_fails(self):
        caps = X11ClickThroughCapabilities(no_keyboard_grab=False)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("keyboard grab" in e.lower() for e in result.errors))

    def test_pointer_grab_fails(self):
        caps = X11ClickThroughCapabilities(no_pointer_grab=False)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("pointer grab" in e.lower() for e in result.errors))

    def test_focus_steal_fails(self):
        caps = X11ClickThroughCapabilities(no_focus_steal=False)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("focus stealing" in e.lower() for e in result.errors))

    def test_override_redirect_false_fails(self):
        caps = X11ClickThroughCapabilities(override_redirect=False)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("override_redirect" in e for e in result.errors))

    def test_kill_switch_not_required_fails(self):
        caps = X11ClickThroughCapabilities(kill_switch_required=False)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("kill_switch" in e for e in result.errors))

    def test_chromium_not_allowed(self):
        caps = X11ClickThroughCapabilities(no_chromium=False)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("Chromium" in e for e in result.errors))

    def test_ukm5_db_not_allowed(self):
        caps = X11ClickThroughCapabilities(no_ukm5_db=False)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("UKM5 DB" in e for e in result.errors))

    def test_hide_sla_too_high(self):
        caps = X11ClickThroughCapabilities(hide_sla_ms=600)
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("hide_sla" in e for e in result.errors))


class TestWakeOnlyPlan(unittest.TestCase):
    """Wake-only plan is NOT production-ready."""

    def test_wake_only_not_production_ready(self):
        plan = create_wake_only_renderer_plan()
        self.assertFalse(plan.capabilities.is_production_ready())

    def test_wake_only_fails_validation(self):
        plan = create_wake_only_renderer_plan()
        result = validate_renderer_plan(plan)
        self.assertFalse(result.valid)
        self.assertFalse(result.production_ready)
        # Should have multiple errors
        self.assertGreater(len(result.errors), 0)


class TestRendererPlanNotProductionReady(unittest.TestCase):
    """Edge cases where production_ready should be false."""

    def test_no_pass_through_not_ready(self):
        caps = X11ClickThroughCapabilities(
            input_region_empty=False,
            no_keyboard_grab=False,
            no_pointer_grab=False,
        )
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.production_ready)

    def test_partial_pass_through_not_ready(self):
        # Only pointer pass-through, keyboard grab still enabled
        caps = X11ClickThroughCapabilities(
            input_region_empty=True,
            no_keyboard_grab=False,  # still grabbing keyboard
            no_pointer_grab=True,
        )
        plan = X11RendererPlan(capabilities=caps, display=":0")
        result = validate_renderer_plan(plan)
        self.assertFalse(result.production_ready)


# ══════════════════════════════════════════════════════════════════════
# Safe output validation
# ══════════════════════════════════════════════════════════════════════

class TestSafeOutputValidation(unittest.TestCase):
    """validate_safe_output rejects forbidden fields."""

    def test_safe_dict_passes(self):
        d = {"renderer_type": "x11_click_through", "geometry": "768x1024"}
        result = validate_safe_output(d)
        self.assertTrue(result.valid)

    def test_receipt_rejected(self):
        result = validate_safe_output({"receipt_id": "RCP-001"})
        self.assertFalse(result.valid)

    def test_payment_rejected(self):
        result = validate_safe_output({"payment_amount": 100.50})
        self.assertFalse(result.valid)

    def test_fiscal_rejected(self):
        result = validate_safe_output({"fiscal_data": "..."})
        self.assertFalse(result.valid)

    def test_customer_rejected(self):
        result = validate_safe_output({"customer_name": "Ivan"})
        self.assertFalse(result.valid)

    def test_card_rejected(self):
        result = validate_safe_output({"card_number": "4111111111111111"})
        self.assertFalse(result.valid)

    def test_items_rejected(self):
        result = validate_safe_output({"items": []})
        self.assertFalse(result.valid)

    def test_backend_url_rejected(self):
        result = validate_safe_output({"backend_url": "http://example.com"})
        self.assertFalse(result.valid)

    def test_token_rejected(self):
        result = validate_safe_output({"token": "abc123"})
        self.assertFalse(result.valid)

    def test_secret_rejected(self):
        result = validate_safe_output({"secret": "xyz"})
        self.assertFalse(result.valid)

    def test_api_key_rejected(self):
        result = validate_safe_output({"api_key": "sk-..."})
        self.assertFalse(result.valid)

    def test_password_rejected(self):
        result = validate_safe_output({"password": "hunter2"})
        self.assertFalse(result.valid)

    def test_jwt_rejected(self):
        result = validate_safe_output({"jwt": "eyJhbGci..."})
        self.assertFalse(result.valid)

    def test_bearer_rejected(self):
        result = validate_safe_output({"bearer": "token"})
        self.assertFalse(result.valid)

    def test_scanner_value_rejected(self):
        result = validate_safe_output({"scanner_value": "4820001234567"})
        self.assertFalse(result.valid)

    def test_barcode_rejected(self):
        result = validate_safe_output({"barcode": "4820001234567"})
        self.assertFalse(result.valid)

    def test_event_key_rejected(self):
        result = validate_safe_output({"event_key": "Enter"})
        self.assertFalse(result.valid)

    def test_event_code_rejected(self):
        result = validate_safe_output({"event_code": "Digit1"})
        self.assertFalse(result.valid)

    def test_event_data_rejected(self):
        result = validate_safe_output({"event_data": "text"})
        self.assertFalse(result.valid)

    def test_non_dict_rejected(self):
        result = validate_safe_output("not a dict")
        self.assertFalse(result.valid)

    def test_empty_dict_passes(self):
        result = validate_safe_output({})
        self.assertTrue(result.valid)


# ══════════════════════════════════════════════════════════════════════
# ValidationResult
# ══════════════════════════════════════════════════════════════════════

class TestValidationResult(unittest.TestCase):
    """X11RendererValidationResult construction and bool coercion."""

    def test_valid_result_true(self):
        r = X11RendererValidationResult(valid=True, production_ready=True)
        self.assertTrue(bool(r))

    def test_invalid_result_false(self):
        r = X11RendererValidationResult(valid=False, production_ready=False)
        self.assertFalse(bool(r))

    def test_valid_not_ready(self):
        r = X11RendererValidationResult(valid=True, production_ready=False)
        self.assertTrue(r.valid)
        self.assertFalse(r.production_ready)

    def test_errors_and_warnings(self):
        r = X11RendererValidationResult(
            valid=False, production_ready=False,
            errors=("err1", "err2"), warnings=("warn1",),
        )
        self.assertEqual(len(r.errors), 2)
        self.assertEqual(len(r.warnings), 1)


# ══════════════════════════════════════════════════════════════════════
# Immutability
# ══════════════════════════════════════════════════════════════════════

class TestImmutability(unittest.TestCase):
    """All dataclasses are frozen."""

    def test_capabilities_immutable(self):
        c = X11ClickThroughCapabilities()
        for attr in ["input_region_empty", "no_keyboard_grab", "no_pointer_grab",
                     "no_focus_steal", "override_redirect", "scanner_loss_free"]:
            with self.assertRaises(Exception, msg=f"{attr} should be immutable"):
                setattr(c, attr, False)

    def test_plan_immutable(self):
        plan = create_default_renderer_plan()
        with self.assertRaises(Exception):
            plan.display = ":1"
        with self.assertRaises(Exception):
            plan.validated = True

    def test_validation_result_immutable(self):
        r = X11RendererValidationResult(valid=True, production_ready=True)
        with self.assertRaises(Exception):
            r.valid = False


# ══════════════════════════════════════════════════════════════════════
# Fullscreen profile relationship
# ══════════════════════════════════════════════════════════════════════

class TestFullscreenProfileRelationship(unittest.TestCase):
    """Renderer contract aligns with fullscreen idle screensaver profile."""

    def test_renderer_geometry_matches_profile(self):
        from kso_player.profiles.portrait_fullscreen_idle_screensaver_768 import (
            ROOT_WIDTH as PROFILE_W,
            ROOT_HEIGHT as PROFILE_H,
        )
        self.assertEqual(X11ClickThroughCapabilities().root_width, PROFILE_W)
        self.assertEqual(X11ClickThroughCapabilities().root_height, PROFILE_H)

    def test_profile_not_production_ready_default(self):
        from kso_player.profiles.portrait_fullscreen_idle_screensaver_768 import (
            is_production_ready,
        )
        # Profile defaults to wake_only — NOT production-ready
        self.assertFalse(is_production_ready())

    def test_renderer_is_production_ready(self):
        self.assertTrue(X11ClickThroughCapabilities().is_production_ready())

    def test_fullscreen_profile_input_mode_match(self):
        from kso_player.profiles.portrait_fullscreen_idle_screensaver_768 import (
            INPUT_MODE, PRODUCTION_READY_MODES,
        )
        # Current profile input_mode is wake_only (not ready)
        self.assertEqual(INPUT_MODE, "wake_only")
        # But PRODUCTION_READY_MODES includes x11_click_through
        self.assertIn("x11_click_through", PRODUCTION_READY_MODES)
        # This renderer type matches that production mode
        self.assertEqual(RENDERER_TYPE, "x11_click_through")


if __name__ == "__main__":
    unittest.main()
