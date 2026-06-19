"""KSO Player CLI — safe, read-only, no backend, no auth, no secret.

Commands:
    playlist-status    Check local playlist readiness (read-only)
    safety-check       Check playlist + safety gate (reads local files + manual state)
    playback-dry-run   Full dry-run: playlist → safety gate → session decision
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
    ACTION_PLAY as SAFETY_PLAY,
)
from kso_player.session import select_next_item
from kso_player.safe_output import (
    format_playlist_summary,
    format_safety_decision,
    format_session_decision,
)


def cmd_playlist_status(args: argparse.Namespace) -> None:
    root = Path(args.root)
    playlist = build_playlist(root)
    print(format_playlist_summary(playlist))
    sys.exit(0 if playlist.ready else 1)


def cmd_safety_check(args: argparse.Namespace) -> None:
    root = Path(args.root)
    state = args.state.strip().lower()
    playlist = build_playlist(root)
    snapshot = PlaybackSafetySnapshot(state=state)
    decision = decide_playback_safety(snapshot, playlist)
    print(format_playlist_summary(playlist))
    print(f"state: {state}")
    print(format_safety_decision(decision))
    sys.exit(0 if decision.allowed else 1)


def cmd_playback_dry_run(args: argparse.Namespace) -> None:
    """Full dry-run: playlist → safety gate → session decision.

    Builds playlist, checks safety gate with the given --state,
    selects next item, prints combined safe summary.

    Does NOT play media. Does NOT read real KSO state.
    No backend, no auth, no secret.

    Exit codes:
        0 — session_action=play
        1 — session_action=hold/stop
        2 — invalid CLI args
    """
    root = Path(args.root)
    state = args.state.strip().lower()

    # ── Step 1: Build playlist ────────────────────────────────────
    playlist = build_playlist(root)

    # ── Step 2: Safety gate ───────────────────────────────────────
    snapshot = PlaybackSafetySnapshot(state=state)
    safety_decision = decide_playback_safety(snapshot, playlist)

    # ── Step 3: Session decision ──────────────────────────────────
    session_decision = select_next_item(playlist, safety_decision, state=None)

    # ── Combined safe output ──────────────────────────────────────
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


def _validate_state(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_STATES:
        raise argparse.ArgumentTypeError(
            f"invalid state: '{value}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_STATES))}"
        )
    return normalized


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

    # ── playlist-status ───────────────────────────────────────────
    ps = sub.add_parser(
        "playlist-status",
        help="Check local playlist readiness (read-only, no backend/auth/secret)",
        description=(
            "Check local playlist readiness from manifest + media cache.\n\n"
            "Only reads manifest/current_manifest.json and media/current/.\n"
            "No backend calls, no auth, no secret, no playback.\n\n"
            "Exit codes: 0=ready, 1=not_ready/error, 2=invalid args."
        ),
    )
    ps.add_argument("--root", required=True, help="Agent root path")
    ps.set_defaults(func=cmd_playlist_status)

    # ── safety-check ──────────────────────────────────────────────
    sc = sub.add_parser(
        "safety-check",
        help="Check playlist + safety gate (reads local files + manual --state)",
        description=(
            "Check local playlist readiness + safety gate decision.\n\n"
            "Reads manifest/current_manifest.json and media/current/.\n"
            "Uses the given --state (does NOT read real KSO state).\n"
            "No backend calls, no auth, no secret, no playback.\n\n"
            "Exit codes: 0=allowed, 1=blocked, 2=invalid args."
        ),
    )
    sc.add_argument("--root", required=True, help="Agent root path")
    sc.add_argument(
        "--state", required=True, type=_validate_state,
        help=f"KSO screen state. Allowed: {', '.join(sorted(ALLOWED_STATES))}",
    )
    sc.set_defaults(func=cmd_safety_check)

    # ── playback-dry-run ──────────────────────────────────────────
    pdr = sub.add_parser(
        "playback-dry-run",
        help="Full dry-run: playlist → safety → session (no media played)",
        description=(
            "Full dry-run of the player pipeline.\n\n"
            "Builds playlist → checks safety gate → selects next item.\n"
            "Only reads manifest/current_manifest.json and media/current/.\n"
            "Uses the given --state (does NOT read real KSO state).\n"
            "No backend calls, no auth, no secret. Does NOT play media.\n\n"
            "Exit codes: 0=play, 1=hold/stop, 2=invalid args."
        ),
    )
    pdr.add_argument("--root", required=True, help="Agent root path")
    pdr.add_argument(
        "--state", required=True, type=_validate_state,
        help=f"KSO screen state. Allowed: {', '.join(sorted(ALLOWED_STATES))}",
    )
    pdr.set_defaults(func=cmd_playback_dry_run)

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
