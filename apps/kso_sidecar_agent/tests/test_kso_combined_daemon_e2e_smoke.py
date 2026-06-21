"""KSO Combined Player + Sidecar Daemon Local E2E Smoke.

Tests both daemon cores together:
  sidecar daemon cycle 1 → fake gateway manifest/media → local files
  player daemon cycles → reads local manifest → rotates ads → completed PoP
  sidecar daemon cycle 2 → picks up PoP → fake accepted send → rotation

No real HTTP, no real Chromium, no real sleep, no systemd.
"""

import json as _json
import shutil
import sys as _sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional
from unittest.mock import MagicMock as _MagicMock

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
    DAEMON_STATUS_STOPPED,
    REASON_MAX_CYCLES,
)

# ── Player imports ────────────────────────────────────────────────────
_PLAYER_DIR = _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "kso_player"))

from kso_player.runtime_daemon import (
    run_kso_runtime_daemon,
    KsoRuntimeDaemonResult,
    format_kso_runtime_daemon_result,
    STATUS_OK as P_STATUS_OK,
    REASON_STOPPED,
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
        "manifest_version_id": "mv-combined-001",
        "manifest_hash": "abc123xyz",
        "published_at": "2026-06-20T10:00:00Z",
        "manifest": {
            "schemaVersion": 1,
            "generatedAt": "2026-06-20T10:00:00Z",
            "channel": "kso",
            "storeCode": "store_e2e",
            "deviceCode": "device_e2e",
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

def _make_idle_state(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    return {
        "state": "idle",
        "updated_at_utc": now.isoformat(),
        "source": "ukm4_state_adapter",
    }


def _create_root_with_state(root: Path) -> None:
    """Create root with idle state only. Manifest+media will come from sidecar sync."""
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "kso_state.json").write_text(
        _json.dumps(_make_idle_state()))


def _make_source_shell_dir(base: Path) -> Path:
    """Minimal player_shell directory."""
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


def _noop_sleep() -> Callable[[float], None]:
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
})


def _assert_safe(test, output: str):
    lower = output.lower() if isinstance(output, str) else str(output).lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, lower,
                         f"Safe output must not contain '{fb}': {output[:200]}")


def _assert_health_safe(test, health_path: Path):
    data = _json.loads(health_path.read_text())
    text = _json.dumps(data).lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, text,
                         f"Health must not contain '{fb}': {text[:200]}")


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestKsoCombinedDaemonE2ESmoke(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_cd_"))
        self.root = self.tmp / "kso_root"
        self.root.mkdir(parents=True)
        _create_root_with_state(self.root)

        # Shell dirs for player
        self.source_shell = _make_source_shell_dir(self.tmp)
        self.runtime_shell = _make_runtime_dir(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ══════════════════════════════════════════════════════════════════
    # Main combined E2E scenario
    # ══════════════════════════════════════════════════════════════════

    def test_combined_daemon_e2e_happy_path(self):
        """Sidecar sync → player displays 2 items → sidecar sends PoP."""
        health_sidecar = self.tmp / "sidecar-health.json"
        health_player = self.tmp / "player-health.json"

        # ═══ Phase 1: Sidecar sync manifest + media ═══════════════
        gw1 = FakeGatewayClient()
        http1 = FakeHttpClient()  # No PoP to send yet

        sc_result1 = run_kso_sidecar_daemon(
            str(self.root),
            gateway_client=gw1,
            http_client=http1,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sidecar),
        )

        self.assertEqual(sc_result1.status, DAEMON_STATUS_STOPPED)
        self.assertEqual(sc_result1.cycles_completed, 1)
        self.assertGreaterEqual(sc_result1.sync_ok_count, 1)
        self.assertEqual(sc_result1.pop_sent_count, 0)  # No PoP yet
        _assert_safe(self, format_kso_sidecar_daemon_result(sc_result1))

        # Verify local manifest + media exist
        manifest_path = self.root / "manifest" / "current_manifest.json"
        self.assertTrue(manifest_path.exists(), "Manifest should exist after sync")
        manifest_data = _json.loads(manifest_path.read_text())
        self.assertIn("items", manifest_data)
        self.assertEqual(len(manifest_data["items"]), 2)

        for slot in ["slot-000", "slot-001"]:
            media_path = self.root / "media" / "current" / slot
            self.assertTrue(media_path.exists(), f"Media {slot} should exist")

        # ═══ Phase 2: Player daemon displays 2 items ══════════════
        fake_launcher = _make_fake_launcher()

        p_result = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            prepare_demo_fixture=False,  # Sidecar already set up
            max_cycles=2,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
            health_file=str(health_player),
        )

        self.assertEqual(p_result.status, P_STATUS_OK)
        self.assertEqual(p_result.cycles_completed, 2)
        self.assertEqual(p_result.rendered_count, 2)
        self.assertEqual(p_result.completed_pop_written_count, 2,
                         "Should write 2 completed PoP (one per item)")
        _assert_safe(self, format_kso_runtime_daemon_result(p_result))

        # Verify pending PoP file exists
        pending_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pending_file.exists(), "Pending PoP should exist after player cycles")
        pending_content = pending_file.read_text()
        self.assertIn("completed", pending_content)
        # Count completed events
        completed_count = pending_content.count("completed")
        self.assertGreaterEqual(completed_count, 2,
                                f"Expected >=2 completed events, got {completed_count}")

        # ═══ Phase 3: Sidecar picks up + sends completed PoP ═══════
        gw2 = FakeGatewayClient(
            manifest_responses=[_not_modified_response()],
        )
        http2 = FakeHttpClient()  # Default: accepted

        sc_result2 = run_kso_sidecar_daemon(
            str(self.root),
            gateway_client=gw2,
            http_client=http2,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            health_file=str(health_sidecar),
        )

        self.assertEqual(sc_result2.status, DAEMON_STATUS_STOPPED)
        self.assertGreaterEqual(sc_result2.pop_sent_count, 1,
                                "Should send at least 1 PoP batch")
        _assert_safe(self, format_kso_sidecar_daemon_result(sc_result2))

        # Verify pending is empty after rotation
        if pending_file.exists():
            remaining = pending_file.read_text().strip()
            self.assertEqual(remaining, "",
                             f"Pending should be empty after rotation: {remaining[:100]}")

        # Verify health files
        self.assertTrue(health_sidecar.exists())
        _assert_health_safe(self, health_sidecar)

        self.assertTrue(health_player.exists())
        _assert_health_safe(self, health_player)

    # ══════════════════════════════════════════════════════════════════
    # Negative scenarios
    # ══════════════════════════════════════════════════════════════════

    def test_sidecar_sync_fails_player_no_manifest(self):
        """Sidecar sync fails → player has no manifest → no PoP."""
        # Sidecar with gateway error
        gw1 = FakeGatewayClient(manifest_errors=[FakeHttpError("gateway down")])
        http1 = FakeHttpClient()

        sc_result = run_kso_sidecar_daemon(
            str(self.root), gw1, http1,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )
        self.assertGreaterEqual(sc_result.sync_error_count, 1)

        # Player daemon with no manifest
        fake_launcher = _make_fake_launcher()
        p_result = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
        )

        # Player should handle missing manifest gracefully
        self.assertEqual(p_result.completed_pop_written_count, 0,
                         "No PoP when no manifest")
        _assert_safe(self, format_kso_runtime_daemon_result(p_result))

    def test_state_changes_during_display(self):
        """State changes from idle during second display → only 1 completed PoP."""
        _create_root_with_state(self.root)

        # Phase 1: Sidecar sync
        gw1 = FakeGatewayClient()
        http1 = FakeHttpClient()
        run_kso_sidecar_daemon(
            str(self.root), gw1, http1,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )

        # Prepare state-changing sleep: after first render, change state to "pos"
        state_file = self.root / "state" / "kso_state.json"
        call_count = [0]

        def changing_sleep(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:  # After second sleep (first item displayed)
                state_file.write_text(_json.dumps({
                    "state": "pos",
                    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source": "ukm4_state_adapter",
                }))

        fake_launcher = _make_fake_launcher()
        p_result = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=2,
            sleep_fn=changing_sleep,
            process_launcher=fake_launcher,
            stale_seconds=5,
        )

        # First item completes fine, second hits hold (state=pos)
        self.assertLess(p_result.completed_pop_written_count, 2,
                        "State change should prevent second completed PoP")
        _assert_safe(self, format_kso_runtime_daemon_result(p_result))

    def test_sidecar_reject_pending_preserved(self):
        """Backend reject → pending preserved."""
        _create_root_with_state(self.root)

        # Phase 1: Sidecar sync
        gw1 = FakeGatewayClient()
        http1 = FakeHttpClient()
        run_kso_sidecar_daemon(
            str(self.root), gw1, http1,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )

        # Phase 2: Player writes completed PoP
        fake_launcher = _make_fake_launcher()
        run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
        )

        pending_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pending_file.exists())

        # Phase 3: Sidecar with reject
        gw2 = FakeGatewayClient(manifest_responses=[_not_modified_response()])
        http2 = FakeHttpClient(responses=[
            FakeHttpResponse(status_code=400, json_body={"status": "error"}),
        ])

        sc_result = run_kso_sidecar_daemon(
            str(self.root), gw2, http2,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )

        self.assertEqual(sc_result.pop_sent_count, 0,
                         "Reject → no sent")
        self.assertGreaterEqual(sc_result.pending_preserved_count, 1)

        # Pending still has the event
        self.assertTrue(pending_file.exists(), "Pending must survive reject")
        self.assertIn("completed", pending_file.read_text())
        _assert_safe(self, format_kso_sidecar_daemon_result(sc_result))

    def test_sidecar_network_error_pending_preserved(self):
        """Network error → pending preserved."""
        _create_root_with_state(self.root)

        # Phase 1: Sidecar sync
        gw1 = FakeGatewayClient()
        http1 = FakeHttpClient()
        run_kso_sidecar_daemon(
            str(self.root), gw1, http1,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )

        # Phase 2: Player writes completed PoP
        fake_launcher = _make_fake_launcher()
        run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
        )

        pending_file = self.root / "pop" / "pending" / "player_events.jsonl"
        self.assertTrue(pending_file.exists())

        # Phase 3: Sidecar with network error
        gw2 = FakeGatewayClient(manifest_responses=[_not_modified_response()])
        http2 = FakeHttpClient(errors=[FakeHttpError("connection refused")])

        sc_result = run_kso_sidecar_daemon(
            str(self.root), gw2, http2,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )

        self.assertEqual(sc_result.pop_sent_count, 0)
        self.assertGreaterEqual(sc_result.pop_error_count, 1)
        self.assertTrue(pending_file.exists(),
                        "Pending must survive network error")
        _assert_safe(self, format_kso_sidecar_daemon_result(sc_result))

    def test_no_resent_after_accepted(self):
        """Second send cycle does not resend already-sent events."""
        _create_root_with_state(self.root)

        # Phase 1: Sync
        gw1 = FakeGatewayClient()
        http1 = FakeHttpClient()
        run_kso_sidecar_daemon(
            str(self.root), gw1, http1,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )

        # Phase 2: Player writes PoP
        fake_launcher = _make_fake_launcher()
        run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
        )

        # Phase 3: Sidecar send (accepted)
        gw2 = FakeGatewayClient(manifest_responses=[_not_modified_response()])
        http2 = FakeHttpClient()
        sc1 = run_kso_sidecar_daemon(
            str(self.root), gw2, http2,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )
        self.assertGreaterEqual(sc1.pop_sent_count, 1,
                                "Should send on first cycle")

        # Phase 4: Second sidecar send → no resend
        gw3 = FakeGatewayClient(manifest_responses=[_not_modified_response()])
        http3 = FakeHttpClient()
        sc2 = run_kso_sidecar_daemon(
            str(self.root), gw3, http3,
            max_cycles=1, sleep_fn=_noop_sleep(),
        )
        self.assertEqual(sc2.pop_sent_count, 0,
                         "Should NOT resend already-sent events")
        _assert_safe(self, format_kso_sidecar_daemon_result(sc2))

    # ══════════════════════════════════════════════════════════════════
    # Safety checks
    # ══════════════════════════════════════════════════════════════════

    def test_all_results_repr_safe(self):
        """Every result repr is safe."""
        _create_root_with_state(self.root)

        # Sidecar sync
        sc1 = run_kso_sidecar_daemon(
            str(self.root), FakeGatewayClient(), FakeHttpClient(),
            max_cycles=1, sleep_fn=_noop_sleep(),
        )
        _assert_safe(self, repr(sc1))
        _assert_safe(self, format_kso_sidecar_daemon_result(sc1))

        # Player
        fake_launcher = _make_fake_launcher()
        p = run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
        )
        _assert_safe(self, repr(p))
        _assert_safe(self, format_kso_runtime_daemon_result(p))

        # Health file safety (sidecar max_cycles=0 still writes final health)
        health_sc = self.tmp / "sc-health.json"
        sc2 = run_kso_sidecar_daemon(
            str(self.root), FakeGatewayClient(), FakeHttpClient(),
            max_cycles=0, sleep_fn=_noop_sleep(),
            health_file=str(health_sc),
        )
        _assert_health_safe(self, health_sc)
        _assert_safe(self, repr(sc2))

        # Player health (needs at least 1 cycle to write)
        health_pl = self.tmp / "pl-health.json"
        run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
            health_file=str(health_pl),
        )
        _assert_health_safe(self, health_pl)

    def test_health_files_exist_after_e2e(self):
        """Health files exist and have expected structure after full E2E."""
        _create_root_with_state(self.root)
        health_sc = self.tmp / "sc-health.json"
        health_pl = self.tmp / "pl-health.json"

        # Full E2E
        run_kso_sidecar_daemon(
            str(self.root), FakeGatewayClient(), FakeHttpClient(),
            max_cycles=1, sleep_fn=_noop_sleep(),
            health_file=str(health_sc),
        )

        fake_launcher = _make_fake_launcher()
        run_kso_runtime_daemon(
            root=str(self.root),
            source_shell_dir=str(self.source_shell),
            runtime_shell_dir=str(self.runtime_shell),
            chromium_bin="fake-chromium",
            confirm_launch=True,
            confirm_display_completed=True,
            max_cycles=1,
            sleep_fn=_noop_sleep(),
            process_launcher=fake_launcher,
            health_file=str(health_pl),
        )

        # Both health files exist
        self.assertTrue(health_sc.exists(), "Sidecar health must exist")
        self.assertTrue(health_pl.exists(), "Player health must exist")

        # Structural check
        sc_data = _json.loads(health_sc.read_text())
        self.assertIn("status", sc_data)
        self.assertIn("cycles_completed", sc_data)
        self.assertIn("daemon_status", sc_data)

        pl_data = _json.loads(health_pl.read_text())
        self.assertIn("status", pl_data)
        self.assertIn("cycles_completed", pl_data)
        self.assertIn("rendered_count", pl_data)

        # Safety
        _assert_health_safe(self, health_sc)
        _assert_health_safe(self, health_pl)


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
