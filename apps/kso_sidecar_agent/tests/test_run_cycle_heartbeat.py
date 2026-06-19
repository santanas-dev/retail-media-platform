"""Tests for run_cycle_heartbeat.py — fake HTTP server, no real backend."""

import json, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from kso_sidecar_agent.run_cycle import FORBIDDEN_SUBSTRINGS, RunCycleOptions
from kso_sidecar_agent.run_cycle_heartbeat import send_heartbeat_for_cycle
from kso_sidecar_agent.token_state import TokenState

TOK = "opaque-value-1234567890"
TSEC = "dev-value-1234567890"
TDEV = "550e8400-e29b-41d4-a716-446655440000"
TCODE = "a-05954"
NOW = 1_750_000_000.0

def _vts():
    return TokenState(_access_token=TOK, token_type="bearer", expires_at=NOW+3600,
                      device_id=TDEV, device_code=TCODE, status="active")

def _ets():
    return TokenState(_access_token=TOK, token_type="bearer", expires_at=NOW-3600,
                      device_id=TDEV, device_code=TCODE, status="active")

def _ab():
    return json.dumps({"access_token": TOK, "token_type": "bearer", "expires_in": 3600,
                       "device_id": TDEV, "device_code": TCODE, "status": "active"}).encode()

def _sr(root, url, sec=True):
    from kso_sidecar_agent.local_file_store import init_local_root as ir
    from kso_sidecar_agent.local_config import write_config as wc
    ir(root)
    wc(root, {"backend_base_url": url, "device_code": TCODE, "tls_verify": True,
              "request_timeout_sec": 10, "local_interface_version": "1.0"})
    if sec:
        from kso_sidecar_agent.secret_store import write_secret as ws
        ws(root, TSEC, dev_secret_store=True)

def _ss(hc, p=0):
    s = HTTPServer(("127.0.0.1", p), hc)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t, s.server_address[1]

class Hnd(BaseHTTPRequestHandler):
    AF = None
    HF = None
    HI = False
    ac = 0
    hc = 0

    @classmethod
    def r(cls):
        cls.AF = None
        cls.HF = None
        cls.HI = False
        cls.ac = 0
        cls.hc = 0

    def lm(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            Hnd.ac += 1
            if Hnd.AF:
                self.send_response(Hnd.AF)
                self.end_headers()
                self.wfile.write(b'{"error":"auth fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_ab())
            return
        if self.path == "/api/device-gateway/heartbeat":
            Hnd.hc += 1
            if Hnd.HF:
                self.send_response(Hnd.HF)
                self.end_headers()
                self.wfile.write(b'{"error":"hb fail"}')
                return
            if Hnd.HI:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>not json</html>")
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
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            item_id = "11111111-1111-1111-1111-111111111111"
            sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            manifest = {
                "status": "served",
                "manifest_version_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                "manifest_hash": "c" * 64,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "items": [
                        {"id": item_id, "sha256": sha, "media_path": f"media/{item_id}.png",
                         "duration_ms": 5000, "order": 0}
                    ]
                },
            }
            self.wfile.write(json.dumps(manifest).encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "config_hash": "a" * 64, "config": {"k": "v"},
                                      "generated_at": "2026-06-19T10:00:00+00:00"}).encode())


class TestSendHBForCycle(unittest.TestCase):
    def setUp(self):
        Hnd.r()

    def test_hb_success(self):
        sv, _, p = _ss(Hnd)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = send_heartbeat_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "ok")
                self.assertEqual(res.heartbeat_status, "sent")
        finally:
            sv.shutdown()

    def test_hb_ok_hint(self):
        sv, _, p = _ss(Hnd)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = send_heartbeat_for_cycle(r, ts, cycle_status_hint="ok", now=NOW)
                self.assertEqual(res.heartbeat_status, "sent")
        finally:
            sv.shutdown()

    def test_expired_token(self):
        with tempfile.TemporaryDirectory() as r:
            _sr(r, "http://127.0.0.1:9999")
            ts = _ets()
            res = send_heartbeat_for_cycle(r, ts, now=NOW)
            self.assertEqual(res.step.status, "error")
            self.assertEqual(res.heartbeat_status, "error")
            self.assertEqual(Hnd.hc, 0)

    def test_hb_401(self):
        sv, _, p = _ss(Hnd)
        Hnd.HF = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = send_heartbeat_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertFalse(res.step.fatal)
        finally:
            sv.shutdown()

    def test_hb_500_no_retry(self):
        sv, _, p = _ss(Hnd)
        Hnd.HF = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = send_heartbeat_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertEqual(res.heartbeat_status, "error")
                self.assertEqual(res.attempts, 1)
        finally:
            sv.shutdown()

    def test_no_token_in_step(self):
        sv, _, p = _ss(Hnd)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                ts = _vts()
                res = send_heartbeat_for_cycle(r, ts, now=NOW)
                st = str(res.step).lower()
                self.assertNotIn(TOK, st)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, st, f"Forbidden '{fb}' in hb step")
        finally:
            sv.shutdown()


class TestRunOnceWithHB(unittest.TestCase):
    def setUp(self):
        Hnd.r()

    def _fs(self, r, n):
        return next((s for s in r.steps if s.name == n), None)

    def test_run_once_hb_sent(self):
        sv, _, p = _ss(Hnd)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.last_auth_status, "ok")
                self.assertEqual(res.heartbeat_status, "sent")
                hb = self._fs(res, "heartbeat")
                self.assertEqual(hb.status, "ok")
                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                self.assertEqual(d["_cycle"]["heartbeat_status"], "sent")
        finally:
            sv.shutdown()

    def test_auth_fail_hb_skipped(self):
        sv, _, p = _ss(Hnd)
        Hnd.AF = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.last_auth_status, "error")
                self.assertEqual(res.heartbeat_status, "skipped")
                hb = self._fs(res, "heartbeat")
                self.assertEqual(hb.status, "skipped")
                self.assertEqual(Hnd.hc, 0)
        finally:
            sv.shutdown()

    def test_hb_500_non_fatal(self):
        sv, _, p = _ss(Hnd)
        Hnd.HF = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.heartbeat_status, "error")
                hb = self._fs(res, "heartbeat")
                self.assertEqual(hb.status, "error")
                self.assertFalse(hb.fatal)
        finally:
            sv.shutdown()

    def test_no_token_in_agent_status(self):
        sv, _, p = _ss(Hnd)
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

    def test_local_only_no_hb(self):
        sv, _, p = _ss(Hnd)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                ro(r, options=opts)
                self.assertEqual(Hnd.hc, 0)
        finally:
            sv.shutdown()


if __name__ == "__main__":
    unittest.main()
