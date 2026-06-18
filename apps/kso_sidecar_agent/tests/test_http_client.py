"""Tests for SafeHttpClient — uses local http.server, no real backend calls."""

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.http_client import (
    HttpClientConfig, HttpClientError, SafeHttpClient,
)


# ══════════════════════════════════════════════════════════════════════
# Local fake server
# ══════════════════════════════════════════════════════════════════════

def _start_server(handler_class, port=0):
    """Start a threaded HTTP server on a random port. Returns (server, port)."""
    server = HTTPServer(("127.0.0.1", port), handler_class)
    server.port = server.server_address[1]  # store the actual port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.port


class OkHandler(BaseHTTPRequestHandler):
    """Returns 200 with JSON for any request."""
    def do_GET(self):
        self._respond(200, {"status": "ok", "path": self.path})
    def do_POST(self):
        body_len = int(self.headers.get("Content-Length", 0))
        self._respond(200, {"received": json.loads(self.rfile.read(body_len)) if body_len else None})
    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    def log_message(self, format, *args):
        pass  # suppress logs


class ErrorHandler(BaseHTTPRequestHandler):
    """Returns a configurable status code."""
    STATUS = 500
    BODY = b"not json"
    def do_GET(self):
        self.send_response(self.STATUS)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(self.BODY)
    def log_message(self, format, *args):
        pass


class SlowHandler(BaseHTTPRequestHandler):
    """Sleeps before responding."""
    def do_GET(self):
        time.sleep(30)
    def log_message(self, format, *args):
        pass


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestHttpClientConfig(unittest.TestCase):

    def test_valid_config(self):
        cfg = HttpClientConfig(base_url="https://example.com/api/", timeout_sec=10)
        self.assertEqual(cfg.base_url, "https://example.com/api/")

    def test_base_url_adds_slash(self):
        cfg = HttpClientConfig(base_url="https://example.com/api")
        self.assertEqual(cfg.base_url, "https://example.com/api/")

    def test_invalid_scheme_rejected(self):
        for bad in ("ftp://example.com", "file:///tmp", ""):
            with self.assertRaises(ValueError, msg=f"Should reject: {bad}"):
                HttpClientConfig(base_url=bad)

    def test_url_with_password_rejected(self):
        with self.assertRaises(ValueError):
            HttpClientConfig(base_url="https://user:pass@example.com")

    def test_url_with_query_rejected(self):
        with self.assertRaises(ValueError):
            HttpClientConfig(base_url="https://example.com?token=abc")

    def test_timeout_out_of_range_rejected(self):
        for bad in (0, 121, -1):
            with self.assertRaises(ValueError, msg=f"Should reject timeout: {bad}"):
                HttpClientConfig(base_url="https://example.com", timeout_sec=bad)


class TestSafeHttpClient(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._ok_server, cls._ok_thread, cls._ok_port = _start_server(OkHandler)
        cls._err_server, cls._err_thread, cls._err_port = _start_server(lambda *a, **kw: ErrorHandler(*a, **kw))

    @classmethod
    def tearDownClass(cls):
        cls._ok_server.shutdown()
        cls._err_server.shutdown()

    def _ok_client(self):
        return SafeHttpClient(HttpClientConfig(
            base_url=f"http://127.0.0.1:{self._ok_port}",
            timeout_sec=5,
        ))

    def _err_client(self):
        return SafeHttpClient(HttpClientConfig(
            base_url=f"http://127.0.0.1:{self._err_port}",
            timeout_sec=5,
        ))

    # ── Happy paths ────────────────────────────────────────────────

    def test_get_json_ok(self):
        client = self._ok_client()
        resp = client.get_json("/test")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json_body["status"], "ok")
        self.assertEqual(resp.json_body["path"], "/test")
        self.assertGreater(resp.elapsed_ms, 0)

    def test_post_json_ok(self):
        client = self._ok_client()
        resp = client.post_json("/test", {"key": "val"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json_body["received"]["key"], "val")

    # ── Error classification ───────────────────────────────────────

    def test_404_non_retryable(self):
        ErrorHandler.STATUS = 404
        ErrorHandler.BODY = b"not found"
        client = self._err_client()
        with self.assertRaises(HttpClientError) as ctx:
            client.get_json("/missing")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertFalse(ctx.exception.retryable)

    def test_422_non_retryable(self):
        ErrorHandler.STATUS = 422
        ErrorHandler.BODY = b"unprocessable"
        client = self._err_client()
        with self.assertRaises(HttpClientError) as ctx:
            client.get_json("/bad")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertFalse(ctx.exception.retryable)

    def test_429_retryable(self):
        ErrorHandler.STATUS = 429
        ErrorHandler.BODY = b"rate limited"
        client = self._err_client()
        with self.assertRaises(HttpClientError) as ctx:
            client.get_json("/limited")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertTrue(ctx.exception.retryable)

    def test_500_retryable(self):
        ErrorHandler.STATUS = 500
        ErrorHandler.BODY = b"server error"
        client = self._err_client()
        with self.assertRaises(HttpClientError) as ctx:
            client.get_json("/error")
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertTrue(ctx.exception.retryable)

    # ── Security: path validation ──────────────────────────────────

    def test_path_traversal_rejected(self):
        client = self._ok_client()
        for bad in ("/../etc", "/a/../../etc"):
            with self.assertRaises(ValueError, msg=f"Should reject: {bad}"):
                client.get_json(bad)

    def test_path_no_leading_slash_rejected(self):
        client = self._ok_client()
        with self.assertRaises(ValueError):
            client.get_json("no-slash")

    def test_path_forbidden_substring_rejected(self):
        client = self._ok_client()
        for bad in ("/api/token", "/get/secret", "/jwt/decode"):
            with self.assertRaises(ValueError, msg=f"Should reject path: {bad}"):
                client.get_json(bad)

    # ── Security: header validation ────────────────────────────────

    def test_forbidden_header_value_rejected(self):
        client = self._ok_client()
        with self.assertRaises(ValueError):
            client.get_json("/test", headers={"X-Auth": "Bearer my_token"})

    def test_forbidden_header_with_token_value_rejected(self):
        client = self._ok_client()
        with self.assertRaises(ValueError):
            client.get_json("/test", headers={"X-Auth": "my_token_xyz"})

    # ── Invalid JSON response ──────────────────────────────────────

    def test_invalid_json_safe_error(self):
        ErrorHandler.STATUS = 200
        ErrorHandler.BODY = b"<html>not json</html>"
        client = self._err_client()
        with self.assertRaises(HttpClientError) as ctx:
            client.get_json("/html")
        self.assertIn("Invalid JSON", ctx.exception.message)
        self.assertFalse(ctx.exception.retryable)
        # No raw body in error
        self.assertNotIn("<html>", ctx.exception.message)

    # ── Network error retryable ────────────────────────────────────

    def test_connection_refused_retryable(self):
        client = SafeHttpClient(HttpClientConfig(
            base_url="http://127.0.0.1:1",  # unused port
            timeout_sec=2,
        ))
        with self.assertRaises(HttpClientError) as ctx:
            client.get_json("/test")
        self.assertTrue(ctx.exception.retryable)

    # ── HttpResponse.safe_summary ──────────────────────────────────

    def test_safe_summary_no_body(self):
        client = self._ok_client()
        resp = client.get_json("/test")
        summary = resp.safe_summary()
        self.assertEqual(summary["status_code"], 200)
        self.assertNotIn("json_body", summary)
        self.assertNotIn("path", str(summary))

    # ── Auth endpoint allowlist ────────────────────────────────────

    def test_auth_endpoint_allowed(self):
        client = self._ok_client()
        resp = client.post_json("/api/device-gateway/auth/token", {"test": "ok"})
        self.assertEqual(resp.status_code, 200)

    def test_auth_endpoint_extra_rejected(self):
        client = self._ok_client()
        with self.assertRaises(ValueError):
            client.post_json("/api/device-gateway/auth/token/extra", {})

    def test_auth_endpoint_query_rejected(self):
        client = self._ok_client()
        with self.assertRaises(ValueError):
            client.get_json("/api/device-gateway/auth/token?debug=1")

    def test_bare_token_rejected(self):
        client = self._ok_client()
        with self.assertRaises(ValueError):
            client.get_json("/token")

    def test_api_token_rejected(self):
        client = self._ok_client()
        with self.assertRaises(ValueError):
            client.get_json("/api/token")

    def test_secret_path_rejected(self):
        client = self._ok_client()
        with self.assertRaises(ValueError):
            client.get_json("/api/device-gateway/auth/secret")

    def test_request_body_not_in_error(self):
        ErrorHandler.STATUS = 500
        ErrorHandler.BODY = b"error"
        client = self._err_client()
        with self.assertRaises(HttpClientError) as ctx:
            client.post_json(
                "/api/device-gateway/auth/token",
                {"device_secret": "dev-value-1234567890"},
            )
        self.assertNotIn("dev-value-1234567890", ctx.exception.message)

    def test_response_body_not_in_safe_summary(self):
        ErrorHandler.STATUS = 200
        ErrorHandler.BODY = b'{"access_token": "dev-value-1234567890"}'
        client = self._err_client()
        resp = client.get_json("/api/device-gateway/auth/token")
        summary = resp.safe_summary()
        self.assertNotIn("access_token", str(summary).lower())
        self.assertNotIn("dev-value-1234567890", str(summary))

    def test_auth_endpoint_invalid_json_safe(self):
        ErrorHandler.STATUS = 200
        ErrorHandler.BODY = b"<html>not json</html>"
        client = self._err_client()
        with self.assertRaises(HttpClientError) as ctx:
            client.get_json("/api/device-gateway/auth/token")
        self.assertIn("Invalid JSON", ctx.exception.message)
        self.assertNotIn("<html>", ctx.exception.message)


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
