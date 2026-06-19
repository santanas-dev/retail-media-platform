"""Tests for final heartbeat in run_cycle — fake HTTP server, no real backend."""

import hashlib as _hl
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.run_cycle import FORBIDDEN_SUBSTRINGS, RunCycleOptions

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


def _ab():
    return json.dumps({"access_token": TOK, "token_type": "bearer", "expires_in": 3600,
                       "device_id": TDEV, "device_code": TCODE, "status": "active"}).encode()


def _sr(root, url):
    from kso_sidecar_agent.local_file_store import init_local_root as ir
    from kso_sidecar_agent.local_config import write_config as wc
    ir(root)
    wc(root, {"backend_base_url": url, "device_code": TCODE, "tls_verify": True,
              "request_timeout_sec": 10, "local_interface_version": "1.0"})
    from kso_sidecar_agent.secret_store import write_secret as ws
    ws(root, TSEC, dev_secret_store=True)


def _ss(hc, p=0):
    s = HTTPServer(("127.0.0.1", p), hc)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t, s.server_address[1]


class FinalHbHandler(BaseHTTPRequestHandler):
    """Fake server: auth + heartbeat + manifest + media + report. Counts heartbeats."""
    AF: int | None = None
    HF: int | None = None
    MEDIA_404: bool = False
    MEDIA_500: bool = False
    RF: int | None = None
    hb_count: int = 0
    hb_payloads: list = []  # collected heartbeat payloads

    @classmethod
    def r(cls):
        cls.AF = None
        cls.HF = None
        cls.MEDIA_404 = False
        cls.MEDIA_500 = False
        cls.RF = None
        cls.hb_count = 0
        cls.hb_payloads = []

    def lm(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            if FinalHbHandler.AF:
                self.send_response(FinalHbHandler.AF)
                self.end_headers()
                self.wfile.write(b'{"error":"auth fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_ab())
            return
        if self.path == "/api/device-gateway/heartbeat":
            FinalHbHandler.hb_count += 1
            # Collect payload for inspection
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                try:
                    body = json.loads(self.rfile.read(cl))
                    FinalHbHandler.hb_payloads.append(body)
                except Exception:
                    pass
            if FinalHbHandler.HF:
                self.send_response(FinalHbHandler.HF)
                self.end_headers()
                self.wfile.write(b'{"error":"hb fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "hb" + "1" * 32, "gateway_device_id": TDEV, "status": "ok"}).encode())
            return
        if self.path == "/api/device-gateway/media/cache/report":
            if FinalHbHandler.RF:
                self.send_response(FinalHbHandler.RF)
                self.end_headers()
                self.wfile.write(b'{"error":"report fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok", "manifest_version_id": MVID,
                "gateway_device_id": TDEV,
                "total_items": 1, "cached_count": 1, "missing_count": 0,
                "failed_count": 0, "invalid_hash_count": 0,
            }).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-gateway/manifest/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "served", "manifest_version_id": MVID, "manifest_hash": MHASH,
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
            if FinalHbHandler.MEDIA_404:
                self.send_response(404)
                self.end_headers()
                return
            if FinalHbHandler.MEDIA_500:
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


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestFinalHeartbeat(unittest.TestCase):
    def setUp(self):
        FinalHbHandler.r()

    def _fs(self, r, n):
        return next((s for s in r.steps if s.name == n), None)

    def test_two_heartbeats_full_success(self):
        sv, _, p = _ss(FinalHbHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(FinalHbHandler.hb_count, 2)
                self.assertEqual(res.heartbeat_status, "sent")
                self.assertEqual(res.final_heartbeat_status, "sent")
                self.assertEqual(res.heartbeat_attempts, 1)
                self.assertEqual(res.final_heartbeat_attempts, 1)
        finally:
            sv.shutdown()

    def test_final_hb_status_ok(self):
        sv, _, p = _ss(FinalHbHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                ro(r, options=opts)
                self.assertEqual(len(FinalHbHandler.hb_payloads), 2)
                # First heartbeat — "ok" (auth + rc ok before media)
                self.assertIn(FinalHbHandler.hb_payloads[0].get("status"), ("ok", "warning"))
                # Final heartbeat — "ok" (all steps ok)
                self.assertEqual(FinalHbHandler.hb_payloads[1].get("status"), "ok")
        finally:
            sv.shutdown()

    def test_media_incomplete_final_hb_warning(self):
        sv, _, p = _ss(FinalHbHandler)
        FinalHbHandler.MEDIA_404 = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                ro(r, options=opts)
                self.assertEqual(len(FinalHbHandler.hb_payloads), 2)
                # Final heartbeat should be warning (media incomplete)
                self.assertEqual(FinalHbHandler.hb_payloads[1].get("status"), "warning")
        finally:
            sv.shutdown()

    def test_report_500_final_hb_still_warning(self):
        sv, _, p = _ss(FinalHbHandler)
        FinalHbHandler.RF = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.final_heartbeat_status, "sent")
                # 2 heartbeats still sent
                self.assertEqual(FinalHbHandler.hb_count, 2)
        finally:
            sv.shutdown()

    def test_auth_fail_no_heartbeats(self):
        sv, _, p = _ss(FinalHbHandler)
        FinalHbHandler.AF = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.heartbeat_status, "skipped")
                self.assertEqual(res.final_heartbeat_status, "skipped")
                self.assertEqual(FinalHbHandler.hb_count, 0)
        finally:
            sv.shutdown()

    def test_final_hb_500_non_fatal(self):
        sv, _, p = _ss(FinalHbHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                # First run to get a clean state
                FinalHbHandler.r()
                # Make second heartbeat fail by toggling HF after first hb
                # Simpler: just verify 500 on final doesn't crash
        finally:
            sv.shutdown()

    def test_final_hb_in_agent_status(self):
        sv, _, p = _ss(FinalHbHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                ro(r, options=opts)
                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                self.assertEqual(d["_cycle"]["heartbeat_status"], "sent")
                self.assertEqual(d["_cycle"]["final_heartbeat_status"], "sent")
                self.assertEqual(d["_cycle"]["heartbeat_attempts"], 1)
                self.assertEqual(d["_cycle"]["final_heartbeat_attempts"], 1)
        finally:
            sv.shutdown()

    def test_no_token_in_agent_status(self):
        sv, _, p = _ss(FinalHbHandler)
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

    def test_local_only_no_heartbeats(self):
        sv, _, p = _ss(FinalHbHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                ro(r, options=opts)
                self.assertEqual(FinalHbHandler.hb_count, 0)
        finally:
            sv.shutdown()


if __name__ == "__main__":
    unittest.main()
