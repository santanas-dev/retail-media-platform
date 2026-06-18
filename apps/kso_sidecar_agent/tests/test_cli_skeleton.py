"""Smoke tests for KSO Sidecar Agent skeleton + atomic status + config + dev secret store."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent

TEST_SECRET = "dev-value-1234567890"


def run(*args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR),
    )
    return r.returncode, r.stdout, r.stderr


def run_stdin(secret, *args):
    r = subprocess.run(
        [sys.executable, "-m", "kso_sidecar_agent.cli", *args],
        capture_output=True, text=True, cwd=str(PKG_DIR), input=secret,
    )
    return r.returncode, r.stdout, r.stderr


FORBIDDEN_WORDS = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
]
FORBIDDEN_EXTENDED = FORBIDDEN_WORDS + ["local_path", "file_path"]

DEV_FLAG = ["--dev-secret-store"]


# ══════════════════════════════════════════════════════════════════════

class TestCLISkeleton(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_help(self):
        code, out, err = run("--help")
        self.assertEqual(code, 0, f"err={err}")
        for cmd in ("init-local-root", "doctor", "version", "set-status",
                     "write-config", "config-status",
                     "secret-store-check", "secret-store-set", "secret-store-delete",
                     "runtime-config-status",
                     "sync-runtime-config",
                     "heartbeat-once",
                     "manifest-status",
                     "auth-check"):
            self.assertIn(cmd, out, f"Missing command: {cmd}")

    def test_version(self):
        code, out, err = run("version")
        self.assertEqual(code, 0)
        self.assertIn("0.1.0", out)

    def test_init_creates_folders(self):
        code, out, err = run("init-local-root", "--root", self.root)
        self.assertEqual(code, 0)
        for folder in ["config", "manifest", "media/current", "media/staging",
                        "media/quarantine", "pop", "status", "logs"]:
            self.assertTrue((Path(self.root) / folder).is_dir(), f"Missing: {folder}")

    def test_init_creates_agent_status(self):
        run("init-local-root", "--root", self.root)
        data = json.loads((Path(self.root) / "status" / "agent_status.json").read_text())
        self.assertEqual(data["status"], "stopped")

    def test_doctor_no_init(self):
        code, out, err = run("doctor", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("Issues found", out)

    def test_doctor_no_stacktrace(self):
        code, out, err = run("doctor", "--root", "/nonexistent/path/xyz")
        self.assertNotIn("Traceback", out)
        self.assertNotIn("Traceback", err)

    def test_safe_logger_redact_forbidden(self):
        from kso_sidecar_agent.safe_logger import log
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            log(level="info", event="t", message="api_key found")
            log(level="info", event="t", message="all good")
        finally:
            sys.stdout = old
        lines = [l for l in buf.getvalue().split("\n") if l.strip()]
        self.assertEqual(len(lines), 2)
        for line in lines:
            rec = json.loads(line)
            if "good" in rec["message"]:
                self.assertNotIn("[REDACTED]", rec["message"])
            else:
                self.assertEqual("[REDACTED]", rec["message"])


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
        self.assertEqual(code, 0)
        data = json.loads((Path(self.root) / "status" / "agent_status.json").read_text())
        self.assertEqual(data["status"], "running")

    def test_doctor_with_config(self):
        run("set-status", "--root", self.root, "--status", "running")
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        code, out, err = run("doctor", "--root", self.root)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("All checks passed", out)


# ══════════════════════════════════════════════════════════════════════

class TestLocalConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init-local-root", "--root", self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_config_creates_file(self):
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        data = json.loads((Path(self.root) / "config" / "agent_config.json").read_text())
        self.assertEqual(data["backend_base_url"], "https://example.com")


# ══════════════════════════════════════════════════════════════════════
# Dev Secret Store tests
# ══════════════════════════════════════════════════════════════════════

class TestDevSecretStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run("init-local-root", "--root", self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # ── Dev mode gate ──────────────────────────────────────────────
    def test_check_without_dev_flag_rejected(self):
        code, out, err = run("secret-store-check", "--root", self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("disabled", err.lower() if err else out.lower())

    def test_set_without_dev_flag_rejected(self):
        code, out, err = run_stdin(TEST_SECRET,
                                   "secret-store-set", "--root", self.root, "--stdin")
        self.assertNotEqual(code, 0)

    def test_delete_without_dev_flag_rejected(self):
        code, out, err = run("secret-store-delete", "--root", self.root)
        self.assertNotEqual(code, 0)

    # ── Happy path ─────────────────────────────────────────────────
    def test_set_via_stdin(self):
        code, out, err = run_stdin(
            TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin",
        )
        self.assertEqual(code, 0, f"err={err}")
        self.assertTrue((Path(self.root) / "config" / "device_secret.dev").exists())

    def test_check_after_set(self):
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        code, out, err = run("secret-store-check", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("present:          True", out)

    def test_delete(self):
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        code, out, err = run("secret-store-delete", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertFalse((Path(self.root) / "config" / "device_secret.dev").exists())

    def test_delete_absent_no_error(self):
        code, out, err = run("secret-store-delete", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0)
        self.assertIn("absent", out.lower() if out else err.lower())

    # ── Security: secret never in output ───────────────────────────
    def test_stdout_no_secret(self):
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        code, out, err = run("secret-store-check", "--root", self.root, *DEV_FLAG)
        combined = out + err
        self.assertNotIn(TEST_SECRET, combined, "Secret leaked to check output")

    def test_stderr_no_secret(self):
        code, out, err = run("secret-store-check", "--root", self.root, *DEV_FLAG)
        self.assertNotIn(TEST_SECRET, out + err)

    def test_agent_config_no_secret(self):
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        content = (Path(self.root) / "config" / "agent_config.json").read_text()
        self.assertNotIn(TEST_SECRET, content, "Secret leaked to agent_config.json")

    def test_agent_status_no_secret(self):
        run("set-status", "--root", self.root, "--status", "running")
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        content = (Path(self.root) / "status" / "agent_status.json").read_text()
        self.assertNotIn(TEST_SECRET, content, "Secret leaked to agent_status.json")

    def test_doctor_no_secret(self):
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        code, out, err = run("doctor", "--root", self.root, *DEV_FLAG)
        self.assertNotIn(TEST_SECRET, out + err, "Secret leaked to doctor output")

    def test_config_status_no_secret(self):
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        code, out, err = run("config-status", "--root", self.root)
        self.assertNotIn(TEST_SECRET, out + err, "Secret leaked to config-status")

    # ── Validation ─────────────────────────────────────────────────
    def test_empty_secret_rejected(self):
        code, out, err = run_stdin(
            "\n", "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin",
        )
        self.assertNotEqual(code, 0)

    def test_too_short_secret_rejected(self):
        code, out, err = run_stdin(
            "abc", "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin",
        )
        self.assertNotEqual(code, 0)

    def test_too_long_secret_rejected(self):
        code, out, err = run_stdin(
            "x" * 513, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin",
        )
        self.assertNotEqual(code, 0)

    def test_set_without_stdin_rejected(self):
        code, out, err = run("secret-store-set", "--root", self.root, *DEV_FLAG)
        self.assertNotEqual(code, 0)
        self.assertIn("stdin", (out + err).lower())

    # ── Doctor integration ─────────────────────────────────────────
    def test_doctor_sees_dev_secret_store(self):
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        run("set-status", "--root", self.root, "--status", "running")
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        code, out, err = run("doctor", "--root", self.root, *DEV_FLAG)
        self.assertEqual(code, 0, f"err={err}")
        self.assertIn("dev_secret_store:", out)

    def test_doctor_without_flag_skips_secret(self):
        run_stdin(TEST_SECRET, "secret-store-set", "--root", self.root, *DEV_FLAG, "--stdin")
        run("set-status", "--root", self.root, "--status", "running")
        run("write-config", "--root", self.root,
            "--backend-base-url", "https://example.com", "--device-code", "a-05954")
        code, out, err = run("doctor", "--root", self.root)
        self.assertNotIn("dev_secret_store:", out,
                         "Doctor should not show secret store without flag")

    # ── No --device-secret arg ─────────────────────────────────────
    def test_no_device_secret_arg(self):
        code, out, err = run("--help")
        self.assertNotIn("device-secret", out, "CLI must not have --device-secret arg")
        self.assertNotIn("--secret", out, "CLI must not have --secret arg")
        self.assertNotIn("--token", out, "CLI must not have --token arg")


# ══════════════════════════════════════════════════════════════════════
# Memory Token State tests
# ══════════════════════════════════════════════════════════════════════

TOKEN_VALUE = "opaque-value-1234567890"
NOW = 1_750_000_000.0  # фиксированное время для тестов


class TestTokenState(unittest.TestCase):

    def _valid_response(self, **overrides):
        return {
            "access_token": TOKEN_VALUE,
            "token_type": "bearer",
            "expires_in": 3600,
            "device_id": "550e8400-e29b-41d4-a716-446655440000",
            "device_code": "a-05954",
            "status": "active",
            **overrides,
        }

    # ── from_auth_response ────────────────────────────────────────
    def test_from_auth_response_valid(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(), now=NOW)
        self.assertEqual(ts.device_code, "a-05954")
        self.assertEqual(ts.device_id, "550e8400-e29b-41d4-a716-446655440000")
        self.assertEqual(ts.expires_at, NOW + 3600)
        self.assertTrue(ts.access_token)

    # ── is_valid ───────────────────────────────────────────────────
    def test_is_valid_true(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(), now=NOW)
        # Сейчас (NOW) + safety 30s → expires_at = NOW+3600 > NOW+30
        self.assertTrue(ts.is_valid(now=NOW, safety_window_sec=30))

    def test_is_valid_false_inside_safety_window(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(expires_in=10), now=NOW)
        # expires_at = NOW+10, now+30 > NOW+10
        self.assertFalse(ts.is_valid(now=NOW, safety_window_sec=30))

    def test_is_valid_false_after_expiry(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(expires_in=10), now=NOW)
        # После истечения
        self.assertFalse(ts.is_valid(now=NOW + 20, safety_window_sec=0))

    def test_is_valid_false_no_token(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState()
        self.assertFalse(ts.is_valid())

    # ── authorization_header ───────────────────────────────────────
    def test_authorization_header_bearer(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(), now=NOW)
        hdr = ts.authorization_header(now=NOW)
        self.assertEqual(hdr, f"Bearer {TOKEN_VALUE}")

    def test_authorization_header_invalid_raises(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState()
        with self.assertRaises(ValueError):
            ts.authorization_header()

    # ── safe_summary ───────────────────────────────────────────────
    def test_safe_summary_no_token(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(), now=NOW)
        summary = ts.safe_summary(now=NOW)
        self.assertNotIn("access_token", summary)
        self.assertNotIn(TOKEN_VALUE, str(summary))
        self.assertIn("device_code", summary)
        self.assertEqual(summary["device_code"], "a-05954")

    # ── repr / str ─────────────────────────────────────────────────
    def test_repr_no_token(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(), now=NOW)
        r = repr(ts)
        self.assertNotIn(TOKEN_VALUE, r, f"Token found in repr: {r}")

    def test_str_no_token(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(), now=NOW)
        s = str(ts)
        self.assertNotIn(TOKEN_VALUE, s, f"Token found in str: {s}")

    # ── clear ──────────────────────────────────────────────────────
    def test_clear_removes_token(self):
        from kso_sidecar_agent.token_state import TokenState
        ts = TokenState.from_auth_response(self._valid_response(), now=NOW)
        ts.clear()
        self.assertEqual(ts.access_token, "")
        self.assertFalse(ts.is_valid())

    # ── Validation errors ──────────────────────────────────────────
    def test_missing_access_token_rejected(self):
        from kso_sidecar_agent.token_state import TokenState
        with self.assertRaises(ValueError):
            TokenState.from_auth_response(self._valid_response(access_token=""))

    def test_invalid_token_type_rejected(self):
        from kso_sidecar_agent.token_state import TokenState
        with self.assertRaises(ValueError):
            TokenState.from_auth_response(self._valid_response(token_type="mac"))

    def test_invalid_expires_in_rejected(self):
        from kso_sidecar_agent.token_state import TokenState
        with self.assertRaises(ValueError):
            TokenState.from_auth_response(self._valid_response(expires_in=0))
        with self.assertRaises(ValueError):
            TokenState.from_auth_response(self._valid_response(expires_in=-1))

    def test_invalid_device_id_rejected(self):
        from kso_sidecar_agent.token_state import TokenState
        with self.assertRaises(ValueError):
            TokenState.from_auth_response(self._valid_response(device_id=""))

    # ── Token never in test output ─────────────────────────────────
    def test_token_not_in_test_file(self):
        """Ensure TOKEN_VALUE is not in THIS test file's directory runtime files."""
        # Это тест на сам тест — тестовый токен не должен быть валидным JWT и не должен
        # содержать forbidden words
        self.assertNotIn("eyJ", TOKEN_VALUE)
        for word in ["token", "jwt", "password", "secret", "api_key"]:
            self.assertNotIn(word, TOKEN_VALUE.lower())


if __name__ == "__main__":
    unittest.main()
