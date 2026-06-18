"""Tests for sync-runtime-config CLI — uses fake HTTP servers, no real backend."""

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
TEST_CONFIG_HASH = "abc123hash123"

DEV_FLAG = ["--dev-secret-store"]

# ══════════════════════════════════════════════════════════════════════
# Fake server
# ══════════════════════════════════════════════════════════════════════

def _valid_auth_body():
    return {
        "access_token": TEST_TOKEN,
        "token_type": "bearer",
        "expires_in": 3600,
        "device_id": TEST_DEVICE_ID,
        "device_code": TEST_DEVICE_CODE,
        "status": "active",
    }

def _valid_config_body():
    return {
        "status": "ok",
        "gateway_device_id": TEST_DEVICE_ID,
        "config_hash": TEST_CONFIG_HASH,
        "config": {"display_timeout_sec": 30, "log_level": "info"},
        "generated_at": "2026-06-18T10:00:00+00:00",
    }

class SyncHandler(BaseHTTPRequestHandler):
    """Handles both auth and config endpoints."""

    AUTH_FAIL_STATUS = None   # Set to e.g. 401 to make auth fail
    CONFIG_FAIL_STATUS = None # Set to e.g. 500 to make config fail
    CONFIG_304 = False        # Return 304 for config
    CONFIG_FORBIDDEN = False  # Return config with forbidden key
    CONFIG_INVALID_JSON = False
    LAST_IF_NONE_MATCH = ""
    AUTH_CALL_COUNT = 0
    CONFIG_CALL_COUNT = 0

    @classmethod
    def reset(cls):
        cls.AUTH_FAIL_STATUS = None
        cls.CONFIG_FAIL_STATUS = None
        cls.CONFIG_304 = False
        cls.CONFIG_FORBIDDEN = False
        cls.CONFIG_INVALID_JSON = False
        cls.LAST_IF_NONE_MATCH = ""
        cls.AUTH_CALL_COUNT = 0
        cls.CONFIG_CALL_COUNT = 0

    # ── Auth endpoint ──────────────────────────────────────────────
    def _handle_auth(self):
        SyncHandler.AUTH_CALL_COUNT += 1
        body_len = int(self.headers.get("Content-Length", 0))
        self.rfile.read(body_len)  # consume

        if SyncHandler.AUTH_FAIL_STATUS:
            self.send_response(SyncHandler.AUTH_FAIL_STATUS)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"auth error")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_valid_auth_body()).encode())

    # ── Config endpoint ────────────────────────────────────────────
    def _handle_config(self):
        SyncHandler.CONFIG_CALL_COUNT += 1
        SyncHandler.LAST_IF_NONE_MATCH = self.headers.get("If-None-Match", "")

        if SyncHandler.CONFIG_304:
            self.send_response(304)
            self.end_headers()
            return

        if SyncHandler.CONFIG_FAIL_STATUS:
            self.send_response(SyncHandler.CONFIG_FAIL_STATUS)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"config error")
            return

        if SyncHandler.CONFIG_INVALID_JSON:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>not json</html>")
            return

        body = _valid_config_body()
        if SyncHandler.CONFIG_FORBIDDEN:
            body["config"] = {"api_key": "should-reject"}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("ETag", f'"{TEST_CONFIG_HASH}"')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    # ── Router ─────────────────────────────────────────────────────
    def do_POST(self):
        if self.path.startswith("/api/device-gateway/auth/token"):
            self._handle_auth()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/device-gateway/config/current"):
            self._handle_config()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


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


def _setup_agent_root(root, base_url, with_secret=True):
    _run("init-local-root", "--root", root)
    _run("write-config", "--root", root,
         "--backend-base-url", base_url, "--device-code", TEST_DEVICE_CODE)
    if with_secret:
        _run_stdin(TEST_SECRET, "secret-store-set", "--root", root, *DEV_FLAG, "--stdin")


# ══════════════════════════════════════════════════════════════════════

class TestSyncRuntimeConfig(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._server, cls._thread, cls._port = _start_server(SyncHandler)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()

    def setUp(self):
        SyncHandler.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self._base = f"http://127.0.0.1:{self._port}"
        _setup_agent_root(self.root, self._base, with_secret=True)

    def tearDown(self):
        self.tmp.cleanup()

    # ── Success ────────────────────────────────────────────────────

    def test_sync_success(self):
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("runtime_config_sync: updated", out)
        self.assertIn(TEST_CONFIG_HASH, out)
        self.assertIn("config_keys_count:", out)

    def test_sync_creates_runtime_config_file(self):
        _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        path = Path(self.root) / "config" / "runtime_config.json"
        self.assertTrue(path.exists())

    def test_sync_output_no_token(self):
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertNotIn(TEST_TOKEN, out, "Token leaked to stdout")
        self.assertNotIn(TEST_TOKEN, err, "Token leaked to stderr")

    def test_sync_output_no_secret(self):
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        combined = out + err
        self.assertNotIn(TEST_SECRET, combined, "Secret leaked")

    def test_runtime_config_file_no_token_secret(self):
        _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        content = (Path(self.root) / "config" / "runtime_config.json").read_text()
        self.assertNotIn(TEST_TOKEN, content.lower())
        self.assertNotIn(TEST_SECRET, content.lower())

    # ── ETag / 304 ─────────────────────────────────────────────────

    def test_sync_sends_if_none_match(self):
        # First sync creates the file
        _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        SyncHandler.reset()
        # Second sync should send If-None-Match
        _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertIn(TEST_CONFIG_HASH, SyncHandler.LAST_IF_NONE_MATCH)

    def test_sync_304_not_modified(self):
        # Create local file first
        _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        SyncHandler.reset()
        SyncHandler.CONFIG_304 = True
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("not_modified", out)

    # ── Auth errors ────────────────────────────────────────────────

    def test_auth_401_safe_error(self):
        SyncHandler.AUTH_FAIL_STATUS = 401
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("sync failed", (out + err).lower())
        self.assertEqual(SyncHandler.CONFIG_CALL_COUNT, 0)  # never reached config

    def test_auth_500_with_retry(self):
        SyncHandler.AUTH_FAIL_STATUS = 500
        # Auth fails immediately (no retry_manager by default), but with --retry-auth:
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG, "--retry-auth")
        self.assertNotEqual(code, 0)  # 500×3 = exhaust
        self.assertIn("sync failed", (out + err).lower())

    # ── Config errors ──────────────────────────────────────────────

    def test_config_403_safe_error(self):
        SyncHandler.CONFIG_FAIL_STATUS = 403
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("sync failed", (out + err).lower())

    def test_config_500_safe_error(self):
        SyncHandler.CONFIG_FAIL_STATUS = 500
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)

    def test_config_forbidden_key_rejected(self):
        SyncHandler.CONFIG_FORBIDDEN = True
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("forbidden", (out + err).lower())

    def test_config_invalid_json_safe_error(self):
        SyncHandler.CONFIG_INVALID_JSON = True
        code, out, err = _run("sync-runtime-config", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)

    # ── Error cases ────────────────────────────────────────────────

    def test_no_config_safe_error(self):
        tmp2 = tempfile.TemporaryDirectory()
        _run("init-local-root", "--root", tmp2.name)
        code, out, err = _run("sync-runtime-config", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("Config", err)
        tmp2.cleanup()

    def test_no_secret_safe_error(self):
        tmp2 = tempfile.TemporaryDirectory()
        _setup_agent_root(tmp2.name, self._base, with_secret=False)
        code, out, err = _run("sync-runtime-config", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("secret", (out + err).lower())
        tmp2.cleanup()

    def test_no_dev_flag_rejected(self):
        code, out, err = _run("sync-runtime-config", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("disabled", (out + err).lower())

    # ── No stacktrace ──────────────────────────────────────────────

    def test_no_stacktrace(self):
        tmp2 = tempfile.TemporaryDirectory()
        _run("init-local-root", "--root", tmp2.name)
        code, out, err = _run("sync-runtime-config", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Traceback", err)
        tmp2.cleanup()


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
