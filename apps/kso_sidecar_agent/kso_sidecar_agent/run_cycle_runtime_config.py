"""KSO Sidecar Run Cycle — Runtime Config Sync Step.

Fetches and saves runtime config via RuntimeConfigClient + RuntimeConfigStore.
Only called in backend_enabled mode with a valid TokenState.

Based on: docs/kso_sidecar_run_cycle_design.md
"""

import time as _time
from dataclasses import dataclass, field
from typing import Any, Optional

from kso_sidecar_agent.http_client import HttpClientConfig, HttpClientError, SafeHttpClient
from kso_sidecar_agent.run_cycle import (
    RunCycleStepResult,
    _check_forbidden,
    _redact_forbidden,
    _validate_safe_details,
)
from kso_sidecar_agent.runtime_config_client import RuntimeConfigClient, RuntimeConfigSnapshot
from kso_sidecar_agent.runtime_config_store import write_runtime_config
from kso_sidecar_agent.token_state import TokenState


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class CycleRuntimeConfigResult:
    """Result of the runtime config sync step in a run cycle."""

    step: RunCycleStepResult
    config_status: str = "skipped"     # updated | not_modified | error | skipped

    def __post_init__(self) -> None:
        _check_forbidden(self.config_status, "config_status")


# ══════════════════════════════════════════════════════════════════════
# Runtime config sync function
# ══════════════════════════════════════════════════════════════════════

def sync_runtime_config_for_cycle(
    root,
    token_state: TokenState,
    now: Optional[float] = None,
    http_client: Optional[SafeHttpClient] = None,
) -> CycleRuntimeConfigResult:
    """Fetch and save runtime config as part of a run cycle.

    Args:
        root: Agent root path.
        token_state: Valid TokenState from auth step.
        now: Current unix timestamp.
        http_client: SafeHttpClient (same as used for auth).

    Returns:
        CycleRuntimeConfigResult with safe step and config status.

    Never exposes token, Authorization, or full config in step/output.
    Non-fatal on HTTP errors (500, 401, etc.) if local cache is usable.
    """
    if now is None:
        now = _time.time()

    # ── Validate token ────────────────────────────────────────────
    try:
        if not token_state.is_valid(now=now):
            return CycleRuntimeConfigResult(
                step=RunCycleStepResult(
                    name="runtime_config",
                    status="error",
                    fatal=False,
                    retryable=False,
                    message="Token expired before runtime config fetch",
                ),
                config_status="error",
            )
    except Exception as e:
        return CycleRuntimeConfigResult(
            step=RunCycleStepResult(
                name="runtime_config",
                status="error",
                fatal=False,
                retryable=False,
                message=f"Token validation error — {_redact_forbidden(str(e))}",
            ),
            config_status="error",
        )

    # ── Read existing ETag ────────────────────────────────────────
    existing_etag = None
    try:
        from kso_sidecar_agent.runtime_config_store import read_runtime_config
        existing = read_runtime_config(root)
        existing_etag = existing.get("etag")
    except (FileNotFoundError, ValueError):
        pass  # no local file or invalid — fetch fresh
    except Exception:
        pass

    # ── Build HTTP client if not provided ─────────────────────────
    if http_client is None:
        try:
            from kso_sidecar_agent import local_config as _lc
            cfg = _lc.read_config(root)
            backend_base_url = cfg.get("backend_base_url", "")
            if not backend_base_url:
                return CycleRuntimeConfigResult(
                    step=RunCycleStepResult(
                        name="runtime_config",
                        status="error",
                        fatal=False,
                        retryable=False,
                        message="Config missing backend_base_url for runtime config client",
                    ),
                    config_status="error",
                )
            http_config = HttpClientConfig(
                base_url=backend_base_url,
                timeout_sec=cfg.get("request_timeout_sec", 10),
                tls_verify=cfg.get("tls_verify", True),
            )
            http_client = SafeHttpClient(http_config)
        except (FileNotFoundError, ValueError, KeyError) as e:
            return CycleRuntimeConfigResult(
                step=RunCycleStepResult(
                    name="runtime_config",
                    status="error",
                    fatal=False,
                    retryable=False,
                    message=f"Config error — {_redact_forbidden(str(e))}",
                ),
                config_status="error",
            )

    # ── Fetch runtime config ──────────────────────────────────────
    try:
        rc_client = RuntimeConfigClient(http_client=http_client)
        snapshot = rc_client.fetch_current(token_state, etag=existing_etag, now=now)
    except HttpClientError as e:
        return CycleRuntimeConfigResult(
            step=RunCycleStepResult(
                name="runtime_config",
                status="error",
                fatal=False,
                retryable=getattr(e, "retryable", False),
                message=f"Runtime config fetch failed — {_redact_forbidden(str(e))}",
                safe_details={"status_code": e.status_code},
            ),
            config_status="error",
        )
    except Exception as e:
        return CycleRuntimeConfigResult(
            step=RunCycleStepResult(
                name="runtime_config",
                status="error",
                fatal=False,
                retryable=False,
                message=f"Unexpected error — {_redact_forbidden(str(e))}",
            ),
            config_status="error",
        )

    # ── Not modified ──────────────────────────────────────────────
    if snapshot.not_modified:
        return CycleRuntimeConfigResult(
            step=RunCycleStepResult(
                name="runtime_config",
                status="ok",
                safe_details={
                    "status": "not_modified",
                    "etag_present": existing_etag is not None,
                    "not_modified": True,
                },
            ),
            config_status="not_modified",
        )

    # ── Save ──────────────────────────────────────────────────────
    try:
        store_result = write_runtime_config(root, snapshot)
    except ValueError as e:
        return CycleRuntimeConfigResult(
            step=RunCycleStepResult(
                name="runtime_config",
                status="error",
                fatal=False,
                retryable=False,
                message=f"Runtime config validation failed — {_redact_forbidden(str(e))}",
            ),
            config_status="error",
        )
    except (OSError, RuntimeError) as e:
        return CycleRuntimeConfigResult(
            step=RunCycleStepResult(
                name="runtime_config",
                status="error",
                fatal=False,
                retryable=False,
                message=f"Failed to save runtime config — {_redact_forbidden(str(e))}",
            ),
            config_status="error",
        )

    # ── Success ───────────────────────────────────────────────────
    config_hash_short = ""
    if snapshot.config_hash:
        config_hash_short = snapshot.config_hash[:12]

    return CycleRuntimeConfigResult(
        step=RunCycleStepResult(
            name="runtime_config",
            status="ok",
            safe_details={
                "status": "updated",
                "config_hash_short": config_hash_short,
                "not_modified": False,
            },
        ),
        config_status="updated",
    )
