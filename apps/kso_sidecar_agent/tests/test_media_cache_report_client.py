"""Tests for MediaCacheReportClient — fake HTTP server, no real backend."""

import hashlib as _hl
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

TEST_TOKEN = "opaque-value-1234567890"
TEST_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_DEVICE_CODE = "a-05954"
TEST_MANIFEST_VERSION_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
TEST_MANIFEST_HASH = "c" * 64
TEST_ITEM_1_ID = "11111111-1111-1111-1111-111111111111"
TEST_ITEM_2_ID = "22222222-2222-2222-2222-222222222222"

TEST_CONTENT_1 = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_CONTENT_2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 80

TEST_ITEM_1_SHA = _hl.sha256(TEST_CONTENT_1).hexdigest()
TEST_ITEM_2_SHA = _hl.sha256(TEST_CONTENT_2).hexdigest()

NOW = 1_750_000_000.0


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


def _make_manifest_data():
    return {
        "manifest_version_id": TEST_MANIFEST_VERSION_ID,
        "manifest_hash": TEST_MANIFEST_HASH,
        "source": "current",
        "generated_at": "2026-06-18T10:00:00Z",
        "fetched_at": "2026-06-18T10:00:00Z",
        "items": [
            {
                "manifest_item_id": TEST_ITEM_1_ID,
                "filename": f"{TEST_ITEM_1_ID}.png",
                "sha256": TEST_ITEM_1_SHA,
                "content_type": "image/png",
                "size_bytes": 0,
                "duration_ms": 10000,
                "order": 0,
            },
            {
                "manifest_item_id": TEST_ITEM_2_ID,
                "filename": f"{TEST_ITEM_2_ID}.png",
                "sha256": TEST_ITEM_2_SHA,
                "content_type": "image/png",
                "size_bytes": 0,
                "duration_ms": 5000,
                "order": 1,
            },
        ],
    }


# ══════════════════════════════════════════════════════════════════════
# Fake server
# ══════════════════════════════════════════════════════════════════════

def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


class ReportHandler(BaseHTTPRequestHandler):
    FAIL_CODE = None
    INVALID_JSON = False
    CUSTOM_RESPONSE = None
    last_auth_header = ""
    last_request_body = ""
    calls = 0

    @classmethod
    def reset(cls):
        cls.FAIL_CODE = None
        cls.INVALID_JSON = False
        cls.CUSTOM_RESPONSE = None
        cls.last_auth_header = ""
        cls.last_request_body = ""
        cls.calls = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        ReportHandler.last_auth_header = self.headers.get("Authorization", "")
        ReportHandler.calls += 1

        # Read request body
        cl = int(self.headers.get("Content-Length", 0))
        ReportHandler.last_request_body = self.rfile.read(cl).decode("utf-8") if cl else ""

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

        if self.CUSTOM_RESPONSE is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.CUSTOM_RESPONSE).encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "gateway_device_id": TEST_DEVICE_ID,
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "total_items": 2,
            "cached_count": 2,
            "missing_count": 0,
            "failed_count": 0,
            "invalid_hash_count": 0,
        }).encode())


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestBuildPayload(unittest.TestCase):

    def setUp(self):
        from kso_sidecar_agent.media_cache import ensure_media_dirs, write_media_atomic
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        ensure_media_dirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_manifest(self, manifest_data=None):
        from kso_sidecar_agent.manifest_store import write_current_manifest
        # Write directly to disk for read_current_manifest
        manifest_path = self.root / "manifest" / "current_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data = manifest_data or _make_manifest_data()
        manifest_path.write_text(json.dumps(data))

    def test_build_complete_cache(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        from kso_sidecar_agent.media_cache_report_client import build_media_cache_report_payload

        # Write both files to cache
        item1 = _make_manifest_data()["items"][0]
        item2 = _make_manifest_data()["items"][1]

        class FakeMC:
            pass
        mc1 = FakeMC(); mc1.sha256 = TEST_ITEM_1_SHA; mc1.size_bytes = len(TEST_CONTENT_1)
        mc1.content_type = "image/png"; mc1.content = TEST_CONTENT_1
        mc2 = FakeMC(); mc2.sha256 = TEST_ITEM_2_SHA; mc2.size_bytes = len(TEST_CONTENT_2)
        mc2.content_type = "image/png"; mc2.content = TEST_CONTENT_2

        write_media_atomic(self.root, item1, mc1)
        write_media_atomic(self.root, item2, mc2)

        self._write_manifest()

        payload = build_media_cache_report_payload(self.root)
        self.assertEqual(len(payload.items), 2)

        cached = [i for i in payload.items if i.status == "cached"]
        self.assertEqual(len(cached), 2)
        self.assertEqual(cached[0].reported_sha256, TEST_ITEM_1_SHA)
        self.assertEqual(cached[1].reported_sha256, TEST_ITEM_2_SHA)

    def test_build_missing_media(self):
        from kso_sidecar_agent.media_cache_report_client import build_media_cache_report_payload

        self._write_manifest()
        # No files in cache

        payload = build_media_cache_report_payload(self.root)
        self.assertEqual(len(payload.items), 2)

        missing = [i for i in payload.items if i.status == "missing"]
        self.assertEqual(len(missing), 2)

    def test_build_invalid_hash(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        from kso_sidecar_agent.media_cache_report_client import build_media_cache_report_payload

        # Write correct item 1, write wrong sha256 for item 2
        item1 = _make_manifest_data()["items"][0]
        class FakeMC:
            pass
        mc1 = FakeMC(); mc1.sha256 = TEST_ITEM_1_SHA; mc1.size_bytes = len(TEST_CONTENT_1)
        mc1.content_type = "image/png"; mc1.content = TEST_CONTENT_1
        write_media_atomic(self.root, item1, mc1)

        # Write file with wrong content directly to current
        current = self.root / "media" / "current" / f"{TEST_ITEM_2_ID}.png"
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_bytes(b"corrupted data")

        self._write_manifest()

        payload = build_media_cache_report_payload(self.root)
        self.assertEqual(len(payload.items), 2)

        statuses = {i.manifest_item_id: i.status for i in payload.items}
        self.assertEqual(statuses[TEST_ITEM_1_ID], "cached")
        self.assertEqual(statuses[TEST_ITEM_2_ID], "invalid_hash")

    def test_no_forbidden_in_payload(self):
        from kso_sidecar_agent.media_cache import write_media_atomic
        from kso_sidecar_agent.media_cache_report_client import build_media_cache_report_payload

        item1 = _make_manifest_data()["items"][0]
        class FakeMC:
            pass
        mc1 = FakeMC(); mc1.sha256 = TEST_ITEM_1_SHA; mc1.size_bytes = len(TEST_CONTENT_1)
        mc1.content_type = "image/png"; mc1.content = TEST_CONTENT_1
        write_media_atomic(self.root, item1, mc1)
        self._write_manifest()

        payload = build_media_cache_report_payload(self.root)
        payload_str = json.dumps(payload.as_dict()).lower()

        self.assertNotIn("token", payload_str)
        self.assertNotIn("secret", payload_str)
        self.assertNotIn("authorization", payload_str)
        self.assertNotIn("bearer", payload_str)
        self.assertNotIn("local_path", payload_str)
        self.assertNotIn("file_path", payload_str)
        self.assertNotIn("media_path", payload_str)
        self.assertNotIn("creatives/", payload_str)


class TestMediaCacheReportClient(unittest.TestCase):

    def setUp(self):
        ReportHandler.reset()

    def _make_client(self, port):
        from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
        from kso_sidecar_agent.media_cache_report_client import MediaCacheReportClient
        config = HttpClientConfig(base_url=f"http://127.0.0.1:{port}")
        http = SafeHttpClient(config)
        return MediaCacheReportClient(http)

    def _make_payload(self):
        from kso_sidecar_agent.media_cache_report_client import (
            MediaCacheReportItem, MediaCacheReportPayload,
        )
        return MediaCacheReportPayload(
            manifest_version_id=TEST_MANIFEST_VERSION_ID,
            manifest_hash=TEST_MANIFEST_HASH,
            items=[
                MediaCacheReportItem(
                    manifest_item_id=TEST_ITEM_1_ID,
                    status="cached",
                    reported_sha256=TEST_ITEM_1_SHA,
                    file_size_bytes=len(TEST_CONTENT_1),
                ),
            ],
        )

    def test_send_report_success(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            result = client.send_report(ts, payload, now=NOW)
            self.assertTrue(result.accepted)
            self.assertEqual(result.total_items, 2)
            self.assertEqual(result.cached_count, 2)
            self.assertEqual(result.sent_at, NOW)
        finally:
            server.shutdown()

    def test_auth_header_sent(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            client.send_report(ts, payload, now=NOW)
            self.assertIn(TEST_TOKEN, ReportHandler.last_auth_header)
        finally:
            server.shutdown()

    def test_safe_summary_no_secrets(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            result = client.send_report(ts, payload, now=NOW)
            summary = result.safe_summary()
            summary_str = str(summary).lower()

            self.assertNotIn(TEST_TOKEN, summary_str)
            self.assertNotIn(TEST_ITEM_1_SHA, summary_str)  # full sha not in summary
            self.assertNotIn(TEST_MANIFEST_VERSION_ID, summary_str)  # full UUID not in summary
            self.assertNotIn("authorization", summary_str)
        finally:
            server.shutdown()

    def test_expired_token_no_http(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            client = self._make_client(port)
            ts = _expired_token_state()
            payload = self._make_payload()

            with self.assertRaises(ValueError) as ctx:
                client.send_report(ts, payload, now=NOW)
            self.assertIn("expired", str(ctx.exception).lower())
            self.assertEqual(ReportHandler.calls, 0)
        finally:
            server.shutdown()

    def test_401_safe_error(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            ReportHandler.FAIL_CODE = 401
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.send_report(ts, payload, now=NOW)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertFalse(ctx.exception.retryable)

            # No token in error
            self.assertNotIn(TEST_TOKEN, str(ctx.exception))
            self.assertNotIn("Authorization", str(ctx.exception))
        finally:
            server.shutdown()

    def test_403_safe_error(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            ReportHandler.FAIL_CODE = 403
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.send_report(ts, payload, now=NOW)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertNotIn(TEST_TOKEN, str(ctx.exception))
        finally:
            server.shutdown()

    def test_422_safe_error(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            ReportHandler.FAIL_CODE = 422
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.send_report(ts, payload, now=NOW)
            self.assertEqual(ctx.exception.status_code, 422)
        finally:
            server.shutdown()

    def test_500_retryable(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            ReportHandler.FAIL_CODE = 500
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.send_report(ts, payload, now=NOW)
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertTrue(ctx.exception.retryable)
        finally:
            server.shutdown()

    def test_invalid_json_response(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            ReportHandler.INVALID_JSON = True
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.send_report(ts, payload, now=NOW)
            self.assertIn("Invalid JSON", str(ctx.exception))
            # No body dump
            self.assertNotIn("<html>", str(ctx.exception))
        finally:
            server.shutdown()

    def test_no_token_auth_in_errors(self):
        server, thr, port = _start_server(ReportHandler)
        try:
            ReportHandler.FAIL_CODE = 401
            client = self._make_client(port)
            ts = _valid_token_state()
            payload = self._make_payload()

            from kso_sidecar_agent.http_client import HttpClientError
            with self.assertRaises(HttpClientError) as ctx:
                client.send_report(ts, payload, now=NOW)

            err_msg = str(ctx.exception)
            self.assertNotIn(TEST_TOKEN, err_msg)
            self.assertNotIn("Authorization", err_msg)
            self.assertNotIn("Bearer", err_msg)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
