"""Simulate a single safe media playback (show-once).

Follows kso_local_interface_contract.md.
This is a DEV TOOL. No secrets, no tokens, no network, no real UI/playback.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional

from kso_simulator import manifest_reader, pop_writer


# ── Show-once result codes ───────────────────────────────────────────

SHOW_COMPLETED = "SHOW_COMPLETED"
SHOW_BLOCKED = "SHOW_BLOCKED"
SHOW_FAILED = "SHOW_FAILED"


# ── Result dataclass ─────────────────────────────────────────────────

class ShowResult:
    """Outcome of a show-once attempt."""

    __slots__ = ("status", "reason", "device_event_id", "duration_ms", "detail")

    def __init__(
        self,
        status: str,
        reason: str = "",
        device_event_id: str = "",
        duration_ms: int = 0,
        detail: str = "",
    ) -> None:
        self.status = status             # SHOW_COMPLETED / SHOW_BLOCKED / SHOW_FAILED
        self.reason = reason             # e.g. "kso_not_idle", "media_missing", ...
        self.device_event_id = device_event_id  # set for completed
        self.duration_ms = duration_ms   # actual duration written
        self.detail = detail             # extra context (without stacktrace)


# ── SHA256 helper ────────────────────────────────────────────────────

def _compute_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ── KSO state reader ─────────────────────────────────────────────────

def _read_kso_state(root: Path) -> dict:
    status_file = root / "status" / "kso_status.json"
    if not status_file.exists():
        return {}
    try:
        return json.loads(status_file.read_text())
    except json.JSONDecodeError:
        return {}


# ── Public API ───────────────────────────────────────────────────────

def show_once(
    root: str | Path,
    manifest_item_id: str,
    duration_ms: Optional[int] = None,
) -> ShowResult:
    """Simulate one safe media playback.

    1. Check KSO state (idle + can_show_ads=true)
    2. Read manifest, find item
    3. Verify media file sha256
    4. If all safe → write completed PoP, return SHOW_COMPLETED
    5. Otherwise → return SHOW_BLOCKED or SHOW_FAILED (no PoP written)

    This function NEVER writes completed PoP when safety checks fail.
    It NEVER writes skipped/failed PoP on failure (fail-silent).
    """
    root = Path(root)

    # ── 1. Safety check: KSO state ──────────────────────────────────
    state_data = _read_kso_state(root)
    state = state_data.get("state", "unknown")
    can_show = state_data.get("can_show_ads", False)

    if state != "idle":
        return ShowResult(
            status=SHOW_BLOCKED,
            reason="kso_not_idle",
            detail=f"KSO state is '{state}' (can_show_ads={can_show}). "
                   f"Run 'set-state idle' first.",
        )
    if not can_show:
        return ShowResult(
            status=SHOW_BLOCKED,
            reason="kso_not_idle",
            detail="can_show_ads=false. Run 'set-state idle' first.",
        )

    # ── 2. Read manifest ────────────────────────────────────────────
    try:
        manifest = manifest_reader.read_manifest(root)
    except FileNotFoundError:
        return ShowResult(
            status=SHOW_FAILED,
            reason="manifest_invalid",
            detail="Manifest not found. Run 'init' and create manifest/current_manifest.json.",
        )
    except (ValueError, json.JSONDecodeError) as e:
        return ShowResult(
            status=SHOW_FAILED,
            reason="manifest_invalid",
            detail=str(e),
        )

    # ── 3. Find item in manifest ────────────────────────────────────
    target_item = None
    for item in manifest.items:
        if item.manifest_item_id == manifest_item_id:
            target_item = item
            break

    if target_item is None:
        return ShowResult(
            status=SHOW_FAILED,
            reason="item_not_found",
            detail=f"manifest_item_id '{manifest_item_id}' not found in manifest "
                   f"({manifest.items_count} items).",
        )

    # ── 4. Determine duration ──────────────────────────────────────
    ms = duration_ms if duration_ms is not None else target_item.duration_ms
    if ms < 0:
        return ShowResult(
            status=SHOW_FAILED,
            reason="media_missing",
            detail=f"duration_ms={ms} is negative.",
        )

    # ── 5. Verify media file ────────────────────────────────────────
    media_dir = root / "media" / "current"
    media_path = media_dir / target_item.filename

    # Reject symlinks
    if media_path.is_symlink():
        return ShowResult(
            status=SHOW_FAILED,
            reason="media_missing",
            detail=f"File '{target_item.filename}' is a symlink — not allowed.",
        )

    # Resolve and check path stays inside media/current
    try:
        resolved = media_path.resolve()
    except (OSError, RuntimeError):
        return ShowResult(
            status=SHOW_FAILED,
            reason="media_missing",
            detail=f"Cannot resolve path for '{target_item.filename}'.",
        )

    try:
        resolved.relative_to(media_dir)
    except ValueError:
        return ShowResult(
            status=SHOW_FAILED,
            reason="media_missing",
            detail=f"File '{target_item.filename}' escapes media/current.",
        )

    if not resolved.exists():
        return ShowResult(
            status=SHOW_FAILED,
            reason="media_missing",
            detail=f"File '{target_item.filename}' not found in media/current.",
        )

    # Compute sha256
    try:
        actual_sha = _compute_sha256(resolved)
    except OSError as e:
        return ShowResult(
            status=SHOW_FAILED,
            reason="media_missing",
            detail=f"Read error for '{target_item.filename}': {e}",
        )

    if actual_sha != target_item.sha256:
        return ShowResult(
            status=SHOW_FAILED,
            reason="hash_mismatch",
            detail=f"Expected {target_item.sha256[:12]}..., "
                   f"got {actual_sha[:12]}...",
        )

    # ── 6. All checks passed → write completed PoP ──────────────────
    try:
        event_id = pop_writer.write_pop_event(
            root=root,
            manifest_item_id=manifest_item_id,
            result="completed",
            duration_ms=ms,
        )
    except (ValueError, RuntimeError) as e:
        return ShowResult(
            status=SHOW_FAILED,
            reason="media_missing",
            detail=f"PoP write error: {e}",
        )

    return ShowResult(
        status=SHOW_COMPLETED,
        device_event_id=event_id,
        duration_ms=ms,
        detail=f"PoP completed written to pop/events.log",
    )
