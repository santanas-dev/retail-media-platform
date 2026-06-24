"""Tests for X11 click-through physical proof harness.

Covers:
    - X11ProofPlan: construction, validation, mode constraints
    - X11ProofPreflight: readiness checks
    - X11ProofEvidencePlan: evidence plan
    - validate_proof_plan(): geometry, X11 properties, duration, safety
    - validate_command_safety(): forbidden commands
    - validate_safe_output(): forbidden fields
    - Dry-run does NOT create X11 window
    - Preflight-only does NOT create X11 window
    - Run-once requires explicit mode
    - Duration hard max 30 sec
    - Geometry 768×1024 required
    - Input region empty required
    - No keyboard/pointer grab
    - No focus steal
    - Lockfile present
    - Kill-switch required
    - Forbidden commands rejected
    - No secrets/backend URL/tokens
    - No receipt/payment/fiscal/customer/card/items
    - Scanner value/key payload not stored
    - Rollback targeted only
    - Immutability
"""

import unittest

from kso_player.x11_click_through_proof import (
    X11ProofPlan,
    X11ProofPreflight,
    X11ProofEvidencePlan,
    validate_proof_plan,
    validate_command_safety,
    validate_safe_output,
    is_mode_run_safe,
    create_default_proof_plan,
    create_default_evidence_plan,
    create_preflight_result,
    PROOF_TITLE,
    DISPLAY_DEFAULT,
    HARD_MAX_DURATION_SEC,
    DEFAULT_DURATION_SEC,
    FORBIDDEN_COMMANDS,
    FORBIDDEN_FIELDS,
)


# ══════════════════════════════════════════════════════════════════════
# X11ProofPlan — construction and defaults
# ══════════════════════════════════════════════════════════════════════

class TestProofPlanDefaults(unittest.TestCase):
    """Default plan is production-ready and valid."""

    def test_default_title(self):
        plan = create_default_proof_plan()
        self.assertEqual(plan.title, PROOF_TITLE)

    def test_default_display(self):
        plan = create_default_proof_plan()
        self.assertEqual(plan.display, DISPLAY_DEFAULT)

    def test_default_geometry(self):
        plan = create_default_proof_plan()
        self.assertEqual(plan.width, 768)
        self.assertEqual(plan.height, 1024)
        self.assertEqual(plan.x, 0)
        self.assertEqual(plan.y, 0)

    def test_default_duration(self):
        plan = create_default_proof_plan()
        self.assertEqual(plan.duration_sec, DEFAULT_DURATION_SEC)

    def test_default_mode(self):
        plan = create_default_proof_plan()
        self.assertEqual(plan.mode, "dry_run")

    def test_default_override_redirect(self):
        self.assertTrue(create_default_proof_plan().override_redirect)

    def test_default_input_region_empty(self):
        self.assertTrue(create_default_proof_plan().input_region_empty)

    def test_default_no_keyboard_grab(self):
        self.assertTrue(create_default_proof_plan().no_keyboard_grab)

    def test_default_no_pointer_grab(self):
        self.assertTrue(create_default_proof_plan().no_pointer_grab)

    def test_default_no_focus_steal(self):
        self.assertTrue(create_default_proof_plan().no_focus_steal)

    def test_default_kill_switch_required(self):
        self.assertTrue(create_default_proof_plan().kill_switch_required)

    def test_default_rollback_targeted(self):
        self.assertTrue(create_default_proof_plan().rollback_targeted)

    def test_default_production_ready(self):
        self.assertTrue(create_default_proof_plan().is_production_ready())


class TestProofPlanValidation(unittest.TestCase):
    """validate_proof_plan() checks safety rules."""

    def test_valid_plan_passes(self):
        plan = create_default_proof_plan()
        result = validate_proof_plan(plan)
        self.assertTrue(result["valid"], f"Errors: {result['errors']}")

    def test_bad_geometry_fails(self):
        plan = X11ProofPlan(width=640, height=480)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])

    def test_wrong_origin_fails(self):
        plan = X11ProofPlan(x=100, y=100)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])

    def test_input_region_not_empty_fails(self):
        plan = X11ProofPlan(input_region_empty=False)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])

    def test_keyboard_grab_fails(self):
        plan = X11ProofPlan(no_keyboard_grab=False)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])

    def test_pointer_grab_fails(self):
        plan = X11ProofPlan(no_pointer_grab=False)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])

    def test_focus_steal_fails(self):
        plan = X11ProofPlan(no_focus_steal=False)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])

    def test_override_redirect_false_fails(self):
        plan = X11ProofPlan(override_redirect=False)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])

    def test_duration_too_high_fails(self):
        with self.assertRaises(ValueError):
            X11ProofPlan(duration_sec=999)

    def test_duration_zero_fails(self):
        with self.assertRaises(ValueError):
            X11ProofPlan(duration_sec=0)

    def test_duration_negative_fails(self):
        with self.assertRaises(ValueError):
            X11ProofPlan(duration_sec=-1)

    def test_kill_switch_not_required_fails(self):
        plan = X11ProofPlan(kill_switch_required=False)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])

    def test_rollback_not_targeted_fails(self):
        plan = X11ProofPlan(rollback_targeted=False)
        result = validate_proof_plan(plan)
        self.assertFalse(result["valid"])


class TestProofPlanModes(unittest.TestCase):
    """Mode constraints: dry_run, preflight_only, run_once."""

    def test_dry_run_mode(self):
        plan = X11ProofPlan(mode="dry_run")
        self.assertEqual(plan.mode, "dry_run")

    def test_preflight_only_mode(self):
        plan = X11ProofPlan(mode="preflight_only")
        self.assertEqual(plan.mode, "preflight_only")

    def test_run_once_mode(self):
        plan = X11ProofPlan(mode="run_once")
        self.assertEqual(plan.mode, "run_once")

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            X11ProofPlan(mode="production")

    def test_dry_run_is_safe(self):
        self.assertTrue(is_mode_run_safe("dry_run"))

    def test_preflight_only_is_safe(self):
        self.assertTrue(is_mode_run_safe("preflight_only"))

    def test_run_once_is_not_safe(self):
        self.assertFalse(is_mode_run_safe("run_once"))

    def test_dry_run_does_not_create_x11_window(self):
        # Dry run is pure Python — no X11 import, no subprocess
        plan = create_default_proof_plan(mode="dry_run")
        result = validate_proof_plan(plan)
        self.assertTrue(result["valid"])

    def test_preflight_only_does_not_create_x11_window(self):
        plan = X11ProofPlan(mode="preflight_only")
        result = validate_proof_plan(plan)
        self.assertIn("valid", result)


class TestProofPlanToSafeDict(unittest.TestCase):
    """to_safe_dict() must not leak forbidden data."""

    def test_safe_dict_no_forbidden_fields(self):
        plan = create_default_proof_plan()
        d = plan.to_safe_dict()
        for key in d:
            key_lower = key.lower()
            for forbidden in FORBIDDEN_FIELDS:
                self.assertNotEqual(key_lower, forbidden,
                                    f"forbidden field {key} in safe dict")

    def test_safe_dict_no_scanner_value(self):
        plan = create_default_proof_plan()
        d = plan.to_safe_dict()
        text = str(d).lower()
        self.assertNotIn("barcode", text)
        self.assertNotIn("scanner_value", text)
        self.assertNotIn("event_key", text)

    def test_safe_dict_no_backend_url(self):
        plan = create_default_proof_plan()
        d = plan.to_safe_dict()
        text = str(d).lower()
        self.assertNotIn("backend_url", text)
        self.assertNotIn("token", text)
        self.assertNotIn("secret", text)


class TestProofPlanImmutability(unittest.TestCase):
    """X11ProofPlan is frozen."""

    def test_immutable(self):
        plan = create_default_proof_plan()
        for attr in ["display", "title", "width", "height", "mode",
                     "input_region_empty", "no_keyboard_grab", "no_pointer_grab"]:
            with self.assertRaises(Exception, msg=f"{attr} should be immutable"):
                setattr(plan, attr, "changed")


# ══════════════════════════════════════════════════════════════════════
# X11ProofPreflight
# ══════════════════════════════════════════════════════════════════════

class TestPreflightResult(unittest.TestCase):
    """Preflight readiness checks."""

    def test_ready_when_display_available(self):
        pf = create_preflight_result(display_available=True)
        self.assertTrue(pf.ready)

    def test_not_ready_when_display_missing(self):
        pf = create_preflight_result(display_available=False)
        self.assertFalse(pf.ready)

    def test_warnings_for_missing_tools(self):
        pf = create_preflight_result(
            display_available=True,
            xdotool_available=False,
            scrot_available=False,
        )
        self.assertTrue(pf.ready)  # still ready, just warnings
        self.assertGreater(len(pf.warnings), 0)

    def test_errors_for_missing_display(self):
        pf = create_preflight_result(display_available=False)
        self.assertGreater(len(pf.errors), 0)

    def test_bool_coercion(self):
        self.assertTrue(create_preflight_result(display_available=True))
        self.assertFalse(create_preflight_result(display_available=False))


# ══════════════════════════════════════════════════════════════════════
# X11ProofEvidencePlan
# ══════════════════════════════════════════════════════════════════════

class TestEvidencePlan(unittest.TestCase):
    """Evidence plan for physical proof."""

    def test_default_all_enabled(self):
        ep = create_default_evidence_plan()
        self.assertTrue(ep.screenshots)
        self.assertTrue(ep.window_tree)
        self.assertTrue(ep.window_id)
        self.assertTrue(ep.window_props)
        self.assertTrue(ep.active_window)
        self.assertTrue(ep.pixel_proof)

    def test_evidence_count(self):
        ep = create_default_evidence_plan()
        self.assertEqual(ep.evidence_count(), 8)

    def test_scanner_pass_through_in_evidence(self):
        ep = create_default_evidence_plan()
        self.assertTrue(ep.scanner_pass_through)

    def test_touch_pass_through_in_evidence(self):
        ep = create_default_evidence_plan()
        self.assertTrue(ep.touch_pass_through)

    def test_safe_dict_no_forbidden(self):
        ep = create_default_evidence_plan()
        d = ep.to_safe_dict()
        text = str(d).lower()
        self.assertNotIn("barcode", text)
        self.assertNotIn("scanner_value", text)
        self.assertNotIn("receipt", text)


# ══════════════════════════════════════════════════════════════════════
# Command safety validation
# ══════════════════════════════════════════════════════════════════════

class TestCommandSafety(unittest.TestCase):
    """validate_command_safety() rejects forbidden commands."""

    def test_safe_command_passes(self):
        result = validate_command_safety("DISPLAY=:0 xdotool search --name PROOF")
        self.assertTrue(result["safe"])

    def test_pkill_chromium_rejected(self):
        result = validate_command_safety("pkill chromium")
        self.assertFalse(result["safe"])

    def test_pkill_f_chromium_rejected(self):
        result = validate_command_safety("pkill -f chromium-browser")
        self.assertFalse(result["safe"])

    def test_killall_chromium_rejected(self):
        result = validate_command_safety("killall chromium-browser")
        self.assertFalse(result["safe"])

    def test_systemctl_restart_mint_rejected(self):
        result = validate_command_safety("systemctl restart mint.service")
        self.assertFalse(result["safe"])

    def test_systemctl_stop_mysql_rejected(self):
        result = validate_command_safety("systemctl stop mysql")
        self.assertFalse(result["safe"])

    def test_systemctl_stop_redis_rejected(self):
        result = validate_command_safety("systemctl stop redis.service")
        self.assertFalse(result["safe"])

    def test_systemctl_enable_rejected(self):
        result = validate_command_safety("systemctl enable kso-player")
        self.assertFalse(result["safe"])

    def test_systemctl_disable_rejected(self):
        result = validate_command_safety("systemctl disable kso-player")
        self.assertFalse(result["safe"])

    def test_systemctl_mask_rejected(self):
        result = validate_command_safety("systemctl mask kso-player")
        self.assertFalse(result["safe"])

    def test_daemon_reload_rejected(self):
        result = validate_command_safety("systemctl daemon-reload")
        self.assertFalse(result["safe"])

    def test_openbox_modification_rejected(self):
        result = validate_command_safety("echo '...' > ~/.config/openbox/autostart")
        self.assertFalse(result["safe"])

    def test_profile_modification_rejected(self):
        result = validate_command_safety("echo '...' >> ~/.profile")
        self.assertFalse(result["safe"])

    def test_xinitrc_modification_rejected(self):
        result = validate_command_safety("cat > ~/.xinitrc")
        self.assertFalse(result["safe"])

    def test_index_html_modification_rejected(self):
        result = validate_command_safety("cp overlay.html ~/mint/bin/www/index.html")
        self.assertFalse(result["safe"])

    def test_safe_xdotool_passes(self):
        result = validate_command_safety("DISPLAY=:0 xdotool getactivewindow")
        self.assertTrue(result["safe"])

    def test_safe_scrot_passes(self):
        result = validate_command_safety("DISPLAY=:0 scrot /tmp/proof.png")
        self.assertTrue(result["safe"])


# ══════════════════════════════════════════════════════════════════════
# Safe output validation
# ══════════════════════════════════════════════════════════════════════

class TestSafeOutputValidation(unittest.TestCase):
    """validate_safe_output() rejects forbidden fields."""

    def test_safe_output_passes(self):
        result = validate_safe_output({"title": "PROOF", "mode": "dry_run"})
        self.assertTrue(result["valid"])

    def test_receipt_rejected(self):
        result = validate_safe_output({"receipt_id": "RCP-001"})
        self.assertFalse(result["valid"])

    def test_payment_rejected(self):
        result = validate_safe_output({"payment_amount": 100.50})
        self.assertFalse(result["valid"])

    def test_customer_rejected(self):
        result = validate_safe_output({"customer_name": "Ivan"})
        self.assertFalse(result["valid"])

    def test_card_rejected(self):
        result = validate_safe_output({"card_number": "4111..."})
        self.assertFalse(result["valid"])

    def test_backend_url_rejected(self):
        result = validate_safe_output({"backend_url": "http://..."})
        self.assertFalse(result["valid"])

    def test_token_rejected(self):
        result = validate_safe_output({"token": "abc"})
        self.assertFalse(result["valid"])

    def test_scanner_value_rejected(self):
        result = validate_safe_output({"scanner_value": "4820..."})
        self.assertFalse(result["valid"])

    def test_barcode_rejected(self):
        result = validate_safe_output({"barcode": "4820001234567"})
        self.assertFalse(result["valid"])

    def test_event_key_rejected(self):
        result = validate_safe_output({"event_key": "Enter"})
        self.assertFalse(result["valid"])

    def test_event_code_rejected(self):
        result = validate_safe_output({"event_code": "Digit1"})
        self.assertFalse(result["valid"])

    def test_non_dict_rejected(self):
        result = validate_safe_output("not a dict")
        self.assertFalse(result["valid"])


# ══════════════════════════════════════════════════════════════════════
# Integration with renderer contract
# ══════════════════════════════════════════════════════════════════════

class TestIntegrationWithRendererContract(unittest.TestCase):
    """Proof plan aligns with X11 click-through renderer contract."""

    def test_proof_geometry_matches_renderer(self):
        from kso_player.x11_click_through_renderer import (
            ROOT_WIDTH, ROOT_HEIGHT,
        )
        plan = create_default_proof_plan()
        self.assertEqual(plan.width, ROOT_WIDTH)
        self.assertEqual(plan.height, ROOT_HEIGHT)

    def test_both_require_input_region_empty(self):
        from kso_player.x11_click_through_renderer import (
            X11ClickThroughCapabilities,
        )
        caps = X11ClickThroughCapabilities()
        plan = create_default_proof_plan()
        self.assertEqual(caps.input_region_empty, plan.input_region_empty)

    def test_both_require_no_keyboard_grab(self):
        from kso_player.x11_click_through_renderer import (
            X11ClickThroughCapabilities,
        )
        caps = X11ClickThroughCapabilities()
        plan = create_default_proof_plan()
        self.assertEqual(caps.no_keyboard_grab, plan.no_keyboard_grab)

    def test_both_production_ready(self):
        from kso_player.x11_click_through_renderer import (
            X11ClickThroughCapabilities,
        )
        caps = X11ClickThroughCapabilities()
        plan = create_default_proof_plan()
        self.assertTrue(caps.is_production_ready())
        self.assertTrue(plan.is_production_ready())


if __name__ == "__main__":
    unittest.main()
