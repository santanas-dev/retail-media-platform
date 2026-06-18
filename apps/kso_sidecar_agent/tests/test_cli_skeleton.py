"""Smoke tests for KSO Sidecar Agent skeleton."""

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
        self.assertIn("init-local-root", out)
        self.assertIn("doctor", out)
        self.assertIn("version", out)

    # ── version ────────────────────────────────────────────────────
    def test_version(self):
        code, out, err = run("version")
        self.assertEqual(code, 0)
        self.assertIn("0.1.0", out)

    # ── init-local-root ────────────────────────────────────────────
    def test_init_creates_folders(self):
        code, out, err = run("init-local-root", "--root", self.root)
        self.assertEqual(code, 0)

        expected = [
            "config", "manifest",
            "media/current", "media/staging", "media/quarantine",
            "pop", "status", "logs",
        ]
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

    # ── doctor ─────────────────────────────────────────────────────
    def test_doctor_ok(self):
        run("init-local-root", "--root", self.root)
        code, out, err = run("doctor", "--root", self.root)
        self.assertEqual(code, 0, f"out={out}\nerr={err}")
        self.assertIn("All checks passed", out)

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

    # ── no secrets in runtime files ────────────────────────────────
    def test_no_forbidden_in_agent_status(self):
        run("init-local-root", "--root", self.root)
        status_path = Path(self.root) / "status" / "agent_status.json"
        content = status_path.read_text().lower()
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, content,
                             f"'{word}' found in agent_status.json")

    def test_no_forbidden_in_cli_output(self):
        run("init-local-root", "--root", self.root)
        code, out, err = run("doctor", "--root", self.root)
        combined = (out + err).lower()
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, combined,
                             f"'{word}' found in CLI output")


if __name__ == "__main__":
    unittest.main()
