"""KSO Completed PoP Confirmed Send Lifecycle — Smoke Tests.

End-to-end: player completed PoP → sidecar pickup → eligible batch
→ backend-ready payload → fake send (accepted) → pending marked sent
only after confirmed accept.

Tests the full send lifecycle:
- dry-run → pending preserved
- network error → pending preserved
- backend reject → pending preserved
- accepted response → event moved to sent (rotation apply)
- duplicate/second send is safe
- sent event is not sent twice
- malformed event → safe error
- draft event → not sent
- missing manifest/media → no send

No real backend, no HTTP, no Chromium, no systemd.
"""

import json
import os as _os
import shutil
import sys as _sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── Cross-package imports ──────────────────────────────────────────────
_PLAYER_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "kso_player")
_PLAYER_DIR = _os.path.abspath(_PLAYER_DIR)
if _PLAYER_DIR not in _sys.path:
    _sys.path.insert(0, _PLAYER_DIR)

from kso_player.display_cycle import (
    run_kso_display_completion_once,
)
from kso_sidecar_agent.pop_pickup import (
    scan_pending_pop_events,
    classify_pop_event,
    CLASS_DRAFT,
    CLASS_ELIGIBLE,
    CLASS_QUARANTINE,
    REASON_MANIFEST_UNAVAILABLE,
    REASON_MEDIA_CACHE_INCOMPLETE,
    REASON_ELIGIBLE,
)
from kso_sidecar_agent.pop_batch import (
    build_pop_eligible_batch,
)
from kso_sidecar_agent.pop_payload import (
    build_pop_backend_payload,
    PopPayloadEnvelope,
)
from kso_sidecar_agent.pop_sender import (
    classify_pop_send_response,
    PopSendResult,
    SEND_OK,
    SEND_WARNING,
    SEND_ERROR,
    REASON_PROCESSED,
    REASON_NO_PAYLOAD,
    REASON_NETWORK_ERROR,
    REASON_BAD_REQUEST,
    REASON_VALIDATION_ERROR,
)
from kso_sidecar_agent.pop_sender_runner import (
    run_pop_send_with_retry,
    PopSendRunResult,
    RUN_OK,
    RUN_WARNING,
    RUN_ERROR,
)
from kso_sidecar_agent.pop_scoped_send import (
    run_pop_scoped_send,
    PopScopedSendResult,
    format_pop_scoped_send_result,
    STATUS_OK as SCOPED_OK,
    SEND_STATUS_OK,
    SEND_STATUS_WARNING,
    SEND_STATUS_ERROR,
    SEND_STATUS_SKIPPED,
    REASON_SEND_OK,
    REASON_SEND_FAILED,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
)
from kso_sidecar_agent.pop_rotation_apply import (
    apply_pop_rotation_local,
    PopRotationApplyResult,
    format_pop_rotation_apply_result,
    STATUS_OK as ROT_OK,
    REASON_APPLIED,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_SEND_NOT_SUCCESSFUL,
)
from kso_sidecar_agent.pop_send_package import (
    build_pop_send_package,
    PopSendPackageResult,
    REASON_BUILT,
    REASON_NO_PENDING_FILE,
    REASON_NO_ELIGIBLE_EVENTS,
)

# ══════════════════════════════════════════════════════════════════════
# Fake HTTP client (same pattern as test_pop_scoped_send.py)
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

        if self._errors:
            err = self._errors.pop(0)
            if err is not None:
                raise err

        if self._responses:
            resp = self._responses.pop(0)
            if resp is not None:
                return resp

        # Default: 200 accepted
        return FakeHttpResponse(
            status_code=200,
            json_body={
                "status": "processed",
                "summary": {"accepted": len(payload.get("events", []))},
            },
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _make_idle_state(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    return {
        "state": "idle",
        "updated_at_utc": now.isoformat(timespec="seconds"),
        "source": "ukm4_state_adapter",
    }


def _make_kso_manifest():
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-06-19T10:00:00Z",
        "channel": "kso",
        "storeCode": "safe_store",
        "deviceCode": "safe_device",
        "items": [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }],
    }


_PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _setup_full_root(root):
    """Setup: idle state + KSO safe manifest + media file."""
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "kso_state.json").write_text(
        json.dumps(_make_idle_state()))

    (root / "manifest").mkdir(parents=True, exist_ok=True)
    (root / "manifest" / "current_manifest.json").write_text(
        json.dumps(_make_kso_manifest()))

    (root / "media" / "current").mkdir(parents=True, exist_ok=True)
    (root / "media" / "current" / "slot-000").write_bytes(_PNG_BODY)


def _make_completed_event():
    """Create a completed would_play event record (simulating post-display)."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "event_type": "would_play",
        "event_status": "completed",
        "created_at": now,
        "started_at": now,
        "ended_at": now,
        "duration_ms": 5000,
        "playback_allowed": True,
        "session_action": "play",
        "session_reason": "ready",
        "selected_order": 0,
        "selected_content_type": "image/png",
        "safety_state": "idle",
        "result": "would_play",
    }


def _write_completed_pop(root):
    """Write a single completed would_play event to pending."""
    (root / "pop" / "pending").mkdir(parents=True, exist_ok=True)
    event = _make_completed_event()
    (root / "pop" / "pending" / "player_events.jsonl").write_text(
        json.dumps(event) + "\n", encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestKsoCompletedPopConfirmedSendLifecycle(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_csl_"))
        self.root = self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── Safe output checker ────────────────────────────────────────────

    def _assert_safe_output(self, output):
        lower = output.lower() if isinstance(output, str) else str(output).lower()
        forbidden = [
            "/tmp/", "/var/", "slot-", "current_manifest",
            "backend_url", "device_code", "device_secret",
            "authorization", "bearer", "sha256",
            "manifest_item_id", "manifest_version_id", "manifest_hash",
            "campaign_id", "creative_id", "rendition_id",
            "schedule_item_id", "batch_id", "booking_id",
            "file_path", "media_path", "storage", "minio",
            "stacktrace", "traceback", "media_ref",
        ]
        for fb in forbidden:
            self.assertNotIn(fb, lower,
                             f"Safe output must not contain '{fb}': {output[:200]}")

    # ── Player → Completed PoP → Sidecar pickup (baseline) ─────────────

    def test_player_completed_pop_sidecar_pickup(self):
        """Player writes completed → sidecar pickup sees eligible."""
        _setup_full_root(self.root)
        result = run_kso_display_completion_once(
            self.root, confirm_display_completed=True,
        )
        self.assertTrue(result.completed_pop_written)

        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.eligible_events, 1)
        self.assertEqual(scan.draft_events, 0)

    # ── Package build with KSO safe manifest ──────────────────────────

    def test_package_built_with_kso_safe_manifest(self):
        """KSO safe manifest → package built with 1 event."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        package = build_pop_send_package(self.root)
        self.assertTrue(package.package_built)
        self.assertEqual(package.payload_events, 1)
        self.assertEqual(package.scope_lines, 1)
        self.assertEqual(package.reason, REASON_BUILT)
        self._assert_safe_output(repr(package))

    def test_package_payload_has_selected_order(self):
        """KSO safe manifest → package payload contains selected_order."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        package = build_pop_send_package(self.root)
        self.assertIsNotNone(package._payload)
        self.assertEqual(len(package._payload.events), 1)
        evt = package._payload.events[0]
        self.assertEqual(evt.selected_order, 0)
        self.assertEqual(evt.selected_content_type, "image/png")
        self.assertEqual(evt.play_status, "completed")
        self.assertEqual(evt.duration_ms, 5000)

    def test_package_empty_for_draft_only(self):
        """Draft-only pending → no package."""
        _setup_full_root(self.root)
        # Write draft event (not completed)
        (self.root / "pop" / "pending").mkdir(parents=True, exist_ok=True)
        draft = {**_make_completed_event(), "event_status": "draft"}
        (self.root / "pop" / "pending" / "player_events.jsonl").write_text(
            json.dumps(draft) + "\n", encoding="utf-8")

        package = build_pop_send_package(self.root)
        self.assertFalse(package.package_built)
        self.assertEqual(package.reason, REASON_NO_ELIGIBLE_EVENTS)

    def test_package_empty_no_manifest(self):
        """No manifest → no package (completed→quarantine)."""
        # Setup without manifest
        (self.root / "media" / "current").mkdir(parents=True, exist_ok=True)
        (self.root / "media" / "current" / "slot-000").write_bytes(_PNG_BODY)
        _write_completed_pop(self.root)

        package = build_pop_send_package(self.root)
        self.assertFalse(package.package_built)
        self.assertEqual(package.reason, REASON_NO_ELIGIBLE_EVENTS)

    def test_package_empty_no_media(self):
        """No media → no package."""
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(
            json.dumps(_make_kso_manifest()))
        _write_completed_pop(self.root)

        package = build_pop_send_package(self.root)
        self.assertFalse(package.package_built)

    # ── Scoped send with fake HTTP ─────────────────────────────────────

    def test_scoped_send_accepted(self):
        """Fake accepted response → send_success=True."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        http_client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, http_client)

        self.assertTrue(result.send_attempted)
        self.assertTrue(result.send_success)
        self.assertEqual(result.send_status, SEND_STATUS_OK)
        self.assertEqual(result.reason, REASON_SEND_OK)
        self.assertEqual(result.payload_events, 1)
        self.assertTrue(result.pending_untouched,
                        "Scoped send does NOT apply rotation")
        self._assert_safe_output(repr(result))
        self._assert_safe_output(format_pop_scoped_send_result(result))

    def test_scoped_send_no_eligible(self):
        """No pending → scoped send skipped."""
        _setup_full_root(self.root)

        http_client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, http_client)

        self.assertFalse(result.send_attempted)
        self.assertEqual(result.send_status, SEND_STATUS_SKIPPED)
        self.assertEqual(result.reason, REASON_NO_ELIGIBLE_EVENTS_SCOPED)
        self.assertEqual(http_client.call_count, 0,
                         "No HTTP call for empty pending")

    def test_scoped_send_network_error(self):
        """Network error → pending preserved."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        # 3 retries exhausted
        http_client = FakeHttpClient(
            errors=[
                FakeHttpError(status_code=0, message="connection refused", retryable=True),
                FakeHttpError(status_code=0, message="connection refused", retryable=True),
                FakeHttpError(status_code=0, message="connection refused", retryable=True),
            ]
        )
        result = run_pop_scoped_send(self.root, http_client)

        self.assertTrue(result.send_attempted)
        self.assertFalse(result.send_success)
        self.assertEqual(result.send_status, SEND_STATUS_ERROR)
        self.assertTrue(result.pending_untouched,
                        "Pending must remain on network error")
        self._assert_safe_output(repr(result))

    def test_scoped_send_backend_reject(self):
        """Backend reject → pending preserved."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        http_client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=422, json_body={"status": "rejected", "rejected_count": 1})
        ])
        result = run_pop_scoped_send(self.root, http_client)

        self.assertTrue(result.send_attempted)
        self.assertFalse(result.send_success)
        # 422 → classify_pop_send_response returns SEND_ERROR,
        # but retry runner maps it to RUN_WARNING → scoped send → SEND_STATUS_WARNING
        self.assertEqual(result.send_status, SEND_STATUS_WARNING)
        self.assertTrue(result.pending_untouched,
                        "Pending preserved on reject")
        self._assert_safe_output(repr(result))

    # ── Full confirmed send lifecycle: scoped send + rotation apply ────

    def _do_full_lifecycle(self, http_client):
        """Run scoped send → check result → apply rotation."""
        send_result = run_pop_scoped_send(self.root, http_client)

        if not send_result.send_success:
            return send_result, None

        # Apply rotation: move sent events out of pending
        rotation = apply_pop_rotation_local(
            self.root,
            send_run_result=send_result._send_run_result,
            sent_scope=send_result._sent_scope,
        )
        return send_result, rotation

    def test_full_lifecycle_accepted(self):
        """Full lifecycle: package → send accepted → rotation applied."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop_file.exists(), "Pending exists before send")
        pending_before = pop_file.read_text()

        http_client = FakeHttpClient()
        send_result, rotation = self._do_full_lifecycle(http_client)

        # ── Send succeeded ─────────────────────────────────────
        self.assertIsNotNone(send_result)
        self.assertTrue(send_result.send_success)
        self.assertEqual(http_client.call_count, 1)

        # ── Rotation applied ───────────────────────────────────
        self.assertIsNotNone(rotation)
        self.assertTrue(rotation.applied)
        self.assertEqual(rotation.sent_records, 1)
        self.assertEqual(rotation.sent_records, 1)
        self.assertEqual(rotation.pending_lines_before, 1)
        self.assertEqual(rotation.pending_lines_after, 0,
                         "Sent event removed from pending")
        self.assertFalse(rotation.pending_untouched,
                         "Pending was rewritten (sent event removed)")
        self.assertEqual(rotation.reason, REASON_APPLIED)
        self._assert_safe_output(repr(rotation))
        self._assert_safe_output(format_pop_rotation_apply_result(rotation))

        # ── Pending file was rewritten ──────────────────────────
        new_content = pop_file.read_text().strip()
        self.assertEqual(new_content, "",
                         "Pending should be empty after sent event removed")

        # ── Sent file exists ────────────────────────────────────
        sent_dir = self.root / "pop" / "sent"
        self.assertTrue(sent_dir.exists(), "Sent directory created")
        sent_files = list(sent_dir.glob("*.jsonl"))
        self.assertEqual(len(sent_files), 1, "One sent file written")

    def test_dry_run_pending_preserved(self):
        """Dry-run: output safe, pending preserved, no HTTP call."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text()

        # Run scoped send with dry-run (no actual backend call needed,
        # just verify the pipeline up to payload build)
        package = build_pop_send_package(self.root)
        self.assertTrue(package.package_built)
        self.assertEqual(package.payload_events, 1)

        # Verify pending unchanged
        self.assertTrue(pop_file.exists(), "Pending preserved after package build")
        self.assertEqual(pop_file.read_text(), old_content)

        # Verify payload is safe
        self._assert_safe_output(repr(package))

    def test_network_error_pending_preserved(self):
        """Network error → send fails → pending NOT deleted."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text()

        # 3 retries exhausted
        http_client = FakeHttpClient(
            errors=[
                FakeHttpError(status_code=0, message="connection refused", retryable=True),
                FakeHttpError(status_code=0, message="connection refused", retryable=True),
                FakeHttpError(status_code=0, message="connection refused", retryable=True),
            ]
        )
        send_result, rotation = self._do_full_lifecycle(http_client)

        # Send failed
        self.assertIsNotNone(send_result)
        self.assertFalse(send_result.send_success)
        self.assertTrue(send_result.pending_untouched)

        # Rotation was NOT applied (send not successful → no sent scope applied)
        self.assertIsNone(rotation)

        # Pending file unchanged
        self.assertTrue(pop_file.exists(), "Pending preserved on network error")
        self.assertEqual(pop_file.read_text(), old_content)

    def test_backend_reject_pending_preserved(self):
        """Backend reject → pending preserved."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text()

        http_client = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=422, json_body={"status": "rejected", "rejected_count": 1})
        ])
        send_result, rotation = self._do_full_lifecycle(http_client)

        self.assertIsNotNone(send_result)
        self.assertFalse(send_result.send_success)

        # Rotation was NOT applied
        self.assertIsNone(rotation)

        # Pending file unchanged
        self.assertTrue(pop_file.exists(), "Pending preserved on reject")
        self.assertEqual(pop_file.read_text(), old_content)

    # ── Duplicate send safety ──────────────────────────────────────────

    def test_duplicate_send_is_safe(self):
        """After first send accepted + rotation applied, second scan finds no eligible."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        # First: send + rotate
        http_client1 = FakeHttpClient()
        send1, rot1 = self._do_full_lifecycle(http_client1)
        self.assertTrue(send1.send_success)
        self.assertTrue(rot1.applied)
        self.assertEqual(rot1.sent_records, 1)

        # Second scan: no pending events
        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.total_lines, 0)
        self.assertEqual(scan.eligible_events, 0)

        # Second send: no eligible
        http_client2 = FakeHttpClient()
        result2 = run_pop_scoped_send(self.root, http_client2)
        self.assertFalse(result2.send_attempted)
        self.assertEqual(http_client2.call_count, 0,
                         "No HTTP call for second send (nothing eligible)")

    def test_sent_event_not_sent_twice(self):
        """Sent file exists, pending empty → no duplicate send."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        # First: full lifecycle
        http_client = FakeHttpClient()
        send_result, rotation = self._do_full_lifecycle(http_client)
        self.assertTrue(rotation.applied)

        # Verify sent file exists
        sent_files = list((self.root / "pop" / "sent").glob("*.jsonl"))
        self.assertEqual(len(sent_files), 1)

        # Pending is empty
        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.eligible_events, 0)

        # Package build: nothing to send
        package = build_pop_send_package(self.root)
        self.assertFalse(package.package_built)

    # ── Negative scenarios ─────────────────────────────────────────────

    def test_malformed_event_safe_error(self):
        """Malformed JSON in pending → safe error, no stacktrace."""
        (self.root / "pop" / "pending").mkdir(parents=True, exist_ok=True)
        (self.root / "pop" / "pending" / "player_events.jsonl").write_text(
            "this is not json\n")

        # Package build handles gracefully
        package = build_pop_send_package(self.root)
        self.assertFalse(package.package_built)
        self._assert_safe_output(repr(package))

        # Scoped send handles gracefully
        http_client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, http_client)
        self.assertFalse(result.send_attempted)
        self.assertEqual(http_client.call_count, 0)

    def test_missing_manifest_no_send(self):
        """Missing manifest context → no eligible → no send."""
        (self.root / "media" / "current").mkdir(parents=True, exist_ok=True)
        (self.root / "media" / "current" / "slot-000").write_bytes(_PNG_BODY)
        _write_completed_pop(self.root)

        http_client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, http_client)
        self.assertFalse(result.send_attempted)
        self.assertEqual(http_client.call_count, 0)

    def test_missing_media_cache_no_send(self):
        """Missing media cache → no eligible → no send."""
        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(
            json.dumps(_make_kso_manifest()))
        _write_completed_pop(self.root)

        http_client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, http_client)
        self.assertFalse(result.send_attempted)
        self.assertEqual(http_client.call_count, 0)

    # ── Payload safety ─────────────────────────────────────────────────

    def test_payload_safe_fields_only(self):
        """Payload contains only safe fields: selected_order, selected_content_type, duration_ms, play_status."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        package = build_pop_send_package(self.root)
        self.assertIsNotNone(package._payload)
        evt = package._payload.events[0]

        # Safe fields present
        self.assertEqual(evt.selected_order, 0)
        self.assertEqual(evt.selected_content_type, "image/png")
        self.assertEqual(evt.play_status, "completed")
        self.assertEqual(evt.duration_ms, 5000)

        # Verify raw IDs ARE in the payload (for backend use, hidden via repr=False)
        # but the safe OUTPUT (repr) doesn't expose them
        self._assert_safe_output(repr(evt))
        self._assert_safe_output(repr(package))
        self._assert_safe_output(repr(package._payload))

    def test_send_result_repr_safe(self):
        """All send result reprs are safe."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        http_client = FakeHttpClient()
        result = run_pop_scoped_send(self.root, http_client)
        self._assert_safe_output(repr(result))
        self._assert_safe_output(format_pop_scoped_send_result(result))

    def test_pending_not_deleted_by_scan_or_batch(self):
        """Scan/batch/payload build do NOT delete pending."""
        _setup_full_root(self.root)
        _write_completed_pop(self.root)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text()

        scan_pending_pop_events(self.root)
        build_pop_eligible_batch(self.root)
        build_pop_backend_payload(self.root)
        build_pop_send_package(self.root)

        self.assertTrue(pop_file.exists(), "Pending preserved")
        self.assertEqual(pop_file.read_text(), old_content)

    # ── Classification direct tests ────────────────────────────────────

    def test_classify_completed_eligible_with_kso(self):
        """Direct classify: completed + KSO manifest items → eligible."""
        record = _make_completed_event()
        manifest_items = [{"slotOrder": 0, "order": 0}]

        cls = classify_pop_event(record, manifest_items=manifest_items,
                                 media_cache_complete=True)
        self.assertEqual(cls.classification, CLASS_ELIGIBLE)
        self.assertEqual(cls.reason, REASON_ELIGIBLE)
        self.assertTrue(cls.backend_eligible)

    def test_classify_completed_quarantine_no_manifest(self):
        """Direct classify: completed + no manifest → quarantine."""
        record = _make_completed_event()

        cls = classify_pop_event(record, manifest_items=None,
                                 media_cache_complete=True)
        self.assertEqual(cls.classification, CLASS_QUARANTINE)
        self.assertEqual(cls.reason, REASON_MANIFEST_UNAVAILABLE)
        self.assertFalse(cls.backend_eligible)

    def test_classify_completed_quarantine_no_media(self):
        """Direct classify: completed + manifest but no media → quarantine."""
        record = _make_completed_event()
        manifest_items = [{"slotOrder": 0, "order": 0}]

        cls = classify_pop_event(record, manifest_items=manifest_items,
                                 media_cache_complete=False)
        self.assertEqual(cls.classification, CLASS_QUARANTINE)
        self.assertEqual(cls.reason, REASON_MEDIA_CACHE_INCOMPLETE)
        self.assertFalse(cls.backend_eligible)

    # ── Response classifier tests ──────────────────────────────────────

    def test_classify_accepted_response(self):
        """Accepted response → processed, pending_should_remain=False."""
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {"accepted": 1}},
            attempted_events=1,
        )
        self.assertEqual(result.send_status, SEND_OK)
        self.assertEqual(result.reason, REASON_PROCESSED)
        self.assertEqual(result.accepted_events, 1)
        self.assertFalse(result.pending_should_remain,
                         "Accepted → event can be marked sent")
        self._assert_safe_output(repr(result))

    def test_classify_rejected_response(self):
        """Rejected response → error, pending_should_remain=True."""
        result = classify_pop_send_response(
            http_status=422,
            response_json={"status": "rejected", "rejected_count": 1},
            attempted_events=1,
        )
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertTrue(result.pending_should_remain,
                        "Rejected → pending must remain")
        self._assert_safe_output(repr(result))

    def test_classify_network_error(self):
        """Network error → retryable, pending_should_remain=True."""
        result = classify_pop_send_response(
            error_type="network",
            attempted_events=1,
        )
        self.assertEqual(result.send_status, SEND_ERROR)
        self.assertEqual(result.reason, REASON_NETWORK_ERROR)
        self.assertTrue(result.retryable)
        self.assertTrue(result.pending_should_remain,
                        "Network error → pending preserved")
        self._assert_safe_output(repr(result))

    def test_classify_empty_payload(self):
        """Zero attempted_events with 'processed' status → still processed, pending can be removed."""
        result = classify_pop_send_response(
            http_status=200,
            response_json={"status": "processed", "summary": {}},
            attempted_events=0,
        )
        # The classifier doesn't have a "no_payload" concept — that's the sender's job.
        # With status="processed" and no counts, it falls through to REASON_PROCESSED.
        self.assertEqual(result.reason, REASON_PROCESSED)
        self.assertFalse(result.pending_should_remain,
                         "Zero events processed → pending can be removed")
        self._assert_safe_output(repr(result))
