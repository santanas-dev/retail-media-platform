"""KSO Player CLI — safe, read-only, no backend, no auth, no secret.

Commands:
    playlist-status    Check local playlist readiness (read-only)
    safety-check       Check playlist + safety gate (reads local files + manual state)
    playback-dry-run   Full dry-run: playlist → safety → session
    simulate-step      Simulate one playback step (no media played, no sleep)
    --help             Show help

Only reads manifest/current_manifest.json and media/current/.
No HTTP, no auth, no secret, no playback.
Does NOT read real KSO state — state is passed via --state flag.
"""

import argparse
import sys
from pathlib import Path

from kso_player.playlist import build_playlist
from kso_player.safety import (
    PlaybackSafetySnapshot,
    decide_playback_safety,
    ALLOWED_STATES,
)
from kso_player.session import select_next_item
from kso_player.simulator import simulate_playback_step, SIM_STATUS_WOULD_PLAY
from kso_player.events import build_playback_event_draft, EVENT_TYPE_WOULD_PLAY


def cmd_playlist_status(args: argparse.Namespace) -> None:
    root = Path(args.root)
    playlist = build_playlist(root)
    from kso_player.safe_output import format_playlist_summary
    print(format_playlist_summary(playlist))
    sys.exit(0 if playlist.ready else 1)


def cmd_safety_check(args: argparse.Namespace) -> None:
    root = Path(args.root)
    state = args.state.strip().lower()
    playlist = build_playlist(root)
    snapshot = PlaybackSafetySnapshot(state=state)
    decision = decide_playback_safety(snapshot, playlist)
    from kso_player.safe_output import format_playlist_summary, format_safety_decision
    print(format_playlist_summary(playlist))
    print(f"state: {state}")
    print(format_safety_decision(decision))
    sys.exit(0 if decision.allowed else 1)


def cmd_playback_dry_run(args: argparse.Namespace) -> None:
    root = Path(args.root)
    state = args.state.strip().lower()
    playlist = build_playlist(root)
    snapshot = PlaybackSafetySnapshot(state=state)
    safety_decision = decide_playback_safety(snapshot, playlist)
    session_decision = select_next_item(playlist, safety_decision, state=None)

    print(f"playlist_ready: {str(playlist.ready).lower()}")
    print(f"playback_allowed: {str(safety_decision.allowed).lower()}")
    print(f"safety_action: {safety_decision.action}")
    print(f"safety_reason: {safety_decision.reason}")
    print(f"session_action: {session_decision.action}")
    print(f"session_reason: {session_decision.reason}")

    if session_decision.selected_item is not None:
        item = session_decision.selected_item
        print(f"selected_order: {item.order}")
        print(f"selected_content_type: {item.content_type}")
        print(f"selected_duration_ms: {item.duration_ms}")

    sys.exit(0 if session_decision.action == "play" else 1)


def cmd_simulate_step(args: argparse.Namespace) -> None:
    """Simulate one playback step.

    No media played, no sleep/wait, no PoP, no HTTP.
    """
    root = Path(args.root)
    state = args.state.strip().lower()
    playlist = build_playlist(root)
    snapshot = PlaybackSafetySnapshot(state=state)
    safety_decision = decide_playback_safety(snapshot, playlist)
    sim_result = simulate_playback_step(playlist, safety_decision, session_state=None)

    print(f"playlist_ready: {str(playlist.ready).lower()}")
    print(f"playback_allowed: {str(safety_decision.allowed).lower()}")
    print(f"simulation_status: {sim_result.simulated_status}")
    print(f"session_action: {sim_result.session_action}")
    print(f"session_reason: {sim_result.session_reason}")

    if sim_result.selected_order is not None:
        print(f"selected_order: {sim_result.selected_order}")
    if sim_result.selected_content_type is not None:
        print(f"selected_content_type: {sim_result.selected_content_type}")
    if sim_result.selected_duration_ms is not None:
        print(f"selected_duration_ms: {sim_result.selected_duration_ms}")

    sys.exit(0 if sim_result.simulated_status == SIM_STATUS_WOULD_PLAY else 1)


def cmd_event_dry_run(args: argparse.Namespace) -> None:
    """Build in-memory event draft. No PoP, no JSONL, no backend, no media played."""
    root = Path(args.root)
    state = args.state.strip().lower()
    playlist = build_playlist(root)
    snapshot = PlaybackSafetySnapshot(state=state)
    safety_decision = decide_playback_safety(snapshot, playlist)
    sim_result = simulate_playback_step(playlist, safety_decision, session_state=None)
    event = build_playback_event_draft(sim_result, safety_decision)

    print(f"playlist_ready: {str(playlist.ready).lower()}")
    print(f"playback_allowed: {str(safety_decision.allowed).lower()}")
    print(f"simulation_status: {sim_result.simulated_status}")
    print(f"event_type: {event.event_type}")
    print(f"event_status: {event.event_status}")
    print(f"session_action: {event.session_action}")
    print(f"session_reason: {event.session_reason}")

    if event.selected_order is not None:
        print(f"selected_order: {event.selected_order}")
    if event.selected_content_type is not None:
        print(f"selected_content_type: {event.selected_content_type}")
    if event.selected_duration_ms is not None:
        print(f"selected_duration_ms: {event.selected_duration_ms}")

    sys.exit(0 if event.event_type == EVENT_TYPE_WOULD_PLAY else 1)


def _validate_state(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_STATES:
        raise argparse.ArgumentTypeError(
            f"invalid state: '{value}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_STATES))}"
        )
    return normalized


def _add_state_arg(subparser):
    subparser.add_argument("--root", required=True, help="Agent root path")
    subparser.add_argument(
        "--state", required=True, type=_validate_state,
        help=f"KSO screen state. Allowed: {', '.join(sorted(ALLOWED_STATES))}",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kso-player",
        description=(
            "KSO Player — safe, read-only local playlist checker.\n\n"
            "Only reads manifest/current_manifest.json and media/current/.\n"
            "No backend calls, no auth, no secret, no playback."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="This is a core skeleton. Playback, UI, and KSO integration will be separate steps.",
    )
    sub = parser.add_subparsers(dest="command")

    ps = sub.add_parser("playlist-status", help="Check local playlist readiness")
    ps.add_argument("--root", required=True, help="Agent root path")
    ps.set_defaults(func=cmd_playlist_status)

    sc = sub.add_parser("safety-check", help="Check playlist + safety gate")
    _add_state_arg(sc)
    sc.set_defaults(func=cmd_safety_check)

    pdr = sub.add_parser("playback-dry-run", help="Full dry-run: playlist → safety → session")
    _add_state_arg(pdr)
    pdr.set_defaults(func=cmd_playback_dry_run)

    ss = sub.add_parser("simulate-step",
                        help="Simulate one playback step (no media played, no sleep)")
    _add_state_arg(ss)
    ss.set_defaults(func=cmd_simulate_step)

    edr = sub.add_parser("event-dry-run",
                         help="Build in-memory event draft (no PoP, no JSONL, no backend)")
    _add_state_arg(edr)
    edr.set_defaults(func=cmd_event_dry_run)

    return parser


def main() -> None:
    parser = _build_parser()
    if len(sys.argv) == 1 or sys.argv[1] in ("-h", "--help"):
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
