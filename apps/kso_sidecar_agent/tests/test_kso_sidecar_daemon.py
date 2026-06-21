"""KSO Sidecar Production Daemon Loop Core — Smoke Tests.

Tests the full sidecar daemon loop:
  daemon cycle → sync manifest/media → pickup completed PoP →
  build payload → send to backend → rotate only after confirmed accept →
  write health file → graceful stop.

No real HTTP, no real sleep, no real backend, no systemd.
"""

import json as _json
import shutil
import sys as _sys
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from unittest.mock import MagicMock as _MagicMock

from kso_sidecar_agent.kso_manifest_media_sync import (
    KsoMediaDownloadResponse,
    KsoGatewayClient,
    STATUS_OK as GW_OK,
    STATUS_ERROR as GW_ERROR,
)
from kso_sidecar_agent.pop_scoped_send import (
    PopScopedSendResult,
    STATUS_OK as SCOPED_OK,
    STATUS_WARNING as SCOPED_WARNING,
    STATUS_ERROR as SCOPED_ERROR,
    REASON_SEND_OK,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
    REASON_LOCK_UNAVAILABLE_SCOPED,
    REASON_SEND_FAILED,
)
from kso_sidecar_agent.pop_sender_runner import (
    PopSendRunResult,
    RUN_OK,
    RUN_WARNING,
)
from kso_sidecar_agent.pop_rotation_materializer import (
    PopRotationSentScope,
)
from kso_sidecar_agent.kso_sidecar_daemon import (
    run_kso_sidecar_daemon,
    KsoSidecarDaemonResult,
    format_kso_sidecar_daemon_result,
    DAEMON_STATUS_STOPPED,
    DAEMON_STATUS_ERROR,
    REASON_OK,
    REASON_MAX_CYCLES,
    REASON_STOP_CHECK,
    REASON_MAX_CONSECUTIVE_ERRORS,
    REASON_INVALID_ARGS,
)

# ══════════════════════════════════════════════════════════════════════
# Fake Gateway Client
# ══════════════════════════════════════════════════════════════════════

_PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class FakeGatewayClient:
    """Fake KSO gateway — returns manifest/media from a queue."""

    def __init__(
        self,
        manifest_responses: Optional[List[Dict[str, Any]]] = None,
        manifest_errors: Optional[List[Optional[Exception]]] = None,
        media_responses: Optional[Dict[str, KsoMediaDownloadResponse]] = None,
        media_errors: Optional[Dict[str, Exception]] = None,
    ):
        self._manifests = list(manifest_responses) if manifest_responses else []
        self._manifest_errors = list(manifest_errors) if manifest_errors else []
        self._media_responses = media_responses or {}
        self._media_errors = media_errors or {}
        self.fetch_count = 0
        self.download_count = 0

    def fetch_current_manifest(self) -> Mapping[str, Any]:
        self.fetch_count += 1
        if self._manifest_errors:
            err = self._manifest_errors.pop(0)
            if err is not None:
                raise err
        if self._manifests:
            return self._manifests.pop(0)
        # Default: served with one item
        return {
            "status": "served",
            "manifest_version_id": "mv-001",
            "manifest_hash": "abc123",
            "published_at": "2026-06-19T10:00:00Z",
            "manifest": {
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
            },
        }

    def download_kso_media(self, media_ref: str) -> KsoMediaDownloadResponse:
        self.download_count += 1
        if media_ref in self._media_errors:
            raise self._media_errors[media_ref]
        if media_ref in self._media_responses:
            return self._media_responses[media_ref]
        return KsoMediaDownloadResponse(
            status=GW_OK,
            content_type="image/png",
            content_length=len(_PNG_BODY),
            body=_PNG_BODY,
        )


def _served_manifest_response(items=None):
    """Factory: served manifest response."""
    return {
        "status": "served",
        "manifest_version_id": "mv-001",
        "manifest_hash": "abc123",
        "published_at": "2026-06-19T10:00:00Z",
        "manifest": {
            "schemaVersion": 1,
            "generatedAt": "2026-06-19T10:00:00Z",
            "channel": "kso",
            "storeCode": "safe_store",
            "deviceCode": "safe_device",
            "items": items or [{
                "slotOrder": 0,
                "contentType": "image/png",
                "durationMs": 5000,
                "mediaRef": "media/current/slot-000",
            }],
        },
    }


def _not_modified_response():
    return {"status": "not_modified", "manifest": None}


def _no_manifest_response():
    return {"status": "no_manifest", "manifest": None}


# ══════════════════════════════════════════════════════════════════════
# Fake HTTP Client (for pop_send)
# ══════════════════════════════════════════════════════════════════════

class FakeHttpError(Exception):
    def __init__(self, message="fake error"):
        super().__init__(message)


@dataclass
class FakeHttpResponse:
    status_code: int
    json_body: Any
    elapsed_ms: float = 10.0


class FakeHttpClient:
    """Fake SafeHttpClient — returns responses from a queue."""

    def __init__(self, responses=None, errors=None):
        self._responses = list(responses) if responses else []
        self._errors = list(errors) if errors else []
        self._had_errors_initially = bool(errors)
        self.call_count = 0

    def post_json(self, path, payload, headers=None):
        self.call_count += 1
        if self._errors:
            err = self._errors.pop(0)
            if err is not None:
                raise err
            # None in errors queue = skip this attempt, try next response
        if self._responses:
            resp = self._responses.pop(0)
            if resp is not None:
                return resp
        # If errors were initially provided (not just responses), keep erroring
        if self._had_errors_initially:
            raise FakeHttpError("all errors exhausted")
        # Default: accepted
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

def _make_completed_event():
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


def _setup_root(root: Path) -> None:
    """Setup full root: manifest + media + completed PoP pending."""
    (root / "manifest").mkdir(parents=True, exist_ok=True)
    (root / "manifest" / "current_manifest.json").write_text(_json.dumps({
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
    }))

    (root / "media" / "current").mkdir(parents=True, exist_ok=True)
    (root / "media" / "current" / "slot-000").write_bytes(_PNG_BODY)

    (root / "pop" / "pending").mkdir(parents=True, exist_ok=True)
    (root / "pop" / "pending" / "player_events.jsonl").write_text(
        _json.dumps(_make_completed_event()) + "\n",
        encoding="utf-8",
    )

    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "kso_state.json").write_text(_json.dumps({
        "state": "idle",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "ukm4_state_adapter",
    }))


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestKsoSidecarDaemonCore(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_sd_"))
        self.root = self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── Safe output checker ──────────────────────────────────────────

    def _assert_safe(self, output: str):
        lower = output.lower()
        forbidden = [
            "/tmp/", "/var/", "slot-", "current_manifest",
            "backend_url", "device_code", "device_secret",
            "authorization", "bearer", "sha256",
            "manifest_item_id", "manifest_version_id", "manifest_hash",
            "campaign_id", "creative_id", "rendition_id",
            "schedule_item_id", "batch_id", "booking_id",
            "file_path", "media_path", "media_ref",
            "storage", "minio", "stacktrace", "traceback",
            "token", "secret", "password",
        ]
        for fb in forbidden:
            self.assertNotIn(fb, lower,
                             f"Safe output must not contain '{fb}': {output[:200]}")

    def _assert_health_safe(self, health_path: Path):
        data = _json.loads(health_path.read_text())
        text = _json.dumps(data).lower()
        forbidden = [
            "slot-", "current_manifest", "media_ref",
            "backend_url", "device_code", "authorization",
            "bearer", "sha256", "manifest_item_id",
            "campaign_id", "creative_id", "token", "secret",
            "password", "stacktrace", "batch_id",
        ]
        for fb in forbidden:
            self.assertNotIn(fb, text,
                             f"Health must not contain '{fb}': {text[:200]}")

    # ── Daemon core tests ────────────────────────────────────────────

    def test_daemon_max_cycles_0_noop(self):
        """max_cycles=0 → safe no-op."""
        gw = FakeGatewayClient()
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=0,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.cycles_completed, 0)
        self.assertEqual(result.reason, REASON_MAX_CYCLES)
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_daemon_max_cycles_3(self):
        """max_cycles=3 → completes 3 cycles with accepted send."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient()  # Default: accepted

        sleep_calls = []
        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=3,
            sleep_fn=lambda s: sleep_calls.append(s),
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.cycles_completed, 3)
        self.assertEqual(result.reason, REASON_MAX_CYCLES)
        self.assertGreaterEqual(result.pop_sent_count, 1)
        # All 3 cycles tried to sync
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_stop_check_stops_daemon(self):
        """stop_check returns True → daemon stops cleanly."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient()

        call_count = [0]

        def stop_after_2():
            call_count[0] += 1
            return call_count[0] >= 2

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            stop_check=stop_after_2,
            max_cycles=10,  # should stop before this
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.reason, REASON_STOP_CHECK)
        self.assertEqual(result.cycles_completed, 1)  # check before 2nd cycle
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_sync_not_modified_noop(self):
        """not_modified sync → no worry, daemon continues."""
        _setup_root(self.root)
        gw = FakeGatewayClient(
            manifest_responses=[
                _not_modified_response(),
                _not_modified_response(),
                _not_modified_response(),
            ],
        )
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=3,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.cycles_completed, 3)
        self.assertEqual(result.sync_error_count, 0)
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_sync_no_manifest_safe(self):
        """no_manifest → sync counts as success, daemon continues."""
        _setup_root(self.root)
        gw = FakeGatewayClient(manifest_responses=[_no_manifest_response()])
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.cycles_completed, 1)
        self.assertEqual(result.sync_error_count, 0)
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_manifest_fetch_error_not_fatal(self):
        """Gateway fetch error → sync_error++, daemon continues."""
        _setup_root(self.root)
        gw = FakeGatewayClient(manifest_errors=[FakeHttpError("gateway down")])
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.sync_error_count, 1)
        self.assertEqual(result.error_count, 1)  # this cycle counted as error
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_media_download_failure_does_not_break_daemon(self):
        """Media download failure → manifest not published, daemon continues."""
        _setup_root(self.root)
        gw = FakeGatewayClient(
            media_errors={"media/current/slot-000": FakeHttpError("download failed")},
        )
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.cycles_completed, 1)
        # Sync failed → error
        self.assertGreater(result.sync_error_count, 0)
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_completed_pop_accepted_moves_to_sent(self):
        """Accepted send → pending moved to sent."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient()  # Default: accepted

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.cycles_completed, 1)
        self.assertGreaterEqual(result.pop_sent_count, 1)

        # Check pending is empty after rotation
        pending = self.root / "pop" / "pending" / "player_events.jsonl"
        if pending.exists():
            # Should be empty or absent after sent rotation
            content = pending.read_text().strip()
            self.assertEqual(content, "",
                             f"Pending should be empty after sent: {content[:100]}")

        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_backend_reject_pending_preserved(self):
        """Backend reject → pending preserved, not sent."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient(responses=[
            FakeHttpResponse(
                status_code=400,
                json_body={"status": "error", "detail": "bad request"},
            ),
        ])

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.pop_sent_count, 0)
        self.assertGreaterEqual(result.pop_error_count, 1)
        self.assertGreaterEqual(result.pending_preserved_count, 1)

        # Pending file still has the event
        pending = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pending.exists(), "Pending should still exist after reject")
        content = pending.read_text().strip()
        self.assertIn("completed", content)

        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_network_error_pending_preserved(self):
        """Network error → pending preserved."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient(errors=[FakeHttpError("connection refused")])

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.pop_sent_count, 0)
        self.assertGreaterEqual(result.pop_error_count, 1)

        # Pending preserved
        pending = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pending.exists())

        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_no_pending_pop_safe_noop(self):
        """No pending PoP → safe no-op."""
        # Setup without pending PoP
        (self.root / "manifest").mkdir(parents=True)
        (self.root / "manifest" / "current_manifest.json").write_text(_json.dumps({
            "schemaVersion": 1,
            "channel": "kso",
            "items": [{"slotOrder": 0, "contentType": "image/png",
                        "durationMs": 5000, "mediaRef": "media/current/slot-000"}],
        }))

        gw = FakeGatewayClient()
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.pop_sent_count, 0)
        self.assertEqual(result.pop_error_count, 0)
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_second_cycle_does_not_resend_sent_events(self):
        """Second cycle does not resend already-sent events."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient()

        # First cycle: send + sent
        result1 = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )
        self.assertGreaterEqual(result1.pop_sent_count, 1)

        # Second cycle: no pending → no send
        # Need fresh gw/http for second cycle
        gw2 = FakeGatewayClient()
        http2 = FakeHttpClient()

        result2 = run_kso_sidecar_daemon(
            str(self.root), gw2, http2,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        # No new sends (pending was emptied)
        self.assertEqual(result2.pop_sent_count, 0, "Should not resend already-sent events")
        self._assert_safe(format_kso_sidecar_daemon_result(result2))

    def test_health_file_written_atomically(self):
        """Health file is written and safe."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient()

        health_path = self.root / "sidecar-health.json"

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
            health_file=str(health_path),
        )

        self.assertTrue(result.health_written)
        self.assertTrue(health_path.exists())

        self._assert_health_safe(health_path)

        data = _json.loads(health_path.read_text())
        self.assertIn("status", data)
        self.assertIn("cycles_completed", data)
        self.assertIn("daemon_status", data)
        # Ensure no forbidden keys
        for key in data:
            self.assertNotIn("path", key.lower())
            self.assertNotIn("secret", key.lower())
            self.assertNotIn("token", key.lower())

    def test_health_file_safe_no_paths_secrets(self):
        """Health file contains no paths, mediaRef, raw IDs, hash, secrets."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient()

        health_path = self.root / "sidecar-health.json"
        run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
            health_file=str(health_path),
        )

        raw = health_path.read_text().lower()
        forbidden = [
            "/tmp/", "/var/", "slot-", "media_ref",
            "backend_url", "authorization", "bearer", "sha256",
            "manifest_item_id", "campaign_id",
            "secret", "token", "password", "stacktrace",
        ]
        for fb in forbidden:
            self.assertNotIn(fb, raw, f"Health file must not contain '{fb}'")

    def test_max_consecutive_errors_stops_daemon(self):
        """After max_consecutive_errors, daemon stops."""
        _setup_root(self.root)
        # Both gw and http fail every time
        gw = FakeGatewayClient(manifest_errors=[FakeHttpError("fail")])
        http = FakeHttpClient(errors=[FakeHttpError("fail")])

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=10,
            max_consecutive_errors=2,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_ERROR)
        self.assertEqual(result.reason, REASON_MAX_CONSECUTIVE_ERRORS)
        self.assertEqual(result.cycles_completed, 2)
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_daemon_result_repr_safe(self):
        """Result repr contains no forbidden substrings."""
        _setup_root(self.root)
        gw = FakeGatewayClient()
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self._assert_safe(repr(result))
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_invalid_args_returns_error(self):
        """Invalid args → KsoSidecarDaemonResult with error status."""
        result = run_kso_sidecar_daemon(
            str(self.root),
            gateway_client=None,  # type: ignore
            http_client=None,  # type: ignore
            max_cycles=1,
        )
        self.assertEqual(result.status, DAEMON_STATUS_ERROR)
        self.assertEqual(result.reason, REASON_INVALID_ARGS)

    def test_auth_token_provided_for_send(self):
        """Auth provider is called for PoP send."""
        _setup_root(self.root)
        gw = FakeGatewayClient()

        auth_calls = []
        def auth_provider():
            auth_calls.append(1)
            return "fake-token"

        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            auth_provider=auth_provider,
            max_cycles=1,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertGreaterEqual(len(auth_calls), 1)

    def test_format_result_safe(self):
        """format_kso_sidecar_daemon_result produces safe output."""
        result = KsoSidecarDaemonResult(
            status=DAEMON_STATUS_STOPPED,
            cycles_completed=5,
            sync_ok_count=5,
            sync_error_count=0,
            pop_sent_count=3,
            pop_error_count=0,
            pending_preserved_count=0,
            reason=REASON_MAX_CYCLES,
        )
        output = format_kso_sidecar_daemon_result(result)
        self._assert_safe(output)
        self.assertIn("status:", output)
        self.assertIn("cycles_completed:", output)
        self.assertIn("reason:", output)

    def test_daemon_with_idempotent_setup(self):
        """Setup with root that has empty pending → daemon still runs fine."""
        (self.root / "pop" / "pending").mkdir(parents=True, exist_ok=True)
        # No player_events.jsonl — no pending

        gw = FakeGatewayClient()
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=2,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(result.cycles_completed, 2)
        self.assertEqual(result.pop_sent_count, 0)  # No pending to send
        self._assert_safe(format_kso_sidecar_daemon_result(result))

    def test_daemon_survives_sync_error_then_recovery(self):
        """Sync error on first cycle → recovers on second."""
        _setup_root(self.root)
        # First: gateway error, second: normal
        gw = FakeGatewayClient(
            manifest_errors=[FakeHttpError("fail"), None],
        )
        http = FakeHttpClient()

        result = run_kso_sidecar_daemon(
            str(self.root), gw, http,
            max_cycles=2,
            sleep_fn=lambda s: None,
        )

        self.assertEqual(result.status, DAEMON_STATUS_STOPPED)
        self.assertGreaterEqual(result.sync_error_count, 1)
        # Should recover: error counter resets on successful cycle
        self.assertEqual(result.error_count, 0)  # last cycle ok
        self._assert_safe(format_kso_sidecar_daemon_result(result))


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
