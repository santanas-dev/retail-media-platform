"""Tests for kso_player.cli event-dry-run — event draft CLI, in-memory only."""

import hashlib as _hl
import json as _json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
PNG_SHA = _hl.sha256(PNG).hexdigest()
MVID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MHASH = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
MID1 = "11111111-1111-1111-1111-111111111111"

MANIFEST_FILE = "manifest/current_manifest.json"
MEDIA_CURRENT = "media/current"

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
}

PKG_DIR = Path(__file__).resolve().parent.parent


def _run_cli(*args):
    cmd = [sys.executable, "-m", "kso_player.cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PKG_DIR))
    return proc.stdout, proc.stderr, proc.returncode


def _setup_ready(root):
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "manifest").mkdir(parents=True, exist_ok=True)
    (root / MEDIA_CURRENT).mkdir(parents=True, exist_ok=True)
    item = {"manifest_item_id": MID1, "filename": "item.png",
            "content_type": "image/png", "sha256": PNG_SHA,
            "size_bytes": len(PNG), "duration_ms": 5000, "order": 0}
    manifest = {"manifest_version_id": MVID, "manifest_hash": MHASH,
                "source": "current", "generated_at": "2026-06-20T10:00:00Z",
                "valid_until": None, "fetched_at": "2026-06-20T10:01:00Z",
                "campaign_id": None, "items": [item]}
    (root / MANIFEST_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST_FILE).write_text(_json.dumps(manifest))
    (root / MEDIA_CURRENT / "item.png").write_bytes(PNG)


# ══════════════════════════════════════════════════════════════════════

class TestEventDryRunHelp(unittest.TestCase):
    def test_help(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("event-dry-run", out)

    def test_event_dry_run_help(self):
        out, err, rc = _run_cli("event-dry-run", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--root", out)
        self.assertIn("--state", out)


class TestEventDryRunHappy(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_idle_would_play(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertEqual(rc, 0)
        self.assertIn("event_type: would_play", out)
        self.assertIn("event_status: draft", out)
        self.assertIn("simulation_status: would_play", out)
        self.assertIn("session_action: play", out)
        self.assertIn("selected_order:", out)
        self.assertIn("selected_content_type:", out)
        self.assertIn("selected_duration_ms:", out)

    def test_no_sleep(self):
        t0 = time.time()
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertLess(time.time() - t0, 2.0, "event-dry-run should not sleep")


class TestEventDryRunBlocked(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_payment_blocked(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "payment")
        self.assertEqual(rc, 1)
        self.assertIn("event_type: blocked", out)
        self.assertIn("event_status: draft", out)
        self.assertIn("session_action: stop", out)

    def test_transaction_blocked(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "transaction")
        self.assertEqual(rc, 1)

    def test_service_blocked(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "service")
        self.assertEqual(rc, 1)

    def test_error_blocked(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "error")
        self.assertEqual(rc, 1)

    def test_maintenance_blocked(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "maintenance")
        self.assertEqual(rc, 1)

    def test_offline_blocked(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "offline")
        self.assertEqual(rc, 1)

    def test_unknown_exit_1(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "unknown")
        self.assertEqual(rc, 1)


class TestEventDryRunNotReady(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_not_ready(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertEqual(rc, 1)
        # When playlist is not ready, safety blocked → event_type=blocked
        self.assertIn("event_type: blocked", out)


class TestEventDryRunArgs(unittest.TestCase):
    def test_missing_root(self):
        out, err, rc = _run_cli("event-dry-run", "--state", "idle")
        self.assertEqual(rc, 2)

    def test_missing_state(self):
        out, err, rc = _run_cli("event-dry-run", "--root", "/tmp/xyz")
        self.assertEqual(rc, 2)

    def test_invalid_state(self):
        out, err, rc = _run_cli("event-dry-run", "--root", "/tmp/xyz", "--state", "watching_tv")
        self.assertEqual(rc, 2)


class TestEventDryRunSecurity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_no_filename(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertNotIn("item.png", out)
        self.assertNotIn("filename", out.lower())

    def test_no_manifest_item_id(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertNotIn(MID1, out)

    def test_no_sha256(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertNotIn(PNG_SHA[:16], out)

    def test_no_absolute_paths(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertNotIn(str(self.root), out + err)

    def test_no_forbidden(self):
        for state in ["idle", "payment"]:
            out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", state)
            combined = (out + err).lower()
            for fb in FORBIDDEN:
                self.assertNotIn(fb, combined, f"state='{state}' contains forbidden '{fb}'")

    def test_no_full_manifest(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertNotIn(MVID, out + err)

    def test_no_media_bytes(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertNotIn("PNG", out + err)

    def test_no_stacktrace(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertNotIn("Traceback", out + err)


class TestEventDryRunNoIO(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_no_backend_no_files(self):
        out, err, rc = _run_cli("event-dry-run", "--root", str(self.root), "--state", "idle")
        self.assertEqual(rc, 0)

    def test_no_secret_config_token(self):
        root2 = Path(tempfile.mkdtemp())
        (root2 / "manifest").mkdir()
        (root2 / MEDIA_CURRENT).mkdir(parents=True)
        item = {"manifest_item_id": MID1, "filename": "item.png",
                "content_type": "image/png", "sha256": PNG_SHA,
                "size_bytes": len(PNG), "duration_ms": 5000, "order": 0}
        manifest = {"manifest_version_id": MVID, "manifest_hash": MHASH,
                    "source": "current", "generated_at": "2026-06-20T10:00:00Z",
                    "valid_until": None, "fetched_at": "2026-06-20T10:01:00Z",
                    "campaign_id": None, "items": [item]}
        (root2 / MANIFEST_FILE).parent.mkdir(parents=True, exist_ok=True)
        (root2 / MANIFEST_FILE).write_text(_json.dumps(manifest))
        (root2 / MEDIA_CURRENT / "item.png").write_bytes(PNG)
        out, err, rc = _run_cli("event-dry-run", "--root", str(root2), "--state", "payment")
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
