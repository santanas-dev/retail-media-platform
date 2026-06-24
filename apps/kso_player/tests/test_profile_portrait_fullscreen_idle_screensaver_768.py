"""Tests for portrait_fullscreen_idle_screensaver_768 player profile contract.

Covers:
    - Profile exists in registry
    - Geometry: 768×1024 fullscreen
    - State rules: idle → visible, all others → hidden
    - DOM hide triggers exist
    - Priority ordering
    - Forbidden fields
    - Scanner safety: no value saved
    - No receipt/payment/fiscal/customer/card/items fields
    - No backend URL/token/secrets
    - Kill-switch overrides visible
    - Immutable constants
"""

import unittest

from kso_player.profiles import get_profile
from kso_player.profiles.portrait_fullscreen_idle_screensaver_768 import (
    PROFILE_CODE,
    DOM_HIDE_TRIGGERS,
    HIDE_TRIGGER_PRIORITY,
    HIDE_TARGET_MS,
    HIDE_TRIGGER_PASSTHROUGH,
    SCANNER_TRIGGERS,
    FORBIDDEN_STATE_FIELDS,
    FORBIDDEN_LOG_FIELDS,
    SAFE_LOG_FIELDS,
    SHOW_ON_STATES,
    HIDE_ON_STATES,
    VALID_STATES,
    REQUIRED_STATE_FIELDS,
    validate_state_contract,
    portrait_fullscreen_idle_screensaver_768 as profile_instance,
)


class TestProfileExists(unittest.TestCase):
    """Profile must be registered and retrievable."""

    def test_profile_in_registry(self):
        p = get_profile(PROFILE_CODE)
        self.assertIsNotNone(p, f"Profile {PROFILE_CODE} not in registry")

    def test_profile_code_matches(self):
        p = get_profile(PROFILE_CODE)
        self.assertEqual(p.code, PROFILE_CODE)

    def test_profile_name_not_empty(self):
        p = get_profile(PROFILE_CODE)
        self.assertTrue(len(p.name) > 0)


class TestGeometryFullscreen(unittest.TestCase):
    """Fullscreen screensaver: 768×1024, (0,0)."""

    def test_root_dimensions(self):
        p = get_profile(PROFILE_CODE)
        self.assertEqual(p.root_width, 768)
        self.assertEqual(p.root_height, 1024)

    def test_window_position_is_zero_zero(self):
        p = get_profile(PROFILE_CODE)
        self.assertEqual(p.overlay_x, 0)
        self.assertEqual(p.overlay_y, 0)

    def test_window_is_fullscreen(self):
        p = get_profile(PROFILE_CODE)
        self.assertEqual(p.overlay_width, 768)
        self.assertEqual(p.overlay_height, 1024)

    def test_creative_is_fullscreen(self):
        p = get_profile(PROFILE_CODE)
        self.assertEqual(p.creative_width, 768)
        self.assertEqual(p.creative_height, 1024)
        self.assertEqual(p.creative_x, 0)
        self.assertEqual(p.creative_y, 0)

    def test_not_no_fullscreen(self):
        p = get_profile(PROFILE_CODE)
        self.assertFalse(p.no_fullscreen)


class TestStateRules(unittest.TestCase):
    """Idle → visible, all other states → hidden."""

    def test_idle_is_show_state(self):
        self.assertIn("idle", SHOW_ON_STATES)

    def test_no_other_show_states(self):
        self.assertEqual(SHOW_ON_STATES, frozenset({"idle"}))

    def test_hide_states_include_all_non_idle(self):
        for state in ["busy", "scan", "cart", "payment",
                      "error", "offline", "unknown", "stale"]:
            self.assertIn(state, HIDE_ON_STATES, f"{state} not in HIDE_ON_STATES")

    def test_idle_not_in_hide_states(self):
        self.assertNotIn("idle", HIDE_ON_STATES)

    def test_idle_only_flag(self):
        p = get_profile(PROFILE_CODE)
        self.assertTrue(p.idle_only)

    def test_hide_sla(self):
        p = get_profile(PROFILE_CODE)
        self.assertEqual(p.hide_sla_ms, 500)


class TestDOMHideTriggers(unittest.TestCase):
    """All required DOM events present."""

    def test_touch_trigger(self):
        self.assertIn("touchstart", DOM_HIDE_TRIGGERS)

    def test_pointer_trigger(self):
        self.assertIn("pointerdown", DOM_HIDE_TRIGGERS)

    def test_mouse_trigger(self):
        self.assertIn("mousedown", DOM_HIDE_TRIGGERS)

    def test_click_trigger(self):
        self.assertIn("click", DOM_HIDE_TRIGGERS)

    def test_keydown_trigger(self):
        self.assertIn("keydown", DOM_HIDE_TRIGGERS)

    def test_input_trigger(self):
        self.assertIn("input", DOM_HIDE_TRIGGERS)

    def test_wheel_trigger(self):
        self.assertIn("wheel", DOM_HIDE_TRIGGERS)

    def test_all_triggers_have_priority(self):
        for trigger in DOM_HIDE_TRIGGERS:
            self.assertIn(trigger, HIDE_TRIGGER_PRIORITY,
                          f"{trigger} missing priority")

    def test_all_triggers_have_target_ms(self):
        for trigger in DOM_HIDE_TRIGGERS:
            self.assertIn(trigger, HIDE_TARGET_MS,
                          f"{trigger} missing target_ms")

    def test_all_triggers_have_passthrough(self):
        for trigger in DOM_HIDE_TRIGGERS:
            self.assertIn(trigger, HIDE_TRIGGER_PASSTHROUGH,
                          f"{trigger} missing passthrough flag")


class TestPriorityOrdering(unittest.TestCase):
    """kill_switch > state_change > keydown/input > touch/pointer > click > wheel."""

    def test_kill_switch_highest(self):
        ks_prio = HIDE_TRIGGER_PRIORITY["kill_switch"]
        for trigger in DOM_HIDE_TRIGGERS:
            self.assertLess(ks_prio, HIDE_TRIGGER_PRIORITY[trigger],
                            f"kill_switch not higher than {trigger}")

    def test_keyboard_higher_than_touch(self):
        self.assertLess(HIDE_TRIGGER_PRIORITY["keydown"],
                        HIDE_TRIGGER_PRIORITY["touchstart"])

    def test_touch_higher_than_click(self):
        self.assertLess(HIDE_TRIGGER_PRIORITY["touchstart"],
                        HIDE_TRIGGER_PRIORITY["click"])

    def test_click_higher_than_wheel(self):
        self.assertLess(HIDE_TRIGGER_PRIORITY["click"],
                        HIDE_TRIGGER_PRIORITY["wheel"])

    def test_keydown_and_input_same_priority(self):
        self.assertEqual(HIDE_TRIGGER_PRIORITY["keydown"],
                         HIDE_TRIGGER_PRIORITY["input"])

    def test_touch_pointer_mouse_same_priority(self):
        self.assertEqual(HIDE_TRIGGER_PRIORITY["touchstart"],
                         HIDE_TRIGGER_PRIORITY["pointerdown"])
        self.assertEqual(HIDE_TRIGGER_PRIORITY["touchstart"],
                         HIDE_TRIGGER_PRIORITY["mousedown"])


class TestHideSLA(unittest.TestCase):
    """All hide targets ≤ 500ms."""

    def test_all_targets_within_sla(self):
        for trigger, target_ms in HIDE_TARGET_MS.items():
            self.assertLessEqual(target_ms, 500,
                                 f"{trigger} target {target_ms}ms exceeds SLA")

    def test_high_priority_fast(self):
        for trigger in ["kill_switch", "keydown", "input", "touchstart"]:
            self.assertLessEqual(HIDE_TARGET_MS[trigger], 200,
                                 f"{trigger} target > 200ms")


class TestForbiddenFields(unittest.TestCase):
    """State contract must reject forbidden fields."""

    def test_forbidden_state_fields(self):
        self.assertIn("receipt_id", FORBIDDEN_STATE_FIELDS)
        self.assertIn("payment_amount", FORBIDDEN_STATE_FIELDS)
        self.assertIn("fiscal_data", FORBIDDEN_STATE_FIELDS)
        self.assertIn("customer_name", FORBIDDEN_STATE_FIELDS)
        self.assertIn("card_number", FORBIDDEN_STATE_FIELDS)
        self.assertIn("items", FORBIDDEN_STATE_FIELDS)
        self.assertIn("total_amount", FORBIDDEN_STATE_FIELDS)

    def test_validate_rejects_forbidden(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "test",
            "state": "idle",
            "source": "test",
            "updated_at_utc": "2024-01-01T00:00:00Z",
            "receipt_id": "RCP-001",
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any("receipt_id" in e for e in result["errors"]))


class TestScannerSafety(unittest.TestCase):
    """Scanner (keyboard wedge) events must NOT log values."""

    def test_scanner_triggers_identified(self):
        self.assertIn("keydown", SCANNER_TRIGGERS)
        self.assertIn("input", SCANNER_TRIGGERS)

    def test_scanner_value_not_in_safe_log_fields(self):
        self.assertNotIn("event_key", SAFE_LOG_FIELDS)
        self.assertNotIn("event_code", SAFE_LOG_FIELDS)
        self.assertNotIn("scanner_value", SAFE_LOG_FIELDS)
        self.assertNotIn("barcode", SAFE_LOG_FIELDS)

    def test_forbidden_log_fields(self):
        for field in ["event_key", "event_code", "event_keycode",
                      "event_data", "event_value", "input_value",
                      "scanner_value", "barcode", "key_value"]:
            self.assertIn(field, FORBIDDEN_LOG_FIELDS,
                          f"{field} not in FORBIDDEN_LOG_FIELDS")

    def test_safe_log_fields_only_binary(self):
        self.assertIn("input_event_detected", SAFE_LOG_FIELDS)
        self.assertIn("hide_trigger", SAFE_LOG_FIELDS)
        self.assertIn("hide_target_ms", SAFE_LOG_FIELDS)
        self.assertIn("scanner_risk", SAFE_LOG_FIELDS)

    def test_keydown_passthrough_is_false(self):
        self.assertFalse(HIDE_TRIGGER_PASSTHROUGH["keydown"])
        self.assertFalse(HIDE_TRIGGER_PASSTHROUGH["input"])

    def test_touch_passthrough_is_true(self):
        self.assertTrue(HIDE_TRIGGER_PASSTHROUGH["touchstart"])
        self.assertTrue(HIDE_TRIGGER_PASSTHROUGH["pointerdown"])
        self.assertTrue(HIDE_TRIGGER_PASSTHROUGH["mousedown"])
        self.assertTrue(HIDE_TRIGGER_PASSTHROUGH["click"])


class TestValidStates(unittest.TestCase):
    """All required states are valid."""

    def test_all_required_states_valid(self):
        for state in ["idle", "busy", "scan", "cart", "payment",
                      "error", "offline", "unknown", "stale"]:
            self.assertIn(state, VALID_STATES)

    def test_validate_accepts_idle(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "test",
            "state": "idle",
            "source": "test",
            "updated_at_utc": "2024-01-01T00:00:00Z",
        })
        self.assertTrue(result["valid"], f"Errors: {result['errors']}")

    def test_validate_rejects_invalid_state(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "test",
            "state": "playing",
            "source": "test",
            "updated_at_utc": "2024-01-01T00:00:00Z",
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any("invalid state" in e for e in result["errors"]))


class TestRequiredFields(unittest.TestCase):
    """State contract requires specific fields."""

    def test_required_fields(self):
        for field in ["schema_version", "device_code", "state",
                      "source", "updated_at_utc"]:
            self.assertIn(field, REQUIRED_STATE_FIELDS)

    def test_validate_missing_required(self):
        result = validate_state_contract({"state": "idle"})
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)


class TestNoSecretsOrBackend(unittest.TestCase):
    """Profile must not contain backend URL, tokens, or secrets."""

    def test_no_backend_url_in_constants(self):
        import inspect
        source = inspect.getsource(
            __import__(
                "kso_player.profiles.portrait_fullscreen_idle_screensaver_768",
                fromlist=[""]
            )
        )
        source_lower = source.lower()
        # Check for URL patterns
        forbidden_urls = ["https://", "http://", "api.", "backend_url"]
        for url_pattern in forbidden_urls:
            self.assertNotIn(url_pattern, source_lower,
                             f"URL pattern '{url_pattern}' found in profile")

    def test_no_token_in_constants(self):
        import inspect
        source = inspect.getsource(
            __import__(
                "kso_player.profiles.portrait_fullscreen_idle_screensaver_768",
                fromlist=[""]
            )
        )
        source_lower = source.lower()
        self.assertNotIn("bearer", source_lower)
        self.assertNotIn("jwt", source_lower)
        self.assertNotIn("api_key", source_lower)


class TestKillSwitchOverride(unittest.TestCase):
    """Kill-switch has highest priority."""

    def test_kill_switch_priority_zero(self):
        self.assertEqual(HIDE_TRIGGER_PRIORITY["kill_switch"], 0)

    def test_kill_switch_passthrough_false(self):
        self.assertFalse(HIDE_TRIGGER_PASSTHROUGH["kill_switch"])

    def test_kill_switch_fast_hide(self):
        self.assertEqual(HIDE_TARGET_MS["kill_switch"], 200)


class TestImmutableConstants(unittest.TestCase):
    """Constants must be immutable (frozenset)."""

    def test_dom_hide_triggers_is_frozenset(self):
        self.assertIsInstance(DOM_HIDE_TRIGGERS, frozenset)

    def test_show_on_states_is_frozenset(self):
        self.assertIsInstance(SHOW_ON_STATES, frozenset)

    def test_hide_on_states_is_frozenset(self):
        self.assertIsInstance(HIDE_ON_STATES, frozenset)

    def test_forbidden_state_fields_is_frozenset(self):
        self.assertIsInstance(FORBIDDEN_STATE_FIELDS, frozenset)

    def test_valid_states_is_frozenset(self):
        self.assertIsInstance(VALID_STATES, frozenset)

    def test_scanner_triggers_is_frozenset(self):
        self.assertIsInstance(SCANNER_TRIGGERS, frozenset)


class TestUKM5NoDBAccess(unittest.TestCase):
    """Profile must have no_ukm5_db=True."""

    def test_no_ukm5_db(self):
        p = get_profile(PROFILE_CODE)
        self.assertTrue(p.no_ukm5_db)


if __name__ == "__main__":
    unittest.main()
