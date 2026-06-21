#!/usr/bin/env python3
"""KSO Linux Safe Bootstrap Installer.

Prepares file system layout for KSO production deployment.
By default, runs in dry-run mode — NO changes to the system.

Usage:
    # Dry-run (safe, no changes):
    python3 kso_linux_bootstrap.py --dry-run

    # Staging target-root:
    python3 kso_linux_bootstrap.py --apply --target-root /tmp/kso-install-root

    # Production (requires explicit danger flag):
    python3 kso_linux_bootstrap.py --apply --target-root / \
        --i-understand-this-writes-to-system-paths

NEVER: systemctl start, enable, restart, daemon-reload.
"""

import argparse
import json as _json
import os as _os
import shutil as _shutil
import sys as _sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

# ── Project paths relative to this script ──────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_INFRA_DIR = _SCRIPT_DIR.parent
_SYSTEMD_SRC = _INFRA_DIR / "systemd"
_ENV_SRC = _INFRA_DIR / "env-examples"
_README_SRC = _INFRA_DIR / "README.md"

# ── KSO Linux paths ────────────────────────────────────────────────────
KSO_PATHS = {
    "opt": "/opt/verny/kso",
    "etc": "/etc/verny/kso",
    "var_lib": "/var/lib/verny/kso",
    "run": "/run/verny/kso",
    "var_log": "/var/log/verny/kso",
    "systemd": "/etc/systemd/system",
}

ALLOWED_OUTPUT_PATHS = frozenset({
    "/opt/verny/kso",
    "/etc/verny/kso",
    "/var/lib/verny/kso",
    "/run/verny/kso",
    "/var/log/verny/kso",
    "/etc/systemd/system/kso-player.service",
    "/etc/systemd/system/kso-sidecar.service",
})

FORBIDDEN_IN_OUTPUT = frozenset({
    "secret", "token", "password", "authorization",
    "bearer", "backend_url", "device_code", "api_key",
    "stacktrace", "traceback",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class BootstrapResult:
    """Safe bootstrap result. Never contains secrets/paths beyond allowed."""

    status: str = "ok"                    # ok | error | warning
    dry_run: bool = True
    applied: bool = False
    target_root: str = "/"
    production_mode: bool = False

    directories_planned: int = 0
    directories_created: int = 0
    directories_skipped: int = 0

    files_planned: int = 0
    files_copied: int = 0
    files_skipped: int = 0

    env_existing_count: int = 0
    systemd_units_verified: bool = False
    unit_verify_status: str = "skipped"

    warnings: List[str] = field(default_factory=list)
    warnings_count: int = 0

    reason: str = "dry_run_completed"

    def __post_init__(self):
        self.warnings_count = len(self.warnings)

    def __repr__(self) -> str:
        return (
            f"BootstrapResult("
            f"status={self.status!r}, "
            f"dry_run={self.dry_run}, "
            f"applied={self.applied}, "
            f"target_root={self.target_root!r}, "
            f"directories_planned={self.directories_planned}, "
            f"directories_created={self.directories_created}, "
            f"files_planned={self.files_planned}, "
            f"files_copied={self.files_copied}, "
            f"env_existing_count={self.env_existing_count}, "
            f"systemd_units_verified={self.systemd_units_verified}, "
            f"warnings_count={self.warnings_count}, "
            f"reason={self.reason!r})"
        )


def format_bootstrap_result(result: BootstrapResult) -> str:
    """Safe formatted output. No secrets, no paths beyond allowed."""
    lines = [
        f"status: {result.status}",
        f"dry_run: {str(result.dry_run).lower()}",
        f"applied: {str(result.applied).lower()}",
        f"target_root: {result.target_root}",
        f"production_mode: {str(result.production_mode).lower()}",
        f"directories_planned: {result.directories_planned}",
        f"directories_created: {result.directories_created}",
        f"directories_skipped: {result.directories_skipped}",
        f"files_planned: {result.files_planned}",
        f"files_copied: {result.files_copied}",
        f"files_skipped: {result.files_skipped}",
        f"env_existing_count: {result.env_existing_count}",
        f"systemd_units_verified: {str(result.systemd_units_verified).lower()}",
        f"unit_verify_status: {result.unit_verify_status}",
        f"warnings_count: {result.warnings_count}",
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
# Core
# ══════════════════════════════════════════════════════════════════════

def _resolve_target(target_root: str, kso_path: str) -> Path:
    """Resolve a KSO path under target_root."""
    tr = Path(target_root)
    # Strip leading slash to join under target_root
    rel = kso_path.lstrip("/")
    return (tr / rel).resolve()


def _check_path_safety(target_root: Path) -> Optional[str]:
    """Check target_root is not doing something unsafe."""
    if str(target_root) == "/":
        return None  # Requires explicit flag, handled elsewhere
    # Must be under /tmp/ for safety
    resolved = str(target_root.resolve())
    if not resolved.startswith("/tmp/"):
        return f"Unsafe target_root: {resolved} (must be /tmp/... or / with danger flag)"
    return None


def _collect_plan(target_root: str, result: BootstrapResult):
    """Collect directories and files to create without making changes."""
    dirs = []
    for key in ("opt", "etc", "var_lib", "run", "var_log", "systemd"):
        dirs.append(_resolve_target(target_root, KSO_PATHS[key]))

    files = [
        (_SYSTEMD_SRC / "kso-sidecar.service",
         _resolve_target(target_root, KSO_PATHS["systemd"]) / "kso-sidecar.service"),
        (_SYSTEMD_SRC / "kso-player.service",
         _resolve_target(target_root, KSO_PATHS["systemd"]) / "kso-player.service"),
    ]

    env_files = [
        (_ENV_SRC / "kso-sidecar.env.example",
         _resolve_target(target_root, KSO_PATHS["etc"]) / "kso-sidecar.env.example"),
        (_ENV_SRC / "kso-player.env.example",
         _resolve_target(target_root, KSO_PATHS["etc"]) / "kso-player.env.example"),
    ]

    return dirs, files, env_files


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_bootstrap(
    target_root: str = "/tmp/kso-install-root",
    apply: bool = False,
    production_confirm: bool = False,
    verify_units: bool = False,
    command_runner: Optional[Callable[[List[str]], tuple[int, str, str]]] = None,
    validate_env: Optional[str] = None,
) -> BootstrapResult:
    """Run KSO Linux bootstrap installer.

    Args:
        target_root: Install root. /tmp/... for staging, / for production.
        apply: Actually make changes (default dry-run).
        production_confirm: Required when target_root=/.
        verify_units: Run systemd-analyze verify.
        command_runner: Injectable command runner for unit verify.
        validate_env: Optional path to env file for validation.

    Returns:
        BootstrapResult — always safe, never raises.
    """
    result = BootstrapResult(
        dry_run=not apply,
        applied=False,
        target_root=target_root,
        production_mode=(target_root == "/"),
    )

    # ── Production safety gate ──────────────────────────────────────
    if target_root == "/" and apply and not production_confirm:
        result.status = "error"
        result.reason = "production_requires_confirm"
        result.warnings.append(
            "Production target_root=/ requires --apply AND "
            "--i-understand-this-writes-to-system-paths"
        )
        return result

    if target_root == "/" and not apply:
        result.status = "ok"
        result.reason = "dry_run_completed"
        # Still show plan for dry-run on production root
        dirs, files, env_files = _collect_plan(target_root, result)
        result.directories_planned = len(dirs)
        result.files_planned = len(files) + len(env_files)
        return result

    # ── Safety check for non-production target ─────────────────────
    if target_root != "/":
        safety = _check_path_safety(Path(target_root))
        if safety:
            result.status = "error"
            result.reason = "unsafe_target_root"
            result.warnings.append(safety)
            return result

    # ── Collect plan ───────────────────────────────────────────────
    dirs, files, env_files = _collect_plan(target_root, result)
    result.directories_planned = len(dirs)
    result.files_planned = len(files) + len(env_files)

    if not apply:
        result.reason = "dry_run_completed"
        return result

    # ══════════════════════════════════════════════════════════════════
    # Apply mode
    # ══════════════════════════════════════════════════════════════════

    # ── Create directories ──────────────────────────────────────────
    for d in dirs:
        try:
            if d.exists():
                if d.is_dir():
                    result.directories_skipped += 1
                else:
                    result.warnings.append(f"Path exists but is not a directory")
            else:
                d.mkdir(parents=True, exist_ok=True)
                result.directories_created += 1
        except OSError as e:
            result.warnings.append(f"Cannot create directory")
            continue

    # ── Copy systemd unit files ─────────────────────────────────────
    for src, dst in files:
        try:
            if dst.exists():
                result.warnings.append("Unit file already exists — not overwritten")
                result.files_skipped += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(str(src), str(dst))
            result.files_copied += 1
        except OSError:
            result.warnings.append("Cannot copy unit file")
            continue

    # ── Copy env examples (only as .example, never overwrite) ──────
    for src, dst in env_files:
        try:
            # Check if real env exists (without .example suffix)
            real_env = Path(str(dst).replace(".env.example", ".env"))
            if real_env.exists():
                result.env_existing_count += 1
                # Still copy .example if it doesn't exist
                if dst.exists():
                    result.files_skipped += 1
                    continue
            if dst.exists():
                result.files_skipped += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(str(src), str(dst))
            result.files_copied += 1
        except OSError:
            result.warnings.append("Cannot copy env example")
            continue

    # ── Env validation ──────────────────────────────────────────────
    if validate_env:
        try:
            vp = Path(validate_env)
            if vp.exists():
                content = vp.read_text()
                if "CHANGE_ME" in content or "CHANGE..." in content or "CHANGE_ME_SECRET" in content:
                    result.warnings.append(
                        "Env file contains CHANGE_ME placeholders — fill real values "
                        "before production"
                    )
                if "Bearer " in content:
                    result.warnings.append("Env file may contain real token")
                result.env_existing_count += 1
            else:
                result.warnings.append("Env file not found for validation")
        except Exception:
            result.warnings.append("Cannot read env file for validation")

    # ── Systemd unit verify ─────────────────────────────────────────
    if verify_units:
        runner = command_runner or _default_command_runner
        sidecar_unit = _resolve_target(target_root, KSO_PATHS["systemd"]) / "kso-sidecar.service"
        player_unit = _resolve_target(target_root, KSO_PATHS["systemd"]) / "kso-player.service"

        all_ok = True
        for unit in [sidecar_unit, player_unit]:
            if not unit.exists():
                result.unit_verify_status = "missing"
                result.warnings.append("Unit file not found for verify")
                all_ok = False
                continue
            try:
                exit_code, stdout, stderr = runner(
                    ["systemd-analyze", "verify", str(unit)]
                )
                if exit_code != 0:
                    result.unit_verify_status = "failed"
                    result.warnings.append("systemd-analyze verify returned non-zero")
                    all_ok = False
            except Exception:
                result.unit_verify_status = "error"
                result.warnings.append("systemd-analyze verify failed")
                all_ok = False

        if all_ok:
            result.unit_verify_status = "ok"
            result.systemd_units_verified = True

    result.applied = True
    result.warnings_count = len(result.warnings)
    result.status = "ok" if result.warnings_count == 0 else "warning"
    result.reason = "applied" if result.warnings_count == 0 else "applied_with_warnings"
    return result


# ══════════════════════════════════════════════════════════════════════
# Default command runner
# ══════════════════════════════════════════════════════════════════════

def _default_command_runner(cmd: List[str]) -> tuple[int, str, str]:
    """Real command runner. Used only when systemd-analyze is available."""
    import subprocess
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stdout, proc.stderr


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kso-linux-bootstrap",
        description="KSO Linux safe bootstrap installer",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Plan only, no changes (default)",
    )
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Apply changes (with --target-root)",
    )
    parser.add_argument(
        "--target-root", type=str, default="/tmp/kso-install-root",
        help="Install root (/tmp/... for staging, / for production)",
    )
    parser.add_argument(
        "--i-understand-this-writes-to-system-paths",
        action="store_true", default=False,
        help="REQUIRED for production target-root=/",
    )
    parser.add_argument(
        "--verify-units", action="store_true", default=False,
        help="Run systemd-analyze verify on copied units",
    )
    parser.add_argument(
        "--validate-env", type=str, default=None,
        help="Path to env file for validation",
    )

    args = parser.parse_args()

    # --apply implies no --dry-run
    dry_run = not args.apply

    result = run_bootstrap(
        target_root=args.target_root,
        apply=args.apply,
        production_confirm=args.i_understand_this_writes_to_system_paths,
        verify_units=args.verify_units,
        validate_env=args.validate_env,
    )

    print(format_bootstrap_result(result))
    if result.status == "error":
        _sys.exit(1)
    _sys.exit(0)


if __name__ == "__main__":
    main()
