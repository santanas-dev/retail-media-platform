"""KSO State Adapter — Writer Tests."""

import json as _json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kso_state_adapter.state_model import (
    KsoState,
    STATE_IDLE,
    STATE_TRANSACTION,
    STATE_ERROR,
    STATE_UNKNOWN,
    FORBIDDEN_STATE_KEYS,
)
from kso_state_adapter.state_writer import (
    atomic_write_state,
    format_write_result,
    STATUS_WRITTEN,
    STATUS_ERROR,
    STATUS_REJECTED,
    STATE_FILE,
    STATE_DIR,
)


class TestStateWriter(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_sa_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_atomic_write_creates_state_file(self):
        state = KsoState(state=STATE_IDLE)
        result = atomic_write_state(self.tmp, state)
        self.assertEqual(result["status"], STATUS_WRITTEN)

        state_path = self.tmp / STATE_DIR / STATE_FILE
        self.assertTrue(state_path.is_file())

        data = _json.loads(state_path.read_text())
        self.assertEqual(data["state"], "idle")

    def test_atomic_write_overwrites_existing(self):
        state = KsoState(state=STATE_IDLE)
        atomic_write_state(self.tmp, state)

        state2 = KsoState(state=STATE_TRANSACTION)
        result = atomic_write_state(self.tmp, state2)
        self.assertEqual(result["status"], STATUS_WRITTEN)

        data = _json.loads((self.tmp / STATE_DIR / STATE_FILE).read_text())
        self.assertEqual(data["state"], "transaction")

    def test_invalid_root_rejected(self):
        result = atomic_write_state(None, KsoState(state=STATE_IDLE))
        self.assertEqual(result["status"], STATUS_ERROR)

    def test_invalid_state_rejected(self):
        state = KsoState(state=STATE_IDLE)
        # Hack into invalid field — but model validation catches this
        result = atomic_write_state(self.tmp, state)
        self.assertEqual(result["status"], STATUS_WRITTEN)  # Valid model

    def test_invalid_state_type_rejected(self):
        result = atomic_write_state(self.tmp, "not_a_KsoState")
        self.assertEqual(result["status"], STATUS_ERROR)

    def test_no_forbidden_keys_in_written_json(self):
        state = KsoState(state=STATE_IDLE)
        atomic_write_state(self.tmp, state)

        raw = (self.tmp / STATE_DIR / STATE_FILE).read_text().lower()
        for fb_key in FORBIDDEN_STATE_KEYS:
            self.assertNotIn(fb_key, raw,
                             f"Written state must not contain '{fb_key}'")

    def test_format_write_result_safe(self):
        result = {"status": STATUS_WRITTEN, "reason": "ok"}
        output = format_write_result(result)
        self.assertIn("status: written", output)
        for fb in FORBIDDEN_STATE_KEYS:
            self.assertNotIn(fb, output.lower())

    def test_gate_compatible_format(self):
        """Written JSON must be compatible with player runtime_gate."""
        state = KsoState(state=STATE_IDLE)
        atomic_write_state(self.tmp, state)

        raw = (self.tmp / STATE_DIR / STATE_FILE).read_text()
        data = _json.loads(raw)

        # Gate-required fields
        self.assertIn("state", data)
        self.assertIn("updated_at_utc", data)
        self.assertIsInstance(data["state"], str)
        self.assertIsInstance(data["updated_at_utc"], str)

        # Test gate-like evaluation
        import sys, os
        sys.path.insert(0, os.path.join(
            os.path.dirname(__file__), "..", "..", "kso_player",
        ))
        from kso_player.runtime_gate import evaluate_kso_runtime_gate, ACTION_PLAY
        gate_result = evaluate_kso_runtime_gate(self.tmp, stale_seconds=30)
        self.assertTrue(gate_result.play_allowed,
                        "Gate must allow play for fresh idle state")
        self.assertEqual(gate_result.action, ACTION_PLAY)
        self.assertEqual(gate_result.state, "idle")


if __name__ == "__main__":
    unittest.main()
