"""Tests for KSO Player Local Render Plan Core.

Tests build_kso_render_plan() and format function.
Uses local state + manifest + media fixtures.
NO backend, NO HTTP, NO secret reading. NO PoP written.
"""

import hashlib
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase

from kso_player.render_plan import (
    KsoRenderPlanResult,
    build_kso_render_plan,
    format_kso_render_plan_result,
    RENDER_ACTION_RENDER,
    RENDER_ACTION_HOLD,
    MEDIA_IMAGE,
    MEDIA_VIDEO,
    MEDIA_UNKNOWN,
    DURATION_SHORT,
    DURATION_MEDIUM,
    DURATION_LONG,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_READY_TO_RENDER,
    REASON_DECISION_HOLD,
    REASON_UNSUPPORTED_MEDIA_TYPE,
    REASON_NO_SELECTED_ITEM,
    REASON_INVALID_ARGS,
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


def _write_state(root, state="idle", age_seconds=5):
    state_dir = Path(root) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    data = {"state": state, "updated_at_utc": updated_at.isoformat(), "source": "test"}
    (state_dir / "kso_state.json").write_text(json.dumps(data, sort_keys=True))


def _sha(content):
    return hashlib.sha256(content).hexdigest()


CONTENT = b"fake-media-content"
CONTENT_SHA = _sha(CONTENT)


def _write_manifest(root, items=None):
    manifest_dir = Path(root) / "manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    if items is None:
        items = [{"manifest_item_id": "m-001", "order": 1,
                   "content_type": "image/png", "duration_ms": 5000,
                   "filename": "ad_001.png", "sha256": CONTENT_SHA}]
    (manifest_dir / "current_manifest.json").write_text(
        json.dumps({"manifest_id": "test", "schema_version": 1, "items": items},
                   sort_keys=True))


def _write_media(root, filename="ad_001.png", content=CONTENT):
    media_dir = Path(root) / "media" / "current"
    media_dir.mkdir(parents=True, exist_ok=True)
    filepath = media_dir / filename
    filepath.write_bytes(content)
    sha_path = Path(str(filepath) + ".sha256")
    sha_path.write_text(_sha(content) + "\n")


def _full_fixture(root, state="idle", age_seconds=5, content_type="image/png",
                  duration_ms=5000, filename="ad_001.png"):
    """Complete working fixture."""
    _write_state(root, state, age_seconds)
    _write_media(root, filename=filename)
    _write_manifest(root, items=[{
        "manifest_item_id": "m-001", "order": 1,
        "content_type": content_type, "duration_ms": duration_ms,
        "filename": filename,
        "sha256": _sha(CONTENT),
    }])


# ══════════════════════════════════════════════════════════════════════
# Tests: render
# ══════════════════════════════════════════════════════════════════════

class TestRender(TestCase):
    """idle + ready content + image/video → render."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_image_renders(self):
        _full_fixture(self.tmp, content_type="image/png")
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.render_action, RENDER_ACTION_RENDER)
        self.assertTrue(result.play_allowed)
        self.assertTrue(result.selected_present)
        self.assertEqual(result.media_type, MEDIA_IMAGE)
        self.assertEqual(result.reason, REASON_READY_TO_RENDER)
        self.assertTrue(result.pop_event_should_be_written)

    def test_video_renders(self):
        _full_fixture(self.tmp, content_type="video/mp4", duration_ms=30000)
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_RENDER)
        self.assertEqual(result.media_type, MEDIA_VIDEO)

    def test_image_jpeg_renders(self):
        _full_fixture(self.tmp, content_type="image/jpeg")
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.media_type, MEDIA_IMAGE)

    def test_short_duration(self):
        _full_fixture(self.tmp, duration_ms=5000)
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.duration_bucket, DURATION_SHORT)

    def test_medium_duration(self):
        _full_fixture(self.tmp, duration_ms=15000)
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.duration_bucket, DURATION_MEDIUM)

    def test_long_duration(self):
        _full_fixture(self.tmp, duration_ms=90000)
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.duration_bucket, DURATION_LONG)


# ══════════════════════════════════════════════════════════════════════
# Tests: decision hold
# ══════════════════════════════════════════════════════════════════════

class TestDecisionHold(TestCase):
    """Non-idle / stale / missing state → render_action=hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_transaction_hold(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertFalse(result.play_allowed)
        self.assertEqual(result.reason, REASON_DECISION_HOLD)
        self.assertFalse(result.selected_present)

    def test_payment_hold(self):
        _full_fixture(self.tmp, state="payment")
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertEqual(result.reason, REASON_DECISION_HOLD)

    def test_receipt_hold(self):
        _full_fixture(self.tmp, state="receipt")
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertEqual(result.reason, REASON_DECISION_HOLD)

    def test_missing_state_hold(self):
        _write_manifest(self.tmp)
        _write_media(self.tmp)
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertEqual(result.reason, REASON_DECISION_HOLD)

    def test_stale_state_hold(self):
        _full_fixture(self.tmp, age_seconds=120)
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertEqual(result.reason, REASON_DECISION_HOLD)

    def test_missing_manifest_hold(self):
        _write_state(self.tmp)
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertEqual(result.reason, REASON_DECISION_HOLD)


# ══════════════════════════════════════════════════════════════════════
# Tests: unsupported media type
# ══════════════════════════════════════════════════════════════════════

class TestUnsupportedMedia(TestCase):
    """Unknown content_type → hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_audio_hold(self):
        _full_fixture(self.tmp, content_type="audio/mpeg")
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertEqual(result.reason, REASON_UNSUPPORTED_MEDIA_TYPE)
        self.assertTrue(result.selected_present)
        self.assertEqual(result.media_type, MEDIA_UNKNOWN)

    def test_text_hold(self):
        _full_fixture(self.tmp, content_type="text/html")
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)
        self.assertEqual(result.reason, REASON_UNSUPPORTED_MEDIA_TYPE)

    def test_application_hold(self):
        _full_fixture(self.tmp, content_type="application/pdf")
        result = build_kso_render_plan(self.tmp)
        self.assertEqual(result.render_action, RENDER_ACTION_HOLD)


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid args
# ══════════════════════════════════════════════════════════════════════

class TestInvalidArgs(TestCase):
    """Invalid args → safe error."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stale_seconds_zero(self):
        result = build_kso_render_plan(self.tmp, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_stale_seconds_negative(self):
        result = build_kso_render_plan(self.tmp, stale_seconds=-1)
        self.assertEqual(result.status, STATUS_ERROR)

    def test_invalid_root(self):
        result = build_kso_render_plan(None)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(TestCase):
    """Read-only — no PoP, no state write, no files created."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_pop_event_written(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        self.assertTrue(result.pop_event_should_be_written)
        pop_pending = self.tmp / "pop" / "pending"
        self.assertFalse(pop_pending.exists(),
            "PoP must not be written in render plan step")

    def test_no_pop_event_written_on_hold(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_render_plan(self.tmp)
        self.assertFalse(result.pop_event_should_be_written)
        pop_pending = self.tmp / "pop" / "pending"
        self.assertFalse(pop_pending.exists())

    def test_no_state_file_modified(self):
        _full_fixture(self.tmp)
        state_path = self.tmp / "state" / "kso_state.json"
        before = state_path.read_text()
        build_kso_render_plan(self.tmp)
        self.assertEqual(before, state_path.read_text())

    def test_no_http_no_backend(self):
        import kso_player.render_plan as mod
        source = open(mod.__file__).read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestOutputSafety(TestCase):
    """repr/format never exposes IDs, paths, internal fields."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repr_no_path(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = repr(result)
        self.assertNotIn(str(self.tmp), text)
        self.assertNotIn("kso_state.json", text)
        self.assertNotIn("ad_001.png", text)

    def test_format_no_path(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = format_kso_render_plan_result(result)
        self.assertNotIn(str(self.tmp), text)

    def test_no_manifest_item_id_in_output(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = repr(result) + format_kso_render_plan_result(result)
        self.assertNotIn("manifest_item_id", text)
        self.assertNotIn("m-001", text)

    def test_no_campaign_ids(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = repr(result) + format_kso_render_plan_result(result)
        for fb in ("campaign_id", "creative_id", "schedule_item_id"):
            self.assertNotIn(fb, text)

    def test_no_sha256_in_output(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = repr(result) + format_kso_render_plan_result(result)
        self.assertNotIn("sha256", text)

    def test_no_timestamps(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = repr(result) + format_kso_render_plan_result(result)
        self.assertNotIn("2026", text)
        self.assertNotIn("+00:00", text)

    def test_no_forbidden_substrings(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = repr(result) + format_kso_render_plan_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_hold_result_safe(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_render_plan(self.tmp)
        text = repr(result) + format_kso_render_plan_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_error_no_stacktrace(self):
        result = build_kso_render_plan(self.tmp, stale_seconds=0)
        text = repr(result) + format_kso_render_plan_result(result)
        self.assertNotIn("Traceback", text)

    def test_internal_fields_not_in_repr(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = repr(result)
        self.assertNotIn("_selected_item", text)
        self.assertNotIn("_duration_seconds", text)

    def test_internal_fields_not_in_format(self):
        _full_fixture(self.tmp)
        result = build_kso_render_plan(self.tmp)
        text = format_kso_render_plan_result(result)
        self.assertNotIn("_selected_item", text)
        self.assertNotIn("_duration_seconds", text)


if __name__ == "__main__":
    import unittest
    unittest.main()
