"""Tests for state_observer — safe idle-only state contract.

Validates:
    - PlayerStateSnapshot construction and validation
    - from_dict() with valid/invalid/forbidden data
    - read_state_snapshot() file-based reading with all error paths
    - resolve_visibility() priority: kill-switch > state > idle
    - apply_state_snapshot() integration with ShellPlan
    - Immutability — snapshot is frozen, plan not mutated
    - No network/DB/subprocess/UKM5/mysql references in module source
    - Legacy landscape tests not broken
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from kso_player.state_observer import (
    DEFAULT_STATE_PATH,
    DEFAULT_STALE_AFTER_MS,
    ALLOWED_STATES,
    SHOW_STATES,
    HIDE_STATES,
    FORBIDDEN_STATE_KEYS,
    FORBIDDEN_KEY_PATTERNS,
    STATE_IDLE,
    STATE_BUSY,
    STATE_SCAN,
    STATE_CART,
    STATE_PAYMENT,
    STATE_ERROR,
    STATE_OFFLINE,
    STATE_UNKNOWN,
    STATE_STALE,
    PlayerStateSnapshot,
    from_dict,
    read_state_snapshot,
    resolve_visibility,
)
from kso_player.shell_plan import (
    build_shell_plan,
    apply_state_snapshot,
    ShellPlan,
    PLAN_MODE_VISIBLE,
    PLAN_MODE_HIDDEN,
)

PROFILE_CODE = "portrait_idle_overlay_768"

# ══════════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════════

def _sample_snapshot(state=STATE_IDLE, device="a-05954", updated_at=None):
    """Create a valid non-stale snapshot for testing."""
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return PlayerStateSnapshot(
        schema_version=1,
        device_code=device,
        state=state,
        source="observer",
        updated_at_utc=updated_at,
        stale_after_ms=999_999_999,  # effectively never stale in tests
    )

def _sample_dict(state=STATE_IDLE, device="a-05954", updated_at=None):
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "device_code": device,
        "state": state,
        "source": "observer",
        "updated_at_utc": updated_at,
        "stale_after_ms": 999_999_999,
    }


# ══════════════════════════════════════════════════════════════════════
# PlayerStateSnapshot construction & validation
# ══════════════════════════════════════════════════════════════════════


class TestPlayerStateSnapshotConstruction(unittest.TestCase):
    """Valid snapshot construction and property access."""

    def test_idle_snapshot_constructed(self):
        snap = _sample_snapshot(STATE_IDLE)
        self.assertEqual(snap.state, STATE_IDLE)
        self.assertTrue(snap.is_idle)
        self.assertTrue(snap.allows_display)

    def test_idle_effective_state(self):
        snap = _sample_snapshot(STATE_IDLE)
        self.assertEqual(snap.effective_state, STATE_IDLE)

    def test_busy_not_idle(self):
        snap = _sample_snapshot(STATE_BUSY)
        self.assertFalse(snap.is_idle)
        self.assertFalse(snap.allows_display)

    def test_scan_hidden(self):
        snap = _sample_snapshot(STATE_SCAN)
        self.assertFalse(snap.allows_display)

    def test_cart_hidden(self):
        snap = _sample_snapshot(STATE_CART)
        self.assertFalse(snap.allows_display)

    def test_payment_hidden(self):
        snap = _sample_snapshot(STATE_PAYMENT)
        self.assertFalse(snap.allows_display)

    def test_error_hidden(self):
        snap = _sample_snapshot(STATE_ERROR)
        self.assertFalse(snap.allows_display)

    def test_offline_hidden(self):
        snap = _sample_snapshot(STATE_OFFLINE)
        self.assertFalse(snap.allows_display)

    def test_unknown_hidden(self):
        snap = _sample_snapshot(STATE_UNKNOWN)
        self.assertFalse(snap.allows_display)

    def test_stale_hidden(self):
        snap = _sample_snapshot(STATE_STALE)
        self.assertFalse(snap.allows_display)

    def test_snapshot_is_frozen(self):
        snap = _sample_snapshot()
        with self.assertRaises(Exception):
            snap.state = "busy"  # frozen dataclass

    # ── Validation on construction ────────────────────────────────

    def test_invalid_state_raises(self):
        with self.assertRaises(ValueError):
            PlayerStateSnapshot(
                schema_version=1, device_code="dev", state="INVALID",
                source="test", updated_at_utc="2026-01-01T00:00:00Z",
            )

    def test_negative_schema_version_raises(self):
        with self.assertRaises(ValueError):
            PlayerStateSnapshot(
                schema_version=0, device_code="dev", state=STATE_IDLE,
                source="test", updated_at_utc="2026-01-01T00:00:00Z",
            )

    def test_empty_device_code_raises(self):
        with self.assertRaises(ValueError):
            PlayerStateSnapshot(
                schema_version=1, device_code="", state=STATE_IDLE,
                source="test", updated_at_utc="2026-01-01T00:00:00Z",
            )

    def test_empty_source_raises(self):
        with self.assertRaises(ValueError):
            PlayerStateSnapshot(
                schema_version=1, device_code="dev", state=STATE_IDLE,
                source="", updated_at_utc="2026-01-01T00:00:00Z",
            )

    def test_empty_updated_at_raises(self):
        with self.assertRaises(ValueError):
            PlayerStateSnapshot(
                schema_version=1, device_code="dev", state=STATE_IDLE,
                source="test", updated_at_utc="",
            )

    def test_negative_stale_after_ms_raises(self):
        with self.assertRaises(ValueError):
            PlayerStateSnapshot(
                schema_version=1, device_code="dev", state=STATE_IDLE,
                source="test", updated_at_utc="2026-01-01T00:00:00Z",
                stale_after_ms=-1,
            )

    def test_non_int_stale_after_ms_raises(self):
        with self.assertRaises(ValueError):
            PlayerStateSnapshot(
                schema_version=1, device_code="dev", state=STATE_IDLE,
                source="test", updated_at_utc="2026-01-01T00:00:00Z",
                stale_after_ms="1000",  # string, not int
            )


# ══════════════════════════════════════════════════════════════════════
# Staleness
# ══════════════════════════════════════════════════════════════════════


class TestPlayerStateSnapshotStaleness(unittest.TestCase):
    """Staleness checks — stale overrides all states to hide."""

    def test_fresh_snapshot_not_stale(self):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        snap = PlayerStateSnapshot(
            schema_version=1, device_code="dev", state=STATE_IDLE,
            source="test", updated_at_utc=now, stale_after_ms=5000,
        )
        self.assertFalse(snap.is_stale)
        self.assertEqual(snap.effective_state, STATE_IDLE)
        self.assertTrue(snap.allows_display)

    def test_old_timestamp_is_stale(self):
        old = "2020-01-01T00:00:00Z"
        snap = PlayerStateSnapshot(
            schema_version=1, device_code="dev", state=STATE_IDLE,
            source="test", updated_at_utc=old, stale_after_ms=5000,
        )
        self.assertTrue(snap.is_stale)
        self.assertEqual(snap.effective_state, STATE_STALE)
        self.assertFalse(snap.allows_display)

    def test_stale_idle_hides(self):
        old = "2020-01-01T00:00:00Z"
        snap = PlayerStateSnapshot(
            schema_version=1, device_code="dev", state=STATE_IDLE,
            source="test", updated_at_utc=old, stale_after_ms=5000,
        )
        self.assertFalse(snap.allows_display)

    def test_stale_payment_hides(self):
        old = "2020-01-01T00:00:00Z"
        snap = PlayerStateSnapshot(
            schema_version=1, device_code="dev", state=STATE_PAYMENT,
            source="test", updated_at_utc=old, stale_after_ms=5000,
        )
        self.assertFalse(snap.allows_display)

    def test_unknown_always_hides_independent_of_staleness(self):
        # Even fresh unknown must hide
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        snap = PlayerStateSnapshot(
            schema_version=1, device_code="dev", state=STATE_UNKNOWN,
            source="test", updated_at_utc=now, stale_after_ms=5000,
        )
        self.assertFalse(snap.allows_display)
        self.assertEqual(snap.effective_state, STATE_UNKNOWN)

    def test_unparseable_timestamp_is_stale(self):
        snap = PlayerStateSnapshot(
            schema_version=1, device_code="dev", state=STATE_IDLE,
            source="test", updated_at_utc="not-a-timestamp",
            stale_after_ms=5000,
        )
        self.assertTrue(snap.is_stale)
        self.assertEqual(snap.effective_state, STATE_STALE)


# ══════════════════════════════════════════════════════════════════════
# from_dict() — dict → snapshot
# ══════════════════════════════════════════════════════════════════════


class TestFromDict(unittest.TestCase):
    """from_dict() validates and constructs snapshots from raw dicts."""

    def test_valid_idle_dict(self):
        snap = from_dict(_sample_dict(STATE_IDLE))
        self.assertEqual(snap.state, STATE_IDLE)
        self.assertTrue(snap.allows_display)

    def test_valid_busy_dict(self):
        snap = from_dict(_sample_dict(STATE_BUSY))
        self.assertEqual(snap.state, STATE_BUSY)
        self.assertFalse(snap.allows_display)

    def test_forbidden_field_receipt_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["receipt_id"] = "12345"
        with self.assertRaises(ValueError) as ctx:
            from_dict(data)
        self.assertIn("forbidden", str(ctx.exception).lower())

    def test_forbidden_field_fiscal_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["fiscal_data"] = "xxx"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_payment_amount_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["payment_amount"] = 100
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_customer_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["customer_name"] = "John"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_card_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["card_number"] = "4111..."
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_items_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["items"] = [{"name": "milk"}]
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_phone_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["phone"] = "+7999..."
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_email_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["email"] = "x@y.com"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_pan_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["pan"] = "1234..."
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_cashier_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["cashier_id"] = "c001"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_token_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["token"] = "secret"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_password_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["password"] = "hunter2"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_backend_url_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["backend_url"] = "http://..."
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_ukm5_db_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["ukm5_db_host"] = "localhost"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_mysql_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["mysql_connection"] = "mysql://..."
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_file_path_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["file_path"] = "/etc/shadow"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_secret_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["secret"] = "abc123"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_api_key_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["api_key"] = "sk-..."
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_field_connection_string_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["connection_string"] = "mysql://..."
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_substring_transaction_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["transaction_uuid"] = "uuid-123"
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_forbidden_substring_redis_rejected(self):
        data = _sample_dict(STATE_IDLE)
        data["redis_connection_pool"] = "redis://..."
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_not_dict_raises(self):
        with self.assertRaises(ValueError):
            from_dict("not a dict")

    def test_invalid_state_in_dict(self):
        data = _sample_dict(STATE_IDLE)
        data["state"] = "playing_music"  # not allowed
        with self.assertRaises(ValueError):
            from_dict(data)

    def test_missing_state_defaults_to_unknown(self):
        data = {
            "schema_version": 1,
            "device_code": "dev",
            "source": "test",
            "updated_at_utc": "2026-01-01T00:00:00Z",
        }
        snap = from_dict(data)
        self.assertEqual(snap.state, STATE_UNKNOWN)
        self.assertFalse(snap.allows_display)

    def test_extra_unknown_keys_dropped_silently(self):
        data = _sample_dict(STATE_IDLE)
        data["extra_field"] = "ignored"
        data["another_thing"] = 42
        snap = from_dict(data)
        self.assertEqual(snap.state, STATE_IDLE)
        self.assertTrue(snap.allows_display)

    def test_stale_after_ms_default_applied(self):
        data = _sample_dict(STATE_IDLE)
        del data["stale_after_ms"]
        snap = from_dict(data)
        self.assertEqual(snap.stale_after_ms, DEFAULT_STALE_AFTER_MS)


# ══════════════════════════════════════════════════════════════════════
# read_state_snapshot() — file-based reading
# ══════════════════════════════════════════════════════════════════════


class TestReadStateSnapshotFile(unittest.TestCase):
    """read_state_snapshot() reads state JSON from filesystem."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        self.tmp_path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def _write_json(self, data):
        with open(self.tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_read_valid_idle(self):
        self._write_json(_sample_dict(STATE_IDLE))
        snap = read_state_snapshot(self.tmp_path)
        self.assertEqual(snap.state, STATE_IDLE)
        self.assertTrue(snap.allows_display)

    def test_read_valid_busy(self):
        self._write_json(_sample_dict(STATE_BUSY))
        snap = read_state_snapshot(self.tmp_path)
        self.assertEqual(snap.state, STATE_BUSY)
        self.assertFalse(snap.allows_display)

    def test_read_valid_payment(self):
        self._write_json(_sample_dict(STATE_PAYMENT))
        snap = read_state_snapshot(self.tmp_path)
        self.assertFalse(snap.allows_display)

    def test_read_valid_error(self):
        self._write_json(_sample_dict(STATE_ERROR))
        snap = read_state_snapshot(self.tmp_path)
        self.assertFalse(snap.allows_display)

    def test_read_valid_unknown(self):
        self._write_json(_sample_dict(STATE_UNKNOWN))
        snap = read_state_snapshot(self.tmp_path)
        self.assertFalse(snap.allows_display)

    def test_read_valid_stale_state(self):
        self._write_json(_sample_dict(STATE_STALE))
        snap = read_state_snapshot(self.tmp_path)
        self.assertFalse(snap.allows_display)


class TestReadStateSnapshotErrors(unittest.TestCase):
    """read_state_snapshot() error paths — all yield UNKNOWN."""

    def _assert_unknown(self, snap):
        self.assertEqual(snap.state, STATE_UNKNOWN)
        self.assertFalse(snap.allows_display)
        self.assertEqual(snap.device_code, "unknown")

    def test_missing_file_returns_unknown(self):
        snap = read_state_snapshot("/tmp/__nonexistent_hermes_test_state_file_xyz__")
        self._assert_unknown(snap)

    def test_broken_json_returns_unknown(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("this is not json {{{")
            path = f.name
        try:
            snap = read_state_snapshot(path)
            self._assert_unknown(snap)
        finally:
            os.unlink(path)

    def test_empty_file_returns_unknown(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("")
            path = f.name
        try:
            snap = read_state_snapshot(path)
            self._assert_unknown(snap)
        finally:
            os.unlink(path)

    def test_forbidden_field_in_file_returns_unknown(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            data = _sample_dict(STATE_IDLE)
            data["receipt_id"] = "1234"
            json.dump(data, f)
            path = f.name
        try:
            snap = read_state_snapshot(path)
            self._assert_unknown(snap)
        finally:
            os.unlink(path)

    def test_invalid_state_in_file_returns_unknown(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            data = _sample_dict(STATE_IDLE)
            data["state"] = "INVALID_STATE"
            json.dump(data, f)
            path = f.name
        try:
            snap = read_state_snapshot(path)
            self._assert_unknown(snap)
        finally:
            os.unlink(path)

    def test_file_is_directory_returns_unknown(self):
        snap = read_state_snapshot("/tmp")
        self._assert_unknown(snap)

    @patch("builtins.open", side_effect=PermissionError("denied"))
    def test_permission_error_returns_unknown(self, mock_open):
        snap = read_state_snapshot("/root/forbidden.json")
        self._assert_unknown(snap)

    @patch("os.path.exists", side_effect=PermissionError("denied"))
    def test_exists_permission_error_returns_unknown(self, mock_exists):
        snap = read_state_snapshot("/root/forbidden.json")
        self._assert_unknown(snap)

    def test_none_path_returns_unknown(self):
        snap = read_state_snapshot(None)
        self._assert_unknown(snap)

    def test_empty_string_path_returns_unknown(self):
        snap = read_state_snapshot("")
        self._assert_unknown(snap)

    def test_whitespace_path_returns_unknown(self):
        snap = read_state_snapshot("   ")
        self._assert_unknown(snap)


# ══════════════════════════════════════════════════════════════════════
# resolve_visibility()
# ══════════════════════════════════════════════════════════════════════


class TestResolveVisibility(unittest.TestCase):
    """resolve_visibility() — state + kill-switch → visible/hidden."""

    def test_idle_no_kill_switch_visible(self):
        snap = _sample_snapshot(STATE_IDLE)
        self.assertEqual(resolve_visibility(snap, False), "visible")

    def test_idle_with_kill_switch_hidden(self):
        snap = _sample_snapshot(STATE_IDLE)
        self.assertEqual(resolve_visibility(snap, True), "hidden")

    def test_busy_no_kill_switch_hidden(self):
        snap = _sample_snapshot(STATE_BUSY)
        self.assertEqual(resolve_visibility(snap, False), "hidden")

    def test_busy_with_kill_switch_hidden(self):
        snap = _sample_snapshot(STATE_BUSY)
        self.assertEqual(resolve_visibility(snap, True), "hidden")

    def test_scan_hidden(self):
        snap = _sample_snapshot(STATE_SCAN)
        self.assertEqual(resolve_visibility(snap, False), "hidden")

    def test_cart_hidden(self):
        snap = _sample_snapshot(STATE_CART)
        self.assertEqual(resolve_visibility(snap, False), "hidden")

    def test_payment_hidden(self):
        snap = _sample_snapshot(STATE_PAYMENT)
        self.assertEqual(resolve_visibility(snap, False), "hidden")

    def test_error_hidden(self):
        snap = _sample_snapshot(STATE_ERROR)
        self.assertEqual(resolve_visibility(snap, False), "hidden")

    def test_offline_hidden(self):
        snap = _sample_snapshot(STATE_OFFLINE)
        self.assertEqual(resolve_visibility(snap, False), "hidden")

    def test_unknown_hidden(self):
        snap = _sample_snapshot(STATE_UNKNOWN)
        self.assertEqual(resolve_visibility(snap, False), "hidden")

    def test_stale_state_hidden(self):
        snap = _sample_snapshot(STATE_STALE)
        self.assertEqual(resolve_visibility(snap, False), "hidden")

    def test_stale_timestamp_idle_hidden(self):
        old = "2020-01-01T00:00:00Z"
        snap = PlayerStateSnapshot(
            schema_version=1, device_code="dev", state=STATE_IDLE,
            source="test", updated_at_utc=old, stale_after_ms=5000,
        )
        self.assertEqual(resolve_visibility(snap, False), "hidden")


# ══════════════════════════════════════════════════════════════════════
# ShellPlan + state snapshot integration
# ══════════════════════════════════════════════════════════════════════


class TestApplyStateSnapshot(unittest.TestCase):
    """apply_state_snapshot() resolves visibility from snapshot + kill-switch."""

    @classmethod
    def setUpClass(cls):
        cls.plan: ShellPlan = build_shell_plan(
            PROFILE_CODE, initial_state=STATE_UNKNOWN, kill_switch_active=False
        )

    def test_idle_no_kill_switch_visible(self):
        snap = _sample_snapshot(STATE_IDLE)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertTrue(result.is_visible())
        self.assertEqual(result.visible_plan, PLAN_MODE_VISIBLE)

    def test_idle_with_kill_switch_hidden(self):
        snap = _sample_snapshot(STATE_IDLE)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=True)
        self.assertTrue(result.is_hidden())
        self.assertEqual(result.visible_plan, PLAN_MODE_HIDDEN)

    def test_busy_no_kill_switch_hidden(self):
        snap = _sample_snapshot(STATE_BUSY)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertTrue(result.is_hidden())

    def test_payment_no_kill_switch_hidden(self):
        snap = _sample_snapshot(STATE_PAYMENT)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertTrue(result.is_hidden())

    def test_unknown_no_kill_switch_hidden(self):
        snap = _sample_snapshot(STATE_UNKNOWN)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertTrue(result.is_hidden())

    def test_stale_state_no_kill_switch_hidden(self):
        snap = _sample_snapshot(STATE_STALE)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertTrue(result.is_hidden())

    def test_stale_timestamp_hidden(self):
        old = "2020-01-01T00:00:00Z"
        snap = PlayerStateSnapshot(
            schema_version=1, device_code="dev", state=STATE_IDLE,
            source="test", updated_at_utc=old, stale_after_ms=5000,
        )
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertTrue(result.is_hidden())

    def test_original_plan_not_mutated(self):
        original_visibility = self.plan.visible_plan
        snap = _sample_snapshot(STATE_IDLE)
        apply_state_snapshot(self.plan, snap, kill_switch_active=True)
        self.assertEqual(self.plan.visible_plan, original_visibility,
                         "Original plan must not be mutated")

    def test_geometry_preserved(self):
        snap = _sample_snapshot(STATE_IDLE)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertEqual(result.window_x, self.plan.window_x)
        self.assertEqual(result.window_y, self.plan.window_y)
        self.assertEqual(result.window_width, self.plan.window_width)
        self.assertEqual(result.window_height, self.plan.window_height)

    def test_safety_flags_preserved(self):
        snap = _sample_snapshot(STATE_IDLE)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertEqual(result.kill_switch_required, self.plan.kill_switch_required)
        self.assertEqual(result.always_on_top, self.plan.always_on_top)
        self.assertEqual(result.no_focus_steal, self.plan.no_focus_steal)
        self.assertEqual(result.forbidden_zones, self.plan.forbidden_zones)

    def test_window_type_preserved(self):
        snap = _sample_snapshot(STATE_IDLE)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertEqual(result.window_type, self.plan.window_type)
        self.assertEqual(result.fullscreen, self.plan.fullscreen)
        self.assertEqual(result.kiosk, self.plan.kiosk)

    def test_kill_switch_priority_over_state(self):
        """Kill-switch takes priority: idle + ks_active → hidden."""
        snap = _sample_snapshot(STATE_IDLE)
        # Confirm idle alone gives visible
        vis = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertTrue(vis.is_visible())
        # Kill-switch overrides
        hid = apply_state_snapshot(self.plan, snap, kill_switch_active=True)
        self.assertTrue(hid.is_hidden())

    def test_state_priority_over_idle(self):
        """State != idle takes priority over idle."""
        # busy → hidden even without kill-switch
        snap = _sample_snapshot(STATE_BUSY)
        result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
        self.assertTrue(result.is_hidden())

    def test_all_non_idle_states_hidden(self):
        for state in HIDE_STATES:
            snap = _sample_snapshot(state)
            result = apply_state_snapshot(self.plan, snap, kill_switch_active=False)
            self.assertTrue(
                result.is_hidden(),
                f"State {state!r} should be hidden, got {result.visible_plan!r}"
            )


# ══════════════════════════════════════════════════════════════════════
# Safety assertions — no network/UKM5/DB references
# ══════════════════════════════════════════════════════════════════════


class TestStateObserverNoLeaks(unittest.TestCase):
    """State observer module must NOT reference network, UKM5, DB, or secrets."""

    def test_module_has_no_network_imports(self):
        import kso_player.state_observer as so
        source = so.__dict__
        network_modules = ["http", "urllib", "socket", "requests", "aiohttp",
                           "httpx", "urllib3", "websocket"]
        for mod_name in network_modules:
            self.assertNotIn(mod_name, source,
                             f"state_observer must not import {mod_name}")

    def test_module_has_no_db_imports(self):
        import kso_player.state_observer as so
        source = so.__dict__
        db_modules = ["sqlite3", "psycopg2", "sqlalchemy", "mysql",
                      "redis", "pymongo", "clickhouse"]
        for mod_name in db_modules:
            self.assertNotIn(mod_name, source,
                             f"state_observer must not import {mod_name}")

    def test_module_has_no_subprocess(self):
        import kso_player.state_observer as so
        source = so.__dict__
        self.assertNotIn("subprocess", source,
                         "state_observer must not import subprocess")

    def _extract_functional_code(self, module):
        """Extract non-docstring, non-comment code lines from a module."""
        import inspect
        source_lines = []
        in_triple = False
        for line in inspect.getsource(module).split("\n"):
            s = line.strip()
            # Handle comments
            if s.startswith("#"):
                continue
            # Handle triple-quoted docstrings
            if s.startswith('"""') or s.startswith("'''"):
                # Check if single-line: opening and closing on same line
                opener = s[:3]
                rest = s[3:]
                if opener in rest:
                    # Single-line docstring — skip entirely
                    continue
                # Multi-line: toggle state
                in_triple = not in_triple
                continue
            if in_triple:
                continue
            if not s:
                continue
            source_lines.append(s.lower())
        return "\n".join(source_lines)

    def test_no_references_to_ukm5_in_functional_code(self):
        """Functional code must not reference UKM5 (except as forbidden-key string literals)."""
        import kso_player.state_observer as so
        func_code = self._extract_functional_code(so)
        # Filter out string literals in FORBIDDEN constants
        filtered = "\n".join(
            line for line in func_code.split("\n")
            if '"ukm5' not in line and "'ukm5" not in line
        )
        self.assertNotIn("ukm5", filtered,
                         "state_observer functional code must not reference UKM5")

    def test_no_references_to_mysql_in_functional_code(self):
        """Functional code must not reference MySQL (except as forbidden-key string literals)."""
        import kso_player.state_observer as so
        func_code = self._extract_functional_code(so)
        filtered = "\n".join(
            line for line in func_code.split("\n")
            if '"mysql' not in line and "'mysql" not in line
        )
        self.assertNotIn("mysql", filtered,
                         "state_observer must not reference MySQL in functional code")

    def test_default_path_is_under_run(self):
        self.assertTrue(
            DEFAULT_STATE_PATH.startswith("/run/verny/kso/"),
            f"State path {DEFAULT_STATE_PATH} must be under /run/verny/kso/"
        )


# ══════════════════════════════════════════════════════════════════════
# Snapshot repr safety
# ══════════════════════════════════════════════════════════════════════


class TestSnapshotRepr(unittest.TestCase):
    """Snapshot repr is safe and contains no forbidden data."""

    def test_repr_contains_device_code(self):
        snap = _sample_snapshot(STATE_IDLE, device="a-05954")
        self.assertIn("a-05954", repr(snap))

    def test_repr_contains_state(self):
        snap = _sample_snapshot(STATE_IDLE)
        self.assertIn("idle", repr(snap))

    def test_repr_no_forbidden_substrings(self):
        snap = _sample_snapshot(STATE_IDLE)
        r = repr(snap)
        forbidden = ["receipt", "payment", "fiscal", "customer",
                     "card", "pan", "token", "secret", "password",
                     "file_path", "backend_url"]
        for fb in forbidden:
            self.assertNotIn(fb, r.lower(),
                             f"repr must not contain '{fb}'")

    def test_repr_no_file_paths(self):
        snap = _sample_snapshot(STATE_IDLE)
        r = repr(snap)
        self.assertNotIn("/", r)


# ══════════════════════════════════════════════════════════════════════
# Legacy landscape compatibility
# ══════════════════════════════════════════════════════════════════════


class TestStateObserverLegacyNotBroken(unittest.TestCase):
    """Legacy landscape player tests are NOT affected by state_observer."""

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

    def test_kill_switch_imports_cleanly(self):
        import kso_player.kill_switch
        self.assertTrue(hasattr(kso_player.kill_switch, "is_kill_switch_active"))


# ══════════════════════════════════════════════════════════════════════
# Snapshot immutability across the pipeline
# ══════════════════════════════════════════════════════════════════════


class TestSnapshotImmutability(unittest.TestCase):
    """Snapshots are frozen — no mutation anywhere in the pipeline."""

    def test_snapshot_is_frozen(self):
        snap = _sample_snapshot()
        with self.assertRaises(Exception):
            snap.state = "busy"

    def test_resolve_visibility_does_not_mutate_snapshot(self):
        snap = _sample_snapshot(STATE_IDLE)
        original_state = snap.state
        resolve_visibility(snap, False)
        self.assertEqual(snap.state, original_state)

    def test_apply_state_snapshot_does_not_mutate_snapshot(self):
        plan = build_shell_plan(PROFILE_CODE)
        snap = _sample_snapshot(STATE_IDLE)
        original_state = snap.state
        apply_state_snapshot(plan, snap, kill_switch_active=False)
        self.assertEqual(snap.state, original_state)

    def test_read_state_snapshot_returns_frozen(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(_sample_dict(STATE_IDLE), f)
            path = f.name
        try:
            snap = read_state_snapshot(path)
            with self.assertRaises(Exception):
                snap.state = "busy"
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
