"""Tests for KSO Sidecar Stale Lock Detector.

Tests detect_pop_pending_lock_staleness() and format function.
Pure file I/O — no HTTP, no backend, no secret reading.
DETECT-ONLY — never deletes, renames, or modifies lock files.
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase

from kso_sidecar_agent.pop_stale_lock_detector import (
    PopStaleLockDetectionResult,
    detect_pop_pending_lock_staleness,
    format_pop_stale_lock_detection_result,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_NO_LOCK,
    REASON_FRESH_LOCK,
    REASON_STALE_DETECTED,
    REASON_CRITICAL_STALE_DETECTED,
    REASON_V1_DETECT_ONLY,
    REASON_INVALID_MARKER_DETECT_ONLY,
    REASON_INVALID_ARGS,
    REASON_READ_FAILED,
    AGE_FRESH,
    AGE_STALE,
    AGE_CRITICAL,
    AGE_UNKNOWN,
    PROC_ALIVE,
    PROC_NOT_ALIVE,
    PROC_UNKNOWN,
    PROC_NOT_CHECKED,
    FORBIDDEN_SUBSTRINGS,
    POP_PENDING_DIR,
    POP_LOCK_FILE,
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


def _write_v2_lock(root, age_seconds=0, pid=None, boot_id_hash="abc123"):
    """Write a v2 lock marker with controlled age."""
    pending = Path(root) / POP_PENDING_DIR
    pending.mkdir(parents=True, exist_ok=True)
    lock_path = pending / POP_LOCK_FILE

    created_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    if pid is None:
        pid = os.getpid()

    marker = {
        "schema_version": 2,
        "component": "sidecar",
        "operation": "rotation_apply",
        "created_at_utc": created_at.isoformat(),
        "pid": pid,
        "boot_id_hash": boot_id_hash,
    }
    lock_path.write_text(json.dumps(marker, sort_keys=True))
    # Set mtime to match age
    mtime = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).timestamp()
    os.utime(str(lock_path), (mtime, mtime))


def _write_v1_lock(root, age_seconds=0):
    """Write a v1 'locked\\n' lock marker with controlled age."""
    pending = Path(root) / POP_PENDING_DIR
    pending.mkdir(parents=True, exist_ok=True)
    lock_path = pending / POP_LOCK_FILE
    lock_path.write_text("locked\n")
    mtime = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).timestamp()
    os.utime(str(lock_path), (mtime, mtime))


def _write_invalid_lock(root, content="garbage", age_seconds=0):
    """Write an invalid/corrupt lock marker."""
    pending = Path(root) / POP_PENDING_DIR
    pending.mkdir(parents=True, exist_ok=True)
    lock_path = pending / POP_LOCK_FILE
    lock_path.write_text(content)
    mtime = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).timestamp()
    os.utime(str(lock_path), (mtime, mtime))


# ══════════════════════════════════════════════════════════════════════
# Tests: no lock
# ══════════════════════════════════════════════════════════════════════

class TestNoLock(TestCase):
    """Tests when lock file does not exist."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_lock_ok(self):
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertFalse(result.lock_present)
        self.assertFalse(result.stale_detected)
        self.assertFalse(result.critical)
        self.assertFalse(result.cleanup_allowed)
        self.assertEqual(result.reason, REASON_NO_LOCK)
        self.assertEqual(result.marker_version, 0)

    def test_no_lock_format_safe(self):
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = format_pop_stale_lock_detection_result(result)
        self.assertIn("status: ok", text)
        self.assertIn("lock_present: false", text)
        self.assertTrue(_no_forbidden(text), f"forbidden in format: {text[:200]}")

    def test_no_lock_repr_safe(self):
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = repr(result)
        self.assertTrue(_no_forbidden(text), f"forbidden in repr: {text[:200]}")


# ══════════════════════════════════════════════════════════════════════
# Tests: fresh v2 lock
# ══════════════════════════════════════════════════════════════════════

class TestFreshV2Lock(TestCase):
    """Tests with a fresh (non-stale) v2 lock."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_v2_lock_ok(self):
        _write_v2_lock(self.tmp, age_seconds=30)
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertTrue(result.lock_present)
        self.assertFalse(result.stale_detected)
        self.assertFalse(result.critical)
        self.assertFalse(result.cleanup_allowed)
        self.assertEqual(result.marker_version, 2)
        self.assertEqual(result.age_bucket, AGE_FRESH)
        self.assertEqual(result.reason, REASON_FRESH_LOCK)

    def test_fresh_v2_lock_process_alive(self):
        _write_v2_lock(self.tmp, age_seconds=5, pid=os.getpid())
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.process_status, PROC_ALIVE)

    def test_fresh_v2_lock_lock_not_deleted(self):
        _write_v2_lock(self.tmp, age_seconds=30)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists())
        detect_pop_pending_lock_staleness(self.tmp)
        self.assertTrue(lock_path.exists(), "lock must NOT be deleted")

    def test_fresh_v2_lock_format_safe(self):
        _write_v2_lock(self.tmp, age_seconds=30)
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = format_pop_stale_lock_detection_result(result)
        self.assertIn("cleanup_allowed: false", text)
        self.assertTrue(_no_forbidden(text))

    def test_fresh_v2_lock_repr_safe(self):
        _write_v2_lock(self.tmp, age_seconds=30)
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_fresh_v2_lock_no_pid_in_output(self):
        _write_v2_lock(self.tmp, age_seconds=30)
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = repr(result) + format_pop_stale_lock_detection_result(result)
        self.assertNotIn("pid", text.lower().replace("_pid", ""))  # "pid" not standalone
        # "pid" appears only in field names, not values — check no numeric pid
        pid_str = str(os.getpid())
        self.assertNotIn(pid_str, text)


# ══════════════════════════════════════════════════════════════════════
# Tests: stale v2 lock
# ══════════════════════════════════════════════════════════════════════

class TestStaleV2Lock(TestCase):
    """Tests with a stale v2 lock (> stale_seconds)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stale_v2_lock_detected(self):
        _write_v2_lock(self.tmp, age_seconds=700)  # > 600 stale_seconds
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertTrue(result.lock_present)
        self.assertTrue(result.stale_detected)
        self.assertFalse(result.critical)
        self.assertFalse(result.cleanup_allowed)
        self.assertEqual(result.marker_version, 2)
        self.assertEqual(result.age_bucket, AGE_STALE)
        self.assertEqual(result.reason, REASON_STALE_DETECTED)

    def test_stale_v2_lock_not_deleted(self):
        _write_v2_lock(self.tmp, age_seconds=700)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        detect_pop_pending_lock_staleness(self.tmp)
        self.assertTrue(lock_path.exists(), "stale lock must NOT be deleted")

    def test_stale_v2_lock_pid_not_alive(self):
        _write_v2_lock(self.tmp, age_seconds=700, pid=99999)  # unlikely to exist
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.process_status, PROC_NOT_ALIVE)

    def test_stale_v2_lock_custom_thresholds(self):
        _write_v2_lock(self.tmp, age_seconds=200)
        result = detect_pop_pending_lock_staleness(
            self.tmp, stale_seconds=100, critical_seconds=500)
        self.assertTrue(result.stale_detected)
        self.assertFalse(result.critical)
        self.assertEqual(result.age_bucket, AGE_STALE)

    def test_stale_v2_lock_no_boot_id_in_output(self):
        _write_v2_lock(self.tmp, age_seconds=700)
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = repr(result) + format_pop_stale_lock_detection_result(result)
        self.assertNotIn("boot_id", text.lower())
        self.assertNotIn("abc123", text)


# ══════════════════════════════════════════════════════════════════════
# Tests: critical stale v2 lock
# ══════════════════════════════════════════════════════════════════════

class TestCriticalStaleV2Lock(TestCase):
    """Tests with a critically stale v2 lock (> critical_seconds)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_critical_stale_v2_lock(self):
        _write_v2_lock(self.tmp, age_seconds=2000)  # > 1800 critical_seconds
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertTrue(result.stale_detected)
        self.assertTrue(result.critical)
        self.assertFalse(result.cleanup_allowed)
        self.assertEqual(result.age_bucket, AGE_CRITICAL)
        self.assertIn(result.reason, [REASON_STALE_DETECTED, REASON_CRITICAL_STALE_DETECTED])

    def test_critical_stale_v2_lock_not_deleted(self):
        _write_v2_lock(self.tmp, age_seconds=2000)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        detect_pop_pending_lock_staleness(self.tmp)
        self.assertTrue(lock_path.exists())

    def test_critical_stale_cleanup_always_false(self):
        _write_v2_lock(self.tmp, age_seconds=10000)
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertFalse(result.cleanup_allowed)
        self.assertIn("cleanup_allowed: false",
                      format_pop_stale_lock_detection_result(result))


# ══════════════════════════════════════════════════════════════════════
# Tests: v1 lock
# ══════════════════════════════════════════════════════════════════════

class TestV1Lock(TestCase):
    """Tests with a v1 'locked\\n' lock marker."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_v1_fresh_lock_detect_only(self):
        _write_v1_lock(self.tmp, age_seconds=30)
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertTrue(result.lock_present)
        self.assertEqual(result.marker_version, 1)
        self.assertFalse(result.stale_detected)
        self.assertFalse(result.critical)
        self.assertFalse(result.cleanup_allowed)
        self.assertEqual(result.reason, REASON_V1_DETECT_ONLY)

    def test_v1_stale_lock_detect_only(self):
        _write_v1_lock(self.tmp, age_seconds=700)
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertTrue(result.stale_detected)
        self.assertFalse(result.cleanup_allowed)
        self.assertEqual(result.reason, REASON_V1_DETECT_ONLY)

    def test_v1_critical_lock_detect_only(self):
        _write_v1_lock(self.tmp, age_seconds=2000)
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertTrue(result.stale_detected)
        self.assertTrue(result.critical)
        self.assertFalse(result.cleanup_allowed)
        self.assertEqual(result.reason, REASON_V1_DETECT_ONLY)

    def test_v1_lock_not_deleted(self):
        _write_v1_lock(self.tmp, age_seconds=700)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        detect_pop_pending_lock_staleness(self.tmp)
        self.assertTrue(lock_path.exists(), "v1 lock must NOT be deleted")

    def test_v1_lock_not_deleted_even_critical(self):
        _write_v1_lock(self.tmp, age_seconds=10000)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        detect_pop_pending_lock_staleness(self.tmp)
        self.assertTrue(lock_path.exists())


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid marker
# ══════════════════════════════════════════════════════════════════════

class TestInvalidMarker(TestCase):
    """Tests with invalid/corrupt lock markers."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_garbage_marker_detect_only(self):
        _write_invalid_lock(self.tmp, content="not valid json at all!!!", age_seconds=30)
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertEqual(result.marker_version, 0)
        self.assertFalse(result.cleanup_allowed)
        self.assertEqual(result.reason, REASON_INVALID_MARKER_DETECT_ONLY)

    def test_json_not_dict_marker(self):
        _write_invalid_lock(self.tmp, content='[1, 2, 3]', age_seconds=30)
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertEqual(result.marker_version, 0)
        self.assertFalse(result.cleanup_allowed)

    def test_unknown_schema_version(self):
        pending = self.tmp / POP_PENDING_DIR
        pending.mkdir(parents=True, exist_ok=True)
        lock_path = pending / POP_LOCK_FILE
        marker = {"schema_version": 99, "component": "unknown"}
        lock_path.write_text(json.dumps(marker))
        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertFalse(result.cleanup_allowed)

    def test_invalid_marker_not_deleted(self):
        _write_invalid_lock(self.tmp, content="corrupt", age_seconds=700)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        detect_pop_pending_lock_staleness(self.tmp)
        self.assertTrue(lock_path.exists())


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid arguments
# ══════════════════════════════════════════════════════════════════════

class TestInvalidArgs(TestCase):
    """Tests with invalid function arguments."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stale_seconds_zero(self):
        result = detect_pop_pending_lock_staleness(self.tmp, stale_seconds=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_stale_seconds_negative(self):
        result = detect_pop_pending_lock_staleness(self.tmp, stale_seconds=-1)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_critical_le_stale(self):
        result = detect_pop_pending_lock_staleness(
            self.tmp, stale_seconds=600, critical_seconds=600)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_critical_lt_stale(self):
        result = detect_pop_pending_lock_staleness(
            self.tmp, stale_seconds=600, critical_seconds=500)
        self.assertEqual(result.status, STATUS_ERROR)

    def test_invalid_root_type(self):
        result = detect_pop_pending_lock_staleness(None)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_invalid_args_repr_safe(self):
        result = detect_pop_pending_lock_staleness(self.tmp, stale_seconds=0)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))


# ══════════════════════════════════════════════════════════════════════
# Tests: read failure
# ══════════════════════════════════════════════════════════════════════

class TestReadFailure(TestCase):
    """Tests when lock file exists but cannot be read."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_is_directory(self):
        pending = self.tmp / POP_PENDING_DIR
        pending.mkdir(parents=True, exist_ok=True)
        lock_path = pending / POP_LOCK_FILE
        lock_path.mkdir()  # lock is a directory — read will fail

        result = detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_READ_FAILED)
        self.assertFalse(result.stale_detected)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestNoSideEffects(TestCase):
    """Detector does NOT delete, rename, or modify anything."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_sent_quarantine_dry_run_failed_created(self):
        _write_v2_lock(self.tmp, age_seconds=700)
        detect_pop_pending_lock_staleness(self.tmp)
        pop_dir = self.tmp / "pop"
        if pop_dir.exists():
            for bad in ("sent", "quarantine", "dry_run", "failed"):
                self.assertFalse((pop_dir / bad).exists(),
                    f"'{bad}/' should not exist")

    def test_no_pending_modified(self):
        pending = self.tmp / POP_PENDING_DIR
        pending.mkdir(parents=True, exist_ok=True)
        jsonl_path = pending / "player_events.jsonl"
        original = '{"test": true}\n'
        jsonl_path.write_text(original)

        _write_v2_lock(self.tmp, age_seconds=700)
        detect_pop_pending_lock_staleness(self.tmp)
        self.assertEqual(jsonl_path.read_text(), original)

    def test_no_new_files_in_pending(self):
        _write_v2_lock(self.tmp, age_seconds=700)
        pending = self.tmp / POP_PENDING_DIR
        before = set()
        if pending.exists():
            before = {f.name for f in pending.iterdir()}

        detect_pop_pending_lock_staleness(self.tmp)

        after = {f.name for f in pending.iterdir()}
        self.assertEqual(before, after, "no new files should appear in pending")

    def test_module_no_http_imports(self):
        import kso_sidecar_agent.pop_stale_lock_detector as mod
        source = open(mod.__file__).read()
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import socket", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("http_client", source)

    def test_result_no_lock_path(self):
        _write_v2_lock(self.tmp, age_seconds=700)
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = repr(result) + format_pop_stale_lock_detection_result(result)
        self.assertNotIn("player_events.lock", text)
        self.assertNotIn(".lock", text.lower())

    def test_result_no_marker_json(self):
        _write_v2_lock(self.tmp, age_seconds=700)
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = repr(result) + format_pop_stale_lock_detection_result(result)
        self.assertNotIn("created_at_utc", text)
        self.assertNotIn("rotation_apply", text)

    def test_result_no_stacktrace(self):
        _write_v2_lock(self.tmp, age_seconds=700)
        result = detect_pop_pending_lock_staleness(self.tmp)
        text = repr(result) + format_pop_stale_lock_detection_result(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("line ", text)


# ══════════════════════════════════════════════════════════════════════
# Tests: format function standalone
# ══════════════════════════════════════════════════════════════════════

class TestFormatFunction(TestCase):
    """format_pop_stale_lock_detection_result standalone tests."""

    def test_format_all_fields_present(self):
        result = PopStaleLockDetectionResult(
            status=STATUS_OK,
            lock_present=True,
            marker_version=2,
            stale_detected=True,
            critical=False,
            cleanup_allowed=False,
            age_bucket=AGE_STALE,
            process_status=PROC_NOT_ALIVE,
            reason=REASON_STALE_DETECTED,
            stale_seconds=600,
            critical_seconds=1800,
            age_seconds=700,
        )
        text = format_pop_stale_lock_detection_result(result)
        self.assertIn("status: ok", text)
        self.assertIn("lock_present: true", text)
        self.assertIn("stale_detected: true", text)
        self.assertIn("critical: false", text)
        self.assertIn("cleanup_allowed: false", text)
        self.assertIn("age_bucket: stale", text)
        self.assertIn("process_status: not_alive", text)
        self.assertTrue(_no_forbidden(text))

    def test_format_no_forbidden_in_reason(self):
        for reason in [
            REASON_NO_LOCK, REASON_FRESH_LOCK, REASON_STALE_DETECTED,
            REASON_CRITICAL_STALE_DETECTED, REASON_V1_DETECT_ONLY,
            REASON_INVALID_MARKER_DETECT_ONLY, REASON_INVALID_ARGS,
            REASON_READ_FAILED,
        ]:
            result = PopStaleLockDetectionResult(reason=reason)
            text = format_pop_stale_lock_detection_result(result)
            self.assertTrue(_no_forbidden(text), f"reason={reason}: forbidden in format")


if __name__ == "__main__":
    import unittest
    unittest.main()
