"""Tests for KSO Player Local Playback Decision Core.

Tests evaluate_kso_playback_runtime_decision() and format function.
Uses local state + manifest + media fixtures.
NO backend, NO HTTP, NO secret reading. NO PoP written.
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase

from kso_player.runtime_decision import (
    KsoPlaybackRuntimeDecisionResult,
    evaluate_kso_playback_runtime_decision,
    format_kso_playback_runtime_decision_result,
    ACTION_PLAY,
    ACTION_HOLD,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_READY_TO_PLAY,
    REASON_STATE_GATE_HOLD,
    REASON_LOCAL_CONTENT_NOT_READY,
    REASON_SESSION_OR_SAFETY_HOLD,
    REASON_INVALID_ARGS,
    REASON_INTERNAL_ERROR,
    FORBIDDEN_SUBSTRINGS,
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


def _write_state_file(root, state="idle", age_seconds=5):
    """Write kso_state.json with controlled age."""
    state_dir = Path(root) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    data = {
        "state": state,
        "updated_at_utc": updated_at.isoformat(),
        "source": "test",
    }
    (state_dir / "kso_state.json").write_text(json.dumps(data, sort_keys=True))


def _write_manifest(root, items=None, manifest_id="test-manifest-1"):
    """Write a minimal current_manifest.json."""
    if items is None:
        import hashlib
        sha = hashlib.sha256(b"fake-media-content").hexdigest()
        items = [
            {
                "manifest_item_id": "m-001",
                "order": 1,
                "content_type": "image",
                "duration_ms": 5000,
                "filename": "ad_001.png",
                "sha256": sha,
            }
        ]
    manifest_dir = Path(root) / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_id": manifest_id,
        "schema_version": 1,
        "items": items,
    }
    (manifest_dir / "current_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True))


def _write_media_file(root, media_id="media-001", filename="ad_001.png",
                      sha256_hex=None, content=b"fake-media"):
    """Write a media file to media/current/ and a .sha256 sidecar."""
    import hashlib
    if sha256_hex is None:
        sha256_hex = hashlib.sha256(content).hexdigest()
    media_dir = Path(root) / "media" / "current"
    media_dir.mkdir(parents=True, exist_ok=True)
    filepath = media_dir / filename
    filepath.write_bytes(content)
    # Write .sha256 sidecar
    sha_path = Path(str(filepath) + ".sha256")
    sha_path.write_text(sha256_hex + "\n")

    # Also ensure manifest's sha256 matches
    return sha256_hex  # caller should use this in manifest


def _full_fixture(root, state="idle", age_seconds=5):
    """Set up a complete working fixture: state + manifest + media."""
    _write_state_file(root, state, age_seconds)
    # Write media first to get correct sha256
    import hashlib
    content = b"fake-media-content"
    sha256_hex = hashlib.sha256(content).hexdigest()
    _write_media_file(root, content=content, sha256_hex=sha256_hex)
    _write_manifest(root, items=[{
        "manifest_item_id": "m-001",
        "order": 1,
        "content_type": "image",
        "duration_ms": 5000,
        "filename": "ad_001.png",
        "sha256": sha256_hex,
    }])


# ══════════════════════════════════════════════════════════════════════
# Tests: ready to play
# ══════════════════════════════════════════════════════════════════════

class TestReadyToPlay(TestCase):
    """idle state + ready content → play_allowed=true."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ready_to_play(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.play_allowed)
        self.assertEqual(result.action, ACTION_PLAY)
        self.assertEqual(result.reason, REASON_READY_TO_PLAY)
        self.assertEqual(result.state, "idle")
        self.assertTrue(result.content_ready)
        self.assertTrue(result.selected_present)
        self.assertTrue(result.pop_event_should_be_written)

    def test_ready_to_play_format(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = format_kso_playback_runtime_decision_result(result)
        self.assertIn("play_allowed: true", text)
        self.assertIn("action: play", text)
        self.assertTrue(_no_forbidden(text))

    def test_ready_to_play_repr_safe(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_ready_to_play_gate_action_is_play(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertEqual(result.gate_action, ACTION_PLAY)


# ══════════════════════════════════════════════════════════════════════
# Tests: state gate blocks
# ══════════════════════════════════════════════════════════════════════

class TestStateGateBlocks(TestCase):
    """Non-idle or invalid state → hold, reason=state_gate_hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_transaction_blocks(self):
        _full_fixture(self.tmp, state="transaction")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.action, ACTION_HOLD)
        self.assertEqual(result.reason, REASON_STATE_GATE_HOLD)
        self.assertEqual(result.state, "transaction")

    def test_payment_blocks(self):
        _full_fixture(self.tmp, state="payment")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_STATE_GATE_HOLD)

    def test_receipt_blocks(self):
        _full_fixture(self.tmp, state="receipt")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_STATE_GATE_HOLD)

    def test_service_blocks(self):
        _full_fixture(self.tmp, state="service")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)

    def test_error_blocks(self):
        _full_fixture(self.tmp, state="error")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)

    def test_maintenance_blocks(self):
        _full_fixture(self.tmp, state="maintenance")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)

    def test_offline_blocks(self):
        _full_fixture(self.tmp, state="offline")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)

    def test_unknown_blocks(self):
        _full_fixture(self.tmp, state="unknown")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)

    def test_missing_state_blocks(self):
        # No state file — but manifest/media exist
        _write_manifest(self.tmp)
        _write_media_file(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_STATE_GATE_HOLD)

    def test_stale_state_blocks(self):
        _full_fixture(self.tmp, state="idle", age_seconds=120)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_STATE_GATE_HOLD)

    def test_invalid_state_json_blocks(self):
        _write_manifest(self.tmp)
        _write_media_file(self.tmp)
        state_dir = self.tmp / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "kso_state.json").write_text("garbage")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_STATE_GATE_HOLD)

    def test_invalid_state_value_blocks(self):
        _full_fixture(self.tmp, state="playing")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_STATE_GATE_HOLD)

    def test_content_not_checked_when_state_blocks(self):
        # State blocks → content_ready should remain False
        _full_fixture(self.tmp, state="transaction")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.content_ready)
        self.assertFalse(result.selected_present)


# ══════════════════════════════════════════════════════════════════════
# Tests: local content not ready
# ══════════════════════════════════════════════════════════════════════

class TestLocalContentNotReady(TestCase):
    """State=idle but manifest/media missing → hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_manifest_blocks(self):
        _write_state_file(self.tmp, state="idle")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_LOCAL_CONTENT_NOT_READY)
        self.assertEqual(result.state, "idle")
        self.assertFalse(result.content_ready)

    def test_empty_manifest_blocks(self):
        _write_state_file(self.tmp, state="idle")
        _write_manifest(self.tmp, items=[])
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_LOCAL_CONTENT_NOT_READY)

    def test_idle_but_missing_media_blocks(self):
        _write_state_file(self.tmp, state="idle")
        _write_manifest(self.tmp)
        # No media file → manifest says filename=ad_001.png but file absent
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_LOCAL_CONTENT_NOT_READY)

    def test_gate_action_is_play_when_content_not_ready(self):
        _write_state_file(self.tmp, state="idle")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertEqual(result.gate_action, ACTION_PLAY)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_LOCAL_CONTENT_NOT_READY)


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid args
# ══════════════════════════════════════════════════════════════════════

class TestInvalidArgs(TestCase):
    """Invalid arguments → safe error."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stale_seconds_zero(self):
        result = evaluate_kso_playback_runtime_decision(self.tmp, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_stale_seconds_negative(self):
        result = evaluate_kso_playback_runtime_decision(self.tmp, stale_seconds=-1)
        self.assertEqual(result.status, STATUS_ERROR)

    def test_invalid_root(self):
        result = evaluate_kso_playback_runtime_decision(None)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(TestCase):
    """Decision is READ-ONLY — no PoP write, no state write, no files created."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_pop_event_written_on_play(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertTrue(result.play_allowed)
        self.assertTrue(result.pop_event_should_be_written)
        # But no actual PoP file should exist
        pop_pending = self.tmp / "pop" / "pending"
        self.assertFalse(pop_pending.exists(),
            "PoP must not be written in decision step")

    def test_no_pop_event_written_on_hold(self):
        _full_fixture(self.tmp, state="transaction")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        self.assertFalse(result.play_allowed)
        self.assertFalse(result.pop_event_should_be_written)
        pop_pending = self.tmp / "pop" / "pending"
        self.assertFalse(pop_pending.exists())

    def test_no_state_file_written(self):
        _full_fixture(self.tmp)
        state_path = self.tmp / "state" / "kso_state.json"
        before = state_path.read_text()
        evaluate_kso_playback_runtime_decision(self.tmp)
        after = state_path.read_text()
        self.assertEqual(before, after, "player must not modify kso_state.json")

    def test_no_sent_quarantine_dry_run_failed(self):
        _full_fixture(self.tmp)
        evaluate_kso_playback_runtime_decision(self.tmp)
        for bad in ("sent", "quarantine", "dry_run", "failed"):
            self.assertFalse((self.tmp / bad).exists(),
                f"'{bad}/' should not exist")

    def test_no_http_no_backend(self):
        import kso_player.runtime_decision as mod
        source = open(mod.__file__).read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestOutputSafety(TestCase):
    """Result/repr/format never contains IDs, paths, secrets."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_play_result_no_path(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        self.assertNotIn(str(self.tmp), text)
        self.assertNotIn("kso_state.json", text)

    def test_hold_result_no_path(self):
        _full_fixture(self.tmp, state="transaction")
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        self.assertNotIn("kso_state.json", text)

    def test_result_no_manifest_item_id(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        self.assertNotIn("manifest_item_id", text)
        self.assertNotIn("media-001", text)

    def test_result_no_campaign_ids(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        for fb in ("campaign_id", "creative_id", "schedule_item_id", "batch_id"):
            self.assertNotIn(fb, text)

    def test_result_no_media_path(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        self.assertNotIn("ad_001", text)
        self.assertNotIn("media_path", text)
        self.assertNotIn("creatives/", text)

    def test_result_no_sha256(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        self.assertNotIn("sha256", text)

    def test_result_no_timestamps(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        self.assertNotIn("2026", text)
        self.assertNotIn("+00:00", text)

    def test_result_no_forbidden(self):
        _full_fixture(self.tmp)
        result = evaluate_kso_playback_runtime_decision(self.tmp)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_error_result_no_stacktrace(self):
        result = evaluate_kso_playback_runtime_decision(self.tmp, stale_seconds=0)
        text = repr(result) + format_kso_playback_runtime_decision_result(result)
        self.assertNotIn("Traceback", text)

    def test_all_reasons_safe(self):
        for reason in [
            REASON_READY_TO_PLAY, REASON_STATE_GATE_HOLD,
            REASON_LOCAL_CONTENT_NOT_READY, REASON_SESSION_OR_SAFETY_HOLD,
            REASON_INVALID_ARGS, REASON_INTERNAL_ERROR,
        ]:
            result = KsoPlaybackRuntimeDecisionResult(reason=reason)
            text = format_kso_playback_runtime_decision_result(result)
            self.assertTrue(_no_forbidden(text),
                f"reason={reason}: forbidden in format")


if __name__ == "__main__":
    import unittest
    unittest.main()
