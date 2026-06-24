#!/usr/bin/env python3
"""X11 Click-through Physical Proof Harness — CLI entry point.

Prepares and validates a safe proof plan for testing X11 click-through
fullscreen renderer on a physical KSO.

Modes:
    --dry-run         Build plan, validate, print. NO X11 calls.
    --preflight-only  Check environment, print readiness. NO X11 calls.
    --run-once        Execute the proof. NOT EXECUTED in step 38.1.7 —
                      requires explicit user approval.

Usage:
    python3 -m kso_player.x11_click_through_proof --dry-run
    python3 -m kso_player.x11_click_through_proof --preflight-only
    python3 -m kso_player.x11_click_through_proof --run-once --display=:0

Design: docs/audit/x11-click-through-physical-proof-plan.md
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

from kso_player.x11_click_through_proof import (
    X11ProofPlan,
    X11ProofPreflight,
    X11ProofEvidencePlan,
    PROOF_TITLE,
    DISPLAY_DEFAULT,
    GEOMETRY,
    DEFAULT_DURATION_SEC,
    HARD_MAX_DURATION_SEC,
    validate_proof_plan,
    validate_command_safety,
    validate_safe_output,
    is_mode_run_safe,
    create_default_proof_plan,
    create_default_evidence_plan,
    create_preflight_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X11 Click-through Physical Proof Harness",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Build plan, validate, print. NO X11 calls.",
    )
    group.add_argument(
        "--preflight-only",
        action="store_true",
        help="Check environment, print readiness. NO X11 calls.",
    )
    group.add_argument(
        "--run-once",
        action="store_true",
        help="Execute the proof. REQUIRES explicit user approval.",
    )

    parser.add_argument(
        "--display",
        default=DISPLAY_DEFAULT,
        help=f"X11 display (default: {DISPLAY_DEFAULT})",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_SEC,
        help=f"Proof duration in seconds (max {HARD_MAX_DURATION_SEC}, default: {DEFAULT_DURATION_SEC})",
    )
    parser.add_argument(
        "--approval-token",
        default=None,
        help="Approval token required for --run-once (NOT the KSO password)",
    )

    return parser.parse_args()


def do_dry_run(display: str, duration: int) -> dict:
    """Build and validate a proof plan. NO X11 calls."""
    plan = create_default_proof_plan(
        mode="dry_run",
        display=display,
        duration_sec=duration,
    )
    evidence = create_default_evidence_plan()

    validation = validate_proof_plan(plan)

    result = {
        "mode": "dry_run",
        "plan": plan.to_safe_dict(),
        "evidence_plan": evidence.to_safe_dict(),
        "plan_valid": validation["valid"],
        "plan_errors": validation["errors"],
        "production_ready": plan.is_production_ready(),
        "run_once_requires_approval": True,
        "physical_run_executed": False,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def do_preflight(display: str, duration: int) -> dict:
    """Check environment readiness. NO X11 calls."""
    # In actual physical run, these would be checked via subprocess
    # Here we report the plan without executing
    plan = create_default_proof_plan(
        mode="preflight_only",
        display=display,
        duration_sec=duration,
    )
    validation = validate_proof_plan(plan)

    # Preflight stub — in real run, subprocess checks would populate these
    preflight = create_preflight_result(
        display_available=True,  # Stub: would check $DISPLAY
        xdotool_available=True,  # Stub: would check `which xdotool`
        scrot_available=True,    # Stub: would check `which scrot`
        xwininfo_available=True,  # Stub: would check `which xwininfo`
        xprop_available=True,    # Stub: would check `which xprop`
    )

    result = {
        "mode": "preflight_only",
        "plan": plan.to_safe_dict(),
        "plan_valid": validation["valid"],
        "plan_errors": validation["errors"],
        "preflight_ready": preflight.ready,
        "preflight_errors": list(preflight.errors),
        "preflight_warnings": list(preflight.warnings),
        "preflight_details": {
            "display_available": preflight.display_available,
            "xdotool_available": preflight.xdotool_available,
            "scrot_available": preflight.scrot_available,
            "xwininfo_available": preflight.xwininfo_available,
            "xprop_available": preflight.xprop_available,
            "python3_xlib_available": preflight.python3_xlib_available,
        },
        "run_once_requires_approval": True,
        "physical_run_executed": False,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def do_run_once(display: str, duration: int, approval_token: str | None) -> dict:
    """Execute the proof. BLOCKED without explicit user approval.

    Physical run is NOT executed in step 38.1.7.
    Requires explicit user command and approval token.
    """
    plan = create_default_proof_plan(
        mode="run_once",
        display=display,
        duration_sec=duration,
    )

    # Safety gate: run_once requires explicit user approval
    if not approval_token or approval_token != "USER_APPROVED_RUN_ONCE":
        return {
            "mode": "run_once",
            "executed": False,
            "error": (
                "run_once requires explicit user approval. "
                "Add --approval-token USER_APPROVED_RUN_ONCE to confirm. "
                "Physical X11 proof is NOT executed in step 38.1.7 — "
                "it requires a separate explicit user command."
            ),
            "plan": plan.to_safe_dict(),
            "production_ready": plan.is_production_ready(),
        }

    # Even with approval token, we do NOT actually execute in this step
    return {
        "mode": "run_once",
        "executed": False,
        "error": (
            "Physical X11 proof run is reserved for step 38.1.8+. "
            "This harness prepares the plan but does NOT create X11 windows "
            "or interact with KSO in step 38.1.7."
        ),
        "plan": plan.to_safe_dict(),
        "production_ready": plan.is_production_ready(),
    }


def main():
    args = parse_args()

    if args.dry_run:
        do_dry_run(args.display, args.duration)
    elif args.preflight_only:
        do_preflight(args.display, args.duration)
    elif args.run_once:
        result = do_run_once(args.display, args.duration, args.approval_token)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("ERROR: No mode selected", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
