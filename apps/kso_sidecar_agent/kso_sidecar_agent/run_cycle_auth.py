"""KSO Sidecar Run Cycle — Auth Step.

Performs device authentication as part of the run cycle.
Token stays in memory only — never in RunCycleResult, agent_status, or on disk.
Only called when backend_enabled=True in RunCycleOptions.

Based on: docs/kso_sidecar_run_cycle_design.md
"""

import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kso_sidecar_agent import device_auth_client as _auth
from kso_sidecar_agent import local_config as _lc
from kso_sidecar_agent import secret_store as _ss
from kso_sidecar_agent.http_client import HttpClientConfig, HttpClientError, SafeHttpClient
from kso_sidecar_agent.retry_backoff import BackoffPolicy, RetryBackoffManager
from kso_sidecar_agent.run_cycle import (
    FORBIDDEN_SUBSTRINGS,
    RunCycleOptions,
    RunCycleStepResult,
    _check_forbidden,
    _redact_forbidden,
    _validate_safe_details,
)
from kso_sidecar_agent.token_state import TokenState


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class CycleAuthResult:
    """Result of the auth step in a run cycle. Token stays in memory only."""

    step: RunCycleStepResult                     # safe step result for RunCycleResult
    token_state: Optional[TokenState] = None     # memory-only access token
    attempts: int = 0
    expires_in_sec: float = 0.0

    def __post_init__(self) -> None:
        if self.token_state is not None:
            # Verify it's a TokenState but NEVER expose the token value
            pass


# ══════════════════════════════════════════════════════════════════════
# Auth function
# ══════════════════════════════════════════════════════════════════════

def authenticate_for_cycle(
    root,
    options: RunCycleOptions,
    now: Optional[float] = None,
    http_client: Optional[SafeHttpClient] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
) -> CycleAuthResult:
    """Perform device auth for a run cycle. Token stays in memory only.

    Only works when options.backend_enabled=True and options.dev_secret_store=True.
    Otherwise returns a skipped step without HTTP calls.

    Args:
        root: Agent root path (str or Path).
        options: RunCycleOptions with backend_enabled and dev_secret_store.
        now: Current unix timestamp (defaults to time.time()).
        http_client: Optional pre-configured SafeHttpClient. If None, builds from config.
        sleep_fn: Sleep function for retry delays (defaults to time.sleep()).

    Returns:
        CycleAuthResult with step (safe), token_state (memory-only), attempts, expires_in_sec.

    Never exposes token, secret, Authorization in the returned step or any output.
    """
    if now is None:
        now = _time.time()

    if not options.backend_enabled:
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="skipped",
                message="Backend not enabled",
            ),
            attempts=0,
        )

    # ── Read config ───────────────────────────────────────────────
    try:
        cfg = _lc.read_config(root)
    except (FileNotFoundError, ValueError) as e:
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="error",
                fatal=True,
                retryable=False,
                message=f"Config error — {_redact_forbidden(str(e))}",
            ),
            attempts=0,
        )

    backend_base_url = cfg.get("backend_base_url", "")
    if not backend_base_url:
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="error",
                fatal=True,
                retryable=False,
                message="Config missing backend_base_url",
            ),
            attempts=0,
        )

    # ── Read secret ───────────────────────────────────────────────
    if not options.dev_secret_store:
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="error",
                fatal=True,
                retryable=False,
                message="Dev secret store not enabled — set dev_secret_store=True",
            ),
            attempts=0,
        )

    try:
        secret = _ss.read_secret(root, dev_secret_store=True)
    except RuntimeError as e:
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="error",
                fatal=True,
                retryable=False,
                message=f"Secret store error — {_redact_forbidden(str(e))}",
            ),
            attempts=0,
        )

    if not secret:
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="error",
                fatal=True,
                retryable=False,
                message="Device secret is empty",
            ),
            attempts=0,
        )

    def _read_secret() -> str:
        return secret

    # ── Build HTTP client ─────────────────────────────────────────
    if http_client is None:
        http_config = HttpClientConfig(
            base_url=backend_base_url,
            timeout_sec=cfg.get("request_timeout_sec", 10),
            tls_verify=cfg.get("tls_verify", True),
        )
        http_client = SafeHttpClient(http_config)

    # ── Build auth client ─────────────────────────────────────────
    auth_client = _auth.DeviceAuthClient(
        http_client=http_client,
        config=cfg,
        secret_reader=_read_secret,
    )

    # ── Build retry manager (optional) ────────────────────────────
    retry_manager = None
    if options.retry_auth:
        policy = BackoffPolicy(max_attempts=options.auth_max_attempts)
        retry_manager = RetryBackoffManager(policy)

    # ── Authenticate ──────────────────────────────────────────────
    try:
        token_state = auth_client.authenticate(
            now=now,
            retry_manager=retry_manager,
            sleep_fn=sleep_fn,
        )
    except HttpClientError as e:
        retryable = getattr(e, "retryable", False)
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="error",
                fatal=True,
                retryable=retryable,
                message=f"Auth failed — {_redact_forbidden(str(e))}",
                safe_details={"status_code": e.status_code},
            ),
            attempts=auth_client.last_attempts,
        )
    except (ValueError, RuntimeError) as e:
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="error",
                fatal=True,
                retryable=False,
                message=f"Auth failed — {_redact_forbidden(str(e))}",
            ),
            attempts=auth_client.last_attempts,
        )
    except Exception as e:
        return CycleAuthResult(
            step=RunCycleStepResult(
                name="auth",
                status="error",
                fatal=True,
                retryable=False,
                message=f"Unexpected auth error — {_redact_forbidden(str(e))}",
            ),
            attempts=auth_client.last_attempts,
        )

    # ── Success ───────────────────────────────────────────────────
    summary = token_state.safe_summary(now=now)

    return CycleAuthResult(
        step=RunCycleStepResult(
            name="auth",
            status="ok",
            safe_details={
                "device_id": token_state.device_id,
                "status": token_state.status,
            },
        ),
        token_state=token_state,
        attempts=auth_client.last_attempts,
        expires_in_sec=summary.get("expires_in_sec", 0),
    )
