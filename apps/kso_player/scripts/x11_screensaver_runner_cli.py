#!/usr/bin/env python3
"""X11 Screensaver Runner CLI — safe entry point for guarded screensaver execution.

Modes:
    --dry-run         Build plan, validate, simulate lifecycle. NO X11 calls.
    --preflight-only  Check environment, print readiness. NO X11 calls.
    --run-once        Execute the screensaver run. REQUIRES explicit approval token.

Usage:
    python3 -m kso_player.x11_screensaver_runner --dry-run
    python3 -m kso_player.x11_screensaver_runner --preflight-only
    python3 -m kso_player.x11_screensaver_runner --run-once --display=:0 --approval-token USER_APPROVED_RUN_ONCE

Design: docs/audit/x11-screensaver-runner-design.md
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root if running from scripts/
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from kso_player.x11_screensaver_runner import (
    ScreensaverRunPlan,
    ScreensaverRunResult,
    RUNNER_NAME,
    RUNNER_VERSION,
    MODE_DRY_RUN,
    MODE_PREFLIGHT_ONLY,
    MODE_RUN_ONCE,
    APPROVAL_TOKEN,
    DEFAULT_MAX_DURATION_SEC,
    HARD_MAX_DURATION_SEC,
    DEFAULT_STATE_PATH,
    DEFAULT_KILL_SWITCH_PATH,
    DEFAULT_LOCKFILE_PATH,
    build_plan,
    validate_runner_plan,
    validate_runner_safe_output,
    simulate_run,
)
from kso_player.state_observer import (
    STATE_IDLE,
    STATE_UNKNOWN,
    STATE_BUSY,
    STATE_PAYMENT,
    read_state_snapshot,
    PlayerStateSnapshot,
)
from kso_player.kill_switch import is_kill_switch_active


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X11 Screensaver Runner — guarded fullscreen idle screensaver",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Build plan, validate, simulate lifecycle. NO X11 calls.",
    )
    group.add_argument(
        "--preflight-only",
        action="store_true",
        help="Check environment, print readiness. NO X11 calls.",
    )
    group.add_argument(
        "--run-once",
        action="store_true",
        help="Execute the screensaver run. REQUIRES explicit approval token.",
    )

    parser.add_argument(
        "--display",
        default=":0",
        help="X11 display (default: ':0')",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_MAX_DURATION_SEC,
        help=f"Max runtime in seconds (max {HARD_MAX_DURATION_SEC}, default: {DEFAULT_MAX_DURATION_SEC})",
    )
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_PATH,
        help=f"Path to KSO state JSON (default: {DEFAULT_STATE_PATH})",
    )
    parser.add_argument(
        "--kill-switch",
        default=DEFAULT_KILL_SWITCH_PATH,
        help=f"Path to kill-switch flag (default: {DEFAULT_KILL_SWITCH_PATH})",
    )
    parser.add_argument(
        "--approval-token",
        default=None,
        help=f"Approval token required for --run-once (value: {APPROVAL_TOKEN})",
    )

    return parser.parse_args()


def do_dry_run(args: argparse.Namespace) -> ScreensaverRunResult:
    """Build plan, validate, simulate lifecycle. NO X11 calls."""
    plan = build_plan(
        mode=MODE_DRY_RUN,
        display=args.display,
        max_duration_sec=min(args.duration, HARD_MAX_DURATION_SEC),
        state_path=args.state_file,
        kill_switch_path=args.kill_switch,
    )

    val = validate_runner_plan(plan)

    # Try reading current state for realistic simulation
    snapshot = read_state_snapshot(args.state_file)
    ks_active = is_kill_switch_active(args.kill_switch)

    result = simulate_run(
        plan=plan,
        snapshot=snapshot,
        kill_switch_active=ks_active,
    )

    output = {
        "mode": MODE_DRY_RUN,
        "plan_valid": val["valid"],
        "plan_errors": val["errors"],
        "result": result.to_safe_dict(),
        "physical_run_executed": False,
        "run_once_requires_approval": True,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return result


def do_preflight(args: argparse.Namespace) -> ScreensaverRunResult:
    """Check environment, print readiness. NO X11 calls."""
    plan = build_plan(
        mode=MODE_PREFLIGHT_ONLY,
        display=args.display,
        max_duration_sec=min(args.duration, HARD_MAX_DURATION_SEC),
        state_path=args.state_file,
        kill_switch_path=args.kill_switch,
    )

    val = validate_runner_plan(plan)

    # Environment checks
    import os

    env_checks = {
        "display_set": bool(os.environ.get("DISPLAY")),
        "display_value": os.environ.get("DISPLAY", "not set"),
        "state_file_exists": Path(args.state_file).exists(),
        "kill_switch_exists": Path(args.kill_switch).exists(),
        "kill_switch_active": is_kill_switch_active(args.kill_switch),
    }

    snapshot = read_state_snapshot(args.state_file)

    result = simulate_run(
        plan=plan,
        snapshot=snapshot,
        kill_switch_active=env_checks["kill_switch_active"],
    )

    output = {
        "mode": MODE_PREFLIGHT_ONLY,
        "plan_valid": val["valid"],
        "plan_errors": val["errors"],
        "environment": env_checks,
        "current_state": snapshot.effective_state,
        "result": result.to_safe_dict(),
        "physical_run_executed": False,
        "run_once_requires_approval": True,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return result


def do_run_once(args: argparse.Namespace) -> ScreensaverRunResult:
    """Execute the screensaver run. BLOCKED without approval token.

    Physical run reserved for a separate step — not executed in 38.1.9.
    """
    plan = build_plan(
        mode=MODE_RUN_ONCE,
        display=args.display,
        max_duration_sec=min(args.duration, HARD_MAX_DURATION_SEC),
        state_path=args.state_file,
        kill_switch_path=args.kill_switch,
        approval_token=args.approval_token,
    )

    val = validate_runner_plan(plan)

    if not args.approval_token or args.approval_token != APPROVAL_TOKEN:
        result = {
            "mode": MODE_RUN_ONCE,
            "executed": False,
            "error": (
                f"run_once requires explicit user approval. "
                f"Add --approval-token {APPROVAL_TOKEN} to confirm. "
                f"Physical screensaver run is NOT executed in step 38.1.9 — "
                f"it requires a separate explicit user command."
            ),
            "plan_valid": val["valid"],
            "plan_errors": val["errors"],
            "run_once_requires_approval": True,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return ScreensaverRunResult(
            started=False,
            visible=False,
            reason="none",
            state=STATE_UNKNOWN,
            stop_reason="error",
            proof_summary="APPROVAL REQUIRED",
            mode=MODE_RUN_ONCE,
        )

    # Even with approval, we simulate only in step 38.1.9
    snapshot = read_state_snapshot(args.state_file)
    ks_active = is_kill_switch_active(args.kill_switch)

    sim_result = simulate_run(
        plan=plan,
        snapshot=snapshot,
        kill_switch_active=ks_active,
    )

    output = {
        "mode": MODE_RUN_ONCE,
        "executed": False,
        "note": (
            "Physical X11 screensaver run is reserved for step 38.1.10+. "
            "This harness simulates the lifecycle in step 38.1.9 "
            "but does NOT create X11 windows or interact with KSO."
        ),
        "plan_valid": val["valid"],
        "plan_errors": val["errors"],
        "simulation": sim_result.to_safe_dict(),
        "run_once_requires_approval": True,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return sim_result


def main():
    args = parse_args()

    if args.dry_run:
        do_dry_run(args)
    elif args.preflight_only:
        do_preflight(args)
    elif args.run_once:
        result = do_run_once(args)
        safe = validate_runner_safe_output(result.to_safe_dict())
        if not safe["valid"]:
            print(
                f"WARNING: result contains forbidden fields: {safe['errors']}",
                file=sys.stderr,
            )
            # Force-overwrite forbidden fields
            clean = ScreensaverRunResult(
                started=result.started,
                visible=False,
                reason="hidden_forbidden",
                state=STATE_UNKNOWN,
                kill_switch_active=True,
                duration_sec=0.0,
                rollback_done=True,
                stop_reason="forbidden",
                proof_summary="OUTPUT CONTAINED FORBIDDEN FIELDS — scrubbed",
                mode=result.mode,
            )
            print(json.dumps(clean.to_safe_dict(), indent=2, ensure_ascii=False))
    else:
        print("ERROR: No mode selected", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
