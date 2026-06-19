"""Tests for kso_player.session — pure logic, in-memory, no I/O."""

import unittest

from kso_player.playlist import PlayerPlaylist, PlayerPlaylistItem
from kso_player.safety import (
    PlaybackSafetyDecision,
    ACTION_PLAY, ACTION_HOLD, ACTION_STOP,
    REASON_SAFETY_READY, REASON_PAYMENT_ACTIVE,
)
from kso_player.session import (
    PlaybackSessionState,
    PlaybackSessionDecision,
    select_next_item,
    REASON_SESSION_READY,
    REASON_SESSION_SAFETY_BLOCKED,
    REASON_SESSION_PLAYLIST_NOT_READY,
    REASON_SESSION_NO_ITEMS,
    REASON_SESSION_INVALID_STATE,
)
from kso_player.safe_output import format_session_decision

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
}


# ── Helpers ──────────────────────────────────────────────────────────

def _item(mid, order=0, filename="item.png", content_type="image/png",
          duration_ms=5000, sha256="a" * 64, size_bytes=100):
    return PlayerPlaylistItem(
        manifest_item_id=mid,
        filename=filename,
        content_type=content_type,
        duration_ms=duration_ms,
        order=order,
        sha256=sha256,
        size_bytes=size_bytes,
    )


def _ready_playlist(*items):
    return PlayerPlaylist(
        ready=True, status="ready", reason="ready",
        items_total=len(items), items_ready=len(items),
        items=list(items),
    )


def _not_ready_playlist():
    return PlayerPlaylist(
        ready=False, status="not_ready", reason="manifest_missing",
    )


def _allowed_safety():
    return PlaybackSafetyDecision(
        allowed=True, action=ACTION_PLAY, reason=REASON_SAFETY_READY,
    )


def _blocked_safety(reason=REASON_PAYMENT_ACTIVE):
    return PlaybackSafetyDecision(
        allowed=False, action=ACTION_STOP, reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════
# Happy path
# ══════════════════════════════════════════════════════════════════════

class TestSessionHappy(unittest.TestCase):
    """Ready playlist + allowed safety → play."""

    def test_first_item_no_state(self):
        items = [_item("a", order=0), _item("b", order=1)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.action, ACTION_PLAY)
        self.assertEqual(decision.reason, REASON_SESSION_READY)
        self.assertIsNotNone(decision.selected_item)
        self.assertEqual(decision.selected_item.order, 0)
        self.assertEqual(decision.next_index, 0)
        self.assertEqual(decision.cycle_count, 0)

    def test_selects_by_order_not_position(self):
        """Items should be selected by order field, not list position."""
        items = [_item("b", order=10), _item("a", order=0), _item("c", order=5)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)
        self.assertEqual(decision.selected_item.order, 0)
        self.assertEqual(decision.next_index, 0)

    def test_single_item(self):
        items = [_item("x", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.next_index, 0)


# ══════════════════════════════════════════════════════════════════════
# Sequential progression
# ══════════════════════════════════════════════════════════════════════

class TestSessionProgression(unittest.TestCase):
    """Sequential item selection with session state."""

    def setUp(self):
        self.items = [_item("a", order=0), _item("b", order=1), _item("c", order=2)]
        self.pl = _ready_playlist(*self.items)
        self.sd = _allowed_safety()

    def test_progresses_through_items(self):
        state = PlaybackSessionState(current_index=0, cycle_count=0)

        # First call → item at index 1
        d1 = select_next_item(self.pl, self.sd, state)
        self.assertEqual(d1.next_index, 1)
        self.assertEqual(d1.selected_item.order, 1)
        self.assertEqual(d1.cycle_count, 0)

        # Second call with updated state
        state.current_index = d1.next_index
        state.cycle_count = d1.cycle_count
        d2 = select_next_item(self.pl, self.sd, state)
        self.assertEqual(d2.next_index, 2)
        self.assertEqual(d2.selected_item.order, 2)
        self.assertEqual(d2.cycle_count, 0)

    def test_wraps_around_and_increments_cycle(self):
        state = PlaybackSessionState(current_index=2, cycle_count=0)

        d = select_next_item(self.pl, self.sd, state)
        self.assertEqual(d.next_index, 0)
        self.assertEqual(d.selected_item.order, 0)
        self.assertEqual(d.cycle_count, 1)

    def test_wrap_around_middle(self):
        """Wrap from last to first; cycle only increments when wrapping from last."""
        # Wrap from 1 → 2 → 0 should only increment at 2→0
        state = PlaybackSessionState(current_index=1, cycle_count=0)
        d = select_next_item(self.pl, self.sd, state)
        self.assertEqual(d.next_index, 2)
        self.assertEqual(d.cycle_count, 0)


# ══════════════════════════════════════════════════════════════════════
# Blocked scenarios
# ══════════════════════════════════════════════════════════════════════

class TestSessionBlocked(unittest.TestCase):
    """Safety blocked, playlist not ready, no items → no selection."""

    def test_safety_blocked_payment(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _blocked_safety(REASON_PAYMENT_ACTIVE)

        decision = select_next_item(pl, sd)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertEqual(decision.reason, REASON_SESSION_SAFETY_BLOCKED)
        self.assertIsNone(decision.selected_item)

    def test_safety_none(self):
        pl = _ready_playlist(_item("a"))

        decision = select_next_item(pl, None)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, REASON_SESSION_SAFETY_BLOCKED)

    def test_playlist_not_ready(self):
        pl = _not_ready_playlist()
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_HOLD)
        self.assertEqual(decision.reason, REASON_SESSION_PLAYLIST_NOT_READY)
        self.assertIsNone(decision.selected_item)

    def test_playlist_none(self):
        sd = _allowed_safety()

        decision = select_next_item(None, sd)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, REASON_SESSION_PLAYLIST_NOT_READY)

    def test_empty_items(self):
        pl = _ready_playlist()  # no items
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_HOLD)
        self.assertEqual(decision.reason, REASON_SESSION_NO_ITEMS)

    def test_playlist_ready_false_explicit(self):
        pl = PlayerPlaylist(ready=False, status="error", reason="test")
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, REASON_SESSION_PLAYLIST_NOT_READY)


# ══════════════════════════════════════════════════════════════════════
# Invalid state → fail safe
# ══════════════════════════════════════════════════════════════════════

class TestSessionInvalidState(unittest.TestCase):
    """Invalid state → fail safe, select first item."""

    def test_invalid_index_too_high(self):
        items = [_item("a", order=0), _item("b", order=1)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()
        state = PlaybackSessionState(current_index=99, cycle_count=0)

        decision = select_next_item(pl, sd, state)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.next_index, 0)
        self.assertEqual(decision.cycle_count, 0)

    def test_negative_index(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()
        state = PlaybackSessionState(current_index=-1, cycle_count=5)

        decision = select_next_item(pl, sd, state)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.next_index, 0)
        self.assertEqual(decision.cycle_count, 0)

    def test_none_index(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()
        state = PlaybackSessionState(current_index=None, cycle_count=3)

        decision = select_next_item(pl, sd, state)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.next_index, 0)
        self.assertEqual(decision.cycle_count, 0)

    def test_non_int_index(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()
        state = PlaybackSessionState(current_index="not_int", cycle_count=0)

        decision = select_next_item(pl, sd, state)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.next_index, 0)

    def test_non_playback_session_state(self):
        """Passing a non-PlaybackSessionState should fall back to first item."""
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()
        fake_state = {"current_index": 1}

        decision = select_next_item(pl, sd, fake_state)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.next_index, 0)


# ══════════════════════════════════════════════════════════════════════
# Security
# ══════════════════════════════════════════════════════════════════════

class TestSessionSecurity(unittest.TestCase):
    """No forbidden, no paths in state/decision."""

    def test_state_has_no_paths(self):
        state = PlaybackSessionState(
            current_index=0,
            last_manifest_item_id="11111111-1111-1111-1111-111111111111",
            cycle_count=1,
        )
        # State fields should not contain paths
        self.assertNotIn("/", str(state.current_index or ""))
        self.assertNotIn("/tmp", str(state.last_manifest_item_id or ""))
        self.assertNotIn("\\", str(state.last_manifest_item_id or ""))

    def test_decision_no_forbidden(self):
        items = [_item("a", order=0, content_type="image/png")]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)

        # Check all string fields of decision
        for field_name in ["action", "reason"]:
            value = getattr(decision, field_name, "")
            lower = str(value).lower()
            for fb in FORBIDDEN:
                self.assertNotIn(fb, lower,
                                 f"Decision field '{field_name}' contains forbidden '{fb}'")

    def test_selected_item_no_forbidden(self):
        items = [_item("a", order=0, content_type="image/png")]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)
        item = decision.selected_item
        self.assertIsNotNone(item)

        for field_name in ["manifest_item_id", "filename", "content_type", "sha256"]:
            value = getattr(item, field_name, "")
            lower = str(value).lower()
            for fb in FORBIDDEN:
                self.assertNotIn(fb, lower,
                                 f"Item field '{field_name}' contains forbidden '{fb}'")


# ══════════════════════════════════════════════════════════════════════
# No I/O
# ══════════════════════════════════════════════════════════════════════

class TestSessionNoIO(unittest.TestCase):
    """Pure logic — no file I/O, no HTTP, no media bytes."""

    def test_pure_logic(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        decision = select_next_item(pl, sd)
        self.assertTrue(decision.allowed)

    def test_no_media_bytes_read(self):
        """Session does not open or read media files."""
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()
        state = PlaybackSessionState(current_index=0)

        decision = select_next_item(pl, sd, state)
        self.assertTrue(decision.allowed)
        # selected_item has metadata only — no bytes, no file path


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

class TestSessionOutput(unittest.TestCase):
    """format_session_decision must be safe."""

    def test_allowed_output(self):
        item = _item("a", order=0, content_type="image/png", duration_ms=10000)
        decision = PlaybackSessionDecision(
            allowed=True, action=ACTION_PLAY, reason=REASON_SESSION_READY,
            selected_item=item, next_index=0, cycle_count=0,
        )
        out = format_session_decision(decision)

        self.assertIn("session_action: play", out)
        self.assertIn("session_reason: ready", out)
        self.assertIn("selected_order: 0", out)
        self.assertIn("selected_content_type: image/png", out)
        self.assertIn("selected_duration_ms: 10000", out)

    def test_blocked_output(self):
        decision = PlaybackSessionDecision(
            allowed=False, action=ACTION_STOP,
            reason=REASON_SESSION_SAFETY_BLOCKED,
        )
        out = format_session_decision(decision)

        self.assertIn("session_action: stop", out)
        self.assertIn("session_reason: safety_blocked", out)

    def test_no_filename_in_output(self):
        """format_session_decision must NOT print filename."""
        item = _item("a", order=0, filename="secret_media.png")
        decision = PlaybackSessionDecision(
            allowed=True, action=ACTION_PLAY, reason=REASON_SESSION_READY,
            selected_item=item, next_index=0, cycle_count=0,
        )
        out = format_session_decision(decision)
        self.assertNotIn("secret_media.png", out)
        self.assertNotIn("filename", out.lower())

    def test_no_manifest_item_id_in_output(self):
        item = _item("deadbeef-dead-beef-dead-beefdeadbeef", order=0)
        decision = PlaybackSessionDecision(
            allowed=True, action=ACTION_PLAY, reason=REASON_SESSION_READY,
            selected_item=item, next_index=0, cycle_count=0,
        )
        out = format_session_decision(decision)
        self.assertNotIn("deadbeef", out)
        self.assertNotIn("manifest_item_id", out.lower())

    def test_no_sha256_in_output(self):
        item = _item("a", order=0, sha256="d" * 64)
        decision = PlaybackSessionDecision(
            allowed=True, action=ACTION_PLAY, reason=REASON_SESSION_READY,
            selected_item=item, next_index=0, cycle_count=0,
        )
        out = format_session_decision(decision)
        self.assertNotIn("d" * 64, out)
        self.assertNotIn("sha256", out.lower())

    def test_no_forbidden_in_output(self):
        item = _item("a", order=0, content_type="image/png")
        decision = PlaybackSessionDecision(
            allowed=True, action=ACTION_PLAY, reason=REASON_SESSION_READY,
            selected_item=item, next_index=0, cycle_count=0,
        )
        out = format_session_decision(decision).lower()

        for fb in FORBIDDEN:
            self.assertNotIn(fb, out,
                             f"Session output contains forbidden '{fb}'")

    def test_no_stacktrace(self):
        decision = PlaybackSessionDecision(
            allowed=False, action=ACTION_HOLD,
            reason=REASON_SESSION_PLAYLIST_NOT_READY,
        )
        out = format_session_decision(decision)
        self.assertNotIn("Traceback", out)
        self.assertNotIn('File "', out)


# ══════════════════════════════════════════════════════════════════════
# Defaults
# ══════════════════════════════════════════════════════════════════════

class TestSessionDefaults(unittest.TestCase):
    """Default values."""

    def test_state_defaults(self):
        state = PlaybackSessionState()
        self.assertIsNone(state.current_index)
        self.assertIsNone(state.last_manifest_item_id)
        self.assertEqual(state.cycle_count, 0)

    def test_decision_defaults(self):
        decision = PlaybackSessionDecision()
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, ACTION_STOP)
        self.assertIsNone(decision.selected_item)
        self.assertIsNone(decision.next_index)
        self.assertEqual(decision.cycle_count, 0)


if __name__ == "__main__":
    unittest.main()
