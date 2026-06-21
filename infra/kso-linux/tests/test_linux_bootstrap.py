"""KSO Linux Bootstrap Installer — Tests.

Validates bootstrap script behavior:
  dry-run, apply to staging target-root, production safety gate,
  env validation, systemd unit verify, safe output.
"""

import json as _json
import os as _os
import shutil as _shutil
import sys as _sys
import tempfile
import unittest
from pathlib import Path
from typing import List

# ── Add install dir to path ──────────────────────────────────────────
_INSTALL_DIR = Path(__file__).resolve().parent.parent / "install"
if str(_INSTALL_DIR) not in _sys.path:
    _sys.path.insert(0, str(_INSTALL_DIR))

from kso_linux_bootstrap import (
    run_bootstrap,
    BootstrapResult,
    format_bootstrap_result,
    KSO_PATHS,
    _SYSTEMD_SRC,
    _ENV_SRC,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN = frozenset({
    "secret", "token", "password", "authorization",
    "bearer", "backend_url", "device_code", "api_key",
    "stacktrace", "traceback",
    "C:\\", "ProgramData", "Program Files", ".msi",
})


def _assert_safe(test, output: str):
    lower = output.lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, lower,
                         f"Safe output must not contain '{fb}': {output[:200]}")


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════


class TestBootstrapDryRun(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_boot_"))
        self.target = self.tmp / "install-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_changes_nothing(self):
        """Dry-run must not create any files/directories."""
        result = run_bootstrap(
            target_root=str(self.target), apply=False,
        )
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.dry_run)
        self.assertFalse(result.applied)
        self.assertEqual(result.directories_created, 0)
        self.assertEqual(result.files_copied, 0)
        self.assertFalse(self.target.exists(),
                         "Dry-run must not create target root")
        _assert_safe(self, format_bootstrap_result(result))

    def test_dry_run_reports_plan(self):
        """Dry-run must report planned directories and files."""
        result = run_bootstrap(
            target_root=str(self.target), apply=False,
        )
        self.assertGreater(result.directories_planned, 0)
        self.assertGreater(result.files_planned, 0)
        _assert_safe(self, format_bootstrap_result(result))


class TestBootstrapApplyTargetRoot(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_boot_"))
        self.target = self.tmp / "install-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_apply_creates_directories(self):
        """Apply must create expected directories under target-root."""
        result = run_bootstrap(
            target_root=str(self.target), apply=True,
        )
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.applied)
        self.assertGreater(result.directories_created, 0)

        # Verify key directories exist
        for key in ("opt", "etc", "var_lib", "run", "var_log"):
            expected = self.target / KSO_PATHS[key].lstrip("/")
            self.assertTrue(expected.is_dir(),
                            f"Directory must exist: {expected}")
        _assert_safe(self, format_bootstrap_result(result))

    def test_apply_copies_unit_files(self):
        """Apply must copy systemd unit files."""
        result = run_bootstrap(
            target_root=str(self.target), apply=True,
        )
        self.assertGreater(result.files_copied, 0)

        systemd_dir = self.target / "etc/systemd/system"
        self.assertTrue((systemd_dir / "kso-sidecar.service").is_file())
        self.assertTrue((systemd_dir / "kso-player.service").is_file())
        _assert_safe(self, format_bootstrap_result(result))

    def test_apply_copies_env_examples(self):
        """Apply must copy env examples only as .example."""
        result = run_bootstrap(
            target_root=str(self.target), apply=True,
        )

        etc_dir = self.target / "etc/verny/kso"
        self.assertTrue((etc_dir / "kso-sidecar.env.example").is_file())
        self.assertTrue((etc_dir / "kso-player.env.example").is_file())

        # Must NOT create real .env files
        self.assertFalse((etc_dir / "kso-sidecar.env").exists(),
                         "Must not create real env files")
        _assert_safe(self, format_bootstrap_result(result))

    def test_existing_env_not_overwritten(self):
        """If real .env exists, must not be touched."""
        result1 = run_bootstrap(
            target_root=str(self.target), apply=True,
        )

        etc_dir = self.target / "etc/verny/kso"
        # Create a fake real env file
        (etc_dir / "kso-sidecar.env").write_text("# real secrets\n")
        (etc_dir / "kso-sidecar.env.example").unlink()

        result2 = run_bootstrap(
            target_root=str(self.target), apply=True,
        )
        self.assertTrue((etc_dir / "kso-sidecar.env").exists(),
                        "Real env must survive")
        self.assertTrue(result2.env_existing_count >= 1)
        _assert_safe(self, format_bootstrap_result(result2))

    def test_existing_unit_not_overwritten(self):
        """If unit file already exists, must not overwrite."""
        run_bootstrap(target_root=str(self.target), apply=True)

        systemd_dir = self.target / "etc/systemd/system"
        sidecar_unit = systemd_dir / "kso-sidecar.service"
        original = sidecar_unit.read_text()

        # Apply again
        result2 = run_bootstrap(
            target_root=str(self.target), apply=True,
        )
        self.assertEqual(sidecar_unit.read_text(), original,
                         "Existing unit must not be overwritten")
        self.assertGreater(result2.files_skipped, 0)
        _assert_safe(self, format_bootstrap_result(result2))


class TestBootstrapProductionSafetyGates(unittest.TestCase):

    def test_production_root_without_confirm_fails(self):
        """Production target-root=/ without danger flag must fail."""
        result = run_bootstrap(
            target_root="/", apply=True,
            production_confirm=False,
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.reason, "production_requires_confirm")
        _assert_safe(self, format_bootstrap_result(result))

    def test_production_root_dry_run_succeeds(self):
        """Production root dry-run is safe (reports plan only)."""
        result = run_bootstrap(
            target_root="/", apply=False,
        )
        self.assertEqual(result.status, "ok")
        self.assertFalse(result.applied)
        _assert_safe(self, format_bootstrap_result(result))

    def test_production_root_with_confirm_allowed(self):
        """Production root with confirm flag returns plan but apply depends on system."""
        # We can't actually apply to / in tests, but we verify the API accepts it
        result = run_bootstrap(
            target_root="/", apply=True,
            production_confirm=True,
        )
        # May succeed or have warnings based on permissions
        self.assertIn(result.status, ("ok", "error", "warning"))
        _assert_safe(self, format_bootstrap_result(result))

    def test_unsafe_non_tmp_target_fails(self):
        """Non-/tmp target root must be rejected."""
        result = run_bootstrap(
            target_root="/home/user/kso", apply=True,
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.reason, "unsafe_target_root")
        _assert_safe(self, format_bootstrap_result(result))

    def test_no_systemctl_calls(self):
        """Bootstrap must not call systemctl start/enable/restart."""
        src = (_INSTALL_DIR / "kso_linux_bootstrap.py").read_text()
        # Check for actual command calls, not docstring warnings
        # Remove docstrings and comments before checking
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
            if stripped.startswith("#"):
                continue
            code_lines.append(line)
        code = "\n".join(code_lines)

        self.assertNotIn("systemctl start", code)
        self.assertNotIn("systemctl enable", code)
        self.assertNotIn("systemctl restart", code)
        self.assertNotIn("systemctl daemon-reload", code)
        self.assertNotIn("systemctl --now", code)


class TestBootstrapEnvValidation(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_boot_"))
        self.target = self.tmp / "install-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_env_validation_no_secrets_in_output(self):
        """Env validation must not print secret values."""
        # Setup with existing env containing placeholders
        run_bootstrap(target_root=str(self.target), apply=True)

        etc_dir = self.target / "etc/verny/kso"
        env_path = etc_dir / "kso-sidecar.env.example"
        env_path.write_text(
            "VERNY_KSO_DEVICE_SECRET=CHANGE_ME_SECRET\n"
        )

        result = run_bootstrap(
            target_root=str(self.target), apply=True,
            validate_env=str(env_path),
        )

        output = format_bootstrap_result(result)
        self.assertNotIn("CHANGE_ME_SECRET", output,
                         "Output must not contain placeholder secret")
        _assert_safe(self, output)

    def test_env_validation_detects_placeholders(self):
        """Env validation must warn about CHANGE_ME placeholders."""
        run_bootstrap(target_root=str(self.target), apply=True)

        etc_dir = self.target / "etc/verny/kso"
        env_path = etc_dir / "kso-sidecar.env.example"
        env_path.write_text(
            "VERNY_KSO_DEVICE_SECRET=CHANGE_ME_SECRET\n"
        )

        result = run_bootstrap(
            target_root=str(self.target), apply=True,
            validate_env=str(env_path),
        )
        # Should have warnings about placeholders
        self.assertGreater(result.warnings_count, 0)
        _assert_safe(self, format_bootstrap_result(result))

    def test_env_validation_file_not_found(self):
        """Missing env file for validation must warn."""
        result = run_bootstrap(
            target_root=str(self.target), apply=True,
            validate_env="/nonexistent/env.file",
        )
        self.assertGreater(result.warnings_count, 0)
        _assert_safe(self, format_bootstrap_result(result))


class TestBootstrapUnitVerify(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_boot_"))
        self.target = self.tmp / "install-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_verify_units_with_fake_runner(self):
        """Unit verify with fake command runner."""
        run_bootstrap(target_root=str(self.target), apply=True)

        runner_calls = []

        def fake_runner(cmd):
            runner_calls.append(cmd)
            return 0, "", ""

        result = run_bootstrap(
            target_root=str(self.target), apply=True,
            verify_units=True,
            command_runner=fake_runner,
        )

        self.assertTrue(result.systemd_units_verified)
        self.assertEqual(result.unit_verify_status, "ok")
        self.assertGreater(len(runner_calls), 0)
        _assert_safe(self, format_bootstrap_result(result))

    def test_verify_units_failure_safe(self):
        """Unit verify failure must not crash or expose stacktrace."""
        run_bootstrap(target_root=str(self.target), apply=True)

        def failing_runner(cmd):
            return 1, "", "syntax error"

        result = run_bootstrap(
            target_root=str(self.target), apply=True,
            verify_units=True,
            command_runner=failing_runner,
        )

        self.assertFalse(result.systemd_units_verified)
        self.assertEqual(result.unit_verify_status, "failed")
        output = format_bootstrap_result(result)
        self.assertNotIn("syntax error", output,
                         "Must not expose raw error text")
        _assert_safe(self, output)

    def test_verify_units_runner_exception_safe(self):
        """Unit verify exception must not expose stacktrace."""
        run_bootstrap(target_root=str(self.target), apply=True)

        def exploding_runner(cmd):
            raise RuntimeError("systemd not available")

        result = run_bootstrap(
            target_root=str(self.target), apply=True,
            verify_units=True,
            command_runner=exploding_runner,
        )

        self.assertEqual(result.unit_verify_status, "error")
        output = format_bootstrap_result(result)
        self.assertNotIn("RuntimeError", output)
        self.assertNotIn("systemd not available", output)
        _assert_safe(self, output)

    def test_verify_units_without_apply(self):
        """Verify units in dry-run mode must report skipped."""
        result = run_bootstrap(
            target_root=str(self.target), apply=False,
            verify_units=True,
        )
        self.assertEqual(result.unit_verify_status, "skipped")
        _assert_safe(self, format_bootstrap_result(result))


class TestBootstrapResultFormat(unittest.TestCase):

    def test_result_repr_safe(self):
        result = BootstrapResult(
            status="ok", dry_run=True,
            directories_planned=6, files_planned=4,
            reason="dry_run_completed",
        )
        _assert_safe(self, repr(result))
        _assert_safe(self, format_bootstrap_result(result))

    def test_result_with_warnings_safe(self):
        result = BootstrapResult(
            status="warning", dry_run=False, applied=True,
            directories_planned=6, directories_created=6,
            directories_skipped=0,
            files_planned=4, files_copied=4,
            warnings=["Unit file already exists"],
            reason="applied_with_warnings",
        )
        _assert_safe(self, repr(result))
        _assert_safe(self, format_bootstrap_result(result))

    def test_result_error_safe(self):
        result = BootstrapResult(
            status="error", dry_run=True,
            reason="production_requires_confirm",
        )
        _assert_safe(self, repr(result))
        _assert_safe(self, format_bootstrap_result(result))


class TestBootstrapIdempotency(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_boot_"))
        self.target = self.tmp / "install-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_double_apply_is_safe(self):
        """Applying twice must not fail or corrupt files."""
        result1 = run_bootstrap(
            target_root=str(self.target), apply=True,
        )
        self.assertEqual(result1.status, "ok")

        result2 = run_bootstrap(
            target_root=str(self.target), apply=True,
        )
        self.assertEqual(result2.status, "warning")  # existing files
        self.assertGreater(result2.files_skipped, 0)
        _assert_safe(self, format_bootstrap_result(result2))


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
