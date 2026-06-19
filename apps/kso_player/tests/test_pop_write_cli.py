"""Tests for kso_player.cli pop-write — event draft + local JSONL write."""

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
POP_JSONL = "pop/pending/player_events.jsonl"

FORBIDDEN = {
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data", "card_number", "pan",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
    "customer_id", "phone", "email", "receipt_number", "fiscal_data",
}

PKG_DIR = Path(__file__).resolve().parent.parent


def _run_cli(*args):
    cmd = [sys.executable, "-m", "kso_player.cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PKG_DIR))
    return proc.stdout, proc.stderr, proc.returncode


def _setup_ready(root):
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


def _read_jsonl(root):
    path = root / POP_JSONL
    if not path.exists():
        return []
    lines = path.read_text().strip().split("\n")
    if lines == [""]:
        return []
    return [_json.loads(line) for line in lines]


# ══════════════════════════════════════════════════════════════════════

class TestPopWriteHelp(unittest.TestCase):
    def test_help_lists_command(self):
        out, err, rc = _run_cli("--help")
        self.assertEqual(rc, 0)
        self.assertIn("pop-write", out)

    def test_pop_write_help(self):
        out, err, rc = _run_cli("pop-write", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("--root", out)
        self.assertIn("--state", out)


class TestPopWriteHappy(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_idle_would_play_writes(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertEqual(rc, 0, f"Expected exit 0, got {rc}. err={err}")
        self.assertIn("pop_write_status: written", out)
        self.assertIn("pop_write_reason: written", out)
        self.assertIn("event_type: would_play", out)
        self.assertIn("line_size_bytes:", out)

    def test_idle_jsonl_contains_would_play(self):
        _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        records = _read_jsonl(self.root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event_type"], "would_play")
        self.assertEqual(records[0]["safety_state"], "idle")
        self.assertEqual(records[0]["result"], "would_play")
        self.assertTrue(records[0]["playback_allowed"])

    def test_no_sleep(self):
        t0 = time.time()
        _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertLess(time.time() - t0, 2.0, "pop-write should not sleep")


class TestPopWriteBlocked(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_payment_blocked_writes(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "payment")
        self.assertEqual(rc, 0, f"Blocked events should still write (exit 0). err={err}")
        self.assertIn("pop_write_status: written", out)
        self.assertIn("event_type: blocked", out)

    def test_payment_jsonl_contains_blocked(self):
        _run_cli("pop-write", "--root", str(self.root), "--state", "payment")
        records = _read_jsonl(self.root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event_type"], "blocked")
        self.assertEqual(records[0]["safety_state"], "payment")

    def test_all_blocked_states_write(self):
        for state in ["transaction", "service", "error", "maintenance", "offline", "unknown"]:
            tmp = Path(tempfile.mkdtemp())
            try:
                _setup_ready(tmp)
                out, err, rc = _run_cli("pop-write", "--root", str(tmp), "--state", state)
                self.assertEqual(rc, 0, f"State '{state}': expected exit 0, got {rc}. err={err}")
                self.assertIn("pop_write_status: written", out)
                records = _read_jsonl(tmp)
                self.assertEqual(records[0]["safety_state"], state)
            finally:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)


class TestPopWriteNotReady(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_manifest_missing_writes(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertEqual(rc, 0, f"not_ready should still write. err={err}")
        self.assertIn("pop_write_status: written", out)
        self.assertIn("event_type:", out)

    def test_manifest_missing_jsonl(self):
        _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        records = _read_jsonl(self.root)
        self.assertEqual(len(records), 1)
        self.assertIn(records[0]["event_type"], {"blocked", "not_ready", "error"})


class TestPopWriteSecondAppend(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_second_run_appends(self):
        _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        _run_cli("pop-write", "--root", str(self.root), "--state", "payment")
        records = _read_jsonl(self.root)
        self.assertEqual(len(records), 2, f"Expected 2 lines, got {len(records)}")
        self.assertEqual(records[0]["event_type"], "would_play")
        self.assertEqual(records[1]["event_type"], "blocked")


class TestPopWriteArgs(unittest.TestCase):
    def test_missing_root(self):
        out, err, rc = _run_cli("pop-write", "--state", "idle")
        self.assertEqual(rc, 2, f"Expected exit 2, got {rc}")

    def test_missing_state(self):
        out, err, rc = _run_cli("pop-write", "--root", "/tmp/xyz")
        self.assertEqual(rc, 2, f"Expected exit 2, got {rc}")

    def test_invalid_state(self):
        out, err, rc = _run_cli("pop-write", "--root", "/tmp/xyz", "--state", "watching_tv")
        self.assertEqual(rc, 2, f"Expected exit 2, got {rc}")

    def test_invalid_state_no_file_created(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            out, err, rc = _run_cli("pop-write", "--root", str(tmp), "--state", "bogus")
            self.assertEqual(rc, 2)
            self.assertFalse((tmp / POP_JSONL).exists(),
                "Invalid state should not create JSONL file")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestPopWriteSecurity(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_stdout_no_filename(self):
        # Test multiple states
        for state in ["idle", "payment"]:
            out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", state)
            self.assertNotIn("item.png", out + err)
            self.assertNotIn("filename", (out + err).lower())

    def test_stdout_no_manifest_item_id(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertNotIn(MID1, out + err)

    def test_stdout_no_sha256(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertNotIn(PNG_SHA[:16], out + err)

    def test_stdout_no_absolute_paths(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertNotIn(str(self.root), out + err)

    def test_stdout_no_forbidden(self):
        for state in ["idle", "payment"]:
            out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", state)
            combined = (out + err).lower()
            for fb in FORBIDDEN:
                self.assertNotIn(fb, combined,
                    f"stdout/err for state='{state}' contains forbidden '{fb}'")

    def test_stdout_no_full_manifest(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertNotIn(MVID, out + err)

    def test_stdout_no_media_bytes(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertNotIn("PNG", out + err)

    def test_stdout_no_stacktrace(self):
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertNotIn("Traceback", out + err)

    def test_jsonl_no_forbidden(self):
        """JSONL file must not contain any forbidden substrings."""
        _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        _run_cli("pop-write", "--root", str(self.root), "--state", "payment")
        content = (self.root / POP_JSONL).read_text().lower()
        for fb in FORBIDDEN:
            self.assertNotIn(fb, content,
                f"JSONL contains forbidden '{fb}'")

    def test_jsonl_no_filename_or_id(self):
        _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        content = (self.root / POP_JSONL).read_text().lower()
        self.assertNotIn("filename", content)
        self.assertNotIn("manifest_item_id", content)
        self.assertNotIn("sha256", content)

    def test_jsonl_parseable_line_ends_newline(self):
        _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        content = (self.root / POP_JSONL).read_text()
        self.assertTrue(content.endswith("\n"), "JSONL must end with newline")
        lines = content.strip().split("\n")
        self.assertEqual(len(lines), 1)
        parsed = _json.loads(lines[0])
        self.assertIsInstance(parsed, dict)


class TestPopWriteNoIO(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        _setup_ready(self.root)

    def test_no_http(self):
        """CLI should not make HTTP calls — works offline."""
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertEqual(rc, 0)

    def test_no_secret_config_token(self):
        """CLI works without config/secret/token files."""
        tmp = Path(tempfile.mkdtemp())
        try:
            _setup_ready(tmp)
            out, err, rc = _run_cli("pop-write", "--root", str(tmp), "--state", "payment")
            self.assertEqual(rc, 0)
            self.assertIn("pop_write_status: written", out)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_sent_quarantine_rotation(self):
        """CLI only writes to pop/pending/, never creates sent/ or quarantine/."""
        out, err, rc = _run_cli("pop-write", "--root", str(self.root), "--state", "idle")
        self.assertEqual(rc, 0)
        self.assertFalse((self.root / "pop" / "sent").exists(),
            "pop/sent/ should NOT be created — sidecar responsibility")
        self.assertFalse((self.root / "pop" / "quarantine").exists(),
            "pop/quarantine/ should NOT be created — sidecar responsibility")

    def test_no_backend_send(self):
        """CLI must not import or use backend/sidecar modules."""
        import kso_player.cli as cli_mod
        source = open(cli_mod.__file__).read()
        self.assertNotIn("from backend", source)
        self.assertNotIn("import backend", source)


if __name__ == "__main__":
    unittest.main()
