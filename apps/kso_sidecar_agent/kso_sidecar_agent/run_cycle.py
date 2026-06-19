"""KSO Sidecar Run Cycle — Core Skeleton.

Dataclasses and functions for the future unified run-cycle orchestrator.
Skeleton only: no HTTP calls, no real clients called, no backend.
Implements: options, step result, cycle result, status classification,
and safe agent_status update with _cycle block.

Based on: docs/kso_sidecar_run_cycle_design.md
"""

import json as _json
import re as _re
import time as _time
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from kso_sidecar_agent.atomic_io import atomic_write_json
from kso_sidecar_agent.paths import AGENT_STATUS_FILE

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

ALLOWED_CYCLE_STATUSES = frozenset({"ok", "warning", "degraded", "error"})

FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "media_path", "creatives/",
    "authorization", "bearer", "device_secret", "access_token",
})

SAFE_DETAILS_KEY_RE = _re.compile(r"^[a-z][a-z0-9_]{0,31}$")


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden(value: str, field: str) -> None:
    """Raise ValueError if value contains forbidden substrings."""
    if not isinstance(value, str):
        return
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(
                f"Field '{field}' contains forbidden substring '{fb}'"
            )


def _redact_forbidden(value: str) -> str:
    """Replace forbidden substrings with [REDACTED]."""
    result = value
    lower = result.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            # Case-insensitive replacement
            idx = lower.find(fb)
            while idx != -1:
                result = result[:idx] + "[REDACTED]" + result[idx + len(fb):]
                lower = result.lower()
                idx = lower.find(fb)
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_safe_details(details: dict) -> dict:
    """Validate safe_details dict: keys must match SAFE_DETAILS_KEY_RE,
    keys and values must not contain forbidden substrings.
    Unsafe keys/values are silently excluded."""
    if not isinstance(details, dict):
        return {}
    cleaned = {}
    for key, value in details.items():
        if not isinstance(key, str) or not SAFE_DETAILS_KEY_RE.match(key):
            continue  # skip keys that don't match pattern
        # Check key for forbidden
        try:
            _check_forbidden(key, f"safe_details key '{key}'")
        except ValueError:
            continue  # skip keys with forbidden substrings
        if isinstance(value, str):
            try:
                _check_forbidden(value, f"safe_details.{key}")
            except ValueError:
                continue  # skip values with forbidden substrings
            cleaned[key] = value
        elif isinstance(value, (int, float, bool)) or value is None:
            cleaned[key] = value
        else:
            cleaned[key] = str(value)[:200]  # truncate
    return cleaned


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class RunCycleOptions:
    """Options for a single run cycle. No secrets, no backend calls."""

    retry_auth: bool = False
    retry_heartbeat: bool = False
    skip_runtime_config: bool = False
    skip_heartbeat: bool = False
    skip_manifest: bool = False
    skip_media: bool = False
    skip_report: bool = False
    max_cycle_sec: int = 120

    def __post_init__(self) -> None:
        if not isinstance(self.max_cycle_sec, int) or self.max_cycle_sec < 1 or self.max_cycle_sec > 600:
            raise ValueError(
                f"max_cycle_sec must be 1–600, got {self.max_cycle_sec!r}"
            )


@dataclass
class RunCycleStepResult:
    """Result of a single step in a run cycle."""

    name: str                          # preflight, auth, sync_runtime_config, etc.
    status: str = "ok"                 # ok | skipped | warning | error | degraded
    fatal: bool = False
    retryable: bool = False
    message: str = ""
    duration_ms: float = 0.0
    safe_details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _check_forbidden(self.name, "step.name")
        _check_forbidden(self.status, "step.status")
        if self.message:
            self.message = _redact_forbidden(self.message)
        self.safe_details = _validate_safe_details(self.safe_details)


@dataclass
class RunCycleResult:
    """Result of a single run cycle. Safe for output — never contains secrets."""

    status: str                        # ok | warning | degraded | error
    started_at: str = ""               # ISO8601
    finished_at: str = ""              # ISO8601
    duration_ms: float = 0.0
    steps: list[RunCycleStepResult] = field(default_factory=list)
    media_cache_complete: bool = False
    media_items_total: int = 0
    media_items_cached: int = 0
    media_items_missing: int = 0
    media_items_failed: int = 0
    last_error_code: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_CYCLE_STATUSES:
            raise ValueError(
                f"Invalid cycle status '{self.status}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_CYCLE_STATUSES))}"
            )
        if self.last_error_code:
            _check_forbidden(self.last_error_code, "last_error_code")

    def safe_summary(self) -> dict:
        """Return safe metadata only — no secrets, no paths, no full IDs."""
        step_summaries = []
        for s in self.steps:
            step_summaries.append({
                "name": s.name,
                "status": s.status,
                "fatal": s.fatal,
            })

        return {
            "status": self.status,
            "duration_ms": self.duration_ms,
            "steps": step_summaries,
            "media_cache_complete": self.media_cache_complete,
            "media_items_total": self.media_items_total,
            "media_items_cached": self.media_items_cached,
            "media_items_failed": self.media_items_failed,
            "last_error_code": self.last_error_code,
        }

    def _cycle_block(self) -> dict:
        """Build the _cycle block for agent_status.json. Safe — no secrets."""
        block = {
            "last_cycle_at": self.finished_at or _now_iso(),
            "last_cycle_status": self.status,
            "last_cycle_duration_ms": int(self.duration_ms),
            "media_cache_complete": self.media_cache_complete,
            "media_items_total": self.media_items_total,
            "media_items_cached": self.media_items_cached,
            "media_items_missing": self.media_items_missing,
            "media_items_failed": self.media_items_failed,
        }
        if self.last_error_code:
            block["last_error_code"] = self.last_error_code
        else:
            block["last_error_code"] = None

        # Security scan
        block_str = _json.dumps(block).lower()
        for fb in FORBIDDEN_SUBSTRINGS:
            if fb in block_str:
                raise ValueError(
                    f"_cycle_block contains forbidden substring '{fb}'"
                )
        return block


@dataclass
class RunCycleContext:
    """Minimal context for a single run cycle. No secrets, no HTTP state yet."""

    root: str
    options: RunCycleOptions
    started_at: str = ""               # ISO8601
    run_id: str = ""

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = _now_iso()
        if not self.run_id:
            self.run_id = str(_uuid.uuid4())
        _check_forbidden(self.run_id, "run_id")
        _check_forbidden(self.root, "root")


# ══════════════════════════════════════════════════════════════════════
# Functions
# ══════════════════════════════════════════════════════════════════════

def build_run_cycle_context(
    root,
    options: Optional[RunCycleOptions] = None,
    now: Optional[float] = None,
) -> RunCycleContext:
    """Create a minimal RunCycleContext. No backend calls, no secret reading.

    Args:
        root: Agent root path (str or Path).
        options: RunCycleOptions (defaults to default).
        now: Current timestamp (defaults to time.time()).

    Returns:
        RunCycleContext with safe run_id and timestamp.
    """
    if options is None:
        options = RunCycleOptions()

    root = str(root)

    _check_forbidden(root, "root")

    started_at = _now_iso()

    ctx = RunCycleContext(
        root=root,
        options=options,
        started_at=started_at,
    )

    return ctx


def classify_cycle_status(
    steps: list[RunCycleStepResult],
    media_cache_complete: Optional[bool] = None,
) -> str:
    """Determine the overall cycle status from step results.

    Rules (in priority order):
    1. Any fatal error → 'error'
    2. Any 'degraded' step (without fatal) → 'degraded'
    3. Any 'warning'/'error' step or media_cache_complete is False → 'warning'
    4. Otherwise → 'ok'

    When media_cache_complete is None (media not checked), it doesn't affect status.

    Args:
        steps: List of RunCycleStepResult from all steps.
        media_cache_complete: If True, media cache is complete.
            If False, forces 'warning' (unless fatal/degraded).
            If None, no effect on status.

    Returns:
        One of: 'ok', 'warning', 'degraded', 'error'
    """
    has_fatal = any(s.fatal and s.status == "error" for s in steps)
    if has_fatal:
        return "error"

    has_degraded = any(s.status == "degraded" for s in steps)
    if has_degraded:
        return "degraded"

    has_warning_or_error = any(
        s.status in ("warning", "error") for s in steps
    )
    if has_warning_or_error:
        return "warning"

    if media_cache_complete is False:
        return "warning"

    return "ok"


def build_cycle_result(
    context: RunCycleContext,
    steps: list[RunCycleStepResult],
    now: Optional[float] = None,
    media_status: Optional[dict] = None,
) -> RunCycleResult:
    """Build a RunCycleResult from context, steps, and optional media status.

    Args:
        context: RunCycleContext (provides started_at).
        steps: List of step results.
        now: Current timestamp (defaults to time.time()).
        media_status: Optional dict from media_cache_status():
                      {items_total, items_cached, items_missing,
                       items_invalid_hash, items_invalid_size, cache_complete}

    Returns:
        RunCycleResult with computed status, duration, and safe fields.
    """
    if now is None:
        now = _time.time()

    finished_at = _now_iso()

    # Compute duration
    started_ts = context.started_at or finished_at
    try:
        started_dt = datetime.fromisoformat(started_ts.replace("Z", "+00:00"))
        finished_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        duration_ms = (finished_dt - started_dt).total_seconds() * 1000
        if duration_ms < 0:
            duration_ms = 0.0
    except (ValueError, TypeError):
        duration_ms = 0.0

    # Media stats
    if media_status is not None:
        media_cache_complete = media_status.get("cache_complete", False)
        media_items_total = media_status.get("items_total", 0)
        media_items_cached = media_status.get("items_cached", 0)
        media_items_missing = media_status.get("items_missing", 0)
        media_items_failed = (
            media_status.get("items_invalid_hash", 0) +
            media_status.get("items_invalid_size", 0)
        )
    else:
        media_cache_complete = None
        media_items_total = 0
        media_items_cached = 0
        media_items_missing = 0
        media_items_failed = 0

    # Classify
    status = classify_cycle_status(steps, media_cache_complete=media_cache_complete)

    # Last error code
    last_error_code = None
    for s in reversed(steps):
        if s.status == "error":
            last_error_code = s.name.upper().replace(" ", "_")
            _check_forbidden(last_error_code, "last_error_code")
            break

    result = RunCycleResult(
        status=status,
        started_at=started_ts,
        finished_at=finished_at,
        duration_ms=duration_ms,
        steps=list(steps),
        media_cache_complete=bool(media_cache_complete) if media_cache_complete is not None else False,
        media_items_total=media_items_total,
        media_items_cached=media_items_cached,
        media_items_missing=media_items_missing,
        media_items_failed=media_items_failed,
        last_error_code=last_error_code,
    )

    return result


def update_cycle_status(root, result: RunCycleResult) -> dict:
    """Write the _cycle block to agent_status.json atomically.

    Preserves all existing fields in agent_status.json.
    Only adds/updates the _cycle block.
    Never writes token, secret, Authorization, paths.

    Args:
        root: Agent root path (str or Path).
        result: RunCycleResult with computed status and media stats.

    Returns:
        The full agent_status dict that was written.
    """
    root = Path(root)

    _check_forbidden(str(root), "root")

    status_path = root / AGENT_STATUS_FILE

    # Read existing status (or start with minimal)
    existing = {}
    if status_path.exists():
        try:
            raw = status_path.read_text(encoding="utf-8")
            existing = _json.loads(raw)
        except (_json.JSONDecodeError, OSError):
            existing = {}

    if not isinstance(existing, dict):
        existing = {}

    # Build _cycle block
    cycle_block = result._cycle_block()

    # Security scan on cycle block
    cycle_str = _json.dumps(cycle_block).lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in cycle_str:
            raise ValueError(
                f"_cycle_block contains forbidden substring '{fb}'"
            )

    # Merge: preserve all existing fields, add/update _cycle
    merged = dict(existing)
    merged["_cycle"] = cycle_block

    # Final security scan on merged dict
    merged_str = _json.dumps(merged).lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in merged_str:
            raise ValueError(
                f"agent_status contains forbidden substring '{fb}'"
            )

    # Atomic write
    atomic_write_json(status_path, merged)

    return merged


def run_once(
    root,
    options: Optional[RunCycleOptions] = None,
    now: Optional[float] = None,
) -> RunCycleResult:
    """Execute one run cycle — SKELETON ONLY.

    On this step:
    - Preflight: validate root, ensure dirs exist
    - NO backend calls
    - NO auth
    - NO sync operations
    - Returns safe RunCycleResult with preflight step only.

    Args:
        root: Agent root path.
        options: RunCycleOptions.
        now: Current timestamp.

    Returns:
        RunCycleResult — always succeeds (skeleton).
    """
    if now is None:
        now = _time.time()

    if options is None:
        options = RunCycleOptions()

    ctx = build_run_cycle_context(root, options, now=now)

    steps: list[RunCycleStepResult] = []

    # ── Preflight step ─────────────────────────────────────────────
    try:
        root_path = Path(str(root))
        if not root_path.is_dir():
            raise FileNotFoundError(f"Agent root does not exist: {root}")

        # Check for status directory (minimal validation)
        status_dir = root_path / "status"
        if not status_dir.is_dir():
            status_dir.mkdir(parents=True, exist_ok=True)

        steps.append(RunCycleStepResult(
            name="preflight",
            status="ok",
            message="Agent root exists and is writable",
        ))
    except Exception as e:
        steps.append(RunCycleStepResult(
            name="preflight",
            status="error",
            fatal=True,
            retryable=False,
            message=_redact_forbidden(str(e)),
        ))

    # ── Build result ───────────────────────────────────────────────
    result = build_cycle_result(ctx, steps, now=now)

    # ── Update agent_status ────────────────────────────────────────
    try:
        update_cycle_status(root, result)
    except (OSError, ValueError):
        pass  # non-fatal: status update failure shouldn't block

    return result
