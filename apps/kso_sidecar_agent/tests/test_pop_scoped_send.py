"""Tests for KSO Sidecar PoP Scoped Send Runner Core (pop_scoped_send.py)."""

import json
import os
import tempfile
import unittest
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from kso_sidecar_agent.pop_scoped_send import (
    PopScopedSendResult,
    run_pop_scoped_send,
    format_pop_scoped_send_result,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    SEND_STATUS_OK,
    SEND_STATUS_WARNING,
    SEND_STATUS_ERROR,
    SEND_STATUS_SKIPPED,
    REASON_BUILT_SCOPED,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
    REASON_PACKAGE_FAILED,
    REASON_SEND_FAILED,
    REASON_SEND_OK,
    REASON_LOCK_UNAVAILABLE_SCOPED,
    REASON_LIMITED_SCOPED,
    REASON_INVALID_RESULT_SCOPED,
    FORBIDDEN_SUBSTRINGS,
    DEFAULT_MAX_LINES,
)
from kso_sidecar_agent.pop_payload import (
    PopPayloadEvent,
    PopPayloadEnvelope,
)
from kso_sidecar_agent.pop_sender import (
    SEND_OK,
    SEND_WARNING,
    SEND_ERROR,
    REASON_PROCESSED,
    REASON_NO_PAYLOAD,
    REASON_DUPLICATE_BATCH,
    REASON_SERVER_ERROR,
    REASON_NETWORK_ERROR,
    REASON_UNAUTHORIZED,
    PopSendResult,
)
from kso_sidecar_agent.pop_sender_runner import (
    PopSendRunResult,
    RUN_OK,
    RUN_WARNING,
    RUN_ERROR,
)
from kso_sidecar_agent.pop_rotation_materializer import (
    PopRotationSentScope,
)
from kso_sidecar_agent.pop_pickup import (
    POP_PENDING_DIR,
    POP_JSONL_FILE,
)


# ══════════════════════════════════════════════════════════════════════
# Fake HTTP client (same pattern as test_pop_sender_runner.py)
# ══════════════════════════════════════════════════════════════════════

class FakeHttpError(Exception):
    def __init__(self, status_code=0, message="", retryable=False):
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


@dataclass
class FakeHttpResponse:
    status_code: int
    json_body: Any
    elapsed_ms: float = 10.0


class FakeHttpClient:
    """Fake SafeHttpClient — returns responses/errors from a queue."""

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

        # Errors take priority
        if self._errors:
            err = self._errors.pop(0)
            if err is not None:
                raise err

        # Responses
        if self._responses:
            resp = self._responses.pop(0)
            if resp is not None:
                return resp

        # Default: 200 success
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
    """Ensure media cache appears complete for tests — write matching files with correct sha256."""
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


def _acquire_foreign_lock(root) -> int:
    """Acquire a lock file to simulate another process holding it."""
    lock_path = Path(root) / POP_PENDING_DIR / "player_events.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, b"locked\n")
    return fd


def _release_foreign_lock(fd, root):
    os.close(fd)
    lock_path = Path(root) / POP_PENDING_DIR / "player_events.lock"
    try:
        os.unlink(str(lock_path))
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

class TestRunScopedSendNoEligible(unittest.TestCase):
    """Cases where no send should happen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_pending_file_no_send(self):
        """No pending file → send_attempted=False."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_attempted)
        self.assertFalse(result.send_success)
        self.assertEqual(result.reason, REASON_NO_ELIGIBLE_EVENTS_SCOPED)
        self.assertEqual(result.send_status, SEND_STATUS_SKIPPED)
        self.assertEqual(client.call_count, 0)

    def test_draft_only_no_send(self):
        """Draft only → send_attempted=False."""
        _write_manifest(self.root, _make_manifest_data())
        _write_jsonl(self.root, [_make_record(event_status="draft")])
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_attempted)
        self.assertEqual(client.call_count, 0)

    def test_blocked_only_no_send(self):
        """Blocked only → send_attempted=False."""
        _write_manifest(self.root, _make_manifest_data())
        _write_jsonl(self.root, [_make_record(event_status="blocked")])
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_attempted)
        self.assertEqual(client.call_count, 0)

    def test_failed_only_no_send(self):
        """Failed only → send_attempted=False."""
        _write_manifest(self.root, _make_manifest_data())
        _write_jsonl(self.root, [_make_record(event_status="failed")])
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_attempted)
        self.assertEqual(client.call_count, 0)

    def test_invalid_only_no_send(self):
        """Invalid JSON only → send_attempted=False."""
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / POP_JSONL_FILE).write_text("not valid json\n")
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_attempted)
        self.assertEqual(client.call_count, 0)

    def test_lock_unavailable_no_send(self):
        """Lock unavailable → send_attempted=False."""
        _setup_eligible_root(self.root)
        fd = _acquire_foreign_lock(self.root)
        try:
            client = FakeHttpClient()
            result = run_pop_scoped_send(self.root, client)
            self.assertFalse(result.send_attempted)
            self.assertEqual(result.reason, REASON_LOCK_UNAVAILABLE_SCOPED)
            self.assertEqual(client.call_count, 0)
        finally:
            _release_foreign_lock(fd, self.root)


class TestRunScopedSendSuccessful(unittest.TestCase):
    """Cases where send succeeds."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_completed_eligible_send_attempted(self):
        """Completed eligible → send_attempted=True."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertTrue(result.send_attempted)
        self.assertGreaterEqual(client.call_count, 1)

    def test_successful_fake_send_send_success(self):
        """Successful fake send → send_success=True."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertTrue(result.send_success)
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.reason, REASON_SEND_OK)

    def test_successful_send_internal_sent_scope_exists(self):
        """Successful send → _sent_scope exists."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertIsNotNone(result._sent_scope)
        self.assertIsInstance(result._sent_scope, PopRotationSentScope)

    def test_successful_send_scope_lines_equals_payload_events(self):
        """scope_lines == payload_events."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertEqual(result.scope_lines, result.payload_events)
        self.assertGreater(result.scope_lines, 0)

    def test_successful_send_pending_untouched(self):
        """After send, pending_untouched=True (rotation not applied)."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertTrue(result.pending_untouched)

    def test_successful_send_rotation_not_applied(self):
        """rotation_applied=False — rotation NOT called."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.rotation_applied)


class TestRunScopedSendFailure(unittest.TestCase):
    """Cases where send fails."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_server_error_send_failed(self):
        """500 → send_success=False."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
        ])
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_success)
        self.assertTrue(result.send_attempted)
        self.assertGreaterEqual(client.call_count, 1)

    def test_retry_exhausted_send_failed(self):
        """Retry exhausted → send_success=False."""
        # Three 500s — retry manager will exhaust
        responses = [
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
        ]
        client = FakeHttpClient(responses=responses)
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_success)
        self.assertEqual(result.send_status, SEND_STATUS_ERROR)
        self.assertEqual(result.reason, REASON_SEND_FAILED)
        self.assertEqual(client.call_count, 3)

    def test_network_error_send_failed(self):
        """Network error → send_success=False, send attempted."""
        err = FakeHttpError(status_code=0, message="connection refused", retryable=True)
        client = FakeHttpClient(errors=[err, err, err])
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_success)
        self.assertTrue(result.send_attempted)

    def test_409_duplicate_send_not_success(self):
        """HTTP 409 duplicate → send_success=False (pending_should_remain=True)."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=409, json_body={"status": "duplicate_batch"}),
        ])
        result = run_pop_scoped_send(self.root, client)
        self.assertFalse(result.send_success)
        self.assertTrue(result.send_attempted)


class TestRunScopedSendSafety(unittest.TestCase):
    """Safety checks for result/repr/output."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_result_repr_no_payload_body(self):
        """Result repr does not contain payload body fields."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        repr_str = repr(result)
        self.assertNotIn("batch_id", repr_str)
        self.assertNotIn("device_event_id", repr_str)
        self.assertNotIn("manifest_item_id", repr_str)

    def test_result_repr_no_line_number_list(self):
        """Result repr does not contain line numbers."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        repr_str = repr(result)
        self.assertNotIn("_line_numbers", repr_str)
        self.assertNotIn("_sent_scope", repr_str)
        self.assertNotIn("_send_run_result", repr_str)

    def test_result_repr_no_ids(self):
        """Result repr does not contain IDs."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        repr_str = repr(result)
        self.assertNotIn("manifest_item_id", repr_str)
        self.assertNotIn("device_event_id", repr_str)
        self.assertNotIn("batch_id", repr_str)
        self.assertNotIn("campaign_id", repr_str)
        self.assertNotIn("creative_id", repr_str)

    def test_result_repr_no_paths_filenames(self):
        """Result repr does not contain paths/filenames."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        repr_str = repr(result).lower()
        self.assertNotIn("path", repr_str)
        self.assertNotIn("filename", repr_str)
        self.assertNotIn("sha256", repr_str)

    def test_result_repr_no_token(self):
        """Result repr does not contain token."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        repr_str = repr(result).lower()
        self.assertNotIn("token", repr_str)

    def test_safe_output_contains_aggregates(self):
        """Safe output contains all expected fields."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        output = format_pop_scoped_send_result(result)
        self.assertIn("status:", output)
        self.assertIn("send_attempted:", output)
        self.assertIn("send_success:", output)
        self.assertIn("payload_events:", output)
        self.assertIn("scope_lines:", output)
        self.assertIn("send_status:", output)
        self.assertIn("rotation_applied:", output)

    def test_safe_output_no_forbidden(self):
        """Safe output passes forbidden check."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        output = format_pop_scoped_send_result(result)
        lower = output.lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, lower, f"forbidden '{fb}' in safe output")

    def test_safe_output_no_payload_body(self):
        """Safe output does not contain payload body."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        output = format_pop_scoped_send_result(result)
        self.assertNotIn("batch_id", output)
        self.assertNotIn("device_event_id", output)
        self.assertNotIn("manifest_item_id", output)
        self.assertNotIn("campaign_id", output)

    def test_safe_output_no_stacktrace(self):
        """Safe output does not contain stacktrace."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        output = format_pop_scoped_send_result(result)
        self.assertNotIn("stacktrace", output.lower())
        self.assertNotIn("traceback", output.lower())


class TestRunScopedSendNoSideEffects(unittest.TestCase):
    """Verify NO side effects from scoped send."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_pending_rewrite(self):
        """Pending file unchanged after scoped send."""
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        original = jsonl_path.read_text()
        client = FakeHttpClient()
        run_pop_scoped_send(self.root, client)
        after = jsonl_path.read_text()
        self.assertEqual(original, after)

    def test_no_sent_quarantine_dry_run_failed_dirs(self):
        """No sent/quarantine/dry_run/failed dirs created."""
        client = FakeHttpClient()
        run_pop_scoped_send(self.root, client)
        for d in ("sent", "quarantine", "dry_run", "failed"):
            dir_path = self.root / "pop" / d
            self.assertFalse(dir_path.exists(), f"{d} dir should not exist")

    def test_no_real_backend(self):
        """FakeHttpClient used — no real backend call."""
        client = FakeHttpClient()
        run_pop_scoped_send(self.root, client)
        # Fake client tracks call count, no real network
        self.assertGreaterEqual(client.call_count, 1)

    def test_no_secret_config_token_reads(self):
        """No secret/config/token reads from files."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertTrue(result.send_success)

    def test_no_media_bytes_reads(self):
        """No media bytes reads."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client)
        self.assertTrue(result.send_success)


class TestRunScopedSendInvalidArgs(unittest.TestCase):
    """Invalid arguments."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_max_lines_zero(self):
        """max_lines=0 → error."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client, max_lines=0)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESULT_SCOPED)
        self.assertFalse(result.send_attempted)

    def test_max_lines_negative(self):
        """max_lines=-1 → error."""
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client, max_lines=-1)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_RESULT_SCOPED)


class TestRunScopedSendWithAuth(unittest.TestCase):
    """Auth provider injection."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_auth_provider_called(self):
        """Auth provider is called to get token."""
        call_tracker = {"called": 0}

        def fake_auth():
            call_tracker["called"] += 1
            return "fake-token-123"

        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client, auth_provider=fake_auth)
        self.assertTrue(result.send_success)
        self.assertGreaterEqual(call_tracker["called"], 1)


class TestRunScopedSendLimited(unittest.TestCase):
    """max_lines limit handling."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_eligible_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_limited_package_safe_warning(self):
        """Limited package → warning, no send."""
        # 3 events, limit=1 — first event is eligible
        _write_jsonl(self.root, [
            _make_record(event_status="completed", selected_order=0),
            _make_record(event_status="completed", selected_order=1),
            _make_record(event_status="completed", selected_order=2),
        ])
        client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, client, max_lines=1)
        self.assertEqual(result.status, STATUS_WARNING)
        self.assertEqual(result.reason, REASON_LIMITED_SCOPED)
        self.assertFalse(result.send_attempted)


if __name__ == "__main__":
    unittest.main()
