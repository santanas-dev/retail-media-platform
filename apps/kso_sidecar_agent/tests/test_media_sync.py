"""Tests for sync-media CLI — fake HTTP server, no real backend."""

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
TEST_ITEM_1_ID = "11111111-1111-1111-1111-111111111111"
TEST_ITEM_2_ID = "22222222-2222-2222-2222-222222222222"

TEST_CONTENT_1 = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_CONTENT_2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 80

TEST_ITEM_1_SHA = _hl.sha256(TEST_CONTENT_1).hexdigest()
TEST_ITEM_2_SHA = _hl.sha256(TEST_CONTENT_2).hexdigest()

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
                    "id": TEST_ITEM_1_ID,
                    "sha256": TEST_ITEM_1_SHA,
                    "media_path": "creatives/test1.png",
                    "duration_ms": 10000,
                    "loop_position": 0,
                },
                {
                    "id": TEST_ITEM_2_ID,
                    "sha256": TEST_ITEM_2_SHA,
                    "media_path": "creatives/test2.png",
                    "duration_ms": 5000,
                    "loop_position": 1,
                },
            ],
        },
    }).encode()


# ══════════════════════════════════════════════════════════════════════
# Fake server
# ══════════════════════════════════════════════════════════════════════

def _start_server(handler_class, port=0):
    server = HTTPServer(("127.0.0.1", port), handler_class)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, server.server_address[1]


class MediaSyncHandler(BaseHTTPRequestHandler):
    """Handles auth, manifest, and media endpoints for sync-media tests."""

    AUTH_FAIL = None
    MANIFEST_FAIL = None
    MEDIA_1_FAIL = None
    MEDIA_2_FAIL = None
    MEDIA_1_CONTENT = None
    MEDIA_2_CONTENT = None
    MEDIA_1_SHA = None
    MEDIA_2_SHA = None
    MEDIA_1_CONTENT_TYPE = "image/png"
    MEDIA_2_CONTENT_TYPE = "image/png"
    last_auth_header = ""
    calls = 0

    @classmethod
    def reset(cls):
        cls.AUTH_FAIL = None
        cls.MANIFEST_FAIL = None
        cls.MEDIA_1_FAIL = None
        cls.MEDIA_2_FAIL = None
        cls.MEDIA_1_CONTENT = None
        cls.MEDIA_2_CONTENT = None
        cls.MEDIA_1_SHA = None
        cls.MEDIA_2_SHA = None
        cls.MEDIA_1_CONTENT_TYPE = "image/png"
        cls.MEDIA_2_CONTENT_TYPE = "image/png"
        cls.last_auth_header = ""
        cls.calls = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        MediaSyncHandler.last_auth_header = self.headers.get("Authorization", "")
        MediaSyncHandler.calls += 1

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
        MediaSyncHandler.last_auth_header = self.headers.get("Authorization", "")
        MediaSyncHandler.calls += 1

        path = self.path

        if path == "/api/device-gateway/manifest/current":
            if self.MANIFEST_FAIL:
                self.send_response(self.MANIFEST_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"manifest fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_valid_manifest_current())
            return

        if TEST_ITEM_1_ID in path:
            if self.MEDIA_1_FAIL:
                self.send_response(self.MEDIA_1_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"media fail"}')
                return
            content = self.MEDIA_1_CONTENT or TEST_CONTENT_1
            sha = self.MEDIA_1_SHA or _hl.sha256(content).hexdigest()
            ct = self.MEDIA_1_CONTENT_TYPE
        elif TEST_ITEM_2_ID in path:
            if self.MEDIA_2_FAIL:
                self.send_response(self.MEDIA_2_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"media fail"}')
                return
            content = self.MEDIA_2_CONTENT or TEST_CONTENT_2
            sha = self.MEDIA_2_SHA or _hl.sha256(content).hexdigest()
            ct = self.MEDIA_2_CONTENT_TYPE
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-SHA256", sha)
        self.end_headers()
        self.wfile.write(content)


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestMediaSync(unittest.TestCase):

    def setUp(self):
        MediaSyncHandler.reset()

    def test_sync_success_both_downloaded(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)

                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
                self.assertEqual(rc, 0)

                self.assertIn("complete", out)
                self.assertIn("items_downloaded:     2", out)
                self.assertIn("cache_complete:       true", out)

                self.assertNotIn(TEST_TOKEN, out)
                self.assertNotIn(TEST_TOKEN, err)
                self.assertNotIn("Authorization", out)
                self.assertNotIn("media_path", out)
                self.assertNotIn("local_path", out.lower())

                current = Path(root) / "media" / "current"
                self.assertTrue((current / f"{TEST_ITEM_1_ID}.png").exists())
                self.assertTrue((current / f"{TEST_ITEM_2_ID}.png").exists())
        finally:
            server.shutdown()

    def test_existing_valid_skipped(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)
                _run("sync-media", "--root", root, *DEV_FLAG)

                MediaSyncHandler.calls = 0

                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
                self.assertEqual(rc, 0)

                self.assertIn("complete", out)
                self.assertIn("items_cached:         2", out)
                self.assertIn("items_downloaded:     0", out)
                self.assertIn("cache_complete:       true", out)
        finally:
            server.shutdown()

    def test_staging_not_leftover(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)
                _run("sync-media", "--root", root, *DEV_FLAG)

                staging = Path(root) / "media" / "staging"
                downloads = list(staging.glob("*.download"))
                self.assertEqual(len(downloads), 0)
        finally:
            server.shutdown()

    def test_sha256_mismatch_not_cached(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)

                # Content doesn't match manifest sha
                MediaSyncHandler.MEDIA_1_CONTENT = b"wrong"
                MediaSyncHandler.MEDIA_1_SHA = _hl.sha256(b"wrong").hexdigest()

                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
                self.assertEqual(rc, 0)

                self.assertIn("incomplete", out)
                self.assertIn("cache_complete:       false", out)

                current = Path(root) / "media" / "current"
                self.assertFalse((current / f"{TEST_ITEM_1_ID}.png").exists())
        finally:
            server.shutdown()

    def test_media_404_incomplete(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)

                MediaSyncHandler.MEDIA_1_FAIL = 404

                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
                self.assertEqual(rc, 0)

                self.assertIn("incomplete", out)
                self.assertIn("items_missing:        1", out)
                self.assertIn("cache_complete:       false", out)
        finally:
            server.shutdown()

    def test_media_500_nonfatal(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)

                MediaSyncHandler.MEDIA_2_FAIL = 500

                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
                self.assertEqual(rc, 0)

                self.assertIn("incomplete", out)
                self.assertIn("items_failed:         1", out)
                self.assertNotIn("<html>", out)
                self.assertNotIn("stacktrace", out.lower())
        finally:
            server.shutdown()

    def test_auth_401_fatal(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)

                MediaSyncHandler.AUTH_FAIL = 401
                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
                self.assertNotEqual(rc, 0)
                self.assertIn("Media sync failed", err)
        finally:
            server.shutdown()

    # Auth retry tested in test_manifest_sync.py — same mechanism

    def test_missing_config_fatal(self):
        with tempfile.TemporaryDirectory() as root:
            _run("init-local-root", "--root", root)
            rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
            self.assertNotEqual(rc, 0)
            self.assertIn("Config", err)

    def test_missing_secret_fatal(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_root(root, "http://127.0.0.1:1", with_secret=False)
            rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
            self.assertNotEqual(rc, 0)
            self.assertIn("secret", err.lower())

    def test_no_dev_flag_fatal(self):
        with tempfile.TemporaryDirectory() as root:
            _setup_root(root, "http://127.0.0.1:1")
            rc, out, err = _run("sync-media", "--root", root)
            self.assertNotEqual(rc, 0)

    def test_missing_manifest_fatal(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
                self.assertNotEqual(rc, 0)
                self.assertIn("Manifest", err)
        finally:
            server.shutdown()

    def test_no_token_secret_auth_in_output(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)
                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)

                combined = out + err
                self.assertNotIn(TEST_TOKEN, combined)
                self.assertNotIn(TEST_SECRET, combined)
                self.assertNotIn("Authorization", combined)
                self.assertNotIn("Bearer", combined)
                self.assertNotIn("access_token", combined.lower())
                self.assertNotIn("device_secret", combined.lower())
        finally:
            server.shutdown()

    def test_no_media_path_in_output(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)
                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)

                self.assertNotIn("creatives/", out)
                self.assertNotIn("media_path", out)
                self.assertNotIn("local_path", out.lower())
                self.assertNotIn("file_path", out.lower())
        finally:
            server.shutdown()

    def test_no_media_bytes_in_output(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)
                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)

                self.assertNotIn(TEST_CONTENT_1.decode("latin-1"), out)
                self.assertNotIn(TEST_CONTENT_2.decode("latin-1"), out)
        finally:
            server.shutdown()

    def test_no_stacktrace(self):
        server, thr, port = _start_server(MediaSyncHandler)
        try:
            with tempfile.TemporaryDirectory() as root:
                _setup_root(root, f"http://127.0.0.1:{port}")
                _run("sync-manifest", "--root", root, *DEV_FLAG)
                MediaSyncHandler.AUTH_FAIL = 401
                rc, out, err = _run("sync-media", "--root", root, *DEV_FLAG)
                self.assertNotIn("Traceback", err)
                self.assertNotIn("stacktrace", (out + err).lower())
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
