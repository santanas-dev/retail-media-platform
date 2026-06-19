"""KSO Sidecar Run Cycle — Media Cache Report Step.

Sends media cache report to backend via MediaCacheReportClient.
Only called in backend_enabled mode with valid manifest and token.
Report retry is NOT connected at this step.

Based on: docs/kso_sidecar_run_cycle_design.md
"""

import time as _time
from dataclasses import dataclass
from typing import Optional

from kso_sidecar_agent.http_client import HttpClientConfig, HttpClientError, SafeHttpClient
from kso_sidecar_agent.media_cache_report_client import (
    MediaCacheReportClient,
    MediaCacheReportPayload,
    MediaCacheReportResult,
    build_media_cache_report_payload,
)
from kso_sidecar_agent.run_cycle import (
    RunCycleStepResult,
    _check_forbidden,
    _redact_forbidden,
    _validate_safe_details,
)
from kso_sidecar_agent.token_state import TokenState


# ── Result ────────────────────────────────────────────────────────────

@dataclass
class CycleMediaReportResult:
    """Result of media cache report step. No secrets, no full report, no paths."""

    step: RunCycleStepResult
    report_status: str = "skipped"  # sent | error | skipped
    items_total: int = 0
    cached_count: int = 0
    missing_count: int = 0
    failed_count: int = 0
    invalid_hash_count: int = 0
    backend_status: str = ""

    def __post_init__(self) -> None:
        _check_forbidden(self.report_status, "report_status")
        if self.backend_status:
            _check_forbidden(self.backend_status, "backend_status")


# ── Main ─────────────────────────────────────────────────────────────

def send_media_cache_report_for_cycle(
    root,
    token_state: TokenState,
    now: Optional[float] = None,
    http_client: Optional[SafeHttpClient] = None,
) -> CycleMediaReportResult:
    """Build and send a media cache report to backend.

    Args:
        root: Agent root path.
        token_state: Valid TokenState.
        now: Current timestamp.
        http_client: SafeHttpClient (builds from config if None).

    Returns:
        CycleMediaReportResult with safe step and report status.
    """
    if now is None:
        now = _time.time()

    # ── Validate token ────────────────────────────────────────────
    try:
        if not token_state.is_valid(now=now):
            return CycleMediaReportResult(
                step=RunCycleStepResult(
                    name="report",
                    status="error",
                    fatal=False,
                    message="Token expired before media cache report",
                ),
                report_status="error",
            )
    except Exception as e:
        return CycleMediaReportResult(
            step=RunCycleStepResult(
                name="report",
                status="error",
                fatal=False,
                message=f"Token validation error — {_redact_forbidden(str(e))}",
            ),
            report_status="error",
        )

    # ── Build payload ─────────────────────────────────────────────
    try:
        payload: MediaCacheReportPayload = build_media_cache_report_payload(root)
    except FileNotFoundError:
        # No local manifest — cannot build report
        return CycleMediaReportResult(
            step=RunCycleStepResult(
                name="report",
                status="skipped",
                message="Skipped — local manifest missing, cannot build report",
            ),
            report_status="skipped",
        )
    except (ValueError, RuntimeError) as e:
        return CycleMediaReportResult(
            step=RunCycleStepResult(
                name="report",
                status="error",
                fatal=False,
                message=f"Cannot build media report — {_redact_forbidden(str(e))}",
            ),
            report_status="error",
        )

    # Handle empty manifest (no items)
    if not payload.items:
        return CycleMediaReportResult(
            step=RunCycleStepResult(
                name="report",
                status="ok",
                message="No items in manifest — nothing to report",
                safe_details={"items_total": 0},
            ),
            report_status="sent",
        )

    # ── Build HTTP client if not provided ─────────────────────────
    if http_client is None:
        try:
            from kso_sidecar_agent import local_config as _lc
            cfg = _lc.read_config(root)
            backend_base_url = cfg.get("backend_base_url", "")
            if not backend_base_url:
                return CycleMediaReportResult(
                    step=RunCycleStepResult(
                        name="report", status="error", fatal=False,
                        message="Config missing backend_base_url",
                    ),
                    report_status="error",
                )
            http_config = HttpClientConfig(
                base_url=backend_base_url,
                timeout_sec=cfg.get("request_timeout_sec", 10),
                tls_verify=cfg.get("tls_verify", True),
            )
            http_client = SafeHttpClient(http_config)
        except Exception as e:
            return CycleMediaReportResult(
                step=RunCycleStepResult(
                    name="report", status="error", fatal=False,
                    message=f"Config error — {_redact_forbidden(str(e))}",
                ),
                report_status="error",
            )

    # ── Send report ───────────────────────────────────────────────
    report_client = MediaCacheReportClient(http_client=http_client)

    try:
        result: MediaCacheReportResult = report_client.send_report(
            token_state, payload, now=now,
        )
    except HttpClientError as e:
        status_code = getattr(e, "status_code", 0)
        retryable = getattr(e, "retryable", False)
        return CycleMediaReportResult(
            step=RunCycleStepResult(
                name="report",
                status="error",
                fatal=False,
                retryable=retryable,
                message=f"Report send failed ({status_code}) — {_redact_forbidden(str(e))}",
                safe_details={"status_code": status_code},
            ),
            report_status="error",
            items_total=payload.safe_summary()["items_total"],
        )
    except (ValueError, RuntimeError) as e:
        return CycleMediaReportResult(
            step=RunCycleStepResult(
                name="report",
                status="error",
                fatal=False,
                message=f"Report send failed — {_redact_forbidden(str(e))}",
            ),
            report_status="error",
            items_total=payload.safe_summary()["items_total"],
        )

    # ── Build safe result ─────────────────────────────────────────
    safe = payload.safe_summary()

    report_status = "sent" if result.accepted else "error"
    backend_status = result.backend_status or ""

    return CycleMediaReportResult(
        step=RunCycleStepResult(
            name="report",
            status="ok" if result.accepted else "error",
            safe_details={
                "report_status": report_status,
                "items_total": result.total_items,
                "cached_count": result.cached_count,
                "missing_count": result.missing_count,
                "failed_count": result.failed_count,
                "invalid_hash_count": result.invalid_hash_count,
            },
        ),
        report_status=report_status,
        items_total=result.total_items,
        cached_count=result.cached_count,
        missing_count=result.missing_count,
        failed_count=result.failed_count,
        invalid_hash_count=result.invalid_hash_count,
        backend_status=backend_status,
    )
