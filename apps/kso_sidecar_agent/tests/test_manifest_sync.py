"""Tests for sync-manifest CLI — fake HTTP server, no real backend."""

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

DEV_FLAG = ["--dev-secret-store"]

NOW = 1_750_000_000.0


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


def _setup_root(root, base_url, with_secret=True):
    _run("init-local-root", "--root", root)
    _run("write-config", "--root", root,
         "--backend-base-url", base_url, "--device-code", TEST_DEVICE_CODE)
    if with_secret:
        _run_stdin(TEST_SECRET, "secret-store-set", "--root", root,
                   *DEV_FLAG, "--stdin")


# ══════════════════════════════════════════════════════════════════════
# Fake server
# ══════════════════════════════════════════════════════════════════════

def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


def _valid_auth_body():
    return json.dumps({
        "access_token": TEST_TOKEN, "token_type": "bearer",
        "expires_in": 3600, "device_id": TEST_DEVICE_ID,
        "device_code": TEST_DEVICE_CODE, "status": "active",
    }).encode()


def _valid_manifest_current():
    return json.dumps({
        "status": "served",
        "manifest_version_id": TEST_MANIFEST_VERSION_ID,
        "manifest_hash": "c" * 64,
        "published_at": "2026-06-18T10:00:00+00:00",
        "manifest": {
            "items": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "sha256": "a" * 64,
                    "media_path": "creatives/test.mp4",
                    "duration_ms": 15000,
                    "loop_position": 0,
                },
            ],
        },
    }).encode()


def _valid_not_modified():
    return json.dumps({
        "status": "not_modified",
        "manifest_version_id": TEST_MANIFEST_VERSION_ID,
        "manifest_hash": "c" * 64,
    }).encode()


def _valid_no_manifest():
    return json.dumps({"status": "no_manifest"}).encode()


class SyncManifestHandler(BaseHTTPRequestHandler):
    """Handles auth + manifest/current endpoints."""

    AUTH_CODE = 200
    MANIFEST_CODE = 200
    MANIFEST_BODY = _valid_manifest_current()
    INVALID_JSON = False
    last_auth_header = ""
    auth_calls = 0
    manifest_calls = 0

    @classmethod
    def reset(cls):
        cls.AUTH_CODE = 200
        cls.MANIFEST_CODE = 200
        cls.MANIFEST_BODY = _valid_manifest_current()
        cls.INVALID_JSON = False
        cls.last_auth_header = ""
        cls.auth_calls = 0
        cls.manifest_calls = 0

    def do_POST(self):
        if self.path.startswith("/api/device-gateway/auth/token"):
            SyncManifestHandler.auth_calls += 1
            body_len = int(self.headers.get("Content-Length", 0))
            self.rfile.read(body_len)
            if SyncManifestHandler.AUTH_CODE != 200:
                self.send_response(SyncManifestHandler.AUTH_CODE)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"auth error")
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(_valid_auth_body())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/device-gateway/manifest/current"):
            SyncManifestHandler.manifest_calls += 1
            SyncManifestHandler.last_auth_header = self.headers.get("Authorization", "")
            code = SyncManifestHandler.MANIFEST_CODE
            if SyncManifestHandler.INVALID_JSON:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>not json</html>")
            elif code != 200:
                self.send_response(code)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"manifest error")
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(SyncManifestHandler.MANIFEST_BODY)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


# ══════════════════════════════════════════════════════════════════════
# CLI tests
# ══════════════════════════════════════════════════════════════════════

class TestSyncManifestCLI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._server, cls._thread, cls._port = _start_server(SyncManifestHandler)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()

    def setUp(self):
        SyncManifestHandler.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self._base = f"http://127.0.0.1:{self._port}"
        _setup_root(self.root, self._base, with_secret=True)

    def tearDown(self):
        self.tmp.cleanup()

    # ── Success ──────────────────────────────────────────────────────

    def test_success_manifest_written(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("manifest_sync:", out)
        self.assertIn("updated", out)
        # File exists
        path = Path(self.root) / CURRENT_MANIFEST_FILE
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["source"], "current")
        self.assertEqual(len(data["items"]), 1)

    def test_output_no_token(self):
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotIn(TEST_TOKEN, out + err)

    def test_output_no_secret(self):
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotIn(TEST_SECRET, out + err)

    def test_output_no_authorization(self):
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotIn("Bearer", out + err)

    def test_output_no_media_path(self):
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotIn("creatives/", out + err)

    def test_local_manifest_no_token_secret(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        path = Path(self.root) / CURRENT_MANIFEST_FILE
        content = path.read_text()
        self.assertNotIn(TEST_TOKEN, content)
        self.assertNotIn(TEST_SECRET, content)
        self.assertNotIn("authorization", content.lower())
        self.assertNotIn("bearer", content.lower())

    def test_local_manifest_no_media_path(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        path = Path(self.root) / CURRENT_MANIFEST_FILE
        content = path.read_text()
        self.assertNotIn("creatives/", content)

    def test_local_manifest_no_local_path(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        path = Path(self.root) / CURRENT_MANIFEST_FILE
        content = path.read_text()
        self.assertNotIn("local_path", content.lower())
        self.assertNotIn("file_path", content.lower())

    def test_item_filename_from_item_id(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        path = Path(self.root) / CURRENT_MANIFEST_FILE
        data = json.loads(path.read_text())
        item = data["items"][0]
        self.assertIn("11111111-1111", item["filename"])
        self.assertEqual(item["content_type"], "video/mp4")

    # ── not_modified ─────────────────────────────────────────────────

    def test_not_modified_with_existing(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        # First sync — creates manifest
        _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        mtime_before = (Path(self.root) / CURRENT_MANIFEST_FILE).stat().st_mtime

        # Second sync — not_modified
        SyncManifestHandler.MANIFEST_BODY = _valid_not_modified()
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("not_modified", out)
        self.assertIn("local_manifest_present: true", out)

        # File not overwritten
        mtime_after = (Path(self.root) / CURRENT_MANIFEST_FILE).stat().st_mtime
        self.assertEqual(mtime_before, mtime_after)

    def test_not_modified_without_existing(self):
        SyncManifestHandler.MANIFEST_BODY = _valid_not_modified()
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("not_modified", out)
        self.assertIn("local_manifest_present: false", out)

    # ── no_manifest ──────────────────────────────────────────────────

    def test_no_manifest_without_existing(self):
        SyncManifestHandler.MANIFEST_BODY = _valid_no_manifest()
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("no_manifest", out)
        # No manifest file created
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        path = Path(self.root) / CURRENT_MANIFEST_FILE
        self.assertFalse(path.exists())

    def test_no_manifest_does_not_delete_existing(self):
        # First sync — creates manifest
        _run("sync-manifest", "--root", self.root, *DEV_FLAG)

        # no_manifest should NOT delete existing
        SyncManifestHandler.MANIFEST_BODY = _valid_no_manifest()
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("local_manifest_present: true", out)

        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        path = Path(self.root) / CURRENT_MANIFEST_FILE
        self.assertTrue(path.exists())

    # ── Auth errors ──────────────────────────────────────────────────

    def test_auth_401_no_manifest_call(self):
        SyncManifestHandler.AUTH_CODE = 401
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("Manifest sync failed", err)
        self.assertEqual(SyncManifestHandler.manifest_calls, 0)

    def test_auth_500_with_retry(self):
        # 500 then 200
        class RetryAuthHandler(BaseHTTPRequestHandler):
            calls = 0
            def do_POST(self):
                RetryAuthHandler.calls += 1
                body_len = int(self.headers.get("Content-Length", 0))
                self.rfile.read(body_len)
                if RetryAuthHandler.calls < 3:
                    self.send_response(500)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"error")
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(_valid_auth_body())
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(_valid_manifest_current())
            def log_message(self, f, *a): pass

        svr, thr, port = _start_server(RetryAuthHandler)
        try:
            tmp = tempfile.TemporaryDirectory()
            root = tmp.name
            base = f"http://127.0.0.1:{port}"
            _setup_root(root, base, with_secret=True)
            code, out, err = _run("sync-manifest", "--root", root,
                                  "--retry-auth", "--auth-max-attempts", "3", *DEV_FLAG)
            self.assertEqual(code, 0, f"err={err}")
            self.assertIn("updated", out)
        finally:
            svr.shutdown()
            tmp.cleanup()

    # ── Manifest errors ──────────────────────────────────────────────

    def test_manifest_401_safe(self):
        SyncManifestHandler.MANIFEST_CODE = 401
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("Manifest sync failed", err)
        self.assertNotIn(TEST_TOKEN, out + err)

    def test_manifest_403_safe(self):
        SyncManifestHandler.MANIFEST_CODE = 403
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)

    def test_manifest_404_safe(self):
        SyncManifestHandler.MANIFEST_CODE = 404
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)

    def test_manifest_422_safe(self):
        SyncManifestHandler.MANIFEST_CODE = 422
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)

    def test_manifest_500_retryable(self):
        SyncManifestHandler.MANIFEST_CODE = 500
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("retryable:           True", err)

    def test_invalid_json_safe(self):
        SyncManifestHandler.INVALID_JSON = True
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)

    def test_forbidden_key_reject_no_file(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        SyncManifestHandler.MANIFEST_BODY = json.dumps({
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "token": "bad",
            "manifest": {"items": []},
        }).encode()
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertFalse((Path(self.root) / CURRENT_MANIFEST_FILE).exists())

    def test_invalid_sha256_reject_no_file(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        SyncManifestHandler.MANIFEST_BODY = json.dumps({
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "manifest": {"items": [{"id": "11111111-1111-1111-1111-111111111111", "sha256": "BAD"}]},
        }).encode()
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertFalse((Path(self.root) / CURRENT_MANIFEST_FILE).exists())

    def test_unsafe_media_path_reject_no_file(self):
        from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE
        SyncManifestHandler.MANIFEST_BODY = json.dumps({
            "status": "served",
            "manifest_version_id": TEST_MANIFEST_VERSION_ID,
            "manifest": {"items": [{"id": "11111111-1111-1111-1111-111111111111", "sha256": "a" * 64, "media_path": "../evil.mp4"}]},
        }).encode()
        code, out, err = _run("sync-manifest", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertFalse((Path(self.root) / CURRENT_MANIFEST_FILE).exists())

    # ── Config / Secret errors ───────────────────────────────────────

    def test_missing_config(self):
        tmp2 = tempfile.TemporaryDirectory()
        _run("init-local-root", "--root", tmp2.name)
        code, out, err = _run("sync-manifest", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("Config", err)
        tmp2.cleanup()

    def test_missing_secret(self):
        tmp2 = tempfile.TemporaryDirectory()
        _setup_root(tmp2.name, self._base, with_secret=False)
        code, out, err = _run("sync-manifest", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("secret", (out + err).lower())
        tmp2.cleanup()

    def test_no_dev_flag_rejected(self):
        code, out, err = _run("sync-manifest", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("disabled", (out + err).lower())

    def test_no_stacktrace(self):
        tmp2 = tempfile.TemporaryDirectory()
        _run("init-local-root", "--root", tmp2.name)
        code, out, err = _run("sync-manifest", "--root", tmp2.name, *DEV_FLAG)
        self.assertNotIn("Traceback", out + err)
        tmp2.cleanup()


if __name__ == "__main__":
    unittest.main()
