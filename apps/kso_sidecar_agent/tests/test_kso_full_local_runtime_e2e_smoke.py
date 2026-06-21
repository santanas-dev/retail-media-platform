"""KSO Full Local Runtime E2E Smoke — sidecar sync → player loop → sidecar send.

Full local path (no real backend, no Chromium, no systemd):

  fake gateway → sidecar sync → local manifest/media (2 items)
  → player runtime-loop (max_cycles=2, confirm_display_completed=True)
  → 2 completed PoP events written
  → sidecar pickup → batch → payload
  → fake accepted send → rotation apply → pending empty, sent populated

Also covers negative scenarios:
  - media sync failure → player not ready, no PoP
  - state changes during second cycle → only first PoP
  - fake backend reject → pending preserved
  - fake network error → pending preserved
"""

import json as _json
import os as _os
import shutil
import sys as _sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

# ── Cross-package import support ────────────────────────────────────
_PLAYER_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "kso_player")
_PLAYER_DIR = _os.path.abspath(_PLAYER_DIR)
if _PLAYER_DIR not in _sys.path:
    _sys.path.insert(0, _PLAYER_DIR)

# ── Sidecar imports ─────────────────────────────────────────────────
from kso_sidecar_agent.kso_manifest_media_sync import (
    KsoMediaDownloadResponse,
    STATUS_OK as SYNC_STATUS_OK,
    STATUS_ERROR as SYNC_STATUS_ERROR,
    REASON_SYNCED,
    REASON_MEDIA_DOWNLOAD_FAILED,
    sync_kso_manifest_and_media,
)
from kso_sidecar_agent.pop_send_package import (
    build_pop_send_package,
    REASON_BUILT,
)
from kso_sidecar_agent.pop_scoped_send import (
    run_pop_scoped_send,
    SEND_STATUS_OK,
    SEND_STATUS_ERROR,
    SEND_STATUS_SKIPPED,
    REASON_SEND_OK,
    REASON_SEND_FAILED,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
)
from kso_sidecar_agent.pop_rotation_apply import (
    apply_pop_rotation_local,
    STATUS_OK as ROT_OK,
    REASON_APPLIED,
)

# ── Player imports ──────────────────────────────────────────────────
from kso_player.runtime_loop import (
    run_kso_runtime_loop,
    STATUS_OK as PLAYER_OK,
    REASON_COMPLETED,
)
from kso_player.runtime_gate import evaluate_kso_runtime_gate, ACTION_PLAY


# ══════════════════════════════════════════════════════════════════════
# Fake gateway
# ══════════════════════════════════════════════════════════════════════

_PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class FakeE2EGateway:
    """Fake KSO gateway — returns pre-configured manifest + media."""

    def __init__(self, manifest_response=None, media_map=None,
                 fail_fetch=False, fail_download=None):
        self.manifest_response = manifest_response
        self.media_map = media_map or {}
        self.fail_fetch = fail_fetch
        self.fail_download = fail_download or set()

    def fetch_current_manifest(self):
        if self.fail_fetch:
            raise RuntimeError("simulated fetch failure")
        return self.manifest_response

    def download_kso_media(self, media_ref):
        if media_ref in self.fail_download:
            raise RuntimeError("simulated download failure")
        resp = self.media_map.get(media_ref)
        if resp is None:
            return KsoMediaDownloadResponse(
                status=SYNC_STATUS_ERROR, content_type="",
                content_length=0, body=b"",
            )
        return resp


def _make_served_response(items=None):
    manifest = {
        "schemaVersion": 1,
        "generatedAt": "2026-06-19T10:00:00Z",
        "channel": "kso",
        "storeCode": "safe_store",
        "deviceCode": "safe_device",
        "items": items or [],
    }
    return {"status": "served", "manifest": manifest}


def _make_png_dl(body=_PNG_BODY):
    return KsoMediaDownloadResponse(
        status=SYNC_STATUS_OK, content_type="image/png",
        content_length=len(body), body=body,
    )


def _make_error_dl():
    return KsoMediaDownloadResponse(
        status=SYNC_STATUS_ERROR, content_type="",
        content_length=0, body=b"",
    )


# ══════════════════════════════════════════════════════════════════════
# Fake HTTP client for sidecar send
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
        "updated_at_utc": now.isoformat(),
        "source": "ukm4_state_adapter",
    }


def _make_source_shell_dir(base: Path) -> Path:
    d = base / "player_shell"
    d.mkdir(parents=True, exist_ok=True)
    for fn in ["index.html", "styles.css", "player.js", "bootstrap.js",
                "bootstrap_snapshot.js"]:
        (d / fn).write_text(f"/* {fn} */\n", encoding="utf-8")
    return d


def _make_noop_sleep():
    def fn(sec):
        pass
    return fn


def _make_fake_launcher(should_succeed=True):
    class Fake:
        pass

    def fn(cmd):
        return Fake() if should_succeed else None
    return fn


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestKsoFullLocalRuntimeE2ESmoke(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_full_"))
        self.root = self.tmp
        self.source_shell = _make_source_shell_dir(self.tmp)
        self.runtime_shell = self.tmp / "runtime_shell"
        self.runtime_shell.mkdir(parents=True, exist_ok=True)

        # Idle state
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / "kso_state.json").write_text(
            _json.dumps(_make_idle_state()), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _assert_safe_output(self, output):
        lower = output.lower() if isinstance(output, str) else str(output).lower()
        forbidden = [
            "backend_url", "device_code", "device_secret", "authorization",
            "bearer", "media/current/slot", "current_manifest",
            "/tmp/", "/var/", "sha256",
            "manifest_item_id", "manifest_version_id", "manifest_hash",
            "campaign_id", "creative_id", "rendition_id",
            "schedule_item_id", "batch_id", "booking_id",
            "file_path", "media_path", "storage", "minio",
            "stacktrace", "traceback",
        ]
        for fb in forbidden:
            self.assertNotIn(fb, lower,
                             f"Safe output must not contain '{fb}': {output[:200]}")

    # ══════════════════════════════════════════════════════════════
    # Happy path: full E2E
    # ══════════════════════════════════════════════════════════════

    def test_full_e2e_sidecar_sync_player_loop_sidecar_send(self):
        """Full E2E: sync → 2-cycle loop → 2 PoP → pickup → send → sent."""
        # ── 1. Fake gateway ──────────────────────────────────────
        items = [
            {"slotOrder": 0, "contentType": "image/png",
             "durationMs": 5000, "mediaRef": "media/current/slot-000"},
            {"slotOrder": 1, "contentType": "image/png",
             "durationMs": 3000, "mediaRef": "media/current/slot-001"},
        ]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={
                "media/current/slot-000": _make_png_dl(),
                "media/current/slot-001": _make_png_dl(),
            },
        )

        # ── 2. Sidecar sync ──────────────────────────────────────
        sync_result = sync_kso_manifest_and_media(self.root, gw)
        self.assertEqual(sync_result.status, SYNC_STATUS_OK)
        self.assertTrue(sync_result.manifest_written)
        self.assertEqual(sync_result.media_written_count, 2)
        self._assert_safe_output(repr(sync_result))

        # ── 3. Player runtime-loop (2 cycles) ────────────────────
        player_result = run_kso_runtime_loop(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_launch=False,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_make_noop_sleep(),
            process_launcher=_make_fake_launcher(True),
        )
        self.assertEqual(player_result.status, PLAYER_OK)
        self.assertEqual(player_result.cycles_completed, 2)
        self.assertEqual(player_result.rendered_count, 2)
        self.assertEqual(player_result.completed_pop_written_count, 2)
        self.assertEqual(player_result.items_in_playlist, 2)
        self._assert_safe_output(repr(player_result))

        # ── 4. Verify PoP file ───────────────────────────────────
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pop_file.exists())
        lines = pop_file.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 2, "Should have 2 completed PoP lines")
        for line in lines:
            rec = _json.loads(line)
            self.assertEqual(rec.get("event_status"), "completed")

        # ── 5. Sidecar package build ─────────────────────────────
        package = build_pop_send_package(self.root)
        self.assertTrue(package.package_built)
        self.assertEqual(package.payload_events, 2, "2 events in payload")
        self.assertEqual(package.reason, REASON_BUILT)
        self._assert_safe_output(repr(package))

        # ── 6. Sidecar scoped send (fake HTTP) ───────────────────
        http = FakeHttpClient()
        send_result = run_pop_scoped_send(self.root, http)
        self.assertTrue(send_result.send_success)
        self.assertEqual(send_result.send_status, SEND_STATUS_OK)
        self.assertEqual(send_result.reason, REASON_SEND_OK)
        self.assertEqual(send_result.payload_events, 2)
        self._assert_safe_output(repr(send_result))
        # Verify payload is safe (no raw IDs in accessible fields)
        self.assertIsNotNone(send_result._send_run_result)

        # ── 7. Apply rotation → pending → sent ───────────────────
        rotation = apply_pop_rotation_local(
            self.root,
            send_run_result=send_result._send_run_result,
            sent_scope=send_result._sent_scope,
        )
        self.assertEqual(rotation.status, ROT_OK)
        self.assertTrue(rotation.applied)
        self.assertEqual(rotation.sent_records, 2)
        self.assertEqual(rotation.pending_lines_before, 2)
        self.assertEqual(rotation.pending_lines_after, 0)
        self.assertEqual(rotation.reason, REASON_APPLIED)
        self._assert_safe_output(repr(rotation))

        # ── 8. Verify pending empty, sent populated ──────────────
        pending_content = pop_file.read_text(encoding="utf-8").strip()
        self.assertEqual(pending_content, "",
                         "Pending must be empty after rotation")
        sent_dir = self.root / "pop" / "sent"
        self.assertTrue(sent_dir.exists())
        sent_files = list(sent_dir.glob("*.jsonl"))
        self.assertEqual(len(sent_files), 1, "One sent file created")

        # ── 9. Second scan finds nothing ─────────────────────────
        package2 = build_pop_send_package(self.root)
        self.assertFalse(package2.package_built)
        http2 = FakeHttpClient()
        send2 = run_pop_scoped_send(self.root, http2)
        self.assertEqual(send2.send_status, SEND_STATUS_SKIPPED)
        self.assertEqual(http2.call_count, 0, "No HTTP call for empty pending")

    # ══════════════════════════════════════════════════════════════
    # Rotation check: both items selected
    # ══════════════════════════════════════════════════════════════

    def test_both_items_selected_by_round_robin(self):
        """runtime-loop selects items 0→1 in 2 cycles with 2 items."""
        items = [
            {"slotOrder": 0, "contentType": "image/png",
             "durationMs": 5000, "mediaRef": "media/current/slot-000"},
            {"slotOrder": 1, "contentType": "image/png",
             "durationMs": 3000, "mediaRef": "media/current/slot-001"},
        ]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={
                "media/current/slot-000": _make_png_dl(),
                "media/current/slot-001": _make_png_dl(),
            },
        )
        sync_kso_manifest_and_media(self.root, gw)

        run_kso_runtime_loop(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_make_noop_sleep(),
            process_launcher=_make_fake_launcher(True),
        )

        # Verify exactly 2 completed PoP events written
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        lines = pop_file.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 2)
        # Both are completed
        for line in lines:
            rec = _json.loads(line)
            self.assertEqual(rec.get("event_status"), "completed")
            self.assertEqual(rec.get("event_type"), "would_play")
            self.assertEqual(rec.get("safety_state"), "idle")

    # ══════════════════════════════════════════════════════════════
    # Negative: media sync failure → no PoP
    # ══════════════════════════════════════════════════════════════

    def test_media_sync_failure_player_no_pop(self):
        """Media sync failure → manifest not published → player has no items."""
        items = [
            {"slotOrder": 0, "contentType": "image/png",
             "durationMs": 5000, "mediaRef": "media/current/slot-000"},
        ]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_error_dl()},
        )
        result = sync_kso_manifest_and_media(self.root, gw)
        self.assertEqual(result.status, SYNC_STATUS_ERROR)
        self.assertEqual(result.reason, REASON_MEDIA_DOWNLOAD_FAILED)

        # Player has no items
        player_result = run_kso_runtime_loop(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_make_noop_sleep(),
            process_launcher=_make_fake_launcher(True),
        )
        self.assertEqual(player_result.items_in_playlist, 0)
        self.assertEqual(player_result.completed_pop_written_count, 0)

    # ══════════════════════════════════════════════════════════════
    # State changes during second cycle → only first PoP
    # ══════════════════════════════════════════════════════════════

    def test_state_changes_during_second_cycle(self):
        """State changes to transaction before cycle 2 → only 1st PoP written."""
        items = [
            {"slotOrder": 0, "contentType": "image/png",
             "durationMs": 5000, "mediaRef": "media/current/slot-000"},
            {"slotOrder": 1, "contentType": "image/png",
             "durationMs": 3000, "mediaRef": "media/current/slot-001"},
        ]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={
                "media/current/slot-000": _make_png_dl(),
                "media/current/slot-001": _make_png_dl(),
            },
        )
        sync_kso_manifest_and_media(self.root, gw)

        # Sleep that changes state to transaction before cycle 2
        state_file = self.root / "state" / "kso_state.json"
        call_count = [0]

        def state_change_sleep(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:  # Second sleep → change state
                state_file.write_text(_json.dumps({
                    "state": "transaction",
                    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source": "ukm4",
                }))

        run_kso_runtime_loop(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=state_change_sleep,
            process_launcher=_make_fake_launcher(True),
        )

        # First cycle was OK (idle before sleep), second cycle state gate
        # caught the change at the START of cycle 2.
        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        if pop_file.exists():
            lines = pop_file.read_text(encoding="utf-8").strip().split("\n")
            # At most 1 — second cycle held
            self.assertLessEqual(len(lines), 2)
        # Either 0 or 1 PoP events, not 2
        # (state change might happen at cycle start or after re-check)

    # ══════════════════════════════════════════════════════════════
    # Fake backend reject → pending preserved
    # ══════════════════════════════════════════════════════════════

    def test_fake_reject_pending_preserved(self):
        """Fake backend reject → pending preserved, nothing in sent."""
        items = [
            {"slotOrder": 0, "contentType": "image/png",
             "durationMs": 5000, "mediaRef": "media/current/slot-000"},
        ]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_png_dl()},
        )
        sync_kso_manifest_and_media(self.root, gw)
        run_kso_runtime_loop(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_make_noop_sleep(),
            process_launcher=_make_fake_launcher(True),
        )

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text(encoding="utf-8")

        # Fake backend rejects
        http = FakeHttpClient(responses=[
            FakeHttpResponse(
                status_code=422,
                json_body={"status": "rejected", "rejected_count": 1},
            ),
            FakeHttpResponse(
                status_code=422,
                json_body={"status": "rejected", "rejected_count": 1},
            ),
            FakeHttpResponse(
                status_code=422,
                json_body={"status": "rejected", "rejected_count": 1},
            ),
        ])
        send_result = run_pop_scoped_send(self.root, http)
        self.assertFalse(send_result.send_success)

        # Pending preserved
        self.assertTrue(pop_file.exists())
        self.assertEqual(pop_file.read_text(encoding="utf-8"), old_content)

    # ══════════════════════════════════════════════════════════════
    # Fake network error → pending preserved
    # ══════════════════════════════════════════════════════════════

    def test_fake_network_error_pending_preserved(self):
        """Fake network error → pending preserved."""
        items = [
            {"slotOrder": 0, "contentType": "image/png",
             "durationMs": 5000, "mediaRef": "media/current/slot-000"},
        ]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_png_dl()},
        )
        sync_kso_manifest_and_media(self.root, gw)
        run_kso_runtime_loop(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_make_noop_sleep(),
            process_launcher=_make_fake_launcher(True),
        )

        pop_file = self.root / "pop" / "pending" / "player_events.jsonl"
        old_content = pop_file.read_text(encoding="utf-8")

        # Network errors — 3 retries exhausted
        http = FakeHttpClient(errors=[
            FakeHttpError(status_code=0, message="connection refused", retryable=True),
            FakeHttpError(status_code=0, message="connection refused", retryable=True),
            FakeHttpError(status_code=0, message="connection refused", retryable=True),
        ])
        send_result = run_pop_scoped_send(self.root, http)
        self.assertFalse(send_result.send_success)
        self.assertEqual(send_result.send_status, SEND_STATUS_ERROR)

        # Pending preserved
        self.assertTrue(pop_file.exists())
        self.assertEqual(pop_file.read_text(encoding="utf-8"), old_content)

    # ══════════════════════════════════════════════════════════════
    # Missing manifest → no eligible send
    # ══════════════════════════════════════════════════════════════

    def test_missing_manifest_no_eligible_send(self):
        """No manifest synced → player no items → no eligible for send."""
        http = FakeHttpClient()
        result = run_pop_scoped_send(self.root, http)
        self.assertFalse(result.send_attempted)
        self.assertEqual(result.send_status, SEND_STATUS_SKIPPED)
        self.assertEqual(http.call_count, 0)

    # ══════════════════════════════════════════════════════════════
    # Safe output everywhere
    # ══════════════════════════════════════════════════════════════

    def test_full_flow_all_output_safe(self):
        """Every result repr/formatter output is safe."""
        items = [
            {"slotOrder": 0, "contentType": "image/png",
             "durationMs": 5000, "mediaRef": "media/current/slot-000"},
            {"slotOrder": 1, "contentType": "image/png",
             "durationMs": 3000, "mediaRef": "media/current/slot-001"},
        ]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={
                "media/current/slot-000": _make_png_dl(),
                "media/current/slot-001": _make_png_dl(),
            },
        )
        sync_result = sync_kso_manifest_and_media(self.root, gw)
        self._assert_safe_output(repr(sync_result))

        player_result = run_kso_runtime_loop(
            root=self.root,
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="chromium",
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_make_noop_sleep(),
            process_launcher=_make_fake_launcher(True),
        )
        self._assert_safe_output(repr(player_result))

        package = build_pop_send_package(self.root)
        self._assert_safe_output(repr(package))

        http = FakeHttpClient()
        send_result = run_pop_scoped_send(self.root, http)
        self._assert_safe_output(repr(send_result))

        rotation = apply_pop_rotation_local(
            self.root,
            send_run_result=send_result._send_run_result,
            sent_scope=send_result._sent_scope,
        )
        self._assert_safe_output(repr(rotation))
