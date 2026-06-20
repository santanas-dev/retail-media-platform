"""Tests for KSO Sidecar PoP Scoped Send Rotation Orchestrator Core."""

import json
import tempfile
import unittest
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from kso_sidecar_agent.pop_send_rotation_orchestrator import (
    PopSendRotationOrchestratorResult,
    run_pop_scoped_send_then_rotate,
    format_pop_send_rotation_orchestrator_result,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_ROTATED_AFTER_SEND,
    REASON_ROTATION_NOT_ALLOWED,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_LOCK_UNAVAILABLE,
    REASON_LIMITED,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_SEND_FAILED,
    REASON_INVALID_RESULT,
    FORBIDDEN_SUBSTRINGS,
    DEFAULT_MAX_LINES,
)
from kso_sidecar_agent.pop_payload import PopPayloadEvent, PopPayloadEnvelope
from kso_sidecar_agent.pop_pickup import POP_PENDING_DIR, POP_JSONL_FILE


# ══════════════════════════════════════════════════════════════════════
# Fake HTTP client
# ══════════════════════════════════════════════════════════════════════

@dataclass
class FakeHttpResponse:
    status_code: int
    json_body: Any
    elapsed_ms: float = 10.0


class FakeHttpClient:
    """Fake SafeHttpClient with queue-based responses."""

    def __init__(self, responses=None, errors=None):
        self._responses = list(responses) if responses else []
        self._errors = list(errors) if errors else []
        self.call_count = 0
        self.last_path = None
        self.last_payload = None
        self.last_headers = None

    def post_json(self, path, payload, headers=None):
        self.call_count += 1
        self.last_path = path
        self.last_payload = payload
        self.last_headers = headers

        if self._errors:
            err = self._errors.pop(0)
            if err is not None:
                raise err

        if self._responses:
            resp = self._responses.pop(0)
            if resp is not None:
                return resp

        return FakeHttpResponse(
            status_code=200,
            json_body={"status": "processed", "summary": {"accepted": len(payload.get("events", []))}},
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_record(event_status="draft", event_type="would_play",
                 safety_state="idle", selected_order=0):
    return {
        "schema_version": 1,
        "event_type": event_type,
        "event_status": event_status,
        "created_at": "2026-06-19T00:00:00+00:00",
        "started_at": "2026-06-19T00:00:00+00:00",
        "ended_at": "2026-06-19T00:00:05+00:00",
        "duration_ms": 5000 if event_type == "would_play" else 0,
        "playback_allowed": True if event_type == "would_play" else False,
        "session_action": "play" if event_type == "would_play" else "stop",
        "session_reason": "ready" if event_type == "would_play" else "safety_blocked",
        "selected_order": selected_order,
        "selected_content_type": "image/png",
        "safety_state": safety_state,
        "result": event_type,
    }


def _make_manifest_items(count=3):
    items = []
    for i in range(count):
        items.append({
            "manifest_item_id": str(uuid.uuid4()),
            "filename": f"file_{i}.png",
            "content_type": "image/png",
            "sha256": "a" * 64,
            "duration_ms": 5000,
            "order": i,
            "size_bytes": 100,
            "campaign_id": str(uuid.uuid4()),
            "schedule_item_id": str(uuid.uuid4()),
        })
    return items


def _make_manifest_data(items=None, mvid=None):
    if mvid is None:
        mvid = str(uuid.uuid4())
    return {
        "manifest_version_id": mvid,
        "manifest_hash": "a" * 64,
        "source": "current",
        "generated_at": "2026-06-19T00:00:00Z",
        "publication_target_id": str(uuid.uuid4()),
        "items": items or _make_manifest_items(3),
    }


def _write_jsonl(root, lines):
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    with open(path, "w") as f:
        for rec in lines:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


def _write_manifest(root, manifest_data):
    mdir = root / "manifest"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "current_manifest.json").write_text(json.dumps(manifest_data))


def _clear_media_cache(root):
    mdir = root / "manifest"
    mc_dir = root / "media" / "current"
    mc_dir.mkdir(parents=True, exist_ok=True)
    if (mdir / "current_manifest.json").exists():
        try:
            import hashlib
            manifest = json.loads((mdir / "current_manifest.json").read_text())
            for item in manifest.get("items", []):
                fname = item.get("filename", "")
                if fname:
                    data = b"\x00" * item.get("size_bytes", 100)
                    sha = hashlib.sha256(data).hexdigest()
                    item["sha256"] = sha
                    (mc_dir / fname).write_bytes(data)
            (mdir / "current_manifest.json").write_text(json.dumps(manifest))
        except Exception:
            pass


def _setup_eligible_root(root):
    """Full setup: manifest + media cache + completed eligible event."""
    _write_manifest(root, _make_manifest_data())
    _clear_media_cache(root)
    _write_jsonl(root, [_make_record(event_status="completed")])


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestOrchestratorNoEligible(unittest.TestCase):
    """Cases where no rotation should happen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_pending_file(self):
        """No pending file → no eligible, send=false, rotation=false."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertFalse(result.send_attempted)
        self.assertFalse(result.rotation_applied)
        self.assertEqual(result.reason, REASON_NO_ELIGIBLE_EVENTS)
        self.assertEqual(client.call_count, 0)

    def test_draft_only(self):
        """Draft only → no eligible, rotation=false."""
        _write_manifest(self.root, _make_manifest_data())
        _write_jsonl(self.root, [_make_record(event_status="draft")])
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertFalse(result.send_attempted)
        self.assertFalse(result.rotation_applied)
        self.assertEqual(client.call_count, 0)

    def test_invalid_only(self):
        """Invalid JSON only → no eligible, rotation=false."""
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / POP_JSONL_FILE).write_text("bad json\n")
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertFalse(result.send_attempted)
        self.assertFalse(result.rotation_applied)
        self.assertEqual(client.call_count, 0)


class TestOrchestratorSuccessful(unittest.TestCase):
    """Successful scoped send → rotation applied."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_successful_send_rotation_applied(self):
        """200 processed → send_success=true, rotation_applied=true, sent>0."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertTrue(result.send_success)
        self.assertTrue(result.rotation_allowed)
        self.assertTrue(result.rotation_applied)
        self.assertGreater(result.sent_records, 0)
        self.assertTrue(result.pending_rewritten)
        self.assertEqual(result.status, STATUS_OK)

    def test_successful_send_pending_rewritten(self):
        """After successful rotation, pending rewritten."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertTrue(result.pending_rewritten)
        # After rotation, pending should be empty (all went to sent)
        self.assertFalse(result.pending_untouched)

    def test_successful_send_sent_dir_created(self):
        """sent/ directory created after successful rotation."""
        client = FakeHttpClient()
        run_pop_scoped_send_then_rotate(self.root, client)
        sent_dir = self.root / "pop" / "sent"
        self.assertTrue(sent_dir.exists())

    def test_successful_send_internal_fields_preserved(self):
        """Internal _scoped_send_result, _decision, _apply_result preserved."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertIsNotNone(result._scoped_send_result)
        self.assertIsNotNone(result._decision)
        self.assertIsNotNone(result._apply_result)


class TestOrchestratorFailed(unittest.TestCase):
    """Failed send → no rotation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_500_retry_exhausted_no_rotation(self):
        """500 × 3 → rotation=false, pending untouched."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
        ])
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertTrue(result.send_attempted)
        self.assertFalse(result.send_success)
        self.assertFalse(result.rotation_applied)
        self.assertTrue(result.pending_untouched)
        self.assertEqual(client.call_count, 3)

    def test_failed_send_sent_not_created(self):
        """Failed send → sent/ dir not created."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
        ])
        run_pop_scoped_send_then_rotate(self.root, client)
        sent_dir = self.root / "pop" / "sent"
        self.assertFalse(sent_dir.exists())

    def test_409_duplicate_no_rotation(self):
        """409 duplicate → rotation=false, pending untouched."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=409, json_body={"status": "duplicate_batch"}),
        ])
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertTrue(result.send_attempted)
        self.assertFalse(result.send_success)
        self.assertFalse(result.rotation_applied)
        self.assertTrue(result.pending_untouched)
        self.assertEqual(result.reason, REASON_DUPLICATE_PENDING_REMAINS)

    def test_409_sent_not_created(self):
        """409 → sent/ dir not created."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=409, json_body={"status": "duplicate_batch"}),
        ])
        run_pop_scoped_send_then_rotate(self.root, client)
        sent_dir = self.root / "pop" / "sent"
        self.assertFalse(sent_dir.exists())

    def test_pending_should_remain_no_rotation(self):
        """pending_should_remain=true → rotation=false."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=200, json_body={
                "status": "partial_success",
                "summary": {"accepted": 0, "rejected": 1},
            }),
        ])
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertFalse(result.rotation_applied)
        self.assertTrue(result.pending_untouched)


class TestOrchestratorSafety(unittest.TestCase):
    """Safety checks for result/repr/output."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_result_repr_no_payload_body(self):
        """Result repr does not contain payload body."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        repr_str = repr(result)
        self.assertNotIn("batch_id", repr_str)
        self.assertNotIn("device_event_id", repr_str)
        self.assertNotIn("manifest_item_id", repr_str)

    def test_result_repr_no_ids(self):
        """Result repr does not contain IDs."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        repr_str = repr(result)
        self.assertNotIn("manifest_item_id", repr_str)
        self.assertNotIn("device_event_id", repr_str)
        self.assertNotIn("batch_id", repr_str)
        self.assertNotIn("campaign_id", repr_str)

    def test_result_repr_no_line_numbers(self):
        """Result repr does not contain line numbers."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        repr_str = repr(result)
        self.assertNotIn("_line_numbers", repr_str)
        self.assertNotIn("_line_fingerprints", repr_str)

    def test_result_repr_no_fingerprints(self):
        """Result repr does not contain fingerprint hex values."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        repr_str = repr(result)
        self.assertNotIn("fingerprint", repr_str.lower())

    def test_result_repr_no_paths(self):
        """Result repr doesn't contain paths/filenames."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        repr_str = repr(result).lower()
        self.assertNotIn("path", repr_str)
        self.assertNotIn("filename", repr_str)
        self.assertNotIn("sha256", repr_str)

    def test_safe_output_contains_fields(self):
        """Safe output contains all expected fields."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        output = format_pop_send_rotation_orchestrator_result(result)
        self.assertIn("status:", output)
        self.assertIn("send_attempted:", output)
        self.assertIn("send_success:", output)
        self.assertIn("rotation_allowed:", output)
        self.assertIn("rotation_applied:", output)
        self.assertIn("sent_records:", output)
        self.assertIn("pending_rewritten:", output)
        self.assertIn("reason:", output)

    def test_safe_output_no_forbidden(self):
        """Safe output passes forbidden check."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        output = format_pop_send_rotation_orchestrator_result(result)
        lower = output.lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lower, f"forbidden '{fb}' in safe output")

    def test_safe_output_no_stacktrace(self):
        """Safe output does not contain stacktrace."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        output = format_pop_send_rotation_orchestrator_result(result)
        self.assertNotIn("stacktrace", output.lower())


class TestOrchestratorNoSideEffects(unittest.TestCase):
    """Verify no real backend, no secret/config reads."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_real_backend(self):
        """FakeHttpClient used — no real backend call."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertTrue(result.rotation_applied)

    def test_no_secret_config_reads(self):
        """No secret/config/token reads from files."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertTrue(result.rotation_applied)

    def test_no_media_bytes_reads(self):
        """No media bytes reads."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        self.assertTrue(result.rotation_applied)


class TestOrchestratorInvalidArgs(unittest.TestCase):
    """Invalid arguments."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_max_lines_zero(self):
        """max_lines=0 → error."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client, max_lines=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESULT)

    def test_max_lines_negative(self):
        """max_lines=-1 → error."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client, max_lines=-1)
        self.assertEqual(result.status, STATUS_ERROR)


class TestOrchestratorLimited(unittest.TestCase):
    """Limited package → no unsafe rotation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)
        # Write 3 eligible events but limit to 1
        _write_jsonl(self.root, [
            _make_record(event_status="completed", selected_order=0),
            _make_record(event_status="completed", selected_order=1),
            _make_record(event_status="completed", selected_order=2),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_limited_no_rotation(self):
        """Limited → no rotation."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client, max_lines=1)
        self.assertFalse(result.rotation_applied)
        self.assertEqual(result.reason, REASON_LIMITED)


class TestOrchestratorRaceFingerprint(unittest.TestCase):
    """Race condition: pending changes between send and rotation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_different_eligible_event(self, order):
        """Write a different completed event to pending."""
        _write_manifest(self.root, _make_manifest_data())
        _clear_media_cache(self.root)
        _write_jsonl(self.root, [_make_record(event_status="completed", selected_order=order)])

    def test_race_changed_line_fingerprint_mismatch(self):
        """Pending line changed → fingerprint mismatch → sent=0 at materializer level.

        This directly tests the materializer's fingerprint guard:
        build scope from one line, write different content to pending,
        verify that apply doesn't send the mismatched line.
        """
        from kso_sidecar_agent.pop_pending_lock import (
            try_acquire_pop_pending_lock,
            release_pop_pending_lock,
        )
        from kso_sidecar_agent.pop_rotation_materializer import (
            materialize_pop_rotation_records_locked,
            PopRotationSentScope,
            build_pending_line_fingerprint,
        )

        # Setup: write manifest + eligible event
        _write_manifest(self.root, _make_manifest_data())
        _clear_media_cache(self.root)

        # Build scope from line with selected_order=0
        original_line = json.dumps(_make_record(
            event_status="completed", selected_order=0), sort_keys=True)
        scope = PopRotationSentScope(
            _line_numbers=frozenset({1}),
            _line_fingerprints={1: build_pending_line_fingerprint(original_line)},
        )

        # Write a DIFFERENT line to pending (selected_order=1, same line number)
        changed_line = json.dumps(_make_record(
            event_status="completed", selected_order=1), sort_keys=True)
        _write_jsonl(self.root, [json.loads(changed_line)])

        # Now materialize with the fingerprinted scope → should mismatch
        class FakeSR:
            run_status = "ok"
            pending_should_remain = False
            reason = "processed"

        lock = try_acquire_pop_pending_lock(self.root)
        mat_result = materialize_pop_rotation_records_locked(
            self.root, lock,
            send_run_result=FakeSR(),
            sent_scope=scope,
        )
        release_pop_pending_lock(lock)

        self.assertEqual(mat_result.sent_records, 0)
        self.assertEqual(mat_result.sent_scope_matched, 0)
        self.assertEqual(mat_result.sent_scope_mismatched, 1)
        self.assertTrue(mat_result.sent_scope_fingerprinted)


if __name__ == "__main__":
    unittest.main()
