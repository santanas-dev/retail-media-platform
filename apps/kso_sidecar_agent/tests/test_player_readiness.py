"""Tests for player_readiness.py — local only, no backend, no secret."""

import hashlib as _hl
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kso_sidecar_agent.player_readiness import (
    PlayerReadinessSnapshot,
    build_player_readiness_snapshot,
    REASON_READY,
    REASON_MANIFEST_MISSING,
    REASON_MANIFEST_INVALID,
    REASON_MEDIA_INCOMPLETE,
    REASON_MEDIA_CORRUPTED,
    REASON_NO_MEDIA_ITEMS,
)

PKG_DIR = Path(__file__).resolve().parent.parent

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
PNG_SHA = _hl.sha256(PNG).hexdigest()
MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "c" * 64
MID = "11111111-1111-1111-1111-111111111111"

FORBIDDEN = {"token", "jwt", "password", "secret", "api_key",
             "private_key", "payment_card", "receipt", "local_path",
             "file_path", "authorization", "bearer", "device_secret",
             "access_token", "media_path", "creatives/",
             "backend_base_url", "127.0.0.1", "device_code"}


def _setup(root, with_manifest=False, with_media=False, with_cycle=None):
    from kso_sidecar_agent.local_file_store import init_local_root
    from kso_sidecar_agent.local_config import write_config
    init_local_root(root)
    write_config(root, {"backend_base_url": "http://127.0.0.1:8080", "device_code": "a-05954",
                        "tls_verify": True, "request_timeout_sec": 10, "local_interface_version": "1.0"})
    if with_manifest:
        from kso_sidecar_agent.manifest_store import write_current_manifest
        from kso_sidecar_agent.manifest_client import ManifestSnapshot
        items = [{"id": MID, "sha256": PNG_SHA, "media_path": f"media/{MID}.png",
                  "duration_ms": 5000, "order": 0}]
        snap = ManifestSnapshot(status="served", manifest_version_id=MVID, manifest_hash=MHASH,
                                published_at="2026-06-19T10:00:00Z", items=items, source="current")
        write_current_manifest(root, snap)
    if with_media:
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        ensure_media_dirs(root)
        fp = Path(root) / "media" / "current" / f"{MID}.png"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(PNG)
    if with_cycle:
        from kso_sidecar_agent.atomic_io import atomic_write_json
        dp = Path(root) / "status" / "agent_status.json"
        dp.parent.mkdir(parents=True, exist_ok=True)
        existing = {"status": "running"}
        existing["_cycle"] = with_cycle
        atomic_write_json(dp, existing)


def _run(*args):
    r = subprocess.run([sys.executable, "-m", "kso_sidecar_agent.cli", *args],
                       capture_output=True, text=True, cwd=str(PKG_DIR))
    return r.returncode, r.stdout, r.stderr


def _no_forbidden(self, text, label=""):
    lower = text.lower()
    for fb in FORBIDDEN:
        self.assertNotIn(fb, lower, f"Forbidden '{fb}' in {label}")


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestPlayerReadiness(unittest.TestCase):

    def test_full_ready(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True, with_media=True)
            snap = build_player_readiness_snapshot(r)
            self.assertTrue(snap.ready)
            self.assertTrue(snap.can_play_local_content)
            self.assertEqual(snap.reason, REASON_READY)
            self.assertEqual(snap.media_items_total, 1)
            self.assertEqual(snap.media_items_cached, 1)

    def test_manifest_missing(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r)
            snap = build_player_readiness_snapshot(r)
            self.assertFalse(snap.ready)
            self.assertEqual(snap.reason, REASON_MANIFEST_MISSING)

    def test_manifest_invalid(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r)
            mf = Path(r) / "manifest" / "current_manifest.json"
            mf.parent.mkdir(parents=True, exist_ok=True)
            mf.write_text("not valid json {{\"broken\"")
            snap = build_player_readiness_snapshot(r)
            self.assertFalse(snap.ready)
            self.assertEqual(snap.reason, REASON_MANIFEST_INVALID)

    def test_media_missing(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True)  # no media
            snap = build_player_readiness_snapshot(r)
            self.assertFalse(snap.ready)
            self.assertEqual(snap.reason, REASON_MEDIA_INCOMPLETE)

    def test_media_corrupted(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True)
            from kso_sidecar_agent.media_cache import ensure_media_dirs
            ensure_media_dirs(r)
            fp = Path(r) / "media" / "current" / f"{MID}.png"
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(b"corrupted")
            snap = build_player_readiness_snapshot(r)
            self.assertFalse(snap.ready)
            self.assertEqual(snap.reason, REASON_MEDIA_CORRUPTED)

    def test_no_media_items(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True)
            # Write manifest with 0 items
            from kso_sidecar_agent.manifest_store import write_current_manifest
            from kso_sidecar_agent.manifest_client import ManifestSnapshot
            snap_empty = ManifestSnapshot(status="served", manifest_version_id=MVID,
                                          manifest_hash=MHASH,
                                          published_at="2026-06-19T10:00:00Z",
                                          items=[], source="current")
            write_current_manifest(r, snap_empty)
            snap = build_player_readiness_snapshot(r)
            self.assertFalse(snap.ready)
            self.assertEqual(snap.reason, REASON_NO_MEDIA_ITEMS)

    def test_degraded_cycle_ready(self):
        """Degraded cycle with complete cache → ready=true."""
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True, with_media=True,
                   with_cycle={"last_cycle_status": "degraded",
                               "offline_ready": True,
                               "can_play_local_content": True})
            snap = build_player_readiness_snapshot(r)
            self.assertTrue(snap.ready)
            self.assertEqual(snap.last_cycle_status, "degraded")
            self.assertTrue(snap.offline_ready)

    def test_cycle_can_play_but_media_missing(self):
        """_cycle.can_play_local_content=true but actual media missing → NOT ready."""
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True,  # no media
                   with_cycle={"last_cycle_status": "degraded",
                               "can_play_local_content": True})
            snap = build_player_readiness_snapshot(r)
            self.assertFalse(snap.ready)
            self.assertEqual(snap.reason, REASON_MEDIA_INCOMPLETE)

    # ── CLI ───────────────────────────────────────────────────────

    def test_cli_ready_exit_0(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True, with_media=True)
            rc, out, err = _run("player-readiness", "--root", r)
            self.assertEqual(rc, 0, f"stderr: {err}")
            self.assertIn("player_ready:           true", out)

    def test_cli_not_ready_exit_1(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r)  # no manifest
            rc, out, err = _run("player-readiness", "--root", r)
            self.assertEqual(rc, 1)
            self.assertIn("player_ready:           false", out)

    def test_cli_no_backend_calls(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True, with_media=True)
            rc, out, err = _run("player-readiness", "--root", r)
            # No auth, no secret, no HTTP errors
            self.assertNotIn("auth", out.lower())
            self.assertNotIn("secret", out.lower())
            self.assertNotIn("connection refused", err.lower())

    def test_cli_no_forbidden(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, with_manifest=True, with_media=True)
            rc, out, err = _run("player-readiness", "--root", r)
            _no_forbidden(self, out, "stdout")
            _no_forbidden(self, err, "stderr")


if __name__ == "__main__":
    unittest.main()
