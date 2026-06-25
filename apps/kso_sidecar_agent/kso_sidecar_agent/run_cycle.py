"""KSO Sidecar Run Cycle — Core Skeleton with Local Readiness.

Dataclasses and functions for the unified run-cycle orchestrator.
Implements: options, step result, cycle result, status classification,
local readiness preflight, safe agent_status update with _cycle block,
auth, runtime config sync, heartbeat, manifest sync, media sync, and report steps.

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
from kso_sidecar_agent.retry_backoff import BackoffPolicy, RetryBackoffManager

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

    # Backend control
    backend_enabled: bool = False
    dev_secret_store: bool = False

    # Retry
    retry_auth: bool = False
    retry_heartbeat: bool = False
    auth_max_attempts: int = 3
    heartbeat_max_attempts: int = 3

    # Step skips
    skip_runtime_config: bool = False
    skip_heartbeat: bool = False
    skip_manifest: bool = False
    skip_media: bool = False
    skip_report: bool = False

    # Limits
    max_cycle_sec: int = 120

    def __post_init__(self) -> None:
        if not isinstance(self.max_cycle_sec, int) or self.max_cycle_sec < 1 or self.max_cycle_sec > 600:
            raise ValueError(
                f"max_cycle_sec must be 1–600, got {self.max_cycle_sec!r}"
            )
        if not isinstance(self.auth_max_attempts, int) or self.auth_max_attempts < 1 or self.auth_max_attempts > 10:
            raise ValueError(
                f"auth_max_attempts must be 1–10, got {self.auth_max_attempts!r}"
            )
        if not isinstance(self.heartbeat_max_attempts, int) or self.heartbeat_max_attempts < 1 or self.heartbeat_max_attempts > 10:
            raise ValueError(
                f"heartbeat_max_attempts must be 1–10, got {self.heartbeat_max_attempts!r}"
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
    last_auth_status: Optional[str] = None     # ok | error | skipped
    auth_attempts: int = 0
    heartbeat_status: Optional[str] = None     # sent | error | skipped
    heartbeat_attempts: int = 0
    final_heartbeat_status: Optional[str] = None  # sent | error | skipped
    final_heartbeat_attempts: int = 0
    runtime_config_status: Optional[str] = None  # updated | not_modified | missing | invalid
    manifest_status: Optional[str] = None        # updated | not_modified | no_manifest | missing | invalid
    media_report_status: Optional[str] = None     # sent | error | skipped
    media_cache_complete: bool = False
    media_items_total: int = 0
    media_items_cached: int = 0
    media_items_missing: int = 0
    media_items_failed: int = 0
    last_error_code: Optional[str] = None
    offline_ready: bool = False                    # local cache full, can play without backend
    can_play_local_content: bool = False           # manifest valid + media cache complete
    degraded_reason: Optional[str] = None           # backend_unavailable | none | local_cache_incomplete | auth_failed

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_CYCLE_STATUSES:
            raise ValueError(
                f"Invalid cycle status '{self.status}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_CYCLE_STATUSES))}"
            )
        if self.last_error_code:
            _check_forbidden(self.last_error_code, "last_error_code")
        if self.runtime_config_status:
            _check_forbidden(self.runtime_config_status, "runtime_config_status")
        if self.manifest_status:
            _check_forbidden(self.manifest_status, "manifest_status")
        if self.media_report_status:
            _check_forbidden(self.media_report_status, "media_report_status")
        if self.degraded_reason:
            _check_forbidden(self.degraded_reason, "degraded_reason")

    def safe_summary(self) -> dict:
        """Return safe metadata only — no secrets, no paths, no full IDs."""
        step_summaries = []
        for s in self.steps:
            step_summaries.append({
                "name": s.name,
                "status": s.status,
                "fatal": s.fatal,
            })

        summary = {
            "status": self.status,
            "duration_ms": self.duration_ms,
            "steps": step_summaries,
            "media_cache_complete": self.media_cache_complete,
            "media_items_total": self.media_items_total,
            "media_items_cached": self.media_items_cached,
            "media_items_failed": self.media_items_failed,
            "last_error_code": self.last_error_code,
        }
        if self.runtime_config_status:
            summary["runtime_config_status"] = self.runtime_config_status
        if self.manifest_status:
            summary["manifest_status"] = self.manifest_status
        if self.offline_ready:
            summary["offline_ready"] = self.offline_ready
        if self.can_play_local_content:
            summary["can_play_local_content"] = self.can_play_local_content
        if self.degraded_reason:
            summary["degraded_reason"] = self.degraded_reason
        return summary

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

        if self.last_auth_status:
            block["last_auth_status"] = self.last_auth_status
        if self.auth_attempts > 0:
            block["auth_attempts"] = self.auth_attempts

        if self.heartbeat_status:
            block["heartbeat_status"] = self.heartbeat_status
        if self.heartbeat_attempts > 0:
            block["heartbeat_attempts"] = self.heartbeat_attempts

        if self.final_heartbeat_status:
            block["final_heartbeat_status"] = self.final_heartbeat_status
        if self.final_heartbeat_attempts > 0:
            block["final_heartbeat_attempts"] = self.final_heartbeat_attempts

        if self.runtime_config_status:
            _check_forbidden(self.runtime_config_status, "runtime_config_status")
            block["runtime_config_status"] = self.runtime_config_status

        if self.manifest_status:
            _check_forbidden(self.manifest_status, "manifest_status")
            block["manifest_status"] = self.manifest_status

        if self.media_report_status:
            _check_forbidden(self.media_report_status, "media_report_status")
            block["media_report_status"] = self.media_report_status

        if self.offline_ready:
            block["offline_ready"] = self.offline_ready
        if self.can_play_local_content:
            block["can_play_local_content"] = self.can_play_local_content
        if self.degraded_reason:
            _check_forbidden(self.degraded_reason, "degraded_reason")
            block["degraded_reason"] = self.degraded_reason

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


# ── Local Readiness ─────────────────────────────────────────────────

def evaluate_local_readiness(root) -> dict:
    """Check all local files without any backend calls, auth, or secret reading.

    Checks:
        - root exists / initialized
        - config/agent_config.json present and valid
        - config/runtime_config.json status
        - manifest/current_manifest.json status
        - media/current cache status

    Args:
        root: Agent root path (str or Path).

    Returns:
        Dict with keys: root_exists, config_present, config_valid,
        config_error, runtime_config_present, runtime_config_valid,
        runtime_config_error, manifest_present, manifest_valid,
        manifest_error, manifest_items_count, media_status (dict or None),
        media_cache_complete.

    Never reads secret, never makes HTTP calls, never exposes paths/config.
    """
    from kso_sidecar_agent import local_config as _lc
    from kso_sidecar_agent import runtime_config_store as _rcs
    from kso_sidecar_agent import manifest_store as _ms
    from kso_sidecar_agent import media_cache as _mc

    root = Path(root)
    result: dict[str, Any] = {
        "root_exists": root.is_dir(),
        "config_present": False,
        "config_valid": False,
        "config_error": None,
        "runtime_config_present": False,
        "runtime_config_valid": False,
        "runtime_config_error": None,
        "manifest_present": False,
        "manifest_valid": False,
        "manifest_error": None,
        "manifest_items_count": 0,
        "media_status": None,
        "media_cache_complete": None,
    }

    if not result["root_exists"]:
        return result

    # ── Config ────────────────────────────────────────────────────
    try:
        cfg = _lc.config_status(root)
        result["config_present"] = cfg["present"]
        result["config_valid"] = cfg["ok"]
        if not cfg["ok"] and cfg.get("error"):
            result["config_error"] = _redact_forbidden(str(cfg["error"]))
    except Exception as e:
        result["config_error"] = _redact_forbidden(str(e))

    # ── Runtime config ────────────────────────────────────────────
    try:
        rc = _rcs.runtime_config_status(root)
        result["runtime_config_present"] = rc["present"]
        result["runtime_config_valid"] = rc["ok"]
        if not rc["ok"] and rc.get("error"):
            result["runtime_config_error"] = _redact_forbidden(str(rc["error"]))
    except Exception as e:
        result["runtime_config_error"] = _redact_forbidden(str(e))

    # ── Manifest ─────────────────────────────────────────────────
    try:
        ms = _ms.manifest_store_status(root)
        result["manifest_present"] = ms["present"]
        result["manifest_valid"] = ms["validation_status"] == "ok"
        if not result["manifest_valid"] and ms.get("validation_status"):
            result["manifest_error"] = ms["validation_status"]
        if ms["present"] and ms["validation_status"] == "ok":
            result["manifest_items_count"] = ms["items_count"]
    except Exception as e:
        result["manifest_error"] = _redact_forbidden(str(e))

    # ── Media cache ──────────────────────────────────────────────
    if result["manifest_present"] and result["manifest_valid"]:
        try:
            manifest = _ms.read_current_manifest(root)
            items = manifest.get("items", [])
            if items:
                mc_status = _mc.media_cache_status(root, manifest_items=items)
                result["media_status"] = mc_status
                result["media_cache_complete"] = mc_status.get("cache_complete", False)
        except Exception as e:
            result["media_cache_complete"] = False
            result["media_status"] = {
                "error": _redact_forbidden(str(e)),
                "cache_complete": False,
                "items_total": 0,
            }

    return result


def _build_local_readiness_steps(root) -> list[RunCycleStepResult]:
    """Build step results for local readiness checks. No backend, no auth, no secret.

    Returns list of RunCycleStepResult:
        - local_config: ok/warning/error (fatal on missing/invalid config)
        - runtime_config: ok/warning (non-fatal)
        - manifest: ok/warning/error (fatal on invalid, non-fatal on missing)
        - media_cache: ok/warning/error/skipped
    """
    steps: list[RunCycleStepResult] = []
    readiness = evaluate_local_readiness(root)

    # ── Step: local_config ────────────────────────────────────────
    if not readiness["config_present"]:
        steps.append(RunCycleStepResult(
            name="local_config",
            status="error",
            fatal=True,
            message="Config file missing — cannot determine backend URL",
        ))
    elif not readiness["config_valid"]:
        steps.append(RunCycleStepResult(
            name="local_config",
            status="error",
            fatal=True,
            message=readiness.get("config_error", "Config invalid"),
        ))
    else:
        steps.append(RunCycleStepResult(
            name="local_config",
            status="ok",
            safe_details={"present": True, "valid": True},
        ))

    # ── Step: runtime_config ─────────────────────────────────────
    if readiness["runtime_config_present"] and readiness["runtime_config_valid"]:
        steps.append(RunCycleStepResult(
            name="runtime_config",
            status="ok",
            safe_details={"present": True, "valid": True},
        ))
    elif not readiness["runtime_config_present"]:
        steps.append(RunCycleStepResult(
            name="runtime_config",
            status="warning",
            message="Runtime config missing — will be fetched from backend",
            safe_details={"present": False, "valid": False},
        ))
    else:
        steps.append(RunCycleStepResult(
            name="runtime_config",
            status="warning",
            message=f"Runtime config invalid — {readiness.get('runtime_config_error', '')}",
            safe_details={"present": True, "valid": False},
        ))

    # ── Step: manifest ───────────────────────────────────────────
    if readiness["manifest_present"] and readiness["manifest_valid"]:
        steps.append(RunCycleStepResult(
            name="manifest",
            status="ok",
            safe_details={
                "present": True,
                "valid": True,
                "items_total": readiness.get("manifest_items_count", 0),
            },
        ))
    elif not readiness["manifest_present"]:
        steps.append(RunCycleStepResult(
            name="manifest",
            status="warning",
            message="Local manifest missing — will be fetched from backend",
            safe_details={"present": False, "valid": False},
        ))
    else:
        steps.append(RunCycleStepResult(
            name="manifest",
            status="error",
            fatal=False,  # non-fatal: can be re-fetched from backend
            message=f"Local manifest invalid — {readiness.get('manifest_error', '')}",
            safe_details={"present": True, "valid": False},
        ))

    # ── Step: media_cache ─────────────────────────────────────────
    if not readiness["manifest_valid"] or not readiness["manifest_present"]:
        # Cannot check media cache without valid manifest
        steps.append(RunCycleStepResult(
            name="media_cache",
            status="skipped",
            message="Skipped — manifest missing or invalid",
            safe_details={"reason": "no_valid_manifest"},
        ))
    else:
        media_status = readiness.get("media_status") or {}
        items_total = media_status.get("items_total", 0)
        items_cached = media_status.get("items_cached", 0)
        items_missing = media_status.get("items_missing", 0)
        invalid_hash = media_status.get("items_invalid_hash", 0)
        invalid_size = media_status.get("items_invalid_size", 0)
        cache_complete = media_status.get("cache_complete", False)

        if cache_complete:
            steps.append(RunCycleStepResult(
                name="media_cache",
                status="ok",
                safe_details={
                    "items_total": items_total,
                    "items_cached": items_cached,
                    "cache_complete": True,
                },
            ))
        elif invalid_hash > 0 or invalid_size > 0:
            steps.append(RunCycleStepResult(
                name="media_cache",
                status="error",
                fatal=False,  # non-fatal: can be re-downloaded
                message=f"{invalid_hash + invalid_size} files corrupted — need re-download",
                safe_details={
                    "items_total": items_total,
                    "items_cached": items_cached,
                    "items_missing": items_missing,
                    "invalid_hash": invalid_hash,
                    "invalid_size": invalid_size,
                    "cache_complete": False,
                },
            ))
        elif items_total == 0:
            steps.append(RunCycleStepResult(
                name="media_cache",
                status="ok",
                message="Manifest has no items",
                safe_details={"items_total": 0, "cache_complete": True},
            ))
        else:
            steps.append(RunCycleStepResult(
                name="media_cache",
                status="warning",
                message=f"{items_missing} files missing — will be downloaded",
                safe_details={
                    "items_total": items_total,
                    "items_cached": items_cached,
                    "items_missing": items_missing,
                    "cache_complete": False,
                },
            ))

    return steps


def _is_local_ready(readiness: dict) -> bool:
    """Check if the local state is sufficient for KSO to operate (degraded mode).

    Local-ready means: valid config + valid manifest + complete media cache.
    """
    return (
        readiness.get("config_valid", False) and
        readiness.get("manifest_valid", False) and
        readiness.get("media_cache_complete", False) is True
    )


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
        from kso_player.timestamp_utils import parse_iso_utc
        started_dt = parse_iso_utc(started_ts)
        finished_dt = parse_iso_utc(finished_at)
        if started_dt is None or finished_dt is None:
            duration_ms = 0.0
        else:
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

    # Derive runtime_config_status and manifest_status from steps
    runtime_config_status = None
    manifest_status = None
    for s in steps:
        if s.name == "runtime_config":
            if s.status == "ok":
                runtime_config_status = "valid"
            elif s.status == "warning":
                runtime_config_status = "missing" if s.safe_details.get("present") is False else "invalid"
            elif s.status == "error":
                runtime_config_status = "invalid"
        elif s.name == "manifest":
            if s.status == "ok":
                manifest_status = "valid"
            elif s.status == "warning":
                manifest_status = "missing" if s.safe_details.get("present") is False else "invalid"
            elif s.status == "error":
                manifest_status = "invalid"

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
        runtime_config_status=runtime_config_status,
        manifest_status=manifest_status,
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


# ── Degraded / offline fallback ──────────────────────────────────────

def _is_degradable_backend_error(auth_result) -> bool:
    """Check if the auth failure is a backend-unavailable error (not credentials)."""
    step = auth_result.step if auth_result else None
    if step is None or step.status != "error":
        return False
    return step.retryable and step.fatal


def _check_local_content_ready(root) -> bool:
    """Check if local manifest + media cache is complete (can serve content offline)."""
    try:
        from kso_sidecar_agent.manifest_store import read_current_manifest as _rm
        from kso_sidecar_agent.media_cache import media_cache_status as _mcs
        manifest = _rm(root)
        items = manifest.get("items", [])
        if not items:
            return False
        mc = _mcs(root, manifest_items=items)
        return mc.get("cache_complete", False)
    except Exception:
        return False


def _apply_degraded_fallback(root, result, options, auth_result) -> None:
    """If backend is unreachable but local cache is complete, override to degraded."""
    if not options.backend_enabled:
        return
    if result.status != "error":
        return
    if not _is_degradable_backend_error(auth_result):
        return
    if not _check_local_content_ready(root):
        result.degraded_reason = "local_cache_incomplete"
        return
    result.status = "degraded"
    result.offline_ready = True
    result.can_play_local_content = True
    result.degraded_reason = "backend_unavailable"


def run_once(
    root,
    options: Optional[RunCycleOptions] = None,
    now: Optional[float] = None,
) -> RunCycleResult:
    """Execute one run cycle — with local readiness, auth, runtime config, heartbeat, manifest, and media sync.

    On this step:
    - Preflight: validate root + local readiness checks
    - Checks config, runtime_config, manifest, media_cache on DISK
    - Backend-enabled mode: auth → runtime config → heartbeat → manifest → media
    - NO media cache report
    - NO second/final heartbeat
    - Returns safe RunCycleResult.

    Args:
        root: Agent root path.
        options: RunCycleOptions.
        now: Current timestamp.

    Returns:
        RunCycleResult — reflects local readiness state.
    """
    if now is None:
        now = _time.time()

    if options is None:
        options = RunCycleOptions()

    ctx = build_run_cycle_context(root, options, now=now)

    steps: list[RunCycleStepResult] = []

    # ── Preflight: root exists ────────────────────────────────────
    root_path = Path(str(root))
    if not root_path.is_dir():
        steps.append(RunCycleStepResult(
            name="preflight",
            status="error",
            fatal=True,
            message=f"Agent root does not exist: {root}",
        ))
        result = build_cycle_result(ctx, steps, now=now)
        try:
            update_cycle_status(root, result)
        except (OSError, ValueError):
            pass
        return result

    # Ensure status directory
    status_dir = root_path / "status"
    if not status_dir.is_dir():
        try:
            status_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            steps.append(RunCycleStepResult(
                name="preflight",
                status="error",
                fatal=True,
                message=_redact_forbidden(str(e)),
            ))
            result = build_cycle_result(ctx, steps, now=now)
            return result

    steps.append(RunCycleStepResult(
        name="preflight",
        status="ok",
        message="Agent root exists and is writable",
    ))

    # ── Local readiness checks ────────────────────────────────────
    try:
        local_steps = _build_local_readiness_steps(root)
        steps.extend(local_steps)
    except Exception as e:
        steps.append(RunCycleStepResult(
            name="local_readiness",
            status="error",
            fatal=False,
            message=_redact_forbidden(f"Local readiness check failed: {e}"),
        ))

    # ── Auth step (only when backend_enabled) ──────────────────────
    from kso_sidecar_agent.run_cycle_auth import authenticate_for_cycle as _auth_for_cycle

    auth_result = _auth_for_cycle(root, options, now=now)
    steps.append(auth_result.step)

    # ── Runtime config sync (backend_enabled + auth ok) ────────────
    from kso_sidecar_agent.run_cycle_runtime_config import (
        sync_runtime_config_for_cycle as _sync_rc,
    )

    rc_result = None
    # When backend enabled, replace local readiness runtime_config step with sync result
    if options.backend_enabled:
        steps = [s for s in steps if s.name != "runtime_config"]

    if options.backend_enabled and auth_result.token_state is not None and auth_result.step.status == "ok":
        try:
            rc_result = _sync_rc(root, auth_result.token_state, now=now)
            steps.append(rc_result.step)
        except Exception as e:
            steps.append(RunCycleStepResult(
                name="runtime_config",
                status="error",
                fatal=False,
                message=_redact_forbidden(f"Runtime config sync error: {e}"),
            ))
    elif options.backend_enabled and auth_result.step.status == "error":
        steps.append(RunCycleStepResult(
            name="runtime_config",
            status="skipped",
            message="Skipped — auth failed",
        ))

    # ── Heartbeat step (backend_enabled + auth ok) ──────────────────
    from kso_sidecar_agent.run_cycle_heartbeat import (
        send_heartbeat_for_cycle as _send_hb,
        _build_heartbeat_status_hint as _hb_hint,
    )

    hb_result = None
    if options.backend_enabled and auth_result.token_state is not None and auth_result.step.status == "ok":
        hb_hint = _hb_hint(True, rc_result.config_status if rc_result else None)
        hb_retry = None
        if options.retry_heartbeat:
            hb_policy = BackoffPolicy(max_attempts=options.heartbeat_max_attempts)
            hb_retry = RetryBackoffManager(hb_policy)
        try:
            hb_result = _send_hb(
                root, auth_result.token_state,
                cycle_status_hint=hb_hint,
                now=now,
                retry_manager=hb_retry,
            )
            steps.append(hb_result.step)
        except Exception as e:
            steps.append(RunCycleStepResult(
                name="heartbeat",
                status="error",
                fatal=False,
                message=_redact_forbidden(f"Heartbeat error: {e}"),
            ))
    elif options.backend_enabled and auth_result.step.status == "error":
        steps.append(RunCycleStepResult(
            name="heartbeat",
            status="skipped",
            message="Skipped — auth failed",
        ))

    # ── Manifest step (backend_enabled + auth ok) ───────────────────
    # When backend enabled, replace local readiness manifest step with sync result
    if options.backend_enabled:
        steps = [s for s in steps if s.name != "manifest"]

    from kso_sidecar_agent.run_cycle_manifest import (
        sync_manifest_for_cycle as _sync_manifest,
    )

    manifest_result = None
    if options.backend_enabled and auth_result.token_state is not None and auth_result.step.status == "ok":
        try:
            manifest_result = _sync_manifest(root, auth_result.token_state, now=now)
            steps.append(manifest_result.step)
        except Exception as e:
            steps.append(RunCycleStepResult(
                name="manifest",
                status="error",
                fatal=False,
                message=_redact_forbidden(f"Manifest sync error: {e}"),
            ))
    elif options.backend_enabled and auth_result.step.status == "error":
        steps.append(RunCycleStepResult(
            name="manifest",
            status="skipped",
            message="Skipped — auth failed",
        ))

    # ── Media sync step (backend_enabled + auth ok + manifest valid) ──
    # When backend enabled, replace local readiness media_cache step with sync result
    if options.backend_enabled:
        steps = [s for s in steps if s.name != "media_cache"]

    from kso_sidecar_agent.run_cycle_media import (
        sync_media_for_cycle as _sync_media,
    )

    media_sync_result = None
    if options.backend_enabled and auth_result.token_state is not None and auth_result.step.status == "ok":
        try:
            media_sync_result = _sync_media(root, auth_result.token_state, now=now)
            steps.append(media_sync_result.step)
        except Exception as e:
            steps.append(RunCycleStepResult(
                name="media",
                status="error",
                fatal=False,
                message=_redact_forbidden(f"Media sync error: {e}"),
            ))
    elif options.backend_enabled and auth_result.step.status == "error":
        steps.append(RunCycleStepResult(
            name="media",
            status="skipped",
            message="Skipped — auth failed",
        ))

    # ── Media report step (backend_enabled + auth ok) ────────────────
    from kso_sidecar_agent.run_cycle_media_report import (
        send_media_cache_report_for_cycle as _send_report,
    )

    report_result = None
    if options.backend_enabled and auth_result.token_state is not None and auth_result.step.status == "ok":
        try:
            report_result = _send_report(root, auth_result.token_state, now=now)
            steps.append(report_result.step)
        except Exception as e:
            steps.append(RunCycleStepResult(
                name="report",
                status="error",
                fatal=False,
                message=_redact_forbidden(f"Media report error: {e}"),
            ))
    elif options.backend_enabled and auth_result.step.status == "error":
        steps.append(RunCycleStepResult(
            name="report",
            status="skipped",
            message="Skipped — auth failed",
        ))

    # ── Final heartbeat step (backend_enabled + auth ok) ─────────────
    final_hb_result = None
    if options.backend_enabled and auth_result.token_state is not None and auth_result.step.status == "ok":
        # Build final status hint from all step results
        _has_fatal = any(s.fatal and s.status == "error" for s in steps)
        _has_warning = any(
            s.status in ("warning", "error") for s in steps
        )
        _media_incomplete = (
            media_sync_result is not None and not media_sync_result.cache_complete
        )
        if _has_fatal:
            final_hb_hint = "error"
        elif _has_warning or _media_incomplete:
            final_hb_hint = "warning"
        else:
            final_hb_hint = "ok"

        try:
            final_hb_result = _send_hb(
                root, auth_result.token_state,
                cycle_status_hint=final_hb_hint,
                now=now,
            )
            steps.append(final_hb_result.step)
        except Exception as e:
            steps.append(RunCycleStepResult(
                name="heartbeat",
                status="error",
                fatal=False,
                message=_redact_forbidden(f"Final heartbeat error: {e}"),
            ))
    elif options.backend_enabled and auth_result.step.status == "error":
        steps.append(RunCycleStepResult(
            name="heartbeat",
            status="skipped",
            message="Skipped — auth failed",
        ))

    # ── Build result ───────────────────────────────────────────────
    # In backend mode: use media sync result instead of local readiness scan
    if options.backend_enabled and media_sync_result is not None:
        media_status = {
            "cache_complete": media_sync_result.cache_complete,
            "items_total": media_sync_result.items_total,
            "items_cached": media_sync_result.items_cached + media_sync_result.items_downloaded,
            "items_missing": media_sync_result.items_missing,
            "items_invalid_hash": 0,
            "items_invalid_size": 0,
        }
    else:
        try:
            readiness = evaluate_local_readiness(root)
            media_status = readiness.get("media_status")
        except Exception:
            media_status = None

    result = build_cycle_result(ctx, steps, now=now, media_status=media_status)

    # ── Inject auth metadata into result ───────────────────────────
    if auth_result.step.status == "ok":
        result.last_auth_status = "ok"
    elif auth_result.step.status == "skipped":
        result.last_auth_status = "skipped"
    elif auth_result.step.status == "error":
        result.last_auth_status = "error"
    result.auth_attempts = auth_result.attempts

    # ── Inject runtime config metadata ─────────────────────────────
    if rc_result is not None:
        result.runtime_config_status = rc_result.config_status

    # ── Inject heartbeat metadata into result ──────────────────────
    if hb_result is not None:
        result.heartbeat_status = hb_result.heartbeat_status
        result.heartbeat_attempts = hb_result.attempts
    elif options.backend_enabled and auth_result.step.status == "error":
        result.heartbeat_status = "skipped"

    # ── Inject manifest metadata into result ───────────────────────
    if manifest_result is not None:
        result.manifest_status = manifest_result.manifest_status
        result.media_items_total = manifest_result.items_count
    elif options.backend_enabled and auth_result.step.status == "error":
        result.manifest_status = "skipped"

    # ── Inject media sync metadata into result ─────────────────────
    if media_sync_result is not None:
        result.media_cache_complete = media_sync_result.cache_complete
        result.media_items_total = media_sync_result.items_total
        result.media_items_cached = media_sync_result.items_cached + media_sync_result.items_downloaded
        result.media_items_missing = media_sync_result.items_missing
        result.media_items_failed = media_sync_result.items_failed

    # ── Inject media report metadata into result ───────────────────
    if report_result is not None:
        result.media_report_status = report_result.report_status
    elif options.backend_enabled and auth_result.step.status == "error":
        result.media_report_status = "skipped"

    # ── Inject final heartbeat metadata into result ────────────────
    if final_hb_result is not None:
        result.final_heartbeat_status = final_hb_result.heartbeat_status
        result.final_heartbeat_attempts = final_hb_result.attempts
    elif options.backend_enabled and auth_result.step.status == "error":
        result.final_heartbeat_status = "skipped"

    # ── Degraded / offline fallback ─────────────────────────────────
    _apply_degraded_fallback(root, result, options, auth_result)

    # ── Update agent_status ────────────────────────────────────────
    try:
        update_cycle_status(root, result)
    except (OSError, ValueError):
        pass  # non-fatal: status update failure shouldn't block

    return result
