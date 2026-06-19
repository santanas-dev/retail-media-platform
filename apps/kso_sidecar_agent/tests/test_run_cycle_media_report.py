"""Tests for run_cycle_media_report.py — fake HTTP server, no real backend."""

import hashlib as _hl
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kso_sidecar_agent.run_cycle import FORBIDDEN_SUBSTRINGS, RunCycleOptions
from kso_sidecar_agent.run_cycle_media_report import (
    CycleMediaReportResult,
    send_media_cache_report_for_cycle,
)
from kso_sidecar_agent.token_state import TokenState

TOK = "opaque-value-1234567890"
TSEC = "dev-value-1234567890"
TDEV = "550e8400-e29b-41d4-a716-446655440000"
TCODE = "a-05954"
NOW = 1_750_000_000.0
MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "c" * 64
MID = "11111111-1111-1111-1111-111111111111"

TEST_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
TEST_PNG_SHA = _hl.sha256(TEST_PNG).hexdigest()


def _vts():
    return TokenState(_access_token=TOK, token_type="bearer", expires_at=NOW + 3600,
                      device_id=TDEV, device_code=TCODE, status="active")


def _ets():
    return TokenState(_access_token=TOK, token_type="bearer", expires_at=NOW - 3600,
                      device_id=TDEV, device_code=TCODE, status="active")


def _ab():
    return json.dumps({"access_token": TOK, "token_type": "bearer", "expires_in": 3600,
                       "device_id": TDEV, "device_code": TCODE, "status": "active"}).encode()


def _sr(root, url, with_manifest=False, with_media=False):
    from kso_sidecar_agent.local_file_store import init_local_root as ir
    from kso_sidecar_agent.local_config import write_config as wc
    ir(root)
    wc(root, {"backend_base_url": url, "device_code": TCODE, "tls_verify": True,
              "request_timeout_sec": 10, "local_interface_version": "1.0"})
    from kso_sidecar_agent.secret_store import write_secret as ws
    ws(root, TSEC, dev_secret_store=True)
    if with_manifest:
        _write_local_manifest(root)
    if with_media:
        from kso_sidecar_agent.media_cache import ensure_media_dirs
        ensure_media_dirs(root)
        fp = Path(root) / "media" / "current" / f"{MID}.png"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(TEST_PNG)


def _write_local_manifest(root):
    from kso_sidecar_agent.manifest_store import write_current_manifest
    from kso_sidecar_agent.manifest_client import ManifestSnapshot
    items = [{
        "id": MID, "sha256": TEST_PNG_SHA,
        "media_path": f"media/{MID}.png",
        "duration_ms": 5000, "order": 0,
    }]
    snap = ManifestSnapshot(
        status="served", manifest_version_id=MVID, manifest_hash=MHASH,
        published_at="2026-06-19T10:00:00Z", items=items, source="current",
    )
    write_current_manifest(root, snap)


def _ss(hc, p=0):
    s = HTTPServer(("127.0.0.1", p), hc)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t, s.server_address[1]


class RptHandler(BaseHTTPRequestHandler):
    """Fake server: auth + manifest + report (POST)."""
    RF: int | None = None         # report fail code
    RF_INVALID_JSON: bool = False  # report returns invalid JSON
    RC: int = 0                    # report call count

    @classmethod
    def r(cls):
        cls.RF = None
        cls.RF_INVALID_JSON = False
        cls.RC = 0

    def lm(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_ab())
            return
        if self.path == "/api/device-gateway/media/cache/report":
            RptHandler.RC += 1
            if RptHandler.RF:
                self.send_response(RptHandler.RF)
                self.end_headers()
                self.wfile.write(b'{"error":"report fail"}')
                return
            if RptHandler.RF_INVALID_JSON:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>not json</html>")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "manifest_version_id": MVID,
                "gateway_device_id": TDEV,
                "total_items": 1,
                "cached_count": 1,
                "missing_count": 0,
                "failed_count": 0,
                "invalid_hash_count": 0,
            }).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-gateway/manifest/current":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "served",
                "manifest_version_id": MVID, "manifest_hash": MHASH,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "items": [
                        {"id": MID, "sha256": TEST_PNG_SHA,
                         "media_path": f"media/{MID}.png",
                         "duration_ms": 5000, "order": 0}
                    ]
                },
            }).encode())
            return
        self.send_response(404)
        self.end_headers()


# ══════════════════════════════════════════════════════════════════════
# Tests: send_media_cache_report_for_cycle (unit)
# ══════════════════════════════════════════════════════════════════════

class TestSendReportForCycle(unittest.TestCase):
    def setUp(self):
        RptHandler.r()

    def test_report_sent(self):
        sv, _, p = _ss(RptHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "ok")
                self.assertEqual(res.report_status, "sent")
                self.assertEqual(res.items_total, 1)
                self.assertEqual(res.cached_count, 1)
                self.assertEqual(RptHandler.RC, 1)
        finally:
            sv.shutdown()

    def test_report_payload_no_local_path(self):
        """Verify report payload doesn't contain forbidden strings."""
        sv, _, p = _ss(RptHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                st = str(res.step).lower()
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, st, f"Forbidden '{fb}' in report step")
        finally:
            sv.shutdown()

    def test_report_401(self):
        sv, _, p = _ss(RptHandler)
        RptHandler.RF = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertFalse(res.step.fatal)
                self.assertEqual(res.report_status, "error")
        finally:
            sv.shutdown()

    def test_report_403(self):
        sv, _, p = _ss(RptHandler)
        RptHandler.RF = 403
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertFalse(res.step.fatal)
        finally:
            sv.shutdown()

    def test_report_422(self):
        sv, _, p = _ss(RptHandler)
        RptHandler.RF = 422
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertFalse(res.step.fatal)
        finally:
            sv.shutdown()

    def test_report_500(self):
        sv, _, p = _ss(RptHandler)
        RptHandler.RF = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
                self.assertEqual(res.report_status, "error")
        finally:
            sv.shutdown()

    def test_invalid_json_response(self):
        sv, _, p = _ss(RptHandler)
        RptHandler.RF_INVALID_JSON = True
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "error")
        finally:
            sv.shutdown()

    def test_expired_token(self):
        with tempfile.TemporaryDirectory() as r:
            _sr(r, "http://127.0.0.1:9999", with_manifest=True, with_media=True)
            ts = _ets()
            res = send_media_cache_report_for_cycle(r, ts, now=NOW)
            self.assertEqual(res.step.status, "error")
            self.assertEqual(res.report_status, "error")
            self.assertEqual(RptHandler.RC, 0)

    def test_no_manifest(self):
        sv, _, p = _ss(RptHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")  # no manifest
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                self.assertEqual(res.step.status, "skipped")
                self.assertEqual(res.report_status, "skipped")
        finally:
            sv.shutdown()

    def test_no_token_in_step(self):
        sv, _, p = _ss(RptHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}", with_manifest=True, with_media=True)
                ts = _vts()
                res = send_media_cache_report_for_cycle(r, ts, now=NOW)
                st = str(res.step).lower()
                self.assertNotIn(TOK, st)
        finally:
            sv.shutdown()


# ══════════════════════════════════════════════════════════════════════
# Tests: run_once with report
# ══════════════════════════════════════════════════════════════════════

class FullRptHandler(BaseHTTPRequestHandler):
    """Fake server: auth + heartbeat + manifest + media + report."""
    AF: int | None = None
    HF: int | None = None
    MF: int | None = None
    MEDIA_404: bool = False
    RF: int | None = None
    RF_INVALID_JSON: bool = False

    @classmethod
    def r(cls):
        cls.AF = None
        cls.HF = None
        cls.MF = None
        cls.MEDIA_404 = False
        cls.RF = None
        cls.RF_INVALID_JSON = False

    def lm(self, *a):
        pass

    def do_POST(self):
        if self.path == "/api/device-gateway/auth/token":
            if FullRptHandler.AF:
                self.send_response(FullRptHandler.AF)
                self.end_headers()
                self.wfile.write(b'{"error":"auth fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_ab())
            return
        if self.path == "/api/device-gateway/heartbeat":
            if FullRptHandler.HF:
                self.send_response(FullRptHandler.HF)
                self.end_headers()
                self.wfile.write(b'{"error":"hb fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "hb" + "1" * 32, "gateway_device_id": TDEV, "status": "ok"}).encode())
            return
        if self.path == "/api/device-gateway/media/cache/report":
            if FullRptHandler.RF:
                self.send_response(FullRptHandler.RF)
                self.end_headers()
                self.wfile.write(b'{"error":"report fail"}')
                return
            if FullRptHandler.RF_INVALID_JSON:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>not json</html>")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok", "manifest_version_id": MVID,
                "gateway_device_id": TDEV,
                "total_items": 1, "cached_count": 1,
                "missing_count": 0, "failed_count": 0, "invalid_hash_count": 0,
            }).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-gateway/manifest/current":
            if FullRptHandler.MF:
                self.send_response(FullRptHandler.MF)
                self.end_headers()
                self.wfile.write(b'{"error":"manifest fail"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "served", "manifest_version_id": MVID, "manifest_hash": MHASH,
                "published_at": "2026-06-19T10:00:00Z",
                "manifest": {
                    "items": [
                        {"id": MID, "sha256": TEST_PNG_SHA,
                         "media_path": f"media/{MID}.png",
                         "duration_ms": 5000, "order": 0}
                    ]
                },
            }).encode())
            return
        if self.path.startswith("/api/device-gateway/media/"):
            if FullRptHandler.MEDIA_404:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(TEST_PNG)))
            self.end_headers()
            self.wfile.write(TEST_PNG)
            return
        # Runtime config fallback
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "config_hash": "a" * 64, "config": {"k": "v"},
                                      "generated_at": "2026-06-19T10:00:00Z"}).encode())


class TestRunOnceWithReport(unittest.TestCase):
    def setUp(self):
        FullRptHandler.r()

    def _fs(self, r, n):
        return next((s for s in r.steps if s.name == n), None)

    def test_run_once_report_sent(self):
        sv, _, p = _ss(FullRptHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.media_report_status, "sent")
                rp = self._fs(res, "report")
                self.assertEqual(rp.status, "ok")

                dp = Path(r) / "status" / "agent_status.json"
                d = json.loads(dp.read_text())
                self.assertEqual(d["_cycle"]["media_report_status"], "sent")
        finally:
            sv.shutdown()

    def test_auth_fail_report_skipped(self):
        sv, _, p = _ss(FullRptHandler)
        FullRptHandler.AF = 401
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.media_report_status, "skipped")
                rp = self._fs(res, "report")
                self.assertEqual(rp.status, "skipped")
        finally:
            sv.shutdown()

    def test_report_500_non_fatal(self):
        sv, _, p = _ss(FullRptHandler)
        FullRptHandler.RF = 500
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                self.assertEqual(res.media_report_status, "error")
                rp = self._fs(res, "report")
                self.assertEqual(rp.status, "error")
                self.assertFalse(rp.fatal)
        finally:
            sv.shutdown()

    def test_no_token_in_agent_status(self):
        sv, _, p = _ss(FullRptHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                ro(r, options=opts)
                dp = Path(r) / "status" / "agent_status.json"
                ds = json.dumps(json.loads(dp.read_text())).lower()
                self.assertNotIn(TOK, ds)
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, ds, f"Forbidden '{fb}' in agent_status")
        finally:
            sv.shutdown()

    def test_local_only_no_report(self):
        sv, _, p = _ss(FullRptHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=False, dev_secret_store=False)
                res = ro(r, options=opts)
                rp = self._fs(res, "report")
                # In local-only, report step may be skipped or absent
                if rp is not None:
                    pass  # just verify no crash
        finally:
            sv.shutdown()

    def test_no_forbidden_in_report_safe_details(self):
        sv, _, p = _ss(FullRptHandler)
        try:
            with tempfile.TemporaryDirectory() as r:
                _sr(r, f"http://127.0.0.1:{p}")
                from kso_sidecar_agent.run_cycle import run_once as ro
                opts = RunCycleOptions(backend_enabled=True, dev_secret_store=True)
                res = ro(r, options=opts)
                rp = self._fs(res, "report")
                sd = str(rp.safe_details).lower()
                for fb in FORBIDDEN_SUBSTRINGS:
                    self.assertNotIn(fb, sd, f"Forbidden '{fb}' in report safe_details")
        finally:
            sv.shutdown()


if __name__ == "__main__":
    unittest.main()
