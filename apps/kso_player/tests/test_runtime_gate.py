"""Tests for KSO Player Runtime Gate.

Tests evaluate_kso_runtime_gate() and format function.
Pure file I/O — no HTTP, no backend, no secret reading.
Player NEVER writes kso_state.json.
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase

from kso_player.runtime_gate import (
    KsoRuntimeGateResult,
    evaluate_kso_runtime_gate,
    format_kso_runtime_gate_result,
    ALLOWED_STATES,
    ACTION_PLAY,
    ACTION_HOLD,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_PLAY_ALLOWED,
    REASON_MISSING_STATE_FILE,
    REASON_INVALID_JSON,
    REASON_SCHEMA_MISMATCH,
    REASON_INVALID_STATE,
    REASON_MISSING_UPDATED_AT,
    REASON_INVALID_UPDATED_AT,
    REASON_STALE_STATE,
    REASON_FUTURE_TIMESTAMP,
    REASON_NON_IDLE_STATE,
    REASON_READ_FAILED,
    REASON_INVALID_ARGS,
    AGE_FRESH,
    AGE_STALE,
    AGE_UNKNOWN,
    FORBIDDEN_SUBSTRINGS,
    STATE_DIR,
    STATE_FILE,
)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return False
    return True


def _write_state(root, state="idle", age_seconds=5, source="ukm4_state_adapter"):
    """Write a valid kso_state.json with controlled age."""
    state_dir = Path(root) / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / STATE_FILE

    updated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    data = {
        "state": state,
        "updated_at_utc": updated_at.isoformat(),
        "source": source,
    }
    state_path.write_text(json.dumps(data, sort_keys=True))


def _write_raw_state(root, content):
    """Write arbitrary content to kso_state.json."""
    state_dir = Path(root) / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / STATE_FILE
    state_path.write_text(content)


# ══════════════════════════════════════════════════════════════════════
# Tests: idle → play
# ══════════════════════════════════════════════════════════════════════

class TestIdlePlay(TestCase):
    """Idle + valid + fresh → play_allowed=true."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_idle_fresh_play_allowed(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.play_allowed)
        self.assertEqual(result.action, ACTION_PLAY)
        self.assertEqual(result.state, "idle")
        self.assertTrue(result.state_valid)
        self.assertTrue(result.fresh)
        self.assertEqual(result.reason, REASON_PLAY_ALLOWED)
        self.assertEqual(result.age_bucket, AGE_FRESH)

    def test_idle_fresh_format(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        text = format_kso_runtime_gate_result(result)
        self.assertIn("play_allowed: true", text)
        self.assertIn("action: play", text)
        self.assertIn("state: idle", text)
        self.assertTrue(_no_forbidden(text))

    def test_idle_fresh_repr_safe(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_idle_at_boundary(self):
        _write_state(self.tmp, state="idle", age_seconds=30)
        result = evaluate_kso_runtime_gate(self.tmp)
        # age_seconds=30, stale_seconds=30 → age > 30 is stale, age == 30 is boundary
        # Implementation uses >, so 30 == stale_seconds is NOT stale
        self.assertTrue(result.play_allowed)
        self.assertEqual(result.reason, REASON_PLAY_ALLOWED)


# ══════════════════════════════════════════════════════════════════════
# Tests: non-idle → hold
# ══════════════════════════════════════════════════════════════════════

class TestNonIdleHold(TestCase):
    """All non-idle states → hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_transaction_hold(self):
        _write_state(self.tmp, state="transaction", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.action, ACTION_HOLD)
        self.assertEqual(result.state, "transaction")
        self.assertEqual(result.reason, REASON_NON_IDLE_STATE)

    def test_payment_hold(self):
        _write_state(self.tmp, state="payment", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.state, "payment")
        self.assertEqual(result.reason, REASON_NON_IDLE_STATE)

    def test_receipt_hold(self):
        _write_state(self.tmp, state="receipt", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.state, "receipt")
        self.assertEqual(result.reason, REASON_NON_IDLE_STATE)

    def test_service_hold(self):
        _write_state(self.tmp, state="service", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.state, "service")

    def test_error_hold(self):
        _write_state(self.tmp, state="error", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.state, "error")

    def test_maintenance_hold(self):
        _write_state(self.tmp, state="maintenance", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.state, "maintenance")

    def test_offline_hold(self):
        _write_state(self.tmp, state="offline", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.state, "offline")

    def test_unknown_hold(self):
        _write_state(self.tmp, state="unknown", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.reason, REASON_NON_IDLE_STATE)

    def test_all_non_idle_states_hold(self):
        non_idle = ALLOWED_STATES - {"idle"}
        for s in sorted(non_idle):
            tmp = Path(tempfile.mkdtemp())
            try:
                _write_state(tmp, state=s, age_seconds=5)
                result = evaluate_kso_runtime_gate(tmp)
                self.assertFalse(result.play_allowed,
                    f"state={s} should be hold, got play_allowed={result.play_allowed}")
                self.assertEqual(result.action, ACTION_HOLD,
                    f"state={s} action should be hold")
                self.assertEqual(result.state, s)
            finally:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Tests: missing / invalid state file
# ══════════════════════════════════════════════════════════════════════

class TestMissingInvalidFile(TestCase):
    """Missing file, invalid JSON, broken schema → hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_hold(self):
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.action, ACTION_HOLD)
        self.assertEqual(result.reason, REASON_MISSING_STATE_FILE)
        self.assertEqual(result.age_bucket, AGE_UNKNOWN)

    def test_invalid_json_hold(self):
        _write_raw_state(self.tmp, "not valid json {{{")
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_INVALID_JSON)

    def test_json_array_hold(self):
        _write_raw_state(self.tmp, '[{"state": "idle"}]')
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_SCHEMA_MISMATCH)

    def test_json_number_hold(self):
        _write_raw_state(self.tmp, "42")
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertFalse(result.play_allowed)

    def test_empty_file_hold(self):
        _write_raw_state(self.tmp, "")
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_INVALID_JSON)


# ══════════════════════════════════════════════════════════════════════
# Tests: missing / invalid state field
# ══════════════════════════════════════════════════════════════════════

class TestInvalidStateField(TestCase):
    """State field missing, wrong type, or invalid value → hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_state_field(self):
        state_dir = self.tmp / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "test",
        }
        (state_dir / STATE_FILE).write_text(json.dumps(data))
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_INVALID_STATE)

    def test_state_not_string(self):
        state_dir = self.tmp / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "state": 123,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        (state_dir / STATE_FILE).write_text(json.dumps(data))
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_INVALID_STATE)

    def test_invalid_state_value(self):
        _write_state(self.tmp, state="playing", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_INVALID_STATE)


# ══════════════════════════════════════════════════════════════════════
# Tests: timestamp issues
# ══════════════════════════════════════════════════════════════════════

class TestTimestampIssues(TestCase):
    """Missing/invalid/stale/future timestamp → hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_updated_at(self):
        state_dir = self.tmp / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        data = {"state": "idle", "source": "test"}
        (state_dir / STATE_FILE).write_text(json.dumps(data))
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_MISSING_UPDATED_AT)

    def test_invalid_timestamp(self):
        state_dir = self.tmp / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "state": "idle",
            "updated_at_utc": "not-a-timestamp",
        }
        (state_dir / STATE_FILE).write_text(json.dumps(data))
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_INVALID_UPDATED_AT)

    def test_empty_timestamp(self):
        state_dir = self.tmp / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "state": "idle",
            "updated_at_utc": "",
        }
        (state_dir / STATE_FILE).write_text(json.dumps(data))
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_INVALID_UPDATED_AT)

    def test_stale_timestamp_hold(self):
        _write_state(self.tmp, state="idle", age_seconds=60)
        result = evaluate_kso_runtime_gate(self.tmp, stale_seconds=30)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_STALE_STATE)
        self.assertEqual(result.age_bucket, AGE_STALE)
        self.assertFalse(result.fresh)

    def test_stale_timestamp_with_custom_threshold(self):
        _write_state(self.tmp, state="idle", age_seconds=15)
        result = evaluate_kso_runtime_gate(self.tmp, stale_seconds=10)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_STALE_STATE)

    def test_future_timestamp_hold(self):
        state_dir = self.tmp / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        data = {
            "state": "idle",
            "updated_at_utc": future,
        }
        (state_dir / STATE_FILE).write_text(json.dumps(data))
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_FUTURE_TIMESTAMP)

    def test_timestamp_with_Z_suffix(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        # _write_state uses isoformat() which includes +00:00
        # Test that fromisoformat handles it
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertTrue(result.play_allowed)


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid arguments
# ══════════════════════════════════════════════════════════════════════

class TestInvalidArgs(TestCase):
    """Invalid stale_seconds or root → safe error."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stale_seconds_zero(self):
        result = evaluate_kso_runtime_gate(self.tmp, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_stale_seconds_negative(self):
        result = evaluate_kso_runtime_gate(self.tmp, stale_seconds=-5)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_invalid_root_type(self):
        result = evaluate_kso_runtime_gate(None)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)


# ══════════════════════════════════════════════════════════════════════
# Tests: read failure
# ══════════════════════════════════════════════════════════════════════

class TestReadFailure(TestCase):
    """Read failure → safe error, no stacktrace."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_state_is_directory(self):
        state_dir = self.tmp / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / STATE_FILE
        state_path.mkdir()  # directory instead of file

        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_READ_FAILED)
        self.assertFalse(result.play_allowed)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects (player NEVER writes state)
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(TestCase):
    """Player is READ-ONLY — never writes kso_state.json."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_does_not_create_state(self):
        evaluate_kso_runtime_gate(self.tmp)
        state_path = self.tmp / STATE_DIR / STATE_FILE
        self.assertFalse(state_path.exists(),
            "player must NOT create kso_state.json")

    def test_valid_state_does_not_modify(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        state_path = self.tmp / STATE_DIR / STATE_FILE
        before = state_path.read_text()
        evaluate_kso_runtime_gate(self.tmp)
        after = state_path.read_text()
        self.assertEqual(before, after,
            "player must NOT modify kso_state.json")

    def test_only_state_dir_accessed(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        evaluate_kso_runtime_gate(self.tmp)
        # No other dirs should appear
        top_dirs = [d.name for d in self.tmp.iterdir() if d.is_dir()]
        self.assertEqual(top_dirs, ["state"],
            f"unexpected dirs created: {top_dirs}")

    def test_no_sent_quarantine_dry_run_failed(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        evaluate_kso_runtime_gate(self.tmp)
        for bad in ("sent", "quarantine", "dry_run", "failed", "pop"):
            self.assertFalse((self.tmp / bad).exists(),
                f"'{bad}/' should not exist")

    def test_module_no_http_imports(self):
        import kso_player.runtime_gate as mod
        source = open(mod.__file__).read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestOutputSafety(TestCase):
    """Result/repr/format never contains paths, timestamps, secrets."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_play_result_no_path(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        text = repr(result) + format_kso_runtime_gate_result(result)
        self.assertNotIn(str(self.tmp), text)
        self.assertNotIn("kso_state.json", text)
        self.assertNotIn(STATE_FILE, text)

    def test_hold_result_no_path(self):
        _write_state(self.tmp, state="transaction", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        text = repr(result) + format_kso_runtime_gate_result(result)
        self.assertNotIn("kso_state.json", text)

    def test_missing_result_no_path(self):
        result = evaluate_kso_runtime_gate(self.tmp)
        text = repr(result) + format_kso_runtime_gate_result(result)
        self.assertNotIn("kso_state.json", text)

    def test_result_no_raw_timestamp(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        text = repr(result) + format_kso_runtime_gate_result(result)
        self.assertNotIn("2026", text)
        self.assertNotIn("+00:00", text)

    def test_result_no_source_value(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        text = repr(result) + format_kso_runtime_gate_result(result)
        self.assertNotIn("ukm4_state_adapter", text)

    def test_result_no_forbidden(self):
        _write_state(self.tmp, state="idle", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        text = repr(result) + format_kso_runtime_gate_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_error_result_no_stacktrace(self):
        result = evaluate_kso_runtime_gate(self.tmp, stale_seconds=0)
        text = repr(result) + format_kso_runtime_gate_result(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("line ", text)

    def test_all_reasons_safe(self):
        for reason in [
            REASON_PLAY_ALLOWED, REASON_MISSING_STATE_FILE,
            REASON_INVALID_JSON, REASON_SCHEMA_MISMATCH,
            REASON_INVALID_STATE, REASON_MISSING_UPDATED_AT,
            REASON_INVALID_UPDATED_AT, REASON_STALE_STATE,
            REASON_FUTURE_TIMESTAMP, REASON_NON_IDLE_STATE,
            REASON_READ_FAILED, REASON_INVALID_ARGS,
        ]:
            result = KsoRuntimeGateResult(reason=reason, action=ACTION_HOLD)
            text = format_kso_runtime_gate_result(result)
            self.assertTrue(_no_forbidden(text),
                f"reason={reason}: forbidden in format")


# ══════════════════════════════════════════════════════════════════════
# Tests: receipt as state (special case — hold but allowed value)
# ══════════════════════════════════════════════════════════════════════

class TestReceiptState(TestCase):
    """receipt is a valid KSO state, but always causes hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_receipt_is_allowed_state(self):
        self.assertIn("receipt", ALLOWED_STATES)

    def test_receipt_causes_hold(self):
        _write_state(self.tmp, state="receipt", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.state, "receipt")
        self.assertTrue(result.state_valid)
        self.assertEqual(result.reason, REASON_NON_IDLE_STATE)

    def test_receipt_in_output_is_safe(self):
        _write_state(self.tmp, state="receipt", age_seconds=5)
        result = evaluate_kso_runtime_gate(self.tmp)
        text = repr(result) + format_kso_runtime_gate_result(result)
        # "receipt" as safety_state is allowed
        self.assertIn("receipt", text)
        # But no receipt_data/receipt_number forbidden
        self.assertNotIn("receipt_data", text)
        self.assertNotIn("receipt_number", text)


if __name__ == "__main__":
    import unittest
    unittest.main()
