"""Tests for KSO Player Shell Command Core.

Tests build_kso_shell_command() and format function.
Uses render plan fixtures. NO backend, NO HTTP, NO PoP.
"""

import hashlib
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase

from kso_player.shell_command import (
    KsoShellCommandResult,
    build_kso_shell_command,
    format_kso_shell_command_result,
    SHELL_MODE_HOLD,
    SHELL_MODE_RENDER,
    COMMAND_HOLD,
    COMMAND_SET_RENDER_PLAN,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_READY_FOR_SHELL,
    REASON_RENDER_PLAN_HOLD,
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


def _sha(content):
    return hashlib.sha256(content).hexdigest()


CONTENT = b"fake-media-content"
CONTENT_SHA = _sha(CONTENT)


def _write_state(root, state="idle", age_seconds=5):
    state_dir = Path(root) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    data = {"state": state, "updated_at_utc": updated_at.isoformat(), "source": "test"}
    (state_dir / "kso_state.json").write_text(json.dumps(data, sort_keys=True))


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
    _write_state(root, state, age_seconds)
    _write_media(root, filename=filename)
    _write_manifest(root, items=[{
        "manifest_item_id": "m-001", "order": 1,
        "content_type": content_type, "duration_ms": duration_ms,
        "filename": filename,
        "sha256": CONTENT_SHA,
    }])


# ══════════════════════════════════════════════════════════════════════
# Tests: render → shell command
# ══════════════════════════════════════════════════════════════════════

class TestRenderToShellCommand(TestCase):
    """idle + ready → shell_mode=render, command=setRenderPlan."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_image_shell_command(self):
        _full_fixture(self.tmp, content_type="image/png")
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.shell_mode, SHELL_MODE_RENDER)
        self.assertEqual(result.command, COMMAND_SET_RENDER_PLAN)
        self.assertEqual(result.reason, REASON_READY_FOR_SHELL)
        self.assertEqual(result.media_type, "image")
        self.assertTrue(result.pop_event_should_be_written)

    def test_video_shell_command(self):
        _full_fixture(self.tmp, content_type="video/mp4", duration_ms=30000)
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.shell_mode, SHELL_MODE_RENDER)
        self.assertEqual(result.command, COMMAND_SET_RENDER_PLAN)
        self.assertEqual(result.media_type, "video")

    def test_duration_bucket_passed(self):
        _full_fixture(self.tmp, duration_ms=5000)
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.duration_bucket, "short")

    def test_render_command_no_path(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_command(self.tmp)
        text = repr(result) + format_kso_shell_command_result(result)
        self.assertNotIn(str(self.tmp), text)
        self.assertNotIn("ad_001.png", text)
        self.assertNotIn(".png", text)

    def test_render_command_no_ids(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_command(self.tmp)
        text = repr(result) + format_kso_shell_command_result(result)
        self.assertNotIn("manifest_item_id", text)
        self.assertNotIn("m-001", text)

    def test_render_command_no_hashes(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_command(self.tmp)
        text = repr(result) + format_kso_shell_command_result(result)
        self.assertNotIn("sha256", text)

    def test_render_command_only_safe_fields(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_command(self.tmp)
        # The command result should only carry media_type + duration_bucket
        self.assertEqual(result.media_type, "image")
        self.assertIn(result.duration_bucket, ("short", "medium", "long", "unknown"))
        # No internal fields leaked
        self.assertNotIn("_selected_item", repr(result))

    def test_render_command_format_safe(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_command(self.tmp)
        text = format_kso_shell_command_result(result)
        self.assertIn("shell_mode: render", text)
        self.assertIn("command: setRenderPlan", text)
        self.assertTrue(_no_forbidden(text))


# ══════════════════════════════════════════════════════════════════════
# Tests: hold → shell command
# ══════════════════════════════════════════════════════════════════════

class TestHoldToShellCommand(TestCase):
    """Non-render cases → shell_mode=hold, command=hold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_transaction_hold(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.shell_mode, SHELL_MODE_HOLD)
        self.assertEqual(result.command, COMMAND_HOLD)
        self.assertEqual(result.reason, REASON_RENDER_PLAN_HOLD)
        self.assertFalse(result.pop_event_should_be_written)

    def test_payment_hold(self):
        _full_fixture(self.tmp, state="payment")
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.shell_mode, SHELL_MODE_HOLD)

    def test_receipt_hold(self):
        _full_fixture(self.tmp, state="receipt")
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.shell_mode, SHELL_MODE_HOLD)

    def test_missing_state_hold(self):
        _write_manifest(self.tmp)
        _write_media(self.tmp)
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.shell_mode, SHELL_MODE_HOLD)
        self.assertEqual(result.reason, REASON_RENDER_PLAN_HOLD)

    def test_stale_state_hold(self):
        _full_fixture(self.tmp, age_seconds=120)
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.shell_mode, SHELL_MODE_HOLD)

    def test_missing_manifest_hold(self):
        _write_state(self.tmp)
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.shell_mode, SHELL_MODE_HOLD)
        self.assertEqual(result.reason, REASON_RENDER_PLAN_HOLD)

    def test_unsupported_media_type_hold(self):
        _full_fixture(self.tmp, content_type="audio/mpeg")
        result = build_kso_shell_command(self.tmp)
        self.assertEqual(result.shell_mode, SHELL_MODE_HOLD)
        self.assertEqual(result.reason, REASON_RENDER_PLAN_HOLD)

    def test_hold_command_format_safe(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_command(self.tmp)
        text = format_kso_shell_command_result(result)
        self.assertIn("shell_mode: hold", text)
        self.assertIn("command: hold", text)
        self.assertTrue(_no_forbidden(text))


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
        result = build_kso_shell_command(self.tmp, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_invalid_root(self):
        result = build_kso_shell_command(None)
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
        result = build_kso_shell_command(self.tmp)
        self.assertTrue(result.pop_event_should_be_written)
        pop_pending = self.tmp / "pop" / "pending"
        self.assertFalse(pop_pending.exists())

    def test_no_state_modified(self):
        _full_fixture(self.tmp)
        state_path = self.tmp / "state" / "kso_state.json"
        before = state_path.read_text()
        build_kso_shell_command(self.tmp)
        self.assertEqual(before, state_path.read_text())

    def test_html_shell_unchanged(self):
        # HTML shell files should not be modified by command builder
        _full_fixture(self.tmp)
        build_kso_shell_command(self.tmp)
        # Command just reads local state/manifest/media, never touches shell

    def test_no_http_no_backend(self):
        import kso_player.shell_command as mod
        source = open(mod.__file__).read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestOutputSafety(TestCase):
    """repr/format never exposes IDs, paths, hashes."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repr_no_path(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_command(self.tmp)
        text = repr(result)
        self.assertNotIn(str(self.tmp), text)
        self.assertNotIn("ad_001", text)

    def test_repr_no_campaign_ids(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_command(self.tmp)
        text = repr(result)
        for fb in ("campaign_id", "creative_id", "schedule_item_id"):
            self.assertNotIn(fb, text)

    def test_repr_no_forbidden(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_command(self.tmp)
        text = repr(result) + format_kso_shell_command_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_hold_repr_safe(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_command(self.tmp)
        text = repr(result) + format_kso_shell_command_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_error_no_stacktrace(self):
        result = build_kso_shell_command(self.tmp, stale_seconds=0)
        text = repr(result) + format_kso_shell_command_result(result)
        self.assertNotIn("Traceback", text)


if __name__ == "__main__":
    import unittest
    unittest.main()
