"""Tests for run_cycle_runtime_config.py — fake HTTP server, no real backend."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.run_cycle import FORBIDDEN_SUBSTRINGS, RunCycleOptions
from kso_sidecar_agent.run_cycle_runtime_config import sync_runtime_config_for_cycle
from kso_sidecar_agent.token_state import TokenState

PKG_DIR = Path(__file__).resolve().parent.parent
TEST_SECRET = "dev-value-1234567890"
TEST_TOKEN = "opaque-value-1234567890"
TEST_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_DEVICE_CODE = "a-05954"
NOW = 1_750_000_000.0
RC_CONFIG_HASH = "a" * 64
RC_CONFIG = {"key1": "value1"}


def _valid_token_state():
    return TokenState(
        _access_token=TEST_TOKEN, token_type="bearer",
        expires_at=NOW + 3600, device_id=TEST_DEVICE_ID,
        device_code=TEST_DEVICE_CODE, status="active",
    )


def _expired_token_state():
    return TokenState(
        _access_token=TEST_TOKEN, token_type="bearer",
        expires_at=NOW - 3600, device_id=TEST_DEVICE_ID,
        device_code=TEST_DEVICE_CODE, status="active",
    )


def _valid_auth_body():
    return json.dumps({
        "access_token": TEST_TOKEN, "token_type": "bearer",
        "expires_in": 3600, "device_id": TEST_DEVICE_ID,
        "device_code": TEST_DEVICE_CODE, "status": "active",
    }).encode()


def _setup_root_with_config(root, base_url, with_secret=True):
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


class RCStepHandler(BaseHTTPRequestHandler):
    AUTH_FAIL = None
    RC_FAIL = None
    RC_NOT_MODIFIED = False
    RC_INVALID_JSON = False
    RC_FORBIDDEN_KEY = False
    auth_calls = 0
    rc_calls = 0

    @classmethod
    def reset(cls):
        cls.AUTH_FAIL = None
        cls.RC_FAIL = None
        cls.RC_NOT_MODIFIED = False
        cls.RC_INVALID_JSON = False
        cls.RC_FORBIDDEN_KEY = False
        cls.auth_calls = 0
        cls.rc_calls = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        RCStepHandler.auth_calls += 1
        if self.AUTH_FAIL:
            self.send_response(self.AUTH_FAIL)
            self.end_headers()
            self.wfile.write(b'{"error":"auth fail"}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(_valid_auth_body())

    def do_GET(self):
        RCStepHandler.rc_calls += 1
        if self.RC_FAIL:
            self.send_response(self.RC_FAIL)
            self.end_headers()
            self.wfile.write(b'{"error":"fail"}')
            return
        if self.RC_NOT_MODIFIED:
            self.send_response(304)
            self.end_headers()
            return
        if self.RC_INVALID_JSON:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>not json</html>")
            return
        config = dict(RC_CONFIG)
        if self.RC_FORBIDDEN_KEY:
            config["access_token"] = "should-be-rejected"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok", "config_hash": RC_CONFIG_HASH,
            "config": config,
            "generated_at": "2026-06-19T10:00:00+00:00",
        }).encode())


class TestSyncRCForCycle(unittest.TestCase):
    def setUp(self):
        RCStepHandler.reset()

    def test_sync_200_saves(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                ts = _valid_token_state()
                result = sync_runtime_config_for_cycle(root, ts, now=NOW)
                self.assertEqual(result.step.status, "ok")
                self.assertEqual(result.config_status, "updated")
                rc_path = Path(root) / "config" / "runtime_config.json"
                self.assertTrue(rc_path.exists())
                data = json.loads(rc_path.read_text())
                self.assertEqual(data["config_hash"], RC_CONFIG_HASH)
        finally:
            server.shutdown()

    def test_304_not_modified(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            RCStepHandler.RC_NOT_MODIFIED = True
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                rc_path = Path(root) / "config" / "runtime_config.json"
                rc_path.parent.mkdir(parents=True, exist_ok=True)
                rc_path.write_text(json.dumps({
                    "config_hash": RC_CONFIG_HASH, "etag": "old-etag",
                    "config": RC_CONFIG,
                    "generated_at": "2026-06-19T09:00:00Z",
                    "fetched_at": "2026-06-19T09:00:00Z",
                }))
                ts = _valid_token_state()
                result = sync_runtime_config_for_cycle(root, ts, now=NOW)
                self.assertEqual(result.config_status, "not_modified")
                self.assertEqual(result.step.status, "ok")
                self.assertTrue(result.step.safe_details.get("not_modified"))
        finally:
            server.shutdown()

    def test_expired_token(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_root_with_config(root, "http://127.0.0.1:9999")
            ts = _expired_token_state()
            result = sync_runtime_config_for_cycle(root, ts, now=NOW)
            self.assertEqual(result.step.status, "error")
            self.assertEqual(result.config_status, "error")
            self.assertEqual(RCStepHandler.rc_calls, 0)

    def test_rc_500(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            RCStepHandler.RC_FAIL = 500
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                ts = _valid_token_state()
                result = sync_runtime_config_for_cycle(root, ts, now=NOW)
                self.assertEqual(result.step.status, "error")
                self.assertFalse(result.step.fatal)
                self.assertEqual(result.config_status, "error")
        finally:
            server.shutdown()

    def test_rc_403(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            RCStepHandler.RC_FAIL = 403
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                ts = _valid_token_state()
                result = sync_runtime_config_for_cycle(root, ts, now=NOW)
                self.assertEqual(result.step.status, "error")
                self.assertFalse(result.step.fatal)
        finally:
            server.shutdown()

    def test_invalid_json(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            RCStepHandler.RC_INVALID_JSON = True
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                ts = _valid_token_state()
                result = sync_runtime_config_for_cycle(root, ts, now=NOW)
                self.assertEqual(result.step.status, "error")
                self.assertNotIn("<html>", result.step.message)
        finally:
            server.shutdown()

    def test_forbidden_key(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            RCStepHandler.RC_FORBIDDEN_KEY = True
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                ts = _valid_token_state()
                result = sync_runtime_config_for_cycle(root, ts, now=NOW)
                self.assertEqual(result.step.status, "error")
                self.assertEqual(result.config_status, "error")
        finally:
            server.shutdown()

    def test_no_token_in_step(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                ts = _valid_token_state()
                result = sync_runtime_config_for_cycle(root, ts, now=NOW)
                step_str = str(result.step).lower()
                self.assertNotIn(TEST_TOKEN, step_str)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, step_str, f"Forbidden '{fb}' in rc step")
        finally:
            server.shutdown()

    def test_no_full_config_in_details(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                ts = _valid_token_state()
                result = sync_runtime_config_for_cycle(root, ts, now=NOW)
                details_str = str(result.step.safe_details)
                self.assertNotIn("value1", details_str)
        finally:
            server.shutdown()


class TestRunOnceWithRC(unittest.TestCase):
    def setUp(self):
        RCStepHandler.reset()

    def _find_step(self, result, name):
        return next((s for s in result.steps if s.name == name), None)

    def test_local_only_no_rc(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                run_once(root, options=opts)
                self.assertEqual(RCStepHandler.rc_calls, 0)
        finally:
            server.shutdown()

    def test_run_once_rc_success(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(root, options=opts)
                self.assertEqual(result.last_auth_status, "ok")
                self.assertEqual(result.runtime_config_status, "updated")
                rc_s = self._find_step(result, "runtime_config")
                self.assertEqual(rc_s.status, "ok")
                status_path = Path(root) / "status" / "agent_status.json"
                data = json.loads(status_path.read_text())
                self.assertEqual(data["_cycle"]["runtime_config_status"], "updated")
        finally:
            server.shutdown()

    def test_auth_fail_rc_skipped(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            RCStepHandler.AUTH_FAIL = 401
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(root, options=opts)
                self.assertEqual(result.last_auth_status, "error")
                self.assertEqual(RCStepHandler.rc_calls, 0)
                rc_s = self._find_step(result, "runtime_config")
                self.assertEqual(rc_s.status, "skipped")
        finally:
            server.shutdown()

    def test_rc_500_warning(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            RCStepHandler.RC_FAIL = 500
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(root, options=opts)
                self.assertEqual(result.runtime_config_status, "error")
                rc_s = self._find_step(result, "runtime_config")
                self.assertEqual(rc_s.status, "error")
                self.assertFalse(rc_s.fatal)
        finally:
            server.shutdown()

    def test_no_token_in_agent_status(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                run_once(root, options=opts)
                status_path = Path(root) / "status" / "agent_status.json"
                data_str = json.dumps(json.loads(status_path.read_text())).lower()
                self.assertNotIn(TEST_TOKEN, data_str)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, data_str, f"Forbidden '{fb}' in agent_status")
        finally:
            server.shutdown()

    def test_local_only_cli_no_rc(self):
        server, thr, port = _start_server(RCStepHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root_with_config(root, f"http://127.0.0.1:{port}")
                env = {**os.environ}
                player_path = str(PKG_DIR.parent / "kso_player")
                existing = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = f"{player_path}:{existing}" if existing else player_path
                r = subprocess.run(
                    [sys.executable, "-m", "kso_sidecar_agent.cli",
                     "run-once", "--root", root, "--local-only"],
                    capture_output=True, text=True, cwd=str(PKG_DIR), timeout=15,
                    env=env,
                )
                self.assertEqual(RCStepHandler.rc_calls, 0)
                self.assertEqual(RCStepHandler.auth_calls, 0)
                self.assertIn("run_cycle:", r.stdout)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
