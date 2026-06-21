"""KSO Sidecar PoP Eligible Batch Builder — safe in-memory candidate collection.

Reads pop/pending/player_events.jsonl, classifies each event, and collects
only eligible candidates into an in-memory batch.

NO backend send, NO file move, NO delete. Read-only batch assembly.
Only returns safe aggregates — never raw events, paths, or secrets.
"""

import json as _json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kso_sidecar_agent.pop_pickup import (
    # Constants
    POP_PENDING_DIR,
    POP_JSONL_FILE,
    ALLOWED_RECORD_KEYS,
    CLASS_DRAFT,
    CLASS_ELIGIBLE,
    CLASS_DIAGNOSTIC,
    CLASS_QUARANTINE,
    CLASS_INVALID,
    SCAN_OK,
    SCAN_WARNING,
    SCAN_ERROR,
    # Functions
    _validate_record,
    classify_pop_event,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

DEFAULT_MAX_EVENTS = 100


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopBatchCandidate:
    """A single eligible candidate for backend submission.

    Contains only safe fields from the player event record.
    Never contains filename, manifest_item_id, sha256, paths, or secrets.
    """

    schema_version: int = 1
    event_type: str = ""
    event_status: str = ""
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: int = 0
    playback_allowed: bool = False
    session_action: str = ""
    session_reason: str = ""
    selected_order: Optional[int] = None
    selected_content_type: Optional[str] = None
    safety_state: str = ""
    result: str = ""


@dataclass
class PopBatchBuildResult:
    """Safe aggregated result of batch building.

    Never contains raw JSON, full event records, paths, secrets,
    manifest_item_id, filename, sha256, or backend URLs.
    """

    status: str = SCAN_OK            # ok | warning | error
    total_lines: int = 0
    candidate_events: int = 0
    skipped_events: int = 0          # non-eligible valid events
    invalid_events: int = 0
    quarantine_events: int = 0
    diagnostic_events: int = 0
    draft_events: int = 0
    batch_limited: bool = False
    max_events: int = DEFAULT_MAX_EVENTS


# ══════════════════════════════════════════════════════════════════════
# Candidate builder
# ══════════════════════════════════════════════════════════════════════

def _record_to_candidate(record: dict) -> PopBatchCandidate:
    """Convert a safe player event record to a PopBatchCandidate.

    Only copies ALLOWED_RECORD_KEYS. Never copies filename,
    manifest_item_id, sha256, or any forbidden fields.
    """
    return PopBatchCandidate(
        schema_version=record.get("schema_version", 1),
        event_type=record.get("event_type", ""),
        event_status=record.get("event_status", ""),
        created_at=record.get("created_at"),
        started_at=record.get("started_at"),
        ended_at=record.get("ended_at"),
        duration_ms=record.get("duration_ms", 0),
        playback_allowed=record.get("playback_allowed", False),
        session_action=record.get("session_action", ""),
        session_reason=record.get("session_reason", ""),
        selected_order=record.get("selected_order"),
        selected_content_type=record.get("selected_content_type"),
        safety_state=record.get("safety_state", ""),
        result=record.get("result", ""),
    )


# ══════════════════════════════════════════════════════════════════════
# Batch builder
# ══════════════════════════════════════════════════════════════════════

def build_pop_eligible_batch(
    root,
    max_events: int = DEFAULT_MAX_EVENTS,
) -> PopBatchBuildResult:
    """Read pending player events and build an in-memory batch of eligible candidates.

    Only events classified as CLASS_ELIGIBLE are included in the batch:
      - event_status = completed
      - safety_state = idle
      - selected_order maps to current manifest
      - media cache complete
      - schema valid, no forbidden fields

    Draft, blocked, failed, invalid, and quarantine events are NOT included.

    Read-only: never deletes, moves, or sends to backend.
    Only returns safe aggregates — never raw events, paths, or secrets.

    Args:
        root: Agent root path (str or Path).
        max_events: Maximum number of candidates in batch (default 100).

    Returns:
        PopBatchBuildResult — always safe, never raises.
    """
    root = Path(root)
    jsonl_path = root / POP_PENDING_DIR / POP_JSONL_FILE

    result = PopBatchBuildResult(max_events=max_events)

    if max_events <= 0:
        result.status = SCAN_ERROR
        return result

    # ── File missing → empty ok result ──────────────────────────
    if not jsonl_path.exists() or not jsonl_path.is_file():
        result.status = SCAN_OK
        return result

    # ── Read manifest for mapping ───────────────────────────────
    manifest_items: Optional[list] = None
    try:
        from kso_sidecar_agent.manifest_store import read_current_manifest
        manifest_data = read_current_manifest(root)
        manifest_items = manifest_data.get("items", [])
    except Exception:
        # Legacy format failed — try KSO safe format
        try:
            from kso_sidecar_agent.kso_safe_manifest_context import (
                read_kso_safe_manifest_context,
                get_manifest_items_for_classifier,
            )
            ctx = read_kso_safe_manifest_context(root)
            if ctx.format == "kso_safe":
                manifest_items = get_manifest_items_for_classifier(ctx)
        except Exception:
            manifest_items = None

    # ── Check media cache completeness ──────────────────────────
    media_cache_complete: Optional[bool] = None
    try:
        from kso_sidecar_agent.media_cache import media_cache_status
        mc_status = media_cache_status(root, manifest_items=manifest_items)
        items_total = mc_status.get("items_total", 0)
        items_cached = mc_status.get("items_cached", 0)
        if items_total > 0 and items_cached == items_total:
            media_cache_complete = True
        elif items_total > 0:
            media_cache_complete = False
        else:
            media_cache_complete = None
    except Exception:
        media_cache_complete = None

    # Legacy media check incomplete — try KSO-aware check
    if media_cache_complete is not True and manifest_items is not None:
        from kso_sidecar_agent.pop_pickup import _kso_media_cache_check
        kso_check = _kso_media_cache_check(root, manifest_items)
        if kso_check is True:
            media_cache_complete = True

    # ── Read and process lines ──────────────────────────────────
    try:
        raw = jsonl_path.read_text(encoding="utf-8")
    except Exception:
        result.status = SCAN_ERROR
        return result

    lines = raw.split("\n")
    candidates: list[PopBatchCandidate] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        result.total_lines += 1

        # Parse JSON
        try:
            record = _json.loads(stripped)
        except Exception:
            result.invalid_events += 1
            continue

        if not isinstance(record, dict):
            result.invalid_events += 1
            continue

        # Validate
        validation_error = _validate_record(record)
        if validation_error is not None:
            result.invalid_events += 1
            continue

        # Classify
        classification = classify_pop_event(
            record,
            manifest_items=manifest_items,
            media_cache_complete=media_cache_complete,
        )

        if classification.classification == CLASS_ELIGIBLE:
            # Check max_events limit
            if len(candidates) >= max_events:
                result.batch_limited = True
                break

            candidate = _record_to_candidate(record)
            candidates.append(candidate)
        elif classification.classification == CLASS_DRAFT:
            result.draft_events += 1
        elif classification.classification == CLASS_DIAGNOSTIC:
            result.diagnostic_events += 1
        elif classification.classification == CLASS_QUARANTINE:
            result.quarantine_events += 1
        else:
            result.invalid_events += 1

    result.candidate_events = len(candidates)
    result.skipped_events = result.draft_events + result.diagnostic_events + result.quarantine_events

    # ── Determine status ────────────────────────────────────────
    if result.invalid_events > 0 and result.candidate_events == 0:
        result.status = SCAN_ERROR
    elif result.invalid_events > 0 or result.quarantine_events > 0:
        result.status = SCAN_WARNING
    else:
        result.status = SCAN_OK

    return result
