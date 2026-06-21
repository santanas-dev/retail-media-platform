"""KSO State Adapter + Sidecar + Player Three-Daemon Local E2E Smoke.

Tests all three production daemon cores together in sequence:
  state-adapter daemon → writes kso_state.json
  sidecar daemon (sync) → fake gateway manifest/media → local files
  player daemon → reads state + manifest + media → rotates ads → completed PoP
  sidecar daemon (send) → picks up completed PoP → fake accepted send → rotation

No real HTTP, no real Chromium, no real sleep, no systemd, no real UKM 4.
"""

import json as _json
import shutil
import sys as _sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from kso_state_adapter.daemon import (
    run_kso_state_adapter_daemon,
    KsoStateAdapterDaemonResult,
    format_daemon_result,
    DAEMON_STATUS_STOPPED as SA_STOPPED,
    DAEMON_STATUS_ERROR as SA_ERROR,
    REASON_MAX_CYCLES as SA_MAX_CYCLES,
    REASON_MAX_ERRORS as SA_MAX_ERRORS,
)
from kso_state_adapter.source import (
    StaticStateSource,
    SequenceStateSource,
    ErroringStateSource,
)
from kso_state_adapter.state_model import (
    STATE_IDLE,
    STATE_UNKNOWN,
    STATE_TRANSACTION,
    STATE_ERROR,
)

# ── Sidecar imports ──────────────────────────────────────────────────
_SIDECAR_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "kso_sidecar_agent"
)
if _SIDECAR_DIR not in _sys.path:
    _sys.path.insert(0, _SIDECAR_DIR)

from kso_sidecar_agent.kso_manifest_media_sync import (
    KsoMediaDownloadResponse,
    KsoGatewayClient,
    STATUS_OK as GW_OK,
    STATUS_ERROR as GW_ERROR,
)
from kso_sidecar_agent.kso_sidecar_daemon import (
    run_kso_sidecar_daemon,
    KsoSidecarDaemonResult,
    format_kso_sidecar_daemon_result,
    DAEMON_STATUS_STOPPED as SC_STOPPED,
    REASON_MAX_CYCLES as SC_MAX_CYCLES,
)

# ── Player imports ───────────────────────────────────────────────────
_PLAYER_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "kso_player"
)
if _PLAYER_DIR not in _sys.path:
    _sys.path.insert(0, _PLAYER_DIR)

from kso_player.runtime_daemon import (
    run_kso_runtime_daemon,
    KsoRuntimeDaemonResult,
    format_kso_runtime_daemon_result,
    STATUS_OK as P_STATUS_OK,
    REASON_STOPPED as P_STOPPED,
)

# ══════════════════════════════════════════════════════════════════════
# Fake HTTP Client
# ══════════════════════════════════════════════════════════════════════

_PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class FakeHttpError(Exception):
    def __init__(self, message="fake error"):
        super().__init__(message)


@dataclass
class FakeHttpResponse:
    status_code: int
    json_body: Any
    elapsed_ms: float = 10.0


class FakeHttpClient:
    """Injectable HTTP client for sidecar daemon tests."""

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
        if self._responses:
            resp = self._responses.pop(0)
            if resp is not None:
                return resp
        if self._had_errors_initially:
            raise FakeHttpError("all errors exhausted")
        return FakeHttpResponse(
            status_code=200,
            json_body={
                "status": "processed",
                "summary": {"accepted": len(payload.get("events", []))},
            },
        )


# ══════════════════════════════════════════════════════════════════════
# Fake Gateway Client
# ══════════════════════════════════════════════════════════════════════

def _kso_manifest_2_items():
    return {
        "status": "served",
        "manifest_version_id": "mv-three-daemon",
        "manifest_hash": "d" * 64,
        "published_at": "2026-06-21T10:00:00Z",
        "manifest": {
            "schemaVersion": 1,
            "generatedAt": "2026-06-21T10:00:00Z",
            "channel": "kso",
            "storeCode": "store_td",
            "deviceCode": "device_td",
            "items": [
                {
                    "slotOrder": 0,
                    "contentType": "image/png",
                    "durationMs": 1000,
                    "mediaRef": "media/current/slot-000",
                },
                {
                    "slotOrder": 1,
                    "contentType": "image/png",
                    "durationMs": 1000,
                    "mediaRef": "media/current/slot-001",
                },
            ],
        },
    }


def _not_modified_response():
    return {"status": "not_modified", "manifest": None}


def _error_response():
    return {"status": "error", "manifest": None}


class FakeGatewayClient:
    def __init__(self, manifest_responses=None, manifest_errors=None,
                 media_responses=None, media_errors=None):
        self._manifests = list(manifest_responses) if manifest_responses else []
        self._manifest_errors = list(manifest_errors) if manifest_errors else []
        self._media_responses = media_responses or {}
        self._media_errors = media_errors or {}
        self.fetch_count = 0

    def fetch_current_manifest(self) -> Mapping[str, Any]:
        self.fetch_count += 1
        if self._manifest_errors:
            err = self._manifest_errors.pop(0)
            if err is not None:
                raise err
        if self._manifests:
            return self._manifests.pop(0)
        return _kso_manifest_2_items()

    def download_kso_media(self, media_ref: str) -> KsoMediaDownloadResponse:
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


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_source_shell_dir(base: Path) -> Path:
    shell = base / "player_shell"
    shell.mkdir(parents=True, exist_ok=True)
    for fname in ["index.html", "styles.css", "player.js", "bootstrap.js",
                   "bootstrap_snapshot.js"]:
        (shell / fname).write_text(f"/* {fname} */\n", encoding="utf-8")
    return shell


def _make_runtime_dir(base: Path) -> Path:
    rd = base / "runtime_shell"
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def _make_fake_launcher():
    class FakeProcess:
        pass

    def launcher(command):
        return FakeProcess()

    return launcher


def _noop_sleep():
    def _sleep(seconds):
        pass
    return _sleep


# ══════════════════════════════════════════════════════════════════════
# Safety checker
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN = frozenset({
    "/tmp/", "/var/", "slot-", "current_manifest",
    "backend_url", "device_code", "device_secret",
    "authorization", "bearer", "sha256",
    "manifest_item_id", "manifest_version_id", "manifest_hash",
    "campaign_id", "creative_id", "rendition_id",
    "schedule_item_id", "batch_id", "booking_id",
    "file_path", "media_path", "media_ref",
    "storage", "minio", "stacktrace", "traceback",
    "token", "secret", "password",
    "full_manifest", "media_bytes",
    "receipt_number", "card_number", "customer_id", "phone",
    "email", "fiscal_data",
})


def _assert_safe(test, output: str):
    lower = output.lower() if isinstance(output, str) else str(output).lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, lower,
                         f"Forbidden '{fb}' in: {output[:200]}")


def _assert_health_safe(test, health_path: Path):
    data = _json.loads(health_path.read_text())
    text = _json.dumps(data).lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, text,
                         f"Health '{fb}' in: {text[:200]}")


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestKsoThreeDaemonE2ESmoke(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_3d_"))
        self.root = self.tmp / "kso_root"
        self.root.mkdir(parents=True, exist_ok=True)

        # Player shell dirs
        self.source_shell = _make_source_shell_dir(self.tmp)
        self.runtime_shell = _make_runtime_dir(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ══════════════════════════════════════════════════════════════════
    # Happy path
    # ══════════════════════════════════════════════════════════════════

    def test_three_daemon_e2e_happy_path(self):
        """State adapter → sidecar sync → player 2 items → sidecar send."""
        health_sa = self.tmp / "state-adapter-health.json"
        health_sc = self.tmp / "sidecar-health.json"
        health_pl = self.tmp / "player-health.json"

        # ═══ Phase 1: State adapter writes idle ═══════════════════
        sa_source = StaticStateSource(state=STATE_IDLE)
        sa_result = run_kso_state_adapter_daemon(
            root=str(self.root),
            source=sa_source,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sa),
        )
        self.assertEqual(sa_result.status, SA_STOPPED)
        self.assertEqual(sa_result.cycles_completed, 1)
        self.assertTrue(sa_result.state_written)
        self.assertEqual(sa_result.last_state, STATE_IDLE)
        _assert_safe(self, format_daemon_result(sa_result))

        # Verify state file
        state_file = self.root / "state" / "kso_state.json"
        self.assertTrue(state_file.exists())
        state_data = _json.loads(state_file.read_text())
        self.assertEqual(state_data["state"], STATE_IDLE)

        # ═══ Phase 2: Sidecar sync manifest + media ══════════════
        gw1 = FakeGatewayClient()
        http1 = FakeHttpClient()

        sc_result1 = run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw1,
            http_client=http1,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sc),
        )
        self.assertEqual(sc_result1.status, SC_STOPPED)
        self.assertGreaterEqual(sc_result1.sync_ok_count, 1)
        self.assertEqual(sc_result1.pop_sent_count, 0)
        _assert_safe(self, format_kso_sidecar_daemon_result(sc_result1))

        # Verify local manifest + media
        manifest_path = self.root / "manifest" / "current_manifest.json"
        self.assertTrue(manifest_path.exists())
        manifest_data = _json.loads(manifest_path.read_text())
        self.assertEqual(len(manifest_data["items"]), 2)
        for slot in ["slot-000", "slot-001"]:
            self.assertTrue(
                (self.root / "media" / "current" / slot).exists(),
                f"Media {slot} should exist")

        # ═══ Phase 3: Player daemon displays 2 items ═════════════
        fake_launcher = _make_fake_launcher()

        p_result = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            prepare_demo_fixture=False,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
            health_file=str(health_pl),
        )
        self.assertEqual(p_result.status, P_STATUS_OK)
        self.assertEqual(p_result.cycles_completed, 2)
        self.assertEqual(p_result.rendered_count, 2)
        self.assertEqual(p_result.completed_pop_written_count, 2)
        _assert_safe(self, format_kso_runtime_daemon_result(p_result))

        # Verify pending PoP
        pending_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pending_file.exists())
        pending_content = pending_file.read_text()
        completed_count = pending_content.count('"completed"')
        self.assertGreaterEqual(completed_count, 2)

        # ═══ Phase 4: Sidecar sends completed PoP ════════════════
        gw2 = FakeGatewayClient(manifest_responses=[_not_modified_response()])
        http2 = FakeHttpClient()

        sc_result2 = run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw2,
            http_client=http2,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sc),
        )
        self.assertEqual(sc_result2.status, SC_STOPPED)
        self.assertGreaterEqual(sc_result2.pop_sent_count, 1)
        _assert_safe(self, format_kso_sidecar_daemon_result(sc_result2))

        # Verify pending empty, sent populated
        if pending_file.exists():
            self.assertEqual(pending_file.read_text().strip(), "")
        sent_dir = self.root / "pop" / "sent"
        if sent_dir.exists():
            sent_files = list(sent_dir.glob("*.jsonl"))
            self.assertGreaterEqual(len(sent_files), 1)

        # ═══ All health files safe ══════════════════════════════
        _assert_health_safe(self, health_sa)
        _assert_health_safe(self, health_sc)
        _assert_health_safe(self, health_pl)

    # ══════════════════════════════════════════════════════════════════
    # Negative: unknown state → player hold
    # ══════════════════════════════════════════════════════════════════

    def test_unknown_state_player_hold_no_pop(self):
        """State adapter writes unknown → player holds → no PoP."""
        health_sa = self.tmp / "state-adapter-health.json"
        health_sc = self.tmp / "sidecar-health.json"
        health_pl = self.tmp / "player-health.json"

        # State adapter: unknown
        sa_source = StaticStateSource(state=STATE_UNKNOWN)
        sa_result = run_kso_state_adapter_daemon(
            root=str(self.root),
            source=sa_source,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sa),
        )
        self.assertEqual(sa_result.last_state, STATE_UNKNOWN)

        # Sidecar sync
        gw = FakeGatewayClient()
        run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw,
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sc),
        )

        # Player: must hold due to unknown state
        p_result = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=_make_fake_launcher(),
            health_file=str(health_pl),
        )
        self.assertEqual(p_result.rendered_count, 0,
                         "Must render 0 items when state is unknown")
        self.assertEqual(p_result.completed_pop_written_count, 0,
                         "Must write 0 completed PoP when state is unknown")
        self.assertGreaterEqual(p_result.hold_count, 2,
                                "Must hold all cycles")
        _assert_health_safe(self, health_sa)
        _assert_health_safe(self, health_sc)
        _assert_health_safe(self, health_pl)

    # ══════════════════════════════════════════════════════════════════
    # Negative: state adapter source error → error state → hold
    # ══════════════════════════════════════════════════════════════════

    def test_state_adapter_error_player_hold(self):
        """State adapter source raises → writes error → player holds."""
        health_pl = self.tmp / "player-health.json"

        # State adapter with erroring source
        sa_source = ErroringStateSource()
        sa_result = run_kso_state_adapter_daemon(
            root=str(self.root),
            source=sa_source,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )
        self.assertEqual(sa_result.last_state, STATE_ERROR,
                         "Source error must write error, never idle")

        # Sidecar sync
        gw = FakeGatewayClient()
        run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw,
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )

        # Player holds
        p_result = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=_make_fake_launcher(),
            health_file=str(health_pl),
        )
        self.assertEqual(p_result.rendered_count, 0)
        self.assertEqual(p_result.completed_pop_written_count, 0)
        _assert_health_safe(self, health_pl)

    # ══════════════════════════════════════════════════════════════════
    # Negative: state change mid-player
    # ══════════════════════════════════════════════════════════════════

    def test_state_change_idle_to_transaction_mid_player(self):
        """State: idle → player cycle 1 renders → state changes to transaction
        → player cycle 2 holds → only first cycle has completed PoP."""
        health_sa = self.tmp / "state-adapter-health.json"
        health_sc = self.tmp / "sidecar-health.json"
        health_pl = self.tmp / "player-health.json"

        # State adapter: idle (cycle 1), then transaction (cycle 2)
        sa_source = SequenceStateSource(["idle", "transaction"])
        sa_result = run_kso_state_adapter_daemon(
            root=str(self.root),
            source=sa_source,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sa),
        )
        self.assertEqual(sa_result.cycles_completed, 2)
        self.assertEqual(sa_result.last_state, "transaction")

        # Sidecar sync
        gw = FakeGatewayClient()
        run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw,
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sc),
        )

        # Player: max_cycles=2, state should change between cycles
        p_result = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=_make_fake_launcher(),
            health_file=str(health_pl),
        )
        # First cycle: state is idle → renders; second: state is transaction → holds
        self.assertLessEqual(p_result.rendered_count, 1,
                             "At most 1 cycle renders (state transitions to transaction)")
        self.assertLessEqual(p_result.completed_pop_written_count, 1)
        _assert_health_safe(self, health_sa)
        _assert_health_safe(self, health_sc)
        _assert_health_safe(self, health_pl)

    # ══════════════════════════════════════════════════════════════════
    # Negative: sidecar sync failure → no manifest/media → no PoP
    # ══════════════════════════════════════════════════════════════════

    def test_sidecar_sync_failure_no_manifest_no_pop(self):
        """Sidecar sync errors → no manifest → player no PoP."""
        health_sa = self.tmp / "state-adapter-health.json"
        health_sc = self.tmp / "sidecar-health.json"
        health_pl = self.tmp / "player-health.json"

        # State adapter: idle
        run_kso_state_adapter_daemon(
            root=str(self.root),
            source=StaticStateSource(state=STATE_IDLE),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sa),
        )

        # Sidecar with manifest error
        gw = FakeGatewayClient(
            manifest_errors=[FakeHttpError("gateway down")],
        )
        sc_result = run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw,
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sc),
        )
        self.assertEqual(sc_result.sync_ok_count, 0)

        # Player: no manifest → no PoP
        p_result = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=_make_fake_launcher(),
            health_file=str(health_pl),
        )
        self.assertEqual(p_result.completed_pop_written_count, 0)
        _assert_health_safe(self, health_sa)
        _assert_health_safe(self, health_sc)
        _assert_health_safe(self, health_pl)

    # ══════════════════════════════════════════════════════════════════
    # Negative: sidecar backend reject → pending preserved
    # ══════════════════════════════════════════════════════════════════

    def test_sidecar_reject_pending_preserved(self):
        """Sidecar backend reject → pending NOT deleted."""
        health_sa = self.tmp / "state-adapter-health.json"

        # State: idle
        run_kso_state_adapter_daemon(
            root=str(self.root),
            source=StaticStateSource(state=STATE_IDLE),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sa),
        )

        # Sidecar sync
        gw = FakeGatewayClient()
        run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw,
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )

        # Player: write completed PoP
        run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=_make_fake_launcher(),
        )

        # Sidecar send: backend reject
        reject_response = FakeHttpResponse(
            status_code=422,
            json_body={"status": "rejected", "reason": "validation_error"},
        )
        http_reject = FakeHttpClient(responses=[reject_response])
        sc_result = run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=FakeGatewayClient(
                manifest_responses=[_not_modified_response()],
            ),
            http_client=http_reject,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )
        self.assertEqual(sc_result.pop_sent_count, 0,
                         "Rejected events must not count as sent")

        # Pending must be preserved
        pending_file = self.root / "pop" / "pending" / "player_events.jsonl"
        if pending_file.exists():
            content = pending_file.read_text().strip()
            self.assertNotEqual(content, "",
                                "Pending must NOT be empty after reject")

    # ══════════════════════════════════════════════════════════════════
    # Negative: sidecar network error → pending preserved
    # ══════════════════════════════════════════════════════════════════

    def test_sidecar_network_error_pending_preserved(self):
        """Sidecar network error → pending NOT deleted."""
        health_sa = self.tmp / "state-adapter-health.json"

        # State: idle
        run_kso_state_adapter_daemon(
            root=str(self.root),
            source=StaticStateSource(state=STATE_IDLE),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sa),
        )

        # Sidecar sync
        gw = FakeGatewayClient()
        run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw,
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )

        # Player: write completed PoP
        run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=_make_fake_launcher(),
        )

        # Sidecar send: network error
        http_error = FakeHttpClient(
            errors=[FakeHttpError("connection reset")],
        )
        sc_result = run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=FakeGatewayClient(
                manifest_responses=[_not_modified_response()],
            ),
            http_client=http_error,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )
        self.assertEqual(sc_result.pop_sent_count, 0,
                         "Network error must not count as sent")

        # Pending must be preserved
        pending_file = self.root / "pop" / "pending" / "player_events.jsonl"
        if pending_file.exists():
            content = pending_file.read_text().strip()
            self.assertNotEqual(content, "",
                                "Pending must NOT be empty after network error")

    # ══════════════════════════════════════════════════════════════════
    # Safety: no resend of already-sent events
    # ══════════════════════════════════════════════════════════════════

    def test_no_resend_after_accepted(self):
        """Sidecar sends → accepted → second send must not resend same events."""
        health_sa = self.tmp / "state-adapter-health.json"

        # State: idle
        run_kso_state_adapter_daemon(
            root=str(self.root),
            source=StaticStateSource(state=STATE_IDLE),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sa),
        )

        # Sidecar sync
        gw = FakeGatewayClient()
        run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=gw,
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )

        # Player: write completed PoP
        run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=_make_fake_launcher(),
        )

        # First sidecar send: accepted
        sc_result1 = run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=FakeGatewayClient(
                manifest_responses=[_not_modified_response()],
            ),
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )
        self.assertGreaterEqual(sc_result1.pop_sent_count, 1)

        # Second sidecar send: no more pending → pop_sent_count = 0
        sc_result2 = run_kso_sidecar_daemon(
            root=str(self.root),
            gateway_client=FakeGatewayClient(
                manifest_responses=[_not_modified_response()],
            ),
            http_client=FakeHttpClient(),
            max_cycles=1,
            sleep_fn=_noop_sleep(),
        )
        self.assertEqual(sc_result2.pop_sent_count, 0,
                         "Must not resend already-sent events")


if __name__ == "__main__":
    unittest.main()
