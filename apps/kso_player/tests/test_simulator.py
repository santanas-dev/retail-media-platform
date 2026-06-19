"""Tests for kso_player.simulator — simulated playback step, pure logic."""

import unittest
from pathlib import Path

from kso_player.playlist import PlayerPlaylist, PlayerPlaylistItem
from kso_player.safety import (
    PlaybackSafetyDecision,
    ACTION_PLAY, ACTION_HOLD, ACTION_STOP,
    REASON_SAFETY_READY, REASON_PAYMENT_ACTIVE,
)
from kso_player.session import (
    PlaybackSessionState,
    REASON_SESSION_SAFETY_BLOCKED,
)
from kso_player.simulator import (
    PlaybackSimulationResult,
    simulate_playback_step,
    SIM_STATUS_WOULD_PLAY,
    SIM_STATUS_BLOCKED,
    SIM_STATUS_NOT_READY,
    SIM_STATUS_ERROR,
)
from kso_player.safe_output import format_simulation_result

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
}


def _item(mid, order=0, content_type="image/png", duration_ms=5000):
    return PlayerPlaylistItem(
        manifest_item_id=mid, filename=f"{mid}.png",
        content_type=content_type, duration_ms=duration_ms,
        order=order, sha256="a" * 64, size_bytes=100,
    )


def _ready_playlist(*items):
    return PlayerPlaylist(
        ready=True, status="ready", reason="ready",
        items_total=len(items), items_ready=len(items),
        items=list(items),
    )


def _not_ready_playlist():
    return PlayerPlaylist(ready=False, status="not_ready", reason="manifest_missing")


def _allowed_safety():
    return PlaybackSafetyDecision(allowed=True, action=ACTION_PLAY, reason=REASON_SAFETY_READY)


def _blocked_safety():
    return PlaybackSafetyDecision(allowed=False, action=ACTION_STOP, reason=REASON_PAYMENT_ACTIVE)


# ══════════════════════════════════════════════════════════════════════
# Happy path
# ══════════════════════════════════════════════════════════════════════

class TestSimulatorHappy(unittest.TestCase):
    """Ready playlist + allowed safety → would_play."""

    def test_would_play(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        result = simulate_playback_step(pl, sd, now="2026-06-20T10:00:00")

        self.assertEqual(result.simulated_status, SIM_STATUS_WOULD_PLAY)
        self.assertEqual(result.session_action, "play")
        self.assertEqual(result.session_reason, "ready")
        self.assertEqual(result.selected_order, 0)
        self.assertEqual(result.selected_content_type, "image/png")
        self.assertEqual(result.selected_duration_ms, 5000)

    def test_timestamps_set(self):
        items = [_item("a", order=0, duration_ms=10000)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        result = simulate_playback_step(pl, sd, now="2026-06-20T10:00:00")

        self.assertEqual(result.started_at, "2026-06-20T10:00:00")
        self.assertIsNotNone(result.would_end_at)
        self.assertNotEqual(result.would_end_at, result.started_at)

    def test_would_end_at_calculated(self):
        items = [_item("a", order=0, duration_ms=10000)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        result = simulate_playback_step(pl, sd, now="2026-06-20T10:00:00")
        self.assertIn("10:00:10", result.would_end_at)

    def test_zero_duration_same_timestamp(self):
        items = [_item("a", order=0, duration_ms=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        result = simulate_playback_step(pl, sd, now="2026-06-20T10:00:00")
        self.assertEqual(result.would_end_at, result.started_at)

    def test_no_sleep_no_wait(self):
        """Simulation must NOT introduce any real delay."""
        import time
        items = [_item("a", order=0, duration_ms=60000)]  # 60 seconds
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        t0 = time.time()
        result = simulate_playback_step(pl, sd)
        elapsed = time.time() - t0

        self.assertEqual(result.simulated_status, SIM_STATUS_WOULD_PLAY)
        self.assertLess(elapsed, 0.1, "Simulation should take <100ms, not 60s")


# ══════════════════════════════════════════════════════════════════════
# Blocked / not ready
# ══════════════════════════════════════════════════════════════════════

class TestSimulatorBlocked(unittest.TestCase):
    """Blocked safety → blocked status."""

    def test_safety_blocked(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _blocked_safety()

        result = simulate_playback_step(pl, sd)

        self.assertEqual(result.simulated_status, SIM_STATUS_BLOCKED)
        self.assertEqual(result.session_action, "stop")
        self.assertEqual(result.session_reason, REASON_SESSION_SAFETY_BLOCKED)
        self.assertIsNone(result.selected_order)

    def test_playlist_not_ready(self):
        pl = _not_ready_playlist()
        sd = _allowed_safety()

        result = simulate_playback_step(pl, sd)

        self.assertEqual(result.simulated_status, SIM_STATUS_NOT_READY)
        self.assertEqual(result.session_action, "hold")
        self.assertIsNone(result.selected_order)


# ══════════════════════════════════════════════════════════════════════
# Sequential progression
# ══════════════════════════════════════════════════════════════════════

class TestSimulatorProgression(unittest.TestCase):
    """Session state progression through items."""

    def test_next_index_returned(self):
        items = [_item("a", order=0), _item("b", order=1)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        result = simulate_playback_step(pl, sd)
        self.assertEqual(result.next_index, 0)
        self.assertEqual(result.cycle_count, 0)

    def test_progression_with_state(self):
        items = [_item("a", order=0), _item("b", order=1), _item("c", order=2)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()
        state = PlaybackSessionState(current_index=1, cycle_count=0)

        result = simulate_playback_step(pl, sd, session_state=state)
        self.assertEqual(result.next_index, 2)
        self.assertEqual(result.selected_order, 2)

    def test_wraps_and_cycles(self):
        items = [_item("a", order=0), _item("b", order=1)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()
        state = PlaybackSessionState(current_index=1, cycle_count=0)

        result = simulate_playback_step(pl, sd, session_state=state)
        self.assertEqual(result.next_index, 0)
        self.assertEqual(result.cycle_count, 1)


# ══════════════════════════════════════════════════════════════════════
# No I/O
# ══════════════════════════════════════════════════════════════════════

class TestSimulatorNoIO(unittest.TestCase):
    """Pure logic — no file I/O, no HTTP, no media bytes."""

    def test_no_media_bytes_read(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        result = simulate_playback_step(pl, sd)
        self.assertEqual(result.simulated_status, SIM_STATUS_WOULD_PLAY)

    def test_no_file_writes(self):
        items = [_item("a", order=0)]
        pl = _ready_playlist(*items)
        sd = _allowed_safety()

        result = simulate_playback_step(pl, sd)
        self.assertEqual(result.simulated_status, SIM_STATUS_WOULD_PLAY)
        # Pure logic — no temporary files, no disk writes


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

class TestSimulatorOutput(unittest.TestCase):
    """format_simulation_result must be safe."""

    def test_would_play_output(self):
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_WOULD_PLAY,
            session_action="play", session_reason="ready",
            selected_order=0, selected_content_type="image/png",
            selected_duration_ms=5000,
        )
        out = format_simulation_result(result)
        self.assertIn("simulation_status: would_play", out)
        self.assertIn("session_action: play", out)
        self.assertIn("selected_order: 0", out)
        self.assertIn("selected_content_type: image/png", out)
        self.assertIn("selected_duration_ms: 5000", out)

    def test_blocked_output(self):
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_BLOCKED,
            session_action="stop", session_reason="safety_blocked",
        )
        out = format_simulation_result(result)
        self.assertIn("simulation_status: blocked", out)
        self.assertIn("session_action: stop", out)

    def test_no_filename_in_output(self):
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_WOULD_PLAY,
            session_action="play", session_reason="ready",
            selected_order=0, selected_content_type="image/png",
            selected_duration_ms=5000,
        )
        out = format_simulation_result(result)
        self.assertNotIn("filename", out.lower())
        self.assertNotIn(".png", out)

    def test_no_manifest_item_id(self):
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_WOULD_PLAY,
            session_action="play", session_reason="ready",
            selected_order=0, selected_content_type="image/png",
            selected_duration_ms=5000,
        )
        out = format_simulation_result(result)
        self.assertNotIn("manifest_item_id", out.lower())
        self.assertNotIn("deadbeef", out)

    def test_no_sha256(self):
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_WOULD_PLAY,
            session_action="play", session_reason="ready",
            selected_order=0, selected_content_type="image/png",
            selected_duration_ms=5000,
        )
        out = format_simulation_result(result)
        self.assertNotIn("sha256", out.lower())

    def test_no_forbidden(self):
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_WOULD_PLAY,
            session_action="play", session_reason="ready",
            selected_order=0, selected_content_type="image/png",
            selected_duration_ms=5000,
        )
        out = format_simulation_result(result).lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, out, f"Simulation output contains forbidden '{fb}'")

    def test_no_stacktrace(self):
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_BLOCKED,
            session_action="stop", session_reason="safety_blocked",
        )
        out = format_simulation_result(result)
        self.assertNotIn("Traceback", out)
        self.assertNotIn('File "', out)


# ══════════════════════════════════════════════════════════════════════
# Defaults
# ══════════════════════════════════════════════════════════════════════

class TestSimulatorDefaults(unittest.TestCase):
    """Default values."""

    def test_default_result(self):
        result = PlaybackSimulationResult()
        self.assertEqual(result.simulated_status, SIM_STATUS_ERROR)
        self.assertEqual(result.session_action, "stop")
        self.assertIsNone(result.selected_order)


if __name__ == "__main__":
    unittest.main()
