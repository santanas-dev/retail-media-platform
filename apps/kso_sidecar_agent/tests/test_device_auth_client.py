"""Tests for DeviceAuthClient — uses local fake HTTP server, no real backend calls."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.device_auth_client import DeviceAuthClient, HttpClientError
from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
from kso_sidecar_agent.token_state import TokenState

PKG_DIR = Path(__file__).resolve().parent.parent

TEST_SECRET = "dev-value-1234567890"
TEST_TOKEN = "opaque-value-1234567890"
TEST_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_DEVICE_CODE = "a-05954"

NOW = 1_750_000_000.0


# ══════════════════════════════════════════════════════════════════════
# Fake auth server helpers
# ══════════════════════════════════════════════════════════════════════

def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


def _valid_auth_body(token=TEST_TOKEN):
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600,
        "device_id": TEST_DEVICE_ID,
        "device_code": TEST_DEVICE_CODE,
        "status": "active",
    }


class AuthOkHandler(BaseHTTPRequestHandler):
    """Returns 200 with a valid auth response for POST /auth/token only."""

    STATUS = 200

    def do_POST(self):
        body_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(body_len) if body_len else b""
        self.send_response(self.STATUS)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(_valid_auth_body()).encode())

    def log_message(self, format, *args):
        pass


class AuthErrorHandler(AuthOkHandler):
    """Configurable status code, non-JSON body."""

    STATUS = 500
    BODY = b"<html>server error</html>"

    def do_POST(self):
        body_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(body_len) if body_len else b""
        self.send_response(self.STATUS)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(self.BODY)


class AuthInvalidJsonHandler(AuthOkHandler):
    """Returns 200 but non-JSON body."""

    def do_POST(self):
        body_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(body_len) if body_len else b""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html>not json</html>")


class AuthSequenceHandler(BaseHTTPRequestHandler):
    """Stateful handler: returns a configurable sequence of (status, body) per call."""

    SEQUENCE: list = []   # list of (status_code, body_bytes)
    _call_count: int = 0

    @classmethod
    def reset(cls, sequence):
        cls.SEQUENCE = list(sequence)
        cls._call_count = 0

    def do_POST(self):
        body_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(body_len) if body_len else b""
        idx = AuthSequenceHandler._call_count
        AuthSequenceHandler._call_count += 1

        if idx < len(self.SEQUENCE):
            status, body = self.SEQUENCE[idx]
        else:
            status, body = 500, b"exhausted"

        self.send_response(status)
        if status == 200:
            self.send_header("Content-Type", "application/json")
        else:
            self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


# ── Retry helpers ──────────────────────────────────────────────────

from kso_sidecar_agent.retry_backoff import BackoffPolicy, RetryBackoffManager


def _build_retry_client(http_port, secret=TEST_SECRET, max_attempts=3):
    """Build a DeviceAuthClient with retry_manager."""
    auth = _build_client(http_port, secret)
    policy = BackoffPolicy(max_attempts=max_attempts, jitter_ratio=0.0)
    retry_mgr = RetryBackoffManager(policy)
    return auth, retry_mgr


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

_DEV_FLAG = ["--dev-secret-store"]


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


def _make_config_dict(base_url):
    return {
        "backend_base_url": base_url,
        "device_code": TEST_DEVICE_CODE,
        "tls_verify": True,
        "request_timeout_sec": 5,
        "local_interface_version": "1.0",
    }


def _build_client(http_port, secret=TEST_SECRET):
    """Build a DeviceAuthClient pointed at a local fake server."""
    cfg = _make_config_dict(f"http://127.0.0.1:{http_port}")
    http = SafeHttpClient(HttpClientConfig(base_url=cfg["backend_base_url"], timeout_sec=3))
    auth = DeviceAuthClient(
        http_client=http,
        config=cfg,
        secret_reader=lambda: secret,
    )
    return auth


def _setup_agent_root(root, base_url, with_secret=True):
    """Init root + write config + optionally write dev secret."""
    code1, out1, err1 = _run("init-local-root", "--root", root)
    code2, out2, err2 = _run(
        "write-config", "--root", root,
        "--backend-base-url", base_url,
        "--device-code", TEST_DEVICE_CODE,
    )
    if with_secret:
        code3, out3, err3 = _run_stdin(
            TEST_SECRET, "secret-store-set", "--root", root, *_DEV_FLAG, "--stdin",
        )
    return code2  # config write


# ══════════════════════════════════════════════════════════════════════
# Tests — DeviceAuthClient (unit)
# ══════════════════════════════════════════════════════════════════════

class TestDeviceAuthClient(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._ok_server, cls._ok_thread, cls._ok_port = _start_server(AuthOkHandler)

    @classmethod
    def tearDownClass(cls):
        cls._ok_server.shutdown()

    # ── Successful auth ────────────────────────────────────────────

    def test_authenticate_success(self):
        auth = _build_client(self._ok_port)
        ts = auth.authenticate(now=NOW)
        self.assertEqual(ts.device_code, TEST_DEVICE_CODE)
        self.assertEqual(ts.device_id, TEST_DEVICE_ID)
        self.assertEqual(ts.status, "active")
        self.assertTrue(ts.is_valid(now=NOW))
        self.assertTrue(ts.access_token)  # token stored in memory

    def test_authenticate_returns_valid_token_state(self):
        auth = _build_client(self._ok_port)
        ts = auth.authenticate(now=NOW)
        self.assertIsInstance(ts, TokenState)
        self.assertEqual(ts.token_type, "bearer")
        self.assertAlmostEqual(ts.expires_at, NOW + 3600)

    # ── Config errors ──────────────────────────────────────────────

    def test_missing_device_code_in_config(self):
        auth = _build_client(self._ok_port)
        auth._config = {}  # override after creation
        with self.assertRaises(ValueError):
            auth.authenticate()

    def test_empty_secret_raises_runtime_error(self):
        auth = _build_client(self._ok_port, secret="")
        with self.assertRaises(RuntimeError):
            auth.authenticate()

    # ── Token in memory only — not on disk ─────────────────────────

    def test_token_not_written_to_any_file(self):
        """Authenticate then verify no token in agent root files."""
        auth = _build_client(self._ok_port)
        ts = auth.authenticate(now=NOW)

        # The token is in ts.access_token (private), not in any file
        # This is verified by design — DeviceAuthClient never writes files.
        self.assertTrue(ts.access_token)

    def test_safe_summary_contains_no_token(self):
        auth = _build_client(self._ok_port)
        ts = auth.authenticate(now=NOW)
        summary = ts.safe_summary(now=NOW)
        self.assertNotIn("access_token", summary)
        self.assertNotIn(TEST_TOKEN, str(summary))
        self.assertIn("device_code", summary)

    # ── Secret never in output ─────────────────────────────────────

    def test_secret_not_in_safe_summary(self):
        auth = _build_client(self._ok_port)
        ts = auth.authenticate(now=NOW)
        summary = ts.safe_summary(now=NOW)
        self.assertNotIn(TEST_SECRET, str(summary))


# ══════════════════════════════════════════════════════════════════════
# Tests — Error responses (unit)
# ══════════════════════════════════════════════════════════════════════

class TestDeviceAuthClientErrors(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._err_server, cls._err_thread, cls._err_port = _start_server(AuthErrorHandler)

    @classmethod
    def tearDownClass(cls):
        cls._err_server.shutdown()

    def _err_auth(self, status, body=None):
        AuthErrorHandler.STATUS = status
        if body is not None:
            AuthErrorHandler.BODY = body
        else:
            AuthErrorHandler.BODY = f"<html>error {status}</html>".encode()

    # ── 401 ────────────────────────────────────────────────────────

    def test_401_non_retryable(self):
        self._err_auth(401)
        auth = _build_client(self._err_port)
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate()
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertFalse(ctx.exception.retryable)

    # ── 403 ────────────────────────────────────────────────────────

    def test_403_non_retryable(self):
        self._err_auth(403)
        auth = _build_client(self._err_port)
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate()
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertFalse(ctx.exception.retryable)

    # ── 422 ────────────────────────────────────────────────────────

    def test_422_non_retryable(self):
        self._err_auth(422)
        auth = _build_client(self._err_port)
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate()
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertFalse(ctx.exception.retryable)

    # ── 500 ────────────────────────────────────────────────────────

    def test_500_retryable(self):
        self._err_auth(500)
        auth = _build_client(self._err_port)
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate()
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertTrue(ctx.exception.retryable)

    # ── Invalid JSON ───────────────────────────────────────────────

    def test_invalid_json_safe_error(self):
        self._err_auth(200, body=b"<html>not json at all</html>")
        auth = _build_client(self._err_port)
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate()
        self.assertIn("Invalid JSON", ctx.exception.message)
        self.assertNotIn("<html>", ctx.exception.message)
        self.assertFalse(ctx.exception.retryable)

    # ── Security: body never in error ──────────────────────────────

    def test_error_no_request_body_dump(self):
        self._err_auth(500)
        auth = _build_client(self._err_port)
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate()
        # Error message must not leak secret
        self.assertNotIn(TEST_SECRET, ctx.exception.message)
        self.assertNotIn("device_secret", ctx.exception.message)

    def test_error_no_response_body_dump(self):
        self._err_auth(200, body=b'{"access_token":"leaked-token-should-not-appear"}')
        auth = _build_client(self._err_port)
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate()
        self.assertNotIn("leaked-token-should-not-appear", ctx.exception.message)

    # ── No stacktrace ──────────────────────────────────────────────

    def test_no_stacktrace_in_error(self):
        self._err_auth(401)
        auth = _build_client(self._err_port)
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate()
        self.assertNotIn("Traceback", str(ctx.exception))
        self.assertNotIn("File ", str(ctx.exception))


# ══════════════════════════════════════════════════════════════════════
# Tests — Retry integration
# ══════════════════════════════════════════════════════════════════════

class TestDeviceAuthRetry(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._seq_server, cls._seq_thread, cls._seq_port = _start_server(AuthSequenceHandler)
        cls._ok_body = json.dumps(_valid_auth_body()).encode()

    @classmethod
    def tearDownClass(cls):
        cls._seq_server.shutdown()

    def setUp(self):
        self.slept: list = []

    def _fake_sleep(self, sec):
        self.slept.append(sec)

    # ── Without retry_manager — single call ────────────────────────

    def test_no_retry_manager_single_call(self):
        auth, _ = _build_retry_client(self._seq_port)
        AuthSequenceHandler.reset([(200, self._ok_body)])
        ts = auth.authenticate(now=NOW)
        self.assertTrue(ts.is_valid(now=NOW))
        self.assertEqual(auth.last_attempts, 1)
        self.assertEqual(AuthSequenceHandler._call_count, 1)

    # ── 500 → 500 → 200: success after 2 retries ───────────────────

    def test_retry_500_twice_then_success(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=3)
        AuthSequenceHandler.reset([
            (500, b"bang"),
            (500, b"bang"),
            (200, self._ok_body),
        ])
        ts = auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertTrue(ts.is_valid(now=NOW))
        self.assertEqual(auth.last_attempts, 3)
        self.assertEqual(AuthSequenceHandler._call_count, 3)
        self.assertEqual(len(self.slept), 2)  # slept after attempts 1 and 2

    # ── 429 → 200: success after 1 retry ───────────────────────────

    def test_retry_429_then_success(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=3)
        AuthSequenceHandler.reset([
            (429, b"rate limited"),
            (200, self._ok_body),
        ])
        ts = auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertTrue(ts.is_valid(now=NOW))
        self.assertEqual(auth.last_attempts, 2)
        self.assertEqual(len(self.slept), 1)

    # ── 500 exhaust ────────────────────────────────────────────────

    def test_retry_500_exhaust(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=3)
        AuthSequenceHandler.reset([
            (500, b"bang"),
            (500, b"bang"),
            (500, b"bang"),
        ])
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(auth.last_attempts, 3)
        self.assertEqual(AuthSequenceHandler._call_count, 3)
        self.assertEqual(len(self.slept), 2)

    # ── Non-retryable: 401 ─────────────────────────────────────────

    def test_401_no_retry(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=3)
        AuthSequenceHandler.reset([(401, b"unauthorized")])
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(auth.last_attempts, 1)
        self.assertEqual(AuthSequenceHandler._call_count, 1)
        self.assertEqual(len(self.slept), 0)

    # ── Non-retryable: 403 ─────────────────────────────────────────

    def test_403_no_retry(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=3)
        AuthSequenceHandler.reset([(403, b"forbidden")])
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(auth.last_attempts, 1)
        self.assertEqual(len(self.slept), 0)

    # ── Non-retryable: 422 ─────────────────────────────────────────

    def test_422_no_retry(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=3)
        AuthSequenceHandler.reset([(422, b"validation")])
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(auth.last_attempts, 1)
        self.assertEqual(len(self.slept), 0)

    # ── Non-retryable: invalid JSON ────────────────────────────────

    def test_invalid_json_no_retry(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=3)
        AuthSequenceHandler.reset([(200, b"<html>bad</html>")])
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(auth.last_attempts, 1)
        self.assertEqual(len(self.slept), 0)

    # ── Non-retryable: missing secret ──────────────────────────────

    def test_missing_secret_no_retry(self):
        auth, _ = _build_retry_client(self._seq_port, secret="", max_attempts=3)
        with self.assertRaises(RuntimeError):
            auth.authenticate(now=NOW)
        self.assertEqual(auth.last_attempts, 0)  # never tried

    # ── Security: no secret/token in errors ────────────────────────

    def test_retry_error_no_secret(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=2)
        AuthSequenceHandler.reset([(500, b"explosion")])
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertNotIn(TEST_SECRET, ctx.exception.message)

    def test_retry_error_no_token(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=2)
        AuthSequenceHandler.reset([(500, b"explosion")])
        with self.assertRaises(HttpClientError) as ctx:
            auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        self.assertNotIn(TEST_TOKEN, ctx.exception.message)

    # ── Fake sleep receives correct delays ─────────────────────────

    def test_fake_sleep_called_with_expected_delays(self):
        auth, retry_mgr = _build_retry_client(self._seq_port, max_attempts=3)
        AuthSequenceHandler.reset([
            (500, b"a"),
            (500, b"b"),
            (200, self._ok_body),
        ])
        auth.authenticate(now=NOW, retry_manager=retry_mgr, sleep_fn=self._fake_sleep)
        # Delays: after attempt 1 delay for attempt 2 = base*2^1 = 4.0
        #         after attempt 2 delay for attempt 3 = base*2^2 = 8.0
        self.assertEqual(len(self.slept), 2)
        self.assertAlmostEqual(self.slept[0], 4.0)
        self.assertAlmostEqual(self.slept[1], 8.0)


# ══════════════════════════════════════════════════════════════════════
# Tests — CLI auth-check (integration via subprocess)
# ══════════════════════════════════════════════════════════════════════

class TestCLIAuthCheck(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._ok_server, cls._ok_thread, cls._ok_port = _start_server(AuthOkHandler)

    @classmethod
    def tearDownClass(cls):
        cls._ok_server.shutdown()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        base_url = f"http://127.0.0.1:{self._ok_port}"
        _setup_agent_root(self.root, base_url, with_secret=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _base_url(self):
        return f"http://127.0.0.1:{self._ok_port}"

    # ── Happy path ─────────────────────────────────────────────────

    def test_auth_check_success(self):
        code, out, err = _run("auth-check", "--root", self.root, *_DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("authenticated:", out)
        self.assertIn("True", out)
        self.assertIn(f"device_code:       {TEST_DEVICE_CODE}", out)
        self.assertIn(TEST_DEVICE_ID, out)
        self.assertIn("active", out)

    def test_auth_check_token_not_in_stdout(self):
        code, out, err = _run("auth-check", "--root", self.root, *_DEV_FLAG)
        self.assertNotIn(TEST_TOKEN, out, "Token leaked to stdout")
        self.assertNotIn("access_token", out, "access_token leaked to stdout")

    def test_auth_check_token_not_in_stderr(self):
        code, out, err = _run("auth-check", "--root", self.root, *_DEV_FLAG)
        self.assertNotIn(TEST_TOKEN, err, "Token leaked to stderr")

    def test_auth_check_secret_not_in_output(self):
        code, out, err = _run("auth-check", "--root", self.root, *_DEV_FLAG)
        combined = out + err
        self.assertNotIn(TEST_SECRET, combined, "Secret leaked to output")

    # ── Token not written to disk ──────────────────────────────────

    def test_auth_check_token_not_in_config_file(self):
        _run("auth-check", "--root", self.root, *_DEV_FLAG)
        content = (Path(self.root) / "config" / "agent_config.json").read_text()
        self.assertNotIn(TEST_TOKEN, content)

    def test_auth_check_token_not_in_status_file(self):
        _run("auth-check", "--root", self.root, *_DEV_FLAG)
        content = (Path(self.root) / "status" / "agent_status.json").read_text()
        self.assertNotIn(TEST_TOKEN, content)

    # ── Error cases ────────────────────────────────────────────────

    def test_auth_check_no_config(self):
        tmp2 = tempfile.TemporaryDirectory()
        root2 = tmp2.name
        _run("init-local-root", "--root", root2)
        code, out, err = _run("auth-check", "--root", root2, *_DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("Config", err)
        tmp2.cleanup()

    def test_auth_check_no_secret(self):
        tmp2 = tempfile.TemporaryDirectory()
        root2 = tmp2.name
        _setup_agent_root(root2, self._base_url(), with_secret=False)
        code, out, err = _run("auth-check", "--root", root2, *_DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("secret", (out + err).lower())
        tmp2.cleanup()

    def test_auth_check_without_dev_flag_rejected(self):
        code, out, err = _run("auth-check", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("disabled", (out + err).lower())

    # ── No stacktrace ──────────────────────────────────────────────

    def test_auth_check_no_traceback_on_error(self):
        tmp2 = tempfile.TemporaryDirectory()
        root2 = tmp2.name
        _run("init-local-root", "--root", root2)
        code, out, err = _run("auth-check", "--root", root2, *_DEV_FLAG)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Traceback", err)
        tmp2.cleanup()


# ══════════════════════════════════════════════════════════════════════
# Tests — 401/403/422 via CLI
# ══════════════════════════════════════════════════════════════════════

class TestCLIAuthCheckErrors(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._err_server, cls._err_thread, cls._err_port = _start_server(AuthErrorHandler)

    @classmethod
    def tearDownClass(cls):
        cls._err_server.shutdown()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        base_url = f"http://127.0.0.1:{self._err_port}"
        _setup_agent_root(self.root, base_url, with_secret=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _check_error(self, status, expected_http_code=None):
        AuthErrorHandler.STATUS = status
        AuthErrorHandler.BODY = b"server error"
        code, out, err = _run("auth-check", "--root", self.root, *_DEV_FLAG)
        self.assertNotEqual(code, 0, f"Expected non-zero for HTTP {status}, got stdout={out}")
        # Error message must not contain secret
        combined = out + err
        self.assertNotIn(TEST_SECRET, combined)
        self.assertNotIn(TEST_TOKEN, combined)
        # Should mention auth failure
        self.assertIn("auth failed", (out + err).lower(), f"Expected 'auth failed' in: {out+err}")

    def test_401_via_cli(self):
        self._check_error(401)

    def test_403_via_cli(self):
        self._check_error(403)

    def test_422_via_cli(self):
        self._check_error(422)

    def test_500_via_cli(self):
        self._check_error(500)

    def test_invalid_json_via_cli(self):
        AuthErrorHandler.STATUS = 200
        AuthErrorHandler.BODY = b"<html>not json</html>"
        code, out, err = _run("auth-check", "--root", self.root, *_DEV_FLAG)
        self.assertNotEqual(code, 0, f"Should fail on invalid JSON, got stdout={out}")
        combined = out + err
        self.assertNotIn("<html>", combined)


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
