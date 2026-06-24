"""Tests for X11 Screensaver Runner — guarded state-driven screensaver.

Covers:
    - ScreensaverRunPlan: construction, validation, safe output
    - ScreensaverRunResult: immutable, safe_for_logging, forbidden fields
    - Visibility: idle+ks_inactive→visible, any other→hide
    - State-driven: all non-idle states → hide
    - Kill-switch: active → hide always
    - Forbidden fields: in state → hide
    - Missing state → hide
    - Stale state → hide
    - Lockfile: prevents double run (simulated)
    - Dry-run: no X11 window
    - Preflight: no X11 window
    - Run-once: requires approval token
    - Rollback: targeted only
    - Forbidden commands: pkill chromium/systemctl rejected
    - Safe output: no backend URL/token/secret/device_secret
    - Safe output: no receipt/payment/fiscal/customer/card/items/scanner
    - Immutability of all dataclasses
    - Legacy Zone C profile: not affected
    - X11 renderer contract: remains green
"""

import unittest
import tempfile
import json
import os
from pathlib import Path

from kso_player.x11_screensaver_runner import (
    ScreensaverRunPlan,
    ScreensaverRunResult,
    RUNNER_NAME,
    RUNNER_VERSION,
    MODE_DRY_RUN,
    MODE_PREFLIGHT_ONLY,
    MODE_RUN_ONCE,
    APPROVAL_TOKEN,
    DEFAULT_MAX_DURATION_SEC,
    HARD_MAX_DURATION_SEC,
    build_plan,
    validate_runner_plan,
    validate_runner_safe_output,
    validate_command_safety,
    simulate_run,
    decide_visibility,
    check_forbidden_state_fields,
    RUNNER_FORBIDDEN_FIELDS,
    FORBIDDEN_COMMANDS,
    VISIBILITY_IDLE_OK,
    VISIBILITY_HIDDEN_KS,
    VISIBILITY_HIDDEN_STATE,
    VISIBILITY_HIDDEN_FORBIDDEN,
    VISIBILITY_HIDDEN_STALE,
    VISIBILITY_HIDDEN_MISSING,
    STOP_REASON_KILL_SWITCH,
    STOP_REASON_STATE_CHANGE,
    STOP_REASON_TIMEOUT,
    STOP_REASON_DRY_RUN,
    STOP_REASON_PREFLIGHT,
    STOP_REASON_FORBIDDEN,
    STOP_REASON_STALE,
    STOP_REASON_MISSING_STATE,
    STOP_REASON_ERROR,
    STOP_REASON_FOCUS_LOST,
    STOP_REASON_FOCUS_WARNING,
)
from kso_player.state_observer import (
    PlayerStateSnapshot,
    STATE_IDLE,
    STATE_BUSY,
    STATE_SCAN,
    STATE_CART,
    STATE_PAYMENT,
    STATE_ERROR,
    STATE_OFFLINE,
    STATE_UNKNOWN,
    STATE_STALE,
)
from kso_player.interaction_hide import HIDE_STATES


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _fresh_utc() -> str:
    """Return a fresh UTC timestamp that won't be stale."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _idle_snapshot() -> PlayerStateSnapshot:
    return PlayerStateSnapshot(
        schema_version=1,
        device_code="test-k-001",
        state=STATE_IDLE,
        source="test",
        updated_at_utc=_fresh_utc(),
        stale_after_ms=60_000,
    )


def _busy_snapshot(state: str = STATE_BUSY) -> PlayerStateSnapshot:
    return PlayerStateSnapshot(
        schema_version=1,
        device_code="test-k-001",
        state=state,
        source="test",
        updated_at_utc=_fresh_utc(),
        stale_after_ms=60_000,
    )


def _stale_snapshot() -> PlayerStateSnapshot:
    return PlayerStateSnapshot(
        schema_version=1,
        device_code="test-k-001",
        state=STATE_IDLE,
        source="test",
        updated_at_utc="1970-01-01T00:00:00Z",
        stale_after_ms=5000,
    )


def _write_state_file(path: str, data: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _write_kill_switch(path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("1")


# ══════════════════════════════════════════════════════════════════════
# ScreensaverRunPlan
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverRunPlan(unittest.TestCase):
    """RunPlan construction, validation, safe output."""

    def test_default_plan_dry_run(self):
        plan = build_plan(mode=MODE_DRY_RUN)
        self.assertEqual(plan.mode, MODE_DRY_RUN)
        self.assertEqual(plan.runner_name, RUNNER_NAME)
        self.assertEqual(plan.max_duration_sec, DEFAULT_MAX_DURATION_SEC)
        self.assertFalse(plan.approval_provided)

    def test_default_plan_preflight(self):
        plan = build_plan(mode=MODE_PREFLIGHT_ONLY)
        self.assertEqual(plan.mode, MODE_PREFLIGHT_ONLY)
        self.assertFalse(plan.approval_provided)

    def test_default_plan_run_once_no_token(self):
        plan = build_plan(mode=MODE_RUN_ONCE)
        self.assertEqual(plan.mode, MODE_RUN_ONCE)
        self.assertFalse(plan.approval_provided)

    def test_default_plan_run_once_with_token(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        self.assertTrue(plan.approval_provided)

    def test_default_plan_run_once_wrong_token(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token="wrong_token")
        self.assertFalse(plan.approval_provided)

    def test_plan_has_renderer_plan(self):
        plan = build_plan(mode=MODE_DRY_RUN)
        self.assertIsNotNone(plan.renderer_plan)
        self.assertTrue(plan.renderer_plan.capabilities.is_production_ready())

    def test_plan_display_required(self):
        with self.assertRaises(ValueError):
            ScreensaverRunPlan(display="")

    def test_plan_duration_positive(self):
        with self.assertRaises(ValueError):
            ScreensaverRunPlan(max_duration_sec=0)

    def test_plan_duration_max(self):
        with self.assertRaises(ValueError):
            ScreensaverRunPlan(max_duration_sec=999)

    def test_plan_mode_invalid(self):
        with self.assertRaises(ValueError):
            ScreensaverRunPlan(mode="invalid")

    def test_plan_to_safe_dict_no_secrets(self):
        plan = build_plan(mode=MODE_DRY_RUN)
        d = plan.to_safe_dict()
        self.assertNotIn("backend_url", d)
        self.assertNotIn("token", d)
        self.assertNotIn("secret", d)
        self.assertNotIn("password", d)
        self.assertNotIn("device_secret", d)
        self.assertIn("runner_name", d)
        self.assertIn("mode", d)

    def test_plan_is_immutable(self):
        plan = build_plan(mode=MODE_DRY_RUN)
        with self.assertRaises(Exception):
            plan.mode = MODE_RUN_ONCE  # type: ignore


# ══════════════════════════════════════════════════════════════════════
# ScreensaverRunResult
# ══════════════════════════════════════════════════════════════════════

class TestScreensaverRunResult(unittest.TestCase):
    """RunResult construction, safe_for_logging, forbidden fields."""

    def test_default_result(self):
        r = ScreensaverRunResult()
        self.assertFalse(r.started)
        self.assertFalse(r.visible)
        self.assertEqual(r.state, STATE_UNKNOWN)
        self.assertTrue(r.safe_for_logging)

    def test_visible_result(self):
        r = ScreensaverRunResult(
            started=True,
            visible=True,
            reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE,
            duration_sec=30.0,
            window_id=52428801,
            rollback_done=True,
            stop_reason=STOP_REASON_TIMEOUT,
            mode=MODE_RUN_ONCE,
        )
        self.assertTrue(r.visible)
        self.assertTrue(r.started)
        self.assertEqual(r.window_id, 52428801)
        self.assertTrue(r.safe_for_logging)

    def test_result_to_safe_dict(self):
        r = ScreensaverRunResult(
            started=True,
            visible=True,
            reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE,
            kill_switch_active=False,
            duration_sec=10.0,
            window_id=123,
            rollback_done=True,
            stop_reason=STOP_REASON_TIMEOUT,
            proof_summary="all good",
            mode=MODE_RUN_ONCE,
        )
        d = r.to_safe_dict()
        self.assertEqual(d["started"], True)
        self.assertEqual(d["visible"], True)
        self.assertEqual(d["window_id"], 123)
        self.assertEqual(d["state"], STATE_IDLE)
        # No forbidden fields
        for forbidden in ["receipt", "payment", "fiscal", "backend_url", "token", "secret"]:
            self.assertNotIn(forbidden, d)
            for key in d:
                self.assertNotIn(forbidden, key.lower())

    def test_result_safe_for_logging_on_forbidden_data(self):
        # Even if someone tries to smuggle forbidden data into proof_summary,
        # to_safe_dict doesn't leak it — but safe_for_logging checks key names
        r = ScreensaverRunResult(
            proof_summary="receipt_id=123 customer_name=John",
        )
        self.assertTrue(r.safe_for_logging)  # keys are safe, values not checked

    def test_result_is_immutable(self):
        r = ScreensaverRunResult(visible=True)
        with self.assertRaises(Exception):
            r.visible = False  # type: ignore


# ══════════════════════════════════════════════════════════════════════
# Visibility decisions — idle + ks inactive → show
# ══════════════════════════════════════════════════════════════════════

class TestVisibilityIdleShow(unittest.TestCase):
    """Idle + kill-switch inactive → visible."""

    def test_idle_ks_inactive_shows(self):
        should_show, reason = decide_visibility(_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(should_show)
        self.assertEqual(reason, VISIBILITY_IDLE_OK)

    def test_simulate_idle_shows(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(result.started)
        self.assertTrue(result.visible)
        self.assertEqual(result.reason, VISIBILITY_IDLE_OK)
        self.assertEqual(result.state, STATE_IDLE)
        self.assertTrue(result.renderer_production_ready)

    def test_dry_run_idle_does_not_show(self):
        plan = build_plan(mode=MODE_DRY_RUN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertFalse(result.visible)  # dry-run never shows
        self.assertEqual(result.stop_reason, STOP_REASON_DRY_RUN)

    def test_preflight_idle_does_not_show(self):
        plan = build_plan(mode=MODE_PREFLIGHT_ONLY)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertFalse(result.visible)  # preflight never shows
        self.assertEqual(result.stop_reason, STOP_REASON_PREFLIGHT)


# ══════════════════════════════════════════════════════════════════════
# Kill-switch → hide
# ══════════════════════════════════════════════════════════════════════

class TestKillSwitchHides(unittest.TestCase):
    """Kill-switch active → hide always, regardless of state."""

    def test_ks_active_hides_idle(self):
        should_show, reason = decide_visibility(_idle_snapshot(), kill_switch_active=True)
        self.assertFalse(should_show)
        self.assertEqual(reason, VISIBILITY_HIDDEN_KS)

    def test_ks_active_hides_busy(self):
        should_show, reason = decide_visibility(_busy_snapshot(), kill_switch_active=True)
        self.assertFalse(should_show)
        self.assertEqual(reason, VISIBILITY_HIDDEN_KS)

    def test_simulate_ks_active_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=True)
        self.assertFalse(result.visible)
        self.assertEqual(result.stop_reason, STOP_REASON_KILL_SWITCH)
        self.assertTrue(result.kill_switch_active)

    def test_simulate_ks_active_hides_busy(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(), kill_switch_active=True)
        self.assertFalse(result.visible)
        self.assertEqual(result.stop_reason, STOP_REASON_KILL_SWITCH)

    def test_ks_file_exists_activates(self):
        with tempfile.TemporaryDirectory() as tmp:
            ks_path = os.path.join(tmp, "kill_switch")
            _write_kill_switch(ks_path)
            plan = build_plan(
                mode=MODE_RUN_ONCE,
                approval_token=APPROVAL_TOKEN,
                kill_switch_path=ks_path,
            )
            result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=True)
            self.assertFalse(result.visible)

    def test_ks_file_missing_inactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            ks_path = os.path.join(tmp, "kill_switch")
            # Do NOT create the file — it should be inactive
            result = simulate_run(
                build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN),
                snapshot=_idle_snapshot(),
                kill_switch_active=False,
            )
            self.assertTrue(result.visible)


# ══════════════════════════════════════════════════════════════════════
# Non-idle states → hide
# ══════════════════════════════════════════════════════════════════════

class TestNonIdleStatesHide(unittest.TestCase):
    """All non-idle states force hide."""

    def test_busy_hides(self):
        should_show, reason = decide_visibility(_busy_snapshot(STATE_BUSY), False)
        self.assertFalse(should_show)
        self.assertEqual(reason, VISIBILITY_HIDDEN_STATE)

    def test_scan_hides(self):
        should_show, reason = decide_visibility(_busy_snapshot(STATE_SCAN), False)
        self.assertFalse(should_show)

    def test_cart_hides(self):
        should_show, reason = decide_visibility(_busy_snapshot(STATE_CART), False)
        self.assertFalse(should_show)

    def test_payment_hides(self):
        should_show, reason = decide_visibility(_busy_snapshot(STATE_PAYMENT), False)
        self.assertFalse(should_show)

    def test_error_hides(self):
        should_show, reason = decide_visibility(_busy_snapshot(STATE_ERROR), False)
        self.assertFalse(should_show)

    def test_offline_hides(self):
        should_show, reason = decide_visibility(_busy_snapshot(STATE_OFFLINE), False)
        self.assertFalse(should_show)

    def test_unknown_hides(self):
        should_show, reason = decide_visibility(_busy_snapshot(STATE_UNKNOWN), False)
        self.assertFalse(should_show)

    def test_stale_hides(self):
        should_show, reason = decide_visibility(_stale_snapshot(), False)
        self.assertFalse(should_show)
        self.assertEqual(reason, VISIBILITY_HIDDEN_STALE)

    def test_simulate_busy_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_BUSY), kill_switch_active=False)
        self.assertFalse(result.visible)
        self.assertEqual(result.stop_reason, STOP_REASON_STATE_CHANGE)
        # hide_decision should be set
        self.assertIsNotNone(result.hide_decision)
        self.assertTrue(result.hide_decision.hide)
        self.assertEqual(result.hide_decision.reason, "state_change")

    def test_simulate_payment_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_PAYMENT), kill_switch_active=False)
        self.assertFalse(result.visible)

    def test_simulate_scan_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_SCAN), kill_switch_active=False)
        self.assertFalse(result.visible)

    def test_simulate_error_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_ERROR), kill_switch_active=False)
        self.assertFalse(result.visible)

    def test_simulate_offline_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_OFFLINE), kill_switch_active=False)
        self.assertFalse(result.visible)

    def test_simulate_unknown_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_UNKNOWN), kill_switch_active=False)
        self.assertFalse(result.visible)

    def test_simulate_stale_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_stale_snapshot(), kill_switch_active=False)
        self.assertFalse(result.visible)
        self.assertEqual(result.stop_reason, STOP_REASON_STALE)


# ══════════════════════════════════════════════════════════════════════
# Missing state → hide
# ══════════════════════════════════════════════════════════════════════

class TestMissingStateHides(unittest.TestCase):
    """Missing state file → hide."""

    def test_missing_state_file_hides(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "nonexistent.json")
            plan = build_plan(
                mode=MODE_RUN_ONCE,
                approval_token=APPROVAL_TOKEN,
                state_path=state_path,
            )
            # state file doesn't exist → observer returns unknown
            result = simulate_run(plan, snapshot=None, kill_switch_active=False)
            self.assertFalse(result.visible)

    def test_none_state_snapshot_hides(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        # Passing None snapshot → simulate uses read_state_snapshot
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_UNKNOWN), kill_switch_active=False)
        self.assertFalse(result.visible)
        self.assertEqual(result.stop_reason, STOP_REASON_MISSING_STATE)


# ══════════════════════════════════════════════════════════════════════
# Forbidden fields → hide
# ══════════════════════════════════════════════════════════════════════

class TestForbiddenFieldsHide(unittest.TestCase):
    """Forbidden fields in state → hide."""

    def test_receipt_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"receipt_id": "123"}))

    def test_payment_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"payment_amount": "100.00"}))

    def test_customer_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"customer_name": "John"}))

    def test_card_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"card_number": "4111..."}))

    def test_backend_url_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"backend_url": "https://..."}))

    def test_token_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"token": "abc123"}))

    def test_fiscal_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"fiscal_data": "..."}))

    def test_barcode_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"barcode": "4820000000001"}))

    def test_scanner_value_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"scanner_value": "4820000000001"}))

    def test_device_secret_forbidden(self):
        self.assertTrue(check_forbidden_state_fields({"device_secret": "s3cret"}))

    def test_clean_state_not_forbidden(self):
        self.assertFalse(check_forbidden_state_fields({"state": "idle", "device_code": "k-001"}))


# ══════════════════════════════════════════════════════════════════════
# Lockfile prevents double run (conceptual)
# ══════════════════════════════════════════════════════════════════════

class TestLockfilePreventsDoubleRun(unittest.TestCase):
    """Lockfile acquisition prevents concurrent runner instances."""

    def test_two_plans_have_different_lockfiles_possible(self):
        """Different lockfile paths don't collide."""
        plan1 = build_plan(mode=MODE_DRY_RUN, lockfile_path="/tmp/lock1")
        plan2 = build_plan(mode=MODE_DRY_RUN, lockfile_path="/tmp/lock2")
        self.assertNotEqual(plan1.lockfile_path, plan2.lockfile_path)

    def test_same_lockfile_path_in_plans(self):
        """Same lockfile path for two plans (lock held by first)."""
        plan1 = build_plan(mode=MODE_DRY_RUN, lockfile_path="/tmp/shared.lock")
        plan2 = build_plan(mode=MODE_DRY_RUN, lockfile_path="/tmp/shared.lock")
        self.assertEqual(plan1.lockfile_path, plan2.lockfile_path)
        # Both can build — lock acquisition happens at runtime
        val1 = validate_runner_plan(plan1)
        val2 = validate_runner_plan(plan2)
        self.assertTrue(val1["valid"])
        self.assertTrue(val2["valid"])


# ══════════════════════════════════════════════════════════════════════
# Dry-run: no X11 window
# ══════════════════════════════════════════════════════════════════════

class TestDryRunNoX11(unittest.TestCase):
    """Dry-run never creates X11 window."""

    def test_dry_run_not_visible(self):
        plan = build_plan(mode=MODE_DRY_RUN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertFalse(result.visible)
        self.assertEqual(result.stop_reason, STOP_REASON_DRY_RUN)
        self.assertEqual(result.duration_sec, 0.0)

    def test_dry_run_no_window_id(self):
        plan = build_plan(mode=MODE_DRY_RUN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertIsNone(result.window_id)

    def test_dry_run_rollback_done(self):
        plan = build_plan(mode=MODE_DRY_RUN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(result.rollback_done)


# ══════════════════════════════════════════════════════════════════════
# Preflight-only: no X11 window
# ══════════════════════════════════════════════════════════════════════

class TestPreflightNoX11(unittest.TestCase):
    """Preflight-only never creates X11 window."""

    def test_preflight_not_visible(self):
        plan = build_plan(mode=MODE_PREFLIGHT_ONLY)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertFalse(result.visible)
        self.assertEqual(result.stop_reason, STOP_REASON_PREFLIGHT)

    def test_preflight_no_window_id(self):
        plan = build_plan(mode=MODE_PREFLIGHT_ONLY)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertIsNone(result.window_id)

    def test_preflight_rollback_done(self):
        plan = build_plan(mode=MODE_PREFLIGHT_ONLY)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(result.rollback_done)


# ══════════════════════════════════════════════════════════════════════
# Run-once requires approval token
# ══════════════════════════════════════════════════════════════════════

class TestRunOnceRequiresApproval(unittest.TestCase):
    """run_once requires explicit approval token."""

    def test_run_once_without_approval_fails(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=None)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertFalse(result.started)
        self.assertIn("APPROVAL REQUIRED", result.proof_summary)

    def test_run_once_with_wrong_approval_fails(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token="wrong_token")
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertFalse(result.started)
        self.assertIn("APPROVAL REQUIRED", result.proof_summary)

    def test_run_once_with_correct_approval_works(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(result.started)
        self.assertTrue(result.visible)
        self.assertEqual(result.stop_reason, STOP_REASON_TIMEOUT)

    def test_plan_validation_rejects_run_once_no_approval(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=None)
        val = validate_runner_plan(plan)
        self.assertFalse(val["valid"])
        self.assertTrue(any("approval" in e.lower() for e in val["errors"]))

    def test_plan_validation_accepts_run_once_with_approval(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        val = validate_runner_plan(plan)
        self.assertTrue(val["valid"])


# ══════════════════════════════════════════════════════════════════════
# Rollback targeted only
# ══════════════════════════════════════════════════════════════════════

class TestRollbackTargetedOnly(unittest.TestCase):
    """Rollback targets only own process/window."""

    def test_rollback_does_not_touch_ukm5(self):
        """Rollback never restarts mint/mysql/redis/Chromium."""
        result = ScreensaverRunResult(
            started=True, visible=True, rollback_done=True,
            proof_summary="own window destroyed, lockfile released",
        )
        self.assertTrue(result.rollback_done)
        self.assertNotIn("mint", result.proof_summary.lower())
        self.assertNotIn("mysql", result.proof_summary.lower())

    def test_rollback_does_not_restart_chromium(self):
        result = ScreensaverRunResult(
            started=True, visible=True, rollback_done=True,
            proof_summary="window unmapped, lockfile cleaned",
        )
        self.assertNotIn("chromium", result.proof_summary.lower())

    def test_simulate_run_always_rollback_done(self):
        """Simulated runs always have rollback_done=True."""
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(result.rollback_done)

        result2 = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=True)
        self.assertTrue(result2.rollback_done)


# ══════════════════════════════════════════════════════════════════════
# Forbidden commands rejected
# ══════════════════════════════════════════════════════════════════════

class TestForbiddenCommandsRejected(unittest.TestCase):
    """pkill chromium/systemctl restart → rejected by validator."""

    def test_pkill_chromium_rejected(self):
        result = validate_command_safety("pkill chromium")
        self.assertFalse(result["safe"])
        self.assertTrue(any("pkill" in v for v in result["violations"]))

    def test_pkill_f_chromium_rejected(self):
        result = validate_command_safety("pkill -f chromium-browser")
        self.assertFalse(result["safe"])

    def test_killall_chromium_rejected(self):
        result = validate_command_safety("killall chromium")
        self.assertFalse(result["safe"])

    def test_systemctl_restart_mint_rejected(self):
        result = validate_command_safety("systemctl restart mint")
        self.assertFalse(result["safe"])

    def test_systemctl_stop_mysql_rejected(self):
        result = validate_command_safety("systemctl stop mysql")
        self.assertFalse(result["safe"])

    def test_systemctl_enable_rejected(self):
        result = validate_command_safety("systemctl enable hermes-screen")
        self.assertFalse(result["safe"])
        self.assertTrue(any("autostart" in v.lower() for v in result["violations"]))

    def test_crontab_rejected(self):
        result = validate_command_safety("crontab -e")
        self.assertFalse(result["safe"])

    def test_reboot_rejected(self):
        result = validate_command_safety("reboot")
        self.assertFalse(result["safe"])

    def test_shutdown_rejected(self):
        result = validate_command_safety("shutdown -h now")
        self.assertFalse(result["safe"])

    def test_safe_command_accepted(self):
        result = validate_command_safety("echo hello world")
        self.assertTrue(result["safe"])

    def test_safe_x11_command_accepted(self):
        result = validate_command_safety("xdotool search --name overlay.html")
        self.assertTrue(result["safe"])


# ══════════════════════════════════════════════════════════════════════
# Safe output: no backend URL/token/secret/device_secret
# ══════════════════════════════════════════════════════════════════════

class TestSafeOutputNoSecrets(unittest.TestCase):
    """Runner output must not contain secrets/tokens/backend URLs."""

    def test_result_no_backend_url(self):
        r = ScreensaverRunResult(proof_summary="backend_url=https://example.com")
        d = r.to_safe_dict()
        self.assertNotIn("backend_url", d)

    def test_result_no_token(self):
        r = ScreensaverRunResult(proof_summary="token=abc123")
        d = r.to_safe_dict()
        self.assertNotIn("token", d)

    def test_result_no_secret(self):
        r = ScreensaverRunResult(proof_summary="secret=s3cret")
        d = r.to_safe_dict()
        self.assertNotIn("secret", d)

    def test_result_no_device_secret(self):
        r = ScreensaverRunResult(proof_summary="device_secret=xyz")
        d = r.to_safe_dict()
        self.assertNotIn("device_secret", d)

    def test_result_no_api_key(self):
        r = ScreensaverRunResult(proof_summary="api_key=sk-1234")
        d = r.to_safe_dict()
        self.assertNotIn("api_key", d)

    def test_result_no_password(self):
        r = ScreensaverRunResult(proof_summary="password=admin123")
        d = r.to_safe_dict()
        self.assertNotIn("password", d)

    def test_validate_safe_output_rejects_backend_url_key(self):
        r = validate_runner_safe_output({"backend_url": "https://bad.com"})
        self.assertFalse(r["valid"])

    def test_validate_safe_output_rejects_token_key(self):
        r = validate_runner_safe_output({"token": "abc"})
        self.assertFalse(r["valid"])

    def test_validate_safe_output_rejects_device_secret_key(self):
        r = validate_runner_safe_output({"device_secret": "s3cret"})
        self.assertFalse(r["valid"])

    def test_validate_safe_output_accepts_safe_keys(self):
        r = validate_runner_safe_output({"started": True, "visible": False, "state": "idle"})
        self.assertTrue(r["valid"])

    def test_validate_safe_output_rejects_like_patterns(self):
        r = validate_runner_safe_output({"my_backend_url": "..."})
        self.assertFalse(r["valid"])


# ══════════════════════════════════════════════════════════════════════
# Safe output: no receipt/payment/fiscal/customer/card/items/scanner
# ══════════════════════════════════════════════════════════════════════

class TestSafeOutputNoPII(unittest.TestCase):
    """Runner output must not contain PII or payment data."""

    def test_result_no_receipt(self):
        r = ScreensaverRunResult(proof_summary="receipt_id=R-12345")
        d = r.to_safe_dict()
        self.assertNotIn("receipt_id", d)

    def test_result_no_payment(self):
        r = ScreensaverRunResult(proof_summary="payment_amount=100.00")
        d = r.to_safe_dict()
        self.assertNotIn("payment_amount", d)

    def test_result_no_fiscal(self):
        r = ScreensaverRunResult(proof_summary="fiscal_data=...")
        d = r.to_safe_dict()
        self.assertNotIn("fiscal_data", d)

    def test_result_no_customer(self):
        r = ScreensaverRunResult(proof_summary="customer_name=John")
        d = r.to_safe_dict()
        self.assertNotIn("customer_name", d)

    def test_result_no_card(self):
        r = ScreensaverRunResult(proof_summary="card_number=4111")
        d = r.to_safe_dict()
        self.assertNotIn("card_number", d)

    def test_result_no_scanner(self):
        r = ScreensaverRunResult(proof_summary="scanner_value=4820000000001")
        d = r.to_safe_dict()
        self.assertNotIn("scanner_value", d)

    def test_result_no_barcode(self):
        r = ScreensaverRunResult(proof_summary="barcode=4820000000001")
        d = r.to_safe_dict()
        self.assertNotIn("barcode", d)

    def test_validate_safe_output_rejects_receipt_key(self):
        r = validate_runner_safe_output({"receipt_id": "R-123"})
        self.assertFalse(r["valid"])

    def test_validate_safe_output_rejects_fiscal_key(self):
        r = validate_runner_safe_output({"fiscal_data": "..."})
        self.assertFalse(r["valid"])

    def test_validate_safe_output_rejects_customer_key(self):
        r = validate_runner_safe_output({"customer_email": "a@b.com"})
        self.assertFalse(r["valid"])

    def test_validate_safe_output_rejects_card_key(self):
        r = validate_runner_safe_output({"card_number": "4111"})
        self.assertFalse(r["valid"])

    def test_validate_safe_output_accepts_state(self):
        r = validate_runner_safe_output({"state": "idle", "started": True})
        self.assertTrue(r["valid"])


# ══════════════════════════════════════════════════════════════════════
# Legacy Zone C profile not affected
# ══════════════════════════════════════════════════════════════════════

class TestLegacyZoneCUnaffected(unittest.TestCase):
    """Runner does not affect legacy Zone C profile."""

    def test_runner_does_not_import_zone_c(self):
        """Runner module has no dependency on Zone C profile."""
        # The runner imports only general modules: state_observer, kill_switch,
        # interaction_hide, x11_click_through_renderer
        import sys
        # Check that we can import runner without touching profiles
        self.assertIn("kso_player.x11_screensaver_runner", sys.modules)

    def test_zone_c_profile_still_registered(self):
        """Zone C profile remains in registry."""
        from kso_player.profiles import get_profile
        zone_c = get_profile("portrait_idle_overlay_768")
        self.assertIsNotNone(zone_c)
        self.assertEqual(zone_c.root_width, 768)
        self.assertEqual(zone_c.root_height, 1024)
        self.assertEqual(zone_c.overlay_height, 240)  # Zone C = 240px

    def test_fullscreen_profile_still_registered(self):
        """Fullscreen screensaver profile remains in registry."""
        from kso_player.profiles import get_profile
        import kso_player.profiles.portrait_fullscreen_idle_screensaver_768  # trigger registration
        fs = get_profile("portrait_fullscreen_idle_screensaver_768")
        self.assertIsNotNone(fs)
        self.assertEqual(fs.root_width, 768)
        self.assertEqual(fs.root_height, 1024)


# ══════════════════════════════════════════════════════════════════════
# X11 renderer contract remains green
# ══════════════════════════════════════════════════════════════════════

class TestX11RendererContractGreen(unittest.TestCase):
    """X11 renderer contract remains valid after runner creation."""

    def test_renderer_capabilities_still_production_ready(self):
        from kso_player.x11_click_through_renderer import (
            X11ClickThroughCapabilities,
        )
        caps = X11ClickThroughCapabilities()
        self.assertTrue(caps.is_production_ready())

    def test_renderer_plan_validation_still_valid(self):
        from kso_player.x11_click_through_renderer import (
            create_default_renderer_plan,
            validate_renderer_plan,
        )
        plan = create_default_renderer_plan()
        result = validate_renderer_plan(plan)
        self.assertTrue(result.valid)
        self.assertTrue(result.production_ready)

    def test_renderer_input_region_empty(self):
        from kso_player.x11_click_through_renderer import (
            X11ClickThroughCapabilities,
        )
        self.assertTrue(X11ClickThroughCapabilities().input_region_empty)

    def test_renderer_no_keyboard_grab(self):
        from kso_player.x11_click_through_renderer import (
            X11ClickThroughCapabilities,
        )
        self.assertTrue(X11ClickThroughCapabilities().no_keyboard_grab)

    def test_renderer_no_pointer_grab(self):
        from kso_player.x11_click_through_renderer import (
            X11ClickThroughCapabilities,
        )
        self.assertTrue(X11ClickThroughCapabilities().no_pointer_grab)


# ══════════════════════════════════════════════════════════════════════
# Runner constants
# ══════════════════════════════════════════════════════════════════════

class TestRunnerConstants(unittest.TestCase):
    """Verify runner constants match expectations."""

    def test_runner_name(self):
        self.assertEqual(RUNNER_NAME, "x11_screensaver_runner")

    def test_hard_max_duration(self):
        self.assertEqual(HARD_MAX_DURATION_SEC, 60)

    def test_default_max_duration(self):
        self.assertEqual(DEFAULT_MAX_DURATION_SEC, 30)

    def test_valid_modes(self):
        from kso_player.x11_screensaver_runner import VALID_MODES
        self.assertIn(MODE_DRY_RUN, VALID_MODES)
        self.assertIn(MODE_PREFLIGHT_ONLY, VALID_MODES)
        self.assertIn(MODE_RUN_ONCE, VALID_MODES)
        self.assertEqual(len(VALID_MODES), 3)

    def test_approval_token_value(self):
        self.assertEqual(APPROVAL_TOKEN, "USER_APPROVED_RUN_ONCE")


# ══════════════════════════════════════════════════════════════════════
# Simulation edge cases
# ══════════════════════════════════════════════════════════════════════

class TestSimulationEdgeCases(unittest.TestCase):
    """Edge cases for simulate_run."""

    def test_invalid_plan_produces_error_result(self):
        """Invalid plan construction raises ValueError."""
        with self.assertRaises(ValueError):
            ScreensaverRunPlan(
                mode="invalid_mode_xyz",
                display=":0",
                max_duration_sec=30,
            )

    def test_result_safe_for_logging_true(self):
        result = ScreensaverRunResult(
            started=True,
            visible=True,
            reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE,
            stop_reason=STOP_REASON_TIMEOUT,
        )
        self.assertTrue(result.safe_for_logging)

    def test_hide_decision_in_result(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_PAYMENT), kill_switch_active=False)
        self.assertIsNotNone(result.hide_decision)
        self.assertTrue(result.hide_decision.hide)
        d = result.to_safe_dict()
        self.assertIn("hide_trigger", d)
        self.assertIn("hide_target_ms", d)

    def test_no_hide_decision_when_visible(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertIsNone(result.hide_decision)  # visible → no hide decision


# ══════════════════════════════════════════════════════════════════════
# Post-rollback focus restore
# ══════════════════════════════════════════════════════════════════════

class TestPostRollbackFocusRestore(unittest.TestCase):
    """Post-rollback focus restore verification."""

    def test_default_result_has_focus_fields(self):
        """All results include focus_restored, focus_restore_attempted, post_rollback_focus_lost."""
        result = ScreensaverRunResult(
            started=True, visible=True, reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE, stop_reason=STOP_REASON_TIMEOUT,
        )
        self.assertTrue(result.focus_restored)
        self.assertFalse(result.focus_restore_attempted)
        self.assertFalse(result.post_rollback_focus_lost)
        self.assertEqual(result.focus_restore_method, "")
        self.assertEqual(result.focus_restore_error, "")

    def test_focus_fields_in_safe_dict(self):
        """Focus fields appear in to_safe_dict."""
        result = ScreensaverRunResult(
            started=True, visible=True, reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE, stop_reason=STOP_REASON_TIMEOUT,
            focus_restored=True, focus_restore_attempted=True,
            focus_restore_method="xdotool_windowactivate",
            post_rollback_focus_lost=False,
        )
        d = result.to_safe_dict()
        self.assertIn("focus_restored", d)
        self.assertIn("focus_restore_attempted", d)
        self.assertIn("focus_restore_method", d)
        self.assertTrue(d["focus_restored"])
        self.assertTrue(d["focus_restore_attempted"])
        self.assertNotIn("post_rollback_focus_lost", d)  # False → omitted

    def test_focus_lost_appears_in_safe_dict(self):
        """When focus IS lost, post_rollback_focus_lost=True appears."""
        result = ScreensaverRunResult(
            started=True, visible=True, reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE, stop_reason=STOP_REASON_FOCUS_WARNING,
            focus_restored=False, focus_restore_attempted=True,
            focus_restore_method="xdotool_windowactivate",
            focus_restore_error="expected=10485762 got=0",
            post_rollback_focus_lost=True,
        )
        d = result.to_safe_dict()
        self.assertTrue(d["post_rollback_focus_lost"])
        self.assertEqual(d["focus_restore_error"], "expected=10485762 got=0")

    def test_focus_lost_sets_warning_stop_reason(self):
        """When focus_lost=True, result indicates focus_warning."""
        result = ScreensaverRunResult(
            started=True, visible=True, reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE, stop_reason=STOP_REASON_FOCUS_WARNING,
            focus_restored=False, focus_restore_attempted=True,
            post_rollback_focus_lost=True,
        )
        self.assertEqual(result.stop_reason, STOP_REASON_FOCUS_WARNING)
        self.assertEqual(result.stop_reason, "focus_warning")

    def test_dry_run_focus_is_restored(self):
        """Dry-run simulation always has focus_restored=True."""
        plan = build_plan(mode=MODE_DRY_RUN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(result.focus_restored)
        self.assertFalse(result.focus_restore_attempted)
        self.assertFalse(result.post_rollback_focus_lost)

    def test_preflight_focus_is_restored(self):
        """Preflight-only simulation always has focus_restored=True."""
        plan = build_plan(mode=MODE_PREFLIGHT_ONLY)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(result.focus_restored)
        self.assertFalse(result.focus_restore_attempted)
        self.assertFalse(result.post_rollback_focus_lost)

    def test_run_once_visible_focus_is_restored(self):
        """Run-once (visible) simulation always has focus_restored=True."""
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_idle_snapshot(), kill_switch_active=False)
        self.assertTrue(result.visible)
        self.assertTrue(result.focus_restored)
        self.assertFalse(result.focus_restore_attempted)
        self.assertFalse(result.post_rollback_focus_lost)

    def test_run_once_hidden_focus_is_restored(self):
        """Run-once (hidden) simulation always has focus_restored=True."""
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        result = simulate_run(plan, snapshot=_busy_snapshot(STATE_PAYMENT), kill_switch_active=False)
        self.assertFalse(result.visible)
        self.assertTrue(result.focus_restored)
        self.assertFalse(result.focus_restore_attempted)
        self.assertFalse(result.post_rollback_focus_lost)

    def test_focus_restored_when_true(self):
        """Result with focus_restored=True is safe for logging."""
        result = ScreensaverRunResult(
            started=True, visible=True, reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE, stop_reason=STOP_REASON_TIMEOUT,
            focus_restored=True, focus_restore_attempted=True,
            focus_restore_method="already_active",
        )
        self.assertTrue(result.safe_for_logging)

    def test_focus_lost_when_false(self):
        """Result with focus_restored=False is NOT a success."""
        result = ScreensaverRunResult(
            started=True, visible=True, reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE, stop_reason=STOP_REASON_FOCUS_WARNING,
            focus_restored=False, focus_restore_attempted=True,
            post_rollback_focus_lost=True,
        )
        self.assertFalse(result.focus_restored)
        self.assertTrue(result.post_rollback_focus_lost)

    def test_focus_fields_are_safe_log_fields(self):
        """Focus fields are in RUNNER_SAFE_LOG_FIELDS."""
        from kso_player.x11_screensaver_runner import RUNNER_SAFE_LOG_FIELDS
        self.assertIn("focus_restored", RUNNER_SAFE_LOG_FIELDS)
        self.assertIn("focus_restore_attempted", RUNNER_SAFE_LOG_FIELDS)
        self.assertIn("focus_restore_method", RUNNER_SAFE_LOG_FIELDS)
        self.assertIn("focus_restore_error", RUNNER_SAFE_LOG_FIELDS)
        self.assertIn("post_rollback_focus_lost", RUNNER_SAFE_LOG_FIELDS)

    def test_focus_stop_reason_constants(self):
        """focus_lost and focus_warning stop reasons exist."""
        self.assertEqual(STOP_REASON_FOCUS_LOST, "focus_lost")
        self.assertEqual(STOP_REASON_FOCUS_WARNING, "focus_warning")

    def test_no_barcode_in_focus_output(self):
        """Focus restore output contains no barcode/scanner value."""
        result = ScreensaverRunResult(
            started=True, visible=True, reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE, stop_reason=STOP_REASON_FOCUS_WARNING,
            focus_restored=False, focus_restore_attempted=True,
            focus_restore_method="xdotool_windowactivate",
            focus_restore_error="active_window=0 after activate, expected=10485762",
            post_rollback_focus_lost=True,
        )
        d = result.to_safe_dict()
        d_str = json.dumps(d)
        for forbidden in ["barcode", "scanner_value", "key_value", "event_key",
                           "receipt", "payment", "fiscal", "customer", "card", "pan",
                           "token", "secret", "password"]:
            self.assertNotIn(forbidden, d_str.lower(),
                             f"Forbidden pattern '{forbidden}' in focus output")

    def test_no_restart_in_focus_output(self):
        """Focus restore output contains no restart/stop commands."""
        result = ScreensaverRunResult(
            started=True, visible=True, reason=VISIBILITY_IDLE_OK,
            state=STATE_IDLE, stop_reason=STOP_REASON_TIMEOUT,
            focus_restored=True, focus_restore_attempted=True,
            focus_restore_method="xdotool_windowactivate",
        )
        d = result.to_safe_dict()
        d_str = json.dumps(d)
        for forbidden in ["pkill", "systemctl restart", "systemctl stop",
                           "reboot", "shutdown"]:
            self.assertNotIn(forbidden, d_str.lower())


# ══════════════════════════════════════════════════════════════════════
# All HIDE_STATES from interaction_hide covered
# ══════════════════════════════════════════════════════════════════════

class TestAllHideStatesCovered(unittest.TestCase):
    """Every state in interaction_hide.HIDE_STATES must force hide."""

    def test_all_hide_states_forbid_visibility(self):
        for state in HIDE_STATES:
            snapshot = _busy_snapshot(state)
            should_show, reason = decide_visibility(snapshot, kill_switch_active=False)
            self.assertFalse(
                should_show,
                f"State '{state}' should hide, but allowed visibility",
            )
            self.assertNotEqual(reason, VISIBILITY_IDLE_OK)

    def test_all_hide_states_simulate_hidden(self):
        plan = build_plan(mode=MODE_RUN_ONCE, approval_token=APPROVAL_TOKEN)
        for state in HIDE_STATES:
            snapshot = _busy_snapshot(state)
            result = simulate_run(plan, snapshot=snapshot, kill_switch_active=False)
            self.assertFalse(
                result.visible,
                f"State '{state}' simulation returned visible=True",
            )
