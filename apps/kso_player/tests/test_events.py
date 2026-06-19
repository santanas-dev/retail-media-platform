"""Tests for kso_player.events — in-memory event draft, no files, no PoP."""

import unittest

from kso_player.simulator import (
    PlaybackSimulationResult,
    SIM_STATUS_WOULD_PLAY,
    SIM_STATUS_BLOCKED,
    SIM_STATUS_NOT_READY,
    SIM_STATUS_ERROR,
)
from kso_player.safety import PlaybackSafetyDecision
from kso_player.events import (
    PlaybackEventDraft,
    build_playback_event_draft,
    EVENT_TYPE_WOULD_PLAY,
    EVENT_TYPE_BLOCKED,
    EVENT_TYPE_NOT_READY,
    EVENT_TYPE_ERROR,
    EVENT_STATUS_DRAFT,
)
from kso_player.safe_output import format_playback_event_draft

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
}


def _sim(status, order=0, ct="image/png", dur=5000, started="2026-06-20T10:00:00",
         ended="2026-06-20T10:00:05", action="play", reason="ready"):
    return PlaybackSimulationResult(
        simulated_status=status,
        session_action=action, session_reason=reason,
        selected_order=order, selected_content_type=ct, selected_duration_ms=dur,
        started_at=started, would_end_at=ended,
        next_index=0, cycle_count=0,
    )


def _allowed_safety():
    return PlaybackSafetyDecision(allowed=True, action="play", reason="ready")


def _blocked_safety():
    return PlaybackSafetyDecision(allowed=False, action="stop", reason="payment_active")


# ══════════════════════════════════════════════════════════════════════

class TestEventBuild(unittest.TestCase):
    def test_would_play(self):
        sim = _sim(SIM_STATUS_WOULD_PLAY)
        event = build_playback_event_draft(sim, now="2026-06-20T10:01:00")
        self.assertEqual(event.event_type, EVENT_TYPE_WOULD_PLAY)
        self.assertEqual(event.event_status, EVENT_STATUS_DRAFT)
        self.assertTrue(event.playback_allowed)
        self.assertEqual(event.session_action, "play")
        self.assertEqual(event.selected_order, 0)

    def test_blocked(self):
        sim = _sim(SIM_STATUS_BLOCKED, action="stop", reason="safety_blocked", order=None, ct=None, dur=None)
        event = build_playback_event_draft(sim)
        self.assertEqual(event.event_type, EVENT_TYPE_BLOCKED)
        self.assertFalse(event.playback_allowed)
        self.assertIsNone(event.selected_order)

    def test_not_ready(self):
        sim = _sim(SIM_STATUS_NOT_READY, action="hold", reason="playlist_not_ready", order=None, ct=None, dur=None)
        event = build_playback_event_draft(sim)
        self.assertEqual(event.event_type, EVENT_TYPE_NOT_READY)
        self.assertFalse(event.playback_allowed)

    def test_error_sim_status(self):
        sim = _sim(SIM_STATUS_ERROR, order=None, ct=None, dur=None)
        event = build_playback_event_draft(sim)
        self.assertEqual(event.event_type, EVENT_TYPE_ERROR)

    def test_created_at_set(self):
        sim = _sim(SIM_STATUS_WOULD_PLAY)
        event = build_playback_event_draft(sim, now="2026-06-20T10:01:00")
        self.assertEqual(event.created_at, "2026-06-20T10:01:00")

    def test_timestamps_carried(self):
        sim = _sim(SIM_STATUS_WOULD_PLAY, started="S", ended="E")
        event = build_playback_event_draft(sim)
        self.assertEqual(event.started_at, "S")
        self.assertEqual(event.would_end_at, "E")

    def test_safety_decision_used(self):
        sim = _sim(SIM_STATUS_WOULD_PLAY)
        sd = _blocked_safety()
        event = build_playback_event_draft(sim, safety_decision=sd)
        self.assertFalse(event.playback_allowed)

    def test_none_simulation(self):
        event = build_playback_event_draft(None)
        self.assertEqual(event.event_type, EVENT_TYPE_ERROR)
        self.assertEqual(event.event_status, EVENT_STATUS_DRAFT)

    def test_non_simulation_type(self):
        event = build_playback_event_draft({"status": "would_play"})
        self.assertEqual(event.event_type, EVENT_TYPE_ERROR)


class TestEventSecurity(unittest.TestCase):
    def test_no_filename(self):
        event = build_playback_event_draft(_sim(SIM_STATUS_WOULD_PLAY))
        self.assertFalse(hasattr(event, "filename"))
        self.assertFalse(hasattr(event, "manifest_item_id"))
        self.assertFalse(hasattr(event, "sha256"))

    def test_no_paths(self):
        event = build_playback_event_draft(_sim(SIM_STATUS_WOULD_PLAY))
        for field in ["session_action", "session_reason", "event_type", "event_status"]:
            val = str(getattr(event, field, ""))
            self.assertNotIn("/", val)
        # content_type may contain / (MIME type) — that's fine

    def test_status_always_draft(self):
        for status in [SIM_STATUS_WOULD_PLAY, SIM_STATUS_BLOCKED, SIM_STATUS_NOT_READY]:
            event = build_playback_event_draft(_sim(status))
            self.assertEqual(event.event_status, EVENT_STATUS_DRAFT)


class TestEventOutput(unittest.TestCase):
    def test_would_play_output(self):
        event = build_playback_event_draft(_sim(SIM_STATUS_WOULD_PLAY), now="2026-06-20T10:01:00")
        out = format_playback_event_draft(event)
        self.assertIn("event_type: would_play", out)
        self.assertIn("event_status: draft", out)
        self.assertIn("playback_allowed: true", out)
        self.assertIn("session_action: play", out)
        self.assertIn("selected_order: 0", out)
        self.assertIn("selected_content_type: image/png", out)
        self.assertIn("selected_duration_ms: 5000", out)

    def test_blocked_output(self):
        sim = _sim(SIM_STATUS_BLOCKED, action="stop", reason="safety_blocked", order=None, ct=None, dur=None)
        event = build_playback_event_draft(sim)
        out = format_playback_event_draft(event)
        self.assertIn("event_type: blocked", out)
        self.assertIn("playback_allowed: false", out)
        self.assertNotIn("selected_order:", out)

    def test_no_filename_in_output(self):
        event = build_playback_event_draft(_sim(SIM_STATUS_WOULD_PLAY))
        out = format_playback_event_draft(event)
        self.assertNotIn("filename", out.lower())
        self.assertNotIn(".png", out)

    def test_no_manifest_item_id(self):
        event = build_playback_event_draft(_sim(SIM_STATUS_WOULD_PLAY))
        out = format_playback_event_draft(event)
        self.assertNotIn("manifest_item_id", out.lower())

    def test_no_sha256(self):
        event = build_playback_event_draft(_sim(SIM_STATUS_WOULD_PLAY))
        out = format_playback_event_draft(event)
        self.assertNotIn("sha256", out.lower())

    def test_no_forbidden(self):
        event = build_playback_event_draft(_sim(SIM_STATUS_WOULD_PLAY))
        out = format_playback_event_draft(event).lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, out, f"Event output contains forbidden '{fb}'")

    def test_no_stacktrace(self):
        event = build_playback_event_draft(_sim(SIM_STATUS_ERROR, order=None, ct=None, dur=None))
        out = format_playback_event_draft(event)
        self.assertNotIn("Traceback", out)


class TestEventDefaults(unittest.TestCase):
    def test_defaults(self):
        event = PlaybackEventDraft()
        self.assertEqual(event.event_type, EVENT_TYPE_ERROR)
        self.assertEqual(event.event_status, EVENT_STATUS_DRAFT)
        self.assertFalse(event.playback_allowed)
        self.assertEqual(event.session_action, "stop")


if __name__ == "__main__":
    unittest.main()
