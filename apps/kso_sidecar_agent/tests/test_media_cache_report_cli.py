"""Tests for report-media-cache CLI — fake HTTP server, no real backend."""

import hashlib as _hl
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
TEST_MANIFEST_VERSION_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
TEST_MANIFEST_HASH = "c" * 64
TEST_ITEM_1_ID = "11111111-1111-1111-1111-111111111111"
TEST_ITEM_2_ID = "22222222-2222-2222-2222-222222222222"

TEST_CONTENT_1 = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_CONTENT_2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 80

TEST_ITEM_1_SHA = _hl.sha256(TEST_CONTENT_1).hexdigest()
TEST_ITEM_2_SHA = _hl.sha256(TEST_CONTENT_2).hexdigest()

DEV_FLAG = ["--dev-secret-store"]


def _run(*args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR),
        timeout=30,
    )
    return r.returncode, r.stdout, r.stderr


def _run_stdin(secret, *args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR), input=secret,
        timeout=30,
    )
    return r.returncode, r.stdout, r.stderr


def _setup_root(root, base_url, with_secret=True, with_manifest=True):
    """Set up a root with config, secret, and optional manifest + media."""
    _run("init-local-root", "--root", root)
    _run("write-config", "--root", root,
         "--backend-base-url", base_url, "--device-code", TEST_DEVICE_CODE)
    if with_secret:
        _run_stdin(TEST_SECRET, "secret-store-set", "--root", root,
                   *DEV_FLAG, "--stdin")

    if with_manifest:
        # Write manifest directly
        manifest_dir = Path(root) / "manifest"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_data = {
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
        (manifest_dir / "current_manifest.json").write_text(json.dumps(manifest_data))

        # Create media dirs
        for d in ("media/current", "media/staging", "media/quarantine"):
            (Path(root) / d).mkdir(parents=True, exist_ok=True)


def _valid_auth_body():
    return json.dumps({
        "access_token": TEST_TOKEN, "token_type": "bearer",
        "expires_in": 3600, "device_id": TEST_DEVICE_ID,
        "device_code": TEST_DEVICE_CODE, "status": "active",
    }).encode()


def _valid_report_response():
    return json.dumps({
        "status": "ok",
        "gateway_device_id": TEST_DEVICE_ID,
        "manifest_version_id": TEST_MANIFEST_VERSION_ID,
        "total_items": 2,
        "cached_count": 0,
        "missing_count": 2,
        "failed_count": 0,
        "invalid_hash_count": 0,
    }).encode()


# ══════════════════════════════════════════════════════════════════════
# Fake server — handles auth and report endpoints
# ══════════════════════════════════════════════════════════════════════

def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


class ReportCLIHandler(BaseHTTPRequestHandler):
    """Handles auth POST + report POST for report-media-cache CLI tests."""

    AUTH_FAIL = None           # int status code -> fail auth
    REPORT_FAIL = None         # int status code -> fail report
    INVALID_JSON = False       # return HTML instead of JSON
    CUSTOM_RESPONSE = None     # override report response
    last_auth_header = ""
    last_report_auth_header = ""
    last_report_body = ""
    auth_calls = 0
    report_calls = 0

    @classmethod
    def reset(cls):
        cls.AUTH_FAIL = None
        cls.REPORT_FAIL = None
        cls.INVALID_JSON = False
        cls.CUSTOM_RESPONSE = None
        cls.last_auth_header = ""
        cls.last_report_auth_header = ""
        cls.last_report_body = ""
        cls.auth_calls = 0
        cls.report_calls = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        auth_header = self.headers.get("Authorization", "")
        cl = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(cl) if cl else b""

        if self.path == "/api/device-gateway/auth/token":
            ReportCLIHandler.last_auth_header = auth_header
            ReportCLIHandler.auth_calls += 1

            if self.AUTH_FAIL:
                self.send_response(self.AUTH_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"auth fail"}')
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_valid_auth_body())
            return

        if self.path == "/api/device-gateway/media/cache/report":
            ReportCLIHandler.last_report_auth_header = auth_header
            ReportCLIHandler.last_report_body = body.decode("utf-8")
            ReportCLIHandler.report_calls += 1

            if self.REPORT_FAIL:
                self.send_response(self.REPORT_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"report fail"}')
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
            self.wfile.write(_valid_report_response())
            return

        # Unknown path
        self.send_response(404)
        self.end_headers()


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestReportMediaCacheCLI(unittest.TestCase):

    def setUp(self):
        ReportCLIHandler.reset()

    # ── Success flows ───────────────────────────────────────────────

    def test_report_success(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertEqual(rc, 0)
                self.assertIn("media_cache_report:  sent", out)
                self.assertIn("backend_status:      ok", out)
                self.assertIn("items_total:", out)
        finally:
            server.shutdown()

    def test_report_payload_correct(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertEqual(ReportCLIHandler.report_calls, 1)

                payload = json.loads(ReportCLIHandler.last_report_body)
                self.assertEqual(payload["manifest_version_id"], TEST_MANIFEST_VERSION_ID)
                self.assertEqual(payload["manifest_hash"], TEST_MANIFEST_HASH)
                self.assertIsInstance(payload["items"], list)
                self.assertEqual(len(payload["items"]), 2)

                for item in payload["items"]:
                    self.assertIn("manifest_item_id", item)
                    self.assertIn("status", item)
        finally:
            server.shutdown()

    def test_auth_header_sent_to_report_endpoint(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                _run("report-media-cache", "--root", root, *DEV_FLAG)

                # Auth endpoint was called (but has no Authorization — it creates the token)
                self.assertEqual(ReportCLIHandler.auth_calls, 1)
                # Report endpoint must have the token
                self.assertEqual(ReportCLIHandler.report_calls, 1)
                self.assertNotEqual(ReportCLIHandler.last_report_auth_header, "")
                self.assertIn(TEST_TOKEN, ReportCLIHandler.last_report_auth_header)
        finally:
            server.shutdown()

    # ── Safe output — no secrets ────────────────────────────────────

    def test_no_token_in_output(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertEqual(rc, 0)
                self.assertNotIn(TEST_TOKEN, out)
                self.assertNotIn(TEST_TOKEN, err)
        finally:
            server.shutdown()

    def test_no_secret_in_output(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertEqual(rc, 0)
                self.assertNotIn(TEST_SECRET, out)
                self.assertNotIn(TEST_SECRET, err)
        finally:
            server.shutdown()

    def test_no_authorization_in_output(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertEqual(rc, 0)
                self.assertNotIn("Authorization", out)
                self.assertNotIn("Authorization", err)
                self.assertNotIn("Bearer", out)
                self.assertNotIn("Bearer", err)
        finally:
            server.shutdown()

    def test_no_request_body_in_output(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertEqual(rc, 0)
                self.assertNotIn(TEST_MANIFEST_VERSION_ID, out)
                self.assertNotIn(TEST_MANIFEST_HASH, out)
        finally:
            server.shutdown()

    def test_no_report_items_in_output(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertEqual(rc, 0)
                self.assertNotIn(TEST_ITEM_1_ID, out)
                self.assertNotIn(TEST_ITEM_2_ID, out)
                self.assertNotIn(TEST_ITEM_1_SHA, out)
                self.assertNotIn(TEST_ITEM_2_SHA, out)
        finally:
            server.shutdown()

    def test_no_local_path_in_output(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertEqual(rc, 0)
                self.assertNotIn("local_path", out.lower())
                self.assertNotIn("local_path", err.lower())
                self.assertNotIn("file_path", out.lower())
                self.assertNotIn("media_path", out.lower())
                self.assertNotIn("creatives/", out.lower())
        finally:
            server.shutdown()

    # ── Missing manifest ────────────────────────────────────────────

    def test_missing_manifest_error(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}", with_manifest=False)

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
                self.assertIn("ERROR", err)
        finally:
            server.shutdown()

    def test_invalid_manifest_error(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                # Corrupt manifest
                manifest_path = Path(root) / "manifest" / "current_manifest.json"
                manifest_path.write_text("not valid json {{{")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
                self.assertIn("ERROR", err)
        finally:
            server.shutdown()

    # ── Config errors ───────────────────────────────────────────────

    def test_missing_config_error(self):
        with tempfile.TemporaryDirectory() as root:
            # No config at all
            (Path(root) / "manifest").mkdir(parents=True, exist_ok=True)

            rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

            self.assertNotEqual(rc, 0)
            self.assertIn("Config", err)

    def test_missing_secret_error(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}", with_secret=False)

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
        finally:
            server.shutdown()

    def test_no_dev_secret_store_reject(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                # No --dev-secret-store flag
                rc, out, err = _run("report-media-cache", "--root", root)

                self.assertNotEqual(rc, 0)
                self.assertIn("disabled", (out + err).lower())
        finally:
            server.shutdown()

    # ── Auth errors ─────────────────────────────────────────────────

    def test_auth_401_report_not_called(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            ReportCLIHandler.AUTH_FAIL = 401

            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
                self.assertEqual(ReportCLIHandler.report_calls, 0)
                self.assertNotIn(TEST_TOKEN, out)
                self.assertNotIn(TEST_TOKEN, err)
        finally:
            server.shutdown()

    def test_auth_500_with_retry_success(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            # First auth call fails with 500, reset on second
            call_count = [0]

            class RetryAuthHandler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_POST(self):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(b'{"error":"server error"}')
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(_valid_auth_body())

            server2, thr2, port2 = _start_server(
                type("RetryAuthHandler2", (RetryAuthHandler,), {}),
            )
            try:
                with tempfile.TemporaryDirectory() as root:
                    _setup_root(root, f"http://127.0.0.1:{port2}")

                    rc, out, err = _run(
                        "report-media-cache", "--root", root, *DEV_FLAG,
                        "--retry-auth", "--auth-max-attempts", "3",
                    )

                    # Auth should have been retried and succeeded (but report will fail
                    # since this fake server only handles auth)
                    # We just care that auth 500 doesn't crash and retry fires
                    self.assertGreaterEqual(call_count[0], 2)
            finally:
                server2.shutdown()
        finally:
            server.shutdown()

    # ── Report HTTP errors ──────────────────────────────────────────

    def test_report_401_safe_error(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            ReportCLIHandler.REPORT_FAIL = 401

            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
                self.assertIn("Media cache report failed", err)
                self.assertIn("retryable:          false", err)
                self.assertNotIn(TEST_TOKEN, out)
                self.assertNotIn(TEST_TOKEN, err)
        finally:
            server.shutdown()

    def test_report_403_safe_error(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            ReportCLIHandler.REPORT_FAIL = 403

            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
                self.assertIn("Media cache report failed", err)
                self.assertNotIn(TEST_TOKEN, out)
        finally:
            server.shutdown()

    def test_report_422_safe_error(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            ReportCLIHandler.REPORT_FAIL = 422

            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
                self.assertIn("Media cache report failed", err)
        finally:
            server.shutdown()

    def test_report_500_retryable_error(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            ReportCLIHandler.REPORT_FAIL = 500

            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
                self.assertIn("Media cache report failed", err)
                self.assertIn("retryable:          true", err)
        finally:
            server.shutdown()

    def test_invalid_json_response_safe_error(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            ReportCLIHandler.INVALID_JSON = True

            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotEqual(rc, 0)
                self.assertNotIn("<html>", err)
                self.assertNotIn("<html>", out)
        finally:
            server.shutdown()

    # ── No stacktrace ───────────────────────────────────────────────

    def test_no_stacktrace_in_output(self):
        server, thr, port = _start_server(ReportCLIHandler)
        try:
            ReportCLIHandler.REPORT_FAIL = 500

            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")

                rc, out, err = _run("report-media-cache", "--root", root, *DEV_FLAG)

                self.assertNotIn("Traceback", out)
                self.assertNotIn("Traceback", err)
                self.assertNotIn("File \"", out)
                self.assertNotIn("File \"", err)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
