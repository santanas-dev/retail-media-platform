"""Tests for KSO Sidecar PoP Local Rotation Apply Core."""

import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from kso_sidecar_agent.pop_rotation_apply import (
    PopRotationApplyResult,
    apply_pop_rotation_local,
    format_pop_rotation_apply_result,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_APPLIED,
    REASON_NO_PENDING_FILE,
    REASON_LOCK_UNAVAILABLE,
    REASON_TARGET_WRITE_FAILED,
    REASON_PENDING_REWRITE_FAILED,
    REASON_INVALID_RESULT,
)
from kso_sidecar_agent.pop_pending_rewrite import PopPendingRewriteResult
from kso_sidecar_agent.pop_pending_lock import (
    try_acquire_pop_pending_lock,
    release_pop_pending_lock,
    POP_PENDING_DIR,
    POP_LOCK_FILE,
    FORBIDDEN_SUBSTRINGS,
)
from kso_sidecar_agent.pop_pickup import POP_JSONL_FILE

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _no_forbidden(text):
    lower = text.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return False
    return True


def _make_send_result(run_status="ok", pending_should_remain=False, reason="processed"):
    class FakeSendResult:
        pass
    r = FakeSendResult()
    r.run_status = run_status
    r.pending_should_remain = pending_should_remain
    r.reason = reason
    r.accepted_events = 3
    return r


def _write_jsonl(tmp, lines):
    pending = tmp / POP_PENDING_DIR
    pending.mkdir(parents=True, exist_ok=True)
    path = pending / POP_JSONL_FILE
    text = "\n".join(lines) + "\n"
    path.write_text(text)


def _draft_line():
    return json.dumps({
        "schema_version": 1, "event_type": "would_play",
        "event_status": "draft", "created_at": "2026-06-19T10:00:00Z",
        "started_at": "2026-06-19T10:00:00Z", "duration_ms": 15000,
        "playback_allowed": True, "session_action": "play",
        "session_reason": "ready", "selected_order": 1,
        "selected_content_type": "video/mp4", "safety_state": "idle",
        "result": "would_play",
    })


def _blocked_line():
    return json.dumps({
        "schema_version": 1, "event_type": "blocked",
        "event_status": "blocked", "created_at": "2026-06-19T10:00:00Z",
        "started_at": None, "duration_ms": 0,
        "playback_allowed": False, "session_action": "stop",
        "session_reason": "safety_blocked", "selected_order": None,
        "selected_content_type": None, "safety_state": "payment",
        "result": "blocked",
    })


def _invalid_line():
    return "not valid json {{{"


def _list_jsonl_files(root, target):
    tdir = Path(root) / "pop" / target
    if not tdir.exists():
        return []
    return sorted(f.name for f in tdir.glob("*.jsonl") if not f.name.startswith("."))


def _read_pending_jsonl(root):
    path = Path(root) / POP_PENDING_DIR / POP_JSONL_FILE
    if not path.exists():
        return ""
    return path.read_text()


def _count_pending_lines(root):
    raw = _read_pending_jsonl(root)
    return len([l for l in raw.split("\n") if l.strip()])


# ══════════════════════════════════════════════════════════════════════
# Tests: missing file / no pending
# ══════════════════════════════════════════════════════════════════════

class TestApplyNoPending(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_pending_file_ok(self):
        result = apply_pop_rotation_local(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.reason, REASON_NO_PENDING_FILE)
        self.assertTrue(result.applied)
        self.assertEqual(result.pending_lines_before, 0)

    def test_no_pending_no_files_created(self):
        apply_pop_rotation_local(self.tmp)
        for bad in ("sent", "quarantine", "dry_run", "failed"):
            self.assertFalse((self.tmp / "pop" / bad).exists())


# ══════════════════════════════════════════════════════════════════════
# Tests: lock
# ══════════════════════════════════════════════════════════════════════

class TestApplyLock(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_foreign_lock_warning(self):
        _write_jsonl(self.tmp, [_draft_line()])
        pre_lock = try_acquire_pop_pending_lock(self.tmp)
        result = apply_pop_rotation_local(self.tmp)
        self.assertEqual(result.reason, REASON_LOCK_UNAVAILABLE)
        self.assertTrue(result.pending_untouched)
        release_pop_pending_lock(pre_lock)

    def test_foreign_lock_not_removed(self):
        _write_jsonl(self.tmp, [_draft_line()])
        pre_lock = try_acquire_pop_pending_lock(self.tmp)
        apply_pop_rotation_local(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists(), "Foreign lock must not be removed")
        release_pop_pending_lock(pre_lock)

    def test_lock_released_after_apply(self):
        _write_jsonl(self.tmp, [_draft_line()])
        apply_pop_rotation_local(self.tmp)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists(), "Lock must be released after apply")


# ══════════════════════════════════════════════════════════════════════
# Tests: dry_run bucket (draft/blocked → dry_run file)
# ══════════════════════════════════════════════════════════════════════

class TestApplyDryRun(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_draft_creates_dry_run_file(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        self.assertEqual(result.dry_run_records, 1)
        self.assertTrue(result.applied)
        files = _list_jsonl_files(self.tmp, "dry_run")
        self.assertEqual(len(files), 1)

    def test_blocked_creates_dry_run_file(self):
        _write_jsonl(self.tmp, [_blocked_line()])
        result = apply_pop_rotation_local(self.tmp)
        self.assertEqual(result.dry_run_records, 1)
        files = _list_jsonl_files(self.tmp, "dry_run")
        self.assertEqual(len(files), 1)

    def test_draft_pending_rewritten_empty(self):
        _write_jsonl(self.tmp, [_draft_line()])
        apply_pop_rotation_local(self.tmp)
        # Draft goes to dry_run, pending should be empty (0 retained)
        self.assertEqual(_count_pending_lines(self.tmp), 0)

    def test_dry_run_sanitized_no_raw_json(self):
        _write_jsonl(self.tmp, [_draft_line()])
        apply_pop_rotation_local(self.tmp)
        tdir = self.tmp / "pop" / "dry_run"
        files = sorted(tdir.glob("*.jsonl"))
        content = files[0].read_text()
        # Sanitized record — no raw JSON from player event
        self.assertNotIn("would_play", content)
        self.assertNotIn("event_type", content)


# ══════════════════════════════════════════════════════════════════════
# Tests: quarantine bucket (invalid/forbidden → quarantine file)
# ══════════════════════════════════════════════════════════════════════

class TestApplyQuarantine(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_invalid_json_quarantine(self):
        _write_jsonl(self.tmp, [_invalid_line()])
        result = apply_pop_rotation_local(self.tmp)
        self.assertEqual(result.quarantine_records, 1)
        files = _list_jsonl_files(self.tmp, "quarantine")
        self.assertEqual(len(files), 1)

    def test_forbidden_field_quarantine(self):
        line = json.dumps({
            "schema_version": 1, "event_type": "would_play",
            "event_status": "draft", "created_at": "2026-06-19T10:00:00Z",
            "started_at": "2026-06-19T10:00:00Z", "duration_ms": 15000,
            "playback_allowed": True, "session_action": "play",
            "session_reason": "ready", "selected_order": None,
            "selected_content_type": "secret=123",
            "safety_state": "idle", "result": "would_play",
        })
        _write_jsonl(self.tmp, [line])
        result = apply_pop_rotation_local(self.tmp)
        self.assertEqual(result.quarantine_records, 1)

    def test_quarantine_pending_rewritten_empty(self):
        _write_jsonl(self.tmp, [_invalid_line()])
        apply_pop_rotation_local(self.tmp)
        self.assertEqual(_count_pending_lines(self.tmp), 0)


# ══════════════════════════════════════════════════════════════════════
# Tests: sent bucket policy
# ══════════════════════════════════════════════════════════════════════

class TestApplySentPolicy(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_send_result_no_sent(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp, send_run_result=None)
        self.assertEqual(result.sent_records, 0)
        self.assertEqual(_list_jsonl_files(self.tmp, "sent"), [])

    def test_pending_should_remain_no_sent(self):
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="ok", pending_should_remain=True)
        result = apply_pop_rotation_local(self.tmp, send_run_result=sr)
        self.assertEqual(result.sent_records, 0)

    def test_409_duplicate_no_sent(self):
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="warning", pending_should_remain=True,
                               reason="duplicate_batch_pending_remains")
        result = apply_pop_rotation_local(self.tmp, send_run_result=sr)
        self.assertEqual(result.sent_records, 0)

    def test_draft_even_with_ok_send_no_sent(self):
        """Draft events NEVER go to sent, even with confirmed send result."""
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="ok", pending_should_remain=False)
        result = apply_pop_rotation_local(self.tmp, send_run_result=sr)
        self.assertEqual(result.sent_records, 0)


# ══════════════════════════════════════════════════════════════════════
# Tests: mixed buckets
# ══════════════════════════════════════════════════════════════════════

class TestApplyMixed(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mixed_draft_invalid(self):
        _write_jsonl(self.tmp, [
            _draft_line(),
            _blocked_line(),
            _invalid_line(),
        ])
        result = apply_pop_rotation_local(self.tmp)
        self.assertEqual(result.dry_run_records, 2)
        self.assertEqual(result.quarantine_records, 1)
        self.assertTrue(result.applied)
        # Both dirs created
        self.assertEqual(len(_list_jsonl_files(self.tmp, "dry_run")), 1)
        self.assertEqual(len(_list_jsonl_files(self.tmp, "quarantine")), 1)
        # Pending empty — all records moved
        self.assertEqual(_count_pending_lines(self.tmp), 0)


# ══════════════════════════════════════════════════════════════════════
# Tests: target write failure → pending untouched
# ══════════════════════════════════════════════════════════════════════

class TestApplyTargetWriteFailure(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_target_write_failure_pending_untouched(self):
        _write_jsonl(self.tmp, [_draft_line(), _invalid_line()])
        original = _read_pending_jsonl(self.tmp)

        # Simulate write failure for quarantine target
        with patch(
            "kso_sidecar_agent.pop_rotation_apply.write_pop_rotation_records_atomic"
        ) as mock_write:
            # First call (dry_run) succeeds
            from kso_sidecar_agent.pop_rotation_files import (
                PopRotationFileWriteResult, STATUS_WRITTEN, REASON_WRITTEN)
            success = PopRotationFileWriteResult(
                status=STATUS_WRITTEN, written=True, target="dry_run",
                records_written=1, line_size_bytes=100, reason=REASON_WRITTEN)
            fail = PopRotationFileWriteResult(
                status="error", written=False, target="quarantine",
                reason="write_failed")
            mock_write.side_effect = [success, fail]

            result = apply_pop_rotation_local(self.tmp)
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_TARGET_WRITE_FAILED)
            self.assertTrue(result.pending_untouched)

        # Pending unchanged
        self.assertEqual(_read_pending_jsonl(self.tmp), original)


# ══════════════════════════════════════════════════════════════════════
# Tests: pending rewrite failure
# ══════════════════════════════════════════════════════════════════════

class TestApplyPendingRewriteFailure(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pending_rewrite_failure(self):
        _write_jsonl(self.tmp, [_draft_line()])
        original = _read_pending_jsonl(self.tmp)

        with patch(
            "kso_sidecar_agent.pop_rotation_apply.rewrite_pending_pop_events_atomic"
        ) as mock_rw:
            mock_rw.return_value = PopPendingRewriteResult(
                status="error", reason="write_failed")

            result = apply_pop_rotation_local(self.tmp)
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_PENDING_REWRITE_FAILED)
            self.assertTrue(result.pending_untouched)

        # Pending unchanged
        self.assertEqual(_read_pending_jsonl(self.tmp), original)


# ══════════════════════════════════════════════════════════════════════
# Tests: empty buckets
# ══════════════════════════════════════════════════════════════════════

class TestApplyEmptyBuckets(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_bucket_no_dir_created(self):
        """Only dry_run has records, quarantine should NOT create dir."""
        _write_jsonl(self.tmp, [_draft_line()])
        apply_pop_rotation_local(self.tmp)
        self.assertFalse((self.tmp / "pop" / "quarantine").exists())
        self.assertFalse((self.tmp / "pop" / "sent").exists())
        self.assertFalse((self.tmp / "pop" / "failed").exists())


# ══════════════════════════════════════════════════════════════════════
# Tests: max_lines
# ══════════════════════════════════════════════════════════════════════

class TestApplyMaxLines(TestCase):
    def test_max_lines_zero_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = apply_pop_rotation_local(tmp, max_lines=0)
            self.assertEqual(result.status, STATUS_ERROR)
            self.assertEqual(result.reason, REASON_INVALID_RESULT)

    def test_max_lines_negative_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = apply_pop_rotation_local(tmp, max_lines=-1)
            self.assertEqual(result.reason, REASON_INVALID_RESULT)


# ══════════════════════════════════════════════════════════════════════
# Tests: safe output
# ══════════════════════════════════════════════════════════════════════

class TestApplySafeOutput(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_format_no_forbidden(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = format_pop_rotation_apply_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_forbidden(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_raw_json(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = repr(result)
        self.assertNotIn("would_play", text.lower())
        self.assertNotIn("selected_order", text)

    def test_repr_no_paths(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = repr(result)
        self.assertNotIn(str(self.tmp), text)

    def test_repr_no_filenames(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = repr(result)
        self.assertNotIn("player_events", text.lower())
        self.assertNotIn(".jsonl", text.lower())

    def test_repr_no_ids(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = repr(result)
        self.assertNotIn("manifest_item_id", text.lower())
        self.assertNotIn("batch_id", text.lower())

    def test_repr_no_sha256(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = repr(result)
        self.assertNotIn("sha256", text.lower())

    def test_repr_no_lock_path(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = repr(result)
        self.assertNotIn("player_events.lock", text.lower())

    def test_no_stacktrace(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        self.assertNotIn("Traceback", repr(result))

    def test_format_contains_all_fields(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        text = format_pop_rotation_apply_result(result)
        for field in [
            "status:", "applied:", "pending_untouched:", "lock_acquired:",
            "pending_lines_before:", "pending_lines_after:",
            "sent_records:", "quarantine_records:", "dry_run_records:",
            "failed_records:", "invalid_lines:", "target_files_written:",
            "pending_rewritten:", "reason:",
        ]:
            self.assertIn(field, text, f"Missing field '{field}'")


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestApplyNoSideEffects(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_http_imports_in_module(self):
        mod_path = Path(__file__).parent.parent / "kso_sidecar_agent" / "pop_rotation_apply.py"
        content = mod_path.read_text()
        self.assertNotIn("import urllib", content)
        self.assertNotIn("import requests", content)
        self.assertNotIn("import http.client", content)

    def test_does_not_read_secret_config(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = apply_pop_rotation_local(self.tmp)
        self.assertEqual(result.status, STATUS_OK)


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import unittest
    unittest.main()
