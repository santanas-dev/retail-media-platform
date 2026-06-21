"""KSO Linux Preflight Validator — Tests.

Validates preflight checks:
  directories, env files, systemd units, Chromium, player_shell,
  CLI, health path. All injectable, no real systemd/Chromium.
"""

import os as _os
import shutil as _shutil
import sys as _sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple

_INFRA_DIR = Path(__file__).resolve().parent.parent
_PREFLIGHT_DIR = _INFRA_DIR / "preflight"
if str(_PREFLIGHT_DIR) not in _sys.path:
    _sys.path.insert(0, str(_PREFLIGHT_DIR))

from kso_linux_preflight import (
    run_preflight,
    PreflightResult,
    format_preflight_result,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    KSO_PATHS,
)

FORBIDDEN = frozenset({
    "secret", "token", "password", "authorization",
    "bearer", "backend_url", "device_code", "api_key",
    "stacktrace", "traceback",
    "CHANGE_ME", "C:\\", "ProgramData", ".msi",
})


def _assert_safe(test, output: str):
    lower = output.lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, lower,
                         f"Safe output must not contain '{fb}': {output[:200]}")


def _setup_staging_root(base: Path) -> Path:
    """Create a complete staging root: dirs + units + env examples."""
    target = base / "staging-root"

    for key, path in KSO_PATHS.items():
        d = target / path.lstrip("/")
        d.mkdir(parents=True, exist_ok=True)

    # Player shell
    ps = target / "opt/verny/kso/player_shell"
    ps.mkdir(parents=True, exist_ok=True)
    for fname in ("index.html", "styles.css", "player.js",
                   "bootstrap.js", "bootstrap_snapshot.js"):
        (ps / fname).write_text(f"/* {fname} */\n")

    # Systemd units
    sd = target / "etc/systemd/system"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "kso-sidecar.service").write_text("[Unit]\n")
    (sd / "kso-player.service").write_text("[Unit]\n")

    # Env files
    etc = target / "etc/verny/kso"
    etc.mkdir(parents=True, exist_ok=True)
    (etc / "kso-sidecar.env").write_text(
        "VERNY_KSO_BACKEND_URL=https://backend.example\n"
        "VERNY_KSO_DEVICE_CODE=CHANGE_ME\n"
        "VERNY_KSO_DEVICE_SECRET=CHANGE_ME_SECRET\n"
    )
    (etc / "kso-player.env").write_text(
        "VERNY_KSO_CHROMIUM_BIN=/usr/bin/chromium\n"
    )

    return target


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestPreflightPass(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_pf_"))

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_preflight_passes_on_prepared_root(self):
        target = _setup_staging_root(self.tmp)
        # Use clean env (no placeholders) for a clean pass
        (target / "etc/verny/kso/kso-sidecar.env").write_text(
            "VERNY_KSO_BACKEND_URL=https://backend.prod.example\n"
            "VERNY_KSO_DEVICE_CODE=a-05954\n"
            "VERNY_KSO_DEVICE_SECRET=prod_s..."
        )
        result = run_preflight(target_root=str(target))
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.directories_missing, 0)
        self.assertEqual(result.systemd_units_missing, 0)
        self.assertTrue(result.player_shell_ok)
        self.assertTrue(result.sidecar_env_present)
        self.assertTrue(result.player_env_present)
        self.assertTrue(result.health_path_writable)
        _assert_safe(self, format_preflight_result(result))

    def test_result_repr_safe(self):
        target = _setup_staging_root(self.tmp)
        result = run_preflight(target_root=str(target))
        _assert_safe(self, repr(result))
        _assert_safe(self, format_preflight_result(result))


class TestPreflightDirectories(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_pf_"))

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reports_missing_directories(self):
        target = self.tmp / "empty-root"
        target.mkdir()
        result = run_preflight(target_root=str(target))
        self.assertGreater(result.directories_missing, 0)
        self.assertEqual(result.status, STATUS_ERROR)
        _assert_safe(self, format_preflight_result(result))


class TestPreflightEnv(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_pf_"))

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reports_missing_sidecar_env(self):
        target = _setup_staging_root(self.tmp)
        (target / "etc/verny/kso/kso-sidecar.env").unlink()
        result = run_preflight(target_root=str(target))
        self.assertFalse(result.sidecar_env_present)
        self.assertGreater(result.warnings_count, 0)
        _assert_safe(self, format_preflight_result(result))

    def test_reports_missing_player_env(self):
        target = _setup_staging_root(self.tmp)
        (target / "etc/verny/kso/kso-player.env").unlink()
        result = run_preflight(target_root=str(target))
        self.assertFalse(result.player_env_present)
        self.assertGreater(result.warnings_count, 0)
        _assert_safe(self, format_preflight_result(result))

    def test_detects_placeholders_without_printing_values(self):
        target = _setup_staging_root(self.tmp)
        result = run_preflight(target_root=str(target))
        self.assertTrue(result.sidecar_env_has_placeholders)
        self.assertGreater(result.warnings_count, 0)

        output = format_preflight_result(result)
        self.assertNotIn("CHANGE_ME_SECRET", output)
        self.assertNotIn("CHANGE_ME", output)
        _assert_safe(self, output)

    def test_rejects_non_https_backend(self):
        target = _setup_staging_root(self.tmp)
        (target / "etc/verny/kso/kso-sidecar.env").write_text(
            "VERNY_KSO_BACKEND_URL=http://insecure.example\n"
            "VERNY_KSO_DEVICE_CODE=code123\n"
            "VERNY_KSO_DEVICE_SECRET=real_secret_abc\n"
        )
        result = run_preflight(target_root=str(target))
        self.assertFalse(result.sidecar_env_backend_https)
        self.assertGreater(result.warnings_count, 0)

        output = format_preflight_result(result)
        self.assertNotIn("http://insecure", output,
                         "Must not print backend URL value")
        self.assertNotIn("code123", output,
                         "Must not print device code")
        self.assertNotIn("real_secret_abc", output,
                         "Must not print secret")
        _assert_safe(self, output)

    def test_clean_env_no_warnings(self):
        target = _setup_staging_root(self.tmp)
        (target / "etc/verny/kso/kso-sidecar.env").write_text(
            "VERNY_KSO_BACKEND_URL=https://backend.prod.example\n"
            "VERNY_KSO_DEVICE_CODE=a-05954\n"
            "VERNY_KSO_DEVICE_SECRET=real_prod_secret\n"
        )
        (target / "etc/verny/kso/kso-player.env").write_text(
            "VERNY_KSO_CHROMIUM_BIN=/usr/bin/chromium\n"
        )
        result = run_preflight(target_root=str(target))
        self.assertFalse(result.sidecar_env_has_placeholders)
        self.assertFalse(result.player_env_has_placeholders)
        _assert_safe(self, format_preflight_result(result))


class TestPreflightSystemdUnits(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_pf_"))

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reports_missing_units(self):
        target = _setup_staging_root(self.tmp)
        (target / "etc/systemd/system/kso-sidecar.service").unlink()
        result = run_preflight(target_root=str(target))
        self.assertGreater(result.systemd_units_missing, 0)
        _assert_safe(self, format_preflight_result(result))

    def test_unit_verify_with_fake_runner(self):
        target = _setup_staging_root(self.tmp)
        calls = []

        def fake_runner(cmd):
            calls.append(cmd)
            return 0, "", ""

        result = run_preflight(
            target_root=str(target),
            verify_units=True,
            command_runner=fake_runner,
        )
        self.assertTrue(result.systemd_units_verify_ok)
        self.assertEqual(result.systemd_units_verify_status, "ok")
        self.assertGreater(len(calls), 0)
        _assert_safe(self, format_preflight_result(result))

    def test_unit_verify_failure_safe(self):
        target = _setup_staging_root(self.tmp)

        def failing_runner(cmd):
            return 1, "", "syntax error at line 5"

        result = run_preflight(
            target_root=str(target),
            verify_units=True,
            command_runner=failing_runner,
        )
        self.assertFalse(result.systemd_units_verify_ok)
        output = format_preflight_result(result)
        self.assertNotIn("syntax error", output)
        _assert_safe(self, output)


class TestPreflightCLI(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_pf_"))

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cli_help_with_fake_runner(self):
        target = _setup_staging_root(self.tmp)
        calls = []

        def fake_runner(cmd):
            calls.append(cmd[0:3])  # Store command without full path
            return 0, "help output", ""

        result = run_preflight(
            target_root=str(target),
            verify_cli=True,
            command_runner=fake_runner,
        )
        self.assertTrue(result.cli_sidecar_ok)
        self.assertTrue(result.cli_player_ok)
        self.assertGreater(len(calls), 0)
        _assert_safe(self, format_preflight_result(result))

    def test_cli_help_failure_safe(self):
        target = _setup_staging_root(self.tmp)

        def failing_runner(cmd):
            return 1, "", "ImportError: no module named kso_sidecar_agent"

        result = run_preflight(
            target_root=str(target),
            verify_cli=True,
            command_runner=failing_runner,
        )
        self.assertFalse(result.cli_sidecar_ok)
        self.assertFalse(result.cli_player_ok)
        output = format_preflight_result(result)
        self.assertNotIn("ImportError", output)
        self.assertNotIn("kso_sidecar_agent", output)
        _assert_safe(self, output)


class TestPreflightChromium(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_pf_"))

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_chromium_configured_no_launch(self):
        target = _setup_staging_root(self.tmp)
        (target / "etc/verny/kso/kso-player.env").write_text(
            "VERNY_KSO_CHROMIUM_BIN=/usr/bin/chromium\n"
        )
        result = run_preflight(target_root=str(target))
        self.assertTrue(result.chromium_configured)
        # Chromium_bin_checked only set when verify_cli=True
        self.assertFalse(result.chromium_bin_checked)
        _assert_safe(self, format_preflight_result(result))

    def test_chromium_bin_check_fake(self):
        target = _setup_staging_root(self.tmp)
        (target / "etc/verny/kso/kso-player.env").write_text(
            "VERNY_KSO_CHROMIUM_BIN=/usr/bin/chromium\n"
        )

        def fake_runner(cmd):
            if "which" in cmd:
                return 0, "/usr/bin/chromium", ""
            return 0, "help", ""

        result = run_preflight(
            target_root=str(target),
            verify_cli=True,
            command_runner=fake_runner,
        )
        self.assertTrue(result.cli_sidecar_ok)  # fake runner returns 0
        self.assertTrue(result.chromium_bin_checked)


class TestPreflightPlayerShell(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_pf_"))

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_player_shell_missing_files(self):
        target = _setup_staging_root(self.tmp)
        ps = target / "opt/verny/kso/player_shell"
        (ps / "player.js").unlink()
        (ps / "styles.css").unlink()
        result = run_preflight(target_root=str(target))
        self.assertFalse(result.player_shell_ok)
        self.assertEqual(result.player_shell_missing_files_count, 2)
        _assert_safe(self, format_preflight_result(result))

    def test_player_shell_all_ok(self):
        target = _setup_staging_root(self.tmp)
        result = run_preflight(target_root=str(target))
        self.assertTrue(result.player_shell_ok)
        self.assertEqual(result.player_shell_missing_files_count, 0)


class TestPreflightSafety(unittest.TestCase):

    def test_no_systemctl_calls(self):
        src = (_PREFLIGHT_DIR / "kso_linux_preflight.py").read_text()
        lines = src.split("\n")
        code_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            code_lines.append(line)
        code = "\n".join(code_lines)

        for banned in ("systemctl start", "systemctl enable",
                        "systemctl restart", "systemctl daemon-reload"):
            self.assertNotIn(banned, code,
                             f"Preflight must not call {banned}")

    def test_no_curl_wget(self):
        src = (_PREFLIGHT_DIR / "kso_linux_preflight.py").read_text()
        self.assertNotIn("curl", src.lower())
        self.assertNotIn("wget", src.lower())

    def test_no_windows(self):
        src = (_PREFLIGHT_DIR / "kso_linux_preflight.py").read_text()
        # Remove the FORBIDDEN_IN_OUTPUT block itself from the check
        lines = src.split("\n")
        filtered = []
        skip_block = False
        for line in lines:
            if "FORBIDDEN_IN_OUTPUT" in line and "frozenset" in line:
                skip_block = True
                continue
            if skip_block:
                if ")" in line and not "," in line:
                    skip_block = False
                continue
            filtered.append(line)
        code = "\n".join(filtered)
        self.assertNotIn("C:\\", code)
        self.assertNotIn("ProgramData", code)
        self.assertNotIn(".msi", code.lower())


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
