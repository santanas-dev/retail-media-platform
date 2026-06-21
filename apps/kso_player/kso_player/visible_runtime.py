"""KSO Player Visible Runtime Core — one-command local ad display.

Pipeline:
  1. (optional) prepare_demo_fixture → idle state + KSO manifest + media
  2. prepare_kso_local_visual_demo → workspace + snapshot
  3. build Chromium command (guarded, no forbidden flags)
  4. (if confirm_launch) launch Chromium via injected launcher

One command to go from nothing to seeing an ad on screen.
NO systemd, NO backend, NO sidecar, NO completed PoP, NO real HTTP.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from kso_player.local_demo_fixture import (
    prepare_kso_local_demo_fixture,
    KsoLocalDemoFixtureResult,
    STATUS_OK as FIXTURE_STATUS_OK,
    STATUS_ERROR as FIXTURE_STATUS_ERROR,
)
from kso_player.local_chromium_demo_runner import (
    prepare_and_maybe_launch_kso_local_chromium_demo,
    KsoLocalChromiumDemoRunnerResult,
    STATUS_OK as CHROMIUM_STATUS_OK,
    STATUS_ERROR as CHROMIUM_STATUS_ERROR,
    REASON_PREPARED_LAUNCH_READY,
    REASON_PREPARED_LAUNCHED,
    REASON_PREPARE_FAILED,
    REASON_LAUNCH_FAILED,
    REASON_INVALID_ARGS,
)
from kso_player.shell_snapshot import (
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_ERROR = "error"

REASON_READY = "ready"
REASON_LAUNCHED = "launched"
REASON_HOLD = "hold"
REASON_FIXTURE_FAILED = "fixture_failed"
REASON_PREPARE_FAILED_VISIBLE = "prepare_failed"
REASON_LAUNCH_FAILED_VISIBLE = "launch_failed"
REASON_INVALID_ARGS_VISIBLE = "invalid_args"

# Forbidden substrings in safe output
FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "backend_base_url", "127.0.0.1", "device_code",
    "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes",
    "stacktrace", "filename", "media_ref",
    "manifest_version_id", "manifest_hash",
    "rendition_id", "booking_id", "publication_target_id",
    "storage", "minio",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoVisibleRuntimeResult:
    """Safe result of visible runtime preparation and optional launch.

    NEVER contains absolute paths, file URLs, full Chromium commands,
    mediaRef values, IDs, raw JSON, exception text, or forbidden substrings.

    Internal fields (_chromium_result) use repr=False.
    """

    status: str = STATUS_ERROR
    fixture_ready: bool = False
    render_ready: bool = False
    shell_prepared: bool = False
    snapshot_written: bool = False
    launch_ready: bool = False
    launched: bool = False
    reason: str = REASON_INVALID_ARGS_VISIBLE

    # Internal — NEVER exposed in safe output
    _chromium_result: Optional[KsoLocalChromiumDemoRunnerResult] = field(
        default=None, repr=False,
    )

    def __repr__(self) -> str:
        return (
            f"KsoVisibleRuntimeResult("
            f"status={self.status!r}, "
            f"fixture_ready={self.fixture_ready}, "
            f"render_ready={self.render_ready}, "
            f"shell_prepared={self.shell_prepared}, "
            f"snapshot_written={self.snapshot_written}, "
            f"launch_ready={self.launch_ready}, "
            f"launched={self.launched}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_kso_visible_runtime_once(
    root,
    source_shell_dir,
    runtime_shell_dir,
    chromium_bin: str,
    confirm_launch: bool = False,
    prepare_demo_fixture: bool = False,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
    process_launcher: Optional[Callable[[List[str]], Optional[object]]] = None,
) -> KsoVisibleRuntimeResult:
    """Prepare and optionally launch a visible KSO ad in Chromium.

    Full pipeline:
    1. If prepare_demo_fixture: create demo root (idle state + manifest + media)
    2. Call prepare_and_maybe_launch_kso_local_chromium_demo() — existing safe runner
    3. Return safe KsoVisibleRuntimeResult

    By default (confirm_launch=False): only prepares, does NOT launch Chromium.
    With confirm_launch=True: prepares AND launches Chromium.

    This command does NOT write completed PoP automatically.
    Completed PoP must be written separately via display-complete-once
    by the future production runtime loop after display duration elapsed.

    Args:
        root: Agent root path (str or Path).
        source_shell_dir: Immutable shell source directory.
        runtime_shell_dir: Mutable runtime shell directory.
        chromium_bin: Chromium binary path/name (e.g. 'chromium').
        confirm_launch: If True, actually launch Chromium (default False).
        prepare_demo_fixture: If True, create demo fixture first (default False).
        stale_seconds: Max state age before stale (default 30s).
        now: Optional datetime for test time injection.
        process_launcher: Optional callable for Chromium launch (test injection).

    Returns:
        KsoVisibleRuntimeResult — always safe, never raises.
    """
    # ── Validate common args ──────────────────────────────────────
    if not isinstance(chromium_bin, str) or not chromium_bin.strip():
        return KsoVisibleRuntimeResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS_VISIBLE,
        )

    if stale_seconds <= 0:
        return KsoVisibleRuntimeResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS_VISIBLE,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoVisibleRuntimeResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS_VISIBLE,
        )

    # ── Step 1: Optional demo fixture ─────────────────────────────
    fixture_result: Optional[KsoLocalDemoFixtureResult] = None

    if prepare_demo_fixture:
        try:
            fixture_result = prepare_kso_local_demo_fixture(
                root=root,
                now=now,
            )
        except Exception:
            return KsoVisibleRuntimeResult(
                status=STATUS_ERROR,
                reason=REASON_FIXTURE_FAILED,
            )

        if fixture_result.status == FIXTURE_STATUS_ERROR:
            return KsoVisibleRuntimeResult(
                status=STATUS_ERROR,
                reason=REASON_FIXTURE_FAILED,
                fixture_ready=False,
            )

    # ── Step 2: Prepare demo + optionally launch Chromium ─────────
    try:
        chromium_result = prepare_and_maybe_launch_kso_local_chromium_demo(
            root=root,
            source_shell_dir=source_shell_dir,
            runtime_shell_dir=runtime_shell_dir,
            chromium_bin=chromium_bin,
            confirm_launch=confirm_launch,
            stale_seconds=stale_seconds,
            now=now,
            process_launcher=process_launcher,
        )
    except Exception:
        return KsoVisibleRuntimeResult(
            status=STATUS_ERROR,
            reason=REASON_PREPARE_FAILED_VISIBLE,
            fixture_ready=fixture_result.fixture_ready if fixture_result else False,
        )

    # ── Step 3: Map chromium result to visible runtime result ─────
    render_ready = (
        chromium_result.snapshot_mode == SNAPSHOT_MODE_RENDER
        and chromium_result.prepared
    )

    result = KsoVisibleRuntimeResult(
        status=(
            STATUS_OK if chromium_result.status == CHROMIUM_STATUS_OK
            else STATUS_ERROR
        ),
        fixture_ready=fixture_result.fixture_ready if fixture_result else False,
        render_ready=render_ready,
        shell_prepared=chromium_result.prepared,
        snapshot_written=(
            chromium_result.prepared
            and chromium_result.snapshot_mode in (SNAPSHOT_MODE_HOLD, SNAPSHOT_MODE_RENDER)
        ),
        launch_ready=chromium_result.launch_ready,
        launched=chromium_result.launched,
        reason=_map_reason(chromium_result.reason, render_ready),
        _chromium_result=chromium_result,
    )

    return result


def _map_reason(chromium_reason: str, render_ready: bool) -> str:
    """Map chromium runner reason to visible runtime reason."""
    if chromium_reason == REASON_PREPARED_LAUNCH_READY:
        return REASON_READY
    if chromium_reason == REASON_PREPARED_LAUNCHED:
        return REASON_LAUNCHED
    if chromium_reason == REASON_PREPARE_FAILED:
        return REASON_PREPARE_FAILED_VISIBLE
    if chromium_reason == REASON_LAUNCH_FAILED:
        return REASON_LAUNCH_FAILED_VISIBLE
    if chromium_reason == REASON_INVALID_ARGS:
        return REASON_INVALID_ARGS_VISIBLE
    # Fallback: if render_ready but reason unknown → "ready"
    if render_ready:
        return REASON_READY
    return REASON_HOLD


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_kso_visible_runtime_result(result: KsoVisibleRuntimeResult) -> str:
    """Format result as a safe human-readable string.

    NEVER contains absolute paths, file URLs, full Chromium commands,
    mediaRef values, IDs, raw JSON, exception text, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"fixture_ready: {str(result.fixture_ready).lower()}",
        f"render_ready: {str(result.render_ready).lower()}",
        f"shell_prepared: {str(result.shell_prepared).lower()}",
        f"snapshot_written: {str(result.snapshot_written).lower()}",
        f"launch_ready: {str(result.launch_ready).lower()}",
        f"launched: {str(result.launched).lower()}",
        f"reason: {result.reason}",
    ]

    output = "\n".join(lines)

    # Safety scan
    lower = output.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(
                f"Safe output contains forbidden substring '{fb}'"
            )

    return output
