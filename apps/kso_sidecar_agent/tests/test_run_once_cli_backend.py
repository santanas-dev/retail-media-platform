"""Tests for run-once --backend --dev-secret-store CLI — fake backend, no real backend."""

import hashlib as _hl
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

TOK = "opaque-value-1234567890"
TSEC = "dev-value-1234567890"
TDEV = "550e8400-e29b-41d4-a716-446655440000"
TCODE = "a-05954"
MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "c" * 64
MID1 = "11111111-1111-1111-1111-111111111111"
MID2 = "22222222-2222-2222-2222-222222222222"
PNG1 = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 80
PNG1_SHA = _hl.sha256(PNG1).hexdigest()
PNG2_SHA = _hl.sha256(PNG2).hexdigest()


def _run(*args):
    env = {**__import__("os").environ}
    player_path = str(PKG_DIR.parent / "kso_player")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{player_path}:{existing}" if existing else player_path
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR), env=env,
    )
    return r.returncode, r.stdout, r.stderr


def _run_stdin(secret, *args):
    env = {**__import__("os").environ}
    player_path = str(PKG_DIR.parent / "kso_player")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{player_path}:{existing}" if existing else player_path
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR), input=secret,
    )
    return r.returncode, r.stdout, r.stderr


def _setup(root, url):
    _run("init-local-root", "--root", root)
    _run("write-config", "--root", root, "--backend-base-url", url, "--device-code", TCODE)
    _run_stdin(TSEC, "secret-store-set", "--root", root, "--dev-secret-store", "--stdin")


def _ss(hc, p=0):
    s = HTTPServer(("127.0.0.1", p), hc)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t, s.server_address[1]


class CLIHandler(BaseHTTPRequestHandler):
    """Full fake backend for CLI backend tests."""
    AUTH_FAIL: int | None = None
    HB_FAIL: int | None = None
    MEDIA_404: str | None = None
    REPORT_FAIL: int | None = None

    @classmethod
    def reset(cls):
        cls.AUTH_FAIL = None
        cls.HB_FAIL = None
        cls.MEDIA_404 = None
        cls.REPORT_FAIL = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            if CLIHandler.AUTH_FAIL:
                self.send_response(CLIHandler.AUTH_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"auth fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "access_token": TOK, "token_type": "bearer", "expires_in": 3600,
                "device_id": TDEV, "device_code": TCODE, "status": "active",
            }).encode())
            return
        if self.path == "/api/device-gateway/heartbeat":
            if CLIHandler.HB_FAIL:
                self.send_response(CLIHandler.HB_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"hb fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "hb" + "1" * 32, "gateway_device_id": TDEV, "status": "ok"}).encode())
            return
        if self.path == "/api/device-gateway/media/cache/report":
            if CLIHandler.REPORT_FAIL:
                self.send_response(CLIHandler.REPORT_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"report fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok", "manifest_version_id": MVID, "gateway_device_id": TDEV,
                "total_items": 2, "cached_count": 2, "missing_count": 0,
                "failed_count": 0, "invalid_hash_count": 0,
            }).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-gateway/config/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "config_hash": "a" * 64, "config": {"k": "v"},
                                          "generated_at": "2026-06-19T10:00:00Z"}).encode())
            return
        if self.path == "/api/device-gateway/manifest/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "served", "manifest_version_id": MVID, "manifest_hash": MHASH,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "items": [
                        {"id": MID1, "sha256": PNG1_SHA, "media_path": f"media/{MID1}.png",
                         "duration_ms": 5000, "order": 0},
                        {"id": MID2, "sha256": PNG2_SHA, "media_path": f"media/{MID2}.png",
                         "duration_ms": 3000, "order": 1},
                    ]
                },
            }).encode())
            return
        if self.path.startswith("/api/device-gateway/media/"):
            item_id = self.path.split("/")[-1]
            if CLIHandler.MEDIA_404 and item_id == CLIHandler.MEDIA_404:
                self.send_response(404)
                self.end_headers()
                return
            content = PNG1 if item_id == MID1 else PNG2
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        self.send_response(404)
        self.end_headers()


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestRunOnceBackendCLI(unittest.TestCase):
    def setUp(self):
        CLIHandler.reset()

    def _forbidden_in(self, text, label=""):
        forbidden = {"token", "jwt", "password", "secret", "api_key",
                     "private_key", "payment_card", "receipt", "local_path",
                     "file_path", "authorization", "bearer", "device_secret",
                     "access_token", "media_path", "creatives/"}
        lower = text.lower()
        for fb in forbidden:
            self.assertNotIn(fb, lower, f"Forbidden '{fb}' in {label}")

    # ── Happy path ──────────────────────────────────────────────────

    def test_backend_happy_path(self):
        sv, _, p = _ss(CLIHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                rc, out, err = _run("run-once", "--root", r, "--backend", "--dev-secret-store")
                self.assertEqual(rc, 0, f"stderr: {err}")
                self.assertIn("run_cycle:              ok", out)
                self.assertIn("mode:                   backend", out)
                self.assertIn("auth_status:            ok", out)
                self.assertIn("heartbeat_status:       sent", out)
                self.assertIn("final_heartbeat_status: sent", out)
                self.assertIn("manifest_status:        updated", out)
                self.assertIn("media_cache_complete:   true", out)
                self.assertIn("media_report_status:    sent", out)
                self._forbidden_in(out, "stdout")
                self._forbidden_in(err, "stderr")
        finally:
            sv.shutdown()

    def test_backend_media_404_warning(self):
        sv, _, p = _ss(CLIHandler)
        CLIHandler.MEDIA_404 = MID2
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                rc, out, err = _run("run-once", "--root", r, "--backend", "--dev-secret-store")
                self.assertEqual(rc, 0, f"stderr: {err}")
                self.assertIn("run_cycle:              warning", out)
                self.assertIn("media_cache_complete:   false", out)
                self._forbidden_in(out, "stdout")
        finally:
            sv.shutdown()

    def test_backend_report_500_warning(self):
        sv, _, p = _ss(CLIHandler)
        CLIHandler.REPORT_FAIL = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                rc, out, err = _run("run-once", "--root", r, "--backend", "--dev-secret-store")
                self.assertEqual(rc, 0, f"stderr: {err}")
                self.assertIn("run_cycle:              warning", out)
                self.assertIn("media_report_status:    error", out)
                self._forbidden_in(out, "stdout")
        finally:
            sv.shutdown()

    def test_backend_auth_401_error(self):
        sv, _, p = _ss(CLIHandler)
        CLIHandler.AUTH_FAIL = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                rc, out, err = _run("run-once", "--root", r, "--backend", "--dev-secret-store")
                self.assertEqual(rc, 1)
                self.assertIn("run_cycle:              error", out)
                self.assertIn("auth_status:            error", out)
                self._forbidden_in(out, "stdout")
        finally:
            sv.shutdown()

    # ── CLI gate errors ────────────────────────────────────────────

    def test_backend_without_dev_secret_store(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, "http://127.0.0.1:1")
            rc, out, err = _run("run-once", "--root", r, "--backend")
            self.assertEqual(rc, 2)
            self.assertIn("ERROR", err)

    def test_both_local_only_and_backend(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, "http://127.0.0.1:1")
            rc, out, err = _run("run-once", "--root", r, "--local-only", "--backend")
            self.assertEqual(rc, 2)

    def test_no_mode_specified(self):
        with tempfile.TemporaryDirectory() as r:
            _setup(r, "http://127.0.0.1:1")
            rc, out, err = _run("run-once", "--root", r)
            self.assertEqual(rc, 2)

    # ── Local-only regression ─────────────────────────────────────

    def test_local_only_no_backend_calls(self):
        sv, _, p = _ss(CLIHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                rc, out, err = _run("run-once", "--root", r, "--local-only")
                self.assertEqual(rc, 0, f"stderr: {err}")
                self.assertIn("mode:                   local_only", out)
                self.assertNotIn("auth_status:", out)
                self._forbidden_in(out, "stdout")
        finally:
            sv.shutdown()

    # ── Agent status check ────────────────────────────────────────

    def test_agent_status_contains_backend_fields(self):
        sv, _, p = _ss(CLIHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                _run("run-once", "--root", r, "--backend", "--dev-secret-store")
                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                c = d["_cycle"]
                self.assertEqual(c["last_cycle_status"], "ok")
                self.assertEqual(c["heartbeat_status"], "sent")
                self.assertEqual(c["final_heartbeat_status"], "sent")
                self.assertTrue(c["media_cache_complete"])
                self.assertEqual(c["media_report_status"], "sent")
                self._forbidden_in(json.dumps(d).lower(), "agent_status")
        finally:
            sv.shutdown()

    # ── Security ──────────────────────────────────────────────────

    def test_no_token_in_output(self):
        sv, _, p = _ss(CLIHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                rc, out, err = _run("run-once", "--root", r, "--backend", "--dev-secret-store")
                self.assertNotIn(TOK, out)
                self.assertNotIn(TSEC, out)
                self.assertNotIn("127.0.0.1", out)
                self.assertNotIn("backend_base_url", out)
                self.assertNotIn("device_code", out)
        finally:
            sv.shutdown()

    def test_retry_flags_passed(self):
        sv, _, p = _ss(CLIHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                rc, out, err = _run(
                    "run-once", "--root", r, "--backend", "--dev-secret-store",
                    "--retry-auth", "--retry-heartbeat",
                    "--auth-max-attempts", "5", "--heartbeat-max-attempts", "5",
                )
                self.assertEqual(rc, 0, f"stderr: {err}")
        finally:
            sv.shutdown()

    def test_no_stacktrace(self):
        sv, _, p = _ss(CLIHandler)
        CLIHandler.AUTH_FAIL = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _setup(r, f"http://127.0.0.1:{p}")
                rc, out, err = _run("run-once", "--root", r, "--backend", "--dev-secret-store")
                self.assertNotIn("Traceback", out)
                self.assertNotIn("Traceback", err)
        finally:
            sv.shutdown()


if __name__ == "__main__":
    unittest.main()
