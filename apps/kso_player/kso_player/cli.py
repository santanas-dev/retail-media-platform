"""KSO Player CLI — safe, read-only, no backend, no auth, no secret.

Commands:
    playlist-status    Check local playlist readiness (read-only)
    --help             Show help

Only reads manifest/current_manifest.json and media/current/.
No HTTP, no auth, no secret, no playback.
"""

import argparse
import sys
from pathlib import Path

from kso_player.playlist import build_playlist, FORBIDDEN_SUBSTRINGS
from kso_player.safe_output import format_playlist_summary


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
