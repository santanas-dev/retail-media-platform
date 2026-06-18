"""Retry/Backoff Manager for KSO Sidecar Agent.

Stdlib-only. Provides exponential backoff with jitter,
safe error classification, and forbidden-substring redaction in reason strings.

Not yet wired to DeviceAuthClient — that will be a separate step.
"""

import random as _random
import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

from kso_sidecar_agent.http_client import HttpClientError

# ══════════════════════════════════════════════════════════════════════
# Forbidden substrings in reason
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_REASON_SUBSTRINGS = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "device_secret", "access_token",
]


def _redact_reason(reason: str) -> str:
    """Replace any forbidden substring with [REDACTED] (case-insensitive)."""
    result = reason
    lower = result.lower()
    for forbidden in FORBIDDEN_REASON_SUBSTRINGS:
        if forbidden in lower:
            result = result.replace(forbidden, "[REDACTED]")
            # Also try title-case variants
            result = result.replace(forbidden.title(), "[REDACTED]")
            result = result.replace(forbidden.upper(), "[REDACTED]")
    return result


# ══════════════════════════════════════════════════════════════════════
# BackoffPolicy
# ══════════════════════════════════════════════════════════════════════

@dataclass
class BackoffPolicy:
    """Exponential backoff policy configuration."""

    max_attempts: int = 3        # 1–10
    base_delay_sec: float = 2.0  # > 0
    max_delay_sec: float = 60.0  # >= base_delay_sec
    multiplier: float = 2.0      # >= 1.0
    jitter_ratio: float = 0.25   # 0.0–1.0

    def __post_init__(self) -> None:
        if not isinstance(self.max_attempts, int) or self.max_attempts < 1 or self.max_attempts > 10:
            raise ValueError(
                f"max_attempts must be 1–10, got {self.max_attempts!r}"
            )
        if not isinstance(self.base_delay_sec, (int, float)) or self.base_delay_sec <= 0:
            raise ValueError(
                f"base_delay_sec must be > 0, got {self.base_delay_sec!r}"
            )
        if not isinstance(self.max_delay_sec, (int, float)) or self.max_delay_sec < self.base_delay_sec:
            raise ValueError(
                f"max_delay_sec must be >= base_delay_sec ({self.base_delay_sec}), "
                f"got {self.max_delay_sec!r}"
            )
        if not isinstance(self.multiplier, (int, float)) or self.multiplier < 1.0:
            raise ValueError(
                f"multiplier must be >= 1.0, got {self.multiplier!r}"
            )
        if not isinstance(self.jitter_ratio, (int, float)) or self.jitter_ratio < 0.0 or self.jitter_ratio > 1.0:
            raise ValueError(
                f"jitter_ratio must be 0.0–1.0, got {self.jitter_ratio!r}"
            )


# ══════════════════════════════════════════════════════════════════════
# RetryDecision
# ══════════════════════════════════════════════════════════════════════

@dataclass
class RetryDecision:
    """Result of evaluating whether to retry and how long to wait.

    reason is guaranteed safe — forbidden substrings are [REDACTED].
    """

    attempt: int
    max_attempts: int
    retryable: bool
    should_retry: bool
    delay_sec: float
    reason: str

    def __post_init__(self) -> None:
        # Ensure reason is safe
        self.reason = _redact_reason(self.reason)

    def __repr__(self) -> str:
        return (
            f"RetryDecision(attempt={self.attempt}/{self.max_attempts}, "
            f"retryable={self.retryable}, should_retry={self.should_retry}, "
            f"delay_sec={self.delay_sec:.1f}, reason={self.reason!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


# ══════════════════════════════════════════════════════════════════════
# RetryBackoffManager
# ══════════════════════════════════════════════════════════════════════

class RetryBackoffManager:
    """Manages retry decisions with exponential backoff + jitter.

    Does NOT store or log tokens, secrets, request/response bodies.
    """

    def __init__(
        self,
        policy: BackoffPolicy,
        random_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        """Create a retry/backoff manager.

        Args:
            policy: BackoffPolicy with delay/jitter parameters.
            random_fn: Callable returning a float in [0, 1]. Defaults to random.random().
                       Injectable for deterministic tests.
        """
        self._policy = policy
        self._random = random_fn or _random.random

    @property
    def policy(self) -> BackoffPolicy:
        return self._policy

    # ── Error classification ───────────────────────────────────────

    def classify_error(self, error: Exception) -> Tuple[bool, str]:
        """Classify an error as retryable or not. Returns (retryable, reason).

        The reason is the sanitised error message (forbidden substrings → [REDACTED]).
        Never includes request/response bodies, tokens, or secrets.
        """
        # HttpClientError carries its own retryable flag
        if isinstance(error, HttpClientError):
            return error.retryable, _redact_reason(str(error))

        # Network-level errors are retryable
        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return True, _redact_reason(str(error))

        # ValueError / RuntimeError are non-retryable by default
        if isinstance(error, (ValueError, RuntimeError)):
            return False, _redact_reason(str(error))

        # Unknown errors: non-retryable (conservative)
        return False, _redact_reason(str(error))

    # ── Delay computation ──────────────────────────────────────────

    def compute_delay(self, attempt: int) -> float:
        """Compute delay for a given attempt number (1-indexed).

        Formula:
            delay = base_delay_sec * multiplier^(attempt-1)
            delay += jitter: ±(jitter_ratio * delay)
            delay = min(delay, max_delay_sec)

        Args:
            attempt: 1-indexed attempt number.
        """
        if attempt < 1:
            raise ValueError(f"attempt must be >= 1, got {attempt}")

        base = self._policy.base_delay_sec
        exp = attempt - 1
        delay = base * (self._policy.multiplier ** exp)

        # Jitter
        if self._policy.jitter_ratio > 0:
            jitter_range = delay * self._policy.jitter_ratio
            jitter = (self._random() - 0.5) * 2 * jitter_range
            delay += jitter

        # Clamp
        delay = max(delay, 0.0)
        delay = min(delay, self._policy.max_delay_sec)

        return delay

    # ── Decision ───────────────────────────────────────────────────

    def next_decision(self, attempt: int, error: Exception) -> RetryDecision:
        """Compute the next retry decision after an error.

        Args:
            attempt: 1-indexed current attempt number (the one that just failed).
            error: The exception that was raised.

        Returns:
            RetryDecision with retryable/should_retry/delay_sec fields.
        """
        retryable, reason = self.classify_error(error)

        # Should we retry?
        should_retry = retryable and (attempt < self._policy.max_attempts)

        if should_retry:
            delay_sec = self.compute_delay(attempt + 1)  # delay for NEXT attempt
        else:
            delay_sec = 0.0

        return RetryDecision(
            attempt=attempt,
            max_attempts=self._policy.max_attempts,
            retryable=retryable,
            should_retry=should_retry,
            delay_sec=delay_sec,
            reason=reason,
        )


# ══════════════════════════════════════════════════════════════════════
# Simple execute helper
# ══════════════════════════════════════════════════════════════════════

def execute_with_retries(
    operation: Callable[[], Any],
    manager: RetryBackoffManager,
    sleep_fn: Optional[Callable[[float], None]] = None,
) -> Any:
    """Execute operation with retries, returning the result or raising the last error.

    Args:
        operation: Zero-arg callable to execute.
        manager: Configured RetryBackoffManager.
        sleep_fn: Sleep function (accepts seconds). Defaults to time.sleep.
                  Override in tests to avoid real delays.

    Returns:
        The result of operation() on success.

    Raises:
        The last error if all attempts exhausted, or if the error is non-retryable.
    """
    _sleep = sleep_fn or _time.sleep
    last_error: Optional[Exception] = None

    for attempt in range(1, manager.policy.max_attempts + 1):
        try:
            return operation()
        except Exception as e:
            last_error = e
            decision = manager.next_decision(attempt, e)

            if not decision.should_retry:
                raise

            _sleep(decision.delay_sec)

    # Exhausted all attempts
    assert last_error is not None
    raise last_error
