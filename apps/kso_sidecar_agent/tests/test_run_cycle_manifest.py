"""Tests for run_cycle_manifest.py — fake HTTP server, no real backend."""

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.run_cycle import FORBIDDEN_SUBSTRINGS, RunCycleOptions
from kso_sidecar_agent.run_cycle_manifest import CycleManifestResult, sync_manifest_for_cycle
from kso_sidecar_agent.token_state import TokenState

TOK = "opaque-value-1234567890"
TSEC = "dev-value-1234567890"
TDEV = "550e8400-e29b-41d4-a716-446655440000"
TCODE = "a-05954"
NOW = 1_750_000_000.0
MVERS = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "c" * 64
MITEM = "11111111-1111-1111-1111-111111111111"
M_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _vts():
    return TokenState(_access_token=TOK, token_type="bearer", expires_at=NOW + 3600,
                      device_id=TDEV, device_code=TCODE, status="active")


def _ets():
    return TokenState(_access_token=TOK, token_type="bearer", expires_at=NOW - 3600,
                      device_id=TDEV, device_code=TCODE, status="active")


def _ab():
    return json.dumps({"access_token": TOK, "token_type": "bearer", "expires_in": 3600,
                       "device_id": TDEV, "device_code": TCODE, "status": "active"}).encode()


def _valid_manifest_body():
    return json.dumps({
        "status": "served",
        "manifest_version_id": MVERS,
        "manifest_hash": MHASH,
        "published_at": "2026-06-19T10:00:00Z",
        "manifest": {
            "items": [
                {"id": MITEM, "sha256": M_SHA, "media_path": f"media/{MITEM}.png",
                 "duration_ms": 5000, "order": 0}
            ]
        },
    }).encode()


def _sr(root, url, sec=True, with_manifest=False):
    from kso_sidecar_agent.local_file_store import init_local_root as ir
    from kso_sidecar_agent.local_config import write_config as wc
    ir(root)
    wc(root, {"backend_base_url": url, "device_code": TCODE, "tls_verify": True,
              "request_timeout_sec": 10, "local_interface_version": "1.0"})
    if sec:
        from kso_sidecar_agent.secret_store import write_secret as ws
        ws(root, TSEC, dev_secret_store=True)
    if with_manifest:
        from kso_sidecar_agent.manifest_store import write_current_manifest
        from kso_sidecar_agent.manifest_client import ManifestSnapshot
        snap = ManifestSnapshot(
            status="served",
            manifest_version_id=MVERS,
            manifest_hash=MHASH,
            published_at="2026-06-19T10:00:00Z",
            items=[{"id": MITEM, "sha256": M_SHA, "media_path": f"media/{MITEM}.png",
                    "duration_ms": 5000, "order": 0}],
            source="current",
        )
        write_current_manifest(root, snap)


def _ss(hc, p=0):
    s = HTTPServer(("127.0.0.1", p), hc)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t, s.server_address[1]


class MfHandler(BaseHTTPRequestHandler):
    """Fake server: auth (POST) + manifest (GET)."""
    MF: int | None = None       # force manifest fail (status code or None)
    MF_NO_MOD: bool = False     # return not_modified
    MF_NO_MF: bool = False      # return no_manifest
    MF_INVALID_JSON: bool = False
    MF_FORBIDDEN: bool = False  # forbidden key in manifest
    MF_INVALID_SHA: bool = False  # invalid sha256
    MF_UNSAFE_PATH: bool = False  # unsafe media_path
    MC: int = 0  # manifest GET call count

    @classmethod
    def r(cls):
        cls.MF = None
        cls.MF_NO_MOD = False
        cls.MF_NO_MF = False
        cls.MF_INVALID_JSON = False
        cls.MF_FORBIDDEN = False
        cls.MF_INVALID_SHA = False
        cls.MF_UNSAFE_PATH = False
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
            MfHandler.MC += 1

            if MfHandler.MF:
                self.send_response(MfHandler.MF)
                self.end_headers()
                self.wfile.write(b'{"error":"manifest fail"}')
                return

            if MfHandler.MF_NO_MOD:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "not_modified",
                    "manifest_version_id": MVERS,
                }).encode())
                return

            if MfHandler.MF_NO_MF:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "no_manifest"}).encode())
                return

            if MfHandler.MF_INVALID_JSON:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>not json</html>")
                return

            if MfHandler.MF_FORBIDDEN:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "served",
                    "manifest_version_id": MVERS,
                    "manifest_hash": MHASH,
                    "manifest": {
                        "token": "forbidden-value",
                        "items": [
                            {"id": MITEM, "sha256": M_SHA, "media_path": f"media/{MITEM}.png",
                             "duration_ms": 5000, "order": 0}
                        ],
                    },
                }).encode())
                return

            if MfHandler.MF_INVALID_SHA:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "served",
                    "manifest_version_id": MVERS,
                    "manifest_hash": MHASH,
                    "manifest": {
                        "items": [
                            {"id": MITEM, "sha256": "bad",
                             "media_path": f"media/{MITEM}.png",
                             "duration_ms": 5000, "order": 0}
                        ],
                    },
                }).encode())
                return

            if MfHandler.MF_UNSAFE_PATH:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "served",
                    "manifest_version_id": MVERS,
                    "manifest_hash": MHASH,
                    "manifest": {
                        "items": [
                            {"id": MITEM, "sha256": M_SHA,
                             "media_path": "../../../etc/passwd",
                             "duration_ms": 5000, "order": 0}
                        ],
                    },
                }).encode())
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_valid_manifest_body())
            return

        self.send_response(404)
        self.end_headers()


# ══════════════════════════════════════════════════════════════════════
# Tests: sync_manifest_for_cycle (unit)
# ══════════════════════════════════════════════════════════════════════

class TestSyncManifestForCycle(unittest.TestCase):
    def setUp(self):
        MfHandler.r()

    def test_manifest_served(self):
        sv, _, p = _ss(MfHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "ok")
                self.assertEqual(res.manifest_status, "updated")
                self.assertEqual(res.items_count, 1)
                self.assertEqual(MfHandler.MC, 1)

                # Verify file was written
                mp = Path(r) / "manifest" / "current_manifest.json"
                self.assertTrue(mp.exists())
                data = json.loads(mp.read_text())
                self.assertEqual(data["manifest_version_id"], MVERS)
                self.assertEqual(len(data["items"]), 1)
        finally:
            sv.shutdown()

    def test_manifest_not_modified(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF_NO_MOD = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "ok")
                self.assertEqual(res.manifest_status, "not_modified")
                self.assertTrue(res.step.safe_details.get("not_modified"))
        finally:
            sv.shutdown()

    def test_manifest_no_manifest_no_local(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF_NO_MF = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "ok")
                self.assertEqual(res.manifest_status, "no_manifest")
                self.assertTrue(res.step.safe_details.get("no_manifest"))
        finally:
            sv.shutdown()

    def test_manifest_no_manifest_existing_preserved(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF_NO_MF = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.manifest_status, "no_manifest")
                # Existing manifest preserved
                mp = Path(r) / "manifest" / "current_manifest.json"
                self.assertTrue(mp.exists())
        finally:
            sv.shutdown()

    def test_manifest_500_error(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertFalse(res.step.fatal)
                self.assertEqual(res.manifest_status, "error")
        finally:
            sv.shutdown()

    def test_manifest_403(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF = 403
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertFalse(res.step.fatal)
        finally:
            sv.shutdown()

    def test_invalid_json_response(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF_INVALID_JSON = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
        finally:
            sv.shutdown()

    def test_forbidden_key_rejected(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF_FORBIDDEN = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertEqual(res.manifest_status, "error")
                # File should NOT be written
                mp = Path(r) / "manifest" / "current_manifest.json"
                self.assertFalse(mp.exists())
        finally:
            sv.shutdown()

    def test_invalid_sha256_rejected(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF_INVALID_SHA = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertEqual(res.manifest_status, "error")
        finally:
            sv.shutdown()

    def test_unsafe_media_path_rejected(self):
        sv, _, p = _ss(MfHandler)
        MfHandler.MF_UNSAFE_PATH = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertEqual(res.manifest_status, "error")
        finally:
            sv.shutdown()

    def test_expired_token(self):
        with tempfile.TemporaryDirectory() as r:
            _sr(r, "http://127.0.0.1:9999")
            ts = _ets()
            res = sync_manifest_for_cycle(r, ts, now=NOW)
            self.assertEqual(res.step.status, "error")
            self.assertEqual(res.manifest_status, "error")
            self.assertEqual(MfHandler.MC, 0)

    def test_no_token_in_step(self):
        sv, _, p = _ss(MfHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = sync_manifest_for_cycle(r, ts, now=NOW)
                st = str(res.step).lower()
                self.assertNotIn(TOK, st)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, st, f"Forbidden '{fb}' in manifest step")
        finally:
            sv.shutdown()


# ══════════════════════════════════════════════════════════════════════
# Tests: run_once with manifest
# ══════════════════════════════════════════════════════════════════════

class FullHandler(BaseHTTPRequestHandler):
    """Fake server: auth + heartbeat + manifest + report."""
    AF: int | None = None
    HF: int | None = None
    MF: int | None = None
    RF: int | None = None

    @classmethod
    def r(cls):
        cls.AF = None
        cls.HF = None
        cls.MF = None
        cls.RF = None

    def lm(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            if FullHandler.AF:
                self.send_response(FullHandler.AF)
                self.end_headers()
                self.wfile.write(b'{"error":"auth fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_ab())
            return
        if self.path == "/api/device-gateway/heartbeat":
            if FullHandler.HF:
                self.send_response(FullHandler.HF)
                self.end_headers()
                self.wfile.write(b'{"error":"hb fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "hb" + "1" * 32, "gateway_device_id": TDEV, "status": "ok"}).encode())
            return
        if self.path == "/api/device-gateway/media/cache/report":
            if FullHandler.RF:
                self.send_response(FullHandler.RF)
                self.end_headers()
                self.wfile.write(b'{"error":"report fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok", "manifest_version_id": MVERS,
                "gateway_device_id": TDEV,
                "total_items": 1, "cached_count": 0, "missing_count": 1,
                "failed_count": 0, "invalid_hash_count": 0,
            }).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-gateway/manifest/current":
            if FullHandler.MF:
                self.send_response(FullHandler.MF)
                self.end_headers()
                self.wfile.write(b'{"error":"manifest fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_valid_manifest_body())
            return
        if self.path.startswith("/api/device-gateway/media/"):
            self.send_response(404)
            self.end_headers()
            return
        # Runtime config fallback
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "config_hash": "a" * 64, "config": {"k": "v"},
                                      "generated_at": "2026-06-19T10:00:00Z"}).encode())


class TestRunOnceWithManifest(unittest.TestCase):
    def setUp(self):
        FullHandler.r()

    def _fs(self, r, n):
        return next((s for s in r.steps if s.name == n), None)

    def test_run_once_manifest_updated(self):
        sv, _, p = _ss(FullHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.last_auth_status, "ok")
                self.assertEqual(res.manifest_status, "updated")
                mf = self._fs(res, "manifest")
                self.assertEqual(mf.status, "ok")
                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                self.assertEqual(d["_cycle"]["manifest_status"], "updated")
                # Manifest file was written
                mp = Path(r) / "manifest" / "current_manifest.json"
                self.assertTrue(mp.exists())
        finally:
            sv.shutdown()

    def test_auth_fail_manifest_skipped(self):
        sv, _, p = _ss(FullHandler)
        FullHandler.AF = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.last_auth_status, "error")
                self.assertEqual(res.manifest_status, "skipped")
                mf = self._fs(res, "manifest")
                self.assertEqual(mf.status, "skipped")
        finally:
            sv.shutdown()

    def test_manifest_500_non_fatal(self):
        sv, _, p = _ss(FullHandler)
        FullHandler.MF = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.manifest_status, "error")
                mf = self._fs(res, "manifest")
                self.assertEqual(mf.status, "error")
                self.assertFalse(mf.fatal)
        finally:
            sv.shutdown()

    def test_no_token_in_agent_status(self):
        sv, _, p = _ss(FullHandler)
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

    def test_local_only_no_manifest_sync(self):
        sv, _, p = _ss(FullHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                res = ro(r, options=opts)
                mf = self._fs(res, "manifest")
                # In local-only mode, manifest step is from local readiness (warning: missing)
                self.assertIsNotNone(mf)
                self.assertEqual(mf.status, "warning")  # local manifest missing
        finally:
            sv.shutdown()

    def test_full_manifest_not_in_safe_details(self):
        sv, _, p = _ss(FullHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                mf = self._fs(res, "manifest")
                sd = str(mf.safe_details).lower()
                self.assertNotIn("media_path", sd)
                self.assertNotIn("creatives", sd)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, sd, f"Forbidden '{fb}' in manifest safe_details")
        finally:
            sv.shutdown()


if __name__ == "__main__":
    unittest.main()
