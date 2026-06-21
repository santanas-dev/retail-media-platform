"""E2E Local Delivery Smoke — sidecar sync → player pipeline.

Full local path: fake gateway → sidecar kso-sync-once / sync core
→ local manifest + media → player reads safe manifest → player builds render snapshot.

No real backend, no Chromium, no systemd, no PoP write, no installer.
"""

# ── Cross-package import support ─────────────────────────────────────────
# The player package has no pyproject.toml/setup.py yet — it's imported
# via PYTHONPATH. Add it here so tests in the sidecar workspace can import it.
import os as _os
import sys as _sys

_PLAYER_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "kso_player")
_PLAYER_DIR = _os.path.abspath(_PLAYER_DIR)
if _PLAYER_DIR not in _sys.path:
    _sys.path.insert(0, _PLAYER_DIR)

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kso_sidecar_agent.kso_manifest_media_sync import (
    KsoMediaDownloadResponse,
    STATUS_OK as SYNC_STATUS_OK,
    STATUS_ERROR,
    STATUS_NOT_MODIFIED,
    REASON_SYNCED,
    REASON_MEDIA_DOWNLOAD_FAILED,
    REASON_CONTENT_TYPE_MISMATCH,
    sync_kso_manifest_and_media,
)

from kso_player.runtime_gate import (
    evaluate_kso_runtime_gate,
    ACTION_PLAY as GATE_PLAY,
    ACTION_HOLD as GATE_HOLD,
    REASON_PLAY_ALLOWED as GATE_REASON_OK,
    STATUS_OK as GATE_STATUS_OK,
)

from kso_player.playlist import (
    build_playlist,
    REASON_READY as PL_READY,
)

from kso_player.render_plan import (
    build_kso_render_plan,
    RENDER_ACTION_RENDER as RP_RENDER,
    RENDER_ACTION_HOLD as RP_HOLD,
)

from kso_player.shell_snapshot import (
    build_kso_shell_snapshot,
    SNAPSHOT_MODE_RENDER as SS_RENDER,
    SNAPSHOT_MODE_HOLD as SS_HOLD,
    SNAPSHOT_METHOD_SET_RENDER_PLAN as SS_RENDER_METHOD,
)


# ══════════════════════════════════════════════════════════════════════
# Fake gateway
# ══════════════════════════════════════════════════════════════════════

_PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_JPEG_BODY = b"\xff\xd8\xff\xe0" + b"\x01" * 200


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
            raise RuntimeError("simulated download failure for " + media_ref[:10])
        resp = self.media_map.get(media_ref)
        if resp is None:
            return KsoMediaDownloadResponse(
                status=STATUS_ERROR,
                content_type="",
                content_length=0,
                body=b"",
            )
        return resp


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


def _make_served_response(items=None):
    if items is None:
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
    manifest = {
        "schemaVersion": 1,
        "generatedAt": "2026-06-19T10:00:00Z",
        "channel": "kso",
        "storeCode": "safe_store",
        "deviceCode": "safe_device",
        "items": items,
    }
    return {
        "status": "served",
        "manifest": manifest,
    }


def _make_png_dl(body=_PNG_BODY):
    return KsoMediaDownloadResponse(
        status=SYNC_STATUS_OK,
        content_type="image/png",
        content_length=len(body),
        body=body,
    )


def _make_jpeg_dl(body=_JPEG_BODY):
    return KsoMediaDownloadResponse(
        status=SYNC_STATUS_OK,
        content_type="image/jpeg",
        content_length=len(body),
        body=body,
    )


def _make_error_dl():
    return KsoMediaDownloadResponse(
        status=STATUS_ERROR,
        content_type="",
        content_length=0,
        body=b"",
    )


def _make_ct_mismatch_dl():
    """Return image/jpeg when image/png expected."""
    return KsoMediaDownloadResponse(
        status=SYNC_STATUS_OK,
        content_type="image/jpeg",
        content_length=len(_JPEG_BODY),
        body=_JPEG_BODY,
    )


# ══════════════════════════════════════════════════════════════════════
# Happy path E2E
# ══════════════════════════════════════════════════════════════════════

class TestKsoE2ELocalDeliverySmoke(unittest.TestCase):
    """Sidecar sync → player pipeline E2E smoke."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_e2e_"))
        self.root = self.tmp

        # Create state directory with idle state
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        state = _make_idle_state()
        (self.root / "state" / "kso_state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── Happy path ───────────────────────────────────────────────────

    def test_full_e2e_sync_then_player_pipeline(self):
        """Sidecar sync + player pipeline: manifests → media → render snapshot."""
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
        manifest_resp = _make_served_response(items)
        media_map = {"media/current/slot-000": _make_png_dl()}
        gw = FakeE2EGateway(manifest_response=manifest_resp, media_map=media_map)

        # ── Sidecar sync ──
        result = sync_kso_manifest_and_media(self.root, gw)
        self.assertEqual(result.status, SYNC_STATUS_OK)
        self.assertTrue(result.manifest_written)
        self.assertEqual(result.media_written_count, 1)
        self.assertEqual(result.items_count, 1)
        self.assertEqual(result.reason, REASON_SYNCED)

        # Verify local files
        manifest_path = self.root / "manifest" / "current_manifest.json"
        self.assertTrue(manifest_path.exists(), "Manifest file must exist")
        media_path = self.root / "media" / "current" / "slot-000"
        self.assertTrue(media_path.exists(), "Media file must exist")

        # Manifest is safe body only — no gateway wrapper
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn("status", manifest_data,
                         "Manifest must NOT contain gateway wrapper 'status'")
        self.assertNotIn("manifest", manifest_data,
                         "Manifest must NOT contain nested 'manifest' key")
        self.assertEqual(manifest_data["channel"], "kso")
        self.assertEqual(manifest_data["schemaVersion"], 1)

        # ── Player pipeline ──

        # 1. Runtime gate
        gate = evaluate_kso_runtime_gate(self.root)
        self.assertEqual(gate.action, GATE_PLAY)
        self.assertEqual(gate.status, GATE_STATUS_OK)
        self.assertEqual(gate.reason, GATE_REASON_OK)

        # 2. Playlist
        playlist = build_playlist(self.root)
        self.assertTrue(playlist.ready)
        self.assertEqual(playlist.status, "ready")
        self.assertEqual(playlist.reason, PL_READY)
        self.assertEqual(playlist.items_total, 1)
        self.assertEqual(playlist.items_ready, 1)
        self.assertEqual(len(playlist.items), 1)

        # 3. Render plan
        plan = build_kso_render_plan(self.root)
        self.assertEqual(plan.render_action, RP_RENDER)

        # 4. Shell snapshot
        snapshot = build_kso_shell_snapshot(self.root)
        self.assertEqual(snapshot.snapshot_mode, SS_RENDER)
        self.assertEqual(snapshot.shell_method, SS_RENDER_METHOD)

        # Safe output — no raw paths/IDs/hashes
        out = repr(result)
        self._assert_safe_output(out)

    def test_e2e_player_reads_local_manifest_directly(self):
        """Player reads manifest written by sidecar sync."""
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_png_dl()},
        )

        sync_result = sync_kso_manifest_and_media(self.root, gw)
        self.assertEqual(sync_result.status, SYNC_STATUS_OK)

        # Player builds playlist from the local manifest
        playlist = build_playlist(self.root)
        self.assertTrue(playlist.ready)
        self.assertEqual(playlist.items_total, 1)
        self.assertEqual(playlist.items[0].slot_order, 0)
        self.assertEqual(playlist.items[0].content_type, "image/png")
        self.assertEqual(playlist.items[0].duration_ms, 5000)

    def test_e2e_with_empty_items(self):
        """Sync with empty items — manifest written, no media."""
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items=[]),
            media_map={},
        )

        result = sync_kso_manifest_and_media(self.root, gw)
        self.assertEqual(result.status, SYNC_STATUS_OK)
        self.assertTrue(result.manifest_written)
        self.assertEqual(result.media_written_count, 0)
        self.assertEqual(result.items_count, 0)

        manifest_path = self.root / "manifest" / "current_manifest.json"
        self.assertTrue(manifest_path.exists())

        # Player: no items → not ready
        playlist = build_playlist(self.root)
        self.assertFalse(playlist.ready)
        self.assertEqual(playlist.reason, "no_media_items")

    def test_e2e_not_modified_no_op(self):
        """Not modified status → no files written."""
        resp = {"status": "not_modified", "manifest": None}
        gw = FakeE2EGateway(manifest_response=resp, media_map={})

        result = sync_kso_manifest_and_media(self.root, gw)
        self.assertEqual(result.status, STATUS_NOT_MODIFIED)

        # No files written
        manifest_path = self.root / "manifest" / "current_manifest.json"
        self.assertFalse(manifest_path.exists())

    # ── Negative: media failure ───────────────────────────────────────

    def test_media_download_failure_no_manifest_published(self):
        """Media download error → manifest NOT published."""
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_error_dl()},
        )

        result = sync_kso_manifest_and_media(self.root, gw)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_MEDIA_DOWNLOAD_FAILED)

        # Manifest NOT published
        manifest_path = self.root / "manifest" / "current_manifest.json"
        self.assertFalse(
            manifest_path.exists(),
            "Manifest must NOT be published when media download fails",
        )

        # Player remains hold — no manifest
        gate = evaluate_kso_runtime_gate(self.root)
        self.assertEqual(gate.action, GATE_PLAY, "Gate depends on state, not manifest")

        playlist = build_playlist(self.root)
        self.assertFalse(playlist.ready)
        self.assertEqual(playlist.reason, "manifest_missing")

        plan = build_kso_render_plan(self.root)
        self.assertEqual(plan.render_action, RP_HOLD)

    def test_media_failure_preserves_old_manifest(self):
        """Old manifest preserved when second sync media fails."""
        # First: successful sync
        items1 = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
        gw1 = FakeE2EGateway(
            manifest_response=_make_served_response(items1),
            media_map={"media/current/slot-000": _make_png_dl()},
        )
        result1 = sync_kso_manifest_and_media(self.root, gw1)
        self.assertEqual(result1.status, SYNC_STATUS_OK)

        old_manifest = (self.root / "manifest" / "current_manifest.json").read_text()

        # Second: media failure
        items2 = [{
            "slotOrder": 0,
            "contentType": "image/jpeg",
            "durationMs": 3000,
            "mediaRef": "media/current/slot-000",
        }]
        gw2 = FakeE2EGateway(
            manifest_response=_make_served_response(items2),
            media_map={"media/current/slot-000": _make_error_dl()},
        )
        result2 = sync_kso_manifest_and_media(self.root, gw2)
        self.assertEqual(result2.status, STATUS_ERROR)
        self.assertEqual(result2.reason, REASON_MEDIA_DOWNLOAD_FAILED)

        # Old manifest preserved
        current = (self.root / "manifest" / "current_manifest.json").read_text()
        self.assertEqual(current, old_manifest,
                         "Old manifest must be preserved after media failure")

    # ── Negative: content-type mismatch ───────────────────────────────

    def test_content_type_mismatch_no_manifest_published(self):
        """Content-type mismatch → manifest NOT published."""
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",  # expected
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_ct_mismatch_dl()},
        )

        result = sync_kso_manifest_and_media(self.root, gw)
        self.assertEqual(result.status, STATUS_ERROR)
        self.assertEqual(result.reason, REASON_CONTENT_TYPE_MISMATCH)

        manifest_path = self.root / "manifest" / "current_manifest.json"
        self.assertFalse(
            manifest_path.exists(),
            "Manifest must NOT be published on content-type mismatch",
        )

        # Player remains hold
        playlist = build_playlist(self.root)
        self.assertFalse(playlist.ready)
        self.assertEqual(playlist.reason, "manifest_missing")

    def test_content_type_mismatch_preserves_old_manifest(self):
        """Old manifest preserved when second sync has content-type mismatch."""
        # First: successful sync
        gw1 = FakeE2EGateway(
            manifest_response=_make_served_response([{
                "slotOrder": 0, "contentType": "image/png",
                "durationMs": 5000, "mediaRef": "media/current/slot-000",
            }]),
            media_map={"media/current/slot-000": _make_png_dl()},
        )
        result1 = sync_kso_manifest_and_media(self.root, gw1)
        self.assertEqual(result1.status, SYNC_STATUS_OK)

        old_manifest = (self.root / "manifest" / "current_manifest.json").read_text()

        # Second: content-type mismatch
        gw2 = FakeE2EGateway(
            manifest_response=_make_served_response([{
                "slotOrder": 0, "contentType": "image/png",
                "durationMs": 3000, "mediaRef": "media/current/slot-000",
            }]),
            media_map={"media/current/slot-000": _make_ct_mismatch_dl()},
        )
        result2 = sync_kso_manifest_and_media(self.root, gw2)
        self.assertEqual(result2.status, STATUS_ERROR)
        self.assertEqual(result2.reason, REASON_CONTENT_TYPE_MISMATCH)

        current = (self.root / "manifest" / "current_manifest.json").read_text()
        self.assertEqual(current, old_manifest)

    # ── Gate only — state/no-manifest boundary ────────────────────────

    def test_gate_play_manifest_missing_player_hold(self):
        """Gate allows play (state=idle) but player holds because no manifest."""
        gate = evaluate_kso_runtime_gate(self.root)
        self.assertEqual(gate.action, GATE_PLAY)

        playlist = build_playlist(self.root)
        self.assertFalse(playlist.ready)
        self.assertEqual(playlist.reason, "manifest_missing")

        plan = build_kso_render_plan(self.root)
        self.assertEqual(plan.render_action, RP_HOLD)

        snapshot = build_kso_shell_snapshot(self.root)
        self.assertEqual(snapshot.snapshot_mode, SS_HOLD)

    # ── Output safety ─────────────────────────────────────────────────

    def _assert_safe_output(self, output: str):
        """Verify output contains NO forbidden substrings."""
        lower = output.lower()
        # Only check for actual mediaRef VALUES, not field names
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

    def test_sync_result_repr_safe(self):
        """Sync result repr contains no forbidden strings."""
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_png_dl()},
        )
        result = sync_kso_manifest_and_media(self.root, gw)
        self._assert_safe_output(repr(result))

    def test_render_plan_repr_safe(self):
        """Render plan repr contains no forbidden strings."""
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_png_dl()},
        )
        sync_kso_manifest_and_media(self.root, gw)

        plan = build_kso_render_plan(self.root)
        self._assert_safe_output(repr(plan))

    def test_shell_snapshot_repr_safe(self):
        """Shell snapshot repr contains no forbidden strings."""
        items = [{
            "slotOrder": 0,
            "contentType": "image/png",
            "durationMs": 5000,
            "mediaRef": "media/current/slot-000",
        }]
        gw = FakeE2EGateway(
            manifest_response=_make_served_response(items),
            media_map={"media/current/slot-000": _make_png_dl()},
        )
        sync_kso_manifest_and_media(self.root, gw)

        snapshot = build_kso_shell_snapshot(self.root)
        self._assert_safe_output(repr(snapshot))
