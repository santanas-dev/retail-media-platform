"""Tests for kso_sidecar_agent.cli pop-pickup-scan — safe aggregated scan CLI."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

POP_PENDING_DIR = "pop/pending"
POP_JSONL_FILE = "player_events.jsonl"

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "customer_id", "phone", "email", "receipt_number", "fiscal_data",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
    "filename", "manifest_item_id", "sha256",
    "stacktrace",
}

PKG_DIR = Path(__file__).resolve().parent.parent


def _run_cli(*args):
    cmd = [sys.executable, "-m", "kso_sidecar_agent.cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PKG_DIR))
    return proc.stdout, proc.stderr, proc.returncode


def _make_record(event_status="draft", event_type="would_play",
                 safety_state="idle", selected_order=0):
    return {
        "schema_version": 1,
        "event_type": event_type,
        "event_status": event_status,
        "created_at": "2026-06-19T00:00:00+00:00",
        "started_at": "2026-06-19T00:00:00+00:00",
        "ended_at": "2026-06-19T00:00:05+00:00",
        "duration_ms": 5000 if event_type == "would_play" else 0,
        "playback_allowed": True if event_type == "would_play" else False,
        "session_action": "play" if event_type == "would_play" else "stop",
        "session_reason": "ready" if event_type == "would_play" else "safety_blocked",
        "selected_order": selected_order,
        "selected_content_type": "image/png",
        "safety_state": safety_state,
        "result": event_type,
    }


def _write_jsonl(root, lines):
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    with open(path, "w") as f:
        for rec in lines:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


# ══════════════════════════════════════════════════════════════════════


class TestPopPickupScanHelp(unittest.TestCase):
    def test_help_lists_command(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("pop-pickup-scan", out)

    def test_pop_pickup_scan_help(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--root", out)


class TestPopPickupScanEmpty(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_missing_file_exit_0(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertEqual(rc, 0, f"Missing file should exit 0, got {rc}. err={err}")
        self.assertIn("scan_status: ok", out)
        self.assertIn("total_lines: 0", out)
        self.assertIn("draft_events: 0", out)
        self.assertIn("eligible_events: 0", out)


class TestPopPickupScanDraft(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [_make_record("draft")])

    def test_draft_exit_0(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertEqual(rc, 0, f"Draft events should exit 0. err={err}")
        self.assertIn("scan_status: ok", out)
        self.assertIn("draft_events: 1", out)
        self.assertIn("eligible_events: 0", out)
        self.assertIn("backend_eligible_events: 0", out)

    def test_draft_no_backend_eligible(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertIn("backend_eligible_events: 0", out)


class TestPopPickupScanBlocked(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [_make_record("blocked", event_type="blocked")])

    def test_blocked_exit_0(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertEqual(rc, 0)
        self.assertIn("diagnostic_events: 1", out)


class TestPopPickupScanFailed(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [_make_record("failed", event_type="error")])

    def test_failed_exit_0(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertEqual(rc, 0)
        self.assertIn("diagnostic_events: 1", out)


class TestPopPickupScanInvalid(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_invalid_json_exit_1(self):
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True)
        (pending_dir / POP_JSONL_FILE).write_text("not json\n")
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertEqual(rc, 1, f"Invalid JSON should exit 1, got {rc}")
        self.assertIn("invalid_lines: 1", out)
        self.assertIn("scan_status: error", out)

    def test_forbidden_key_exit_1(self):
        rec = _make_record("draft")
        rec["token"] = "abc"
        _write_jsonl(self.root, [rec])
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("invalid_lines: 1", out)
        self.assertIn("scan_status: error", out)


class TestPopPickupScanSecurity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [
            _make_record("draft"),
            _make_record("blocked", event_type="blocked"),
        ])

    def test_no_raw_json(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertNotIn('"event_type"', out)
        self.assertNotIn('"event_status"', out)

    def test_no_filename(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertNotIn("filename", (out + err).lower())

    def test_no_manifest_item_id(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertNotIn("manifest_item_id", (out + err).lower())

    def test_no_sha256(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertNotIn("sha256", (out + err).lower())

    def test_no_absolute_paths(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertNotIn(str(self.root), out + err)

    def test_no_forbidden(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        combined = (out + err).lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, combined,
                f"stdout/err contains forbidden '{fb}'")

    def test_no_stacktrace(self):
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertNotIn("Traceback", out + err)


class TestPopPickupScanNoIO(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_does_not_create_sent_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "sent").exists())

    def test_does_not_create_quarantine_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "quarantine").exists())

    def test_does_not_create_dry_run_dir(self):
        _write_jsonl(self.root, [_make_record("draft")])
        _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "dry_run").exists())

    def test_does_not_delete_pending(self):
        _write_jsonl(self.root, [_make_record("draft")])
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertTrue(jsonl_path.exists(), "CLI must NOT delete pending file")

    def test_no_http(self):
        _write_jsonl(self.root, [_make_record("draft")])
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertEqual(rc, 0)

    def test_no_secret_config_token(self):
        _write_jsonl(self.root, [_make_record("draft")])
        out, err, rc = _run_cli("pop-pickup-scan", "--root", str(self.root))
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
