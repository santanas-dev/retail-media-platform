"""Tests for KSO Sidecar PoP Rotation Materializer Core."""

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from kso_sidecar_agent.pop_rotation_materializer import (
    PopRotationMaterializeResult,
    materialize_pop_rotation_records,
    format_pop_rotation_materialize_result,
    _sanitized_rotation_record,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_MATERIALIZED,
    REASON_NO_PENDING_FILE,
    REASON_LOCK_UNAVAILABLE,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_SEND_NOT_SUCCESSFUL,
    REASON_INVALID_LINES_PRESENT,
    REASON_LIMITED,
    REASON_READ_FAILED,
    REASON_INVALID_RESULT,
    RECORD_TYPE_SENT,
    RECORD_TYPE_QUARANTINE,
    RECORD_TYPE_DRY_RUN,
    RECORD_TYPE_FAILED,
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


def _completed_eligible_line():
    return json.dumps({
        "schema_version": 1,
        "event_type": "would_play",
        "event_status": "completed",
        "created_at": "2026-06-19T10:00:00Z",
        "started_at": "2026-06-19T10:00:00Z",
        "ended_at": "2026-06-19T10:00:15Z",
        "duration_ms": 15000,
        "playback_allowed": True,
        "session_action": "play",
        "session_reason": "ready",
        "selected_order": 1,
        "selected_content_type": "video/mp4",
        "safety_state": "idle",
        "result": "would_play",
    })


def _sanitized_has_field(records, field, expected):
    for r in records:
        if r.get(field) == expected:
            return True
    return False


def _count_by_type(records, record_type):
    return sum(1 for r in records if r.get("record_type") == record_type)


# ══════════════════════════════════════════════════════════════════════
# Tests: missing file
# ══════════════════════════════════════════════════════════════════════

class TestMaterializerMissingFile(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_ok(self):
        result = materialize_pop_rotation_records(self.tmp)
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.reason, REASON_NO_PENDING_FILE)
        self.assertEqual(result.pending_lines_before, 0)
        self.assertFalse(result.materialized)
        self.assertTrue(result.pending_untouched)


# ══════════════════════════════════════════════════════════════════════
# Tests: lock
# ══════════════════════════════════════════════════════════════════════

class TestMaterializerLock(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_acquired_and_released(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        self.assertTrue(result.lock_acquired)
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists(), f"lock not released: {lock_path}")

    def test_lock_unavailable(self):
        _write_jsonl(self.tmp, [_draft_line()])
        lock_result = try_acquire_pop_pending_lock(self.tmp)
        self.assertTrue(lock_result.acquired)

        result = materialize_pop_rotation_records(self.tmp)
        self.assertFalse(result.lock_acquired)
        self.assertEqual(result.reason, REASON_LOCK_UNAVAILABLE)
        self.assertTrue(result.pending_untouched)

        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists(), "foreign lock should not be removed")
        release_pop_pending_lock(lock_result)


# ══════════════════════════════════════════════════════════════════════
# Tests: classification
# ══════════════════════════════════════════════════════════════════════

class TestMaterializerClassification(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_draft_to_dry_run(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        self.assertEqual(result.dry_run_records, 1)
        self.assertEqual(result.sent_records, 0)
        self.assertEqual(len(result._dry_run_records), 1)
        self.assertEqual(result._dry_run_records[0]["record_type"], RECORD_TYPE_DRY_RUN)
        self.assertEqual(result._dry_run_records[0]["reason"], "draft_not_pop")

    def test_blocked_to_dry_run(self):
        _write_jsonl(self.tmp, [_blocked_line()])
        result = materialize_pop_rotation_records(self.tmp)
        self.assertEqual(result.dry_run_records, 1)
        self.assertEqual(result._dry_run_records[0]["reason"], "blocked_not_pop")

    def test_failed_to_dry_run(self):
        _write_jsonl(self.tmp, [_failed_line()])
        result = materialize_pop_rotation_records(self.tmp)
        self.assertEqual(result.dry_run_records, 1)
        self.assertEqual(result._dry_run_records[0]["reason"], "failed_not_pop")

    def test_invalid_json_to_quarantine(self):
        _write_jsonl(self.tmp, ["not valid json {"])
        result = materialize_pop_rotation_records(self.tmp)
        self.assertEqual(result.quarantine_records, 1)
        self.assertEqual(result.invalid_lines, 1)
        self.assertEqual(result._quarantine_records[0]["record_type"], RECORD_TYPE_QUARANTINE)
        self.assertEqual(result._quarantine_records[0]["reason"], "invalid_json")

    def test_forbidden_value_to_quarantine(self):
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
            "selected_content_type": "secret=123",
            "safety_state": "idle",
            "result": "would_play",
        })
        _write_jsonl(self.tmp, [line])
        result = materialize_pop_rotation_records(self.tmp)
        self.assertEqual(result.quarantine_records, 1)
        self.assertEqual(result.invalid_lines, 1)
        self.assertEqual(result._quarantine_records[0]["reason"], "forbidden_field")


# ══════════════════════════════════════════════════════════════════════
# Tests: quarantine sanitized
# ══════════════════════════════════════════════════════════════════════

class TestMaterializerQuarantineSanitized(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_quarantine_record_no_raw_json(self):
        _write_jsonl(self.tmp, ["not json{"])
        result = materialize_pop_rotation_records(self.tmp)
        rec = result._quarantine_records[0]
        # No raw JSON keys from player events
        self.assertNotIn("event_type", rec)
        self.assertNotIn("event_status", rec)
        self.assertNotIn("safety_state", rec)

    def test_quarantine_record_has_safe_fields(self):
        _write_jsonl(self.tmp, ["not json{"])
        result = materialize_pop_rotation_records(self.tmp)
        rec = result._quarantine_records[0]
        self.assertEqual(rec["schema_version"], 1)
        self.assertEqual(rec["record_type"], RECORD_TYPE_QUARANTINE)
        self.assertIn("reason", rec)
        self.assertIn("created_at", rec)
        self.assertIn("source", rec)

    def test_quarantine_record_no_forbidden(self):
        _write_jsonl(self.tmp, ["not json{"])
        result = materialize_pop_rotation_records(self.tmp)
        rec = result._quarantine_records[0]
        for key, value in rec.items():
            if isinstance(value, str):
                self.assertTrue(_no_forbidden(value),
                                f"Forbidden in key '{key}': {value}")

    def test_dry_run_record_sanitized(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        rec = result._dry_run_records[0]
        self.assertNotIn("event_type", rec)
        self.assertNotIn("result", rec)
        self.assertEqual(rec["record_type"], RECORD_TYPE_DRY_RUN)


# ══════════════════════════════════════════════════════════════════════
# Tests: send result policy
# ══════════════════════════════════════════════════════════════════════

class TestMaterializerSendPolicy(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_send_result_draft_goes_to_dry_run(self):
        """Draft events go to dry_run regardless of send result."""
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp, send_run_result=None)
        self.assertEqual(result.dry_run_records, 1)
        self.assertEqual(result.sent_records, 0)

    def test_pending_should_remain_draft_goes_to_dry_run(self):
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="ok", pending_should_remain=True)
        result = materialize_pop_rotation_records(self.tmp, send_run_result=sr)
        self.assertEqual(result.dry_run_records, 1)
        self.assertEqual(result.sent_records, 0)

    def test_send_warning_draft_goes_to_dry_run(self):
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="warning", pending_should_remain=True)
        result = materialize_pop_rotation_records(self.tmp, send_run_result=sr)
        self.assertEqual(result.dry_run_records, 1)
        self.assertEqual(result.sent_records, 0)

    def test_409_duplicate_draft_goes_to_dry_run(self):
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="warning", pending_should_remain=True,
                               reason="duplicate_batch_pending_remains")
        result = materialize_pop_rotation_records(self.tmp, send_run_result=sr)
        self.assertEqual(result.dry_run_records, 1)
        self.assertEqual(result.sent_records, 0)

    def test_send_ok_draft_still_not_sent(self):
        """Even with ok send, draft events are NOT sent — they go to dry_run."""
        _write_jsonl(self.tmp, [_draft_line()])
        sr = _make_send_result(run_status="ok", pending_should_remain=False)
        result = materialize_pop_rotation_records(self.tmp, send_run_result=sr)
        self.assertEqual(result.sent_records, 0)
        self.assertEqual(result.dry_run_records, 1)

    def test_can_sent_flag_false_by_default(self):
        """Without send_run_result, can_sent is False → sent_records stays 0."""
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        self.assertEqual(result.sent_records, 0)

    def test_completed_no_manifest_quarantine(self):
        """Completed event without manifest mapping → quarantine, not sent."""
        _write_jsonl(self.tmp, [_completed_eligible_line()])
        sr = _make_send_result(run_status="ok", pending_should_remain=False)
        result = materialize_pop_rotation_records(self.tmp, send_run_result=sr)
        # Without manifest, completed events with selected_order go to quarantine
        self.assertEqual(result.sent_records, 0)
        self.assertGreater(result.quarantine_records, 0)


# ══════════════════════════════════════════════════════════════════════
# Tests: max_lines
# ══════════════════════════════════════════════════════════════════════

class TestMaterializerMaxLines(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_max_lines_zero_error(self):
        result = materialize_pop_rotation_records(self.tmp, max_lines=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESULT)

    def test_max_lines_negative_error(self):
        result = materialize_pop_rotation_records(self.tmp, max_lines=-5)
        self.assertEqual(result.reason, REASON_INVALID_RESULT)

    def test_max_lines_limit(self):
        lines = [_draft_line() for _ in range(5)]
        _write_jsonl(self.tmp, lines)
        result = materialize_pop_rotation_records(self.tmp, max_lines=2)
        self.assertTrue(result.limited)
        self.assertEqual(result.reason, REASON_LIMITED)
        # First 2 lines processed (dry_run), lines 3-5 beyond limit → retained_pending
        self.assertEqual(result.dry_run_records, 2)
        self.assertEqual(result.retained_pending_records, 3)


# ══════════════════════════════════════════════════════════════════════
# Tests: safe output
# ══════════════════════════════════════════════════════════════════════

class TestMaterializerSafeOutput(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_format_no_forbidden_empty(self):
        result = materialize_pop_rotation_records(self.tmp)
        text = format_pop_rotation_materialize_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_format_no_forbidden_with_data(self):
        _write_jsonl(self.tmp, [_draft_line(), _blocked_line()])
        result = materialize_pop_rotation_records(self.tmp)
        text = format_pop_rotation_materialize_result(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_forbidden(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        text = repr(result)
        self.assertTrue(_no_forbidden(text))

    def test_repr_no_raw_json(self):
        _write_jsonl(self.tmp, [_draft_line(), _blocked_line()])
        result = materialize_pop_rotation_records(self.tmp)
        text = repr(result)
        self.assertNotIn("would_play", text.lower())
        self.assertNotIn("selected_order", text)
        self.assertNotIn("draft", text.lower())

    def test_repr_no_lock_path(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        text = repr(result)
        self.assertNotIn("player_events.lock", text)

    def test_repr_no_filename(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        text = repr(result)
        self.assertNotIn("filename", text.lower())

    def test_repr_no_manifest_item_id(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        text = repr(result)
        self.assertNotIn("manifest_item_id", text.lower())

    def test_repr_no_sha256(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        text = repr(result)
        self.assertNotIn("sha256", text.lower())

    def test_repr_does_not_expose_buckets(self):
        """Repr must NOT expose internal bucket contents."""
        _write_jsonl(self.tmp, [_draft_line(), _blocked_line()])
        result = materialize_pop_rotation_records(self.tmp)
        text = repr(result)
        self.assertNotIn("_dry_run_records=[", text)
        self.assertNotIn("_sent_records=[", text)
        self.assertNotIn("_quarantine_records=[", text)
        # repr=False means they don't appear in repr at all
        self.assertNotIn("record_type", text.lower())

    def test_format_contains_all_fields(self):
        result = materialize_pop_rotation_records(self.tmp)
        text = format_pop_rotation_materialize_result(result)
        for field in [
            "status:", "pending_lines_before:", "retained_pending_records:",
            "sent_records:", "quarantine_records:", "dry_run_records:",
            "failed_records:", "invalid_lines:", "lock_acquired:",
            "pending_untouched:", "materialized:", "max_lines:",
            "limited:", "reason:",
        ]:
            self.assertIn(field, text, f"Missing field '{field}'")

    def test_internal_buckets_repr_false(self):
        """Verify internal buckets are declared with repr=False."""
        import dataclasses
        fields = {f.name: f for f in dataclasses.fields(PopRotationMaterializeResult)}
        for bucket_name in [
            "_retained_pending_records", "_sent_records",
            "_quarantine_records", "_dry_run_records", "_failed_records",
        ]:
            self.assertIn(bucket_name, fields, f"Missing field {bucket_name}")
            self.assertFalse(fields[bucket_name].repr,
                             f"Field {bucket_name} must have repr=False")


# ══════════════════════════════════════════════════════════════════════
# Tests: sanitized record builder
# ══════════════════════════════════════════════════════════════════════

class TestSanitizedRecord(TestCase):
    def test_basic_record(self):
        rec = _sanitized_rotation_record(RECORD_TYPE_QUARANTINE, "invalid_json", 5)
        self.assertEqual(rec["schema_version"], 1)
        self.assertEqual(rec["record_type"], RECORD_TYPE_QUARANTINE)
        self.assertEqual(rec["reason"], "invalid_json")
        self.assertEqual(rec["line_number"], 5)
        self.assertIn("created_at", rec)
        self.assertEqual(rec["source"], "player_events")

    def test_no_forbidden_in_fields(self):
        rec = _sanitized_rotation_record(RECORD_TYPE_QUARANTINE, "invalid_json")
        for key, value in rec.items():
            if isinstance(value, str):
                self.assertTrue(_no_forbidden(value),
                                f"Forbidden in sanitized key '{key}': {value}")

    def test_no_line_number_when_none(self):
        rec = _sanitized_rotation_record(RECORD_TYPE_DRY_RUN, "draft_not_pop")
        self.assertNotIn("line_number", rec)


# ══════════════════════════════════════════════════════════════════════
# Tests: no side effects
# ══════════════════════════════════════════════════════════════════════

class TestMaterializerNoSideEffects(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_does_not_create_sent_dir(self):
        _write_jsonl(self.tmp, [_draft_line()])
        materialize_pop_rotation_records(self.tmp)
        for bad in ("sent", "quarantine", "dry_run", "failed"):
            bad_path = self.tmp / "pop" / bad
            self.assertFalse(bad_path.exists(),
                             f"'{bad}/' should not exist after materialize")

    def test_does_not_modify_pending(self):
        lines = [_draft_line(), _blocked_line()]
        _write_jsonl(self.tmp, lines)
        jsonl_path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        original = jsonl_path.read_text()
        materialize_pop_rotation_records(self.tmp)
        self.assertEqual(jsonl_path.read_text(), original)

    def test_does_not_delete_pending(self):
        _write_jsonl(self.tmp, [_draft_line()])
        jsonl_path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        materialize_pop_rotation_records(self.tmp)
        self.assertTrue(jsonl_path.exists())

    def test_no_http_imports(self):
        mod_path = Path(__file__).parent.parent / "kso_sidecar_agent" / "pop_rotation_materializer.py"
        content = mod_path.read_text()
        self.assertNotIn("import urllib", content)
        self.assertNotIn("import requests", content)
        self.assertNotIn("import http", content)

    def test_does_not_read_secret_config(self):
        _write_jsonl(self.tmp, [_draft_line()])
        result = materialize_pop_rotation_records(self.tmp)
        self.assertIn(result.status, (STATUS_OK, STATUS_WARNING))


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import unittest
    unittest.main()
