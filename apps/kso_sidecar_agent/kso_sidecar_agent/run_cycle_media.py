"""KSO Sidecar Run Cycle — Media Sync Step.

Downloads missing/corrupted media files based on local manifest.
Only called in backend_enabled mode with valid manifest and token.
Media retry is NOT connected at this step.

Based on: docs/kso_sidecar_run_cycle_design.md
"""

import time as _time
from dataclasses import dataclass
from typing import Optional

from kso_sidecar_agent.http_client import HttpClientConfig, HttpClientError, SafeHttpClient
from kso_sidecar_agent.media_cache import ensure_media_dirs, quarantine_media_file, verify_media_file, write_media_atomic
from kso_sidecar_agent.media_client import MediaClient, MediaContent
from kso_sidecar_agent.run_cycle import (
    RunCycleStepResult,
    _check_forbidden,
    _redact_forbidden,
    _validate_safe_details,
)
from kso_sidecar_agent.token_state import TokenState


# ── Result ────────────────────────────────────────────────────────────

@dataclass
class CycleMediaSyncResult:
    """Result of media sync step in a run cycle. No secrets, no media bytes, no paths."""

    step: RunCycleStepResult
    media_status: str = "skipped"  # complete | incomplete | error | skipped
    items_total: int = 0
    items_cached: int = 0
    items_downloaded: int = 0
    items_missing: int = 0
    items_failed: int = 0
    cache_complete: bool = False

    def __post_init__(self) -> None:
        _check_forbidden(self.media_status, "media_status")


# ── Main ─────────────────────────────────────────────────────────────

def sync_media_for_cycle(
    root,
    token_state: TokenState,
    now: Optional[float] = None,
    http_client: Optional[SafeHttpClient] = None,
) -> CycleMediaSyncResult:
    """Download missing/corrupted media files based on local manifest.

    Args:
        root: Agent root path.
        token_state: Valid TokenState.
        now: Current timestamp.
        http_client: SafeHttpClient (builds from config if None).

    Returns:
        CycleMediaSyncResult with safe step and media statistics.
    """
    if now is None:
        now = _time.time()

    # ── Validate token ────────────────────────────────────────────
    try:
        if not token_state.is_valid(now=now):
            return CycleMediaSyncResult(
                step=RunCycleStepResult(
                    name="media",
                    status="error",
                    fatal=False,
                    message="Token expired before media sync",
                ),
                media_status="error",
            )
    except Exception as e:
        return CycleMediaSyncResult(
            step=RunCycleStepResult(
                name="media",
                status="error",
                fatal=False,
                message=f"Token validation error — {_redact_forbidden(str(e))}",
            ),
            media_status="error",
        )

    # ── Read local manifest ───────────────────────────────────────
    try:
        from kso_sidecar_agent.manifest_store import read_current_manifest as _read_mf
        manifest = _read_mf(root)
        manifest_items = manifest.get("items", [])
    except Exception as e:
        return CycleMediaSyncResult(
            step=RunCycleStepResult(
                name="media",
                status="error",
                fatal=False,
                message=f"Cannot read local manifest — {_redact_forbidden(str(e))}",
            ),
            media_status="error",
        )

    if not manifest_items:
        return CycleMediaSyncResult(
            step=RunCycleStepResult(
                name="media",
                status="ok",
                message="Manifest has no items — nothing to sync",
                safe_details={"items_total": 0, "cache_complete": True},
            ),
            media_status="complete",
            cache_complete=True,
        )

    # ── Ensure media dirs ─────────────────────────────────────────
    try:
        ensure_media_dirs(root)
    except OSError as e:
        return CycleMediaSyncResult(
            step=RunCycleStepResult(
                name="media",
                status="error",
                fatal=False,
                message=f"Failed to create media directories — {_redact_forbidden(str(e))}",
            ),
            media_status="error",
        )

    # ── Build HTTP client if not provided ─────────────────────────
    if http_client is None:
        try:
            from kso_sidecar_agent import local_config as _lc
            cfg = _lc.read_config(root)
            backend_base_url = cfg.get("backend_base_url", "")
            if not backend_base_url:
                return CycleMediaSyncResult(
                    step=RunCycleStepResult(
                        name="media", status="error", fatal=False,
                        message="Config missing backend_base_url",
                    ),
                    media_status="error",
                )
            http_config = HttpClientConfig(
                base_url=backend_base_url,
                timeout_sec=cfg.get("request_timeout_sec", 10),
                tls_verify=cfg.get("tls_verify", True),
            )
            http_client = SafeHttpClient(http_config)
        except Exception as e:
            return CycleMediaSyncResult(
                step=RunCycleStepResult(
                    name="media", status="error", fatal=False,
                    message=f"Config error — {_redact_forbidden(str(e))}",
                ),
                media_status="error",
            )

    media_client = MediaClient(http_client=http_client)

    # ── Process each item ─────────────────────────────────────────
    items_total = len(manifest_items)
    items_cached = 0
    items_downloaded = 0
    items_missing = 0
    items_failed = 0

    for item in manifest_items:
        manifest_item_id = item.get("manifest_item_id", "")
        filename = item.get("filename", "")

        # Verify existing file
        try:
            vr = verify_media_file(root, item)
        except Exception:
            vr = {"status": "error", "filename": filename}

        vstatus = vr.get("status", "error")

        if vstatus == "ok":
            # Valid existing file — skip download
            items_cached += 1
            continue

        # File is missing, invalid, or corrupted
        if vstatus == "invalid":
            # Move corrupted to quarantine, try redownload
            try:
                quarantine_media_file(root, filename, reason="sha256 or size mismatch")
            except Exception:
                pass

        # Download
        expected_sha256 = item.get("sha256", "")
        expected_size = item.get("size_bytes", 0) if item.get("size_bytes", 0) > 0 else None
        expected_ct = item.get("content_type", "")

        try:
            media_content: MediaContent = media_client.fetch_media(
                token_state,
                manifest_item_id,
                expected_sha256=expected_sha256,
                expected_size_bytes=expected_size,
                expected_content_type=expected_ct,
                now=now,
            )
        except HttpClientError as e:
            status_code = getattr(e, "status_code", 0)
            if status_code == 404:
                items_missing += 1
            else:
                items_failed += 1
            continue
        except (ValueError, RuntimeError):
            items_failed += 1
            continue

        # Write to media/current
        try:
            write_result = write_media_atomic(root, item, media_content)
            ws = write_result.get("status", "")
            if ws == "written":
                items_downloaded += 1
            else:
                # sha256/size/content_type mismatch on write
                items_failed += 1
        except (ValueError, RuntimeError, OSError):
            items_failed += 1

    # ── Build result ──────────────────────────────────────────────
    cache_complete = (items_cached + items_downloaded) == items_total

    if cache_complete:
        media_status = "complete"
    elif items_failed == 0 and items_missing > 0:
        media_status = "incomplete"
    elif items_failed > 0 or items_missing > 0:
        media_status = "incomplete"
    else:
        media_status = "complete"

    step_status = "ok" if cache_complete else "warning"

    return CycleMediaSyncResult(
        step=RunCycleStepResult(
            name="media",
            status=step_status,
            safe_details={
                "items_total": items_total,
                "items_cached": items_cached,
                "items_downloaded": items_downloaded,
                "items_missing": items_missing,
                "items_failed": items_failed,
                "cache_complete": cache_complete,
            },
        ),
        media_status=media_status,
        items_total=items_total,
        items_cached=items_cached,
        items_downloaded=items_downloaded,
        items_missing=items_missing,
        items_failed=items_failed,
        cache_complete=cache_complete,
    )
