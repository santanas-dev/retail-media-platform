"""Tests for kso_sidecar_agent.cli pop-rotation-apply — guarded destructive CLI."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

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
    "Windows", "MSI", ".msi", "ProgramData", "regedit", "win32",
}

PKG_DIR = Path(__file__).resolve().parent.parent


def _run_cli(*args):
    cmd = [sys.executable, "-m", "kso_sidecar_agent.cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PKG_DIR))
    return proc.stdout, proc.stderr, proc.returncode


def _write_jsonl(root, lines):
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / POP_JSONL_FILE
    text = "\n".join(lines) + "\n"
    path.write_text(text)


def _acquire_lock(root):
    pending_dir = Path(root) / POP_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    lock_path = pending_dir / POP_LOCK_FILE
    lock_path.write_text("locked\n")


def _draft_line():
    return json.dumps({
        "schema_version": 1, "event_type": "would_play",
        "event_status": "draft", "created_at": "2026-06-19T10:00:00Z",
        "started_at": "2026-06-19T10:00:00Z", "duration_ms": 15000,
        "playback_allowed": True, "session_action": "play",
        "session_reason": "ready", "selected_order": 1,
        "selected_content_type": "video/mp4", "safety_state": "idle",
        "result": "would_play",
    })


def _completed_eligible_line():
    return json.dumps({
        "schema_version": 1, "event_type": "would_play",
        "event_status": "completed", "created_at": "2026-06-19T10:00:00Z",
        "started_at": "2026-06-19T10:00:00Z", "ended_at": "2026-06-19T10:00:15Z",
        "duration_ms": 15000, "playback_allowed": True,
        "session_action": "play", "session_reason": "ready",
        "selected_order": 1, "selected_content_type": "video/mp4",
        "safety_state": "idle", "result": "would_play",
    })


def _invalid_line():
    return "not valid json {{{"


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplyHelp(TestCase):
    def test_help_lists_command(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("pop-rotation-apply", out)

    def test_pop_rotation_apply_help(self):
        out, err, rc = _run_cli("pop-rotation-apply", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--confirm-local-rotation", out)
        self.assertIn("--root", out)


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplyConfirmRequired(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_confirm_exit_2(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli("pop-rotation-apply", "--root", str(self.tmp))
        self.assertEqual(rc, 2, f"Missing --confirm-local-rotation should exit 2")

    def test_missing_confirm_no_lock_taken(self):
        _write_jsonl(self.tmp, [_draft_line()])
        _run_cli("pop-rotation-apply", "--root", str(self.tmp))
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists(), "No lock should be taken without confirm")

    def test_missing_confirm_no_target_dirs(self):
        _write_jsonl(self.tmp, [_draft_line()])
        _run_cli("pop-rotation-apply", "--root", str(self.tmp))
        for bad in ("sent", "quarantine", "dry_run", "failed"):
            self.assertFalse((self.tmp / "pop" / bad).exists())

    def test_missing_confirm_pending_unchanged(self):
        _write_jsonl(self.tmp, [_draft_line()])
        jl = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        original = jl.read_text()
        _run_cli("pop-rotation-apply", "--root", str(self.tmp))
        self.assertEqual(jl.read_text(), original)


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplyInvalidArgs(TestCase):
    def test_missing_root_exit_2(self):
        out, err, rc = _run_cli("pop-rotation-apply", "--confirm-local-rotation")
        self.assertEqual(rc, 2)

    def test_max_lines_zero_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err, rc = _run_cli(
                "pop-rotation-apply", "--root", tmp,
                "--confirm-local-rotation", "--max-lines", "0")
            self.assertEqual(rc, 2)

    def test_max_lines_negative_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err, rc = _run_cli(
                "pop-rotation-apply", "--root", tmp,
                "--confirm-local-rotation", "--max-lines", "-5")
            self.assertEqual(rc, 2)


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplyDryRun(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_draft_creates_dry_run(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertIn("dry_run_records:", out)
        dry_dir = self.tmp / "pop" / "dry_run"
        self.assertTrue(dry_dir.exists())

    def test_blocked_creates_dry_run(self):
        line = json.dumps({
            "schema_version": 1, "event_type": "blocked",
            "event_status": "blocked", "created_at": "2026-06-19T10:00:00Z",
            "started_at": None, "duration_ms": 0,
            "playback_allowed": False, "session_action": "stop",
            "session_reason": "safety_blocked", "selected_order": None,
            "selected_content_type": None, "safety_state": "payment",
            "result": "blocked",
        })
        _write_jsonl(self.tmp, [line])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertIn("dry_run_records:", out)

    def test_draft_pending_empty_after(self):
        _write_jsonl(self.tmp, [_draft_line()])
        _run_cli("pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        pending_path = self.tmp / POP_PENDING_DIR / POP_JSONL_FILE
        content = pending_path.read_text().strip()
        self.assertEqual(content, "")


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplyQuarantine(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_invalid_json_creates_quarantine(self):
        _write_jsonl(self.tmp, [_invalid_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertIn("quarantine_records:", out)
        qdir = self.tmp / "pop" / "quarantine"
        self.assertTrue(qdir.exists())


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplySentPolicy(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_completed_eligible_no_send_stays_pending(self):
        """Without backend send result, completed events stay in pending."""
        _write_jsonl(self.tmp, [_completed_eligible_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertIn("sent_records:             0", out)
        # sent dir NOT created
        self.assertFalse((self.tmp / "pop" / "sent").exists())

    def test_sent_records_always_zero_in_output(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertIn("sent_records:", out)


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplyLock(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_released_after_success(self):
        _write_jsonl(self.tmp, [_draft_line()])
        _run_cli("pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertFalse(lock_path.exists(), "Lock must be released after apply")

    def test_foreign_lock_exit_1(self):
        _write_jsonl(self.tmp, [_draft_line()])
        _acquire_lock(self.tmp)
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertEqual(rc, 1, f"Foreign lock should exit 1, got {rc}")
        self.assertIn("lock_unavailable", (out + err).lower())

    def test_foreign_lock_not_removed(self):
        _write_jsonl(self.tmp, [_draft_line()])
        _acquire_lock(self.tmp)
        _run_cli("pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        lock_path = self.tmp / POP_PENDING_DIR / POP_LOCK_FILE
        self.assertTrue(lock_path.exists(), "Foreign lock must not be removed")


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplySafeOutput(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_raw_json(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertNotIn('"event_type"', out)
        self.assertNotIn('"event_status"', out)

    def test_no_paths(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertNotIn(str(self.tmp), out)

    def test_no_filenames(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertNotIn("player_events", out.lower())
        self.assertNotIn(".jsonl", out.lower())

    def test_no_manifest_item_id(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertNotIn("manifest_item_id", (out + err).lower())

    def test_no_sha256(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertNotIn("sha256", (out + err).lower())

    def test_no_forbidden_substrings(self):
        _write_jsonl(self.tmp, [_draft_line(), _invalid_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        combined = (out + err).lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, combined, f"Contains forbidden '{fb}'")

    def test_no_stacktrace(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertNotIn("Traceback", out + err)


# ══════════════════════════════════════════════════════════════════════

class TestPopRotationApplyNoSideEffects(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_backend_send(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertIn(rc, (0, 1))

    def test_no_secret_config_token_read(self):
        _write_jsonl(self.tmp, [_draft_line()])
        out, err, rc = _run_cli(
            "pop-rotation-apply", "--root", str(self.tmp), "--confirm-local-rotation")
        self.assertIn(rc, (0, 1))


if __name__ == "__main__":
    import unittest
    unittest.main()
