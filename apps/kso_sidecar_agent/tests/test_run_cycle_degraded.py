"""Tests for degraded/offline fallback in run_cycle — fake backend, no real backend."""

import hashlib as _hl
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.run_cycle import (
    FORBIDDEN_SUBSTRINGS,
    RunCycleOptions,
    _apply_degraded_fallback,
    _check_local_content_ready,
    _is_degradable_backend_error,
)

TOK = "opaque-value-1234567890"
TSEC = "dev-value-1234567890"
TDEV = "550e8400-e29b-41d4-a716-446655440000"
TCODE = "a-05954"
MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "c" * 64
MID = "11111111-1111-1111-1111-111111111111"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
PNG_SHA = _hl.sha256(PNG).hexdigest()


def _ab():
    return json.dumps({"access_token": TOK, "token_type": "bearer", "expires_in": 3600,
                       "device_id": TDEV, "device_code": TCODE, "status": "active"}).encode()


def _sr(root, url, with_manifest=False, with_media=False):
    from kso_sidecar_agent.local_file_store import init_local_root
    from kso_sidecar_agent.local_config import write_config
    from kso_sidecar_agent.secret_store import write_secret
    init_local_root(root)
    write_config(root, {"backend_base_url": url, "device_code": TCODE, "tls_verify": True,
                        "request_timeout_sec": 10, "local_interface_version": "1.0"})
    write_secret(root, TSEC, dev_secret_store=True)
    if with_manifest:
        _write_local_manifest(root)
    if with_media:
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        ensure_media_dirs(root)
        fp = Path(root) / "media" / "current" / f"{MID}.png"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(PNG)


def _write_local_manifest(root):
    from kso_sidecar_agent.manifest_store import write_current_manifest
    from kso_sidecar_agent.manifest_client import ManifestSnapshot
    items = [{"id": MID, "sha256": PNG_SHA, "media_path": f"media/{MID}.png",
              "duration_ms": 5000, "order": 0}]
    snap = ManifestSnapshot(status="served", manifest_version_id=MVID, manifest_hash=MHASH,
                            published_at="2026-06-19T10:00:00Z", items=items, source="current")
    write_current_manifest(root, snap)


def _ss(hc, p=0):
    s = HTTPServer(("127.0.0.1", p), hc)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t, s.server_address[1]


class DegradedHandler(BaseHTTPRequestHandler):
    """Backend that simulates various failure modes."""
    AUTH_FAIL: int | None = None        # auth error code
    ALL_FAIL: bool = False              # all endpoints fail

    @classmethod
    def reset(cls):
        cls.AUTH_FAIL = None
        cls.ALL_FAIL = False

    def log_message(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            if DegradedHandler.AUTH_FAIL:
                self.send_response(DegradedHandler.AUTH_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"fail"}')
                return
            if DegradedHandler.ALL_FAIL:
                self.send_response(500)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_ab())
            return
        if self.path == "/api/device-gateway/heartbeat":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "hb" + "1"*32, "gateway_device_id": TDEV, "status": "ok"}).encode())
            return
        if self.path == "/api/device-gateway/media/cache/report":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "manifest_version_id": MVID,
                                          "gateway_device_id": TDEV, "total_items": 1,
                                          "cached_count": 1, "missing_count": 0,
                                          "failed_count": 0, "invalid_hash_count": 0}).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-gateway/config/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "config_hash": "a"*64, "config": {"k": "v"},
                                          "generated_at": "2026-06-19T10:00:00Z"}).encode())
            return
        if self.path == "/api/device-gateway/manifest/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "served", "manifest_version_id": MVID, "manifest_hash": MHASH,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {"items": [
                    {"id": MID, "sha256": PNG_SHA, "media_path": f"media/{MID}.png",
                     "duration_ms": 5000, "order": 0}
                ]},
            }).encode())
            return
        if self.path.startswith("/api/device-gateway/media/"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG)))
            self.end_headers()
            self.wfile.write(PNG)
            return
        self.send_response(404)
        self.end_headers()


# ══════════════════════════════════════════════════════════════════════
# Unit: helpers
# ══════════════════════════════════════════════════════════════════════

class TestDegradedHelpers(unittest.TestCase):

    def test_local_content_ready_true(self):
        with tempfile.TemporaryDirectory() as r:
            _sr(r, "http://127.0.0.1:1", with_manifest=True, with_media=True)
            self.assertTrue(_check_local_content_ready(r))

    def test_local_content_ready_false_no_manifest(self):
        with tempfile.TemporaryDirectory() as r:
            _sr(r, "http://127.0.0.1:1")
            self.assertFalse(_check_local_content_ready(r))

    def test_local_content_ready_false_no_media(self):
        with tempfile.TemporaryDirectory() as r:
            _sr(r, "http://127.0.0.1:1", with_manifest=True)  # no media
            self.assertFalse(_check_local_content_ready(r))


# ══════════════════════════════════════════════════════════════════════
# Integration: run_once degraded
# ══════════════════════════════════════════════════════════════════════

class TestRunOnceDegraded(unittest.TestCase):
    def setUp(self):
        DegradedHandler.reset()

    def _forbidden_in(self, obj, label=""):
        s = str(obj).lower()
        if isinstance(obj, dict):
            s = json.dumps(obj).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, s, f"Forbidden '{fb}' in {label}")

    def test_auth_500_local_complete_degraded(self):
        """Auth 500 + local cache complete → degraded."""
        DegradedHandler.AUTH_FAIL = 500
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self.assertEqual(result.status, "degraded")
                self.assertTrue(result.offline_ready)
                self.assertTrue(result.can_play_local_content)
                self.assertEqual(result.degraded_reason, "backend_unavailable")

                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                self.assertEqual(d["_cycle"]["last_cycle_status"], "degraded")
                self.assertTrue(d["_cycle"].get("offline_ready"))
                self.assertTrue(d["_cycle"].get("can_play_local_content"))
                self.assertEqual(d["_cycle"]["degraded_reason"], "backend_unavailable")
                self._forbidden_in(d, "agent_status")
        finally:
            sv.shutdown()

    def test_auth_401_local_complete_not_degraded(self):
        """Auth 401 + local complete → error, NOT degraded."""
        DegradedHandler.AUTH_FAIL = 401
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self.assertEqual(result.status, "error")
                self.assertFalse(result.offline_ready)
        finally:
            sv.shutdown()

    def test_auth_403_not_degraded(self):
        DegradedHandler.AUTH_FAIL = 403
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self.assertEqual(result.status, "error")
        finally:
            sv.shutdown()

    def test_auth_422_not_degraded(self):
        DegradedHandler.AUTH_FAIL = 422
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self.assertEqual(result.status, "error")
        finally:
            sv.shutdown()

    def test_auth_500_no_manifest_not_degraded(self):
        """Auth 500 + no local manifest → error, not degraded."""
        DegradedHandler.AUTH_FAIL = 500
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")  # no manifest
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self.assertEqual(result.status, "error")
                self.assertEqual(result.degraded_reason, "local_cache_incomplete")
        finally:
            sv.shutdown()

    def test_auth_500_no_media_not_degraded(self):
        """Auth 500 + manifest but no media → error."""
        DegradedHandler.AUTH_FAIL = 500
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)  # no media
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self.assertEqual(result.status, "error")
                self.assertEqual(result.degraded_reason, "local_cache_incomplete")
        finally:
            sv.shutdown()

    def test_auth_500_corrupted_media_not_degraded(self):
        """Auth 500 + corrupted media → error, not degraded."""
        DegradedHandler.AUTH_FAIL = 500
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True)
                from kso_sidecar_agent.media_cache import ensure_media_dirs
                ensure_media_dirs(r)
                fp = Path(r) / "media" / "current" / f"{MID}.png"
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(b"corrupted data")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self.assertEqual(result.status, "error")
                self.assertFalse(result.offline_ready)
        finally:
            sv.shutdown()

    def test_local_only_not_degraded(self):
        """Local-only mode: degraded does not apply."""
        sv, _, p = _ss(DegradedHandler)
        DegradedHandler.AUTH_FAIL = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                result = run_once(r, options=opts)
                self.assertNotEqual(result.status, "degraded")
                self.assertFalse(result.offline_ready)
        finally:
            sv.shutdown()

    def test_degraded_no_forbidden_in_result(self):
        DegradedHandler.AUTH_FAIL = 500
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self._forbidden_in(result.safe_summary(), "degraded safe_summary")
                for step in result.steps:
                    self._forbidden_in(step, f"step {step.name}")
        finally:
            sv.shutdown()

    def test_degraded_full_backend_ok(self):
        """Full backend ok → not degraded, status ok."""
        sv, _, p = _ss(DegradedHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)
                self.assertEqual(result.status, "ok")
                self.assertFalse(result.offline_ready)  # not degraded
        finally:
            sv.shutdown()


if __name__ == "__main__":
    unittest.main()
