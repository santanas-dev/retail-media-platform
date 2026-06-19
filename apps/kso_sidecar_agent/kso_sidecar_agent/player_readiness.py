"""KSO Sidecar Player Readiness Snapshot.

Read-only check: can the KSO Player show local content right now?
No backend calls, no secret reading, no auth, no token.
This is the handoff contract for the future KSO Player integration.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kso_sidecar_agent.agent_status import read_status
from kso_sidecar_agent.manifest_store import manifest_store_status, read_current_manifest
from kso_sidecar_agent.media_cache import media_cache_status

# ── Safe reason constants ──────────────────────────────────────────
REASON_READY = "ready"
REASON_MANIFEST_MISSING = "manifest_missing"
REASON_MANIFEST_INVALID = "manifest_invalid"
REASON_MEDIA_INCOMPLETE = "media_incomplete"
REASON_MEDIA_CORRUPTED = "media_corrupted"
REASON_NO_MEDIA_ITEMS = "no_media_items"

ALLOWED_REASONS = frozenset({
    REASON_READY,
    REASON_MANIFEST_MISSING,
    REASON_MANIFEST_INVALID,
    REASON_MEDIA_INCOMPLETE,
    REASON_MEDIA_CORRUPTED,
    REASON_NO_MEDIA_ITEMS,
})


@dataclass
class PlayerReadinessSnapshot:
    """Safe snapshot of local content readiness for the KSO Player."""

    ready: bool = False
    can_play_local_content: bool = False
    reason: str = REASON_READY
    manifest_status: Optional[str] = None      # ok | missing | error
    media_cache_complete: bool = False
    media_items_total: int = 0
    media_items_cached: int = 0
    media_items_missing: int = 0
    media_items_failed: int = 0
    last_cycle_status: Optional[str] = None     # from _cycle
    offline_ready: Optional[bool] = None        # from _cycle

    def as_safe_dict(self) -> dict:
        """Return safe dict for output. No paths, IDs, secrets."""
        d = {
            "ready": self.ready,
            "can_play_local_content": self.can_play_local_content,
            "reason": self.reason,
            "manifest_status": self.manifest_status,
            "media_cache_complete": self.media_cache_complete,
            "media_items_total": self.media_items_total,
            "media_items_cached": self.media_items_cached,
            "media_items_missing": self.media_items_missing,
            "media_items_failed": self.media_items_failed,
        }
        if self.last_cycle_status:
            d["last_cycle_status"] = self.last_cycle_status
        if self.offline_ready is not None:
            d["offline_ready"] = self.offline_ready
        return d


def build_player_readiness_snapshot(root) -> PlayerReadinessSnapshot:
    """Build a safe player readiness snapshot from local files only.

    No backend, no auth, no secret, no token. Only reads:
      - manifest/current_manifest.json
      - media/current/
      - status/agent_status.json (_cycle)

    Args:
        root: Agent root path (str or Path).

    Returns:
        PlayerReadinessSnapshot with safe fields.
    """
    root = Path(root)

    # ── Agent status _cycle (best effort) ────────────────────────
    last_cycle_status = None
    offline_ready = None
    try:
        status = read_status(root)
        cycle = status.get("_cycle", {})
        if isinstance(cycle, dict):
            last_cycle_status = cycle.get("last_cycle_status")
            offline_ready = cycle.get("offline_ready")
    except Exception:
        pass

    # ── Manifest ─────────────────────────────────────────────────
    try:
        ms = manifest_store_status(root)
    except Exception:
        ms = {"present": False, "validation_status": "error", "items_count": 0}

    manifest_ok = ms.get("present") and ms.get("validation_status") == "ok"
    items_count = ms.get("items_count", 0)

    if not ms.get("present"):
        return PlayerReadinessSnapshot(
            ready=False, reason=REASON_MANIFEST_MISSING,
            manifest_status="missing",
            last_cycle_status=last_cycle_status, offline_ready=offline_ready,
        )

    if not manifest_ok:
        return PlayerReadinessSnapshot(
            ready=False, reason=REASON_MANIFEST_INVALID,
            manifest_status="error",
            last_cycle_status=last_cycle_status, offline_ready=offline_ready,
        )

    if items_count == 0:
        return PlayerReadinessSnapshot(
            ready=False, reason=REASON_NO_MEDIA_ITEMS,
            manifest_status="ok",
            last_cycle_status=last_cycle_status, offline_ready=offline_ready,
        )

    # ── Media ────────────────────────────────────────────────────
    try:
        manifest = read_current_manifest(root)
        items = manifest.get("items", [])
    except Exception:
        return PlayerReadinessSnapshot(
            ready=False, reason=REASON_MANIFEST_INVALID,
            manifest_status="error",
            last_cycle_status=last_cycle_status, offline_ready=offline_ready,
        )

    try:
        mc = media_cache_status(root, manifest_items=items)
    except Exception:
        mc = {"items_total": 0, "items_cached": 0, "items_missing": 0,
              "items_invalid_hash": 0, "items_invalid_size": 0, "cache_complete": False}

    total = mc.get("items_total", 0)
    cached = mc.get("items_cached", 0)
    missing = mc.get("items_missing", 0)
    invalid_hash = mc.get("items_invalid_hash", 0)
    invalid_size = mc.get("items_invalid_size", 0)
    failed = invalid_hash + invalid_size
    cache_complete = mc.get("cache_complete", False)

    media_items_cached = cached
    media_items_missing = missing
    media_items_failed = failed

    can_play = cache_complete and total > 0 and missing == 0 and failed == 0

    if not cache_complete:
        if failed > 0:
            reason = REASON_MEDIA_CORRUPTED
        else:
            reason = REASON_MEDIA_INCOMPLETE
        return PlayerReadinessSnapshot(
            ready=False, reason=reason, manifest_status="ok",
            media_cache_complete=False,
            media_items_total=total, media_items_cached=cached,
            media_items_missing=missing, media_items_failed=failed,
            last_cycle_status=last_cycle_status, offline_ready=offline_ready,
        )

    return PlayerReadinessSnapshot(
        ready=True, reason=REASON_READY, manifest_status="ok",
        can_play_local_content=True, media_cache_complete=True,
        media_items_total=total, media_items_cached=cached,
        media_items_missing=0, media_items_failed=0,
        last_cycle_status=last_cycle_status, offline_ready=offline_ready,
    )
