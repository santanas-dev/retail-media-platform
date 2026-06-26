"""Tests for KsoGatewayHttpClient — fake HTTP server, no real backend."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
from kso_sidecar_agent.kso_gateway_client import (
    KsoGatewayHttpClient,
    _validate_media_ref,
)
from kso_sidecar_agent.kso_manifest_media_sync import (
    KsoMediaDownloadResponse,
    STATUS_OK,
    STATUS_ERROR,
)
from kso_sidecar_agent.token_state import TokenState

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

NOW = 1_750_000_000.0
PNG_BODY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # 108 bytes


def _token_state():
    return TokenState(
        _access_token="opaque-test-key-7890",
        token_type="bearer",
        expires_at=NOW + 3600,
        device_id="550e8400-e29b-41d4-a716-446655440000",
        device_code="a-05954",
        status="active",
    )


def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


# ══════════════════════════════════════════════════════════════════════
# Fake HTTP handlers
# ══════════════════════════════════════════════════════════════════════

class ManifestServedHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/device-gateway/manifest/current"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "status": "served",
                "manifest_version_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                "manifest_hash": "c" * 64,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "schemaVersion": 1,
                    "channel": "kso",
                    "storeCode": "store-01",
                    "deviceCode": "dev-01",
                    "items": [],
                },
            }
            self.wfile.write(json.dumps(resp).encode())
        elif self.path.startswith("/api/device-gateway/media/kso/"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG_BODY)))
            self.end_headers()
            self.wfile.write(PNG_BODY)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # Suppress server logs


class Manifest404Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"detail":"Not found"}')

    def log_message(self, *args):
        pass


class Manifest401Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(401)
        self.end_headers()

    def log_message(self, *args):
        pass


class Media404Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"detail":"Not found"}')

    def log_message(self, *args):
        pass


# ══════════════════════════════════════════════════════════════════════
# Tests: manifest
# ══════════════════════════════════════════════════════════════════════

class TestKsoGatewayClientManifest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread, cls.port = _start_server(ManifestServedHandler)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        config = HttpClientConfig(
            base_url=f"http://127.0.0.1:{self.port}",
            timeout_sec=5,
        )
        self.http = SafeHttpClient(config)
        self.client = KsoGatewayHttpClient(self.http, _token_state())

    def test_fetch_manifest_200(self):
        resp = self.client.fetch_current_manifest()
        self.assertEqual(resp["status"], "served")
        self.assertIn("manifest", resp)

    def test_fetch_manifest_404(self):
        from kso_sidecar_agent.http_client import HttpClientError
        srv, thr, port = _start_server(Manifest404Handler)
        try:
            config = HttpClientConfig(base_url=f"http://127.0.0.1:{port}", timeout_sec=2)
            http = SafeHttpClient(config)
            client = KsoGatewayHttpClient(http, _token_state())
            with self.assertRaises(HttpClientError):
                client.fetch_current_manifest()
        finally:
            srv.shutdown()

    def test_fetch_manifest_401(self):
        from kso_sidecar_agent.http_client import HttpClientError
        srv, thr, port = _start_server(Manifest401Handler)
        try:
            config = HttpClientConfig(base_url=f"http://127.0.0.1:{port}", timeout_sec=2)
            http = SafeHttpClient(config)
            client = KsoGatewayHttpClient(http, _token_state())
            with self.assertRaises(HttpClientError):
                client.fetch_current_manifest()
        finally:
            srv.shutdown()


# ══════════════════════════════════════════════════════════════════════
# Tests: media download
# ══════════════════════════════════════════════════════════════════════

class TestKsoGatewayClientMedia(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread, cls.port = _start_server(ManifestServedHandler)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        config = HttpClientConfig(
            base_url=f"http://127.0.0.1:{self.port}",
            timeout_sec=5,
        )
        self.http = SafeHttpClient(config)
        self.client = KsoGatewayHttpClient(self.http, _token_state())

    def test_download_valid_media(self):
        dl = self.client.download_kso_media("media/current/slot-000")
        self.assertEqual(dl.status, STATUS_OK)
        self.assertEqual(dl.content_type, "image/png")
        self.assertEqual(dl.content_length, len(PNG_BODY))
        self.assertEqual(dl.body, PNG_BODY)

    def test_download_media_404(self):
        srv, thr, port = _start_server(Media404Handler)
        try:
            config = HttpClientConfig(base_url=f"http://127.0.0.1:{port}", timeout_sec=2)
            http = SafeHttpClient(config)
            client = KsoGatewayHttpClient(http, _token_state())
            dl = client.download_kso_media("media/current/slot-000")
            self.assertEqual(dl.status, STATUS_ERROR)
        finally:
            srv.shutdown()


# ══════════════════════════════════════════════════════════════════════
# Tests: mediaRef validation (no HTTP)
# ══════════════════════════════════════════════════════════════════════

class TestMediaRefValidation(unittest.TestCase):

    def test_valid_slot_000(self):
        self.assertIsNone(_validate_media_ref("media/current/slot-000"))

    def test_valid_slot_999(self):
        self.assertIsNone(_validate_media_ref("media/current/slot-999"))

    def test_path_traversal(self):
        self.assertIsNotNone(_validate_media_ref("../etc/passwd"))

    def test_absolute_path(self):
        self.assertIsNotNone(_validate_media_ref("/media/current/slot-000"))

    def test_url(self):
        self.assertIsNotNone(_validate_media_ref("http://evil.com/slot-000"))

    def test_backslash(self):
        self.assertIsNotNone(_validate_media_ref("media\\current\\slot-000"))

    def test_wrong_prefix(self):
        self.assertIsNotNone(_validate_media_ref("creatives/ad.png"))

    def test_real_filename(self):
        self.assertIsNotNone(_validate_media_ref("ad_demo.png"))

    def test_empty(self):
        self.assertIsNotNone(_validate_media_ref(""))

    def test_none(self):
        self.assertIsNotNone(_validate_media_ref(None))

    def test_too_many_digits(self):
        self.assertIsNotNone(_validate_media_ref("media/current/slot-1000"))


# ══════════════════════════════════════════════════════════════════════
# Tests: unsafe mediaRef rejected before HTTP
# ══════════════════════════════════════════════════════════════════════

class TestUnsafeMediaRefNoHTTP(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread, cls.port = _start_server(ManifestServedHandler)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        config = HttpClientConfig(
            base_url=f"http://127.0.0.1:{self.port}",
            timeout_sec=5,
        )
        self.http = SafeHttpClient(config)
        self.client = KsoGatewayHttpClient(self.http, _token_state())

    def test_traversal_returns_error_no_http(self):
        dl = self.client.download_kso_media("../etc/passwd")
        self.assertEqual(dl.status, STATUS_ERROR)
        self.assertEqual(dl.body, b"")

    def test_url_returns_error_no_http(self):
        dl = self.client.download_kso_media("http://evil.com/slot-000")
        self.assertEqual(dl.status, STATUS_ERROR)
        self.assertEqual(dl.body, b"")

    def test_absolute_returns_error_no_http(self):
        dl = self.client.download_kso_media("/media/current/slot-000")
        self.assertEqual(dl.status, STATUS_ERROR)
        self.assertEqual(dl.body, b"")


# ══════════════════════════════════════════════════════════════════════
# Tests: output safety
# ══════════════════════════════════════════════════════════════════════

class TestClientOutputSafety(unittest.TestCase):

    def test_download_response_repr_no_body(self):
        dl = KsoMediaDownloadResponse(
            status=STATUS_OK,
            content_type="image/png",
            content_length=108,
            body=PNG_BODY,
        )
        text = repr(dl)
        self.assertNotIn("PNG", text)
        self.assertNotIn("body", text)
        self.assertNotIn("body_bytes", text)

    def test_media_ref_validator_no_exception(self):
        """Validation returns None/error string, never raises."""
        self.assertIsNotNone(_validate_media_ref("../bad"))
        self.assertIsNone(_validate_media_ref("media/current/slot-000"))

    def test_client_repr_safe(self):
        """Client repr has no secrets — only checks for sensitive data leakage."""
        config = HttpClientConfig(base_url="http://127.0.0.1:18421", timeout_sec=2)
        http = SafeHttpClient(config)
        client = KsoGatewayHttpClient(http, _token_state())
        text = repr(client)
        # Verify no secrets leak into repr
        self.assertNotIn("opaque-test-key", text)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("access_token", text)
        # Note: port numbers in repr are NOT a security concern —
        # they're part of the HttpClientConfig and expected to be visible


if __name__ == "__main__":
    unittest.main()
