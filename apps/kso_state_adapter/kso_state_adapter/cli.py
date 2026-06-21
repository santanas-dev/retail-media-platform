"""KSO UKM 4 State Adapter — CLI.

Commands:
    write-once    Write state/kso_state.json once
    daemon        Run state adapter daemon loop
"""

import argparse
import sys as _sys
from pathlib import Path

from kso_state_adapter.state_model import (
    KsoState,
    ALLOWED_STATES,
    STATE_UNKNOWN,
    FORBIDDEN_STATE_KEYS,
)
from kso_state_adapter.state_writer import (
    atomic_write_state,
    format_write_result,
    STATUS_WRITTEN,
)
from kso_state_adapter.source import StaticStateSource
from kso_state_adapter.file_source import SafeStatusFileSource, SafeStatusFileError
from kso_state_adapter.daemon import (
    run_kso_state_adapter_daemon,
    format_daemon_result,
    DAEMON_STATUS_STOPPED,
    DAEMON_STATUS_STOPPING,
)
from kso_state_adapter import VERSION


def cmd_write_once(args: argparse.Namespace) -> None:
    """Write kso_state.json once."""
    try:
        state_str = args.state.lower()
        if state_str not in ALLOWED_STATES:
            print(f"ERROR: Invalid state '{args.state}'", file=_sys.stderr)
            print(f"Allowed: {', '.join(sorted(ALLOWED_STATES))}",
                  file=_sys.stderr)
            _sys.exit(2)
    except Exception:
        print(f"ERROR: Invalid state", file=_sys.stderr)
        _sys.exit(2)

    state = KsoState(state=state_str)
    result = atomic_write_state(args.root, state)

    print(format_write_result(result))
    if result["status"] != STATUS_WRITTEN:
        _sys.exit(1)


def cmd_daemon(args: argparse.Namespace) -> None:
    """Run state adapter daemon."""
    source_type = getattr(args, "source", "static")

    if source_type == "file":
        # File source
        source_file = getattr(args, "source_file", None)
        if not source_file:
            print("ERROR: --source file requires --source-file PATH",
                  file=_sys.stderr)
            _sys.exit(2)
        try:
            source = SafeStatusFileSource(Path(source_file))
        except Exception as e:
            print(f"ERROR: Cannot create file source: {e}", file=_sys.stderr)
            _sys.exit(2)
    else:
        # Static source (default)
        try:
            source_state = args.source_state.lower()
            if source_state not in ALLOWED_STATES:
                print(f"ERROR: Invalid source state '{args.source_state}'",
                      file=_sys.stderr)
                _sys.exit(2)
        except Exception:
            print(f"ERROR: Invalid --source-state", file=_sys.stderr)
            _sys.exit(2)
        source = StaticStateSource(state=source_state)

    result = run_kso_state_adapter_daemon(
        root=args.root,
        source=source,
        interval_seconds=args.interval,
        max_cycles=args.max_cycles,
        health_file=args.health_file,
    )

    print(format_daemon_result(result))
    if result.status not in (DAEMON_STATUS_STOPPED, DAEMON_STATUS_STOPPING):
        _sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kso-state-adapter",
        description="KSO UKM 4 State Adapter",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # version
    p_ver = sub.add_parser("version", help="Show version")
    p_ver.set_defaults(func=lambda args: print(f"kso-state-adapter {VERSION}"))

    # write-once
    p_wo = sub.add_parser("write-once", help="Write kso_state.json once")
    p_wo.add_argument("--root", required=True, help="Agent root path")
    p_wo.add_argument("--state", required=True,
                      help=f"State to write. Allowed: {', '.join(sorted(ALLOWED_STATES))}")
    p_wo.set_defaults(func=cmd_write_once)

    # daemon
    p_dm = sub.add_parser("daemon", help="Run state adapter daemon")
    p_dm.add_argument("--root", required=True, help="Agent root path")
    p_dm.add_argument("--source", type=str, default="static",
                      choices=["static", "file"],
                      help="Source type: static (default) or file")
    p_dm.add_argument("--source-state", type=str, default="unknown",
                      help="State for static source (default: unknown)")
    p_dm.add_argument("--source-file", type=str, default=None,
                      help="Path to status file (for --source file)")
    p_dm.add_argument("--interval", type=float, default=1.0,
                      help="Interval between cycles in seconds (default: 1.0)")
    p_dm.add_argument("--max-cycles", type=int, default=None,
                      help="Max cycles (None = run forever)")
    p_dm.add_argument("--health-file", type=str, default=None,
                      help="Optional path for health JSON")
    p_dm.set_defaults(func=cmd_daemon)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
