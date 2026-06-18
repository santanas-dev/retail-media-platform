"""Tests for HeartbeatClient — uses local fake HTTP server, no real backend."""

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

TEST_SECRET = "dev-value-1234567890"
TEST_TOKEN = "opaque-value-1234567890"
TEST_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_DEVICE_CODE = "a-05954"
NOW = 1_750_000_000.0

DEV_FLAG = ["--dev-secret-store"]


def _valid_token_state(token=TEST_TOKEN):
    from kso_sidecar_agent.token_state import TokenState
    return TokenState(
        _access_token=token, token_type="bearer", expires_at=NOW + 3600,
        device_id=TEST_DEVICE_ID, device_code=TEST_DEVICE_CODE, status="active",
    )


# ══════════════════════════════════════════════════════════════════════
# Fake server
# ══════════════════════════════════════════════════════════════════════

def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


def _valid_auth_body():
    return json.dumps({
        "access_token": TEST_TOKEN, "token_type": "bearer",
        "expires_in": 3600, "device_id": TEST_DEVICE_ID,
        "device_code": TEST_DEVICE_CODE, "status": "active",
    }).encode()


def _valid_hb_response():
    return json.dumps({
        "id": "heartbeat-uuid-123",
        "gateway_device_id": TEST_DEVICE_ID,
        "status": "ok", "created_at": "2026-06-18T10:00:00+00:00",
    }).encode()


class HbHandler(BaseHTTPRequestHandler):
    """Handles both auth and heartbeat endpoints."""

    AUTH_FAIL_CODE = None
    HB_FAIL_CODE = None
    HB_INVALID_JSON = False
    last_auth_header = ""
    auth_calls = 0
    hb_calls = 0

    @classmethod
    def reset(cls):
        cls.AUTH_FAIL_CODE = None
        cls.HB_FAIL_CODE = None
        cls.HB_INVALID_JSON = False
        cls.last_auth_header = ""
        cls.auth_calls = 0
        cls.hb_calls = 0

    def do_POST(self):
        if self.path.startswith("/api/device-gateway/auth/token"):
            self._handle_auth()
        elif self.path.startswith("/api/device-gateway/heartbeat"):
            self._handle_heartbeat()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_auth(self):
        HbHandler.auth_calls += 1
        body_len = int(self.headers.get("Content-Length", 0))
        self.rfile.read(body_len)
        if HbHandler.AUTH_FAIL_CODE:
            self.send_response(HbHandler.AUTH_FAIL_CODE)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"auth error")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_valid_auth_body())

    def _handle_heartbeat(self):
        HbHandler.hb_calls += 1
        HbHandler.last_auth_header = self.headers.get("Authorization", "")
        if HbHandler.HB_INVALID_JSON:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>not json</html>")
        elif HbHandler.HB_FAIL_CODE:
            self.send_response(HbHandler.HB_FAIL_CODE)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"hb error")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_valid_hb_response())

    def log_message(self, format, *args):
        pass


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _run(*args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR),
    )
    return r.returncode, r.stdout, r.stderr


def _run_stdin(secret, *args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR), input=secret,
    )
    return r.returncode, r.stdout, r.stderr


def _setup_root(root, base_url, with_secret=True):
    _run("init-local-root", "--root", root)
    _run("write-config", "--root", root,
         "--backend-base-url", base_url, "--device-code", TEST_DEVICE_CODE)
    if with_secret:
        _run_stdin(TEST_SECRET, "secret-store-set", "--root", root,
                   *DEV_FLAG, "--stdin")


# ══════════════════════════════════════════════════════════════════════
# Payload tests
# ══════════════════════════════════════════════════════════════════════

class TestHeartbeatPayload(unittest.TestCase):

    def test_valid_default(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        p = HeartbeatPayload()
        self.assertEqual(p.status, "ok")

    def test_invalid_status_rejected(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        with self.assertRaises(ValueError):
            HeartbeatPayload(status="offline")

    def test_message_long_rejected(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        with self.assertRaises(ValueError):
            HeartbeatPayload(message="x" * 201)

    def test_message_with_secret_rejected(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        with self.assertRaises(ValueError):
            HeartbeatPayload(message="my secret is safe")

    def test_negative_storage_rejected(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        with self.assertRaises(ValueError):
            HeartbeatPayload(storage_free_mb=-1)

    def test_negative_cache_rejected(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        with self.assertRaises(ValueError):
            HeartbeatPayload(cache_items_count=-1)

    def test_invalid_manifest_hash_rejected(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        with self.assertRaises(ValueError):
            HeartbeatPayload(current_manifest_hash="abc")

    def test_details_with_forbidden_rejected(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        with self.assertRaises(ValueError):
            HeartbeatPayload(details_json={"token": "val"})


# ══════════════════════════════════════════════════════════════════════
# Client tests
# ══════════════════════════════════════════════════════════════════════

class TestHeartbeatClient(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._server, cls._thread, cls._port = _start_server(HbHandler)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()

    def setUp(self):
        HbHandler.reset()

    def _client(self):
        from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
        from kso_sidecar_agent.heartbeat_client import HeartbeatClient
        http = SafeHttpClient(HttpClientConfig(
            base_url=f"http://127.0.0.1:{self._port}", timeout_sec=3,
        ))
        return HeartbeatClient(http_client=http)

    def test_send_heartbeat_success(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        hb = self._client()
        ts = _valid_token_state()
        result = hb.send_heartbeat(ts, HeartbeatPayload(status="ok"), now=NOW)
        self.assertEqual(result.status, "sent")

    def test_auth_header_sent(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        hb = self._client()
        hb.send_heartbeat(_valid_token_state(), HeartbeatPayload(), now=NOW)
        self.assertIn("Bearer", HbHandler.last_auth_header)
        self.assertIn(TEST_TOKEN, HbHandler.last_auth_header)

    def test_expired_token_rejected(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload
        from kso_sidecar_agent.token_state import TokenState
        hb = self._client()
        ts = TokenState(_access_token=TEST_TOKEN, token_type="bearer",
                        expires_at=NOW - 1, device_id="x", device_code="x",
                        status="active")
        with self.assertRaises(ValueError):
            hb.send_heartbeat(ts, HeartbeatPayload(), now=NOW)

    def test_hb_401_safe(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload, HttpClientError
        HbHandler.HB_FAIL_CODE = 401
        hb = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            hb.send_heartbeat(_valid_token_state(), HeartbeatPayload(), now=NOW)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertNotIn(TEST_TOKEN, ctx.exception.message)

    def test_hb_403_safe(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload, HttpClientError
        HbHandler.HB_FAIL_CODE = 403
        hb = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            hb.send_heartbeat(_valid_token_state(), HeartbeatPayload(), now=NOW)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_hb_422_safe(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload, HttpClientError
        HbHandler.HB_FAIL_CODE = 422
        hb = self._client()
        with self.assertRaises(HttpClientError):
            hb.send_heartbeat(_valid_token_state(), HeartbeatPayload(), now=NOW)

    def test_hb_500_retryable(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload, HttpClientError
        HbHandler.HB_FAIL_CODE = 500
        hb = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            hb.send_heartbeat(_valid_token_state(), HeartbeatPayload(), now=NOW)
        self.assertTrue(ctx.exception.retryable)

    def test_invalid_json_response(self):
        from kso_sidecar_agent.heartbeat_client import HeartbeatPayload, HttpClientError
        HbHandler.HB_INVALID_JSON = True
        hb = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            hb.send_heartbeat(_valid_token_state(), HeartbeatPayload(), now=NOW)
        self.assertIn("Invalid JSON", ctx.exception.message)


# ══════════════════════════════════════════════════════════════════════
# CLI tests
# ══════════════════════════════════════════════════════════════════════

class TestCLIHeartbeatOnce(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._server, cls._thread, cls._port = _start_server(HbHandler)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()

    def setUp(self):
        HbHandler.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self._base = f"http://127.0.0.1:{self._port}"
        _setup_root(self.root, self._base, with_secret=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_success(self):
        code, out, err = _run("heartbeat-once", "--root", self.root,
                              "--status", "ok", *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("heartbeat:         sent", out)

    def test_no_token_in_output(self):
        code, out, err = _run("heartbeat-once", "--root", self.root, *DEV_FLAG)
        self.assertNotIn(TEST_TOKEN, out)
        self.assertNotIn(TEST_TOKEN, err)

    def test_no_secret_in_output(self):
        code, out, err = _run("heartbeat-once", "--root", self.root, *DEV_FLAG)
        self.assertNotIn(TEST_SECRET, out + err)

    def test_no_auth_in_output(self):
        code, out, err = _run("heartbeat-once", "--root", self.root, *DEV_FLAG)
        self.assertNotIn("Bearer", out + err)

    def test_auth_401_no_hb(self):
        HbHandler.AUTH_FAIL_CODE = 401
        code, out, err = _run("heartbeat-once", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertEqual(HbHandler.hb_calls, 0)

    def test_no_config_error(self):
        tmp2 = tempfile.TemporaryDirectory()
        _run("init-local-root", "--root", tmp2.name)
        code, out, err = _run("heartbeat-once", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("Config", err)
        tmp2.cleanup()

    def test_no_secret_error(self):
        tmp2 = tempfile.TemporaryDirectory()
        _setup_root(tmp2.name, self._base, with_secret=False)
        code, out, err = _run("heartbeat-once", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("secret", (out + err).lower())
        tmp2.cleanup()

    def test_no_dev_flag(self):
        code, out, err = _run("heartbeat-once", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("disabled", (out + err).lower())

    def test_hb_500_cli(self):
        HbHandler.HB_FAIL_CODE = 500
        code, out, err = _run("heartbeat-once", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("Heartbeat failed", err)

    def test_hb_403_cli(self):
        HbHandler.HB_FAIL_CODE = 403
        code, out, err = _run("heartbeat-once", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)

    def test_hb_422_cli(self):
        HbHandler.HB_FAIL_CODE = 422
        code, out, err = _run("heartbeat-once", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)

    def test_invalid_status_cli(self):
        code, out, err = _run("heartbeat-once", "--root", self.root,
                              "--status", "offline", *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("Invalid payload", err)

    def test_no_stacktrace(self):
        tmp2 = tempfile.TemporaryDirectory()
        _run("init-local-root", "--root", tmp2.name)
        code, out, err = _run("heartbeat-once", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Traceback", err)
        tmp2.cleanup()


if __name__ == "__main__":
    unittest.main()
