"""KSO Player CLI — safe, read-only, no backend, no auth, no secret.

Commands:
    playlist-status    Check local playlist readiness (read-only)
    safety-check       Check playlist + safety gate (reads local files + manual state)
    playback-dry-run   Full dry-run: playlist → safety → session
    simulate-step      Simulate one playback step (no media played, no sleep)
    event-dry-run      Build in-memory event draft (no PoP, no JSONL, no backend)
    pop-write          Build event draft + write to local JSONL (no backend, no sidecar)
    shell-snapshot-write  Write bootstrap_snapshot.js to runtime shell directory
    local-demo-prepare    Full vertical demo: workspace + media alias + snapshot
    local-chromium-demo   Guarded local Chromium demo: prepare + optionally launch
    local-demo-fixture    Create local demo fixture: idle state + manifest + media
    display-cycle-once    Run one display cycle: render decision + optional draft PoP
    display-complete-once Run completed display cycle: optional completed PoP write
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
from kso_player.display_cycle import (
    run_kso_display_cycle_once,
    run_kso_display_completion_once,
    format_kso_display_cycle_result,
)
from kso_player.session import select_next_item
from kso_player.simulator import simulate_playback_step, SIM_STATUS_WOULD_PLAY
from kso_player.events import build_playback_event_draft, EVENT_TYPE_WOULD_PLAY
from kso_player.pop_writer import write_pop_event, STATUS_WRITTEN
from kso_player.runtime_snapshot_writer import (
    write_kso_runtime_bootstrap_snapshot,
    format_kso_runtime_snapshot_write_result,
    REASON_WRITTEN as REASON_SNAPSHOT_WRITTEN,
    STATUS_ERROR as SNAPSHOT_STATUS_ERROR,
)
from kso_player.local_visual_demo_prepare import (
    prepare_kso_local_visual_demo,
    format_kso_local_visual_demo_prepare_result,
    STATUS_OK as DEMO_STATUS_OK,
    STATUS_ERROR as DEMO_STATUS_ERROR,
)
from kso_player.local_chromium_demo_runner import (
    prepare_and_maybe_launch_kso_local_chromium_demo,
    format_kso_local_chromium_demo_runner_result,
    STATUS_OK as CHROMIUM_STATUS_OK,
    STATUS_ERROR as CHROMIUM_STATUS_ERROR,
)
from kso_player.local_demo_fixture import (
    prepare_kso_local_demo_fixture,
    format_kso_local_demo_fixture_result,
    STATUS_OK as FIXTURE_STATUS_OK,
    STATUS_ERROR as FIXTURE_STATUS_ERROR,
)


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


def cmd_pop_write(args: argparse.Namespace) -> None:
    """Build event draft + write to local pop/pending/player_events.jsonl.

    Pipeline: playlist → safety → simulator → event draft → local JSONL write.
    No backend, no sidecar pickup, no sent/quarantine rotation.
    Media not played, no sleep, no HTTP, no auth, no secret.
    """
    root = Path(args.root)
    state = args.state.strip().lower()
    playlist = build_playlist(root)
    snapshot = PlaybackSafetySnapshot(state=state)
    safety_decision = decide_playback_safety(snapshot, playlist)
    sim_result = simulate_playback_step(playlist, safety_decision, session_state=None)
    event = build_playback_event_draft(sim_result, safety_decision)
    write_result = write_pop_event(root, event, state)

    print(f"playlist_ready: {str(playlist.ready).lower()}")
    print(f"playback_allowed: {str(safety_decision.allowed).lower()}")
    print(f"simulation_status: {sim_result.simulated_status}")
    print(f"event_type: {event.event_type}")
    print(f"event_status: {event.event_status}")
    print(f"pop_write_status: {write_result.status}")
    print(f"pop_write_reason: {write_result.reason}")

    if write_result.line_size_bytes > 0:
        print(f"line_size_bytes: {write_result.line_size_bytes}")

    sys.exit(0 if write_result.status == STATUS_WRITTEN else 1)


def cmd_shell_snapshot_write(args: argparse.Namespace) -> None:
    """Write bootstrap_snapshot.js to the runtime shell directory.

    Pipeline: state → runtime_gate → shell_snapshot → atomic JS write.
    Targets ONLY the runtime shell copy, NEVER the /opt source.
    No backend, no Chromium, no PoP.
    """
    result = write_kso_runtime_bootstrap_snapshot(
        root=args.root,
        runtime_shell_dir=args.runtime_shell_dir,
        stale_seconds=args.stale_seconds,
    )
    print(format_kso_runtime_snapshot_write_result(result))
    if result.status == SNAPSHOT_STATUS_ERROR:
        sys.exit(1)
    sys.exit(0)


def cmd_local_demo_prepare(args: argparse.Namespace) -> None:
    """Prepare a local visual demo: workspace + media alias + bootstrap snapshot.

    Full pipeline: prepare workspace → build snapshot → media aliases → write JS.
    Source shell is NEVER modified.
    No backend, no Chromium, no systemd, no PoP.
    """
    result = prepare_kso_local_visual_demo(
        root=args.root,
        source_shell_dir=args.source_shell_dir,
        runtime_shell_dir=args.runtime_shell_dir,
        stale_seconds=args.stale_seconds,
    )
    print(format_kso_local_visual_demo_prepare_result(result))
    if result.status == DEMO_STATUS_ERROR:
        sys.exit(1)
    sys.exit(0)


def cmd_local_chromium_demo(args: argparse.Namespace) -> None:
    """Guarded local Chromium demo: prepare demo + optionally launch Chromium.

    By default (no --confirm-launch): prepares demo, does NOT launch Chromium.
    With --confirm-launch: prepares demo AND launches Chromium.
    NO systemd, NO backend, NO PoP, NO state write.
    """
    result = prepare_and_maybe_launch_kso_local_chromium_demo(
        root=args.root,
        source_shell_dir=args.source_shell_dir,
        runtime_shell_dir=args.runtime_shell_dir,
        chromium_bin=args.chromium_bin,
        confirm_launch=args.confirm_launch,
        stale_seconds=args.stale_seconds,
    )
    print(format_kso_local_chromium_demo_runner_result(result))
    if result.status == CHROMIUM_STATUS_ERROR:
        sys.exit(1)
    sys.exit(0)


def cmd_local_demo_fixture(args: argparse.Namespace) -> None:
    """Create a local demo fixture root: idle state + manifest + media.

    Writes state/kso_state.json, manifest/current_manifest.json,
    and media/current/ad_demo.png.
    This is a demo-only generator — NOT production state adapter.
    No backend, no secret, no PoP.
    """
    result = prepare_kso_local_demo_fixture(root=args.root)
    print(format_kso_local_demo_fixture_result(result))
    if result.status == FIXTURE_STATUS_ERROR:
        sys.exit(1)
    sys.exit(0)


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


def cmd_display_cycle_once(args: argparse.Namespace) -> None:
    """Run one display cycle: render decision + optional PoP write.

    By default, PoP is NOT written. Use --confirm-pop-write to write.
    No backend, no Chromium, no systemd, no sidecar.
    """
    result = run_kso_display_cycle_once(
        root=args.root,
        stale_seconds=args.stale_seconds,
        confirm_pop_write=args.confirm_pop_write,
    )
    print(format_kso_display_cycle_result(result))
    if result.status == "error":
        sys.exit(1)
    sys.exit(0)


def cmd_display_completion_once(args: argparse.Namespace) -> None:
    """Run one completed display cycle: writes completed PoP event.

    By default, completed PoP is NOT written. Use --confirm-display-completed.
    This simulates a display cycle where the item was actually shown
    for its full duration. The sidecar classifies completed events as eligible
    (with manifest + media available).

    No backend, no Chromium, no systemd, no sidecar.
    """
    result = run_kso_display_completion_once(
        root=args.root,
        stale_seconds=args.stale_seconds,
        confirm_display_completed=args.confirm_display_completed,
    )
    print(format_kso_display_cycle_result(result))
    if result.status == "error":
        sys.exit(1)
    sys.exit(0)  # ← was missing


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

    pw = sub.add_parser("pop-write",
                        help="Build event draft + write to local pop/pending/player_events.jsonl")
    _add_state_arg(pw)
    pw.set_defaults(func=cmd_pop_write)

    ssw = sub.add_parser("shell-snapshot-write",
                         help="Write bootstrap_snapshot.js to runtime shell directory")
    ssw.add_argument("--root", required=True, help="Agent root path")
    ssw.add_argument("--runtime-shell-dir", required=True,
                     help="Runtime shell directory path")
    ssw.add_argument("--stale-seconds", type=int, default=30,
                     help="Max state age before stale (default: 30)")
    ssw.set_defaults(func=cmd_shell_snapshot_write)

    ldp = sub.add_parser("local-demo-prepare",
                         help="Prepare local visual demo: workspace + media alias + snapshot")
    ldp.add_argument("--root", required=True, help="Agent root path")
    ldp.add_argument("--source-shell-dir", required=True,
                     help="Immutable source shell directory")
    ldp.add_argument("--runtime-shell-dir", required=True,
                     help="Runtime shell directory path")
    ldp.add_argument("--stale-seconds", type=int, default=30,
                     help="Max state age before stale (default: 30)")
    ldp.set_defaults(func=cmd_local_demo_prepare)

    lcd = sub.add_parser("local-chromium-demo",
                         help="Guarded local Chromium demo: prepare + optionally launch")
    lcd.add_argument("--root", required=True, help="Agent root path")
    lcd.add_argument("--source-shell-dir", required=True,
                     help="Immutable source shell directory")
    lcd.add_argument("--runtime-shell-dir", required=True,
                     help="Runtime shell directory path")
    lcd.add_argument("--chromium-bin", type=str, default="chromium",
                     help="Chromium binary path (default: chromium)")
    lcd.add_argument("--stale-seconds", type=int, default=30,
                     help="Max state age before stale (default: 30)")
    lcd.add_argument("--confirm-launch", action="store_true", default=False,
                     help="Actually launch Chromium (default: prepare only)")
    lcd.set_defaults(func=cmd_local_chromium_demo)

    ldf = sub.add_parser("local-demo-fixture",
                         help="Create local demo fixture: idle state + manifest + media")
    ldf.add_argument("--root", required=True, help="Agent root path")
    ldf.set_defaults(func=cmd_local_demo_fixture)

    dc = sub.add_parser("display-cycle-once",
                        help="Run one display cycle: gate → render → optional PoP write")
    dc.add_argument("--root", required=True, help="Agent root path")
    dc.add_argument("--stale-seconds", type=int, default=30,
                    help="Max state age before stale (default: 30)")
    dc.add_argument("--confirm-pop-write", action="store_true", default=False,
                    help="Write PoP event to local JSONL (default: no write)")
    dc.set_defaults(func=cmd_display_cycle_once)

    dco = sub.add_parser("display-complete-once",
                         help="Run completed display cycle: render + optional completed PoP write")
    dco.add_argument("--root", required=True, help="Agent root path")
    dco.add_argument("--stale-seconds", type=int, default=30,
                     help="Max state age before stale (default: 30)")
    dco.add_argument("--confirm-display-completed", action="store_true", default=False,
                     help="Write completed PoP event to local JSONL (default: no write)")
    dco.set_defaults(func=cmd_display_completion_once)

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
