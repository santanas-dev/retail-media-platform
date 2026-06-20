"""Tests for KSO Player Local Shell Snapshot Core.

Tests build_kso_shell_snapshot(), serialize_kso_shell_snapshot(),
and format function. Uses render plan fixtures. NO backend, NO HTTP, NO PoP.
"""

import hashlib
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase

from kso_player.shell_snapshot import (
    KsoShellSnapshotResult,
    build_kso_shell_snapshot,
    serialize_kso_shell_snapshot,
    format_kso_shell_snapshot_result,
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
    SNAPSHOT_METHOD_SET_HOLD,
    SNAPSHOT_METHOD_SET_RENDER_PLAN,
    SNAPSHOT_SCHEMA_VERSION,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    SIZE_BUCKET_SMALL,
    SIZE_BUCKET_MEDIUM,
    SIZE_BUCKET_LARGE,
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
# Tests: render → shell snapshot
# ══════════════════════════════════════════════════════════════════════

class TestRenderToShellSnapshot(TestCase):
    """idle + ready → snapshot_mode=render, method=setRenderPlan."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_image_snapshot_render(self):
        _full_fixture(self.tmp, content_type="image/png")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertEqual(result.shell_method, SNAPSHOT_METHOD_SET_RENDER_PLAN)
        self.assertEqual(result.media_type, "image")
        self.assertEqual(result.duration_bucket, "short")
        self.assertTrue(result.pop_event_should_be_written)

    def test_video_snapshot_render(self):
        _full_fixture(self.tmp, content_type="video/mp4", duration_ms=30000)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertEqual(result.shell_method, SNAPSHOT_METHOD_SET_RENDER_PLAN)
        self.assertEqual(result.media_type, "video")
        self.assertEqual(result.duration_bucket, "medium")

    def test_duration_short(self):
        _full_fixture(self.tmp, duration_ms=5000)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.duration_bucket, "short")

    def test_duration_long(self):
        _full_fixture(self.tmp, duration_ms=90000)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.duration_bucket, "long")

    def test_serialized_size_bucket_small(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.serialized_size_bucket, SIZE_BUCKET_SMALL)


# ══════════════════════════════════════════════════════════════════════
# Tests: hold → shell snapshot
# ══════════════════════════════════════════════════════════════════════

class TestHoldToShellSnapshot(TestCase):
    """Non-render cases → snapshot_mode=hold, method=setHold."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_transaction_hold(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)
        self.assertEqual(result.shell_method, SNAPSHOT_METHOD_SET_HOLD)
        self.assertFalse(result.pop_event_should_be_written)

    def test_payment_hold(self):
        _full_fixture(self.tmp, state="payment")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_receipt_hold(self):
        _full_fixture(self.tmp, state="receipt")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_missing_state_hold(self):
        _write_manifest(self.tmp)
        _write_media(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_stale_state_hold(self):
        _full_fixture(self.tmp, age_seconds=120)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_missing_manifest_hold(self):
        _write_state(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_unsupported_media_type_hold(self):
        _full_fixture(self.tmp, content_type="audio/mpeg")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_service_state_hold(self):
        _full_fixture(self.tmp, state="service")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)


# ══════════════════════════════════════════════════════════════════════
# Tests: serialized JSON safety
# ══════════════════════════════════════════════════════════════════════

class TestSerializedJSONSafety(TestCase):
    """Serialized snapshot contains only safe fields."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_render_serialized_has_schema_version(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        obj = json.loads(serialize_kso_shell_snapshot(result))
        self.assertEqual(obj["schemaVersion"], SNAPSHOT_SCHEMA_VERSION)
        self.assertEqual(obj["mode"], "render")
        self.assertEqual(obj["method"], "setRenderPlan")

    def test_render_serialized_payload_keys(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        obj = json.loads(serialize_kso_shell_snapshot(result))
        self.assertIn("mediaType", obj["payload"])
        self.assertIn("durationBucket", obj["payload"])

    def test_hold_serialized_payload(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_snapshot(self.tmp)
        obj = json.loads(serialize_kso_shell_snapshot(result))
        self.assertEqual(obj["mode"], "hold")
        self.assertEqual(obj["method"], "setHold")
        self.assertEqual(obj["payload"], {"reason": "hold"})

    def test_serialized_only_safe_top_keys(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        obj = json.loads(serialize_kso_shell_snapshot(result))
        self.assertTrue(set(obj.keys()).issubset({"schemaVersion", "mode", "method", "payload"}))

    def test_serialized_no_paths(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertNotIn(str(self.tmp), s)
        self.assertNotIn("ad_001", s)
        self.assertNotIn(".png", s.lower())

    def test_serialized_no_ids(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        for fb in ("manifest_item_id", "campaign_id", "creative_id",
                    "schedule_item_id", "device_event_id", "batch_id"):
            self.assertNotIn(fb, s)

    def test_serialized_no_hash(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertNotIn("sha256", s)

    def test_serialized_no_timestamps(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertNotIn("2026-", s)
        self.assertNotIn("started_at", s)
        self.assertNotIn("ended_at", s)

    def test_serialized_no_forbidden(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertTrue(_no_forbidden(s),
            f"forbidden in serialized: {s[:200]}")

    def test_hold_serialized_no_forbidden(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertTrue(_no_forbidden(s))

    def test_serialized_no_media_src(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertNotIn("src", s.lower())
        self.assertNotIn("media_src", s.lower())

    def test_serialized_no_raw_json(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        # Only the snapshot JSON object — no embedded raw JSON from state/manifest
        obj = json.loads(s)
        for val in obj.values():
            if isinstance(val, dict):
                for v in val.values():
                    self.assertNotIsInstance(v, dict)


# ══════════════════════════════════════════════════════════════════════
# Tests: result/repr/format safety
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
        result = build_kso_shell_snapshot(self.tmp)
        text = repr(result)
        self.assertNotIn(str(self.tmp), text)
        self.assertNotIn("ad_001", text)

    def test_repr_no_campaign_ids(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        text = repr(result)
        for fb in ("manifest_item_id", "campaign_id", "creative_id", "schedule_item_id"):
            self.assertNotIn(fb, text)

    def test_repr_no_forbidden(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        text = repr(result) + format_kso_shell_snapshot_result(result)
        self.assertTrue(_no_forbidden(text),
            f"forbidden in output: {text[:200]}")

    def test_hold_repr_safe(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_snapshot(self.tmp)
        text = repr(result) + format_kso_shell_snapshot_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_has_expected_fields(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        text = format_kso_shell_snapshot_result(result)
        self.assertIn("snapshot_mode:", text)
        self.assertIn("shell_method:", text)
        self.assertIn("media_type:", text)
        self.assertIn("duration_bucket:", text)
        self.assertIn("serialized_size_bucket:", text)

    def test_error_no_stacktrace(self):
        result = build_kso_shell_snapshot(self.tmp, stale_seconds=0)
        text = repr(result) + format_kso_shell_snapshot_result(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("stacktrace", text)

    def test_format_safe_no_forbidden(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        text = format_kso_shell_snapshot_result(result)
        self.assertTrue(_no_forbidden(text))


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
        result = build_kso_shell_snapshot(self.tmp)
        self.assertTrue(result.pop_event_should_be_written)
        pop_pending = self.tmp / "pop" / "pending"
        self.assertFalse(pop_pending.exists(),
            f"pop/pending should not exist: {pop_pending}")

    def test_no_state_modified(self):
        _full_fixture(self.tmp)
        state_path = self.tmp / "state" / "kso_state.json"
        before = state_path.read_text()
        build_kso_shell_snapshot(self.tmp)
        self.assertEqual(before, state_path.read_text())

    def test_no_http_no_backend(self):
        import kso_player.shell_snapshot as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)

    def test_no_secret_read(self):
        import kso_player.shell_snapshot as mod
        with open(mod.__file__) as f:
            source = f.read()
        # Check for actual secret/config reading code, not docstring mentions
        self.assertNotIn("os.environ", source)
        self.assertNotIn("os.getenv", source)
        self.assertNotIn("configparser", source.lower())

    def test_no_media_bytes_read(self):
        import kso_player.shell_snapshot as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("read_bytes", source)

    def test_no_direct_chromium(self):
        import kso_player.shell_snapshot as mod
        with open(mod.__file__) as f:
            source = f.read()
        # Check for actual chromium-launching code, not docstring mentions
        self.assertNotIn("subprocess", source.lower())
        self.assertNotIn("webbrowser", source.lower())
        self.assertNotIn("os.system", source.lower())
        self.assertNotIn("Popen", source)

    def test_no_systemd_systemctl(self):
        import kso_player.shell_snapshot as mod
        with open(mod.__file__) as f:
            source = f.read()
        self.assertNotIn("systemd", source.lower())
        self.assertNotIn("systemctl", source.lower())

    def test_no_windows_msi_programdata(self):
        import kso_player.shell_snapshot as mod
        with open(mod.__file__) as f:
            source = f.read().lower()
        for fb in ("Windows Service", "ProgramData", "Windows installer"):
            self.assertNotIn(fb.lower(), source)


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
        result = build_kso_shell_snapshot(self.tmp, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_invalid_root_none(self):
        result = build_kso_shell_snapshot(None)
        self.assertEqual(result.status, STATUS_ERROR)


# ══════════════════════════════════════════════════════════════════════
# Tests: serialized size bucket
# ══════════════════════════════════════════════════════════════════════

class TestSerializedSizeBucket(TestCase):
    """Size bucket is always set correctly."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_render_snapshot_size_bucket_set(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertIn(result.serialized_size_bucket,
            (SIZE_BUCKET_SMALL, SIZE_BUCKET_MEDIUM, SIZE_BUCKET_LARGE))

    def test_hold_snapshot_size_bucket_set(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertIn(result.serialized_size_bucket,
            (SIZE_BUCKET_SMALL, SIZE_BUCKET_MEDIUM, SIZE_BUCKET_LARGE))

    def test_render_snapshot_small(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        # Snapshot should always be small (< 256 bytes)
        self.assertEqual(result.serialized_size_bucket, SIZE_BUCKET_SMALL)

    def test_hold_snapshot_small(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.serialized_size_bucket, SIZE_BUCKET_SMALL)


# ══════════════════════════════════════════════════════════════════════
# Tests: render snapshot with mediaRef
# ══════════════════════════════════════════════════════════════════════

class TestRenderSnapshotWithMediaRef(TestCase):
    """Render snapshot now includes safe mediaRef in payload."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_render_snapshot_has_media_ref_present(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_RENDER)
        self.assertTrue(result.media_ref_present)
        self.assertEqual(result.media_ref_kind, "local_alias")

    def test_render_snapshot_serialized_includes_media_ref(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        obj = json.loads(s)
        self.assertIn("mediaRef", obj["payload"])
        self.assertTrue(obj["payload"]["mediaRef"].startswith("media/current/slot-"))

    def test_render_snapshot_media_ref_is_safe_format(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        obj = json.loads(s)
        mref = obj["payload"]["mediaRef"]
        # Must match safe pattern
        self.assertRegex(mref, r"^media/current/slot-\d+$")
        self.assertNotIn("..", mref)
        self.assertNotIn("//", mref)
        self.assertNotIn("http", mref)

    def test_render_snapshot_media_ref_no_ids(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        for fb in ("manifest_item_id", "campaign_id", "creative_id",
                    "schedule_item_id"):
            self.assertNotIn(fb, s)

    def test_render_snapshot_media_ref_no_hash(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertNotIn("sha256", s)

    def test_render_snapshot_media_ref_no_real_filename(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertNotIn("ad_001", s)
        self.assertNotIn(".png", s)

    def test_render_snapshot_media_ref_no_absolute_path(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        self.assertNotIn(str(self.tmp), s)
        self.assertNotIn("/home", s)


# ══════════════════════════════════════════════════════════════════════
# Tests: hold snapshot — no mediaRef
# ══════════════════════════════════════════════════════════════════════

class TestHoldSnapshotNoMediaRef(TestCase):
    """Hold snapshots never include mediaRef."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hold_snapshot_no_media_ref(self):
        _full_fixture(self.tmp, state="transaction")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)
        self.assertFalse(result.media_ref_present)

    def test_hold_serialized_no_media_ref(self):
        _full_fixture(self.tmp, state="payment")
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        obj = json.loads(s)
        self.assertNotIn("mediaRef", obj["payload"])

    def test_hold_serialized_only_reason(self):
        _full_fixture(self.tmp, state="service")
        result = build_kso_shell_snapshot(self.tmp)
        s = serialize_kso_shell_snapshot(result)
        obj = json.loads(s)
        self.assertEqual(obj["payload"], {"reason": "hold"})

    def test_unsupported_media_type_hold_no_media_ref(self):
        _full_fixture(self.tmp, content_type="audio/mpeg")
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)

    def test_missing_manifest_hold_no_media_ref(self):
        _write_state(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertEqual(result.snapshot_mode, SNAPSHOT_MODE_HOLD)
        self.assertFalse(result.media_ref_present)


# ══════════════════════════════════════════════════════════════════════
# Tests: safety — no side effects (extended)
# ══════════════════════════════════════════════════════════════════════

class TestMediaRefNoSideEffects(TestCase):
    """Media ref doesn't cause PoP writes, state mods, or backend calls."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_pop_event_written_with_media_ref(self):
        _full_fixture(self.tmp)
        result = build_kso_shell_snapshot(self.tmp)
        self.assertTrue(result.media_ref_present)
        pop_pending = self.tmp / "pop" / "pending"
        self.assertFalse(pop_pending.exists())

    def test_no_state_modified_with_media_ref(self):
        _full_fixture(self.tmp)
        state_path = self.tmp / "state" / "kso_state.json"
        before = state_path.read_text()
        build_kso_shell_snapshot(self.tmp)
        self.assertEqual(before, state_path.read_text())


if __name__ == "__main__":
    import unittest
    unittest.main()
