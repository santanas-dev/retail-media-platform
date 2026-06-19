"""KSO Sidecar Run Cycle — Heartbeat Step.

Sends a heartbeat to backend via HeartbeatClient.
Only called in backend_enabled mode with a valid TokenState.

Based on: docs/kso_sidecar_run_cycle_design.md
"""

import time as _time
from dataclasses import dataclass
from typing import Callable, Optional

from kso_sidecar_agent.heartbeat_client import HeartbeatClient, HeartbeatPayload, HeartbeatResult
from kso_sidecar_agent.http_client import HttpClientConfig, HttpClientError, SafeHttpClient
from kso_sidecar_agent.retry_backoff import BackoffPolicy, RetryBackoffManager
from kso_sidecar_agent.run_cycle import (
    RunCycleStepResult,
    _check_forbidden,
    _redact_forbidden,
    _validate_safe_details,
)
from kso_sidecar_agent.token_state import TokenState


@dataclass
class CycleHeartbeatResult:
    step: RunCycleStepResult
    heartbeat_status: str = "skipped"  # sent | error | skipped
    attempts: int = 0
    backend_status: str = ""

    def __post_init__(self) -> None:
        _check_forbidden(self.heartbeat_status, "heartbeat_status")


def _build_heartbeat_status_hint(
    auth_ok: bool,
    rc_status: Optional[str] = None,
) -> str:
    """Determine heartbeat payload status from current cycle state."""
    if not auth_ok:
        return "error"
    if rc_status and rc_status == "error":
        return "warning"
    return "ok"


def send_heartbeat_for_cycle(
    root,
    token_state: TokenState,
    cycle_status_hint: Optional[str] = None,
    now: Optional[float] = None,
    http_client: Optional[SafeHttpClient] = None,
    retry_manager: Optional[RetryBackoffManager] = None,
) -> CycleHeartbeatResult:
    """Send a heartbeat as part of a run cycle.

    Args:
        root: Agent root path.
        token_state: Valid TokenState.
        cycle_status_hint: "ok" | "warning" | "error" — heartbeat payload status.
        now: Current timestamp.
        http_client: SafeHttpClient (builds from config if None).
        retry_manager: Optional RetryBackoffManager.
        sleep_fn: Sleep function for retry delays.

    Returns:
        CycleHeartbeatResult with safe step and heartbeat status.
    """
    if now is None:
        now = _time.time()

    if cycle_status_hint is None:
        cycle_status_hint = "ok"

    # ── Validate token ────────────────────────────────────────────
    try:
        if not token_state.is_valid(now=now):
            return CycleHeartbeatResult(
                step=RunCycleStepResult(
                    name="heartbeat",
                    status="error",
                    fatal=False,
                    message="Token expired before heartbeat",
                ),
                heartbeat_status="error",
            )
    except Exception as e:
        return CycleHeartbeatResult(
            step=RunCycleStepResult(
                name="heartbeat",
                status="error",
                fatal=False,
                message=f"Token validation error — {_redact_forbidden(str(e))}",
            ),
            heartbeat_status="error",
        )

    # ── Build HTTP client if not provided ─────────────────────────
    if http_client is None:
        try:
            from kso_sidecar_agent import local_config as _lc
            cfg = _lc.read_config(root)
            backend_base_url = cfg.get("backend_base_url", "")
            if not backend_base_url:
                return CycleHeartbeatResult(
                    step=RunCycleStepResult(
                        name="heartbeat", status="error", fatal=False,
                        message="Config missing backend_base_url",
                    ),
                    heartbeat_status="error",
                )
            http_config = HttpClientConfig(
                base_url=backend_base_url,
                timeout_sec=cfg.get("request_timeout_sec", 10),
                tls_verify=cfg.get("tls_verify", True),
            )
            http_client = SafeHttpClient(http_config)
        except Exception as e:
            return CycleHeartbeatResult(
                step=RunCycleStepResult(
                    name="heartbeat", status="error", fatal=False,
                    message=f"Config error — {_redact_forbidden(str(e))}",
                ),
                heartbeat_status="error",
            )

    # ── Build payload ─────────────────────────────────────────────
    payload = HeartbeatPayload(
        status=cycle_status_hint,
        message="run cycle heartbeat",
        device_time=None,
    )

    # ── Send heartbeat ────────────────────────────────────────────
    hb_client = HeartbeatClient(http_client=http_client, retry_manager=retry_manager)

    try:
        result: HeartbeatResult = hb_client.send_heartbeat(token_state, payload, now=now)
    except HttpClientError as e:
        return CycleHeartbeatResult(
            step=RunCycleStepResult(
                name="heartbeat",
                status="error",
                fatal=False,
                retryable=getattr(e, "retryable", False),
                message=f"Heartbeat failed — {_redact_forbidden(str(e))}",
                safe_details={"status_code": e.status_code},
            ),
            heartbeat_status="error",
            attempts=hb_client.last_attempts,
        )
    except (ValueError, RuntimeError) as e:
        return CycleHeartbeatResult(
            step=RunCycleStepResult(
                name="heartbeat",
                status="error",
                fatal=False,
                message=f"Heartbeat failed — {_redact_forbidden(str(e))}",
            ),
            heartbeat_status="error",
            attempts=hb_client.last_attempts,
        )

    return CycleHeartbeatResult(
        step=RunCycleStepResult(
            name="heartbeat",
            status="ok",
            safe_details={
                "backend_status": result.backend_status or "accepted",
                "sent": True,
            },
        ),
        heartbeat_status="sent",
        attempts=hb_client.last_attempts,
        backend_status=result.backend_status or "",
    )
