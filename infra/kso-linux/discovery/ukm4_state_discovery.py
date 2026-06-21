"""UKM 4 State Source Discovery — Safe Readonly Script.

Discovers available UKM 4 state sources on a Linux KSO terminal
WITHOUT reading checks, payments, SKUs, personal data, or fiscal data.

Usage:
    python3 ukm4_state_discovery.py --dry-run          # plan only (safe default)
    python3 ukm4_state_discovery.py --process-name-pattern supermag
    python3 ukm4_state_discovery.py --service-name supermag-kiosk
    python3 ukm4_state_discovery.py --status-file /run/verny/kso/state/kso_state.json

Safety: readonly, no DB, no logs, no HTTP, no systemctl start/enable/restart.
"""

import argparse
import json as _json
import os as _os
import subprocess as _subprocess
import sys as _sys
from pathlib import Path
from typing import Dict, List, Optional

VERSION = "0.1.0"

# ══════════════════════════════════════════════════════════════════════
# Safe path allowlists
# ══════════════════════════════════════════════════════════════════════

STATUS_FILE_ALLOWLIST = frozenset({
    "/run/verny/kso",
    "/var/lib/verny/kso",
    "/opt/verny/kso",
})

# Patience: we only look at very specific things, never recursive
SAFE_DIRS = frozenset({
    "/run/verny/kso",
    "/var/lib/verny/kso",
    "/var/log/verny/kso",
    "/opt/verny/kso",
    "/etc/verny/kso",
})


def _in_allowlist(path_str: str, allowlist) -> bool:
    """Check if path or its parent is in allowlist."""
    if not path_str:
        return False
    p = Path(path_str).resolve()
    for allowed in allowlist:
        allowed_p = Path(allowed).resolve()
        try:
            p.relative_to(allowed_p)
            return True
        except ValueError:
            pass
    return False


# ══════════════════════════════════════════════════════════════════════
# Forbidden patterns in output
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_OUTPUT = frozenset({
    "receipt", "payment", "amount", "card", "phone", "email",
    "customer", "fiscal", "token", "secret", "password",
    "authorization", "stacktrace", "traceback",
    "sku", "product", "price", "discount", "tax",
    "pan", "bin", "cvv",
})


def _validate_output_safe(data: dict) -> List[str]:
    """Return list of forbidden strings found. Empty = clean."""
    text = _json.dumps(data).lower()
    hits = []
    for fb in FORBIDDEN_OUTPUT:
        if fb in text:
            hits.append(fb)
    return hits


# ══════════════════════════════════════════════════════════════════════
# Checkers — each is safe and readonly
# ══════════════════════════════════════════════════════════════════════

def _check_process(pattern: Optional[str]) -> dict:
    """Check for a process matching pattern (name only, not full cmdline)."""
    if not pattern:
        return {"checked": False, "reason": "no_pattern_provided"}
    try:
        result = _subprocess.run(
            ["pgrep", "-l", pattern],
            capture_output=True, text=True, timeout=5,
        )
        detected = result.returncode == 0
        # Safe: return count, not process names (may contain secrets)
        line_count = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
        return {
            "checked": True,
            "process_detected": detected,
            "process_count": line_count if detected else 0,
            "reason": "ok",
        }
    except FileNotFoundError:
        return {"checked": True, "process_detected": False,
                "reason": "pgrep_not_found"}
    except Exception as e:
        return {"checked": True, "process_detected": False,
                "reason": "check_error"}


def _check_service(name: Optional[str]) -> dict:
    """Check for a systemd service (using systemctl is-active — readonly)."""
    if not name:
        return {"checked": False, "reason": "no_service_name_provided"}
    try:
        result = _subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            capture_output=True, timeout=5,
        )
        active = result.returncode == 0
        return {
            "checked": True,
            "service_detected": active,
            "service_active": active,
            "reason": "ok",
        }
    except FileNotFoundError:
        return {"checked": True, "service_detected": False,
                "reason": "systemctl_not_found"}
    except Exception as e:
        return {"checked": True, "service_detected": False,
                "reason": "check_error"}


def _check_status_file(path: Optional[str]) -> dict:
    """Check for existence of a status file (does NOT read content)."""
    if not path:
        return {"checked": False, "reason": "no_status_file_provided"}
    if not _in_allowlist(path, STATUS_FILE_ALLOWLIST):
        return {
            "checked": True,
            "status_file_present": False,
            "reason": "path_outside_allowlist",
        }
    try:
        exists = Path(path).is_file()
        return {
            "checked": True,
            "status_file_present": exists,
            "reason": "ok" if exists else "file_not_found",
        }
    except Exception:
        return {
            "checked": True,
            "status_file_present": False,
            "reason": "check_error",
        }


def _check_environment() -> dict:
    """Safe environment check: OS, python, systemd availability."""
    info = {
        "os": _os.uname().sysname,
        "python_version": _sys.version.split()[0],
        "systemctl_available": False,
    }
    try:
        _subprocess.run(["systemctl", "--version"], capture_output=True,
                        timeout=3, check=False)
        info["systemctl_available"] = True
    except FileNotFoundError:
        pass
    for fb in FORBIDDEN_OUTPUT:
        if fb in _json.dumps(info).lower():
            pass  # Should never happen with these safe keys
    return info


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def run_discovery(
    dry_run: bool = True,
    process_name_pattern: Optional[str] = None,
    service_name: Optional[str] = None,
    status_file: Optional[str] = None,
    output_json: bool = False,
) -> dict:
    """Run safe UKM 4 state source discovery.

    Returns a dict with ONLY safe keys.
    Never reads checks, payments, SKUs, fiscal data, or personal data.
    """

    checks_planned: List[str] = []
    results: Dict[str, dict] = {}
    warnings: List[str] = []

    # ── Plan ──────────────────────────────────────────────────────
    checks_planned.append("environment")
    if process_name_pattern:
        checks_planned.append("process")
    if service_name:
        checks_planned.append("service")
    if status_file:
        checks_planned.append("status_file")

    if dry_run:
        return {
            "status": "dry_run",
            "checks_planned": checks_planned,
            "checks_completed": 0,
            "results": {},
            "warnings": warnings,
            "reason": "dry_run_no_actions_performed",
        }

    # ── Execute ───────────────────────────────────────────────────
    completed = 0

    # Environment (always safe)
    env = _check_environment()
    results["environment"] = env
    completed += 1

    # Process
    if process_name_pattern:
        proc = _check_process(process_name_pattern)
        results["process"] = proc
        completed += 1
        if not proc.get("process_detected"):
            warnings.append(f"process_not_detected: {process_name_pattern}")
    else:
        results["process"] = {"checked": False, "reason": "skipped"}

    # Service
    if service_name:
        svc = _check_service(service_name)
        results["service"] = svc
        completed += 1
        if not svc.get("service_detected"):
            warnings.append(f"service_not_detected: {service_name}")
    else:
        results["service"] = {"checked": False, "reason": "skipped"}

    # Status file
    if status_file:
        sf = _check_status_file(status_file)
        results["status_file"] = sf
        completed += 1
        if not sf.get("status_file_present"):
            warnings.append(f"status_file_not_present: {status_file}")
    else:
        results["status_file"] = {"checked": False, "reason": "skipped"}

    output = {
        "status": "completed",
        "checks_planned": checks_planned,
        "checks_completed": completed,
        "warnings_count": len(warnings),
        "results": results,
        "reason": "ok",
    }
    if warnings:
        output["warnings"] = warnings

    # ── Safety scan ───────────────────────────────────────────────
    forbidden = _validate_output_safe(output)
    if forbidden:
        return {
            "status": "error",
            "reason": "forbidden_data_detected_in_output",
            "details": f"forbidden_keys: {','.join(sorted(forbidden))}",
        }

    return output


def format_result(result: dict) -> str:
    """Safe formatted output."""
    if result.get("status") == "error":
        return f"status: error\nreason: {result.get('reason', 'unknown')}"
    return _json.dumps(result, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ukm4-state-discovery",
        description="Safe readonly UKM 4 state source discovery",
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Plan only, no actions (default: True)")
    parser.add_argument("--execute", dest="dry_run", action="store_false",
                        help="Execute checks (off by default)")
    parser.add_argument("--process-name-pattern", type=str, default=None,
                        help="Process name pattern (e.g. 'supermag')")
    parser.add_argument("--service-name", type=str, default=None,
                        help="Systemd service name (e.g. 'supermag-kiosk')")
    parser.add_argument("--status-file", type=str, default=None,
                        help="Status file path to check existence for")
    parser.add_argument("--output-json", action="store_true", default=False,
                        help="Output raw JSON")
    parser.add_argument("--version", action="store_true",
                        help="Show version and exit")

    args = parser.parse_args()

    if args.version:
        print(f"ukm4-state-discovery {VERSION}")
        return

    result = run_discovery(
        dry_run=args.dry_run,
        process_name_pattern=args.process_name_pattern,
        service_name=args.service_name,
        status_file=args.status_file,
        output_json=args.output_json,
    )

    print(format_result(result))

    if result.get("status") == "error":
        _sys.exit(1)


if __name__ == "__main__":
    main()
