"""KSO PoP Fake End-to-End Pipeline Tests.

Full chain tests using ONLY local temp directories and FakeHttpClient:
  player-like event → pending/player_events.jsonl
  → scoped send package → fake backend send → decision → local rotation
  → sent/quarantine/dry_run/pending result

NO real backend, NO real config/token/secret reads, NO media bytes reads.
"""

import json
import tempfile
import unittest
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kso_sidecar_agent.pop_send_rotation_orchestrator import (
    run_pop_scoped_send_then_rotate,
    format_pop_send_rotation_orchestrator_result,
    PopSendRotationOrchestratorResult,
    REASON_ROTATED_AFTER_SEND,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_SEND_FAILED,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_PENDING_SHOULD_REMAIN,
    FORBIDDEN_SUBSTRINGS,
    STATUS_OK,
    STATUS_WARNING,
)
from kso_sidecar_agent.pop_pickup import POP_PENDING_DIR, POP_JSONL_FILE


# ══════════════════════════════════════════════════════════════════════
# Fake HTTP
# ══════════════════════════════════════════════════════════════════════

@dataclass
class FakeHttpResponse:
    status_code: int
    json_body: Any
    elapsed_ms: float = 10.0


class FakeHttpClient:
    """Fake SafeHttpClient with queue-based responses."""

    def __init__(self, responses=None):
        self._responses = list(responses) if responses else []
        self.call_count = 0

    def post_json(self, path, payload, headers=None):
        self.call_count += 1
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

def _make_player_event(event_status="draft", event_type="would_play",
                       safety_state="idle", selected_order=0):
    """Build a player-format event record (matches player pop_writer format)."""
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


def _write_player_event_to_pending(root, event):
    """Simulate player writing a JSONL event to pop/pending/player_events.jsonl."""
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    with open(path, "a") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def _write_manifest(root, manifest_data):
    mdir = root / "manifest"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "current_manifest.json").write_text(json.dumps(manifest_data))


def _setup_media_cache(root):
    """Write media files matching manifest so media cache is complete."""
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


def _setup_full_env(root):
    """Full environment: manifest + media cache."""
    _write_manifest(root, _make_manifest_data())
    _setup_media_cache(root)


def _assert_no_forbidden(text, label=""):
    """Assert text does not contain any forbidden substrings."""
    lower = text.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise AssertionError(f"{label}: forbidden substring '{fb}' in output")


def _assert_no_sent_dirs(root):
    """Assert no sent/quarantine/dry_run/failed dirs exist."""
    for d in ("sent", "quarantine", "dry_run", "failed"):
        assert not (Path(root) / "pop" / d).exists(), f"{d} dir should not exist"


# ══════════════════════════════════════════════════════════════════════
# E2E Tests
# ══════════════════════════════════════════════════════════════════════

class TestE2ECompletedToSent(unittest.TestCase):
    """Scenario 1: completed eligible event → fake 200 → sent/."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_full_env(self.root)
        # Player writes completed event
        _write_player_event_to_pending(self.root, _make_player_event(
            event_status="completed", event_type="would_play",
            safety_state="idle", selected_order=0))

    def tearDown(self):
        self.tmp.cleanup()

    def test_completed_event_goes_to_sent(self):
        """Full chain: player event → package → send → decision → rotation → sent."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)

        # Phase 1: send
        self.assertTrue(result.send_attempted, "Send should be attempted")
        self.assertTrue(result.send_success, "Send should succeed")
        self.assertGreaterEqual(client.call_count, 1, "HTTP client should be called")

        # Phase 2: decision
        self.assertTrue(result.rotation_allowed, "Rotation should be allowed")

        # Phase 3: rotation
        self.assertTrue(result.rotation_applied, "Rotation should be applied")
        self.assertEqual(result.sent_records, 1, "One event should go to sent")
        self.assertEqual(result.status, STATUS_OK)

        # Side effects
        sent_dir = self.root / "pop" / "sent"
        self.assertTrue(sent_dir.exists(), "sent/ directory should exist")

        # Pending should be empty after rotation
        pending_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        if pending_path.exists():
            content = pending_path.read_text().strip()
            self.assertEqual(content, "", "Pending should be empty after full rotation")

        # No other dirs
        for d in ("quarantine", "dry_run", "failed"):
            self.assertFalse((self.root / "pop" / d).exists(), f"{d} should not exist")

    def test_e2e_safe_output_no_forbidden(self):
        """E2E result safe output contains no forbidden substrings."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        output = format_pop_send_rotation_orchestrator_result(result)
        _assert_no_forbidden(output, "e2e_safe_output")

    def test_e2e_result_repr_no_forbidden(self):
        """E2E result repr contains no forbidden substrings."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        _assert_no_forbidden(repr(result), "e2e_repr")


class TestE2EFailedSend(unittest.TestCase):
    """Scenario 2: fake 500 → pending untouched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_full_env(self.root)
        _write_player_event_to_pending(self.root, _make_player_event(
            event_status="completed", event_type="would_play",
            safety_state="idle", selected_order=0))

    def tearDown(self):
        self.tmp.cleanup()

    def test_500_retry_exhausted_pending_untouched(self):
        """Fake 500 × 3 → send failed, rotation=false, pending untouched."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=500, json_body={"error": "server error"}),
            FakeHttpResponse(status_code=500, json_body={"error": "server error"}),
            FakeHttpResponse(status_code=500, json_body={"error": "server error"}),
        ])
        result = run_pop_scoped_send_then_rotate(self.root, client)

        self.assertTrue(result.send_attempted)
        self.assertFalse(result.send_success)
        self.assertFalse(result.rotation_allowed)
        self.assertFalse(result.rotation_applied)
        self.assertTrue(result.pending_untouched)
        # 500 retry exhausted → send result has pending_should_remain=True
        self.assertIn(result.reason, [REASON_SEND_FAILED, REASON_PENDING_SHOULD_REMAIN])

        # No sent/ created
        self.assertFalse((self.root / "pop" / "sent").exists())
        # Pending still has the original event
        pending_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(pending_path.exists())

    def test_500_safe_output_no_forbidden(self):
        """Failed send result safe output contains no forbidden substrings."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
            FakeHttpResponse(status_code=500, json_body={"error": "boom"}),
        ])
        result = run_pop_scoped_send_then_rotate(self.root, client)
        output = format_pop_send_rotation_orchestrator_result(result)
        _assert_no_forbidden(output, "500_output")


class TestE2E409Duplicate(unittest.TestCase):
    """Scenario 3: fake 409 duplicate → pending untouched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_full_env(self.root)
        _write_player_event_to_pending(self.root, _make_player_event(
            event_status="completed", event_type="would_play",
            safety_state="idle", selected_order=0))

    def tearDown(self):
        self.tmp.cleanup()

    def test_409_duplicate_no_rotation(self):
        """Fake 409 → rotation=false, pending untouched, reason=duplicate."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=409, json_body={"status": "duplicate_batch"}),
        ])
        result = run_pop_scoped_send_then_rotate(self.root, client)

        self.assertTrue(result.send_attempted)
        self.assertFalse(result.send_success)
        self.assertFalse(result.rotation_allowed)
        self.assertFalse(result.rotation_applied)
        self.assertTrue(result.pending_untouched)
        self.assertEqual(result.reason, REASON_DUPLICATE_PENDING_REMAINS)

        # No sent/ created
        _assert_no_sent_dirs(self.root)
        # Pending still has event
        pending_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(pending_path.exists())

    def test_409_safe_output_no_forbidden(self):
        """409 result safe output contains no forbidden substrings."""
        client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=409, json_body={"status": "duplicate_batch"}),
        ])
        result = run_pop_scoped_send_then_rotate(self.root, client)
        output = format_pop_send_rotation_orchestrator_result(result)
        _assert_no_forbidden(output, "409_output")


class TestE2EDraftNotSent(unittest.TestCase):
    """Scenario 4: draft → not eligible for send, no rotation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_full_env(self.root)
        # Player writes draft event (not a completed playback)
        _write_player_event_to_pending(self.root, _make_player_event(
            event_status="draft", event_type="would_play",
            safety_state="idle", selected_order=0))

    def tearDown(self):
        self.tmp.cleanup()

    def test_draft_event_not_sent_not_rotated(self):
        """Draft event → send_attempted=false, rotation=false, pending untouched."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)

        self.assertFalse(result.send_attempted)
        self.assertFalse(result.send_success)
        self.assertFalse(result.rotation_applied)
        self.assertEqual(result.reason, REASON_NO_ELIGIBLE_EVENTS)
        self.assertEqual(client.call_count, 0, "No HTTP call for draft")

        # No dirs created
        _assert_no_sent_dirs(self.root)

    def test_draft_safe_output_no_forbidden(self):
        """Draft result safe output contains no forbidden substrings."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        output = format_pop_send_rotation_orchestrator_result(result)
        _assert_no_forbidden(output, "draft_output")


class TestE2EInvalidJson(unittest.TestCase):
    """Scenario 5: invalid JSON → not sent, no rotation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _setup_full_env(self.root)
        # Write invalid JSON to pending
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / POP_JSONL_FILE).write_text("this is not valid json\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_invalid_json_not_sent_not_rotated(self):
        """Invalid JSON → send_attempted=false, rotation=false."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)

        self.assertFalse(result.send_attempted)
        self.assertFalse(result.rotation_applied)
        self.assertEqual(result.reason, REASON_NO_ELIGIBLE_EVENTS)
        self.assertEqual(client.call_count, 0)

        _assert_no_sent_dirs(self.root)

    def test_invalid_json_safe_output_no_forbidden(self):
        """Invalid JSON result safe output contains no forbidden substrings."""
        client = FakeHttpClient()
        result = run_pop_scoped_send_then_rotate(self.root, client)
        output = format_pop_send_rotation_orchestrator_result(result)
        _assert_no_forbidden(output, "invalid_output")


class TestE2EFingerprintRace(unittest.TestCase):
    """Scenario 6: fingerprint mismatch — changed line NOT sent."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_race_changed_line_not_sent(self):
        """Fingerprint mismatch: scope built from line A, pending overwritten with B → sent=0."""
        from kso_sidecar_agent.pop_rotation_materializer import (
            PopRotationSentScope,
            build_pending_line_fingerprint,
        )
        from kso_sidecar_agent.pop_rotation_apply import (
            apply_pop_rotation_local,
        )

        # Setup full environment
        _setup_full_env(self.root)

        # Build scope from line with selected_order=0
        original = json.dumps(_make_player_event(
            event_status="completed", selected_order=0), sort_keys=True)
        scope = PopRotationSentScope(
            _line_numbers=frozenset({1}),
            _line_fingerprints={1: build_pending_line_fingerprint(original)},
        )

        # Write DIFFERENT line to pending (same line number, different content)
        changed = json.dumps(_make_player_event(
            event_status="completed", selected_order=1), sort_keys=True)
        path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(changed + "\n")

        # Fake send result
        class FakeSR:
            run_status = "ok"
            pending_should_remain = False
            reason = "processed"

        # Run full apply (to test fingerprint guard end-to-end)
        apply_result = apply_pop_rotation_local(
            self.root,
            send_run_result=FakeSR(),
            sent_scope=scope,
        )

        # Fingerprint mismatch → sent=0
        self.assertEqual(apply_result.sent_records, 0,
                         "Fingerprint mismatch should result in 0 sent records")
        self.assertTrue(apply_result.applied, "Apply should still complete (wrote other categories)")

        # Verify no sent/ dir (no sent records to write)
        self.assertFalse((self.root / "pop" / "sent").exists(),
                         "sent/ should not exist when no records to send")

    def test_race_safe_output_no_forbidden(self):
        """Race test safe output contains no forbidden substrings."""
        from kso_sidecar_agent.pop_rotation_materializer import (
            PopRotationSentScope,
            build_pending_line_fingerprint,
        )
        from kso_sidecar_agent.pop_rotation_apply import (
            apply_pop_rotation_local,
            format_pop_rotation_apply_result,
        )

        _setup_full_env(self.root)
        original = json.dumps(_make_player_event(
            event_status="completed", selected_order=0), sort_keys=True)
        scope = PopRotationSentScope(
            _line_numbers=frozenset({1}),
            _line_fingerprints={1: build_pending_line_fingerprint(original)},
        )

        changed = json.dumps(_make_player_event(
            event_status="completed", selected_order=1), sort_keys=True)
        path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(changed + "\n")

        class FakeSR:
            run_status = "ok"
            pending_should_remain = False
            reason = "processed"

        result = apply_pop_rotation_local(self.root, send_run_result=FakeSR(), sent_scope=scope)
        output = format_pop_rotation_apply_result(result)
        _assert_no_forbidden(output, "race_output")


if __name__ == "__main__":
    unittest.main()
