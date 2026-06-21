"""KSO Linux Staging Deployment Scenario — Tests.

End-to-end staging deployment validation:
  1. Static unknown staging
  2. File source staging
  3. Unsafe source file path
  4. Missing real env files

No systemctl, no real Chromium, no real UKM 4, no real backend.
All command runners are fake.
"""

import os as _os
import shutil as _shutil
import sys as _sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple

# ── Add infra dirs to path ───────────────────────────────────────────
_INFRA_DIR = Path(__file__).resolve().parent.parent
_INSTALL_DIR = _INFRA_DIR / "install"
_PREFLIGHT_DIR = _INFRA_DIR / "preflight"

for d in (_INSTALL_DIR, _PREFLIGHT_DIR):
    if str(d) not in _sys.path:
        _sys.path.insert(0, str(d))

from kso_linux_bootstrap import (
    run_bootstrap,
    BootstrapResult,
    format_bootstrap_result,
    KSO_PATHS,
)
from kso_linux_preflight import (
    run_preflight,
    PreflightResult,
    format_preflight_result,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
)

# ══════════════════════════════════════════════════════════════════════
# Forbidden substrings for safe output assertions
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN = frozenset({
    "secret", "token", "password", "authorization",
    "bearer", "backend_url", "device_code", "api_key",
    "stacktrace", "traceback",
    "C:\\\\", "ProgramData", ".msi",
    "receipt_number", "receipt_data", "card_number", "pan",
    "customer_id", "phone", "email", "fiscal_data",
    "sku", "amount", "cashier",
    # "total" intentionally NOT forbidden — appears in safe fields
    #   like directories_total, systemd_units_total, checks_total
})


def _assert_safe(test: unittest.TestCase, output: str):
    lower = output.lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb, lower,
                         f"Safe output must not contain '{fb}': {output[:200]}")


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _create_player_shell(target_root: Path) -> None:
    """Create minimal player_shell with 5 required files."""
    ps = target_root / "opt/verny/kso/player_shell"
    ps.mkdir(parents=True, exist_ok=True)
    for fname in ("index.html", "styles.css", "player.js",
                   "bootstrap.js", "bootstrap_snapshot.js"):
        (ps / fname).write_text(f"/* {fname} - staging */\n")


def _create_state_adapter_env(etc_dir: Path,
                                source: str = "static",
                                static_state: str = "unknown",
                                source_file: str = "/run/verny/kso/ukm4-safe-state.json") -> None:
    """Write state-adapter.env."""
    content = (
        f"VERNY_KSO_STATE_SOURCE={source}\n"
        f"VERNY_KSO_STATIC_STATE={static_state}\n"
        f"VERNY_KSO_SOURCE_FILE={source_file}\n"
    )
    (etc_dir / "kso-state-adapter.env").write_text(content)


def _create_sidecar_env(etc_dir: Path) -> None:
    """Write a clean sidecar.env (no placeholders)."""
    (etc_dir / "kso-sidecar.env").write_text(
        "VERNY_KSO_BACKEND_URL=https://backend.prod.example\n"
        "VERNY_KSO_DEVICE_CODE=a-05954\n"
        "VERNY_KSO_DEVICE_SECRET=prod_secret_real\n"
    )


def _create_player_env(etc_dir: Path) -> None:
    """Write player.env."""
    (etc_dir / "kso-player.env").write_text(
        "VERNY_KSO_CHROMIUM_BIN=/usr/bin/chromium\n"
    )


def _create_source_file(content: str, path: Path) -> None:
    """Create a safe status file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _fake_all_pass_runner():
    """Runner that passes every command + captures calls for later inspection.

    Returns (runner, calls_list) tuple.
    """
    calls: List[List[str]] = []

    def runner(cmd: List[str]) -> Tuple[int, str, str]:
        calls.append(cmd)
        return 0, "ok", ""

    return runner, calls


# ══════════════════════════════════════════════════════════════════════
# Scenario 1 — Static unknown staging
# ══════════════════════════════════════════════════════════════════════

class TestScenarioStaticUnknownStaging(unittest.TestCase):
    """Bootstrap → create real env → prepare player_shell → preflight."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_s1_"))
        self.target = self.tmp / "staging-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_static_unknown_staging(self):
        """Bootstrap apply + env files + player_shell → preflight passes."""
        # ── Phase 1: Bootstrap apply to staging root ──────────────
        result = run_bootstrap(
            target_root=str(self.target),
            apply=True,
        )
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.applied)
        self.assertGreater(result.directories_created, 0)
        self.assertGreater(result.files_copied, 0)
        _assert_safe(self, format_bootstrap_result(result))

        # ── Phase 2: Create real env files ────────────────────────
        etc_dir = self.target / "etc/verny/kso"
        _create_state_adapter_env(etc_dir, source="static",
                                   static_state="unknown")
        _create_sidecar_env(etc_dir)
        _create_player_env(etc_dir)

        # Verify real env files exist
        self.assertTrue((etc_dir / "kso-state-adapter.env").is_file())
        self.assertTrue((etc_dir / "kso-sidecar.env").is_file())
        self.assertTrue((etc_dir / "kso-player.env").is_file())

        # ── Phase 3: Prepare player_shell ─────────────────────────
        _create_player_shell(self.target)

        # ── Phase 4: Run preflight ────────────────────────────────
        fake_runner, runner_calls = _fake_all_pass_runner()
        pf_result = run_preflight(
            target_root=str(self.target),
            verify_units=True,
            verify_cli=True,
            command_runner=fake_runner,
        )

        # Should be ok or warning (warnings from .example files OK)
        self.assertIn(pf_result.status, (STATUS_OK, STATUS_WARNING))

        # Verify state adapter config
        self.assertTrue(pf_result.state_adapter_env_present)
        self.assertEqual(pf_result.state_adapter_source_mode, "static")
        self.assertEqual(pf_result.state_adapter_env_missing_keys_count, 0)

        # Player shell should be OK
        self.assertTrue(pf_result.player_shell_ok)
        self.assertEqual(pf_result.player_shell_missing_files_count, 0)

        # Systemd units present
        self.assertEqual(pf_result.systemd_units_ok, 3)
        self.assertEqual(pf_result.systemd_units_missing, 0)

        # CLI checks passed
        self.assertTrue(pf_result.cli_sidecar_ok)
        self.assertTrue(pf_result.cli_player_ok)
        self.assertTrue(pf_result.cli_state_adapter_ok)

        # Verify fake runner was called for CLI checks
        self.assertGreater(len(runner_calls), 0)

        # Output safe
        _assert_safe(self, format_preflight_result(pf_result))

    def test_static_unknown_output_safe(self):
        """Preflight output must not print state values or env secrets."""
        result = run_bootstrap(target_root=str(self.target), apply=True)
        etc_dir = self.target / "etc/verny/kso"
        _create_state_adapter_env(etc_dir, source="static",
                                   static_state="unknown")
        _create_sidecar_env(etc_dir)
        _create_player_env(etc_dir)
        _create_player_shell(self.target)

        pf_result = run_preflight(target_root=str(self.target))
        output = format_preflight_result(pf_result)

        # Must NOT contain raw values
        self.assertNotIn("static", output.lower())
        self.assertNotIn("unknown", output.lower())
        self.assertNotIn("a-05954", output)
        self.assertNotIn("prod_secret_real", output)
        _assert_safe(self, output)


# ══════════════════════════════════════════════════════════════════════
# Scenario 2 — File source staging
# ══════════════════════════════════════════════════════════════════════

class TestScenarioFileSourceStaging(unittest.TestCase):
    """Bootstrap → file source env → source file → preflight."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_s2_"))
        self.target = self.tmp / "staging-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_file_source_staging(self):
        """Bootstrap + file source env + source file → preflight checks."""
        # ── Phase 1: Bootstrap ────────────────────────────────────
        run_bootstrap(target_root=str(self.target), apply=True)

        # ── Phase 2: Create env files ─────────────────────────────
        etc_dir = self.target / "etc/verny/kso"
        _create_state_adapter_env(etc_dir, source="file",
                                   static_state="unknown",
                                   source_file="/run/verny/kso/ukm4-safe-state.json")
        _create_sidecar_env(etc_dir)
        _create_player_env(etc_dir)

        # ── Phase 3: Create source file under allowed root ────────
        # The source file must be under /run/verny/kso/ relative to target
        run_dir = self.target / "run/verny/kso"
        run_dir.mkdir(parents=True, exist_ok=True)
        source_file = run_dir / "ukm4-safe-state.json"
        _create_source_file('{"state":"unknown"}', source_file)

        # ── Phase 4: Prepare player_shell ─────────────────────────
        _create_player_shell(self.target)

        # ── Phase 5: Preflight ────────────────────────────────────
        fake_runner, _ = _fake_all_pass_runner()
        pf_result = run_preflight(
            target_root=str(self.target),
            verify_units=True,
            verify_cli=True,
            command_runner=fake_runner,
        )

        self.assertIn(pf_result.status, (STATUS_OK, STATUS_WARNING))
        self.assertTrue(pf_result.state_adapter_env_present)
        self.assertEqual(pf_result.state_adapter_source_mode, "file")
        self.assertTrue(pf_result.state_adapter_source_file_configured)
        self.assertTrue(pf_result.state_adapter_source_file_allowed)

        _assert_safe(self, format_preflight_result(pf_result))

    def test_file_source_output_no_content(self):
        """Preflight must NOT read/print source file content."""
        run_bootstrap(target_root=str(self.target), apply=True)
        etc_dir = self.target / "etc/verny/kso"
        _create_state_adapter_env(etc_dir, source="file",
                                   static_state="unknown",
                                   source_file="/run/verny/kso/ukm4-safe-state.json")
        _create_sidecar_env(etc_dir)
        _create_player_env(etc_dir)

        # Create source file with forbidden content
        run_dir = self.target / "run/verny/kso"
        run_dir.mkdir(parents=True, exist_ok=True)
        sf = run_dir / "ukm4-safe-state.json"
        sf.write_text('{"state":"unknown","receipt_number":"SECRET"}')

        # Create player_shell
        _create_player_shell(self.target)

        pf_result = run_preflight(target_root=str(self.target))
        output = format_preflight_result(pf_result).lower()

        # Must NOT contain file content
        self.assertNotIn("receipt_number", output)
        self.assertNotIn("secret", output)
        self.assertNotIn("ukm4-safe-state.json", output)

        _assert_safe(self, output)

    def test_file_source_output_no_path_value(self):
        """Preflight output must not contain raw source file path."""
        run_bootstrap(target_root=str(self.target), apply=True)
        etc_dir = self.target / "etc/verny/kso"
        _create_state_adapter_env(etc_dir, source="file",
                                   static_state="unknown",
                                   source_file="/run/verny/kso/ukm4-safe-state.json")
        _create_sidecar_env(etc_dir)
        _create_player_env(etc_dir)
        _create_player_shell(self.target)

        pf_result = run_preflight(target_root=str(self.target))
        output = format_preflight_result(pf_result)

        self.assertNotIn("ukm4-safe-state.json", output)
        self.assertNotIn("/run/verny/kso/ukm4", output)
        _assert_safe(self, output)


# ══════════════════════════════════════════════════════════════════════
# Scenario 3 — Unsafe source file path
# ══════════════════════════════════════════════════════════════════════

class TestScenarioUnsafeSourceFilePath(unittest.TestCase):
    """File source with path outside allowed roots → warning/error."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_s3_"))
        self.target = self.tmp / "staging-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unsafe_source_file_path_rejected(self):
        """Source file under /tmp must be flagged as not allowed."""
        run_bootstrap(target_root=str(self.target), apply=True)
        etc_dir = self.target / "etc/verny/kso"
        _create_state_adapter_env(etc_dir, source="file",
                                   static_state="unknown",
                                   source_file="/tmp/ukm4-safe-state.json")
        _create_sidecar_env(etc_dir)
        _create_player_env(etc_dir)
        _create_player_shell(self.target)

        pf_result = run_preflight(target_root=str(self.target))

        self.assertEqual(pf_result.state_adapter_source_mode, "file")
        self.assertTrue(pf_result.state_adapter_source_file_configured)
        self.assertFalse(pf_result.state_adapter_source_file_allowed)
        self.assertGreater(pf_result.warnings_count, 0)

        _assert_safe(self, format_preflight_result(pf_result))

    def test_unsafe_path_output_no_values(self):
        """Output must not print the unsafe path value."""
        run_bootstrap(target_root=str(self.target), apply=True)
        etc_dir = self.target / "etc/verny/kso"
        _create_state_adapter_env(etc_dir, source="file",
                                   static_state="unknown",
                                   source_file="/tmp/ukm4-safe-state.json")
        _create_sidecar_env(etc_dir)
        _create_player_env(etc_dir)
        _create_player_shell(self.target)

        pf_result = run_preflight(target_root=str(self.target))
        output = format_preflight_result(pf_result)

        self.assertNotIn("/tmp/ukm4-safe-state.json", output)
        self.assertNotIn("ukm4-safe-state", output)
        _assert_safe(self, output)

    def test_invalid_source_mode(self):
        """Invalid source mode must be caught."""
        run_bootstrap(target_root=str(self.target), apply=True)
        etc_dir = self.target / "etc/verny/kso"
        _create_state_adapter_env(etc_dir, source="invalid",
                                   static_state="unknown")
        _create_sidecar_env(etc_dir)
        _create_player_env(etc_dir)
        _create_player_shell(self.target)

        pf_result = run_preflight(target_root=str(self.target))

        self.assertEqual(pf_result.state_adapter_source_mode, "invalid")
        self.assertGreater(pf_result.warnings_count, 0)

        # Preflight may report the mode name in warning text —
        # that's legitimate feedback for the operator to fix config
        _assert_safe(self, format_preflight_result(pf_result))


# ══════════════════════════════════════════════════════════════════════
# Scenario 4 — Missing real env files
# ══════════════════════════════════════════════════════════════════════

class TestScenarioMissingEnvFiles(unittest.TestCase):
    """Bootstrap creates .example only — no real .env files → preflight warns."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_s4_"))
        self.target = self.tmp / "staging-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_env_after_bootstrap_only(self):
        """After bootstrap, only .example files exist, not real .env."""
        result = run_bootstrap(target_root=str(self.target), apply=True)
        self.assertEqual(result.status, "ok")

        etc_dir = self.target / "etc/verny/kso"

        # .example files exist
        self.assertTrue((etc_dir / "kso-state-adapter.env.example").is_file())
        self.assertTrue((etc_dir / "kso-sidecar.env.example").is_file())
        self.assertTrue((etc_dir / "kso-player.env.example").is_file())

        # Real .env files do NOT exist
        self.assertFalse((etc_dir / "kso-state-adapter.env").exists(),
                         "Real env must NOT be created by bootstrap")
        self.assertFalse((etc_dir / "kso-sidecar.env").exists())
        self.assertFalse((etc_dir / "kso-player.env").exists())

    def test_preflight_with_missing_env_does_not_crash(self):
        """Preflight must handle missing env files gracefully — no traceback."""
        run_bootstrap(target_root=str(self.target), apply=True)
        _create_player_shell(self.target)

        # No real env files — only .example from bootstrap
        pf_result = run_preflight(target_root=str(self.target))

        # Must not crash — status may be ERROR (missing dirs + env) or WARNING
        self.assertIn(pf_result.status, (STATUS_WARNING, STATUS_ERROR))

        # Env files are missing
        self.assertFalse(pf_result.sidecar_env_present)
        self.assertFalse(pf_result.player_env_present)
        self.assertFalse(pf_result.state_adapter_env_present)

        _assert_safe(self, format_preflight_result(pf_result))

    def test_preflight_with_missing_env_output_safe(self):
        """Preflight output must not expose secrets when env files missing."""
        run_bootstrap(target_root=str(self.target), apply=True)
        _create_player_shell(self.target)

        pf_result = run_preflight(target_root=str(self.target))
        output = format_preflight_result(pf_result)

        # Warnings about missing env allowed, but no values
        self.assertNotIn("CHANGE_ME", output)
        self.assertNotIn("secret", output.lower())
        _assert_safe(self, output)


# ══════════════════════════════════════════════════════════════════════
# Cross-cutting safety assertions
# ══════════════════════════════════════════════════════════════════════

class TestStagingScenarioSafety(unittest.TestCase):
    """Security invariants across all scenarios."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kso_ss_"))
        self.target = self.tmp / "staging-root"

    def tearDown(self):
        _shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_systemctl_calls_in_code(self):
        """Test file must not contain systemctl calls (outside FORBIDDEN set)."""
        src = Path(__file__).read_text()
        lines = src.split("\n")
        code_lines = []
        in_docstring = False
        skip_forbidden = False
        skip_assert_safe = False
        for line in lines:
            stripped = line.strip()
            # Track docstrings
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue
            # Skip the FORBIDDEN constant definition
            if "FORBIDDEN = frozenset({" in stripped:
                skip_forbidden = True
                continue
            if skip_forbidden:
                if stripped == "})":
                    skip_forbidden = False
                continue
            # Skip the _assert_safe function body (it checks FORBIDDEN)
            if stripped.startswith("def _assert_safe"):
                skip_assert_safe = True
                continue
            if skip_assert_safe:
                # _assert_safe ends at an unindented line
                if stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
                    skip_assert_safe = False
                    code_lines.append(line)
                continue
            code_lines.append(line)
        code = "\n".join(code_lines)

        for banned in ("systemctl start", "systemctl enable",
                        "systemctl restart", "daemon-reload"):
            self.assertNotIn(banned, code,
                             f"Test code must not call {banned}")

    def test_no_real_ukm4_paths(self):
        """Test must not reference Windows paths (outside FORBIDDEN set)."""
        src = Path(__file__).read_text().lower()
        lines = src.split("\n")
        filtered = []
        skip_forbidden = False
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if "forbidden = frozenset({" in stripped and "forbidden" in stripped:
                skip_forbidden = True
                continue
            if skip_forbidden:
                if stripped == "})":
                    skip_forbidden = False
                continue
            filtered.append(line)
        code = "\n".join(filtered)

        self.assertNotIn("C:\\\\", code)
        self.assertNotIn("programdata", code)
        self.assertNotIn(".msi", code)

    def test_no_receipt_payment_pii(self):
        """Test must not read receipt/payment/PII data (outside FORBIDDEN set)."""
        src = Path(__file__).read_text()
        lines = src.split("\n")
        filtered = []
        skip_forbidden = False
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if "FORBIDDEN = frozenset({" in stripped:
                skip_forbidden = True
                continue
            if skip_forbidden:
                if stripped == "})":
                    skip_forbidden = False
                continue
            filtered.append(line)
        code = "\n".join(filtered).lower()
        self.assertNotIn("fiscal_data", code)
        self.assertNotIn("card_number", code)
        self.assertNotIn("payment_card", code)

    def test_bootstrap_preserves_existing_env(self):
        """Bootstrap must not overwrite real .env files."""
        run_bootstrap(target_root=str(self.target), apply=True)

        etc_dir = self.target / "etc/verny/kso"
        # Create a real env file manually
        (etc_dir / "kso-sidecar.env").write_text(
            "VERNY_KSO_BACKEND_URL=https://real.prod.example\n"
            "VERNY_KSO_DEVICE_CODE=REAL_DEVICE\n"
            "VERNY_KSO_DEVICE_SECRET=REAL_SECRET\n"
        )
        original = (etc_dir / "kso-sidecar.env").read_text()

        # Apply bootstrap again
        result = run_bootstrap(target_root=str(self.target), apply=True)
        self.assertEqual((etc_dir / "kso-sidecar.env").read_text(), original,
                         "Bootstrap must not overwrite existing env")
        self.assertGreaterEqual(result.env_existing_count, 1)

        _assert_safe(self, format_bootstrap_result(result))

    def test_static_unknown_is_default(self):
        """Verify static unknown is the safe default in env example."""
        env_example = _INFRA_DIR / "env-examples" / "kso-state-adapter.env.example"
        content = env_example.read_text()

        self.assertIn("VERNY_KSO_STATE_SOURCE=static", content)
        self.assertIn("VERNY_KSO_STATIC_STATE=unknown", content)
        self.assertNotIn("VERNY_KSO_STATIC_STATE=idle", content)


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
