"""Tests for run_cycle_auth.py — fake HTTP server, no real backend."""

import json
import tempfile
import threading
import time as _time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.run_cycle import (
    FORBIDDEN_SUBSTRINGS,
    RunCycleOptions,
)
from kso_sidecar_agent.run_cycle_auth import CycleAuthResult, authenticate_for_cycle

TEST_SECRET = "dev-value-1234567890"
TEST_TOKEN = "opaque-value-1234567890"
TEST_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_DEVICE_CODE = "a-05954"


def _valid_auth_body():
    return json.dumps({
        "access_token": TEST_TOKEN, "token_type": "bearer",
        "expires_in": 3600, "device_id": TEST_DEVICE_ID,
        "device_code": TEST_DEVICE_CODE, "status": "active",
    }).encode()


def _setup_root_with_config(root, base_url, with_secret=True):
    """Set up root with config and optional secret."""
    from kso_sidecar_agent.local_file_store import init_local_root
    from kso_sidecar_agent.local_config import write_config

    init_local_root(root)
    write_config(root, {
        "backend_base_url": base_url,
        "device_code": TEST_DEVICE_CODE,
        "tls_verify": True,
        "request_timeout_sec": 10,
        "local_interface_version": "1.0",
    })

    if with_secret:
        from kso_sidecar_agent.secret_store import write_secret
        write_secret(root, TEST_SECRET, dev_secret_store=True)


def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


class AuthHandler(BaseHTTPRequestHandler):
    """Fake auth server for testing."""

    FAIL_CODE = None
    INVALID_JSON = False
    calls = 0

    @classmethod
    def reset(cls):
        cls.FAIL_CODE = None
        cls.INVALID_JSON = False
        cls.calls = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        AuthHandler.calls += 1

        if self.FAIL_CODE:
            self.send_response(self.FAIL_CODE)
            self.end_headers()
            self.wfile.write(b'{"error":"fail"}')
            return

        if self.INVALID_JSON:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>not json</html>")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(_valid_auth_body())

    def do_GET(self):
        """Serve valid manifest for /manifest/current."""
        if self.path == "/api/device-gateway/manifest/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            item_id = _valid_manifest_item_id()
            manifest_body = {
                "status": "served",
                "manifest_version_id": _valid_manifest_version_id(),
                "manifest_hash": _valid_manifest_hash(),
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "items": [
                        {
                            "id": item_id,
                            "sha256": _valid_manifest_item_sha256(),
                            "media_path": f"media/{item_id}.png",
                            "duration_ms": 5000,
                            "order": 0,
                        }
                    ]
                },
            }
            self.wfile.write(json.dumps(manifest_body).encode())
            return
        if self.path.startswith("/api/device-gateway/media/"):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()


def _noop_sleep(sec):
    pass

def _valid_manifest_version_id():
    return "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

def _valid_manifest_hash():
    return "c" * 64

def _valid_manifest_item_id():
    return "11111111-1111-1111-1111-111111111111"

def _valid_manifest_item_sha256():
    import hashlib
    return hashlib.sha256(b"test content").hexdigest()


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestAuthenticateForCycle(unittest.TestCase):

    def setUp(self):
        AuthHandler.reset()

    # ── Success ────────────────────────────────────────────────────

    def test_auth_success(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                self.assertEqual(result.step.name, "auth")
                self.assertEqual(result.step.status, "ok")
                self.assertIsNotNone(result.token_state)
                self.assertTrue(result.token_state.is_valid())
                self.assertGreater(result.attempts, 0)
                self.assertGreater(result.expires_in_sec, 0)
        finally:
            server.shutdown()

    def test_token_not_in_step(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                step_str = str(result.step.safe_details).lower()
                self.assertNotIn(TEST_TOKEN, step_str)
        finally:
            server.shutdown()

    # ── Skipped when backend_enabled=False ─────────────────────────

    def test_skipped_when_backend_disabled(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_root_with_config(root, "http://127.0.0.1:9999")

            opts = RunCycleOptions(backend_enabled=False, dev_secret_store=True)
            result = authenticate_for_cycle(root, opts)

            self.assertEqual(result.step.name, "auth")
            self.assertEqual(result.step.status, "skipped")
            self.assertIsNone(result.token_state)
            self.assertEqual(result.attempts, 0)
            self.assertEqual(AuthHandler.calls, 0)

    # ── Config errors ──────────────────────────────────────────────

    def test_missing_config_error(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "status").mkdir(parents=True, exist_ok=True)

            opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
            result = authenticate_for_cycle(root, opts)

            self.assertEqual(result.step.status, "error")
            self.assertTrue(result.step.fatal)
            self.assertEqual(AuthHandler.calls, 0)

    def test_missing_secret_error(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}", with_secret=False)

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts)

                self.assertEqual(result.step.status, "error")
                self.assertTrue(result.step.fatal)
                self.assertEqual(AuthHandler.calls, 0)
        finally:
            server.shutdown()

    def test_no_dev_secret_store_reject(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=False)
                result = authenticate_for_cycle(root, opts)

                self.assertEqual(result.step.status, "error")
                self.assertTrue(result.step.fatal)
                self.assertEqual(AuthHandler.calls, 0)
        finally:
            server.shutdown()

    # ── HTTP errors ────────────────────────────────────────────────

    def test_auth_401_error(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            AuthHandler.FAIL_CODE = 401

            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                self.assertEqual(result.step.status, "error")
                self.assertTrue(result.step.fatal)
                self.assertIsNone(result.token_state)
        finally:
            server.shutdown()

    def test_auth_403_error(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            AuthHandler.FAIL_CODE = 403

            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                self.assertEqual(result.step.status, "error")
                self.assertTrue(result.step.fatal)
        finally:
            server.shutdown()

    def test_auth_422_error(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            AuthHandler.FAIL_CODE = 422

            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                self.assertEqual(result.step.status, "error")
                self.assertTrue(result.step.fatal)
        finally:
            server.shutdown()

    def test_auth_500_no_retry(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            AuthHandler.FAIL_CODE = 500

            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True, retry_auth=False)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                self.assertEqual(result.step.status, "error")
                self.assertEqual(result.attempts, 1)
        finally:
            server.shutdown()

    # ── Retry ─────────────────────────────────────────────────────

    def test_auth_500_with_retry_success(self):
        """Auth 500 → retry → 200 success."""

        class RetryHandler(BaseHTTPRequestHandler):
            call_count = 0

            def log_message(self, *args):
                pass

            def do_POST(self):
                RetryHandler.call_count += 1
                if RetryHandler.call_count == 1:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error":"fail"}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(_valid_auth_body())

        server, thr, port = _start_server(RetryHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(
                    backend_enabled=True, dev_secret_store=True,
                    retry_auth=True, auth_max_attempts=3,
                )
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                self.assertEqual(result.step.status, "ok")
                self.assertIsNotNone(result.token_state)
                self.assertEqual(result.attempts, 2)
        finally:
            server.shutdown()

    # ── Invalid JSON ───────────────────────────────────────────────

    def test_invalid_json_error(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            AuthHandler.INVALID_JSON = True

            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                self.assertEqual(result.step.status, "error")
                self.assertIsNone(result.token_state)
        finally:
            server.shutdown()

    # ── Security — no token/secret in step ─────────────────────────

    def test_no_forbidden_in_step(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                step_str = str(result.step).lower()
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, step_str,
                                     f"Forbidden '{fb}' in auth step")
        finally:
            server.shutdown()

    def test_no_token_in_error_step(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            AuthHandler.FAIL_CODE = 401

            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = authenticate_for_cycle(root, opts, sleep_fn=_noop_sleep)

                step_str = str(result.step).lower()
                self.assertNotIn(TEST_TOKEN, step_str)
                self.assertNotIn(TEST_SECRET, step_str)
        finally:
            server.shutdown()


# ══════════════════════════════════════════════════════════════════════
# Tests: run_once with auth
# ══════════════════════════════════════════════════════════════════════

class TestRunOnceWithAuth(unittest.TestCase):

    def setUp(self):
        AuthHandler.reset()

    def _find_step(self, result, name):
        return next((s for s in result.steps if s.name == name), None)

    def test_run_once_local_only_no_auth(self):
        """run_once backend_enabled=False → auth skipped, no HTTP."""
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                result = run_once(root, options=opts)

                auth_s = self._find_step(result, "auth")
                self.assertEqual(auth_s.status, "skipped")
                self.assertEqual(AuthHandler.calls, 0)
                self.assertEqual(result.last_auth_status, "skipped")
        finally:
            server.shutdown()

    def test_run_once_with_auth_success(self):
        """run_once backend_enabled=True → auth ok."""
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(root, options=opts)

                auth_s = self._find_step(result, "auth")
                self.assertEqual(auth_s.status, "ok")
                self.assertEqual(result.last_auth_status, "ok")
                self.assertGreater(result.auth_attempts, 0)
                self.assertEqual(AuthHandler.calls, 2)  # auth + heartbeat
        finally:
            server.shutdown()

    def test_run_once_auth_fail_fatal(self):
        """run_once auth fail → error, rest of cycle not executed."""
        server, thr, port = _start_server(AuthHandler)
        try:
            AuthHandler.FAIL_CODE = 401

            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(root, options=opts)

                auth_s = self._find_step(result, "auth")
                self.assertEqual(auth_s.status, "error")
                self.assertEqual(result.last_auth_status, "error")
                self.assertEqual(result.status, "error")
        finally:
            server.shutdown()

    def test_run_once_auth_puts_status_in_agent_status(self):
        """agent_status _cycle block contains last_auth_status."""
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                run_once(root, options=opts)

                status_path = Path(root) / "status" / "agent_status.json"
                data = json.loads(status_path.read_text())
                self.assertIn("_cycle", data)
                self.assertEqual(data["_cycle"]["last_auth_status"], "ok")
                self.assertIn("auth_attempts", data["_cycle"])
        finally:
            server.shutdown()

    def test_no_token_in_agent_status(self):
        server, thr, port = _start_server(AuthHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")

                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                run_once(root, options=opts)

                status_path = Path(root) / "status" / "agent_status.json"
                data_str = json.dumps(json.loads(status_path.read_text())).lower()

                self.assertNotIn(TEST_TOKEN, data_str)
                self.assertNotIn(TEST_SECRET, data_str)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, data_str,
                                     f"Forbidden '{fb}' in agent_status")
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
