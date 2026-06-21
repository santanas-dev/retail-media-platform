"""KSO State Adapter — Daemon + CLI Tests."""

import json as _json
import shutil
import sys as _sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from kso_state_adapter.state_model import (
    KsoState,
    STATE_IDLE,
    STATE_UNKNOWN,
    STATE_ERROR,
    STATE_TRANSACTION,
    FORBIDDEN_STATE_KEYS,
)
from kso_state_adapter.state_writer import STATE_DIR, STATE_FILE
from kso_state_adapter.source import (
    StaticStateSource,
    SequenceStateSource,
    ErroringStateSource,
)
from kso_state_adapter.daemon import (
    run_kso_state_adapter_daemon,
    KsoStateAdapterDaemonResult,
    format_daemon_result,
    DAEMON_STATUS_STOPPED,
    DAEMON_STATUS_ERROR,
    REASON_MAX_CYCLES,
    REASON_STOP_CHECK,
    REASON_MAX_ERRORS,
    REASON_INVALID_ARGS,
)

FORBIDDEN = frozenset({
    "receipt_number", "card_number", "customer_id", "phone",
    "token", "secret", "stacktrace",
})


def _assert_safe(test, output: str):
    lower = output.lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, lower, f"Safe output: {output[:200]}")


def _noop_sleep(seconds: float):
    pass


class TestStateDaemon(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_sad_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_max_cycles_works(self):
        source = StaticStateSource(state=STATE_IDLE)
        result = run_kso_state_adapter_daemon(
            self.tmp, source, max_cycles=3,
            sleep_fn=_noop_sleep, interval_seconds=0,
        )
        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.cycles_completed, 3)
        self.assertEqual(result.reason, REASON_MAX_CYCLES)
        self.assertTrue(result.state_written)
        self.assertEqual(result.last_state, STATE_IDLE)
        _assert_safe(self, format_daemon_result(result))

    def test_stop_check_works(self):
        source = StaticStateSource(state=STATE_IDLE)
        calls = [0]

        def stop_check():
            calls[0] += 1
            return calls[0] >= 2

        result = run_kso_state_adapter_daemon(
            self.tmp, source, stop_check=stop_check,
            sleep_fn=_noop_sleep, interval_seconds=0,
        )
        self.assertEqual(result.reason, REASON_STOP_CHECK)
        self.assertEqual(result.cycles_completed, 1)
        _assert_safe(self, format_daemon_result(result))

    def test_source_error_writes_error_not_idle(self):
        source = ErroringStateSource()
        result = run_kso_state_adapter_daemon(
            self.tmp, source, max_cycles=1,
            sleep_fn=_noop_sleep, interval_seconds=0,
        )
        self.assertEqual(result.last_state, STATE_ERROR,
                         "Source error must write error, NEVER idle")
        self.assertNotEqual(result.last_state, STATE_IDLE)
        _assert_safe(self, format_daemon_result(result))

    def test_sequence_source(self):
        source = SequenceStateSource(["idle", "transaction", "payment"])
        result = run_kso_state_adapter_daemon(
            self.tmp, source, max_cycles=3,
            sleep_fn=_noop_sleep, interval_seconds=0,
        )
        self.assertEqual(result.cycles_completed, 3)
        # Last state should be "payment"
        self.assertEqual(result.last_state, "payment")
        _assert_safe(self, format_daemon_result(result))

    def test_max_consecutive_errors_stops(self):
        source = ErroringStateSource()
        result = run_kso_state_adapter_daemon(
            self.tmp, source, max_cycles=5,
            max_consecutive_errors=2,
            sleep_fn=_noop_sleep, interval_seconds=0,
        )
        self.assertEqual(result.status, DAEMON_STATUS_ERROR)
        self.assertEqual(result.reason, REASON_MAX_ERRORS)
        self.assertEqual(result.cycles_completed, 2)
        _assert_safe(self, format_daemon_result(result))

    def test_health_file_written(self):
        health_path = self.tmp / "adapter-health.json"
        source = StaticStateSource(state=STATE_IDLE)
        result = run_kso_state_adapter_daemon(
            self.tmp, source, max_cycles=1,
            sleep_fn=_noop_sleep, interval_seconds=0,
            health_file=str(health_path),
        )
        self.assertTrue(result.health_written)
        self.assertTrue(health_path.exists())

        data = _json.loads(health_path.read_text())
        self.assertIn("status", data)
        self.assertIn("last_state", data)
        self.assertIn("cycles_completed", data)

        # No forbidden keys in health
        raw = health_path.read_text().lower()
        for fb in FORBIDDEN_STATE_KEYS:
            self.assertNotIn(fb, raw, f"Health: '{fb}'")

    def test_health_file_safe(self):
        health_path = self.tmp / "adapter-health.json"
        source = StaticStateSource(state=STATE_TRANSACTION)
        result = run_kso_state_adapter_daemon(
            self.tmp, source, max_cycles=1,
            sleep_fn=_noop_sleep, interval_seconds=0,
            health_file=str(health_path),
        )
        data = _json.loads(health_path.read_text())
        # Only safe fields
        for key in data:
            allowed = {"status", "last_state", "cycles_completed",
                        "error_count", "last_reason"}
            self.assertIn(key, allowed, f"Health key '{key}' not allowed")
        _assert_safe(self, format_daemon_result(result))

    def test_invalid_args(self):
        result = run_kso_state_adapter_daemon(
            self.tmp, None, max_cycles=1,
        )
        self.assertEqual(result.status, DAEMON_STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)
        _assert_safe(self, format_daemon_result(result))

    def test_result_repr_safe(self):
        source = StaticStateSource(state=STATE_IDLE)
        result = run_kso_state_adapter_daemon(
            self.tmp, source, max_cycles=1,
            sleep_fn=_noop_sleep,
        )
        _assert_safe(self, repr(result))
        _assert_safe(self, format_daemon_result(result))


class TestStateDAEMonPlayerCompat(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_sad_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_player_gate_reads_adapter_idle_as_play(self):
        """Player gate must allow play for adapter-written idle."""
        source = StaticStateSource(state=STATE_IDLE)
        run_kso_state_adapter_daemon(
            self.tmp, source, max_cycles=1,
            sleep_fn=_noop_sleep, interval_seconds=0,
        )

        import sys as _s, os as _o
        _s.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "kso_player"))
        from kso_player.runtime_gate import evaluate_kso_runtime_gate, ACTION_PLAY

        result = evaluate_kso_runtime_gate(self.tmp, stale_seconds=30)
        self.assertTrue(result.play_allowed,
                        "Gate must allow play for adapter-idle")
        self.assertEqual(result.action, ACTION_PLAY)

    def test_player_gate_holds_for_adapter_non_idle(self):
        """Player gate must hold for non-idle states."""
        for state in ("transaction", "payment", "receipt", "unknown"):
            source = StaticStateSource(state=state)
            run_kso_state_adapter_daemon(
                self.tmp, source, max_cycles=1,
                sleep_fn=_noop_sleep, interval_seconds=0,
            )

            import sys as _s, os as _o
            _s.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "kso_player"))
            from kso_player.runtime_gate import evaluate_kso_runtime_gate, ACTION_HOLD

            result = evaluate_kso_runtime_gate(self.tmp, stale_seconds=30)
            self.assertFalse(result.play_allowed,
                             f"Gate must hold for state '{state}'")
            self.assertEqual(result.action, ACTION_HOLD,
                             f"Gate action must be hold for '{state}'")


class TestStateCLI(unittest.TestCase):

    def test_write_once_help(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "kso_state_adapter.cli", "write-once", "--help"],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
        )
        self.assertEqual(result.returncode, 0)

    def test_daemon_help(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "kso_state_adapter.cli", "daemon", "--help"],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
        )
        self.assertEqual(result.returncode, 0)

    def test_version(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "kso_state_adapter.cli", "version"],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("kso-state-adapter", result.stdout)


if __name__ == "__main__":
    unittest.main()
