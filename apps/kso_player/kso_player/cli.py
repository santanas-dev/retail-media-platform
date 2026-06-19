"""KSO Player CLI — safe, read-only, no backend, no auth, no secret.

Commands:
    playlist-status    Check local playlist readiness (read-only)
    safety-check       Check playlist + safety gate (reads local files + manual state)
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
from kso_player.safe_output import format_playlist_summary, format_safety_decision


def cmd_playlist_status(args: argparse.Namespace) -> None:
    """Print safe playlist status and exit with appropriate code.

    Exit codes:
        0 — playlist ready (all items verified)
        1 — playlist not_ready or error
        2 — invalid CLI args (handled by argparse)
    """
    root = Path(args.root)
    playlist = build_playlist(root)
    print(format_playlist_summary(playlist))

    if playlist.ready:
        sys.exit(0)
    else:
        sys.exit(1)


def cmd_safety_check(args: argparse.Namespace) -> None:
    """Check playlist readiness + safety gate for a given KSO state.

    Builds playlist from local files, creates a safety snapshot with
    the given --state, and prints the combined safe decision.

    Does NOT read real KSO state — the state is passed manually.
    No backend, no auth, no secret, no playback.

    Exit codes:
        0 — playback_allowed=true
        1 — playback_allowed=false
        2 — invalid CLI args (handled by argparse)
    """
    root = Path(args.root)
    state = args.state.strip().lower()

    # ── Build playlist ────────────────────────────────────────────
    playlist = build_playlist(root)

    # ── Safety decision ───────────────────────────────────────────
    snapshot = PlaybackSafetySnapshot(state=state)
    decision = decide_playback_safety(snapshot, playlist)

    # ── Safe output ───────────────────────────────────────────────
    print(format_playlist_summary(playlist))
    print(f"state: {state}")
    print(format_safety_decision(decision))

    if decision.allowed:
        sys.exit(0)
    else:
        sys.exit(1)


def _validate_state(value: str) -> str:
    """Validate --state argument. Returns normalized state or raises argparse error."""
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
        "--state",
        required=True,
        type=_validate_state,
        help=f"KSO screen state. Allowed: {', '.join(sorted(ALLOWED_STATES))}",
    )
    sc.set_defaults(func=cmd_safety_check)

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
