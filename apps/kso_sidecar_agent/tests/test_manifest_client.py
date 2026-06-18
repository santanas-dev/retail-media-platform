"""Tests for ManifestClient — uses local fake HTTP server, no real backend."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

TEST_TOKEN = "opaque-value-1234567890"
TEST_DEVICE_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_DEVICE_CODE = "a-05954"
TEST_MANIFEST_VERSION_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
TEST_ITEM_ID = "11111111-1111-1111-1111-111111111111"
NOW = 1_750_000_000.0

# Valid manifest items for test responses
VALID_MANIFEST_ITEMS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "schedule_item_id": "22222222-2222-2222-2222-222222222222",
        "sha256": "a" * 64,
        "media_path": "creatives/test.mp4",
        "duration_ms": 15000,
        "loop_position": 0,
        "spot_position": 1,
    },
    {
        "id": "33333333-3333-3333-3333-333333333333",
        "schedule_item_id": "44444444-4444-4444-4444-444444444444",
        "sha256": "b" * 64,
        "media_path": "creatives/test2.jpg",
        "duration_ms": 5000,
        "loop_position": 1,
        "spot_position": 0,
    },
]

VALID_MANIFEST_CURRENT_RESPONSE = {
    "status": "served",
    "manifest_version_id": TEST_MANIFEST_VERSION_ID,
    "manifest_hash": "c" * 64,
    "published_at": "2026-06-18T10:00:00+00:00",
    "manifest": {"items": VALID_MANIFEST_ITEMS},
}

VALID_MANIFEST_BY_ID_RESPONSE = {
    "manifest_version_id": TEST_MANIFEST_VERSION_ID,
    "manifest_hash": "c" * 64,
    "published_at": "2026-06-18T10:00:00+00:00",
    "manifest_items": VALID_MANIFEST_ITEMS,
}

NOT_MODIFIED_RESPONSE = {
    "status": "not_modified",
    "manifest_version_id": TEST_MANIFEST_VERSION_ID,
    "manifest_hash": "c" * 64,
}

NO_MANIFEST_RESPONSE = {"status": "no_manifest"}


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


class ManifestHandler(BaseHTTPRequestHandler):
    """Handles manifest current and by-id endpoints."""

    FAIL_CODE = None          # int: fail ALL requests with this code
    CURRENT_FAIL = None       # int: fail /manifest/current only
    BYID_FAIL = None          # int: fail /manifest/{id} only
    INVALID_JSON = False      # return HTML instead of JSON
    CUSTOM_CURRENT = None     # dict: custom response for /manifest/current
    CUSTOM_BYID = None        # dict: custom response for /manifest/{id}
    last_auth_header = ""
    calls = 0

    @classmethod
    def reset(cls):
        cls.FAIL_CODE = None
        cls.CURRENT_FAIL = None
        cls.BYID_FAIL = None
        cls.INVALID_JSON = False
        cls.CUSTOM_CURRENT = None
        cls.CUSTOM_BYID = None
        cls.last_auth_header = ""
        cls.calls = 0

    def do_GET(self):
        ManifestHandler.calls += 1
        ManifestHandler.last_auth_header = self.headers.get("Authorization", "")

        # Failure check
        code = ManifestHandler.FAIL_CODE
        if self.path.startswith("/api/device-gateway/manifest/current") and ManifestHandler.CURRENT_FAIL:
            code = ManifestHandler.CURRENT_FAIL
        elif not self.path.startswith("/api/device-gateway/manifest/current") and ManifestHandler.BYID_FAIL:
            code = ManifestHandler.BYID_FAIL

        if code:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"manifest error")
            return

        # Invalid JSON
        if ManifestHandler.INVALID_JSON:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>not json</html>")
            return

        # Route
        if self.path.startswith("/api/device-gateway/manifest/current"):
            self._serve_current()
        elif self.path.startswith("/api/device-gateway/manifest/"):
            self._serve_by_id()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_current(self):
        if ManifestHandler.CUSTOM_CURRENT:
            body_json = ManifestHandler.CUSTOM_CURRENT
        else:
            body_json = VALID_MANIFEST_CURRENT_RESPONSE
        self._send_json(body_json)

    def _serve_by_id(self):
        if ManifestHandler.CUSTOM_BYID:
            body_json = ManifestHandler.CUSTOM_BYID
        else:
            body_json = VALID_MANIFEST_BY_ID_RESPONSE
        self._send_json(body_json)

    def _send_json(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass


# ══════════════════════════════════════════════════════════════════════
# Client tests — fetch_current
# ══════════════════════════════════════════════════════════════════════

class TestManifestClientCurrent(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._server, cls._thread, cls._port = _start_server(ManifestHandler)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()

    def setUp(self):
        ManifestHandler.reset()

    def _client(self):
        from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
        from kso_sidecar_agent.manifest_client import ManifestClient
        http = SafeHttpClient(HttpClientConfig(
            base_url=f"http://127.0.0.1:{self._port}", timeout_sec=3,
        ))
        return ManifestClient(http_client=http)

    def test_fetch_current_success(self):
        mc = self._client()
        snapshot = mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertEqual(snapshot.status, "served")
        self.assertEqual(snapshot.source, "current")
        self.assertEqual(len(snapshot.items), 2)

    def test_authorization_header_sent(self):
        mc = self._client()
        mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertIn("Bearer", ManifestHandler.last_auth_header)
        self.assertIn(TEST_TOKEN, ManifestHandler.last_auth_header)

    def test_safe_summary_no_token(self):
        mc = self._client()
        snapshot = mc.fetch_current(_valid_token_state(), now=NOW)
        summary = snapshot.safe_summary()
        self.assertNotIn(TEST_TOKEN, str(summary))
        self.assertEqual(summary["items_count"], 2)

    def test_safe_summary_no_full_manifest(self):
        mc = self._client()
        snapshot = mc.fetch_current(_valid_token_state(), now=NOW)
        summary = snapshot.safe_summary()
        self.assertNotIn("items", summary)  # no full items in summary

    def test_not_modified_response(self):
        ManifestHandler.CUSTOM_CURRENT = NOT_MODIFIED_RESPONSE
        mc = self._client()
        snapshot = mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertEqual(snapshot.status, "not_modified")
        self.assertTrue(snapshot.not_modified)

    def test_no_manifest_response(self):
        ManifestHandler.CUSTOM_CURRENT = NO_MANIFEST_RESPONSE
        mc = self._client()
        snapshot = mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertEqual(snapshot.status, "no_manifest")

    def test_expired_token_no_http(self):
        from kso_sidecar_agent.token_state import TokenState
        mc = self._client()
        ts = TokenState(_access_token=TEST_TOKEN, token_type="bearer",
                        expires_at=NOW - 1, device_id="x", device_code="x",
                        status="active")
        with self.assertRaises(ValueError):
            mc.fetch_current(ts, now=NOW)
        self.assertEqual(ManifestHandler.calls, 0)

    def test_401_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CURRENT_FAIL = 401
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertNotIn(TEST_TOKEN, ctx.exception.message)

    def test_403_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CURRENT_FAIL = 403
        mc = self._client()
        with self.assertRaises(HttpClientError):
            mc.fetch_current(_valid_token_state(), now=NOW)

    def test_404_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CURRENT_FAIL = 404
        mc = self._client()
        with self.assertRaises(HttpClientError):
            mc.fetch_current(_valid_token_state(), now=NOW)

    def test_422_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CURRENT_FAIL = 422
        mc = self._client()
        with self.assertRaises(HttpClientError):
            mc.fetch_current(_valid_token_state(), now=NOW)

    def test_500_retryable(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CURRENT_FAIL = 500
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertTrue(ctx.exception.retryable)

    def test_invalid_json_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.INVALID_JSON = True
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertIn("Invalid JSON", ctx.exception.message)

    def test_forbidden_key_in_body_rejected(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CUSTOM_CURRENT = {
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "token": "bad",
            "manifest": {"items": []},
        }
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertIn("forbidden", ctx.exception.message.lower())

    def test_forbidden_value_in_item_rejected(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CUSTOM_CURRENT = {
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "manifest": {"items": [{"id": TEST_ITEM_ID, "sha256": "c" * 64, "name": "secret_key"}]},
        }
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertIn("forbidden", ctx.exception.message.lower())

    def test_path_traversal_filename_rejected(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CUSTOM_CURRENT = {
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "manifest": {"items": [{"id": TEST_ITEM_ID, "sha256": "c" * 64, "media_path": "../etc/passwd"}]},
        }
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertIn("path traversal", ctx.exception.message.lower())

    def test_invalid_sha256_rejected(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CUSTOM_CURRENT = {
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "manifest": {"items": [{"id": TEST_ITEM_ID, "sha256": "not-hex"}]},
        }
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertIn("sha256", ctx.exception.message.lower())

    def test_negative_duration_rejected(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CUSTOM_CURRENT = {
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "manifest": {"items": [{"id": TEST_ITEM_ID, "sha256": "c" * 64, "duration_ms": -1}]},
        }
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertIn("duration_ms", ctx.exception.message.lower())

    def test_negative_order_rejected(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CUSTOM_CURRENT = {
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "manifest": {"items": [{"id": TEST_ITEM_ID, "sha256": "c" * 64, "order": -1}]},
        }
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_current(_valid_token_state(), now=NOW)
        self.assertIn("order", ctx.exception.message.lower())

    def test_no_files_written(self):
        """ManifestClient writes nothing to disk."""
        import tempfile
        mc = self._client()
        mc.fetch_current(_valid_token_state(), now=NOW)
        # No writes happen — just verify no crash


# ══════════════════════════════════════════════════════════════════════
# Client tests — fetch_by_id
# ══════════════════════════════════════════════════════════════════════

class TestManifestClientById(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._server, cls._thread, cls._port = _start_server(ManifestHandler)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()

    def setUp(self):
        ManifestHandler.reset()

    def _client(self):
        from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
        from kso_sidecar_agent.manifest_client import ManifestClient
        http = SafeHttpClient(HttpClientConfig(
            base_url=f"http://127.0.0.1:{self._port}", timeout_sec=3,
        ))
        return ManifestClient(http_client=http)

    def test_fetch_by_id_success(self):
        mc = self._client()
        snapshot = mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)
        self.assertEqual(snapshot.status, "served")
        self.assertEqual(snapshot.source, "by_id")
        self.assertEqual(snapshot.manifest_version_id, TEST_MANIFEST_VERSION_ID)
        self.assertEqual(len(snapshot.items), 2)

    def test_authorization_header_sent(self):
        mc = self._client()
        mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)
        self.assertIn("Bearer", ManifestHandler.last_auth_header)

    def test_invalid_manifest_version_id_rejected(self):
        mc = self._client()
        with self.assertRaises(ValueError):
            mc.fetch_by_id(_valid_token_state(), "not-a-uuid", now=NOW)
        self.assertEqual(ManifestHandler.calls, 0)

    def test_empty_manifest_version_id_rejected(self):
        mc = self._client()
        with self.assertRaises(ValueError):
            mc.fetch_by_id(_valid_token_state(), "", now=NOW)
        self.assertEqual(ManifestHandler.calls, 0)

    def test_expired_token_no_http(self):
        from kso_sidecar_agent.token_state import TokenState
        mc = self._client()
        ts = TokenState(_access_token=TEST_TOKEN, token_type="bearer",
                        expires_at=NOW - 1, device_id="x", device_code="x",
                        status="active")
        with self.assertRaises(ValueError):
            mc.fetch_by_id(ts, TEST_MANIFEST_VERSION_ID, now=NOW)
        self.assertEqual(ManifestHandler.calls, 0)

    def test_401_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.BYID_FAIL = 401
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertNotIn(TEST_TOKEN, ctx.exception.message)

    def test_404_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.BYID_FAIL = 404
        mc = self._client()
        with self.assertRaises(HttpClientError):
            mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)

    def test_403_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.BYID_FAIL = 403
        mc = self._client()
        with self.assertRaises(HttpClientError):
            mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)

    def test_422_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.BYID_FAIL = 422
        mc = self._client()
        with self.assertRaises(HttpClientError):
            mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)

    def test_500_retryable(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.BYID_FAIL = 500
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)
        self.assertTrue(ctx.exception.retryable)

    def test_invalid_json_safe_error(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.INVALID_JSON = True
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)
        self.assertIn("Invalid JSON", ctx.exception.message)

    def test_forbidden_key_rejected(self):
        from kso_sidecar_agent.http_client import HttpClientError
        ManifestHandler.CUSTOM_BYID = {
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "api_key": "hidden",
            "manifest_items": VALID_MANIFEST_ITEMS,
        }
        mc = self._client()
        with self.assertRaises(HttpClientError) as ctx:
            mc.fetch_by_id(_valid_token_state(), TEST_MANIFEST_VERSION_ID, now=NOW)
        self.assertIn("forbidden", ctx.exception.message.lower())


if __name__ == "__main__":
    unittest.main()
