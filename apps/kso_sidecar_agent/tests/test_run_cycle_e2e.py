"""KSO Sidecar Full Run Cycle E2E Smoke — fake backend, no real backend."""

import hashlib as _hl
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.run_cycle import FORBIDDEN_SUBSTRINGS, RunCycleOptions

TOK = "opaque-value-1234567890"
TSEC = "dev-value-1234567890"
TDEV = "550e8400-e29b-41d4-a716-446655440000"
TCODE = "a-05954"
MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "c" * 64
MID1 = "11111111-1111-1111-1111-111111111111"
MID2 = "22222222-2222-2222-2222-222222222222"

PNG1 = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 80
PNG1_SHA = _hl.sha256(PNG1).hexdigest()
PNG2_SHA = _hl.sha256(PNG2).hexdigest()


def _e2e_ab():
    return json.dumps({"access_token": TOK, "token_type": "bearer", "expires_in": 3600,
                       "device_id": TDEV, "device_code": TCODE, "status": "active"}).encode()


def _e2e_setup(root, url):
    from kso_sidecar_agent.local_file_store import init_local_root
    from kso_sidecar_agent.local_config import write_config
    from kso_sidecar_agent.secret_store import write_secret
    init_local_root(root)
    write_config(root, {"backend_base_url": url, "device_code": TCODE, "tls_verify": True,
                        "request_timeout_sec": 10, "local_interface_version": "1.0"})
    write_secret(root, TSEC, dev_secret_store=True)


def _ss(hc, p=0):
    s = HTTPServer(("127.0.0.1", p), hc)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t, s.server_address[1]


# ══════════════════════════════════════════════════════════════════════
# FULL Backend Handler
# ══════════════════════════════════════════════════════════════════════

class E2EBackend(BaseHTTPRequestHandler):
    """Complete fake backend: auth, rc, heartbeat, manifest, media (2 items), report."""

    AUTH_FAIL: int | None = None         # if set, return this code for auth
    MEDIA_404_ITEM: str | None = None    # item ID to 404 on
    MEDIA_500_ITEM: str | None = None    # item ID to 500 on
    REPORT_FAIL: int | None = None       # if set, return this code for report
    HB_FAIL: int | None = None           # if set, return this code for heartbeat

    hb_count: int = 0
    report_count: int = 0
    manifest_count: int = 0
    media_count: int = 0

    @classmethod
    def reset(cls):
        cls.AUTH_FAIL = None
        cls.MEDIA_404_ITEM = None
        cls.MEDIA_500_ITEM = None
        cls.REPORT_FAIL = None
        cls.HB_FAIL = None
        cls.hb_count = 0
        cls.report_count = 0
        cls.manifest_count = 0
        cls.media_count = 0

    def log_message(self, *a):
        pass

    # ── POST ──────────────────────────────────────────────────────
    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            if E2EBackend.AUTH_FAIL:
                self.send_response(E2EBackend.AUTH_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"auth fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_e2e_ab())
            return

        if self.path == "/api/device-gateway/heartbeat":
            E2EBackend.hb_count += 1
            if E2EBackend.HB_FAIL:
                self.send_response(E2EBackend.HB_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"hb fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "id": "hb" + "1" * 32, "gateway_device_id": TDEV, "status": "ok",
            }).encode())
            return

        if self.path == "/api/device-gateway/media/cache/report":
            E2EBackend.report_count += 1
            if E2EBackend.REPORT_FAIL:
                self.send_response(E2EBackend.REPORT_FAIL)
                self.end_headers()
                self.wfile.write(b'{"error":"report fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok", "manifest_version_id": MVID,
                "gateway_device_id": TDEV,
                "total_items": 2, "cached_count": 2, "missing_count": 0,
                "failed_count": 0, "invalid_hash_count": 0,
            }).encode())
            return

        self.send_response(404)
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────
    def do_GET(self):
        # Runtime config
        if self.path == "/api/device-gateway/config/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok", "config_hash": "a" * 64, "config": {"k": "v"},
                "generated_at": "2026-06-19T10:00:00Z",
            }).encode())
            return

        # Manifest
        if self.path == "/api/device-gateway/manifest/current":
            E2EBackend.manifest_count += 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "served",
                "manifest_version_id": MVID,
                "manifest_hash": MHASH,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "items": [
                        {"id": MID1, "sha256": PNG1_SHA, "media_path": f"media/{MID1}.png",
                         "duration_ms": 5000, "order": 0},
                        {"id": MID2, "sha256": PNG2_SHA, "media_path": f"media/{MID2}.png",
                         "duration_ms": 3000, "order": 1},
                    ]
                },
            }).encode())
            return

        # Media metadata (if accessed separately)
        if self.path.startswith("/api/device-gateway/media/") and self.path.endswith("/metadata"):
            item_id = self.path.split("/")[-2]
            if item_id == MID1:
                sha, size = PNG1_SHA, len(PNG1)
            else:
                sha, size = PNG2_SHA, len(PNG2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "manifest_item_id": item_id, "sha256": sha,
                "content_type": "image/png", "size_bytes": size,
                "duration_ms": 5000, "status": "ok",
            }).encode())
            return

        # Media binary
        if self.path.startswith("/api/device-gateway/media/"):
            E2EBackend.media_count += 1
            item_id = self.path.split("/")[-1]

            if E2EBackend.MEDIA_404_ITEM and item_id == E2EBackend.MEDIA_404_ITEM:
                self.send_response(404)
                self.end_headers()
                return
            if E2EBackend.MEDIA_500_ITEM and item_id == E2EBackend.MEDIA_500_ITEM:
                self.send_response(500)
                self.end_headers()
                return

            if item_id == MID1:
                content = PNG1
            elif item_id == MID2:
                content = PNG2
            else:
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_response(404)
        self.end_headers()


# ══════════════════════════════════════════════════════════════════════
# E2E Tests
# ══════════════════════════════════════════════════════════════════════

class TestRunCycleE2E(unittest.TestCase):

    def setUp(self):
        E2EBackend.reset()

    def _no_forbidden_in(self, obj, label=""):
        """Assert no forbidden substrings anywhere in obj."""
        s = str(obj).lower()
        if isinstance(obj, dict):
            s = json.dumps(obj).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(fb, s, f"Forbidden '{fb}' in {label}")

    # ── Happy Path ──────────────────────────────────────────────────

    def test_happy_path_full_cycle(self):
        """Auth ok → rc → initial hb → manifest → 2 media → report → final hb."""
        sv, _, p = _ss(E2EBackend)
        try:
            with tempfile.TemporaryDirectory() as r:
                _e2e_setup(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)

                # Basic status
                self.assertEqual(result.status, "ok")
                self.assertEqual(result.last_auth_status, "ok")
                self.assertEqual(result.heartbeat_status, "sent")
                self.assertEqual(result.final_heartbeat_status, "sent")
                self.assertEqual(result.manifest_status, "updated")
                self.assertTrue(result.media_cache_complete)
                self.assertEqual(result.media_items_total, 2)
                self.assertEqual(result.media_items_cached, 2)
                self.assertEqual(result.media_items_missing, 0)
                self.assertEqual(result.media_items_failed, 0)
                self.assertEqual(result.media_report_status, "sent")

                # Backend call counts
                self.assertEqual(E2EBackend.hb_count, 2)
                self.assertEqual(E2EBackend.report_count, 1)
                self.assertEqual(E2EBackend.manifest_count, 1)
                self.assertEqual(E2EBackend.media_count, 2)

                # Media files
                mp1 = Path(r) / "media" / "current" / f"{MID1}.png"
                mp2 = Path(r) / "media" / "current" / f"{MID2}.png"
                self.assertTrue(mp1.exists())
                self.assertTrue(mp2.exists())
                self.assertEqual(_hl.sha256(mp1.read_bytes()).hexdigest(), PNG1_SHA)
                self.assertEqual(_hl.sha256(mp2.read_bytes()).hexdigest(), PNG2_SHA)

                # Agent status
                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                c = d["_cycle"]
                self.assertEqual(c["last_cycle_status"], "ok")
                self.assertEqual(c["heartbeat_status"], "sent")
                self.assertEqual(c["final_heartbeat_status"], "sent")
                self.assertTrue(c["media_cache_complete"])
                self.assertEqual(c["media_items_total"], 2)
                self.assertEqual(c["media_items_cached"], 2)
                self.assertEqual(c["media_report_status"], "sent")
                self.assertEqual(c["manifest_status"], "updated")

                # Security
                self._no_forbidden_in(result.safe_summary(), "happy safe_summary")
                self._no_forbidden_in(d, "happy agent_status")
        finally:
            sv.shutdown()

    # ── Warning Path: one media 404 ─────────────────────────────────

    def test_one_media_404_warning(self):
        """One media item 404 → incomplete cache, cycle warning."""
        sv, _, p = _ss(E2EBackend)
        E2EBackend.MEDIA_404_ITEM = MID2
        try:
            with tempfile.TemporaryDirectory() as r:
                _e2e_setup(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)

                self.assertEqual(result.status, "warning")
                self.assertFalse(result.media_cache_complete)
                self.assertEqual(result.media_items_missing, 1)
                self.assertEqual(result.media_items_cached, 1)  # MID1 downloaded
                # Report and final hb still sent
                self.assertEqual(result.media_report_status, "sent")
                self.assertEqual(result.final_heartbeat_status, "sent")
                self.assertEqual(E2EBackend.report_count, 1)
                self.assertEqual(E2EBackend.hb_count, 2)

                self._no_forbidden_in(result.safe_summary(), "404 warning safe_summary")
        finally:
            sv.shutdown()

    # ── Warning Path: report 500 ───────────────────────────────────

    def test_report_500_warning(self):
        """Report 500 → cycle warning, media/manifest untouched."""
        sv, _, p = _ss(E2EBackend)
        E2EBackend.REPORT_FAIL = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _e2e_setup(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)

                self.assertEqual(result.status, "warning")
                self.assertEqual(result.media_report_status, "error")
                self.assertTrue(result.media_cache_complete)  # media ok
                self.assertEqual(result.final_heartbeat_status, "sent")  # still sent
                self.assertEqual(E2EBackend.hb_count, 2)

                # Media files untouched
                mp1 = Path(r) / "media" / "current" / f"{MID1}.png"
                self.assertTrue(mp1.exists())
                # Manifest untouched
                mp = Path(r) / "manifest" / "current_manifest.json"
                self.assertTrue(mp.exists())

                self._no_forbidden_in(result.safe_summary(), "report 500 safe_summary")
        finally:
            sv.shutdown()

    # ── Auth Failure ────────────────────────────────────────────────

    def test_auth_failure(self):
        """Auth 401 → error, no backend calls beyond auth."""
        sv, _, p = _ss(E2EBackend)
        E2EBackend.AUTH_FAIL = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _e2e_setup(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)

                self.assertEqual(result.status, "error")
                self.assertEqual(result.last_auth_status, "error")
                self.assertEqual(result.heartbeat_status, "skipped")
                self.assertEqual(result.final_heartbeat_status, "skipped")
                # No backend calls beyond auth
                self.assertEqual(E2EBackend.hb_count, 0)
                self.assertEqual(E2EBackend.manifest_count, 0)
                self.assertEqual(E2EBackend.media_count, 0)
                self.assertEqual(E2EBackend.report_count, 0)

                # Token not in agent_status
                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                ds = json.dumps(d).lower()
                self.assertNotIn(TOK, ds)
                self._no_forbidden_in(d, "auth fail agent_status")
        finally:
            sv.shutdown()

    # ── Local-only regression ─────────────────────────────────────

    def test_local_only_no_backend_calls(self):
        """backend_enabled=False → zero backend calls."""
        sv, _, p = _ss(E2EBackend)
        try:
            with tempfile.TemporaryDirectory() as r:
                _e2e_setup(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                result = run_once(r, options=opts)

                self.assertEqual(E2EBackend.hb_count, 0)
                self.assertEqual(E2EBackend.manifest_count, 0)
                self.assertEqual(E2EBackend.media_count, 0)
                self.assertEqual(E2EBackend.report_count, 0)

                self._no_forbidden_in(result.safe_summary(), "local-only safe_summary")
        finally:
            sv.shutdown()

    # ── Security checks on full result ────────────────────────────

    def test_no_forbidden_in_full_result(self):
        """Complete cycle — verify no forbidden strings anywhere in result."""
        sv, _, p = _ss(E2EBackend)
        try:
            with tempfile.TemporaryDirectory() as r:
                _e2e_setup(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                result = run_once(r, options=opts)

                # Scan all step results
                for step in result.steps:
                    self._no_forbidden_in(step, f"step {step.name}")
                    self._no_forbidden_in(step.safe_details, f"step {step.name} safe_details")
                    self._no_forbidden_in(step.message, f"step {step.name} message")

                # Scan agent_status
                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                self._no_forbidden_in(d, "full agent_status")

                # Check agent_status specifically for IP/URL
                ds = json.dumps(d).lower()
                self.assertNotIn("127.0.0.1", ds)
                self.assertNotIn("backend_base_url", ds)
        finally:
            sv.shutdown()


if __name__ == "__main__":
    unittest.main()
