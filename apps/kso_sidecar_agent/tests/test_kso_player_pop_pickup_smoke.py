"""KSO Player PoP → Sidecar Pickup Smoke.

End-to-end: player display-cycle-once --confirm-pop-write
→ pop/pending/player_events.jsonl → sidecar pickup scan
→ sidecar batch build → backend-ready payload.

No real backend, no HTTP, no Chromium, no systemd.

KNOWN LIMITATION: sidecar read_current_manifest expects legacy manifest
format (manifest_version_id, manifest_hash, source). KSO safe manifest
body doesn't include these. Scanner gracefully falls back to manifest_items=None
which prevents completed→eligible mapping. Completed events go to quarantine.
This will be addressed when sidecar manifest reading supports KSO safe format.
"""

import json
import os as _os
import shutil
import sys as _sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# ── Cross-package imports ──────────────────────────────────────────────
_PLAYER_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "kso_player")
_PLAYER_DIR = _os.path.abspath(_PLAYER_DIR)
if _PLAYER_DIR not in _sys.path:
    _sys.path.insert(0, _PLAYER_DIR)

from kso_player.display_cycle import (
    run_kso_display_cycle_once,
)
from kso_sidecar_agent.pop_pickup import (
    scan_pending_pop_events,
    classify_pop_event,
    CLASS_DRAFT,
    CLASS_ELIGIBLE,
    CLASS_QUARANTINE,
    REASON_MANIFEST_UNAVAILABLE,
)
from kso_sidecar_agent.pop_batch import (
    build_pop_eligible_batch,
)
from kso_sidecar_agent.pop_payload import (
    build_pop_backend_payload,
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


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestPlayerPopSidecarPickupSmoke(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_pps_"))
        self.root = self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── Player → PoP file ──────────────────────────────────────────

    def test_player_writes_pop_only_with_confirm(self):
        """With confirm_pop_write=True → PoP file exists."""
        _setup_full_root(self.root)
        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertTrue(result.pop_written)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop_file.exists(), "PoP file must exist after confirm")

        lines = pop_file.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 1, "Exactly one PoP line")

    def test_without_confirm_sidecar_has_nothing(self):
        """Without confirm → no PoP file → sidecar sees nothing."""
        _setup_full_root(self.root)
        result = run_kso_display_cycle_once(self.root, confirm_pop_write=False)
        self.assertFalse(result.pop_written)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertFalse(pop_file.exists(), "No PoP without confirm")

        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.total_lines, 0)

    def test_non_idle_state_no_pop_sidecar_noop(self):
        """Non-idle state → no PoP → sidecar scan = 0."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = {"state": "transaction", "updated_at_utc": datetime.now(timezone.utc).isoformat(), "source": "ukm4"}
        (self.root / "state" / "kso_state.json").write_text(json.dumps(state))

        (self.root / "manifest").mkdir(parents=True, exist_ok=True)
        (self.root / "manifest" / "current_manifest.json").write_text(json.dumps(_make_kso_manifest()))
        (self.root / "media" / "current").mkdir(parents=True, exist_ok=True)
        (self.root / "media" / "current" / "slot-000").write_bytes(_PNG_BODY)

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertFalse(result.pop_written)

        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.total_lines, 0)

    def test_missing_manifest_no_pop_sidecar_noop(self):
        """Missing manifest → no PoP → sidecar scan = 0."""
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / "kso_state.json").write_text(json.dumps(_make_idle_state()))

        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertFalse(result.pop_written)

        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.total_lines, 0)

    # ── Sidecar pickup → player draft event (full E2E) ─────────────

    def test_sidecar_pickup_sees_player_draft_event(self):
        """Player writes draft → sidecar pickup sees it, classifies as draft."""
        _setup_full_root(self.root)
        result = run_kso_display_cycle_once(self.root, confirm_pop_write=True)
        self.assertTrue(result.pop_written)

        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.total_lines, 1)
        self.assertEqual(scan.draft_events, 1,
                         "Player writes draft event → sidecar sees draft")
        self.assertEqual(scan.eligible_events, 0,
                         "Draft event is NOT eligible for backend")

    def test_sidecar_batch_empty_for_draft_only(self):
        """Draft-only pending → batch is empty (no eligible events)."""
        _setup_full_root(self.root)
        run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        batch = build_pop_eligible_batch(self.root)
        self.assertEqual(batch.candidate_events, 0,
                         "Draft events are not eligible → empty batch")
        self.assertEqual(batch.draft_events, 1)
        self.assertEqual(batch.status, "ok")

    def test_sidecar_payload_empty_for_draft_only(self):
        """Draft-only pending → payload is empty."""
        _setup_full_root(self.root)
        run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        payload = build_pop_backend_payload(self.root)
        self.assertEqual(payload.payload_events, 0,
                         "Draft events not eligible → empty payload")

    # ── Completed classification (direct classify_pop_event) ───────

    def test_completed_event_classified_eligible_with_manifest(self):
        """Direct classify: completed + manifest_items → eligible."""
        record = _make_completed_event()
        manifest_items = [{"slotOrder": 0, "order": 0}]

        cls = classify_pop_event(record, manifest_items=manifest_items,
                                 media_cache_complete=True)
        self.assertEqual(cls.classification, CLASS_ELIGIBLE)
        self.assertTrue(cls.backend_eligible)

    def test_completed_event_classified_quarantine_without_manifest(self):
        """Direct classify: completed + no manifest_items → quarantine."""
        record = _make_completed_event()

        cls = classify_pop_event(record, manifest_items=None,
                                 media_cache_complete=True)
        self.assertEqual(cls.classification, CLASS_QUARANTINE)
        self.assertEqual(cls.reason, REASON_MANIFEST_UNAVAILABLE)
        self.assertFalse(cls.backend_eligible)

    def test_completed_event_scan_quarantine_kso_format(self):
        """Scan with KSO safe manifest → completed goes to quarantine."""
        self.root = self.tmp
        _setup_full_root(self.root)

        # Write completed event directly + KSO manifest
        (self.root / "pop" / "pending").mkdir(parents=True, exist_ok=True)
        event = _make_completed_event()
        (self.root / "pop" / "pending" / "player_events.jsonl").write_text(
            json.dumps(event) + "\n", encoding="utf-8")

        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.total_lines, 1)
        # With KSO safe manifest, read_current_manifest raises ValueError
        # (missing manifest_version_id/manifest_hash/source) → manifest_items=None
        # → completed goes to quarantine
        self.assertEqual(scan.eligible_events, 0)
        self.assertEqual(scan.quarantine_events, 1,
                         "KSO safe manifest → quarantine (known limitation)")

    # ── Negative: corrupted PoP line ───────────────────────────────

    def test_corrupted_pop_line_safe_error(self):
        """Corrupted JSON line → sidecar safe error, no stacktrace."""
        (self.root / "pop" / "pending").mkdir(parents=True, exist_ok=True)
        (self.root / "pop" / "pending" / "player_events.jsonl").write_text(
            "this is not json\n", encoding="utf-8")

        scan = scan_pending_pop_events(self.root)
        self.assertGreaterEqual(scan.total_lines, 1)
        self.assertEqual(scan.eligible_events, 0)

        scan_repr = repr(scan)
        self._assert_safe_output(scan_repr)

    def test_empty_pending_file_safe_noop(self):
        """Empty pending file → safe no-op."""
        (self.root / "pop" / "pending").mkdir(parents=True, exist_ok=True)
        (self.root / "pop" / "pending" / "player_events.jsonl").write_text("")

        scan = scan_pending_pop_events(self.root)
        self.assertEqual(scan.total_lines, 0)
        self.assertEqual(scan.status, "ok")

        batch = build_pop_eligible_batch(self.root)
        self.assertEqual(batch.candidate_events, 0)
        self.assertEqual(batch.status, "ok")

    # ── Pending not deleted ────────────────────────────────────────

    def test_pending_not_deleted_after_pickup_scan(self):
        """Scan does not delete pending events."""
        _setup_full_root(self.root)
        run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text()

        scan_pending_pop_events(self.root)

        self.assertTrue(pop_file.exists(), "Scan must not delete pending")
        self.assertEqual(pop_file.read_text(), old_content,
                         "Scan must not modify pending")

    def test_pending_not_deleted_after_batch_build(self):
        """Batch build does not delete pending events."""
        _setup_full_root(self.root)
        run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text()

        build_pop_eligible_batch(self.root)

        self.assertTrue(pop_file.exists(), "Batch build must not delete pending")
        self.assertEqual(pop_file.read_text(), old_content,
                         "Batch build must not modify pending")

    def test_pending_not_deleted_after_payload_build(self):
        """Payload build does not delete pending events."""
        _setup_full_root(self.root)
        run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text()

        build_pop_backend_payload(self.root)

        self.assertTrue(pop_file.exists(), "Payload build must not delete pending")
        self.assertEqual(pop_file.read_text(), old_content,
                         "Payload build must not modify pending")

    # ── Output safety ──────────────────────────────────────────────

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

    def test_scan_result_repr_safe(self):
        """PopPickupScanResult repr safe."""
        _setup_full_root(self.root)
        run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        scan = scan_pending_pop_events(self.root)
        self._assert_safe_output(repr(scan))

    def test_batch_result_repr_safe(self):
        """PopBatchBuildResult repr safe."""
        _setup_full_root(self.root)
        run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        batch = build_pop_eligible_batch(self.root)
        self._assert_safe_output(repr(batch))

    def test_payload_result_repr_safe(self):
        """PopPayloadBuildResult repr safe."""
        _setup_full_root(self.root)
        run_kso_display_cycle_once(self.root, confirm_pop_write=True)

        payload = build_pop_backend_payload(self.root)
        self._assert_safe_output(repr(payload))

    def test_classification_repr_safe(self):
        """Classification repr safe."""
        record = _make_completed_event()
        cls = classify_pop_event(record, manifest_items=[{"order": 0}],
                                 media_cache_complete=True)
        self._assert_safe_output(repr(cls))
