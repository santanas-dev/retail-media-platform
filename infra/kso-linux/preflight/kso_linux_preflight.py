#!/usr/bin/env python3
"""KSO Linux Deployment Preflight Validator.

Read-only readiness check. Never modifies the system, never starts services.

Usage:
    # Staging:
    python3 kso_linux_preflight.py --target-root /tmp/kso-install-root

    # Production:
    python3 kso_linux_preflight.py --target-root /

NEVER: systemctl start, enable, restart, daemon-reload.
"""

import argparse
import os as _os
import re as _re
import sys as _sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# Try importing constants from bootstrap; fall back to inline defs
try:
    from kso_linux_bootstrap import KSO_PATHS, _resolve_target
except ImportError:
    KSO_PATHS = {
        "opt": "/opt/verny/kso",
        "etc": "/etc/verny/kso",
        "var_lib": "/var/lib/verny/kso",
        "run": "/run/verny/kso",
        "var_log": "/var/log/verny/kso",
        "systemd": "/etc/systemd/system",
    }

    def _resolve_target(target_root: str, kso_path: str) -> Path:
        tr = Path(target_root)
        return (tr / kso_path.lstrip("/")).resolve()


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_WARNING = "warning"

READONLY_DIRS = ("opt",)  # /opt/verny/kso — source
WRITABLE_DIRS = ("var_lib", "run", "var_log")  # must be writable
ALWAYS_CHECK = ("opt", "etc", "var_lib", "run", "var_log", "systemd")

SYSTEMD_UNITS = ("kso-sidecar.service", "kso-player.service")

SIDECAR_ENV_NAME = "kso-sidecar.env"
PLAYER_ENV_NAME = "kso-player.env"

SIDECAR_ENV_REQUIRED_KEYS = frozenset({
    "VERNY_KSO_BACKEND_URL",
    "VERNY_KSO_DEVICE_CODE",
    "VERNY_KSO_DEVICE_SECRET",
})

PLAYER_ENV_REQUIRED_KEYS = frozenset({
    "VERNY_KSO_CHROMIUM_BIN",
})

PLAYER_SHELL_REQUIRED_FILES = (
    "index.html",
    "styles.css",
    "player.js",
    "bootstrap.js",
    "bootstrap_snapshot.js",
)

FORBIDDEN_IN_OUTPUT = frozenset({
    "secret", "token", "password", "authorization",
    "bearer", "backend_url", "device_code", "api_key",
    "stacktrace", "traceback",
    "CHANGE_ME", "C:\\", "ProgramData", ".msi",
})

_PLACEHOLDER_PATTERNS = ("CHANGE_ME", "CHANGE...", "CHANGE_ME_SECRET")


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _parse_env(content: str) -> dict:
    """Parse env file content into key-value dict."""
    result = {}
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        result[key] = value
    return result


def _has_placeholders(value: str) -> bool:
    for p in _PLACEHOLDER_PATTERNS:
        if p in value:
            return True
    return False


def _check_writable(path: Path) -> bool:
    try:
        test_file = path / ".kso_preflight_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PreflightResult:
    """Safe preflight result. Never contains secrets/values."""

    status: str = STATUS_OK
    target_root: str = "/"
    target_root_mode: str = "production"

    # ── Directory checks ─────────────────────────────────────────────
    directories_total: int = 0
    directories_ok: int = 0
    directories_missing: int = 0
    directories_not_writable: int = 0

    # ── Systemd unit checks ─────────────────────────────────────────
    systemd_units_total: int = 2
    systemd_units_ok: int = 0
    systemd_units_missing: int = 0
    systemd_units_verify_ok: bool = False
    systemd_units_verify_status: str = "skipped"

    # ── Env checks ──────────────────────────────────────────────────
    sidecar_env_present: bool = False
    sidecar_env_has_placeholders: bool = True
    sidecar_env_missing_keys_count: int = 0
    sidecar_env_backend_https: bool = True

    player_env_present: bool = False
    player_env_has_placeholders: bool = True
    player_env_missing_keys_count: int = 0

    # ── Chromium check ──────────────────────────────────────────────
    chromium_configured: bool = False
    chromium_bin_checked: bool = False

    # ── Player shell check ──────────────────────────────────────────
    player_shell_ok: bool = False
    player_shell_missing_files_count: int = 0

    # ── CLI checks ──────────────────────────────────────────────────
    cli_sidecar_ok: bool = False
    cli_player_ok: bool = False

    # ── Health path check ───────────────────────────────────────────
    health_path_writable: bool = False

    # ── Summary ─────────────────────────────────────────────────────
    checks_passed: int = 0
    checks_total: int = 0
    warnings_count: int = 0
    errors_count: int = 0

    warnings: List[str] = field(default_factory=list)
    reason: str = "preflight_completed"

    def __repr__(self) -> str:
        return (
            f"PreflightResult("
            f"status={self.status!r}, "
            f"target_root_mode={self.target_root_mode!r}, "
            f"directories_ok={self.directories_ok}/{self.directories_total}, "
            f"systemd_units_ok={self.systemd_units_ok}/{self.systemd_units_total}, "
            f"sidecar_env_present={self.sidecar_env_present}, "
            f"player_env_present={self.player_env_present}, "
            f"chromium_configured={self.chromium_configured}, "
            f"player_shell_ok={self.player_shell_ok}, "
            f"cli_sidecar={self.cli_sidecar_ok}, "
            f"cli_player={self.cli_player_ok}, "
            f"warnings_count={self.warnings_count}, "
            f"errors_count={self.errors_count}, "
            f"reason={self.reason!r})"
        )


def format_preflight_result(result: PreflightResult) -> str:
    """Safe formatted output. No secrets, no values."""
    lines = [
        f"status: {result.status}",
        f"target_root_mode: {result.target_root_mode}",
        "",
        f"directories_total: {result.directories_total}",
        f"directories_ok: {result.directories_ok}",
        f"directories_missing: {result.directories_missing}",
        f"directories_not_writable: {result.directories_not_writable}",
        "",
        f"systemd_units_total: {result.systemd_units_total}",
        f"systemd_units_ok: {result.systemd_units_ok}",
        f"systemd_units_missing: {result.systemd_units_missing}",
        f"systemd_units_verify_ok: {str(result.systemd_units_verify_ok).lower()}",
        f"systemd_units_verify_status: {result.systemd_units_verify_status}",
        "",
        f"sidecar_env_present: {str(result.sidecar_env_present).lower()}",
        f"sidecar_env_has_placeholders: {str(result.sidecar_env_has_placeholders).lower()}",
        f"sidecar_env_missing_keys_count: {result.sidecar_env_missing_keys_count}",
        f"sidecar_env_backend_https: {str(result.sidecar_env_backend_https).lower()}",
        "",
        f"player_env_present: {str(result.player_env_present).lower()}",
        f"player_env_has_placeholders: {str(result.player_env_has_placeholders).lower()}",
        f"player_env_missing_keys_count: {result.player_env_missing_keys_count}",
        "",
        f"chromium_configured: {str(result.chromium_configured).lower()}",
        f"chromium_bin_checked: {str(result.chromium_bin_checked).lower()}",
        "",
        f"player_shell_ok: {str(result.player_shell_ok).lower()}",
        f"player_shell_missing_files_count: {result.player_shell_missing_files_count}",
        "",
        f"cli_sidecar_ok: {str(result.cli_sidecar_ok).lower()}",
        f"cli_player_ok: {str(result.cli_player_ok).lower()}",
        "",
        f"health_path_writable: {str(result.health_path_writable).lower()}",
        "",
        f"checks_passed: {result.checks_passed}",
        f"checks_total: {result.checks_total}",
        f"warnings_count: {result.warnings_count}",
        f"errors_count: {result.errors_count}",
        f"reason: {result.reason}",
    ]
    if result.warnings:
        lines.append("warnings:")
        for w in result.warnings:
            lines.append(f"  - {w}")

    output = "\n".join(lines)
    lower = output.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            raise ValueError(f"Output contains forbidden '{fb}'")
    return output


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_preflight(
    target_root: str = "/tmp/kso-install-root",
    verify_units: bool = False,
    verify_cli: bool = False,
    command_runner: Optional[Callable[[List[str]], Tuple[int, str, str]]] = None,
) -> PreflightResult:
    """Run KSO Linux deployment preflight check.

    Readonly. Never modifies files, never starts services.

    Args:
        target_root: Deployment root.
        verify_units: Run systemd-analyze verify.
        verify_cli: Run CLI --help commands.
        command_runner: Injectable command runner.

    Returns:
        PreflightResult — always safe, never raises.
    """
    result = PreflightResult(
        target_root=target_root,
        target_root_mode="production" if target_root == "/" else "staging",
    )

    # ══════════════════════════════════════════════════════════════════
    # 1. Directory checks
    # ══════════════════════════════════════════════════════════════════
    result.directories_total = len(ALWAYS_CHECK)

    for key in ALWAYS_CHECK:
        d = _resolve_target(target_root, KSO_PATHS[key])
        if not d.exists() or not d.is_dir():
            result.directories_missing += 1
            result.warnings.append(f"Directory missing")
            continue
        result.directories_ok += 1

        # Writable check for mutable dirs
        if key in WRITABLE_DIRS:
            if not _check_writable(d):
                result.directories_not_writable += 1
                result.warnings.append("Directory not writable")

    # ══════════════════════════════════════════════════════════════════
    # 2. Systemd unit checks
    # ══════════════════════════════════════════════════════════════════
    systemd_dir = _resolve_target(target_root, KSO_PATHS["systemd"])
    for unit in SYSTEMD_UNITS:
        unit_path = systemd_dir / unit
        if unit_path.is_file():
            result.systemd_units_ok += 1
        else:
            result.systemd_units_missing += 1
            result.warnings.append("Unit file missing")

    # ── Unit verify (injectable) ────────────────────────────────────
    if verify_units:
        runner = command_runner or _default_command_runner
        all_ok = True
        for unit in SYSTEMD_UNITS:
            unit_path = systemd_dir / unit
            if not unit_path.is_file():
                continue
            try:
                exit_code, _, _ = runner(
                    ["systemd-analyze", "verify", str(unit_path)]
                )
                if exit_code != 0:
                    all_ok = False
            except Exception:
                all_ok = False
                result.systemd_units_verify_status = "error"
        if all_ok:
            result.systemd_units_verify_ok = True
            result.systemd_units_verify_status = "ok"
        else:
            result.systemd_units_verify_status = "failed"
            result.warnings.append("systemd-analyze verify failed")

    # ══════════════════════════════════════════════════════════════════
    # 3. Env file checks
    # ══════════════════════════════════════════════════════════════════
    etc_dir = _resolve_target(target_root, KSO_PATHS["etc"])

    # ── Sidecar env ─────────────────────────────────────────────────
    sidecar_env = etc_dir / SIDECAR_ENV_NAME
    if sidecar_env.is_file():
        result.sidecar_env_present = True
        try:
            content = sidecar_env.read_text()
            env_vars = _parse_env(content)

            # Placeholders?
            has_any = False
            for val in env_vars.values():
                if _has_placeholders(val):
                    has_any = True
                    break
            result.sidecar_env_has_placeholders = has_any
            if has_any:
                result.warnings.append("Sidecar env contains placeholders")

            # Missing keys?
            missing = SIDECAR_ENV_REQUIRED_KEYS - set(env_vars.keys())
            result.sidecar_env_missing_keys_count = len(missing)
            if missing:
                result.warnings.append("Sidecar env missing required keys")

            # Backend URL HTTPS?
            backend = env_vars.get("VERNY_KSO_BACKEND_URL", "")
            if backend and not backend.startswith("https://"):
                result.sidecar_env_backend_https = False
                result.warnings.append("Backend URL is not HTTPS")
            if backend == "https://backend.example":
                result.warnings.append("Backend URL still uses example placeholder")
        except Exception:
            result.warnings.append("Cannot read sidecar env")
    else:
        result.sidecar_env_present = False
        result.warnings.append("Sidecar env file not found")

    # ── Player env ──────────────────────────────────────────────────
    player_env = etc_dir / PLAYER_ENV_NAME
    if player_env.is_file():
        result.player_env_present = True
        try:
            content = player_env.read_text()
            env_vars = _parse_env(content)

            has_any = False
            for val in env_vars.values():
                if _has_placeholders(val):
                    has_any = True
                    break
            result.player_env_has_placeholders = has_any
            if has_any:
                result.warnings.append("Player env contains placeholders")

            missing = PLAYER_ENV_REQUIRED_KEYS - set(env_vars.keys())
            result.player_env_missing_keys_count = len(missing)
            if missing:
                result.warnings.append("Player env missing required keys")

            # Chromium configured?
            chromium_bin = env_vars.get("VERNY_KSO_CHROMIUM_BIN", "")
            if chromium_bin and chromium_bin != "CHANGE_ME":
                result.chromium_configured = True
        except Exception:
            result.warnings.append("Cannot read player env")
    else:
        result.player_env_present = False
        result.warnings.append("Player env file not found")

    # ══════════════════════════════════════════════════════════════════
    # 4. Chromium check (via env — no launch)
    # ══════════════════════════════════════════════════════════════════
    if result.chromium_configured and verify_cli and command_runner:
        try:
            exit_code, _, _ = command_runner(["which", "chromium"])
            result.chromium_bin_checked = (exit_code == 0)
            if not result.chromium_bin_checked:
                result.warnings.append("Chromium binary not found in PATH")
        except Exception:
            result.warnings.append("Cannot check Chromium binary")

    # ══════════════════════════════════════════════════════════════════
    # 5. Player shell check
    # ══════════════════════════════════════════════════════════════════
    player_shell_dir = _resolve_target(target_root, KSO_PATHS["opt"]) / "player_shell"
    if player_shell_dir.is_dir():
        missing_count = 0
        for fname in PLAYER_SHELL_REQUIRED_FILES:
            if not (player_shell_dir / fname).is_file():
                missing_count += 1
        result.player_shell_missing_files_count = missing_count
        if missing_count == 0:
            result.player_shell_ok = True
        else:
            result.warnings.append("Player shell missing required files")
    else:
        result.player_shell_missing_files_count = len(PLAYER_SHELL_REQUIRED_FILES)
        result.warnings.append("Player shell directory not found")

    # ══════════════════════════════════════════════════════════════════
    # 6. Health path writable
    # ══════════════════════════════════════════════════════════════════
    run_dir = _resolve_target(target_root, KSO_PATHS["run"])
    if run_dir.exists() and run_dir.is_dir():
        result.health_path_writable = _check_writable(run_dir)
        if not result.health_path_writable:
            result.warnings.append("Health directory not writable")

    # ══════════════════════════════════════════════════════════════════
    # 7. CLI checks (injectable)
    # ══════════════════════════════════════════════════════════════════
    if verify_cli and command_runner:
        # Sidecar CLI
        try:
            exit_code, _, _ = command_runner(
                ["python3", "-m", "kso_sidecar_agent.cli", "sidecar-daemon", "--help"]
            )
            if exit_code == 0:
                result.cli_sidecar_ok = True
            else:
                result.warnings.append("Sidecar CLI help failed")
        except Exception:
            result.warnings.append("Sidecar CLI not accessible")

        # Player CLI
        try:
            exit_code, _, _ = command_runner(
                ["python3", "-m", "kso_player.cli", "runtime-daemon", "--help"]
            )
            if exit_code == 0:
                result.cli_player_ok = True
            else:
                result.warnings.append("Player CLI help failed")
        except Exception:
            result.warnings.append("Player CLI not accessible")

    # ══════════════════════════════════════════════════════════════════
    # Summary
    # ══════════════════════════════════════════════════════════════════
    result.warnings_count = len(result.warnings)

    # Checks passed = OK items
    passed = result.directories_ok

    # Each systemd unit counts as one check
    passed += result.systemd_units_ok
    total_checks = result.directories_total + result.systemd_units_total

    # Env checks
    if result.sidecar_env_present:
        passed += 1
    total_checks += 1
    if result.player_env_present:
        passed += 1
    total_checks += 1

    # Player shell
    total_checks += 1
    if result.player_shell_ok:
        passed += 1

    # Health
    total_checks += 1
    if result.health_path_writable:
        passed += 1

    # CLI
    if verify_cli:
        total_checks += 2
        if result.cli_sidecar_ok:
            passed += 1
        if result.cli_player_ok:
            passed += 1

    result.checks_passed = passed
    result.checks_total = total_checks

    missing = result.directories_missing + result.systemd_units_missing
    result.errors_count = missing

    if result.errors_count > 0:
        result.status = STATUS_ERROR
        result.reason = "preflight_failed"
    elif result.warnings_count > 0:
        result.status = STATUS_WARNING
        result.reason = "preflight_warnings"
    else:
        result.status = STATUS_OK
        result.reason = "preflight_passed"

    return result


# ══════════════════════════════════════════════════════════════════════
# Default command runner
# ══════════════════════════════════════════════════════════════════════

def _default_command_runner(cmd: List[str]) -> Tuple[int, str, str]:
    import subprocess
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stdout, proc.stderr


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kso-linux-preflight",
        description="KSO Linux deployment preflight validator",
    )
    parser.add_argument(
        "--target-root", type=str, default="/tmp/kso-install-root",
        help="Deployment root (/tmp/... for staging, / for production)",
    )
    parser.add_argument(
        "--verify-units", action="store_true", default=False,
        help="Run systemd-analyze verify on units",
    )
    parser.add_argument(
        "--verify-cli", action="store_true", default=False,
        help="Run CLI --help commands",
    )

    args = parser.parse_args()

    result = run_preflight(
        target_root=args.target_root,
        verify_units=args.verify_units,
        verify_cli=args.verify_cli,
    )

    print(format_preflight_result(result))
    if result.status == STATUS_ERROR:
        _sys.exit(1)
    _sys.exit(0)


if __name__ == "__main__":
    main()
