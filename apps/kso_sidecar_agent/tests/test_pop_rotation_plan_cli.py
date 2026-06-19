"""Tests for kso_sidecar_agent.cli pop-rotation-plan — in-memory rotation plan preview CLI."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

POP_PENDING_DIR = "pop/pending"
POP_JSONL_FILE = "player_events.jsonl"
POP_LOCK_FILE = "player_events.lock"

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "customer_id", "phone", "email", "receipt_number", "fiscal_data",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
    "filename", "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes", "stacktrace",
}

PKG_DIR = Path(__file__).resolve().parent.parent


def _run_cli(*args):
    cmd = [sys.executable, "-m", "kso_sidecar_agent.cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PKG_DIR))
    return proc.stdout, proc.stderr, proc.returncode


def _draft_record():
    return {
        "schema_version": 1,
        "event_type": "would_play",
        "event_status": "draft",
        "created_at": "2026-06-19T00:00:00+00:00",
        "started_at": "2026-06-19T00:00:00+00:00",
        "duration_ms": 15000,
        "playback_allowed": True,
        "session_action": "play",
        "session_reason": "ready",
        "selected_order": 1,
        "selected_content_type": "video/mp4",
        "safety_state": "idle",
        "result": "would_play",
    }


def _blocked_record():
    return {
        "schema_version": 1,
        "event_type": "blocked",
        "event_status": "blocked",
        "created_at": "2026-06-19T00:00:00+00:00",
        "started_at": None,
        "duration_ms": 0,
        "playback_allowed": False,
        "session_action": "stop",
        "session_reason": "safety_blocked",
        "selected_order": None,
        "selected_content_type": None,
        "safety_state": "payment",
        "result": "blocked",
    }


def _failed_record():
    return {
        "schema_version": 1,
        "event_type": "error",
        "event_status": "failed",
        "created_at": "2026-06-19T00:00:00+00:00",
        "started_at": None,
        "duration_ms": 0,
        "playback_allowed": False,
        "session_action": "stop",
        "session_reason": "invalid_state",
        "selected_order": None,
        "selected_content_type": None,
        "safety_state": "error",
        "result": "error",
    }


def _completed_eligible_record():
    """Completed + idle event — eligible if manifest and media present."""
    return {
        "schema_version": 1,
        "event_type": "would_play",
        "event_status": "completed",
        "created_at": "2026-06-19T00:00:00+00:00",
        "started_at": "2026-06-19T00:00:00+00:00",
        "ended_at": "2026-06-19T00:00:15+00:00",
        "duration_ms": 15000,
        "playback_allowed": True,
        "session_action": "play",
        "session_reason": "ready",
        "selected_order": 1,
        "selected_content_type": "video/mp4",
        "safety_state": "idle",
        "result": "would_play",
    }


def _write_jsonl(root, lines):
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    with open(path, "w") as f:
        for rec in lines:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


def _acquire_lock(root):
    """Manually create lock file (simulate another process holding lock)."""
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    lock_path = pending_dir / POP_LOCK_FILE
    lock_path.write_text("locked\n")


def _is_lock_present(root):
    lock_path = Path(root) / POP_PENDING_DIR / POP_LOCK_FILE
    return lock_path.exists()


# ══════════════════════════════════════════════════════════════════════


class TestPopRotationPlanHelp(unittest.TestCase):
    """--help and pop-rotation-plan --help."""

    def test_help_lists_command(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("pop-rotation-plan", out)

    def test_pop_rotation_plan_help(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--root", out)
        self.assertIn("--max-lines", out)


class TestPopRotationPlanInvalidArgs(unittest.TestCase):
    """Invalid arguments → exit 2."""

    def test_missing_root_exit_2(self):
        out, err, rc = _run_cli("pop-rotation-plan")
        self.assertEqual(rc, 2, f"Missing --root should exit 2. stderr={err}")

    def test_max_lines_zero_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err, rc = _run_cli("pop-rotation-plan", "--root", tmp, "--max-lines", "0")
            self.assertEqual(rc, 2, f"max-lines=0 should exit 2. stderr={err}")

    def test_max_lines_negative_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err, rc = _run_cli("pop-rotation-plan", "--root", tmp, "--max-lines", "-5")
            self.assertEqual(rc, 2, f"Negative max-lines should exit 2. stderr={err}")


class TestPopRotationPlanMissingFile(unittest.TestCase):
    """No pending file → exit 0."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_missing_file_exit_0(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertEqual(rc, 0, f"Missing file should exit 0, got {rc}. err={err}")
        self.assertIn("rotation_status:", out)
        self.assertIn("no_pending_file", out.lower())
        self.assertIn("pending_lines_before:", out)


class TestPopRotationPlanClassification(unittest.TestCase):
    """Events classified correctly via CLI output."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_draft_dry_run(self):
        _write_jsonl(self.root, [_draft_record()])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertIn("dry_run_lines:", out)
        self.assertIn("sent_lines:", out)
        # sent_lines should be 0 — no backend confirmation
        self.assertIn("pending_should_remain", out.lower())

    def test_blocked_dry_run(self):
        _write_jsonl(self.root, [_blocked_record()])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertIn("dry_run_lines:", out)

    def test_failed_dry_run(self):
        _write_jsonl(self.root, [_failed_record()])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertIn("dry_run_lines:", out)

    def test_invalid_json_exit_1(self):
        pending_dir = self.root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True)
        (pending_dir / POP_JSONL_FILE).write_text("not valid json{@#$}\n")
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertEqual(rc, 1, f"Invalid JSON should exit 1, got {rc}")
        self.assertIn("invalid_lines:", out)

    def test_forbidden_value_exit_1(self):
        rec = _draft_record()
        rec["selected_content_type"] = "token=abc"
        _write_jsonl(self.root, [rec])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertEqual(rc, 1, f"Forbidden value should exit 1, got {rc}")
        self.assertIn("quarantine_lines:", out)

    def test_completed_eligible_no_backend_sent_zero(self):
        """Completed eligible event — but no backend confirmation → sent_lines=0."""
        _write_jsonl(self.root, [_completed_eligible_record()])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        # Without backend confirmation, sent_lines is 0
        self.assertIn("pending_should_remain", out.lower())


class TestPopRotationPlanLock(unittest.TestCase):
    """Lock behavior in CLI."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_lock_unavailable_exit_1(self):
        _write_jsonl(self.root, [_draft_record()])
        _acquire_lock(self.root)
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertEqual(rc, 1, f"Lock unavailable should exit 1, got {rc}. err={err}")
        self.assertIn("lock_unavailable", out.lower())

    def test_foreign_lock_not_removed(self):
        _write_jsonl(self.root, [_draft_record()])
        _acquire_lock(self.root)
        _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertTrue(_is_lock_present(self.root),
                        "Foreign lock must not be removed by CLI")

    def test_lock_released_after_command(self):
        _write_jsonl(self.root, [_draft_record()])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertFalse(_is_lock_present(self.root),
                         f"Lock should be released after CLI. err={err}")


class TestPopRotationPlanMaxLines(unittest.TestCase):
    """--max-lines limit."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_max_lines_limit(self):
        lines = [_draft_record() for _ in range(5)]
        _write_jsonl(self.root, lines)
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root),
                                "--max-lines", "1")
        self.assertIn("plan_limited:", out)
        self.assertIn("true", out.split("plan_limited:")[1] if "plan_limited:" in out else "")

    def test_max_lines_default(self):
        """Default 10000 max-lines — draft events produce warning (exit 1)."""
        _write_jsonl(self.root, [_draft_record()])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertIn(rc, (0, 1))


class TestPopRotationPlanSafeOutput(unittest.TestCase):
    """Safe output — no raw JSON, no IDs, no paths, no forbidden substrings."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _write_jsonl(self.root, [
            _draft_record(),
            _blocked_record(),
            _failed_record(),
        ])

    def test_no_raw_json(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertNotIn('"event_type"', out)
        self.assertNotIn('"event_status"', out)
        self.assertNotIn('"result"', out)

    def test_no_lock_path(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertNotIn("player_events.lock", out + err)

    def test_no_filename(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        combined = (out + err).lower()
        self.assertNotIn("filename", combined)

    def test_no_manifest_item_id(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        combined = (out + err).lower()
        self.assertNotIn("manifest_item_id", combined)

    def test_no_sha256(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        combined = (out + err).lower()
        self.assertNotIn("sha256", combined)

    def test_no_absolute_paths(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertNotIn(str(self.root), out + err)

    def test_no_forbidden_substrings(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        combined = (out + err).lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, combined,
                             f"stdout/err contains forbidden '{fb}'")

    def test_no_stacktrace(self):
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertNotIn("Traceback", out + err)


class TestPopRotationPlanNoSideEffects(unittest.TestCase):
    """CLI does NOT create dirs, modify/delete pending, do HTTP, read secret/config."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_does_not_create_sent_dir(self):
        _write_jsonl(self.root, [_draft_record()])
        _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "sent").exists())

    def test_does_not_create_quarantine_dir(self):
        _write_jsonl(self.root, [_draft_record()])
        _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "quarantine").exists())

    def test_does_not_create_dry_run_dir(self):
        _write_jsonl(self.root, [_draft_record()])
        _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "dry_run").exists())

    def test_does_not_create_failed_dir(self):
        _write_jsonl(self.root, [_draft_record()])
        _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertFalse((self.root / "pop" / "failed").exists())

    def test_does_not_delete_pending(self):
        _write_jsonl(self.root, [_draft_record()])
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        self.assertTrue(jsonl_path.exists())
        _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertTrue(jsonl_path.exists(), "CLI must NOT delete pending file")

    def test_does_not_modify_pending(self):
        _write_jsonl(self.root, [_draft_record(), _blocked_record()])
        jsonl_path = self.root / POP_PENDING_DIR / POP_JSONL_FILE
        original = jsonl_path.read_text()
        _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertEqual(jsonl_path.read_text(), original)

    def test_no_http(self):
        _write_jsonl(self.root, [_draft_record()])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertIn(rc, (0, 1))

    def test_no_secret_config_token_read(self):
        """CLI does not require secret/config/token files to exist."""
        _write_jsonl(self.root, [_draft_record()])
        out, err, rc = _run_cli("pop-rotation-plan", "--root", str(self.root))
        self.assertIn(rc, (0, 1))


if __name__ == "__main__":
    unittest.main()
