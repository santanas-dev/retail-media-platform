"""KSO Simulator CLI — local KSO software mock.

Usage:
    python -m kso_simulator init --root /tmp/kso-adapter
    python -m kso_simulator set-state idle --root /tmp/kso-adapter
    python -m kso_simulator status --root /tmp/kso-adapter

This is a DEV TOOL, NOT a KSO player.
"""

import argparse
import json
import sys

from kso_simulator import local_fs
from kso_simulator import state_writer
from kso_simulator import pop_writer
from kso_simulator import manifest_reader
from kso_simulator import media_verifier
from kso_simulator import playback_simulator
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


def cmd_manifest_status(args: argparse.Namespace) -> None:
    """Show manifest status: exists, expired, validation, items count."""
    root = args.root
    try:
        info = manifest_reader.read_manifest(root)
    except FileNotFoundError:
        print("Manifest: MISSING (no manifest/current_manifest.json)")
        print("  Run 'init' first, then create a valid manifest file.")
        return
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Manifest: INVALID")
        print(f"  Error: {e}")
        sys.exit(1)

    hash_short = info.manifest_hash[:12]
    expired = "true" if info.expired else "false"
    status = "ok" if not info.expired else "expired"
    print(f"Manifest: PRESENT (validation: {status})")
    print(f"  manifest_version_id: {info.manifest_version_id}")
    print(f"  manifest_hash:       {hash_short}...")
    print(f"  generated_at:        {info.generated_at.isoformat()}")
    print(f"  valid_until:         {info.valid_until.isoformat()}")
    print(f"  expired:             {expired}")
    print(f"  items_count:         {info.items_count}")
    if info.campaign_id:
        print(f"  campaign_id:         {info.campaign_id}")


def cmd_list_items(args: argparse.Namespace) -> None:
    """List manifest items with key fields."""
    try:
        info = manifest_reader.read_manifest(args.root)
    except FileNotFoundError:
        print("ERROR: Manifest not found.", file=sys.stderr)
        sys.exit(1)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Invalid manifest: {e}", file=sys.stderr)
        sys.exit(1)

    if info.items_count == 0:
        print("No items in manifest.")
        return

    print(f"{'ID':38s} {'filename':30s} {'mime':20s} {'dur_ms':>7s} {'order':>5s} {'sha256':>14s}")
    print("-" * 140)
    for item in info.items:
        mid = item.manifest_item_id[:8] + "..."
        sha = item.sha256[:12] + "..."
        print(
            f"{mid:38s} "
            f"{item.filename[:30]:30s} "
            f"{item.content_type[:20]:20s} "
            f"{item.duration_ms:>7d} "
            f"{item.order:>5d} "
            f"{sha:>14s}"
        )


def cmd_verify_media(args: argparse.Namespace) -> None:
    """Verify local media files against manifest."""
    try:
        result = media_verifier.verify_media(args.root)
    except FileNotFoundError:
        print("ERROR: Manifest not found.", file=sys.stderr)
        sys.exit(1)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Invalid manifest: {e}", file=sys.stderr)
        sys.exit(1)

    if result.manifest_expired:
        print("WARNING: manifest is expired — verifying files anyway.\n")

    print(f"Total items:       {result.total_items}")
    print(f"  present:         {result.present}")
    print(f"  missing:         {result.missing}")
    print(f"  hash_ok:         {result.hash_ok}")
    print(f"  hash_mismatch:   {result.hash_mismatch}")
    print(f"  invalid_items:   {result.invalid_items}")
    print()

    STATUS_LABELS = {
        "ok": "ok",
        "missing": "missing",
        "hash_mismatch": "hash_mismatch",
        "invalid_manifest_item": "invalid_item",
        "invalid_media_file": "symlink_rejected",
    }

    print(
        f"{'ID':38s} {'filename':30s} {'status':20s} {'expected_sha':14s} {'actual_sha':14s}"
    )
    print("-" * 120)
    for item in result.items:
        mid = item.manifest_item_id[:8] + "..."
        exp = item.expected_sha256[:12] + "..."
        act = item.actual_sha256[:12] + "..." if item.actual_sha256 else "-"
        status_label = STATUS_LABELS.get(item.status, item.status)
        print(
            f"{mid:38s} "
            f"{item.filename[:30]:30s} "
            f"{status_label:20s} "
            f"{exp:14s} "
            f"{act:14s}"
        )

    # Non-zero exit if any errors
    if result.hash_mismatch > 0 or result.missing > 0 or result.invalid_items > 0:
        sys.exit(1)


def cmd_show_once(args: argparse.Namespace) -> None:
    """Simulate a single safe media playback."""
    try:
        result = playback_simulator.show_once(
            root=args.root,
            manifest_item_id=args.manifest_item_id,
            duration_ms=args.duration_ms,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if result.status == playback_simulator.SHOW_COMPLETED:
        print(f"SHOW_COMPLETED manifest_item_id={result.device_event_id[:8]}... "
              f"duration_ms={result.duration_ms}")
        return

    # SHOW_BLOCKED or SHOW_FAILED
    label = "SHOW_BLOCKED" if result.status == playback_simulator.SHOW_BLOCKED else "SHOW_FAILED"
    print(f"{label} reason={result.reason}")
    if result.detail:
        print(f"  {result.detail}")
    sys.exit(1)


def cmd_run_idle_loop(args: argparse.Namespace) -> None:
    """Run an idle loop through manifest items."""
    result = playback_simulator.run_idle_loop(
        root=args.root,
        iterations=args.iterations,
        interval_ms=args.interval_ms,
        stop_on_blocked=args.stop_on_blocked,
    )

    # Per-item lines
    for res in result.items:
        mid = res.device_event_id[:8] + "..." if res.device_event_id else "-"
        if res.status == playback_simulator.SHOW_COMPLETED:
            print(f"ITEM_COMPLETED manifest_item_id={mid} duration_ms={res.duration_ms}")
        elif res.status == playback_simulator.SHOW_BLOCKED:
            print(f"ITEM_BLOCKED reason={res.reason}")
        else:
            print(f"ITEM_FAILED reason={res.reason}")

    # Summary
    stopped = ""
    if result.stopped_early:
        stopped = " stopped_early=true"
    print(f"\nLOOP_DONE iterations={result.iterations} attempted={result.attempted} "
          f"completed={result.completed} blocked={result.blocked} "
          f"failed={result.failed}{stopped}")

    if result.failed > 0 or (result.blocked > 0 and result.completed == 0):
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

    # manifest-status
    p_ms = sub.add_parser("manifest-status", help="Show manifest status")
    p_ms.add_argument("--root", required=True, help="Root path")
    p_ms.set_defaults(func=cmd_manifest_status)

    # list-items
    p_li = sub.add_parser("list-items", help="List manifest items")
    p_li.add_argument("--root", required=True, help="Root path")
    p_li.set_defaults(func=cmd_list_items)

    # verify-media
    p_vm = sub.add_parser("verify-media", help="Verify media files against manifest")
    p_vm.add_argument("--root", required=True, help="Root path")
    p_vm.set_defaults(func=cmd_verify_media)

    # show-once
    p_so = sub.add_parser("show-once", help="Simulate one safe media playback")
    p_so.add_argument("--root", required=True, help="Root path")
    p_so.add_argument("--manifest-item-id", required=True, help="Media item UUID")
    p_so.add_argument("--duration-ms", type=int, default=None,
                      help="Override duration (default: from manifest)")
    p_so.set_defaults(func=cmd_show_once)

    # run-idle-loop
    p_loop = sub.add_parser("run-idle-loop", help="Loop through manifest items with safety")
    p_loop.add_argument("--root", required=True, help="Root path")
    p_loop.add_argument("--iterations", type=int, default=1,
                        help="Max show attempts (default: 1)")
    p_loop.add_argument("--interval-ms", type=int, default=1000,
                        help="Sleep between items in ms (default: 1000)")
    p_loop.add_argument("--stop-on-blocked", action="store_true", default=False,
                        help="Stop loop on first non-completed result")
    p_loop.set_defaults(func=cmd_run_idle_loop)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
