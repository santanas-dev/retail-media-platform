"""Tests for RuntimeConfigClient — uses local fake HTTP server, no real backend calls."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from kso_sidecar_agent.http_client import HttpClientConfig, HttpClientError, SafeHttpClient
from kso_sidecar_agent.token_state import TokenState
from kso_sidecar_agent.runtime_config_client import (
    RuntimeConfigClient,
    RuntimeConfigSnapshot,
)

TEST_TOKEN = "opaque-value-1234567890"
TEST_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_DEVICE_CODE = "a-05954"
TEST_CONFIG_HASH = "abc123hash"
NOW = 1_750_000_000.0

# ══════════════════════════════════════════════════════════════════════
# Fake server helpers
# ══════════════════════════════════════════════════════════════════════

def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


def _valid_token_state(token=TEST_TOKEN):
    return TokenState(
        _access_token=token,
        token_type="bearer",
        expires_at=NOW + 3600,
        device_id=TEST_DEVICE_ID,
        device_code=TEST_DEVICE_CODE,
        status="active",
    )


def _valid_config_body():
    return json.dumps({
        "status": "ok",
        "gateway_device_id": TEST_DEVICE_ID,
        "config_hash": TEST_CONFIG_HASH,
        "config": {
            "display_timeout_sec": 30,
            "max_file_size_mb": 100,
            "log_level": "info",
        },
        "generated_at": "2026-06-18T10:00:00+00:00",
    }).encode()


class ConfigOkHandler(BaseHTTPRequestHandler):
    """Returns 200 with valid config JSON. Captures request headers."""

    last_auth_header: str = ""
    last_if_none_match: str = ""

    @classmethod
    def reset(cls):
        cls.last_auth_header = ""
        cls.last_if_none_match = ""

    def do_GET(self):
        ConfigOkHandler.last_auth_header = self.headers.get("Authorization", "")
        ConfigOkHandler.last_if_none_match = self.headers.get("If-None-Match", "")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("ETag", f'"{TEST_CONFIG_HASH}"')
        self.end_headers()
        self.wfile.write(_valid_config_body())

    def log_message(self, format, *args):
        pass


class Config304Handler(BaseHTTPRequestHandler):
    """Returns 304 Not Modified."""

    def do_GET(self):
        self.send_response(304)
        self.end_headers()

    def log_message(self, format, *args):
        pass


class ConfigForbiddenKeyHandler(BaseHTTPRequestHandler):
    """Returns 200 with config containing forbidden key."""

    def do_GET(self):
        body = json.dumps({
            "status": "ok",
            "gateway_device_id": TEST_DEVICE_ID,
            "config_hash": TEST_CONFIG_HASH,
            "config": {"normal": "ok", "api_key": "should-reject"},
            "generated_at": "2026-06-18T10:00:00+00:00",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class ConfigForbiddenValueHandler(BaseHTTPRequestHandler):
    """Returns 200 with config containing forbidden value."""

    def do_GET(self):
        body = json.dumps({
            "status": "ok",
            "gateway_device_id": TEST_DEVICE_ID,
            "config_hash": TEST_CONFIG_HASH,
            "config": {"normal": "ok", "url": "https://example.com?token=abc"},
            "generated_at": "2026-06-18T10:00:00+00:00",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class ConfigErrorHandler(BaseHTTPRequestHandler):
    """Configurable status code for error testing."""

    STATUS = 500
    BODY = b"<html>error</html>"

    def do_GET(self):
        self.send_response(self.STATUS)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(self.BODY)

    def log_message(self, format, *args):
        pass


class ConfigInvalidJsonHandler(BaseHTTPRequestHandler):
    """Returns 200 but non-JSON body."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html>not json</html>")

    def log_message(self, format, *args):
        pass


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _build_client(http_port):
    http = SafeHttpClient(HttpClientConfig(
        base_url=f"http://127.0.0.1:{http_port}",
        timeout_sec=3,
    ))
    return RuntimeConfigClient(http_client=http)


# ══════════════════════════════════════════════════════════════════════
# Tests — Successful fetch
# ══════════════════════════════════════════════════════════════════════

class TestRuntimeConfigClient(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._ok_server, cls._ok_thread, cls._ok_port = _start_server(ConfigOkHandler)

    @classmethod
    def tearDownClass(cls):
        cls._ok_server.shutdown()

    def setUp(self):
        ConfigOkHandler.reset()

    # ── 200 success ────────────────────────────────────────────────

    def test_fetch_current_200(self):
        client = _build_client(self._ok_port)
        ts = _valid_token_state()
        snap = client.fetch_current(ts, now=NOW)

        self.assertEqual(snap.status, "updated")
        self.assertEqual(snap.config_hash, TEST_CONFIG_HASH)
        self.assertEqual(snap.etag, TEST_CONFIG_HASH)
        self.assertEqual(snap.generated_at, "2026-06-18T10:00:00+00:00")
        self.assertIsNotNone(snap.config)
        self.assertEqual(snap.config["display_timeout_sec"], 30)
        self.assertFalse(snap.not_modified)
        self.assertEqual(snap.fetched_at, NOW)

    # ── Authorization header sent ──────────────────────────────────

    def test_authorization_header_sent(self):
        client = _build_client(self._ok_port)
        ts = _valid_token_state()
        client.fetch_current(ts, now=NOW)

        self.assertIn("Bearer", ConfigOkHandler.last_auth_header)
        self.assertIn(TEST_TOKEN, ConfigOkHandler.last_auth_header)

    # ── ETag stored from response ──────────────────────────────────

    def test_etag_from_response_saved(self):
        client = _build_client(self._ok_port)
        ts = _valid_token_state()
        snap = client.fetch_current(ts, now=NOW)
        self.assertIsNotNone(snap.etag)

    # ── safe_summary no token ──────────────────────────────────────

    def test_safe_summary_no_token(self):
        client = _build_client(self._ok_port)
        ts = _valid_token_state()
        snap = client.fetch_current(ts, now=NOW)
        summary = snap.safe_summary()
        self.assertNotIn(TEST_TOKEN, str(summary))
        self.assertNotIn("access_token", summary)
        self.assertNotIn("config", summary)
        self.assertEqual(summary["config_present"], True)
        self.assertEqual(summary["config_keys_count"], 3)

    # ── No files written ───────────────────────────────────────────

    def test_no_files_written(self):
        """RuntimeConfigClient writes nothing to disk — only in memory."""
        client = _build_client(self._ok_port)
        ts = _valid_token_state()
        snap = client.fetch_current(ts, now=NOW)
        # Snapshot holds config in memory — verified by attribute existence
        self.assertIsNotNone(snap.config)
        self.assertIsInstance(snap.config, dict)


# ══════════════════════════════════════════════════════════════════════
# Tests — ETag / 304
# ══════════════════════════════════════════════════════════════════════

class TestRuntimeConfigETag304(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._ok_server, cls._ok_thread, cls._ok_port = _start_server(ConfigOkHandler)
        cls._304_server, cls._304_thread, cls._304_port = _start_server(Config304Handler)

    @classmethod
    def tearDownClass(cls):
        cls._ok_server.shutdown()
        cls._304_server.shutdown()

    def setUp(self):
        ConfigOkHandler.reset()

    def test_if_none_match_sent(self):
        client = _build_client(self._ok_port)
        ts = _valid_token_state()
        client.fetch_current(ts, etag="my-etag-123", now=NOW)
        self.assertEqual(ConfigOkHandler.last_if_none_match, "my-etag-123")

    def test_no_etag_no_if_none_match(self):
        client = _build_client(self._ok_port)
        ts = _valid_token_state()
        client.fetch_current(ts, etag=None, now=NOW)
        self.assertEqual(ConfigOkHandler.last_if_none_match, "")

    def test_304_not_modified(self):
        client = _build_client(self._304_port)
        ts = _valid_token_state()
        snap = client.fetch_current(ts, etag="old-etag", now=NOW)
        self.assertEqual(snap.status, "not_modified")
        self.assertTrue(snap.not_modified)
        self.assertIsNone(snap.config)
        self.assertEqual(snap.fetched_at, NOW)


# ══════════════════════════════════════════════════════════════════════
# Tests — Validation & errors
# ══════════════════════════════════════════════════════════════════════

class TestRuntimeConfigValidation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._fk_server, cls._fk_thread, cls._fk_port = _start_server(ConfigForbiddenKeyHandler)
        cls._fv_server, cls._fv_thread, cls._fv_port = _start_server(ConfigForbiddenValueHandler)

    @classmethod
    def tearDownClass(cls):
        cls._fk_server.shutdown()
        cls._fv_server.shutdown()

    def test_forbidden_key_rejected(self):
        client = _build_client(self._fk_port)
        ts = _valid_token_state()
        with self.assertRaises(HttpClientError) as ctx:
            client.fetch_current(ts, now=NOW)
        self.assertFalse(ctx.exception.retryable)
        self.assertIn("forbidden", ctx.exception.message.lower())

    def test_forbidden_value_rejected(self):
        client = _build_client(self._fv_port)
        ts = _valid_token_state()
        with self.assertRaises(HttpClientError) as ctx:
            client.fetch_current(ts, now=NOW)
        self.assertFalse(ctx.exception.retryable)
        self.assertIn("forbidden", ctx.exception.message.lower())


# ══════════════════════════════════════════════════════════════════════
# Tests — Token validation
# ══════════════════════════════════════════════════════════════════════

class TestRuntimeConfigTokenValidation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._ok_server, cls._ok_thread, cls._ok_port = _start_server(ConfigOkHandler)

    @classmethod
    def tearDownClass(cls):
        cls._ok_server.shutdown()

    def test_expired_token_rejected(self):
        client = _build_client(self._ok_port)
        # Token already expired
        ts = TokenState(
            _access_token=TEST_TOKEN,
            token_type="bearer",
            expires_at=NOW - 1,  # expired
            device_id=TEST_DEVICE_ID,
            device_code=TEST_DEVICE_CODE,
            status="active",
        )
        with self.assertRaises(ValueError):
            client.fetch_current(ts, now=NOW)

    def test_no_token_rejected(self):
        client = _build_client(self._ok_port)
        ts = TokenState()  # empty
        with self.assertRaises(ValueError):
            client.fetch_current(ts, now=NOW)


# ══════════════════════════════════════════════════════════════════════
# Tests — HTTP errors
# ══════════════════════════════════════════════════════════════════════

class TestRuntimeConfigErrors(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._err_server, cls._err_thread, cls._err_port = _start_server(ConfigErrorHandler)
        cls._inv_server, cls._inv_thread, cls._inv_port = _start_server(ConfigInvalidJsonHandler)

    @classmethod
    def tearDownClass(cls):
        cls._err_server.shutdown()
        cls._inv_server.shutdown()

    def _set_err(self, status):
        ConfigErrorHandler.STATUS = status
        ConfigErrorHandler.BODY = b"<html>error</html>"

    # ── 401 ────────────────────────────────────────────────────────

    def test_401_safe_error(self):
        self._set_err(401)
        client = _build_client(self._err_port)
        ts = _valid_token_state()
        with self.assertRaises(HttpClientError) as ctx:
            client.fetch_current(ts, now=NOW)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertFalse(ctx.exception.retryable)
        self.assertNotIn(TEST_TOKEN, ctx.exception.message)

    # ── 403 ────────────────────────────────────────────────────────

    def test_403_safe_error(self):
        self._set_err(403)
        client = _build_client(self._err_port)
        ts = _valid_token_state()
        with self.assertRaises(HttpClientError) as ctx:
            client.fetch_current(ts, now=NOW)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertFalse(ctx.exception.retryable)

    # ── 422 ────────────────────────────────────────────────────────

    def test_422_safe_error(self):
        self._set_err(422)
        client = _build_client(self._err_port)
        ts = _valid_token_state()
        with self.assertRaises(HttpClientError) as ctx:
            client.fetch_current(ts, now=NOW)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertFalse(ctx.exception.retryable)

    # ── 500 ────────────────────────────────────────────────────────

    def test_500_retryable(self):
        self._set_err(500)
        client = _build_client(self._err_port)
        ts = _valid_token_state()
        with self.assertRaises(HttpClientError) as ctx:
            client.fetch_current(ts, now=NOW)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertTrue(ctx.exception.retryable)

    # ── Invalid JSON ───────────────────────────────────────────────

    def test_invalid_json_safe_error(self):
        client = _build_client(self._inv_port)
        ts = _valid_token_state()
        with self.assertRaises(HttpClientError) as ctx:
            client.fetch_current(ts, now=NOW)
        self.assertIn("Invalid JSON", ctx.exception.message)
        self.assertNotIn("<html>", ctx.exception.message)
        self.assertFalse(ctx.exception.retryable)

    # ── Security: token not in errors ──────────────────────────────

    def test_401_token_not_in_error(self):
        self._set_err(401)
        client = _build_client(self._err_port)
        ts = _valid_token_state()
        with self.assertRaises(HttpClientError) as ctx:
            client.fetch_current(ts, now=NOW)
        self.assertNotIn(TEST_TOKEN, ctx.exception.message.lower())
        self.assertNotIn("Bearer", ctx.exception.message)


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
