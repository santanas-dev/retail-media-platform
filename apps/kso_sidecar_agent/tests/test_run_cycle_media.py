"""Tests for run_cycle_media.py — fake HTTP server, no real backend."""

import hashlib as _hl
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.run_cycle import FORBIDDEN_SUBSTRINGS, RunCycleOptions
from kso_sidecar_agent.run_cycle_media import CycleMediaSyncResult, sync_media_for_cycle
from kso_sidecar_agent.token_state import TokenState

TOK = "opaque-value-1234567890"
TSEC = "dev-value-1234567890"
TDEV = "550e8400-e29b-41d4-a716-446655440000"
TCODE = "a-05954"
NOW = 1_750_000_000.0
MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "c" * 64
MID = "11111111-1111-1111-1111-111111111111"

TEST_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_PNG_SHA = _hl.sha256(TEST_PNG).hexdigest()
TEST_PNG_BAD = b"\x89PNG\r\n\x1a\n" + b"\xff" * 100
TEST_PNG_BAD_SHA = _hl.sha256(TEST_PNG_BAD).hexdigest()


def _vts():
    return TokenState(_access_token=TOK, token_type="bearer", expires_at=NOW + 3600,
                      device_id=TDEV, device_code=TCODE, status="active")


def _ets():
    return TokenState(_access_token=TOK, token_type="bearer", expires_at=NOW - 3600,
                      device_id=TDEV, device_code=TCODE, status="active")


def _ab():
    return json.dumps({"access_token": TOK, "token_type": "bearer", "expires_in": 3600,
                       "device_id": TDEV, "device_code": TCODE, "status": "active"}).encode()


def _sr(root, url, with_manifest=False):
    from kso_sidecar_agent.local_file_store import init_local_root as ir
    from kso_sidecar_agent.local_config import write_config as wc
    ir(root)
    wc(root, {"backend_base_url": url, "device_code": TCODE, "tls_verify": True,
              "request_timeout_sec": 10, "local_interface_version": "1.0"})
    from kso_sidecar_agent.secret_store import write_secret as ws
    ws(root, TSEC, dev_secret_store=True)
    if with_manifest:
        _write_local_manifest(root, sha=TEST_PNG_SHA)


def _write_local_manifest(root, sha=None, filename=None, size=None):
    """Write a valid local manifest to disk."""
    from kso_sidecar_agent.manifest_store import write_current_manifest
    from kso_sidecar_agent.manifest_client import ManifestSnapshot
    if sha is None:
        sha = TEST_PNG_SHA
    items = [{
        "id": MID, "sha256": sha,
        "media_path": f"media/{MID}.png",
        "duration_ms": 5000, "order": 0,
    }]
    snap = ManifestSnapshot(
        status="served", manifest_version_id=MVID, manifest_hash=MHASH,
        published_at="2026-06-19T10:00:00Z", items=items, source="current",
    )
    write_current_manifest(root, snap)


def _ss(hc, p=0):
    s = HTTPServer(("127.0.0.1", p), hc)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t, s.server_address[1]


class MediaSyncHandler(BaseHTTPRequestHandler):
    """Fake server: auth (POST) + manifest (GET) + media (GET with binary)."""
    MF_404: bool = False       # media returns 404
    MF_500: bool = False        # media returns 500
    MF_BAD_SHA: bool = False    # media returns wrong sha256 content
    MF_WRONG_CT: bool = False   # media returns wrong content-type
    MF_WRONG_SIZE: bool = False # media returns wrong size
    MC: int = 0  # media call count

    @classmethod
    def r(cls):
        cls.MF_404 = False
        cls.MF_500 = False
        cls.MF_BAD_SHA = False
        cls.MF_WRONG_CT = False
        cls.MF_WRONG_SIZE = False
        cls.MC = 0

    def lm(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_ab())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-gateway/manifest/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "served",
                "manifest_version_id": MVID,
                "manifest_hash": MHASH,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "items": [
                        {"id": MID, "sha256": TEST_PNG_SHA,
                         "media_path": f"media/{MID}.png",
                         "duration_ms": 5000, "order": 0}
                    ]
                },
            }).encode())
            return

        if self.path.startswith("/api/device-gateway/media/"):
            MediaSyncHandler.MC += 1

            if MediaSyncHandler.MF_404:
                self.send_response(404)
                self.end_headers()
                return
            if MediaSyncHandler.MF_500:
                self.send_response(500)
                self.end_headers()
                return

            content = TEST_PNG
            if MediaSyncHandler.MF_BAD_SHA:
                content = TEST_PNG_BAD
            if MediaSyncHandler.MF_WRONG_SIZE:
                content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

            ct = "image/png"
            if MediaSyncHandler.MF_WRONG_CT:
                ct = "image/jpeg"

            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_response(404)
        self.end_headers()


# ══════════════════════════════════════════════════════════════════════
# Tests: sync_media_for_cycle (unit)
# ══════════════════════════════════════════════════════════════════════

class TestSyncMediaForCycle(unittest.TestCase):
    def setUp(self):
        MediaSyncHandler.r()

    def test_media_downloaded(self):
        sv, _, p = _ss(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "ok")
                self.assertEqual(res.media_status, "complete")
                self.assertTrue(res.cache_complete)
                self.assertEqual(res.items_total, 1)
                self.assertEqual(res.items_downloaded, 1)
                self.assertEqual(MediaSyncHandler.MC, 1)

                # Verify file exists
                fp = Path(r) / "media" / "current" / f"{MID}.png"
                self.assertTrue(fp.exists())
                self.assertEqual(_hl.sha256(fp.read_bytes()).hexdigest(), TEST_PNG_SHA)
        finally:
            sv.shutdown()

    def test_existing_valid_skipped(self):
        sv, _, p = _ss(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                # Write valid media file first
                from kso_sidecar_agent.media_cache import ensure_media_dirs
                ensure_media_dirs(r)
                fp = Path(r) / "media" / "current" / f"{MID}.png"
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(TEST_PNG)

                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.media_status, "complete")
                self.assertTrue(res.cache_complete)
                self.assertEqual(res.items_cached, 1)
                self.assertEqual(res.items_downloaded, 0)
                self.assertEqual(MediaSyncHandler.MC, 0)  # no download
        finally:
            sv.shutdown()

    def test_missing_404(self):
        sv, _, p = _ss(MediaSyncHandler)
        MediaSyncHandler.MF_404 = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.media_status, "incomplete")
                self.assertFalse(res.cache_complete)
                self.assertEqual(res.items_missing, 1)
        finally:
            sv.shutdown()

    def test_media_500(self):
        sv, _, p = _ss(MediaSyncHandler)
        MediaSyncHandler.MF_500 = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.media_status, "incomplete")
                self.assertFalse(res.cache_complete)
                self.assertEqual(res.items_failed, 1)
        finally:
            sv.shutdown()

    def test_sha256_mismatch_not_written(self):
        sv, _, p = _ss(MediaSyncHandler)
        MediaSyncHandler.MF_BAD_SHA = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.media_status, "incomplete")
                self.assertFalse(res.cache_complete)
                self.assertEqual(res.items_failed, 1)
                # File should NOT be in current
                fp = Path(r) / "media" / "current" / f"{MID}.png"
                self.assertFalse(fp.exists())
        finally:
            sv.shutdown()

    def test_content_type_mismatch_not_written(self):
        sv, _, p = _ss(MediaSyncHandler)
        MediaSyncHandler.MF_WRONG_CT = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.media_status, "incomplete")
                self.assertFalse(res.cache_complete)
                self.assertEqual(res.items_failed, 1)
                fp = Path(r) / "media" / "current" / f"{MID}.png"
                self.assertFalse(fp.exists())
        finally:
            sv.shutdown()

    def test_size_mismatch_not_written(self):
        sv, _, p = _ss(MediaSyncHandler)
        MediaSyncHandler.MF_WRONG_SIZE = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.media_status, "incomplete")
                self.assertFalse(res.cache_complete)
                self.assertEqual(res.items_failed, 1)
        finally:
            sv.shutdown()

    def test_corrupted_existing_redownload_success(self):
        sv, _, p = _ss(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                from kso_sidecar_agent.media_cache import ensure_media_dirs
                ensure_media_dirs(r)
                # Write corrupted file
                fp = Path(r) / "media" / "current" / f"{MID}.png"
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(TEST_PNG_BAD)

                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertTrue(res.cache_complete)
                self.assertEqual(res.items_downloaded, 1)
                self.assertEqual(MediaSyncHandler.MC, 1)
                # Verify file now has correct content
                self.assertEqual(_hl.sha256(fp.read_bytes()).hexdigest(), TEST_PNG_SHA)
                # Corrupted file quarantined
                qp = Path(r) / "media" / "quarantine" / f"{MID}.png.bad"
                self.assertTrue(qp.exists())
        finally:
            sv.shutdown()

    def test_corrupted_existing_download_fails(self):
        sv, _, p = _ss(MediaSyncHandler)
        MediaSyncHandler.MF_500 = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                from kso_sidecar_agent.media_cache import ensure_media_dirs
                ensure_media_dirs(r)
                fp = Path(r) / "media" / "current" / f"{MID}.png"
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(TEST_PNG_BAD)

                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertFalse(res.cache_complete)
                self.assertEqual(res.items_failed, 1)
                self.assertEqual(res.items_cached, 0)
                # Corrupted should be quarantined
                qp = Path(r) / "media" / "quarantine" / f"{MID}.png.bad"
                self.assertTrue(qp.exists())
        finally:
            sv.shutdown()

    def test_no_download_leftover(self):
        sv, _, p = _ss(MediaSyncHandler)
        MediaSyncHandler.MF_500 = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                sync_media_for_cycle(r, ts, now=NOW)
                # No .download files left
                staging = Path(r) / "media" / "staging"
                if staging.is_dir():
                    for f in staging.iterdir():
                        self.assertFalse(f.name.endswith(".download"),
                                         f"Stale .download: {f.name}")
        finally:
            sv.shutdown()

    def test_expired_token(self):
        with tempfile.TemporaryDirectory() as r:
            _sr(r, "http://127.0.0.1:9999", with_manifest=True)
            ts = _ets()
            res = sync_media_for_cycle(r, ts, now=NOW)
            self.assertEqual(res.step.status, "error")
            self.assertEqual(res.media_status, "error")
            self.assertEqual(MediaSyncHandler.MC, 0)

    def test_no_manifest(self):
        sv, _, p = _ss(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")  # no manifest
                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertEqual(res.media_status, "error")
        finally:
            sv.shutdown()

    def test_no_token_in_step(self):
        sv, _, p = _ss(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_media_for_cycle(r, ts, now=NOW)
                st = str(res.step).lower()
                self.assertNotIn(TOK, st)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, st, f"Forbidden '{fb}' in media step")
        finally:
            sv.shutdown()


# ══════════════════════════════════════════════════════════════════════
# Tests: run_once with media
# ══════════════════════════════════════════════════════════════════════

class FullMediaHandler(BaseHTTPRequestHandler):
    """Fake server: auth + heartbeat + manifest + media."""
    AF: int | None = None
    HF: int | None = None
    MF: int | None = None
    MEDIA_404: bool = False
    MEDIA_500: bool = False

    @classmethod
    def r(cls):
        cls.AF = None
        cls.HF = None
        cls.MF = None
        cls.MEDIA_404 = False
        cls.MEDIA_500 = False

    def lm(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            if FullMediaHandler.AF:
                self.send_response(FullMediaHandler.AF)
                self.end_headers()
                self.wfile.write(b'{"error":"auth fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_ab())
            return
        if self.path == "/api/device-gateway/heartbeat":
            if FullMediaHandler.HF:
                self.send_response(FullMediaHandler.HF)
                self.end_headers()
                self.wfile.write(b'{"error":"hb fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "hb" + "1" * 32, "gateway_device_id": TDEV, "status": "ok"}).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-gateway/manifest/current":
            if FullMediaHandler.MF:
                self.send_response(FullMediaHandler.MF)
                self.end_headers()
                self.wfile.write(b'{"error":"manifest fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "served",
                "manifest_version_id": MVID, "manifest_hash": MHASH,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "items": [
                        {"id": MID, "sha256": TEST_PNG_SHA,
                         "media_path": f"media/{MID}.png",
                         "duration_ms": 5000, "order": 0}
                    ]
                },
            }).encode())
            return

        if self.path.startswith("/api/device-gateway/media/"):
            if FullMediaHandler.MEDIA_404:
                self.send_response(404)
                self.end_headers()
                return
            if FullMediaHandler.MEDIA_500:
                self.send_response(500)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(TEST_PNG)))
            self.end_headers()
            self.wfile.write(TEST_PNG)
            return

        # Runtime config fallback
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "config_hash": "a" * 64, "config": {"k": "v"},
                                      "generated_at": "2026-06-19T10:00:00Z"}).encode())


class TestRunOnceWithMedia(unittest.TestCase):
    def setUp(self):
        FullMediaHandler.r()

    def _fs(self, r, n):
        return next((s for s in r.steps if s.name == n), None)

    def test_run_once_media_complete(self):
        sv, _, p = _ss(FullMediaHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertTrue(res.media_cache_complete)
                self.assertEqual(res.media_items_total, 1)
                self.assertEqual(res.media_items_cached, 1)
                self.assertEqual(res.media_items_missing, 0)
                self.assertEqual(res.media_items_failed, 0)
                md = self._fs(res, "media")
                self.assertEqual(md.status, "ok")

                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                self.assertTrue(d["_cycle"]["media_cache_complete"])
                self.assertEqual(d["_cycle"]["media_items_total"], 1)
                # File exists
                fp = Path(r) / "media" / "current" / f"{MID}.png"
                self.assertTrue(fp.exists())
        finally:
            sv.shutdown()

    def test_auth_fail_media_skipped(self):
        sv, _, p = _ss(FullMediaHandler)
        FullMediaHandler.AF = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.last_auth_status, "error")
                md = self._fs(res, "media")
                self.assertEqual(md.status, "skipped")
        finally:
            sv.shutdown()

    def test_media_404_warning(self):
        sv, _, p = _ss(FullMediaHandler)
        FullMediaHandler.MEDIA_404 = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertFalse(res.media_cache_complete)
                self.assertEqual(res.media_items_missing, 1)
                md = self._fs(res, "media")
                self.assertEqual(md.status, "warning")
        finally:
            sv.shutdown()

    def test_media_500_warning(self):
        sv, _, p = _ss(FullMediaHandler)
        FullMediaHandler.MEDIA_500 = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertFalse(res.media_cache_complete)
                self.assertEqual(res.media_items_failed, 1)
        finally:
            sv.shutdown()

    def test_no_token_in_agent_status(self):
        sv, _, p = _ss(FullMediaHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                ro(r, options=opts)
                dp = Path(r) / "status" / "agent_status.json"
                ds = json.dumps(json.loads(dp.read_text())).lower()
                self.assertNotIn(TOK, ds)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, ds, f"Forbidden '{fb}' in agent_status")
        finally:
            sv.shutdown()

    def test_local_only_no_media_sync(self):
        sv, _, p = _ss(FullMediaHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                res = ro(r, options=opts)
                md = self._fs(res, "media_cache")
                self.assertIsNotNone(md)
                self.assertEqual(md.status, "skipped")  # no manifest → skipped
        finally:
            sv.shutdown()

    def test_no_forbidden_in_media_safe_details(self):
        sv, _, p = _ss(FullMediaHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                md = self._fs(res, "media")
                sd = str(md.safe_details).lower()
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, sd, f"Forbidden '{fb}' in media safe_details")
        finally:
            sv.shutdown()


if __name__ == "__main__":
    unittest.main()
