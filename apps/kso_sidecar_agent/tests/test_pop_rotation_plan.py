"""Tests for KSO Sidecar PoP Local Rotation Plan Core.

Tests build_pop_rotation_plan() — in-memory plan, no file writes.
"""

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from kso_sidecar_agent.pop_rotation_plan import (
    PopRotationPlanResult,
    build_pop_rotation_plan,
    format_pop_rotation_plan_result,
    PLAN_OK,
    PLAN_WARNING,
    PLAN_ERROR,
    REASON_PLANNED,
    REASON_NO_PENDING_FILE,
    REASON_LOCK_UNAVAILABLE,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_SEND_NOT_SUCCESSFUL,
    REASON_INVALID_LINES_PRESENT,
    REASON_PLAN_LIMITED,
    REASON_READ_FAILED,
    REASON_INVALID_RESULT,
    FORBIDDEN_SUBSTRINGS,
)
from kso_sidecar_agent.pop_pending_lock import (
    try_acquire_pop_pending_lock,
    release_pop_pending_lock,
    POP_PENDING_DIR,
    POP_LOCK_FILE,
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
    """Create a duck-typed PopSendRunResult."""
    class FakeSendResult:
        pass
    r = FakeSendResult()
    r.run_status = run_status
    r.pending_should_remain = pending_should_remain
    r.reason = reason
    r.accepted_events = 3
    return r


def _write_jsonl(tmp, lines):
    """Write lines to pop/pending/player_events.jsonl."""
    pending = tmp / POP_PENDING_DIR
    pending.mkdir(parents=True, exist_ok=True)
    path = pending / POP_JSONL_FILE
    text = "\n".join(lines) + "\n"
    path.write_text(text)


def _draft_line():
    return json.dumps({
        "schema_version": 1,
        "event_type": "would_play",
        "event_status": "draft",
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
    })


def _blocked_line():
    return json.dumps({
        "schema_version": 1,
        "event_type": "blocked",
        "event_status": "blocked",
        "created_at": "2026-06-19T10:00:00Z",
        "started_at": None,
        "duration_ms": 0,
        "playback_allowed": False,
        "session_action": "stop",
        "session_reason": "safety_blocked",
        "selected_order": None,
        "selected_content_type": None,
        "safety_state": "payment",
        "result": "blocked",
    })


def _failed_line():
    return json.dumps({
        "schema_version": 1,
        "event_type": "error",
        "event_status": "failed",
        "created_at": "2026-06-19T10:00:00Z",
        "started_at": None,
        "duration_ms": 0,
        "playback_allowed": False,
        "session_action": "stop",
        "session_reason": "invalid_state",
        "selected_order": None,
        "selected_content_type": None,
        "safety_state": "error",
        "result": "error",
    })


# ══════════════════════════════════════════════════════════════════════
# Tests: missing file
# ══════════════════════════════════════════════════════════════════════

class TestPlanMissingFile(TestCase):
    """No pending file → ok, empty plan."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_ok(self):
        result = build_pop_rotation_plan(self.tmp)
        self.assertEqual(result.rotation_status, PLAN_OK)
        self.assertEqual(result.reason, REASON_NO_PENDING_FILE)
        self.assertEqual(result.pending_lines_before, 0)
        self.assertTrue(result.pending_untouched)


# ══════════════════════════════════════════════════════════════════════
# Tests: lock
# ══════════════════════════════════════════════════════════════════════

class TestPlanLock(TestCase):
    """Lock behavior in rotation plan."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_acquired_and_released(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = build_pop_rotation_plan(self.tmp)
        self.assertTrue(result.lock_acquired)
        # Lock must be released after plan
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists(),
            f"lock not released after plan: {lock_path}")

    def test_lock_unavailable(self):
        _write_jsonl(self.tmp, [_draft_line()])
        # Pre-acquire lock
        lock_result = try_acquire_pop_pending_lock(self.tmp)
        self.assertTrue(lock_result.acquired)

        result = build_pop_rotation_plan(self.tmp)
        self.assertFalse(result.lock_acquired)
        self.assertEqual(result.reason, REASON_LOCK_UNAVAILABLE)
        self.assertTrue(result.pending_untouched)

        # Foreign lock not removed
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists(), "foreign lock should not be removed")

        release_pop_pending_lock(lock_result)


# ══════════════════════════════════════════════════════════════════════
# Tests: classification
# ══════════════════════════════════════════════════════════════════════

class TestPlanClassification(TestCase):
    """Events are classified correctly."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_draft_goes_to_dry_run(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = build_pop_rotation_plan(self.tmp)
        self.assertEqual(result.dry_run_lines, 1)
        self.assertEqual(result.sent_lines, 0)
        self.assertEqual(result.pending_lines_before, 1)
        self.assertEqual(result.pending_lines_after, 0)

    def test_blocked_goes_to_dry_run(self):
        _write_jsonl(self.tmp, [_blocked_line()])
        result = build_pop_rotation_plan(self.tmp)
        self.assertEqual(result.dry_run_lines, 1)
        self.assertEqual(result.sent_lines, 0)

    def test_failed_goes_to_dry_run(self):
        _write_jsonl(self.tmp, [_failed_line()])
        result = build_pop_rotation_plan(self.tmp)
        self.assertEqual(result.dry_run_lines, 1)
        self.assertEqual(result.sent_lines, 0)

    def test_invalid_json_quarantine(self):
        _write_jsonl(self.tmp, ["not valid json{"])
        result = build_pop_rotation_plan(self.tmp)
        self.assertEqual(result.invalid_lines, 1)
        self.assertEqual(result.quarantine_lines, 1)

    def test_forbidden_value_quarantine(self):
        line = json.dumps({
            "schema_version": 1,
            "event_type": "would_play",
            "event_status": "draft",
            "created_at": "2026-06-19T10:00:00Z",
            "started_at": None,
            "duration_ms": 0,
            "playback_allowed": True,
            "session_action": "play",
            "session_reason": "ready",
            "selected_order": None,
            "selected_content_type": "token=abc",
            "safety_state": "idle",
            "result": "would_play",
        })
        _write_jsonl(self.tmp, [line])
        result = build_pop_rotation_plan(self.tmp)
        self.assertEqual(result.quarantine_lines, 1)


# ══════════════════════════════════════════════════════════════════════
# Tests: send_run_result policy
# ══════════════════════════════════════════════════════════════════════

class TestPlanSendResultPolicy(TestCase):
    """send_run_result controls sent_lines planning."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_send_result_no_sent(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = build_pop_rotation_plan(self.tmp, send_run_result=None)
        self.assertEqual(result.sent_lines, 0)

    def test_pending_should_remain_true_no_sent(self):
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="ok", pending_should_remain=True)
        result = build_pop_rotation_plan(self.tmp, send_run_result=sr)
        self.assertEqual(result.sent_lines, 0)
        self.assertEqual(result.reason, REASON_PENDING_SHOULD_REMAIN)
        self.assertTrue(result.pending_untouched)

    def test_send_warning_no_sent(self):
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="warning", pending_should_remain=True)
        result = build_pop_rotation_plan(self.tmp, send_run_result=sr)
        self.assertEqual(result.sent_lines, 0)

    def test_409_duplicate_no_sent(self):
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="warning", pending_should_remain=True,
                               reason="duplicate_batch_pending_remains")
        result = build_pop_rotation_plan(self.tmp, send_run_result=sr)
        self.assertEqual(result.sent_lines, 0)
        self.assertEqual(result.reason, REASON_DUPLICATE_PENDING_REMAINS)
        self.assertTrue(result.pending_untouched)

    def test_ok_send_with_draft_no_sent(self):
        # Even with ok send, draft events don't become sent — they stay dry_run
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="ok", pending_should_remain=False)
        result = build_pop_rotation_plan(self.tmp, send_run_result=sr)
        self.assertEqual(result.sent_lines, 0)  # draft, not eligible
        self.assertEqual(result.dry_run_lines, 1)


# ══════════════════════════════════════════════════════════════════════
# Tests: max_lines
# ══════════════════════════════════════════════════════════════════════

class TestPlanMaxLines(TestCase):
    """max_lines limit and validation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_max_lines_zero_error(self):
        result = build_pop_rotation_plan(self.tmp, max_lines=0)
        self.assertEqual(result.rotation_status, PLAN_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESULT)

    def test_max_lines_negative_error(self):
        result = build_pop_rotation_plan(self.tmp, max_lines=-5)
        self.assertEqual(result.reason, REASON_INVALID_RESULT)

    def test_max_lines_limit(self):
        lines = [_draft_line() for _ in range(5)]
        _write_jsonl(self.tmp, lines)
        result = build_pop_rotation_plan(self.tmp, max_lines=2)
        self.assertTrue(result.plan_limited)
        self.assertEqual(result.reason, REASON_PLAN_LIMITED)
        # 2 lines processed, 3 beyond limit → stay pending
        self.assertEqual(result.pending_lines_after, 3)


# ══════════════════════════════════════════════════════════════════════
# Tests: safe output
# ══════════════════════════════════════════════════════════════════════

class TestPlanSafeOutput(TestCase):
    """format_pop_rotation_plan_result safety."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_format_no_forbidden_empty(self):
        result = build_pop_rotation_plan(self.tmp)
        text = format_pop_rotation_plan_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_no_forbidden_with_data(self):
        _write_jsonl(self.tmp, [_draft_line(), _blocked_line()])
        result = build_pop_rotation_plan(self.tmp)
        text = format_pop_rotation_plan_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_no_forbidden_lock_unavailable(self):
        _write_jsonl(self.tmp, [_draft_line()])
        lock_result = try_acquire_pop_pending_lock(self.tmp)
        result = build_pop_rotation_plan(self.tmp)
        release_pop_pending_lock(lock_result)
        text = format_pop_rotation_plan_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_forbidden(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = build_pop_rotation_plan(self.tmp)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_raw_json(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = build_pop_rotation_plan(self.tmp)
        text = repr(result)
        self.assertNotIn("would_play", text.lower())
        self.assertNotIn("selected_order", text)

    def test_repr_no_lock_path(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = build_pop_rotation_plan(self.tmp)
        text = repr(result)
        self.assertNotIn("player_events.lock", text)

    def test_repr_no_manifest_item_id(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = build_pop_rotation_plan(self.tmp)
        text = repr(result)
        self.assertNotIn("manifest_item_id", text)

    def test_repr_no_sha256(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = build_pop_rotation_plan(self.tmp)
        text = repr(result)
        self.assertNotIn("sha256", text)

    def test_format_contains_all_fields(self):
        result = build_pop_rotation_plan(self.tmp)
        text = format_pop_rotation_plan_result(result)
        for field in [
            "rotation_status:", "pending_lines_before:", "pending_lines_after:",
            "sent_lines:", "quarantine_lines:", "dry_run_lines:", "failed_lines:",
            "invalid_lines:", "pending_untouched:", "lock_acquired:",
            "plan_limited:", "max_lines:", "reason:",
        ]:
            self.assertIn(field, text, f"Missing field '{field}'")


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestPlanNoSideEffects(TestCase):
    """Plan does NOT write files, create dirs, or do HTTP."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_plan_does_not_create_sent(self):
        _write_jsonl(self.tmp, [_draft_line()])
        build_pop_rotation_plan(self.tmp)
        for bad in ("sent", "quarantine", "dry_run", "failed"):
            pop_dir = self.tmp / "pop"
            if pop_dir.exists():
                bad_path = pop_dir / bad
                self.assertFalse(bad_path.exists(),
                    f"'{bad}/' dir should not exist after plan")

    def test_plan_does_not_modify_jsonl(self):
        lines = [_draft_line(), _blocked_line()]
        _write_jsonl(self.tmp, lines)
        jsonl_path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        original = jsonl_path.read_text()
        build_pop_rotation_plan(self.tmp)
        self.assertEqual(jsonl_path.read_text(), original)

    def test_plan_does_not_delete_pending(self):
        _write_jsonl(self.tmp, [_draft_line()])
        jsonl_path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        build_pop_rotation_plan(self.tmp)
        self.assertTrue(jsonl_path.exists())

    def test_module_no_http_imports(self):
        with open(__file__.replace("tests/test_pop_rotation_plan.py", "kso_sidecar_agent/pop_rotation_plan.py")) as f:
            content = f.read()
        self.assertNotIn("import urllib", content)
        self.assertNotIn("import requests", content)


if __name__ == "__main__":
    import unittest
    unittest.main()
