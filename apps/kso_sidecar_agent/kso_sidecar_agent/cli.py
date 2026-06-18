"""KSO Sidecar Agent CLI — skeleton only.

Commands:
    version         Show version
    init-local-root Create folder structure + agent_status.json
    doctor          Check folder + agent_status.json health

This is a SKELETON. No backend calls, no secrets, no media sync yet.
"""

import argparse
import sys

from kso_sidecar_agent import local_file_store, safe_logger

try:
    from importlib.metadata import version as _version
    VERSION = _version("kso-sidecar-agent")
except Exception:
    VERSION = "0.1.0"


def cmd_version(args: argparse.Namespace) -> None:
    """Print version and exit."""
    print(f"kso-sidecar-agent {VERSION}")


def cmd_init_local_root(args: argparse.Namespace) -> None:
    """Create the kso-adapter folder structure."""
    root = args.root
    local_file_store.init_local_root(root)
    print(f"Initialized agent root at: {root}")
    safe_logger.log(
        level="info",
        event="init_local_root",
        message=f"Agent root initialized: {root}",
    )


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check folder structure and agent_status.json health."""
    result = local_file_store.doctor(args.root)

    print(f"Doctor check for: {args.root}")
    print(f"  root_exists:       {result['root_exists']}")
    print(f"  folders_ok:        {result['folders_ok']}")
    print(f"  total_folders:     {result['total_folders']}")
    missing = result.get("missing_folders", [])
    print(f"  missing_folders:   {len(missing)}")
    for m in missing:
        print(f"    - {m}")

    print(f"  agent_status_ok:   {result['agent_status_ok']}")
    if result["agent_status_error"]:
        print(f"  agent_status_error: {result['agent_status_error']}")
    if result.get("agent_status"):
        print(f"  agent_status:      {result['agent_status']}")

    all_ok = result["root_exists"] and result["folders_ok"] and result["agent_status_ok"]
    if all_ok:
        print("\n✓ All checks passed.")
    else:
        print("\n✗ Issues found.\n  Run 'init-local-root' to create the folder structure.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kso-agent",
        description="KSO Sidecar Agent — skeleton. No backend calls yet.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # version
    p_ver = sub.add_parser("version", help="Show version")
    p_ver.set_defaults(func=cmd_version)

    # init-local-root
    p_init = sub.add_parser("init-local-root", help="Create folder structure")
    p_init.add_argument("--root", required=True, help="Root path for kso-adapter folder")
    p_init.set_defaults(func=cmd_init_local_root)

    # doctor
    p_doc = sub.add_parser("doctor", help="Check folder structure health")
    p_doc.add_argument("--root", required=True, help="Root path to check")
    p_doc.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
