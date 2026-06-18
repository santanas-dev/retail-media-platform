"""Smoke tests for KSO Sidecar Agent skeleton + atomic status store + local config."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent


def run(*args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR),
    )
    return r.returncode, r.stdout, r.stderr


FORBIDDEN_WORDS = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
]

FORBIDDEN_EXTENDED = FORBIDDEN_WORDS + ["local_path", "file_path"]


# ══════════════════════════════════════════════════════════════════════

class TestCLISkeleton(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    # ── help ───────────────────────────────────────────────────────
    def test_help(self):
        code, out, err = run("--help")
        self.assertEqual(code, 0, f"err={err}")
        for cmd in ("init-local-root", "doctor", "version", "set-status",
                     "write-config", "config-status"):
            self.assertIn(cmd, out, f"Missing command: {cmd}")

    # ── version ────────────────────────────────────────────────────
    def test_version(self):
        code, out, err = run("version")
        self.assertEqual(code, 0)
        self.assertIn("0.1.0", out)

    # ── init-local-root ────────────────────────────────────────────
    def test_init_creates_folders(self):
        code, out, err = run("init-local-root", "--root", self.root)
        self.assertEqual(code, 0)
        expected = ["config", "manifest", "media/current", "media/staging",
                     "media/quarantine", "pop", "status", "logs"]
        for folder in expected:
            path = Path(self.root) / folder
            self.assertTrue(path.is_dir(), f"Missing folder: {folder}")

    def test_init_creates_agent_status(self):
        code, out, err = run("init-local-root", "--root", self.root)
        self.assertEqual(code, 0)
        status_path = Path(self.root) / "status" / "agent_status.json"
        self.assertTrue(status_path.exists())
        data = json.loads(status_path.read_text())
        self.assertEqual(data["status"], "stopped")
        self.assertEqual(data["cached_items"], 0)
        self.assertEqual(data["errors"], [])

    # ── doctor (now checks config too) ─────────────────────────────
    def test_doctor_no_init(self):
        code, out, err = run("doctor", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("Issues found", out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Traceback", err)

    def test_doctor_no_stacktrace(self):
        code, out, err = run("doctor", "--root", "/nonexistent/path/xyz")
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Traceback", err)

    # ── safe logger ────────────────────────────────────────────────
    def test_safe_logger_redact_forbidden(self):
        from kso_sidecar_agent.safe_logger import log
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            log(level="info", event="test", message="api_key found in config")
            log(level="info", event="test", message="token expired")
            log(level="info", event="test", message="all good")
        finally:
            sys.stdout = old_stdout
        lines = [l for l in buf.getvalue().split("\n") if l.strip()]
        self.assertEqual(len(lines), 3)
        for line in lines:
            rec = json.loads(line)
            msg = rec["message"].lower()
            if "good" in msg:
                self.assertNotIn("[REDACTED]", rec["message"])
            else:
                self.assertEqual("[REDACTED]", rec["message"])

    # ── no secrets ─────────────────────────────────────────────────
    def test_no_forbidden_in_agent_status(self):
        run("init-local-root", "--root", self.root)
        status_path = Path(self.root) / "status" / "agent_status.json"
        content = status_path.read_text().lower()
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, content, f"'{word}' in agent_status.json")

    def test_no_forbidden_in_cli_output(self):
        run("init-local-root", "--root", self.root)
        # write-config needs to succeed for doctor to be OK
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com",
            "--device-code", "a-05954")
        code, out, err = run("doctor", "--root", self.root)
        combined = (out + err).lower()
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, combined, f"'{word}' in CLI output")


# ══════════════════════════════════════════════════════════════════════

class TestAtomicStatusStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init-local-root", "--root", self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_status_running(self):
        code, out, err = run("set-status", "--root", self.root, "--status", "running")
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("running", out)
        data = json.loads((Path(self.root) / "status" / "agent_status.json").read_text())
        self.assertEqual(data["status"], "running")

    def test_set_status_offline_full(self):
        code, out, err = run(
            "set-status", "--root", self.root, "--status", "offline",
            "--offline-mode", "true", "--cached-items", "3",
            "--invalid-hash-items", "1", "--error", "backend unavailable",
        )
        self.assertEqual(code, 0, f"err={err}")
        data = json.loads((Path(self.root) / "status" / "agent_status.json").read_text())
        self.assertEqual(data["status"], "offline")
        self.assertTrue(data["offline_mode"])
        self.assertEqual(data["cached_items"], 3)
        self.assertEqual(data["invalid_hash_items"], 1)
        self.assertEqual(data["errors"], ["backend unavailable"])

    def test_invalid_status_rejected(self):
        code, out, err = run("set-status", "--root", self.root, "--status", "INVALID")
        self.assertNotEqual(code, 0)
        self.assertIn("ERROR", err)

    def test_negative_cached_items_rejected(self):
        code, out, err = run("set-status", "--root", self.root,
                             "--status", "running", "--cached-items", "-1")
        self.assertNotEqual(code, 0)

    def test_forbidden_error_rejected(self):
        code, out, err = run("set-status", "--root", self.root,
                             "--status", "running", "--error", "token expired")
        self.assertNotEqual(code, 0)
        self.assertIn("ERROR", err)

    def test_symlink_target_rejected(self):
        status_path = Path(self.root) / "status" / "agent_status.json"
        status_path.unlink()
        outside = Path(self.root) / "outside.json"
        outside.write_text("{}")
        status_path.symlink_to(outside)
        code, out, err = run("set-status", "--root", self.root, "--status", "running")
        self.assertNotEqual(code, 0)

    def test_doctor_validates_status(self):
        run("set-status", "--root", self.root, "--status", "warning")
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com",
            "--device-code", "a-05954")
        code, out, err = run("doctor", "--root", self.root)
        self.assertIn("warning", out)

    def test_doctor_catches_broken_json(self):
        (Path(self.root) / "status" / "agent_status.json").write_text("{not json")
        code, out, err = run("doctor", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("Invalid JSON", out)

    def test_doctor_catches_forbidden_value(self):
        (Path(self.root) / "status" / "agent_status.json").write_text(json.dumps({
            "status": "running", "updated_at": "2026-01-01T00:00:00Z",
            "offline_mode": False, "cached_items": 0,
            "invalid_hash_items": 0, "errors": ["token found"],
        }))
        code, out, err = run("doctor", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("Forbidden", out)

    def test_no_tmp_left_after_write(self):
        run("set-status", "--root", self.root, "--status", "running")
        tmp_files = list((Path(self.root) / "status").glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0, f"Found tmp: {tmp_files}")

    def test_no_forbidden_after_set_status(self):
        run("set-status", "--root", self.root, "--status", "running")
        content = (Path(self.root) / "status" / "agent_status.json").read_text().lower()
        for word in FORBIDDEN_EXTENDED:
            self.assertNotIn(word, content, f"'{word}' after set-status")


# ══════════════════════════════════════════════════════════════════════

class TestLocalConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init-local-root", "--root", self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # ── happy path ─────────────────────────────────────────────────
    def test_write_config_creates_file(self):
        code, out, err = run("write-config", "--root", self.root,
                             "--backend-base-url", "https://example.com",
                             "--device-code", "a-05954")
        self.assertEqual(code, 0, f"err={err}")
        config_path = Path(self.root) / "config" / "agent_config.json"
        self.assertTrue(config_path.exists())
        data = json.loads(config_path.read_text())
        self.assertEqual(data["backend_base_url"], "https://example.com")
        self.assertEqual(data["device_code"], "a-05954")
        self.assertTrue(data["tls_verify"])
        self.assertEqual(data["request_timeout_sec"], 10)

    def test_config_status_valid(self):
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com",
            "--device-code", "a-05954")
        code, out, err = run("config-status", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("PRESENT", out)
        self.assertIn("example.com", out)
        self.assertIn("a-05954", out)

    # ── errors ─────────────────────────────────────────────────────
    def test_write_config_no_init(self):
        r2 = tempfile.TemporaryDirectory()
        code, out, err = run("write-config", "--root", r2.name,
                             "--backend-base-url", "https://example.com",
                             "--device-code", "a-05954")
        self.assertNotEqual(code, 0)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Traceback", err)
        r2.cleanup()

    def test_invalid_backend_url_rejected(self):
        for bad_url in ("ftp://example.com", "not-a-url", ""):
            code, out, err = run("write-config", "--root", self.root,
                                 "--backend-base-url", bad_url,
                                 "--device-code", "a-05954")
            self.assertNotEqual(code, 0, f"Should reject: {bad_url}")

    def test_url_with_password_rejected(self):
        code, out, err = run("write-config", "--root", self.root,
                             "--backend-base-url", "https://user:pass@example.com",
                             "--device-code", "a-05954")
        self.assertNotEqual(code, 0)

    def test_url_with_token_query_rejected(self):
        code, out, err = run("write-config", "--root", self.root,
                             "--backend-base-url", "https://example.com?token=abc123",
                             "--device-code", "a-05954")
        self.assertNotEqual(code, 0)

    def test_invalid_device_code_rejected(self):
        for bad in ("ab", "a b", "a@b", ""):
            code, out, err = run("write-config", "--root", self.root,
                                 "--backend-base-url", "https://example.com",
                                 "--device-code", bad)
            self.assertNotEqual(code, 0, f"Should reject device_code: {bad}")

    def test_tls_verify_false_works(self):
        code, out, err = run("write-config", "--root", self.root,
                             "--backend-base-url", "https://example.com",
                             "--device-code", "a-05954",
                             "--tls-verify", "false")
        self.assertEqual(code, 0, f"err={err}")
        data = json.loads((Path(self.root) / "config" / "agent_config.json").read_text())
        self.assertFalse(data["tls_verify"])

    def test_invalid_timeout_rejected(self):
        for bad in ("0", "121", "-1"):
            code, out, err = run("write-config", "--root", self.root,
                                 "--backend-base-url", "https://example.com",
                                 "--device-code", "a-05954",
                                 "--request-timeout-sec", bad)
            self.assertNotEqual(code, 0, f"Should reject timeout: {bad}")

    def test_forbidden_in_device_code_rejected(self):
        code, out, err = run("write-config", "--root", self.root,
                             "--backend-base-url", "https://example.com",
                             "--device-code", "my_token")
        self.assertNotEqual(code, 0)

    def test_forbidden_in_url_rejected(self):
        code, out, err = run("write-config", "--root", self.root,
                             "--backend-base-url", "https://my-secret.example.com",
                             "--device-code", "a-05954")
        self.assertNotEqual(code, 0)

    # ── doctor integration ─────────────────────────────────────────
    def test_doctor_without_config_warns(self):
        run("set-status", "--root", self.root, "--status", "running")
        code, out, err = run("doctor", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("config_ok:", out)
        self.assertIn("config_ok:         False", out, f"out={out}")

    def test_doctor_with_valid_config_ok(self):
        run("set-status", "--root", self.root, "--status", "running")
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com",
            "--device-code", "a-05954")
        code, out, err = run("doctor", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("All checks passed", out)

    def test_doctor_with_invalid_config_issue(self):
        run("set-status", "--root", self.root, "--status", "running")
        # Write invalid config directly
        bad_config = {"backend_base_url": "ftp://bad", "device_code": "x"}
        config_dir = Path(self.root) / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "agent_config.json").write_text(json.dumps(bad_config))
        code, out, err = run("doctor", "--root", self.root)
        self.assertNotEqual(code, 0)

    # ── security ───────────────────────────────────────────────────
    def test_config_file_no_forbidden_words(self):
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com",
            "--device-code", "a-05954")
        content = (Path(self.root) / "config" / "agent_config.json").read_text().lower()
        for word in FORBIDDEN_EXTENDED:
            self.assertNotIn(word, content, f"'{word}' in agent_config.json")

    def test_output_no_forbidden_words(self):
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com",
            "--device-code", "a-05954")
        code, out, err = run("config-status", "--root", self.root)
        combined = (out + err).lower()
        for word in FORBIDDEN_EXTENDED:
            self.assertNotIn(word, combined, f"'{word}' in config-status output")


if __name__ == "__main__":
    unittest.main()
