"""KSO Sidecar PoP Scoped Send Rotation Decision Core — pure-logic gate.

Decides whether apply_pop_rotation_local() should be called based on
the result of run_pop_scoped_send(). Pure logic — no file I/O, no HTTP,
no rotation apply, no pending modification.

Decision is an approval gate: the caller gets a clear yes/no plus
the safe reason why rotation is allowed or blocked.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from kso_sidecar_agent.pop_scoped_send import (
    PopScopedSendResult,
    STATUS_OK as SCOPED_OK,
    STATUS_WARNING as SCOPED_WARNING,
    STATUS_ERROR as SCOPED_ERROR,
    SEND_STATUS_OK,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
    REASON_LOCK_UNAVAILABLE_SCOPED,
    REASON_LIMITED_SCOPED,
    REASON_PACKAGE_FAILED,
    REASON_SEND_FAILED,
    REASON_SEND_OK,
    REASON_INVALID_RESULT_SCOPED,
    FORBIDDEN_SUBSTRINGS,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

ALLOWED_STATUSES = frozenset({STATUS_OK, STATUS_WARNING, STATUS_ERROR})

# ── Safe reasons ─────────────────────────────────────────────────────

REASON_SEND_OK_SCOPE_AVAILABLE = "send_ok_scope_available"
REASON_NO_ELIGIBLE_EVENTS = "no_eligible_events"
REASON_LOCK_UNAVAILABLE = "lock_unavailable"
REASON_LIMITED = "limited"
REASON_DUPLICATE_PENDING_REMAINS = "duplicate_pending_remains"
REASON_PENDING_SHOULD_REMAIN = "pending_should_remain"
REASON_MISSING_SEND_RESULT = "missing_send_result"
REASON_MISSING_SENT_SCOPE = "missing_sent_scope"
REASON_EMPTY_SENT_SCOPE = "empty_sent_scope"
REASON_PENDING_NOT_UNTOUCHED = "pending_not_untouched"
REASON_ALREADY_ROTATED = "already_rotated"
REASON_INVALID_RESULT = "invalid_result"

ALLOWED_REASONS = frozenset({
    REASON_SEND_OK_SCOPE_AVAILABLE,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_LOCK_UNAVAILABLE,
    REASON_LIMITED,
    REASON_SEND_FAILED,
    REASON_PACKAGE_FAILED,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_MISSING_SEND_RESULT,
    REASON_MISSING_SENT_SCOPE,
    REASON_EMPTY_SENT_SCOPE,
    REASON_PENDING_NOT_UNTOUCHED,
    REASON_ALREADY_ROTATED,
    REASON_INVALID_RESULT,
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopSendRotationDecision:
    """Safe decision: should rotation apply run after a scoped send?

    Pure-logic result. NO file I/O, NO HTTP, NO rotation apply call.
    The caller uses this decision to decide whether to call
    apply_pop_rotation_local() with internal fields from the original
    PopScopedSendResult.

    Never contains payload body, raw JSON, line numbers list, file paths,
    IDs, fingerprints, token, secret, backend URL, or stacktrace.
    """

    status: str = STATUS_WARNING              # ok | warning | error
    rotation_allowed: bool = False
    send_attempted: bool = False
    send_success: bool = False
    scope_lines: int = 0
    pending_untouched: bool = True
    reason: str = REASON_NO_ELIGIBLE_EVENTS

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'")
        if self.reason not in ALLOWED_REASONS:
            raise ValueError(
                f"Invalid reason '{self.reason}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_REASONS))}"
            )

    def __repr__(self) -> str:
        return (
            f"PopSendRotationDecision(status={self.status!r}, "
            f"rotation_allowed={self.rotation_allowed}, "
            f"send_attempted={self.send_attempted}, "
            f"send_success={self.send_success}, "
            f"scope_lines={self.scope_lines}, "
            f"pending_untouched={self.pending_untouched}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def decide_pop_rotation_after_scoped_send(
    scoped_send_result: Any,
) -> PopSendRotationDecision:
    """Decide whether rotation apply should run after a scoped send.

    Pure logic — no file I/O, no HTTP, no rotation apply, no pending modification.

    Rotation is allowed ONLY when ALL conditions are met:
      - scoped_send_result.status == "ok"
      - scoped_send_result.send_attempted == True
      - scoped_send_result.send_success == True
      - scoped_send_result._send_run_result is not None
      - scoped_send_result._sent_scope is not None
      - scoped_send_result._sent_scope.size > 0
      - scoped_send_result.pending_untouched == True
      - scoped_send_result.rotation_applied == False

    Args:
        scoped_send_result: PopScopedSendResult from run_pop_scoped_send().

    Returns:
        PopSendRotationDecision — always safe, never raises.
    """
    # ── Validate input type ─────────────────────────────────────
    if not isinstance(scoped_send_result, PopScopedSendResult):
        return PopSendRotationDecision(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESULT,
        )

    sr = scoped_send_result

    # ── Extract common fields ───────────────────────────────────
    decision = PopSendRotationDecision(
        send_attempted=sr.send_attempted,
        send_success=sr.send_success,
        scope_lines=sr.scope_lines,
        pending_untouched=sr.pending_untouched,
    )

    # ── Gate 1: status must be ok ──────────────────────────────
    if sr.status != SCOPED_OK:
        decision.status = STATUS_WARNING
        # Try to detect duplicate/pending_should_remain from internal send result
        send_result = getattr(sr, "_send_run_result", None)
        if send_result is not None:
            send_reason = getattr(send_result, "reason", "")
            if "duplicate" in str(send_reason).lower():
                decision.reason = REASON_DUPLICATE_PENDING_REMAINS
                return decision
            if getattr(send_result, "pending_should_remain", False):
                decision.reason = REASON_PENDING_SHOULD_REMAIN
                return decision
        # Map scoped_send_result reason to decision reason
        reason_map = {
            REASON_NO_ELIGIBLE_EVENTS_SCOPED: REASON_NO_ELIGIBLE_EVENTS,
            REASON_LOCK_UNAVAILABLE_SCOPED: REASON_LOCK_UNAVAILABLE,
            REASON_LIMITED_SCOPED: REASON_LIMITED,
            REASON_PACKAGE_FAILED: REASON_PACKAGE_FAILED,
            REASON_SEND_FAILED: REASON_SEND_FAILED,
            REASON_INVALID_RESULT_SCOPED: REASON_INVALID_RESULT,
        }
        decision.reason = reason_map.get(sr.reason, REASON_SEND_FAILED)
        return decision

    # ── Gate 2: send must have been attempted ───────────────────
    if not sr.send_attempted:
        decision.status = STATUS_WARNING
        decision.reason = REASON_NO_ELIGIBLE_EVENTS
        return decision

    # ── Gate 3: send must have succeeded ────────────────────────
    if not sr.send_success:
        decision.status = STATUS_WARNING
        # Check for duplicate/pending_should_remain patterns
        if sr.reason == REASON_SEND_FAILED:
            # Try to detect duplicate from internal send result
            send_result = getattr(sr, "_send_run_result", None)
            if send_result is not None:
                send_reason = getattr(send_result, "reason", "")
                if "duplicate" in str(send_reason).lower():
                    decision.reason = REASON_DUPLICATE_PENDING_REMAINS
                    return decision
                if getattr(send_result, "pending_should_remain", False):
                    decision.reason = REASON_PENDING_SHOULD_REMAIN
                    return decision
            decision.reason = REASON_SEND_FAILED
        else:
            decision.reason = REASON_SEND_FAILED
        return decision

    # ── Gate 4: send_run_result must exist ──────────────────────
    send_result = getattr(sr, "_send_run_result", None)
    if send_result is None:
        decision.status = STATUS_WARNING
        decision.reason = REASON_MISSING_SEND_RESULT
        return decision

    # ── Gate 5: sent_scope must exist ───────────────────────────
    sent_scope = getattr(sr, "_sent_scope", None)
    if sent_scope is None:
        decision.status = STATUS_WARNING
        decision.reason = REASON_MISSING_SENT_SCOPE
        return decision

    # ── Gate 6: sent_scope must be non-empty ────────────────────
    scope_size = getattr(sent_scope, "size", 0)
    if scope_size <= 0:
        decision.status = STATUS_WARNING
        decision.reason = REASON_EMPTY_SENT_SCOPE
        return decision

    # ── Gate 7: pending must be untouched ───────────────────────
    if not sr.pending_untouched:
        decision.status = STATUS_ERROR
        decision.reason = REASON_PENDING_NOT_UNTOUCHED
        return decision

    # ── Gate 8: rotation must not have been applied already ─────
    if sr.rotation_applied:
        decision.status = STATUS_WARNING
        decision.reason = REASON_ALREADY_ROTATED
        return decision

    # ── All gates passed ────────────────────────────────────────
    decision.status = STATUS_OK
    decision.rotation_allowed = True
    decision.reason = REASON_SEND_OK_SCOPE_AVAILABLE
    return decision


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_send_rotation_decision(decision: PopSendRotationDecision) -> str:
    """Return a safe aggregated string of the rotation decision.

    Never prints payload body, line numbers list, file paths, filenames,
    IDs, fingerprints, token, secret, backend URL, or stacktrace.
    """
    lines = [
        f"status:                  {decision.status}",
        f"rotation_allowed:        {str(decision.rotation_allowed).lower()}",
        f"send_attempted:          {str(decision.send_attempted).lower()}",
        f"send_success:            {str(decision.send_success).lower()}",
        f"scope_lines:             {decision.scope_lines}",
        f"pending_untouched:       {str(decision.pending_untouched).lower()}",
        f"reason:                  {decision.reason}",
    ]

    output = "\n".join(lines)

    # Safety scan
    lower = output.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(
                f"Safe output contains forbidden substring '{fb}'"
            )

    return output
