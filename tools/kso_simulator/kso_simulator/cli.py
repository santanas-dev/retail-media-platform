"""KSO Simulator CLI — local KSO software mock.

Usage:
    python -m kso_simulator init --root /tmp/kso-adapter
    python -m kso_simulator set-state idle --root /tmp/kso-adapter
    python -m kso_simulator status --root /tmp/kso-adapter

This is a DEV TOOL, NOT a KSO player.
"""

import argparse
import sys

from kso_simulator import local_fs
from kso_simulator import state_writer
from kso_simulator import pop_writer
from kso_simulator.pop_writer import ALLOWED_RESULTS
from kso_simulator.safety import ALLOWED_STATES

try:
    from importlib.metadata import version as _version
except ImportError:
    _version = lambda _: "0.1.0"


def cmd_init(args: argparse.Namespace) -> None:
    """Create folder structure and initial kso_status.json."""
    root = args.root
    local_fs.create_folders(root)
    state_writer.write_state(root, "unknown")
    print(f"Initialized KSO simulator at: {root}")
    print(f"  State: unknown (can_show_ads=false)")
    print(f"  Folders created: config, manifest, media/current, media/staging,"
          f" media/quarantine, pop, status, logs")


def cmd_set_state(args: argparse.Namespace) -> None:
    """Set KSO state and write kso_status.json."""
    root = args.root
    state = args.state

    if state not in ALLOWED_STATES:
        print(f"ERROR: Invalid state '{state}'.", file=sys.stderr)
        print(f"Allowed states: {', '.join(sorted(ALLOWED_STATES))}", file=sys.stderr)
        sys.exit(1)

    state_writer.write_state(root, state)
    can_show = state == "idle"
    print(f"State set to: {state} (can_show_ads={'true' if can_show else 'false'})")


def cmd_status(args: argparse.Namespace) -> None:
    """Show current simulator status."""
    import json
    from pathlib import Path

    root = Path(args.root)

    print(f"Root: {root}")

    # Check folders
    expected_folders = [
        "config", "manifest",
        "media/current", "media/staging", "media/quarantine",
        "pop", "status", "logs",
    ]
    print("\nFolders:")
    for folder in expected_folders:
        path = root / folder
        status = "exists" if path.is_dir() else "MISSING"
        print(f"  {folder:25s} {status}")

    # Read kso_status.json
    status_file = root / "status" / "kso_status.json"
    print(f"\nkso_status.json:")
    if status_file.exists():
        try:
            data = json.loads(status_file.read_text())
            print(f"  state:         {data.get('state', 'MISSING')}")
            print(f"  can_show_ads:  {data.get('can_show_ads', 'MISSING')}")
            print(f"  screen:        {data.get('screen', 'MISSING')}")
            print(f"  updated_at:    {data.get('updated_at', 'MISSING')}")
        except json.JSONDecodeError:
            print("  ERROR: Invalid JSON")
    else:
        print("  MISSING (run 'init' first)")

    # Count media files
    media_dir = root / "media" / "current"
    if media_dir.is_dir():
        media_files = list(media_dir.iterdir())
        print(f"\nmedia/current: {len(media_files)} files")

    # Count PoP events
    pop_log = root / "pop" / "events.log"
    if pop_log.exists():
        lines = pop_log.read_text().strip().split("\n")
        n = len([l for l in lines if l.strip()])
        print(f"pop/events.log: {n} events")


def cmd_write_pop(args: argparse.Namespace) -> None:
    """Write a PoP event to pop/events.log (JSONL append)."""
    try:
        event_id = pop_writer.write_pop_event(
            root=args.root,
            manifest_item_id=args.manifest_item_id,
            result=args.result,
            duration_ms=args.duration_ms,
            reason=args.reason,
            started_at=args.started_at,
            ended_at=args.ended_at,
        )
        print(f"PoP event written: {event_id}")
        print(f"  manifest_item_id: {args.manifest_item_id}")
        print(f"  result:           {args.result}")
        print(f"  duration_ms:      {args.duration_ms}")
        if args.reason:
            print(f"  reason:           {args.reason}")
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kso-sim",
        description="KSO Simulator — local KSO software mock for testing KSO Sidecar Agent.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Create folder structure")
    p_init.add_argument("--root", required=True, help="Root path for kso-adapter folder")
    p_init.set_defaults(func=cmd_init)

    # set-state
    p_state = sub.add_parser("set-state", help="Set KSO state")
    p_state.add_argument("state", choices=sorted(ALLOWED_STATES), help="KSO state")
    p_state.add_argument("--root", required=True, help="Root path")
    p_state.set_defaults(func=cmd_set_state)

    # status
    p_status = sub.add_parser("status", help="Show current status")
    p_status.add_argument("--root", required=True, help="Root path")
    p_status.set_defaults(func=cmd_status)

    # write-pop
    p_pop = sub.add_parser("write-pop", help="Write PoP event to JSONL log")
    p_pop.add_argument("--root", required=True, help="Root path")
    p_pop.add_argument("--manifest-item-id", required=True, help="Media item UUID")
    p_pop.add_argument("--result", required=True, choices=sorted(ALLOWED_RESULTS), help="PoP result")
    p_pop.add_argument("--duration-ms", required=True, type=int, help="Duration in ms (>=0)")
    p_pop.add_argument("--reason", default=None, help="Optional reason")
    p_pop.add_argument("--started-at", default=None, help="ISO8601 start time")
    p_pop.add_argument("--ended-at", default=None, help="ISO8601 end time (>= started-at)")
    p_pop.set_defaults(func=cmd_write_pop)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
