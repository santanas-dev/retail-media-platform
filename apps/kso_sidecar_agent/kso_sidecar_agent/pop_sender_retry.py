"""KSO Sidecar PoP Sender Retry Decision Core — safe retry logic.

Pure decision logic for PoP backend send retry:
  - decide_pop_send_retry() → whether to retry, refresh auth, or stop
  - calculate_pop_retry_delay_ms() → exponential backoff (no jitter, stable tests)
  - format_pop_send_retry_decision() → safe aggregated output

No HTTP, no sleep, no auth refresh, no file I/O, no rotation.
Only returns safe PopSendRetryDecision — never payload, IDs, or secrets.
"""

from dataclasses import dataclass
from typing import Optional

from kso_sidecar_agent.pop_sender import (
    SEND_OK,
    SEND_WARNING,
    SEND_ERROR,
    REASON_PROCESSED,
    REASON_DUPLICATE_EVENTS,
    REASON_DUPLICATE_BATCH,
    REASON_NO_PAYLOAD,
    REASON_UNAUTHORIZED,
    REASON_NETWORK_ERROR,
    REASON_TIMEOUT,
    REASON_SERVER_ERROR,
    REASON_RATE_LIMITED,
    REASON_PARTIAL_SUCCESS,
    REASON_BAD_REQUEST,
    REASON_FORBIDDEN,
    REASON_NOT_FOUND,
    REASON_VALIDATION_ERROR,
    REASON_INVALID_RESPONSE,
    REASON_UNKNOWN_RESPONSE,
    FORBIDDEN_IN_OUTPUT,
    PopSendResult,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

ACTION_STOP = "stop"
ACTION_RETRY = "retry"
ACTION_REFRESH_AUTH_THEN_RETRY = "refresh_auth_then_retry"

ALLOWED_ACTIONS = frozenset({
    ACTION_STOP,
    ACTION_RETRY,
    ACTION_REFRESH_AUTH_THEN_RETRY,
})

# ── Safe retry reasons ────────────────────────────────────────────────

RETRY_REASON_SUCCESS = "success"
RETRY_REASON_NO_PAYLOAD = "no_payload"
RETRY_REASON_AUTH_REFRESH_REQUIRED = "auth_refresh_required"
RETRY_REASON_AUTH_REFRESH_FAILED = "auth_refresh_failed"
RETRY_REASON_RETRYABLE_ERROR = "retryable_error"
RETRY_REASON_RETRY_EXHAUSTED = "retry_exhausted"
RETRY_REASON_NON_RETRYABLE_PENDING_REMAINS = "non_retryable_pending_remains"
RETRY_REASON_DUPLICATE_BATCH_PENDING_REMAINS = "duplicate_batch_pending_remains"
RETRY_REASON_INVALID_ARGS = "invalid_args"

ALLOWED_RETRY_REASONS = frozenset({
    RETRY_REASON_SUCCESS,
    RETRY_REASON_NO_PAYLOAD,
    RETRY_REASON_AUTH_REFRESH_REQUIRED,
    RETRY_REASON_AUTH_REFRESH_FAILED,
    RETRY_REASON_RETRYABLE_ERROR,
    RETRY_REASON_RETRY_EXHAUSTED,
    RETRY_REASON_NON_RETRYABLE_PENDING_REMAINS,
    RETRY_REASON_DUPLICATE_BATCH_PENDING_REMAINS,
    RETRY_REASON_INVALID_ARGS,
})

# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopSendRetryDecision:
    """Safe retry decision after a PoP send attempt.

    Never contains payload body, raw response, IDs, token,
    backend URL, endpoint, filename, sha256, paths, or secrets.
    """

    action: str = ACTION_STOP              # stop | retry | refresh_auth_then_retry
    retryable: bool = False
    auth_refresh_required: bool = False
    pending_should_remain: bool = True
    next_attempt_number: Optional[int] = None
    delay_ms: Optional[int] = None
    reason: str = RETRY_REASON_SUCCESS

    def __post_init__(self) -> None:
        if self.action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"Invalid action '{self.action}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_ACTIONS))}"
            )
        if self.reason not in ALLOWED_RETRY_REASONS:
            raise ValueError(
                f"Invalid reason '{self.reason}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_RETRY_REASONS))}"
            )

    def __repr__(self) -> str:
        """Repr only shows safe fields — no IDs, paths, or secrets."""
        return (
            f"PopSendRetryDecision(action={self.action!r}, "
            f"retryable={self.retryable}, "
            f"auth_refresh_required={self.auth_refresh_required}, "
            f"pending_should_remain={self.pending_should_remain}, "
            f"next_attempt_number={self.next_attempt_number}, "
            f"delay_ms={self.delay_ms}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Delay calculation
# ══════════════════════════════════════════════════════════════════════

def calculate_pop_retry_delay_ms(
    attempt_number: int,
    base_delay_ms: int = 1000,
    max_delay_ms: int = 30000,
) -> int:
    """Calculate retry delay with exponential backoff.

    Pure arithmetic — no sleep, no jitter (for stable tests).

    Formula: min(base_delay_ms * 2^(attempt_number-1), max_delay_ms)

    Args:
        attempt_number: Current attempt (1-based). attempt 1 → 1000, 2 → 2000, 3 → 4000.
        base_delay_ms: Base delay in milliseconds (default 1000).
        max_delay_ms: Maximum delay cap in milliseconds (default 30000).

    Returns:
        Delay in milliseconds (always >= 0).
    """
    if not isinstance(attempt_number, int) or attempt_number < 1:
        return 0
    if not isinstance(base_delay_ms, int) or base_delay_ms < 0:
        return 0
    if not isinstance(max_delay_ms, int) or max_delay_ms < 0:
        return 0

    delay = base_delay_ms * (2 ** (attempt_number - 1))
    return min(delay, max_delay_ms)


# ══════════════════════════════════════════════════════════════════════
# Retry decision
# ══════════════════════════════════════════════════════════════════════

def decide_pop_send_retry(
    result: PopSendResult,
    attempt_number: int = 1,
    max_attempts: int = 3,
    auth_refresh_attempted: bool = False,
) -> PopSendRetryDecision:
    """Decide whether to retry, refresh auth, or stop after a PoP send.

    Pure logic — no HTTP, no sleep, no auth refresh, no file I/O.

    Rules (in priority order):
        1. Success (send_status=ok, !pending_should_remain) → stop
        2. no_payload → stop
        3. Auth refresh required + not yet attempted + attempts left →
           refresh_auth_then_retry
        4. Auth refresh required + already attempted → stop
        5. 409 duplicate_batch → stop, pending_should_remain
        6. Retryable + attempts left → retry with delay
        7. Retryable + attempts exhausted → stop
        8. Non-retryable + pending → stop

    Args:
        result: PopSendResult from a send attempt.
        attempt_number: Current attempt number (1-based, default 1).
        max_attempts: Maximum total attempts (default 3).
        auth_refresh_attempted: Whether auth refresh was already tried.

    Returns:
        PopSendRetryDecision — always safe, never raises.
        pending_should_remain=True for any unclear state.
    """
    # ── Validate inputs ──────────────────────────────────────────
    if not isinstance(result, PopSendResult):
        return PopSendRetryDecision(
            action=ACTION_STOP,
            reason=RETRY_REASON_INVALID_ARGS,
            pending_should_remain=True,
        )

    if not isinstance(attempt_number, int) or attempt_number < 1:
        return PopSendRetryDecision(
            action=ACTION_STOP,
            reason=RETRY_REASON_INVALID_ARGS,
            pending_should_remain=True,
        )

    if not isinstance(max_attempts, int) or max_attempts < 1:
        return PopSendRetryDecision(
            action=ACTION_STOP,
            reason=RETRY_REASON_INVALID_ARGS,
            pending_should_remain=True,
        )

    has_attempts_left = attempt_number < max_attempts
    next_attempt = attempt_number + 1 if has_attempts_left else None

    # ── 1. Success → stop ───────────────────────────────────────
    if result.send_status == SEND_OK and not result.pending_should_remain:
        return PopSendRetryDecision(
            action=ACTION_STOP,
            retryable=False,
            pending_should_remain=False,
            reason=RETRY_REASON_SUCCESS,
        )

    # ── 2. no_payload → stop ────────────────────────────────────
    if result.reason == REASON_NO_PAYLOAD:
        return PopSendRetryDecision(
            action=ACTION_STOP,
            retryable=False,
            pending_should_remain=True,
            reason=RETRY_REASON_NO_PAYLOAD,
        )

    # ── 3. Auth refresh required + not attempted → refresh ──────
    if result.auth_refresh_required and not auth_refresh_attempted and has_attempts_left:
        return PopSendRetryDecision(
            action=ACTION_REFRESH_AUTH_THEN_RETRY,
            retryable=True,
            auth_refresh_required=True,
            pending_should_remain=True,
            next_attempt_number=next_attempt,
            reason=RETRY_REASON_AUTH_REFRESH_REQUIRED,
        )

    # ── 4. Auth refresh required + already attempted → stop ─────
    if result.auth_refresh_required and auth_refresh_attempted:
        return PopSendRetryDecision(
            action=ACTION_STOP,
            retryable=False,
            auth_refresh_required=True,
            pending_should_remain=True,
            reason=RETRY_REASON_AUTH_REFRESH_FAILED,
        )

    # ── 5. 409 duplicate_batch → stop ───────────────────────────
    if result.reason == REASON_DUPLICATE_BATCH:
        return PopSendRetryDecision(
            action=ACTION_STOP,
            retryable=False,
            pending_should_remain=True,
            reason=RETRY_REASON_DUPLICATE_BATCH_PENDING_REMAINS,
        )

    # ── 6. Retryable + attempts left → retry ────────────────────
    if result.retryable and has_attempts_left:
        delay_ms = calculate_pop_retry_delay_ms(attempt_number)
        return PopSendRetryDecision(
            action=ACTION_RETRY,
            retryable=True,
            pending_should_remain=True,
            next_attempt_number=next_attempt,
            delay_ms=delay_ms,
            reason=RETRY_REASON_RETRYABLE_ERROR,
        )

    # ── 7. Retryable + attempts exhausted → stop ────────────────
    if result.retryable and not has_attempts_left:
        return PopSendRetryDecision(
            action=ACTION_STOP,
            retryable=False,
            pending_should_remain=True,
            reason=RETRY_REASON_RETRY_EXHAUSTED,
        )

    # ── 8. Non-retryable + pending → stop ───────────────────────
    return PopSendRetryDecision(
        action=ACTION_STOP,
        retryable=False,
        pending_should_remain=True,
        reason=RETRY_REASON_NON_RETRYABLE_PENDING_REMAINS,
    )


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_send_retry_decision(decision: PopSendRetryDecision) -> str:
    """Return a safe aggregated string of the retry decision.

    Never prints payload body, IDs, token, endpoint, backend URL,
    filename, sha256, paths, or secrets.
    """
    lines = [
        f"retry_action:             {decision.action}",
        f"retryable:                {str(decision.retryable).lower()}",
        f"auth_refresh_required:    {str(decision.auth_refresh_required).lower()}",
        f"pending_should_remain:    {str(decision.pending_should_remain).lower()}",
    ]
    if decision.next_attempt_number is not None:
        lines.append(f"next_attempt_number:      {decision.next_attempt_number}")
    if decision.delay_ms is not None:
        lines.append(f"delay_ms:                 {decision.delay_ms}")
    lines.append(f"reason:                   {decision.reason}")

    output = "\n".join(lines)

    # Safety scan: ensure no forbidden substrings in output
    lower = output.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            raise ValueError(
                f"Safe output contains forbidden substring '{fb}'"
            )

    return output
