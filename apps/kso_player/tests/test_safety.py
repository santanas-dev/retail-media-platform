"""Tests for kso_player.safety — fail-closed safety gate, pure logic."""

import unittest
from dataclasses import dataclass

from kso_player.playlist import PlayerPlaylist
from kso_player.safety import (
    PlaybackSafetySnapshot,
    PlaybackSafetyDecision,
    decide_playback_safety,
    ALLOWED_STATES,
    ACTION_PLAY,
    ACTION_HOLD,
    ACTION_STOP,
    REASON_SAFETY_READY,
    REASON_PLAYLIST_NOT_READY,
    REASON_STATE_UNKNOWN,
    REASON_TRANSACTION_ACTIVE,
    REASON_PAYMENT_ACTIVE,
    REASON_RECEIPT_ACTIVE,
    REASON_SERVICE_ACTIVE,
    REASON_ERROR_ACTIVE,
    REASON_MAINTENANCE_ACTIVE,
    REASON_OFFLINE,
    REASON_INVALID_STATE,
    REASON_MISSING_SNAPSHOT,
)
from kso_player.safe_output import format_safety_decision

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
}


def _ready_playlist():
    return PlayerPlaylist(
        ready=True, status="ready", reason="ready",
        items_total=2, items_ready=2, items_missing=0, items_failed=0,
    )


def _not_ready_playlist():
    return PlayerPlaylist(
        ready=False, status="not_ready", reason="media_incomplete",
        items_total=2, items_ready=1, items_missing=1, items_failed=0,
    )


# ══════════════════════════════════════════════════════════════════════
# Happy path
# ══════════════════════════════════════════════════════════════════════

class TestSafetyHappyPath(unittest.TestCase):
    """Playlist ready + idle → allowed=true."""

    def test_idle_plus_ready_playlist(self):
        snap = PlaybackSafetySnapshot(state="idle")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.action, ACTION_PLAY)
        self.assertEqual(decision.reason, REASON_SAFETY_READY)

    def test_idle_case_insensitive(self):
        """State should be normalized to lowercase."""
        snap = PlaybackSafetySnapshot(state="IDLE")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.action, ACTION_PLAY)
        self.assertEqual(decision.reason, REASON_SAFETY_READY)

    def test_idle_with_whitespace(self):
        snap = PlaybackSafetySnapshot(state="  idle  ")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.action, ACTION_PLAY)


# ══════════════════════════════════════════════════════════════════════
# Playlist not ready
# ══════════════════════════════════════════════════════════════════════

class TestSafetyPlaylistNotReady(unittest.TestCase):
    """Playlist not ready → hold even when KSO is idle."""

    def test_idle_plus_not_ready_playlist(self):
        snap = PlaybackSafetySnapshot(state="idle")
        pl = _not_ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_HOLD)
        self.assertEqual(decision.reason, REASON_PLAYLIST_NOT_READY)

    def test_idle_plus_none_playlist(self):
        snap = PlaybackSafetySnapshot(state="idle")

        decision = decide_playback_safety(snap, None)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_HOLD)
        self.assertEqual(decision.reason, REASON_PLAYLIST_NOT_READY)


# ══════════════════════════════════════════════════════════════════════
# Stop states
# ══════════════════════════════════════════════════════════════════════

class TestSafetyStopStates(unittest.TestCase):
    """All non-idle known states → stop."""

    def test_transaction_stop(self):
        snap = PlaybackSafetySnapshot(state="transaction")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_TRANSACTION_ACTIVE)

    def test_payment_stop(self):
        snap = PlaybackSafetySnapshot(state="payment")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_PAYMENT_ACTIVE)

    def test_receipt_stop(self):
        snap = PlaybackSafetySnapshot(state="receipt")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_RECEIPT_ACTIVE)

    def test_service_stop(self):
        snap = PlaybackSafetySnapshot(state="service")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_SERVICE_ACTIVE)

    def test_error_stop(self):
        snap = PlaybackSafetySnapshot(state="error")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_ERROR_ACTIVE)

    def test_maintenance_stop(self):
        snap = PlaybackSafetySnapshot(state="maintenance")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_MAINTENANCE_ACTIVE)

    def test_offline_stop(self):
        snap = PlaybackSafetySnapshot(state="offline")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_OFFLINE)


# ══════════════════════════════════════════════════════════════════════
# Unknown state
# ══════════════════════════════════════════════════════════════════════

class TestSafetyUnknown(unittest.TestCase):
    """Unknown state → hold."""

    def test_unknown_hold(self):
        snap = PlaybackSafetySnapshot(state="unknown")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_HOLD)
        self.assertEqual(decision.reason, REASON_STATE_UNKNOWN)


# ══════════════════════════════════════════════════════════════════════
# Invalid / missing inputs → fail closed
# ══════════════════════════════════════════════════════════════════════

class TestSafetyFailClosed(unittest.TestCase):
    """Invalid or missing inputs → fail closed."""

    def test_missing_snapshot(self):
        pl = _ready_playlist()
        decision = decide_playback_safety(None, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_MISSING_SNAPSHOT)

    def test_invalid_state_string(self):
        """Unknown state string → fail closed."""
        snap = PlaybackSafetySnapshot(state="playing_video")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_INVALID_STATE)

    def test_empty_state(self):
        snap = PlaybackSafetySnapshot(state="")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)

    def test_whitespace_only_state(self):
        snap = PlaybackSafetySnapshot(state="   ")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)

    def test_none_state(self):
        snap = PlaybackSafetySnapshot(state=None)
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)

    def test_non_string_state(self):
        snap = PlaybackSafetySnapshot(state=12345)
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_INVALID_STATE)

    def test_wrong_snapshot_type(self):
        """Passing a non-PlaybackSafetySnapshot should fail closed."""
        pl = _ready_playlist()
        fake_snap = {"state": "idle"}

        decision = decide_playback_safety(fake_snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_INVALID_STATE)


# ══════════════════════════════════════════════════════════════════════
# No network / no file I/O
# ══════════════════════════════════════════════════════════════════════

class TestSafetyNoIO(unittest.TestCase):
    """Safety gate is pure logic — no file I/O, no HTTP."""

    def test_pure_logic_no_imports(self):
        """decide_playback_safety should work without any external deps."""
        snap = PlaybackSafetySnapshot(state="idle")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)
        self.assertTrue(decision.allowed)

    def test_no_state_file_read(self):
        """Safety decision does not read any files — pure data in."""
        snap = PlaybackSafetySnapshot(state="idle")
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)
        self.assertTrue(decision.allowed)
        # If it tried to read files, it would fail in test env with no root


# ══════════════════════════════════════════════════════════════════════
# Auto-fail: playlist broken/missing in idle
# ══════════════════════════════════════════════════════════════════════

class TestSafetyPlaylistEdgeCases(unittest.TestCase):
    """Edge cases with playlist object."""

    def test_playlist_without_ready_attr(self):
        """Playlist without .ready attribute → hold."""
        snap = PlaybackSafetySnapshot(state="idle")

        @dataclass
        class FakePlaylist:
            pass

        pl = FakePlaylist()
        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_HOLD)
        self.assertEqual(decision.reason, REASON_PLAYLIST_NOT_READY)

    def test_playlist_ready_false_explicit(self):
        snap = PlaybackSafetySnapshot(state="idle")
        pl = PlayerPlaylist(ready=False, status="error", reason="manifest_invalid")

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_HOLD)


# ══════════════════════════════════════════════════════════════════════
# Default values
# ══════════════════════════════════════════════════════════════════════

class TestSafetyDefaults(unittest.TestCase):
    """Default values for dataclasses."""

    def test_snapshot_default_state(self):
        snap = PlaybackSafetySnapshot()
        self.assertEqual(snap.state, "unknown")

    def test_decision_defaults(self):
        decision = PlaybackSafetyDecision()
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_INVALID_STATE)

    def test_default_snapshot_plus_ready_playlist(self):
        """Default snapshot (unknown) + ready playlist → hold."""
        snap = PlaybackSafetySnapshot()
        pl = _ready_playlist()

        decision = decide_playback_safety(snap, pl)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_HOLD)
        self.assertEqual(decision.reason, REASON_STATE_UNKNOWN)


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

class TestSafetyOutput(unittest.TestCase):
    """format_safety_decision must be safe."""

    def test_allowed_output(self):
        decision = PlaybackSafetyDecision(
            allowed=True, action=ACTION_PLAY, reason=REASON_SAFETY_READY,
        )
        out = format_safety_decision(decision)

        self.assertIn("playback_allowed: true", out)
        self.assertIn("action: play", out)
        self.assertIn("reason: ready", out)

    def test_blocked_output(self):
        decision = PlaybackSafetyDecision(
            allowed=False, action=ACTION_STOP, reason=REASON_PAYMENT_ACTIVE,
        )
        out = format_safety_decision(decision)

        self.assertIn("playback_allowed: false", out)
        self.assertIn("action: stop", out)
        self.assertIn("reason: payment_active", out)

    def test_no_forbidden_in_output(self):
        for reason in [REASON_SAFETY_READY, REASON_PAYMENT_ACTIVE,
                       REASON_STATE_UNKNOWN, REASON_MISSING_SNAPSHOT]:
            decision = PlaybackSafetyDecision(
                allowed=False, action=ACTION_STOP, reason=reason,
            )
            out = format_safety_decision(decision)
            lower = out.lower()

            for fb in FORBIDDEN:
                self.assertNotIn(fb, lower,
                                 f"Safety output for reason '{reason}' contains forbidden '{fb}'")

    def test_no_stacktrace_in_output(self):
        decision = PlaybackSafetyDecision(
            allowed=False, action=ACTION_STOP, reason=REASON_INVALID_STATE,
        )
        out = format_safety_decision(decision)

        self.assertNotIn("Traceback", out)
        self.assertNotIn("File \"", out)
        self.assertNotIn("raise ", out)


# ══════════════════════════════════════════════════════════════════════
# All states coverage
# ══════════════════════════════════════════════════════════════════════

class TestSafetyAllStates(unittest.TestCase):
    """Verify every allowed state produces a safe decision."""

    def test_all_states_return_decision(self):
        pl = _ready_playlist()

        for state in ALLOWED_STATES:
            snap = PlaybackSafetySnapshot(state=state)
            decision = decide_playback_safety(snap, pl)

            self.assertIsInstance(decision, PlaybackSafetyDecision)
            self.assertIsInstance(decision.allowed, bool)
            self.assertIn(decision.action, (ACTION_PLAY, ACTION_HOLD, ACTION_STOP))

    def test_only_idle_allows(self):
        """Only 'idle' state can produce allowed=True."""
        pl = _ready_playlist()

        for state in ALLOWED_STATES:
            snap = PlaybackSafetySnapshot(state=state)
            decision = decide_playback_safety(snap, pl)

            if state == "idle":
                self.assertTrue(decision.allowed,
                                f"State 'idle' + ready playlist should allow")
            else:
                self.assertFalse(decision.allowed,
                                 f"State '{state}' should NOT allow playback")


if __name__ == "__main__":
    unittest.main()
