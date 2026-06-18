"""Tests for MediaClient — uses local fake HTTP server, no real backend."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

TEST_TOKEN = "opaque-value-1234567890"
TEST_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_DEVICE_CODE = "a-05954"
TEST_MANIFEST_ITEM_ID = "11111111-1111-1111-1111-111111111111"
TEST_SHA256 = "a" * 64
NOW = 1_750_000_000.0

# Valid media content (small PNG-like bytes)
TEST_CONTENT = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_CONTENT_SHA256 = None  # computed later


def _import_sha256():
    import hashlib
    return hashlib.sha256


def _valid_token_state(token=TEST_TOKEN):
    from kso_sidecar_agent.token_state import TokenState
    return TokenState(
        _access_token=token, token_type="bearer", expires_at=NOW + 3600,
        device_id=TEST_DEVICE_ID, device_code=TEST_DEVICE_CODE, status="active",
    )


def _expired_token_state():
    from kso_sidecar_agent.token_state import TokenState
    return TokenState(
        _access_token=TEST_TOKEN, token_type="bearer", expires_at=NOW - 3600,
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


def _valid_metadata_body(sha256=TEST_SHA256):
    return json.dumps({
        "status": "ok",
        "manifest_item_id": TEST_MANIFEST_ITEM_ID,
        "media": {
            "sha256": sha256,
            "content_type": "image/png",
            "size_bytes": len(TEST_CONTENT),
            "duration_ms": 5000,
        },
    }).encode()


def _valid_metadata_not_modified():
    return json.dumps({
        "status": "not_modified",
        "manifest_item_id": TEST_MANIFEST_ITEM_ID,
        "sha256": TEST_SHA256,
    }).encode()


class MediaHandler(BaseHTTPRequestHandler):
    """Handles /media/{id} and /media/{id}/metadata endpoints."""

    FAIL_CODE = None          # int: fail ALL requests with this code
    METADATA_FAIL = None      # int: fail metadata only
    MEDIA_FAIL = None         # int: fail media download only
    INVALID_JSON = False      # return HTML instead of JSON
    CUSTOM_METADATA = None    # dict: custom metadata response
    CUSTOM_CONTENT = None     # bytes: custom media content
    SKIP_CONTENT_TYPE = False # omit Content-Type header
    WRONG_CONTENT_LENGTH = False  # send wrong Content-Length
    SKIP_SHA256_HEADER = False    # omit X-Content-SHA256 header entirely
    WRONG_SHA256_HEADER = False   # send wrong X-Content-SHA256 (deliberate mismatch)
    last_auth_header = ""
    calls = 0

    @classmethod
    def reset(cls):
        cls.FAIL_CODE = None
        cls.METADATA_FAIL = None
        cls.MEDIA_FAIL = None
        cls.INVALID_JSON = False
        cls.CUSTOM_METADATA = None
        cls.CUSTOM_CONTENT = None
        cls.SKIP_CONTENT_TYPE = False
        cls.WRONG_CONTENT_LENGTH = False
        cls.SKIP_SHA256_HEADER = False
        cls.WRONG_SHA256_HEADER = False
        cls.last_auth_header = ""
        cls.calls = 0

    def log_message(self, *args):
        pass  # suppress server logs

    def do_GET(self):
        MediaHandler.last_auth_header = self.headers.get("Authorization", "")
        MediaHandler.calls += 1

        # Fail all
        if self.FAIL_CODE is not None:
            self.send_response(self.FAIL_CODE)
            self.end_headers()
            self.wfile.write(b'{"error":"fail"}')
            return

        # Metadata endpoint
        if self.path.endswith("/metadata"):
            if self.METADATA_FAIL is not None:
                self.send_response(self.METADATA_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"metadata fail"}')
                return
            if self.INVALID_JSON:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>not json</html>")
                return
            if self.CUSTOM_METADATA is not None:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(self.CUSTOM_METADATA).encode())
                return
            # Valid metadata
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_valid_metadata_body())
            return

        # Media download endpoint
        if self.MEDIA_FAIL is not None:
            self.send_response(self.MEDIA_FAIL)
            self.end_headers()
            self.wfile.write(b'{"error":"media fail"}')
            return

        content = self.CUSTOM_CONTENT or TEST_CONTENT
        self.send_response(200)
        if not self.SKIP_CONTENT_TYPE:
            self.send_header("Content-Type", "image/png")
        cl = len(content)
        if self.WRONG_CONTENT_LENGTH:
            self.send_header("Content-Length", str(cl + 100))
        else:
            self.send_header("Content-Length", str(cl))
        if not self.SKIP_SHA256_HEADER:
            import hashlib
            actual_sha = hashlib.sha256(content).hexdigest()
            if self.WRONG_SHA256_HEADER:
                self.send_header("X-Content-SHA256", "b" * 64)
            else:
                self.send_header("X-Content-SHA256", actual_sha)
        self.end_headers()
        self.wfile.write(content)


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestMediaMetadata(unittest.TestCase):

    def setUp(self):
        MediaHandler.reset()

    def _make_client(self, port):
        from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
        from kso_sidecar_agent.media_client import MediaClient
        config = HttpClientConfig(base_url=f"http://127.0.0.1:{port}")
        http = SafeHttpClient(config)
        return MediaClient(http)

    # ── fetch_metadata success ──────────────────────────────────────

    def test_fetch_metadata_success(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            result = client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.sha256, TEST_SHA256)
            self.assertEqual(result.content_type, "image/png")
            self.assertEqual(result.size_bytes, len(TEST_CONTENT))
            self.assertEqual(result.duration_ms, 5000)
            self.assertIsNotNone(result.fetched_at)
        finally:
            server.shutdown()

    def test_fetch_metadata_auth_header_sent(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn(TEST_TOKEN, MediaHandler.last_auth_header)
        finally:
            server.shutdown()

    def test_safe_summary_no_token_no_auth(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            result = client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            summary = result.safe_summary()
            # No full sha256
            self.assertNotIn(TEST_SHA256, str(summary))
            # No token
            self.assertNotIn(TEST_TOKEN, str(summary))
            # No Authorization
            self.assertNotIn("Authorization", str(summary))
            self.assertNotIn("Bearer", str(summary))
        finally:
            server.shutdown()

    def test_fetch_metadata_not_modified(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.CUSTOM_METADATA = {
                "status": "not_modified",
                "manifest_item_id": TEST_MANIFEST_ITEM_ID,
                "sha256": TEST_SHA256,
            }
            client = self._make_client(port)
            ts = _valid_token_state()
            result = client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(result.status, "not_modified")
            self.assertEqual(result.sha256, TEST_SHA256)
        finally:
            server.shutdown()

    # ── fetch_metadata errors ───────────────────────────────────────

    def test_fetch_metadata_expired_token_no_http(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _expired_token_state()
            with self.assertRaises(ValueError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("expired", str(ctx.exception).lower())
            # HTTP request was never made
            self.assertEqual(MediaHandler.calls, 0)
        finally:
            server.shutdown()

    def test_fetch_metadata_invalid_uuid(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            with self.assertRaises(ValueError) as ctx:
                client.fetch_metadata(ts, "not-a-uuid", now=NOW)
            self.assertIn("UUID", str(ctx.exception))
            self.assertEqual(MediaHandler.calls, 0)
        finally:
            server.shutdown()

    def test_fetch_metadata_401(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.METADATA_FAIL = 401
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertFalse(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_metadata_403(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.METADATA_FAIL = 403
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 403)
        finally:
            server.shutdown()

    def test_fetch_metadata_404(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.METADATA_FAIL = 404
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 404)
        finally:
            server.shutdown()

    def test_fetch_metadata_422(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.METADATA_FAIL = 422
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 422)
        finally:
            server.shutdown()

    def test_fetch_metadata_500_retryable(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.METADATA_FAIL = 500
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertTrue(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_metadata_invalid_json(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.INVALID_JSON = True
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("Invalid JSON", str(ctx.exception))
            # No body dump
            self.assertNotIn("<html>", str(ctx.exception))
        finally:
            server.shutdown()

    def test_fetch_metadata_invalid_sha256(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.CUSTOM_METADATA = {
                "status": "ok",
                "manifest_item_id": TEST_MANIFEST_ITEM_ID,
                "media": {
                    "sha256": "bad",
                    "content_type": "image/png",
                    "size_bytes": 100,
                },
            }
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("64 hex", str(ctx.exception).lower())
            self.assertFalse(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_metadata_invalid_content_type(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.CUSTOM_METADATA = {
                "status": "ok",
                "manifest_item_id": TEST_MANIFEST_ITEM_ID,
                "media": {
                    "sha256": TEST_SHA256,
                    "content_type": "application/x-evil",
                    "size_bytes": 100,
                },
            }
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("not in allowed", str(ctx.exception).lower())
        finally:
            server.shutdown()

    def test_fetch_metadata_negative_size(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.CUSTOM_METADATA = {
                "status": "ok",
                "manifest_item_id": TEST_MANIFEST_ITEM_ID,
                "media": {
                    "sha256": TEST_SHA256,
                    "content_type": "image/png",
                    "size_bytes": -1,
                },
            }
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("-1", str(ctx.exception))
            self.assertFalse(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_metadata_missing_media_object(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.CUSTOM_METADATA = {
                "status": "ok",
                "manifest_item_id": TEST_MANIFEST_ITEM_ID,
            }
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("missing", str(ctx.exception).lower())
        finally:
            server.shutdown()


class TestMediaContent(unittest.TestCase):

    def setUp(self):
        MediaHandler.reset()

    def _make_client(self, port):
        from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
        from kso_sidecar_agent.media_client import MediaClient
        config = HttpClientConfig(base_url=f"http://127.0.0.1:{port}")
        http = SafeHttpClient(config)
        return MediaClient(http)

    # ── fetch_media success ─────────────────────────────────────────

    def test_fetch_media_success(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            result = client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(result.size_bytes, len(TEST_CONTENT))
            self.assertEqual(result.content_type, "image/png")
            self.assertEqual(len(result.content), len(TEST_CONTENT))
            # Actual sha256 computed
            self.assertTrue(len(result.sha256) == 64)
            self.assertIsNotNone(result.fetched_at)
        finally:
            server.shutdown()

    def test_fetch_media_auth_header_sent(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn(TEST_TOKEN, MediaHandler.last_auth_header)
        finally:
            server.shutdown()

    def test_safe_summary_no_token_no_content(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            result = client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            summary = result.safe_summary()
            # No content bytes
            str_summary = str(summary)
            self.assertNotIn(TEST_CONTENT.decode("latin-1"), str_summary)
            # No token
            self.assertNotIn(TEST_TOKEN, str_summary)
            # No Authorization
            self.assertNotIn("Authorization", str_summary)
            self.assertNotIn("Bearer", str_summary)
        finally:
            server.shutdown()

    def test_fetch_media_with_expected_sha256_match(self):
        import hashlib
        actual_sha = hashlib.sha256(TEST_CONTENT).hexdigest()
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            result = client.fetch_media(
                ts, TEST_MANIFEST_ITEM_ID,
                expected_sha256=actual_sha, now=NOW,
            )
            self.assertEqual(result.sha256, actual_sha)
        finally:
            server.shutdown()

    def test_fetch_media_with_expected_size_match(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            result = client.fetch_media(
                ts, TEST_MANIFEST_ITEM_ID,
                expected_size_bytes=len(TEST_CONTENT), now=NOW,
            )
            self.assertEqual(result.size_bytes, len(TEST_CONTENT))
        finally:
            server.shutdown()

    def test_fetch_media_with_expected_content_type_match(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            result = client.fetch_media(
                ts, TEST_MANIFEST_ITEM_ID,
                expected_content_type="image/png", now=NOW,
            )
            self.assertEqual(result.content_type, "image/png")
        finally:
            server.shutdown()

    # ── fetch_media errors ──────────────────────────────────────────

    def test_fetch_media_expired_token_no_http(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _expired_token_state()
            with self.assertRaises(ValueError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("expired", str(ctx.exception).lower())
            self.assertEqual(MediaHandler.calls, 0)
        finally:
            server.shutdown()

    def test_fetch_media_invalid_uuid(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            with self.assertRaises(ValueError) as ctx:
                client.fetch_media(ts, "not-a-uuid", now=NOW)
            self.assertIn("UUID", str(ctx.exception))
            self.assertEqual(MediaHandler.calls, 0)
        finally:
            server.shutdown()

    def test_fetch_media_401(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.MEDIA_FAIL = 401
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertFalse(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_media_403(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.MEDIA_FAIL = 403
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 403)
        finally:
            server.shutdown()

    def test_fetch_media_404(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.MEDIA_FAIL = 404
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 404)
        finally:
            server.shutdown()

    def test_fetch_media_422(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.MEDIA_FAIL = 422
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 422)
        finally:
            server.shutdown()

    def test_fetch_media_500_retryable(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.MEDIA_FAIL = 500
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertTrue(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_media_expected_sha256_mismatch(self):
        import hashlib
        wrong_sha = hashlib.sha256(b"wrong").hexdigest()
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(
                    ts, TEST_MANIFEST_ITEM_ID,
                    expected_sha256=wrong_sha, now=NOW,
                )
            self.assertIn("sha256", str(ctx.exception).lower())
            self.assertIn("mismatch", str(ctx.exception).lower())
            self.assertFalse(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_media_expected_size_mismatch(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(
                    ts, TEST_MANIFEST_ITEM_ID,
                    expected_size_bytes=999999, now=NOW,
                )
            self.assertIn("size", str(ctx.exception).lower())
            self.assertIn("mismatch", str(ctx.exception).lower())
            self.assertFalse(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_media_expected_content_type_mismatch(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(
                    ts, TEST_MANIFEST_ITEM_ID,
                    expected_content_type="video/mp4", now=NOW,
                )
            self.assertIn("content_type", str(ctx.exception).lower())
            self.assertFalse(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_media_content_length_mismatch(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.WRONG_CONTENT_LENGTH = True
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            # IncompleteRead due to Content-Length mismatch
            self.assertIn("read response", str(ctx.exception).lower())
            self.assertTrue(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_fetch_media_header_sha256_mismatch(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.WRONG_SHA256_HEADER = True
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("sha256", str(ctx.exception).lower())
        finally:
            server.shutdown()

    def test_fetch_media_missing_content_type(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.SKIP_CONTENT_TYPE = True
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertIn("Content-Type", str(ctx.exception))
        finally:
            server.shutdown()

    def test_fetch_media_max_bytes_exceeded(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(
                    ts, TEST_MANIFEST_ITEM_ID,
                    max_bytes=10, now=NOW,
                )
            self.assertIn("too large", str(ctx.exception).lower())
            self.assertFalse(ctx.exception.retryable)
        finally:
            server.shutdown()

    # ── Security: no token/auth/content in errors ───────────────────

    def test_no_token_in_errors(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.MEDIA_FAIL = 401
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertNotIn(TEST_TOKEN, str(ctx.exception))
        finally:
            server.shutdown()

    def test_no_authorization_in_errors(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.MEDIA_FAIL = 403
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertNotIn("Authorization", str(ctx.exception))
            self.assertNotIn("Bearer", str(ctx.exception))
        finally:
            server.shutdown()

    def test_no_content_bytes_in_errors(self):
        import hashlib
        wrong_sha = hashlib.sha256(b"wrong").hexdigest()
        server, thr, port = _start_server(MediaHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_media(
                    ts, TEST_MANIFEST_ITEM_ID,
                    expected_sha256=wrong_sha, now=NOW,
                )
            # Error message must NOT contain binary content
            err_msg = str(ctx.exception)
            self.assertNotIn(TEST_CONTENT.decode("latin-1"), err_msg)
        finally:
            server.shutdown()

    def test_media_metadata_no_byte_dump_in_error(self):
        server, thr, port = _start_server(MediaHandler)
        try:
            MediaHandler.INVALID_JSON = True
            client = self._make_client(port)
            ts = _valid_token_state()
            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.fetch_metadata(ts, TEST_MANIFEST_ITEM_ID, now=NOW)
            self.assertNotIn("<html>", str(ctx.exception))
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
