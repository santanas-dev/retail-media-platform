"""Tests for portrait_idle_overlay_768 player profile contract.

Validates:
    - Profile exists and is registered
    - Geometry: root, overlay, creative canvas — correct dimensions
    - Overlay is not fullscreen
    - Forbidden zones: payment button, header, close button — no intersection
    - State rules: show/hide correctly for all valid states
    - Hide SLA: <= 500 ms
    - No UKM5 DB flag
    - State contract validation: required fields, forbidden fields
    - Forbidden substrings / sensitive data checks
"""

import unittest

from kso_player.profiles import get_profile, list_profiles, PlayerProfile
from kso_player.profiles.portrait_idle_overlay_768 import (
    PROFILE_CODE,
    ROOT_WIDTH,
    ROOT_HEIGHT,
    OVERLAY_X,
    OVERLAY_Y,
    OVERLAY_WIDTH,
    OVERLAY_HEIGHT,
    CREATIVE_X,
    CREATIVE_Y,
    CREATIVE_WIDTH,
    CREATIVE_HEIGHT,
    SHOW_ON_STATES,
    HIDE_ON_STATES,
    HIDE_SLA_MS,
    IDLE_ONLY,
    NO_FULLSCREEN,
    NO_UKM5_DB,
    PAYMENT_ZONE,
    HEADER_ZONE,
    CLOSE_BTN_ZONE,
    FORBIDDEN_ZONES,
    FORBIDDEN_STATE_FIELDS,
    REQUIRED_STATE_FIELDS,
    VALID_STATES,
    GAP_TO_PAYMENT_MIN,
    validate_state_contract,
)


class TestProfileRegistration(unittest.TestCase):
    """Profile is registered and retrievable."""

    def test_profile_exists_in_registry(self):
        profile = get_profile(PROFILE_CODE)
        self.assertIsNotNone(profile, f"Profile '{PROFILE_CODE}' not registered")

    def test_profile_code_in_list(self):
        codes = list_profiles()
        self.assertIn(PROFILE_CODE, codes)

    def test_profile_is_frozen_dataclass(self):
        profile = get_profile(PROFILE_CODE)
        with self.assertRaises(Exception):
            profile.overlay_y = 999  # type: ignore

    def test_profile_code_matches(self):
        profile = get_profile(PROFILE_CODE)
        self.assertEqual(profile.code, PROFILE_CODE)

    def test_get_nonexistent_profile(self):
        self.assertIsNone(get_profile("nonexistent_profile_xyz"))


class TestGeometry(unittest.TestCase):
    """Geometry: root screen, overlay zone, creative canvas."""

    @classmethod
    def setUpClass(cls):
        cls.profile: PlayerProfile = get_profile(PROFILE_CODE)

    def test_root_screen_dimensions(self):
        self.assertEqual(self.profile.root_width, ROOT_WIDTH)
        self.assertEqual(self.profile.root_height, ROOT_HEIGHT)
        self.assertEqual(ROOT_WIDTH, 768)
        self.assertEqual(ROOT_HEIGHT, 1024)

    def test_overlay_zone_dimensions(self):
        self.assertEqual(self.profile.overlay_x, OVERLAY_X)
        self.assertEqual(self.profile.overlay_y, OVERLAY_Y)
        self.assertEqual(self.profile.overlay_width, OVERLAY_WIDTH)
        self.assertEqual(self.profile.overlay_height, OVERLAY_HEIGHT)
        self.assertEqual(OVERLAY_X, 0)
        self.assertEqual(OVERLAY_Y, 400)
        self.assertEqual(OVERLAY_WIDTH, 768)
        self.assertEqual(OVERLAY_HEIGHT, 240)

    def test_overlay_within_root_screen(self):
        self.assertGreaterEqual(self.profile.overlay_x, 0)
        self.assertGreaterEqual(self.profile.overlay_y, 0)
        self.assertLessEqual(
            self.profile.overlay_x + self.profile.overlay_width,
            self.profile.root_width,
        )
        self.assertLessEqual(
            self.profile.overlay_y + self.profile.overlay_height,
            self.profile.root_height,
        )

    def test_creative_canvas_dimensions(self):
        self.assertEqual(self.profile.creative_x, CREATIVE_X)
        self.assertEqual(self.profile.creative_y, CREATIVE_Y)
        self.assertEqual(self.profile.creative_width, CREATIVE_WIDTH)
        self.assertEqual(self.profile.creative_height, CREATIVE_HEIGHT)
        self.assertEqual(CREATIVE_WIDTH, 768)
        self.assertEqual(CREATIVE_HEIGHT, 200)

    def test_creative_within_overlay(self):
        self.assertGreaterEqual(self.profile.creative_x, self.profile.overlay_x)
        self.assertGreaterEqual(self.profile.creative_y, self.profile.overlay_y)
        self.assertLessEqual(
            self.profile.creative_x + self.profile.creative_width,
            self.profile.overlay_x + self.profile.overlay_width,
        )
        self.assertLessEqual(
            self.profile.creative_y + self.profile.creative_height,
            self.profile.overlay_y + self.profile.overlay_height,
        )

    def test_creative_centered_vertically(self):
        top_margin = self.profile.creative_y - self.profile.overlay_y
        bottom_margin = (self.profile.overlay_y + self.profile.overlay_height) - (
            self.profile.creative_y + self.profile.creative_height
        )
        self.assertEqual(top_margin, 20)  # 420 - 400
        self.assertEqual(bottom_margin, 20)  # 640 - 620

    def test_not_fullscreen(self):
        self.assertTrue(NO_FULLSCREEN)
        self.assertTrue(self.profile.no_fullscreen)
        is_fullscreen = (
            self.profile.overlay_x == 0
            and self.profile.overlay_y == 0
            and self.profile.overlay_width == self.profile.root_width
            and self.profile.overlay_height == self.profile.root_height
        )
        self.assertFalse(is_fullscreen, "Overlay must not be fullscreen")


class TestForbiddenZones(unittest.TestCase):
    """Forbidden zones: payment button, header, close button — no overlap."""

    @classmethod
    def setUpClass(cls):
        cls.profile: PlayerProfile = get_profile(PROFILE_CODE)

    def test_payment_zone_defined(self):
        self.assertEqual(PAYMENT_ZONE, (487, 720, 92, 120))

    def test_header_zone_defined(self):
        self.assertEqual(HEADER_ZONE, (0, 0, 768, 60))

    def test_close_button_zone_defined(self):
        self.assertEqual(CLOSE_BTN_ZONE, (725, 4, 6, 20))

    def test_forbidden_zones_registered(self):
        self.assertIsNotNone(self.profile.forbidden_zones)
        self.assertIn(PAYMENT_ZONE, self.profile.forbidden_zones)
        self.assertIn(HEADER_ZONE, self.profile.forbidden_zones)
        self.assertIn(CLOSE_BTN_ZONE, self.profile.forbidden_zones)

    def test_overlay_does_not_intersect_payment_zone(self):
        """Overlay (y=400-640) must not intersect payment (y=720-840)."""
        gap = self.profile.gap_to_zone(*PAYMENT_ZONE)
        self.assertGreater(gap, 0,
                           f"Overlay intersects payment zone! Gap={gap}")

    def test_gap_to_payment_at_least_minimum(self):
        """Gap from overlay bottom (y=640) to payment top (y=720) >= 80px."""
        gap = self.profile.gap_to_zone(*PAYMENT_ZONE)
        self.assertGreaterEqual(gap, GAP_TO_PAYMENT_MIN,
                                f"Gap {gap}px < minimum {GAP_TO_PAYMENT_MIN}px")

    def test_overlay_does_not_intersect_header_zone(self):
        """Overlay (y=400-640) must not intersect header (y=0-60)."""
        gap = self.profile.gap_to_zone(*HEADER_ZONE)
        self.assertGreater(gap, 0,
                           f"Overlay intersects header zone! Gap={gap}")

    def test_overlay_does_not_intersect_close_button(self):
        """Overlay (y=400-640) must not intersect close button (y=4-24)."""
        gap = self.profile.gap_to_zone(*CLOSE_BTN_ZONE)
        self.assertGreater(gap, 0,
                           f"Overlay intersects close button! Gap={gap}")

    def test_overlay_does_not_overlap_any_forbidden_zone(self):
        for zone in self.profile.forbidden_zones:
            gap = self.profile.gap_to_zone(*zone)
            self.assertGreater(
                gap, 0,
                f"Overlay intersects forbidden zone {zone}! Gap={gap}"
            )

    def test_all_forbidden_zones_within_root(self):
        for zone in self.profile.forbidden_zones:
            fx, fy, fw, fh = zone
            self.assertGreaterEqual(fx, 0)
            self.assertGreaterEqual(fy, 0)
            self.assertLessEqual(fx + fw, self.profile.root_width)
            self.assertLessEqual(fy + fh, self.profile.root_height)


class TestStateRules(unittest.TestCase):
    """State transitions: show/hide correctly for all valid states."""

    @classmethod
    def setUpClass(cls):
        cls.profile: PlayerProfile = get_profile(PROFILE_CODE)

    def test_idle_only_true(self):
        self.assertTrue(IDLE_ONLY)
        self.assertTrue(self.profile.idle_only)

    def test_show_on_states_is_idle_only(self):
        self.assertEqual(SHOW_ON_STATES, frozenset({"idle"}))

    def test_hide_on_states_includes_all_non_idle(self):
        expected = frozenset({
            "busy", "scan", "cart", "payment",
            "error", "offline", "unknown", "stale",
        })
        self.assertEqual(HIDE_ON_STATES, expected)

    def test_idle_allows_display(self):
        self.assertTrue(self.profile.allows_state("idle"))

    def test_busy_hides_display(self):
        self.assertFalse(self.profile.allows_state("busy"))

    def test_payment_hides_display(self):
        self.assertFalse(self.profile.allows_state("payment"))

    def test_scan_hides_display(self):
        self.assertFalse(self.profile.allows_state("scan"))

    def test_cart_hides_display(self):
        self.assertFalse(self.profile.allows_state("cart"))

    def test_error_hides_display(self):
        self.assertFalse(self.profile.allows_state("error"))

    def test_offline_hides_display(self):
        self.assertFalse(self.profile.allows_state("offline"))

    def test_unknown_hides_display(self):
        """Unknown state must ALWAYS hide (safe default)."""
        self.assertFalse(self.profile.allows_state("unknown"))

    def test_stale_hides_display(self):
        """Stale state must ALWAYS hide."""
        self.assertFalse(self.profile.allows_state("stale"))

    def test_unrecognized_state_hides(self):
        """Any unrecognized state must hide (fail-closed)."""
        self.assertFalse(self.profile.allows_state("maintenance"))
        self.assertFalse(self.profile.allows_state("receipt"))
        self.assertFalse(self.profile.allows_state(""))
        self.assertTrue(self.profile.allows_state("IDLE"))  # case-insensitive
        self.assertTrue(self.profile.allows_state("Idle"))   # mixed case ok

    def test_state_case_insensitive(self):
        """State comparison is case-insensitive."""
        self.assertTrue(self.profile.allows_state("Idle"))
        self.assertTrue(self.profile.allows_state("IDLE"))

    def test_state_with_whitespace(self):
        """State comparison strips whitespace."""
        self.assertTrue(self.profile.allows_state("  idle  "))


class TestHideSLA(unittest.TestCase):
    """Hide SLA: <= 500 ms."""

    @classmethod
    def setUpClass(cls):
        cls.profile: PlayerProfile = get_profile(PROFILE_CODE)

    def test_hide_sla_value(self):
        self.assertEqual(HIDE_SLA_MS, 500)
        self.assertEqual(self.profile.hide_sla_ms, 500)

    def test_hide_sla_within_limit(self):
        self.assertLessEqual(self.profile.hide_sla_ms, 500)

    def test_hide_sla_positive(self):
        self.assertGreater(self.profile.hide_sla_ms, 0)


class TestNoUKM5DB(unittest.TestCase):
    """Profile must not require UKM5 DB access."""

    @classmethod
    def setUpClass(cls):
        cls.profile: PlayerProfile = get_profile(PROFILE_CODE)

    def test_no_ukm5_db_flag(self):
        self.assertTrue(NO_UKM5_DB)
        self.assertTrue(self.profile.no_ukm5_db)


class TestForbiddenFields(unittest.TestCase):
    """Profile forbids receipt/payment/fiscal/customer fields."""

    @classmethod
    def setUpClass(cls):
        cls.profile: PlayerProfile = get_profile(PROFILE_CODE)

    def test_forbidden_fields_defined(self):
        self.assertIsInstance(FORBIDDEN_STATE_FIELDS, frozenset)
        self.assertGreater(len(FORBIDDEN_STATE_FIELDS), 0)

    def test_receipt_fields_forbidden(self):
        for field in ["receipt_id", "receipt_number"]:
            self.assertIn(field, FORBIDDEN_STATE_FIELDS)

    def test_payment_fields_forbidden(self):
        for field in ["payment_amount", "payment_method"]:
            self.assertIn(field, FORBIDDEN_STATE_FIELDS)

    def test_fiscal_forbidden(self):
        self.assertIn("fiscal_data", FORBIDDEN_STATE_FIELDS)

    def test_customer_fields_forbidden(self):
        for field in [
            "customer_name", "customer_phone", "customer_email",
            "customer_id", "cashier_id", "cashier_name",
        ]:
            self.assertIn(field, FORBIDDEN_STATE_FIELDS)

    def test_card_fields_forbidden(self):
        for field in ["card_number", "pan"]:
            self.assertIn(field, FORBIDDEN_STATE_FIELDS)

    def test_items_total_forbidden(self):
        for field in ["items", "total_amount"]:
            self.assertIn(field, FORBIDDEN_STATE_FIELDS)

    def test_transaction_forbidden(self):
        self.assertIn("transaction_id", FORBIDDEN_STATE_FIELDS)


class TestStateContractValidation(unittest.TestCase):
    """validate_state_contract() checks required/forbidden fields."""

    def test_valid_minimal_state(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "idle",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
        })
        self.assertTrue(result["valid"], f"Errors: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)

    def test_valid_busy_state(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "busy",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
        })
        self.assertTrue(result["valid"], f"Errors: {result['errors']}")

    def test_missing_required_fields(self):
        result = validate_state_contract({"state": "idle"})
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)

    def test_forbidden_receipt_id(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "idle",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
            "receipt_id": "RCP-001",
        })
        self.assertFalse(result["valid"])
        self.assertIn("forbidden field present: receipt_id", result["errors"])

    def test_forbidden_payment_amount(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "idle",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
            "payment_amount": 100.50,
        })
        self.assertFalse(result["valid"])

    def test_forbidden_customer_phone(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "idle",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
            "customer_phone": "+71234567890",
        })
        self.assertFalse(result["valid"])

    def test_forbidden_card_number(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "idle",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
            "card_number": "4111111111111111",
        })
        self.assertFalse(result["valid"])

    def test_forbidden_items(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "idle",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
            "items": [],
        })
        self.assertFalse(result["valid"])

    def test_invalid_state(self):
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "transaction",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
        })
        self.assertFalse(result["valid"])

    def test_invalid_schema_version(self):
        result = validate_state_contract({
            "schema_version": 999,
            "device_code": "demo_kso_001",
            "state": "idle",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
        })
        self.assertFalse(result["valid"])

    def test_suspicious_field_names_caught(self):
        """Fields with 'total' or 'receipt' in name are caught."""
        result = validate_state_contract({
            "schema_version": 1,
            "device_code": "demo_kso_001",
            "state": "idle",
            "source": "ukm5_safe_observer",
            "updated_at_utc": "2026-06-24T00:00:00Z",
            "receipt_subtotal": 50.0,  # suspicious field
        })
        self.assertFalse(result["valid"])

    def test_state_is_not_a_dict(self):
        result = validate_state_contract("not a dict")
        self.assertFalse(result["valid"])
        result = validate_state_contract(None)
        self.assertFalse(result["valid"])


class TestProfileImmutableConstraints(unittest.TestCase):
    """Profile constructor enforces constraints."""

    def test_overlay_within_root_enforced(self):
        with self.assertRaises(ValueError):
            PlayerProfile(
                code="test", name="Test",
                root_width=100, root_height=100,
                overlay_x=0, overlay_y=0, overlay_width=200, overlay_height=100,
                creative_x=0, creative_y=0, creative_width=100, creative_height=100,
                show_on_states=frozenset({"idle"}),
                hide_on_states=frozenset({"busy"}),
            )

    def test_creative_within_overlay_enforced(self):
        with self.assertRaises(ValueError):
            PlayerProfile(
                code="test", name="Test",
                root_width=768, root_height=1024,
                overlay_x=0, overlay_y=400, overlay_width=768, overlay_height=240,
                creative_x=0, creative_y=100, creative_width=768, creative_height=200,
                show_on_states=frozenset({"idle"}),
                hide_on_states=frozenset({"busy"}),
            )

    def test_idle_only_requires_idle_in_show_states(self):
        with self.assertRaises(ValueError):
            PlayerProfile(
                code="test", name="Test",
                root_width=768, root_height=1024,
                overlay_x=0, overlay_y=400, overlay_width=768, overlay_height=240,
                creative_x=0, creative_y=420, creative_width=768, creative_height=200,
                show_on_states=frozenset({"busy"}),
                hide_on_states=frozenset({"idle"}),
                idle_only=True,
            )

    def test_no_fullscreen_requires_overlay_less_than_root(self):
        with self.assertRaises(ValueError):
            PlayerProfile(
                code="test", name="Test",
                root_width=768, root_height=1024,
                overlay_x=0, overlay_y=0, overlay_width=768, overlay_height=1024,
                creative_x=0, creative_y=420, creative_width=768, creative_height=200,
                show_on_states=frozenset({"idle"}),
                hide_on_states=frozenset({"busy"}),
                no_fullscreen=True,
            )

    def test_hide_sla_must_be_positive(self):
        with self.assertRaises(ValueError):
            PlayerProfile(
                code="test", name="Test",
                root_width=768, root_height=1024,
                overlay_x=0, overlay_y=400, overlay_width=768, overlay_height=240,
                creative_x=0, creative_y=420, creative_width=768, creative_height=200,
                show_on_states=frozenset({"idle"}),
                hide_on_states=frozenset({"busy"}),
                hide_sla_ms=0,
            )

    def test_forbidden_zone_intersection_enforced(self):
        """Profile creation fails if a forbidden zone overlaps overlay."""
        with self.assertRaises(ValueError):
            PlayerProfile(
                code="test", name="Test",
                root_width=768, root_height=1024,
                overlay_x=0, overlay_y=400, overlay_width=768, overlay_height=240,
                creative_x=0, creative_y=420, creative_width=768, creative_height=200,
                show_on_states=frozenset({"idle"}),
                hide_on_states=frozenset({"busy"}),
                forbidden_zones=frozenset({(0, 400, 100, 100)}),  # overlaps!
            )


class TestGapToPayment(unittest.TestCase):
    """Exact gap calculation to payment button."""

    @classmethod
    def setUpClass(cls):
        cls.profile: PlayerProfile = get_profile(PROFILE_CODE)

    def test_gap_to_payment_is_exactly_80(self):
        """Overlay bottom y=640, payment top y=720 → gap = 80."""
        gap = self.profile.gap_to_zone(*PAYMENT_ZONE)
        self.assertEqual(gap, 80, f"Expected gap 80px, got {gap}px")

    def test_gap_to_header_is_exactly_340(self):
        """Overlay top y=400, header bottom y=60 → gap = 340."""
        gap = self.profile.gap_to_zone(*HEADER_ZONE)
        self.assertEqual(gap, 340, f"Expected gap 340px, got {gap}px")


class TestProfileNotRequiresUKM5DB(unittest.TestCase):
    """Profile makes no reference to UKM5 DB, queries, or connections."""

    @classmethod
    def setUpClass(cls):
        cls.profile: PlayerProfile = get_profile(PROFILE_CODE)

    def test_no_mysql_reference_in_code(self):
        """Profile module doesn't import or reference MySQL."""
        import inspect
        from kso_player.profiles import portrait_idle_overlay_768 as mod
        source = inspect.getsource(mod)
        self.assertNotIn("mysql", source.lower())
        self.assertNotIn("mysqldb", source.lower())
        self.assertNotIn("database", source.lower())
        self.assertNotIn("query(", source.lower())
        self.assertNotIn("3306", source)

    def test_no_db_connection_in_profile(self):
        """Profile dataclass has no DB connection fields."""
        fields = {f.name for f in self.profile.__dataclass_fields__.values()}
        db_like = {"db", "database", "connection", "cursor", "query", "mysql"}
        self.assertTrue(fields.isdisjoint(db_like),
                        f"DB-like fields found: {fields & db_like}")


if __name__ == "__main__":
    unittest.main()
