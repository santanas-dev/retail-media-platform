"""Tests for interaction_hide — hide decision logic for fullscreen idle screensaver.

Covers:
    - HideDecision dataclass: immutable, valid reasons, field constraints
    - should_hide(): kill_switch > state > dom_events priority
    - should_hide(): idle + no events → visible
    - should_hide(): every DOM event triggers hide
    - should_hide(): state != idle triggers hide
    - should_hide(): kill_switch overrides state=idle
    - should_hide(): keydown/input → scanner_risk=True
    - should_hide(): touch/pointer/mouse → scanner_risk=False
    - resolve_highest_priority_trigger(): priority ordering
    - resolve_highest_priority_trigger(): unknown events ignored
    - validate_interaction_log(): rejects forbidden fields
    - validate_interaction_log(): accepts safe log entries
    - Immutability of HideDecision
"""

import unittest

from kso_player.interaction_hide import (
    HideDecision,
    should_hide,
    resolve_highest_priority_trigger,
    validate_interaction_log,
    HIDE_TRIGGER_PRIORITY,
    HIDE_TARGET_MS,
    HIDE_TRIGGER_PASSTHROUGH,
    SCANNER_TRIGGERS,
    HIDE_STATES,
)


class TestHideDecisionDataclass(unittest.TestCase):
    """HideDecision: construction, immutability, validation."""

    def test_construction(self):
        d = HideDecision(
            hide=True, reason="keydown", target_ms=200,
            passthrough=False, scanner_risk=True
        )
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "keydown")
        self.assertEqual(d.target_ms, 200)
        self.assertFalse(d.passthrough)
        self.assertTrue(d.scanner_risk)

    def test_no_hide_decision(self):
        d = HideDecision(
            hide=False, reason="none", target_ms=0,
            passthrough=False, scanner_risk=False
        )
        self.assertFalse(d.hide)

    def test_immutable(self):
        d = HideDecision(
            hide=True, reason="touchstart", target_ms=200,
            passthrough=True, scanner_risk=False
        )
        with self.assertRaises(Exception):
            d.hide = False

    def test_invalid_reason_raises(self):
        with self.assertRaises(ValueError):
            HideDecision(
                hide=True, reason="invalid_event", target_ms=200,
                passthrough=False, scanner_risk=False
            )

    def test_negative_target_ms_raises(self):
        with self.assertRaises(ValueError):
            HideDecision(
                hide=True, reason="keydown", target_ms=-1,
                passthrough=False, scanner_risk=False
            )

    def test_all_valid_reasons_accepted(self):
        for reason in ["kill_switch", "state_change", "keydown", "input",
                       "touchstart", "pointerdown", "mousedown", "click",
                       "wheel", "none"]:
            d = HideDecision(
                hide=(reason != "none"), reason=reason, target_ms=200,
                passthrough=False, scanner_risk=False
            )
            self.assertEqual(d.reason, reason)


class TestShouldHideKillSwitch(unittest.TestCase):
    """Kill-switch always wins — highest priority."""

    def test_kill_switch_overrides_idle(self):
        d = should_hide(
            dom_events=frozenset(),
            state="idle",
            kill_switch_active=True,
        )
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "kill_switch")
        self.assertFalse(d.scanner_risk)

    def test_kill_switch_overrides_touch_events(self):
        d = should_hide(
            dom_events=frozenset({"touchstart"}),
            state="idle",
            kill_switch_active=True,
        )
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "kill_switch")

    def test_kill_switch_overrides_busy_state(self):
        d = should_hide(
            dom_events=frozenset(),
            state="busy",
            kill_switch_active=True,
        )
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "kill_switch")

    def test_kill_switch_target_ms(self):
        d = should_hide(kill_switch_active=True)
        self.assertEqual(d.target_ms, HIDE_TARGET_MS["kill_switch"])

    def test_kill_switch_passthrough(self):
        d = should_hide(kill_switch_active=True)
        self.assertFalse(d.passthrough)


class TestShouldHideStateChange(unittest.TestCase):
    """State != idle → hide (second priority after kill-switch)."""

    def test_idle_no_events_visible(self):
        d = should_hide(
            dom_events=frozenset(),
            state="idle",
            kill_switch_active=False,
        )
        self.assertFalse(d.hide)
        self.assertEqual(d.reason, "none")

    def test_busy_hides(self):
        d = should_hide(state="busy")
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "state_change")

    def test_scan_hides(self):
        d = should_hide(state="scan")
        self.assertTrue(d.hide)

    def test_cart_hides(self):
        d = should_hide(state="cart")
        self.assertTrue(d.hide)

    def test_payment_hides(self):
        d = should_hide(state="payment")
        self.assertTrue(d.hide)

    def test_error_hides(self):
        d = should_hide(state="error")
        self.assertTrue(d.hide)

    def test_offline_hides(self):
        d = should_hide(state="offline")
        self.assertTrue(d.hide)

    def test_unknown_hides(self):
        d = should_hide(state="unknown")
        self.assertTrue(d.hide)

    def test_stale_hides(self):
        d = should_hide(state="stale")
        self.assertTrue(d.hide)

    def test_state_change_target_ms(self):
        d = should_hide(state="busy")
        self.assertEqual(d.target_ms, HIDE_TARGET_MS["state_change"])

    def test_state_change_passthrough(self):
        d = should_hide(state="busy")
        self.assertTrue(d.passthrough)

    def test_state_change_scanner_risk_false(self):
        d = should_hide(state="scan")
        self.assertFalse(d.scanner_risk)


class TestShouldHideDOMEvents(unittest.TestCase):
    """DOM events trigger hide when state=idle and kill_switch inactive."""

    def test_touchstart_hides(self):
        d = should_hide(
            dom_events=frozenset({"touchstart"}),
            state="idle",
        )
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "touchstart")
        self.assertFalse(d.scanner_risk)

    def test_pointerdown_hides(self):
        d = should_hide(dom_events=frozenset({"pointerdown"}), state="idle")
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "pointerdown")

    def test_mousedown_hides(self):
        d = should_hide(dom_events=frozenset({"mousedown"}), state="idle")
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "mousedown")

    def test_click_hides(self):
        d = should_hide(dom_events=frozenset({"click"}), state="idle")
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "click")

    def test_keydown_hides(self):
        d = should_hide(dom_events=frozenset({"keydown"}), state="idle")
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "keydown")

    def test_input_hides(self):
        d = should_hide(dom_events=frozenset({"input"}), state="idle")
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "input")

    def test_wheel_hides(self):
        d = should_hide(dom_events=frozenset({"wheel"}), state="idle")
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "wheel")

    def test_touch_target_ms(self):
        d = should_hide(dom_events=frozenset({"touchstart"}), state="idle")
        self.assertEqual(d.target_ms, HIDE_TARGET_MS["touchstart"])

    def test_keydown_target_ms(self):
        d = should_hide(dom_events=frozenset({"keydown"}), state="idle")
        self.assertEqual(d.target_ms, HIDE_TARGET_MS["keydown"])


class TestShouldHideScannerRisk(unittest.TestCase):
    """keydown/input → scanner_risk=True; touch/pointer → scanner_risk=False."""

    def test_keydown_scanner_risk(self):
        d = should_hide(dom_events=frozenset({"keydown"}), state="idle")
        self.assertTrue(d.scanner_risk)

    def test_input_scanner_risk(self):
        d = should_hide(dom_events=frozenset({"input"}), state="idle")
        self.assertTrue(d.scanner_risk)

    def test_touchstart_no_scanner_risk(self):
        d = should_hide(dom_events=frozenset({"touchstart"}), state="idle")
        self.assertFalse(d.scanner_risk)

    def test_pointerdown_no_scanner_risk(self):
        d = should_hide(dom_events=frozenset({"pointerdown"}), state="idle")
        self.assertFalse(d.scanner_risk)

    def test_mousedown_no_scanner_risk(self):
        d = should_hide(dom_events=frozenset({"mousedown"}), state="idle")
        self.assertFalse(d.scanner_risk)

    def test_click_no_scanner_risk(self):
        d = should_hide(dom_events=frozenset({"click"}), state="idle")
        self.assertFalse(d.scanner_risk)

    def test_wheel_no_scanner_risk(self):
        d = should_hide(dom_events=frozenset({"wheel"}), state="idle")
        self.assertFalse(d.scanner_risk)


class TestShouldHidePassthrough(unittest.TestCase):
    """Passthrough intent: True for touch/pointer/click, False for keyboard."""

    def test_touch_passthrough_true(self):
        d = should_hide(dom_events=frozenset({"touchstart"}), state="idle")
        self.assertTrue(d.passthrough)

    def test_keydown_passthrough_false(self):
        d = should_hide(dom_events=frozenset({"keydown"}), state="idle")
        self.assertFalse(d.passthrough)

    def test_input_passthrough_false(self):
        d = should_hide(dom_events=frozenset({"input"}), state="idle")
        self.assertFalse(d.passthrough)


class TestShouldHidePriorityResolution(unittest.TestCase):
    """Multiple simultaneous events → highest priority wins."""

    def test_keydown_wins_over_touch(self):
        d = should_hide(
            dom_events=frozenset({"touchstart", "keydown"}),
            state="idle",
        )
        self.assertEqual(d.reason, "keydown")

    def test_touch_wins_over_click(self):
        d = should_hide(
            dom_events=frozenset({"click", "touchstart"}),
            state="idle",
        )
        self.assertEqual(d.reason, "touchstart")

    def test_click_wins_over_wheel(self):
        d = should_hide(
            dom_events=frozenset({"wheel", "click"}),
            state="idle",
        )
        self.assertEqual(d.reason, "click")

    def test_state_wins_over_events(self):
        d = should_hide(
            dom_events=frozenset({"touchstart"}),
            state="busy",
        )
        self.assertEqual(d.reason, "state_change")

    def test_kill_switch_wins_over_everything(self):
        d = should_hide(
            dom_events=frozenset({"touchstart", "keydown"}),
            state="idle",
            kill_switch_active=True,
        )
        self.assertEqual(d.reason, "kill_switch")


class TestShouldHideDefaults(unittest.TestCase):
    """Default parameters: no events, state=unknown, kill_switch=False."""

    def test_default_state_unknown_hides(self):
        d = should_hide()
        self.assertTrue(d.hide)
        self.assertEqual(d.reason, "state_change")

    def test_none_events_equivalent_to_empty(self):
        d1 = should_hide(dom_events=None, state="idle")
        d2 = should_hide(dom_events=frozenset(), state="idle")
        self.assertEqual(d1.hide, d2.hide)
        self.assertEqual(d1.reason, d2.reason)


class TestResolveHighestPriorityTrigger(unittest.TestCase):
    """Priority ordering for DOM events."""

    def test_empty_returns_none(self):
        self.assertIsNone(resolve_highest_priority_trigger(frozenset()))

    def test_single_event(self):
        result = resolve_highest_priority_trigger(frozenset({"touchstart"}))
        self.assertEqual(result, "touchstart")

    def test_highest_wins(self):
        result = resolve_highest_priority_trigger(
            frozenset({"wheel", "keydown", "touchstart", "click"})
        )
        self.assertEqual(result, "keydown")

    def test_unknown_events_ignored(self):
        result = resolve_highest_priority_trigger(
            frozenset({"domcontentloaded", "load", "touchstart"})
        )
        self.assertEqual(result, "touchstart")

    def test_all_unknown_returns_none(self):
        result = resolve_highest_priority_trigger(
            frozenset({"domcontentloaded", "load"})
        )
        self.assertIsNone(result)

    def test_case_insensitive(self):
        result = resolve_highest_priority_trigger(frozenset({"TouchStart"}))
        self.assertEqual(result, "touchstart")


class TestScannerTriggers(unittest.TestCase):
    """SCANNER_TRIGGERS = {"keydown", "input"}."""

    def test_scanner_triggers_set(self):
        self.assertEqual(SCANNER_TRIGGERS, frozenset({"keydown", "input"}))

    def test_keydown_in_scanner_triggers(self):
        self.assertIn("keydown", SCANNER_TRIGGERS)

    def test_input_in_scanner_triggers(self):
        self.assertIn("input", SCANNER_TRIGGERS)

    def test_touch_not_in_scanner_triggers(self):
        self.assertNotIn("touchstart", SCANNER_TRIGGERS)


class TestValidateInteractionLog(unittest.TestCase):
    """Log validation: reject forbidden fields, accept safe entries."""

    def test_valid_log_entry(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "hide_trigger": "keydown",
            "hide_target_ms": 200,
            "hide_actual_ms": 180,
            "scanner_risk": True,
            "passthrough_attempted": False,
        })
        self.assertTrue(result["valid"], f"Errors: {result['errors']}")

    def test_rejects_event_key(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "event_key": "Enter",
        })
        self.assertFalse(result["valid"])

    def test_rejects_event_code(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "event_code": "Digit1",
        })
        self.assertFalse(result["valid"])

    def test_rejects_event_data(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "event_data": "some text",
        })
        self.assertFalse(result["valid"])

    def test_rejects_event_value(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "event_value": "4820001234567",
        })
        self.assertFalse(result["valid"])

    def test_rejects_input_value(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "input_value": "scanned barcode",
        })
        self.assertFalse(result["valid"])

    def test_rejects_scanner_value(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "scanner_value": "4820001234567",
        })
        self.assertFalse(result["valid"])

    def test_rejects_barcode(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "barcode": "4820001234567",
        })
        self.assertFalse(result["valid"])

    def test_rejects_key_value(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "key_value": "A",
        })
        self.assertFalse(result["valid"])

    def test_rejects_receipt(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "receipt_id": "RCP-001",
        })
        self.assertFalse(result["valid"])

    def test_rejects_payment(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "payment_amount": 100.50,
        })
        self.assertFalse(result["valid"])

    def test_rejects_fiscal(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "fiscal_data": "...",
        })
        self.assertFalse(result["valid"])

    def test_rejects_customer(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "customer_name": "Ivan",
        })
        self.assertFalse(result["valid"])

    def test_rejects_card(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "card_number": "4111111111111111",
        })
        self.assertFalse(result["valid"])

    def test_rejects_phone(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "phone": "+79161234567",
        })
        self.assertFalse(result["valid"])

    def test_rejects_email(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "email": "user@example.com",
        })
        self.assertFalse(result["valid"])

    def test_rejects_url(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "url": "https://example.com",
        })
        self.assertFalse(result["valid"])

    def test_rejects_token(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "token": "abc123",
        })
        self.assertFalse(result["valid"])

    def test_rejects_secret(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "secret": "xyz",
        })
        self.assertFalse(result["valid"])

    def test_rejects_backend(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "backend_url": "http://1.2.3.4",
        })
        self.assertFalse(result["valid"])

    def test_rejects_api_key(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "api_key": "sk-...",
        })
        self.assertFalse(result["valid"])

    def test_rejects_password(self):
        result = validate_interaction_log({
            "input_event_detected": True,
            "password": "hunter2",
        })
        self.assertFalse(result["valid"])

    def test_non_dict_rejected(self):
        result = validate_interaction_log("not a dict")
        self.assertFalse(result["valid"])


class TestHideStates(unittest.TestCase):
    """HIDE_STATES contains all non-idle valid states."""

    def test_all_hide_states_present(self):
        for state in ["busy", "scan", "cart", "payment",
                      "error", "offline", "unknown", "stale"]:
            self.assertIn(state, HIDE_STATES)

    def test_idle_not_in_hide_states(self):
        self.assertNotIn("idle", HIDE_STATES)


if __name__ == "__main__":
    unittest.main()
