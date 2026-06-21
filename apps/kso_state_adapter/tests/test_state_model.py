"""KSO State Adapter — State Model Tests."""

import unittest
from datetime import datetime, timezone

from kso_state_adapter.state_model import (
    KsoState,
    ALLOWED_STATES,
    STATE_IDLE,
    STATE_TRANSACTION,
    STATE_UNKNOWN,
    STATE_ERROR,
    STATE_RECEIPT,
    validate_state_dict,
    FORBIDDEN_STATE_KEYS,
)


class TestStateModel(unittest.TestCase):

    def test_valid_states_accepted(self):
        for s in ALLOWED_STATES:
            state = KsoState(state=s)
            self.assertEqual(state.state, s)

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError):
            KsoState(state="invalid_state")

    def test_empty_state_rejected(self):
        with self.assertRaises(ValueError):
            KsoState(state="")

    def test_default_source(self):
        state = KsoState(state=STATE_IDLE)
        self.assertEqual(state.source, "ukm4_state_adapter")

    def test_updated_at_utc_auto_set(self):
        state = KsoState(state=STATE_IDLE)
        self.assertTrue(state.updated_at_utc)
        # Parseable as ISO8601
        dt = datetime.fromisoformat(state.updated_at_utc)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_custom_updated_at_utc(self):
        ts = "2026-01-01T12:00:00+00:00"
        state = KsoState(state=STATE_IDLE, updated_at_utc=ts)
        self.assertEqual(state.updated_at_utc, ts)

    def test_to_dict_format(self):
        state = KsoState(state=STATE_IDLE, updated_at_utc="2026-01-01T12:00:00Z")
        d = state.to_dict()
        self.assertEqual(d["state"], "idle")
        self.assertEqual(d["updated_at_utc"], "2026-01-01T12:00:00Z")
        self.assertEqual(d["source"], "ukm4_state_adapter")
        self.assertEqual(d["schema_version"], 1)

    def test_validate_forbidden_clean_state(self):
        state = KsoState(state=STATE_IDLE)
        self.assertIsNone(state.validate_forbidden())

    def test_repr_safe(self):
        state = KsoState(state=STATE_IDLE)
        r = repr(state)
        self.assertIn("state='idle'", r)
        for fb in FORBIDDEN_STATE_KEYS:
            self.assertNotIn(fb, r.lower())

    def test_validate_state_dict_clean(self):
        self.assertIsNone(validate_state_dict({
            "state": "idle",
            "updated_at_utc": "2026-01-01T12:00:00Z",
            "source": "ukm4_state_adapter",
        }))

    def test_validate_state_dict_forbidden(self):
        for key in ("receipt_number", "card_number", "customer_id", "phone"):
            err = validate_state_dict({key: "value"})
            self.assertIsNotNone(err, f"Must reject forbidden key '{key}'")

    def test_serialize_then_gate_read(self):
        """Simulate player runtime_gate reading adapter output."""
        state = KsoState(state=STATE_IDLE)
        import json
        data = state.to_dict()
        raw = json.dumps(data)

        # Simulate gate parsing
        parsed = json.loads(raw)
        self.assertEqual(parsed["state"], "idle")
        self.assertIn("updated_at_utc", parsed)
        self.assertEqual(parsed["source"], "ukm4_state_adapter")

        # Gate-compatible: has state and updated_at_utc
        self.assertIn("state", parsed)
        self.assertIn("updated_at_utc", parsed)


if __name__ == "__main__":
    unittest.main()
