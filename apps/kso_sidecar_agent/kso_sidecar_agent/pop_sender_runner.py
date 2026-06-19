"""KSO Sidecar PoP Sender Retry Runner Core — safe send orchestration.

Orchestrates a full PoP send with retry decisions:
  payload envelope → send_pop_payload_batch → classify → retry decision → optional retry

No CLI, no run cycle, no rotation, no file move, no sleep/wait.
token only via in-memory arguments; auth refresh only via injected callback.
Only returns safe PopSendRunResult — never raw response, payload, IDs, or secrets.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from kso_sidecar_agent.pop_sender import (
    SEND_OK,
    SEND_WARNING,
    SEND_ERROR,
    REASON_NO_PAYLOAD,
    REASON_DUPLICATE_BATCH,
    FORBIDDEN_IN_OUTPUT,
    PopSendResult,
    send_pop_payload_batch,
)
from kso_sidecar_agent.pop_sender_retry import (
    ACTION_STOP,
    ACTION_RETRY,
    ACTION_REFRESH_AUTH_THEN_RETRY,
    RETRY_REASON_AUTH_REFRESH_FAILED,
    RETRY_REASON_RETRY_EXHAUSTED,
    RETRY_REASON_NO_PAYLOAD,
    RETRY_REASON_SUCCESS,
    PopSendRetryDecision,
    decide_pop_send_retry,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

RUN_OK = "ok"
RUN_WARNING = "warning"
RUN_ERROR = "error"

ALLOWED_RUN_STATUSES = frozenset({RUN_OK, RUN_WARNING, RUN_ERROR})

REASON_AUTH_REFRESH_FAILED_RUN = "auth_refresh_failed"

ALLOWED_RUN_REASONS = frozenset({
    RETRY_REASON_SUCCESS,
    RETRY_REASON_NO_PAYLOAD,
    RETRY_REASON_RETRY_EXHAUSTED,
    RETRY_REASON_AUTH_REFRESH_FAILED,
    REASON_NO_PAYLOAD,
    REASON_DUPLICATE_BATCH,
    "duplicate_batch_pending_remains",
    "non_retryable_pending_remains",
    "invalid_args",
})

# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopSendRunResult:
    """Safe result of a full PoP send with retry orchestration.

    Never contains payload body, raw response, IDs, token,
    backend URL, endpoint, filename, sha256, paths, or secrets.
    """

    run_status: str = RUN_WARNING             # ok | warning | error
    final_send_status: str = SEND_WARNING     # ok | warning | error
    attempts_made: int = 0
    max_attempts: int = 3
    auth_refresh_attempted: bool = False
    retry_exhausted: bool = False
    attempted_events: int = 0
    accepted_events: int = 0
    duplicate_events: int = 0
    rejected_events: int = 0
    pending_should_remain: bool = True
    reason: str = REASON_NO_PAYLOAD

    def __post_init__(self) -> None:
        if self.run_status not in ALLOWED_RUN_STATUSES:
            raise ValueError(
                f"Invalid run_status '{self.run_status}'"
            )
        if self.final_send_status not in (SEND_OK, SEND_WARNING, SEND_ERROR):
            raise ValueError(
                f"Invalid final_send_status '{self.final_send_status}'"
            )

    def __repr__(self) -> str:
        return (
            f"PopSendRunResult(run_status={self.run_status!r}, "
            f"final_send_status={self.final_send_status!r}, "
            f"attempts_made={self.attempts_made}, "
            f"max_attempts={self.max_attempts}, "
            f"auth_refresh_attempted={self.auth_refresh_attempted}, "
            f"retry_exhausted={self.retry_exhausted}, "
            f"attempted_events={self.attempted_events}, "
            f"accepted_events={self.accepted_events}, "
            f"duplicate_events={self.duplicate_events}, "
            f"rejected_events={self.rejected_events}, "
            f"pending_should_remain={self.pending_should_remain}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════

def run_pop_send_with_retry(
    http_client,
    payload_envelope,
    access_token: Optional[str] = None,
    refresh_auth_callback: Optional[Callable[[], Optional[str]]] = None,
    max_attempts: int = 3,
    now: Optional[str] = None,
) -> PopSendRunResult:
    """Run a full PoP send with retry decisions.

    Orchestration loop:
        1. send_pop_payload_batch(http_client, envelope, token)
        2. decide_pop_send_retry(result, attempt, max_attempts, auth_refreshed)
        3. If stop → return final result
        4. If retry → loop back to send (increment attempt)
        5. If refresh_auth_then_retry → call refresh_auth_callback → one more retry

    No sleep/wait, no file I/O, no reading secret/config/token files.
    Auth refresh only via injected callback — no real auth client.

    Args:
        http_client: SafeHttpClient instance (or duck-typed equivalent).
        payload_envelope: PopPayloadEnvelope to send.
        access_token: Optional JWT access token (in-memory only).
        refresh_auth_callback: Optional callable returning new token string or None.
            Called only when retry decision is refresh_auth_then_retry.
        max_attempts: Maximum send attempts including retries (1-10).
        now: Not used — reserved for future timestamp injection.

    Returns:
        PopSendRunResult — always safe, never raises, never exposes secrets/IDs.
    """
    # ── Validate max_attempts ────────────────────────────────────
    if not isinstance(max_attempts, int) or max_attempts < 1:
        return PopSendRunResult(
            run_status=RUN_ERROR,
            reason="invalid_args",
            pending_should_remain=True,
        )

    attempt_number = 1
    auth_refresh_attempted = False
    current_token = access_token
    final_result: Optional[PopSendResult] = None

    while attempt_number <= max_attempts:
        # ── Send ────────────────────────────────────────────────
        result = send_pop_payload_batch(
            http_client=http_client,
            payload_envelope=payload_envelope,
            access_token=current_token,
            now=now,
        )
        final_result = result

        # ── Decide ──────────────────────────────────────────────
        decision = decide_pop_send_retry(
            result=result,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            auth_refresh_attempted=auth_refresh_attempted,
        )

        # ── Act ─────────────────────────────────────────────────

        # STOP — final result
        if decision.action == ACTION_STOP:
            return _build_run_result(
                result=result,
                attempts_made=attempt_number,
                max_attempts=max_attempts,
                auth_refresh_attempted=auth_refresh_attempted,
                decision=decision,
            )

        # RETRY — loop with incremented attempt
        if decision.action == ACTION_RETRY:
            attempt_number += 1
            continue

        # REFRESH_AUTH_THEN_RETRY
        if decision.action == ACTION_REFRESH_AUTH_THEN_RETRY:
            auth_refresh_attempted = True

            # Call callback for new token
            new_token = None
            if refresh_auth_callback is not None:
                try:
                    new_token = refresh_auth_callback()
                except Exception:
                    new_token = None

            if new_token:
                current_token = new_token
                attempt_number += 1
                # retry once with new token — loop continues
                continue
            else:
                # Auth refresh failed → stop
                return PopSendRunResult(
                    run_status=RUN_WARNING,
                    final_send_status=result.send_status,
                    attempts_made=attempt_number,
                    max_attempts=max_attempts,
                    auth_refresh_attempted=True,
                    retry_exhausted=False,
                    attempted_events=result.attempted_events,
                    accepted_events=result.accepted_events,
                    duplicate_events=result.duplicate_events,
                    rejected_events=result.rejected_events,
                    pending_should_remain=True,
                    reason=REASON_AUTH_REFRESH_FAILED_RUN,
                )

    # ── Loop exhausted ──────────────────────────────────────────
    final = final_result if final_result is not None else PopSendResult(
        reason=REASON_NO_PAYLOAD,
        pending_should_remain=True,
    )
    return PopSendRunResult(
        run_status=RUN_ERROR,
        final_send_status=final.send_status,
        attempts_made=attempt_number - 1,
        max_attempts=max_attempts,
        auth_refresh_attempted=auth_refresh_attempted,
        retry_exhausted=True,
        attempted_events=final.attempted_events,
        accepted_events=final.accepted_events,
        duplicate_events=final.duplicate_events,
        rejected_events=final.rejected_events,
        pending_should_remain=True,
        reason=RETRY_REASON_RETRY_EXHAUSTED,
    )


def _build_run_result(
    result: PopSendResult,
    attempts_made: int,
    max_attempts: int,
    auth_refresh_attempted: bool,
    decision: PopSendRetryDecision,
) -> PopSendRunResult:
    """Build final PopSendRunResult from a stop decision."""
    reason = decision.reason

    # Determine run_status from result
    if result.send_status == SEND_OK and not result.pending_should_remain:
        run_status = RUN_OK
    elif result.reason == REASON_NO_PAYLOAD:
        run_status = RUN_WARNING
        reason = REASON_NO_PAYLOAD
    elif decision.reason == RETRY_REASON_RETRY_EXHAUSTED:
        run_status = RUN_ERROR
    elif result.send_status == SEND_ERROR or result.pending_should_remain:
        run_status = RUN_WARNING
    else:
        run_status = RUN_OK

    return PopSendRunResult(
        run_status=run_status,
        final_send_status=result.send_status,
        attempts_made=attempts_made,
        max_attempts=max_attempts,
        auth_refresh_attempted=auth_refresh_attempted,
        retry_exhausted=(reason == RETRY_REASON_RETRY_EXHAUSTED),
        attempted_events=result.attempted_events,
        accepted_events=result.accepted_events,
        duplicate_events=result.duplicate_events,
        rejected_events=result.rejected_events,
        pending_should_remain=result.pending_should_remain,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_send_run_result(result: PopSendRunResult) -> str:
    """Return a safe aggregated string of the run result.

    Never prints payload body, IDs, token, endpoint, backend URL,
    filename, sha256, paths, or secrets.
    """
    lines = [
        f"run_status:              {result.run_status}",
        f"final_send_status:       {result.final_send_status}",
        f"attempts_made:           {result.attempts_made}",
        f"max_attempts:            {result.max_attempts}",
        f"auth_refresh_attempted:  {str(result.auth_refresh_attempted).lower()}",
        f"retry_exhausted:         {str(result.retry_exhausted).lower()}",
        f"attempted_events:        {result.attempted_events}",
        f"accepted_events:         {result.accepted_events}",
        f"duplicate_events:        {result.duplicate_events}",
        f"rejected_events:         {result.rejected_events}",
        f"pending_should_remain:   {str(result.pending_should_remain).lower()}",
        f"reason:                  {result.reason}",
    ]

    output = "\n".join(lines)

    # Safety scan
    lower = output.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            raise ValueError(
                f"Safe output contains forbidden substring '{fb}'"
            )

    return output
