"""Tests for KSO Sidecar PoP Pending Rewrite Atomic Helper."""

import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from kso_sidecar_agent.pop_pending_rewrite import (
    PopPendingRewriteResult,
    rewrite_pending_pop_events_atomic,
    format_pop_pending_rewrite_result,
    POP_JSONL_FILE,
    STATUS_WRITTEN,
    STATUS_SKIPPED,
    STATUS_ERROR,
    REASON_WRITTEN,
    REASON_LOCK_REQUIRED,
    REASON_UNSAFE_RECORD,
    REASON_WRITE_FAILED,
    REASON_INVALID_ROOT,
)
from kso_sidecar_agent.pop_pending_lock import (
    try_acquire_pop_pending_lock,
    release_pop_pending_lock,
    PopPendingLockResult,
    POP_PENDING_DIR,
    POP_LOCK_FILE,
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


def _safe_record(extra=None):
    r = {
        "schema_version": 1,
        "event_type": "would_play",
        "event_status": "completed",
        "created_at": "2026-06-19T10:00:00Z",
        "started_at": "2026-06-19T10:00:00Z",
        "duration_ms": 15000,
        "playback_allowed": True,
        "session_action": "play",
        "session_reason": "ready",
        "selected_order": 1,
        "selected_content_type": "video/mp4",
        "safety_state": "idle",
        "result": "would_play",
    }
    if extra:
        r.update(extra)
    return r


def _read_pending_jsonl(root):
    path = Path(root) / POP_PENDING_DIR / POP_JSONL_FILE
    if not path.exists():
        return None, []
    raw = path.read_text()
    records = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped:
            records.append(json.loads(stripped))
    return raw, records


def _acquire_lock(root):
    return try_acquire_pop_pending_lock(root)


# ══════════════════════════════════════════════════════════════════════
# Tests: lock required
# ══════════════════════════════════════════════════════════════════════

class TestRewriteLockRequired(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_lock_result_skipped(self):
        result = rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()])
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertEqual(result.reason, REASON_LOCK_REQUIRED)
        self.assertFalse(result.written)

    def test_lock_not_acquired_skipped(self):
        fake = PopPendingLockResult(acquired=False, reason="lock_unavailable")
        result = rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=fake)
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertEqual(result.reason, REASON_LOCK_REQUIRED)

    def test_not_pop_pending_lock_result_skipped(self):
        result = rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record()], lock_result="not_a_lock")
        self.assertEqual(result.reason, REASON_LOCK_REQUIRED)

    def test_no_lock_no_file_created(self):
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()])
        path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertFalse(path.exists(), "No file should be created without lock")


# ══════════════════════════════════════════════════════════════════════
# Tests: basic writes with lock
# ══════════════════════════════════════════════════════════════════════

class TestRewriteBasic(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_with_lock(self):
        lock = _acquire_lock(self.tmp)
        result = rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record()], lock_result=lock)
        release_pop_pending_lock(lock)
        self.assertEqual(result.status, STATUS_WRITTEN)
        self.assertTrue(result.written)
        self.assertEqual(result.records_written, 1)
        self.assertGreater(result.line_size_bytes, 0)
        self.assertEqual(result.reason, REASON_WRITTEN)

    def test_file_created_after_write(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=lock)
        release_pop_pending_lock(lock)
        path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(path.exists())

    def test_jsonl_parseable(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record(), _safe_record()], lock_result=lock)
        release_pop_pending_lock(lock)
        _, records = _read_pending_jsonl(self.tmp)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["schema_version"], 1)

    def test_each_line_ends_with_newline(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=lock)
        release_pop_pending_lock(lock)
        raw, _ = _read_pending_jsonl(self.tmp)
        self.assertIsNotNone(raw)
        self.assertTrue(raw.endswith("\n"))

    def test_empty_records_creates_empty_file(self):
        """Empty records list is allowed — creates empty pending file."""
        lock = _acquire_lock(self.tmp)
        result = rewrite_pending_pop_events_atomic(self.tmp, [], lock_result=lock)
        release_pop_pending_lock(lock)
        self.assertEqual(result.status, STATUS_WRITTEN)
        self.assertTrue(result.written)
        self.assertEqual(result.records_written, 0)
        self.assertEqual(result.line_size_bytes, 0)
        # File should exist but be empty
        path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(path.exists())

    def test_second_write_replaces_not_appends(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record({"marker": "first"})], lock_result=lock)
        rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record({"marker": "second"})], lock_result=lock)
        release_pop_pending_lock(lock)
        _, records = _read_pending_jsonl(self.tmp)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["marker"], "second")

    def test_lock_file_not_deleted_by_helper(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=lock)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists(), "Helper must NOT delete lock file")
        release_pop_pending_lock(lock)
        self.assertFalse(lock_path.exists(), "Lock released after call")


# ══════════════════════════════════════════════════════════════════════
# Tests: unsafe records
# ══════════════════════════════════════════════════════════════════════

class TestRewriteUnsafe(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _do_write(self, records):
        lock = _acquire_lock(self.tmp)
        result = rewrite_pending_pop_events_atomic(self.tmp, records, lock_result=lock)
        release_pop_pending_lock(lock)
        return result

    def test_non_dict_error(self):
        result = self._do_write(["not a dict"])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_forbidden_key_error(self):
        result = self._do_write([_safe_record({"token": "abc"})])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_forbidden_value_error(self):
        result = self._do_write([_safe_record({"safety_state": "access_token=xyz"})])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_forbidden_nested_error(self):
        result = self._do_write([_safe_record({"extra": {"nested": "secret=123"}})])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_UNSAFE_RECORD)

    def test_unsafe_record_preserves_original_pending(self):
        """If validation fails, original pending file stays untouched."""
        lock = _acquire_lock(self.tmp)
        # First write some safe data
        rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record({"marker": "original"})], lock_result=lock)
        # Then try unsafe write — should fail
        rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record({"token": "bad"})], lock_result=lock)
        release_pop_pending_lock(lock)
        _, records = _read_pending_jsonl(self.tmp)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["marker"], "original")


# ══════════════════════════════════════════════════════════════════════
# Tests: atomic / tmp cleanup
# ══════════════════════════════════════════════════════════════════════

class TestRewriteAtomic(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tmp_removed_after_success(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=lock)
        release_pop_pending_lock(lock)
        pending_dir = self.tmp / POP_PENDING_DIR
        tmp_files = list(pending_dir.glob(".*.tmp"))
        self.assertEqual(tmp_files, [], f"tmp leftovers: {tmp_files}")

    def test_tmp_removed_after_failure(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record({"token": "bad"})], lock_result=lock)
        release_pop_pending_lock(lock)
        pending_dir = self.tmp / POP_PENDING_DIR
        if pending_dir.exists():
            tmp_files = list(pending_dir.glob(".*.tmp"))
            self.assertEqual(tmp_files, [])

    def test_simulated_failure_cleans_tmp(self):
        with patch("os.replace", side_effect=OSError("simulated")):
            lock = _acquire_lock(self.tmp)
            result = rewrite_pending_pop_events_atomic(
                self.tmp, [_safe_record()], lock_result=lock)
            release_pop_pending_lock(lock)
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_WRITE_FAILED)
            self.assertNotIn("simulated", repr(result))

            pending_dir = self.tmp / POP_PENDING_DIR
            if pending_dir.exists():
                tmp_files = list(pending_dir.glob(".*.tmp"))
                self.assertEqual(tmp_files, [])

    def test_simulated_failure_no_stacktrace(self):
        with patch("os.replace", side_effect=OSError("disk full")):
            lock = _acquire_lock(self.tmp)
            result = rewrite_pending_pop_events_atomic(
                self.tmp, [_safe_record()], lock_result=lock)
            release_pop_pending_lock(lock)
            self.assertNotIn("disk full", repr(result))
            self.assertNotIn("OSError", repr(result))


# ══════════════════════════════════════════════════════════════════════
# Tests: invalid root
# ══════════════════════════════════════════════════════════════════════

class TestRewriteInvalidRoot(TestCase):
    def test_none_root_error(self):
        result = rewrite_pending_pop_events_atomic(None, [_safe_record()])
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ROOT)


# ══════════════════════════════════════════════════════════════════════
# Tests: safe output
# ══════════════════════════════════════════════════════════════════════

class TestRewriteSafeOutput(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _do_write(self):
        lock = _acquire_lock(self.tmp)
        result = rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record()], lock_result=lock)
        release_pop_pending_lock(lock)
        return result

    def test_format_no_forbidden(self):
        result = self._do_write()
        text = format_pop_pending_rewrite_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_forbidden(self):
        result = self._do_write()
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_file_path(self):
        result = self._do_write()
        text = repr(result)
        self.assertNotIn(str(self.tmp), text)

    def test_repr_no_lock_path(self):
        result = self._do_write()
        text = repr(result)
        self.assertNotIn("player_events.lock", text)

    def test_repr_no_filename(self):
        result = self._do_write()
        text = repr(result)
        self.assertNotIn(POP_JSONL_FILE, text.lower())

    def test_repr_no_ids(self):
        result = self._do_write()
        text = repr(result)
        self.assertNotIn("manifest_item_id", text.lower())
        self.assertNotIn("batch_id", text.lower())

    def test_repr_no_raw_json(self):
        result = self._do_write()
        text = repr(result)
        self.assertNotIn("would_play", text.lower())
        self.assertNotIn("selected_order", text)

    def test_format_contains_all_fields(self):
        result = self._do_write()
        text = format_pop_pending_rewrite_result(result)
        for field in ["status:", "written:", "records_written:", "line_size_bytes:", "reason:"]:
            self.assertIn(field, text, f"Missing field '{field}'")

    def test_no_stacktrace(self):
        with patch("os.replace", side_effect=OSError()):
            lock = _acquire_lock(self.tmp)
            result = rewrite_pending_pop_events_atomic(
                self.tmp, [_safe_record()], lock_result=lock)
            release_pop_pending_lock(lock)
        text = repr(result)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("OSError", text)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestRewriteNoSideEffects(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_does_not_create_sent_dir(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=lock)
        release_pop_pending_lock(lock)
        for bad in ("sent", "quarantine", "dry_run", "failed"):
            self.assertFalse((self.tmp / "pop" / bad).exists(),
                             f"'{bad}/' should not exist after rewrite")

    def test_no_http_imports(self):
        mod_path = Path(__file__).parent.parent / "kso_sidecar_agent" / "pop_pending_rewrite.py"
        content = mod_path.read_text()
        self.assertNotIn("import urllib", content)
        self.assertNotIn("import requests", content)
        self.assertNotIn("import http", content)

    def test_does_not_read_secret_config(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=lock)
        release_pop_pending_lock(lock)
        # Just verifies no exception on missing config
        self.assertFalse((self.tmp / "config").exists())


# ══════════════════════════════════════════════════════════════════════
# Tests: lock preserved by caller
# ══════════════════════════════════════════════════════════════════════

class TestRewriteLockPreserved(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_still_held_after_rewrite(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=lock)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists(), "Lock file must still exist after rewrite")
        release_pop_pending_lock(lock)

    def test_caller_can_release_lock_after_rewrite(self):
        lock = _acquire_lock(self.tmp)
        rewrite_pending_pop_events_atomic(self.tmp, [_safe_record()], lock_result=lock)
        release = release_pop_pending_lock(lock)
        self.assertTrue(release.released)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists(), "Lock released by caller after rewrite")

    def test_can_write_multiple_times_under_same_lock(self):
        lock = _acquire_lock(self.tmp)
        r1 = rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record({"seq": 1})], lock_result=lock)
        self.assertTrue(r1.written)
        r2 = rewrite_pending_pop_events_atomic(
            self.tmp, [_safe_record({"seq": 2})], lock_result=lock)
        self.assertTrue(r2.written)
        release_pop_pending_lock(lock)
        _, records = _read_pending_jsonl(self.tmp)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["seq"], 2)


if __name__ == "__main__":
    import unittest
    unittest.main()
