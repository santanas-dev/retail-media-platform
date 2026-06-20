"""KSO Sidecar PoP Scoped Send Rotation Orchestrator Core.

Full safe local cycle:
  1. build_pop_send_package()  → payload + sent_scope (one snapshot)
  2. run_pop_scoped_send()     → send via retry runner → send result
  3. decide_pop_rotation_after_scoped_send() → decision
  4. if allowed: apply_pop_rotation_local(send_result, sent_scope)

This is the first step where successful fake send CAN trigger local rotation.
Decision gate + fingerprint guard protect against race conditions.

NO CLI, NO run_cycle integration, NO real backend in tests.
Auth via injected provider only.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kso_sidecar_agent.pop_scoped_send import (
    run_pop_scoped_send,
    PopScopedSendResult,
    DEFAULT_MAX_LINES,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
    REASON_LOCK_UNAVAILABLE_SCOPED,
    REASON_LIMITED_SCOPED,
    REASON_PACKAGE_FAILED,
    REASON_SEND_FAILED,
    REASON_SEND_OK,
    REASON_INVALID_RESULT_SCOPED,
    FORBIDDEN_SUBSTRINGS,
    STATUS_OK as SCOPED_OK,
    STATUS_WARNING as SCOPED_WARNING,
    STATUS_ERROR as SCOPED_ERROR,
)
from kso_sidecar_agent.pop_send_rotation_decision import (
    decide_pop_rotation_after_scoped_send,
    PopSendRotationDecision,
    REASON_SEND_OK_SCOPE_AVAILABLE,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_LOCK_UNAVAILABLE,
    REASON_LIMITED,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_MISSING_SEND_RESULT,
    REASON_MISSING_SENT_SCOPE,
    REASON_EMPTY_SENT_SCOPE,
    REASON_PENDING_NOT_UNTOUCHED,
    REASON_ALREADY_ROTATED,
    REASON_INVALID_RESULT,
)
from kso_sidecar_agent.pop_rotation_apply import (
    apply_pop_rotation_local,
    PopRotationApplyResult,
    STATUS_OK as APPLY_OK,
    STATUS_WARNING as APPLY_WARNING,
    STATUS_ERROR as APPLY_ERROR,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

ALLOWED_STATUSES = frozenset({STATUS_OK, STATUS_WARNING, STATUS_ERROR})

# ── Safe reasons ─────────────────────────────────────────────────────

REASON_ROTATED_AFTER_SEND = "rotated_after_send"
REASON_ROTATION_NOT_ALLOWED = "rotation_not_allowed"
REASON_APPLY_FAILED = "apply_failed"
REASON_SENT_SCOPE_REQUIRED = "sent_scope_required"
REASON_SENT_SCOPE_MISMATCH = "sent_scope_mismatch"

ALLOWED_REASONS = frozenset({
    REASON_ROTATED_AFTER_SEND,
    REASON_ROTATION_NOT_ALLOWED,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_LOCK_UNAVAILABLE,
    REASON_LIMITED,
    REASON_PACKAGE_FAILED,
    REASON_SEND_FAILED,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_SENT_SCOPE_REQUIRED,
    REASON_SENT_SCOPE_MISMATCH,
    REASON_APPLY_FAILED,
    REASON_INVALID_RESULT,
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopSendRotationOrchestratorResult:
    """Safe result of the full scoped send → decision → rotation pipeline.

    Never contains payload body, raw JSON, line numbers list, file paths,
    fingerprints, IDs, token, secret, backend URL, or stacktrace.
    """

    status: str = STATUS_OK                        # ok | warning | error
    send_attempted: bool = False
    send_success: bool = False
    rotation_allowed: bool = False
    rotation_applied: bool = False
    pending_untouched: bool = True
    payload_events: int = 0
    scope_lines: int = 0
    sent_records: int = 0
    quarantine_records: int = 0
    dry_run_records: int = 0
    failed_records: int = 0
    pending_rewritten: bool = False
    reason: str = REASON_NO_ELIGIBLE_EVENTS

    # ── Internal-only (repr=False — never exposed) ──────────────────
    _scoped_send_result: Any = field(default=None, repr=False)
    _decision: Any = field(default=None, repr=False)
    _apply_result: Any = field(default=None, repr=False)

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
            f"PopSendRotationOrchestratorResult(status={self.status!r}, "
            f"send_attempted={self.send_attempted}, "
            f"send_success={self.send_success}, "
            f"rotation_allowed={self.rotation_allowed}, "
            f"rotation_applied={self.rotation_applied}, "
            f"pending_untouched={self.pending_untouched}, "
            f"payload_events={self.payload_events}, "
            f"scope_lines={self.scope_lines}, "
            f"sent_records={self.sent_records}, "
            f"quarantine_records={self.quarantine_records}, "
            f"dry_run_records={self.dry_run_records}, "
            f"failed_records={self.failed_records}, "
            f"pending_rewritten={self.pending_rewritten}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_pop_scoped_send_then_rotate(
    root,
    http_client,
    auth_provider: Optional[Callable[[], Optional[str]]] = None,
    max_lines: int = DEFAULT_MAX_LINES,
) -> PopSendRotationOrchestratorResult:
    """Run full scoped send → decision → rotation pipeline.

    Pipeline:
        1. run_pop_scoped_send(root, http_client, auth_provider, max_lines)
           → builds package, sends via retry runner, returns scoped result
        2. decide_pop_rotation_after_scoped_send(scoped_result)
           → checks 8 gates: status, send_attempted, send_success,
             send_result, sent_scope, scope_size, pending_untouched,
             rotation_applied
        3. IF decision.rotation_allowed:
             apply_pop_rotation_local(
                 root,
                 send_run_result=scoped._send_run_result,
                 sent_scope=scoped._sent_scope,
                 max_lines=max_lines,
             )
        4. Return safe aggregates

    Rotation ONLY called if ALL gates pass. 409/pending_should_remain,
    fingerprint mismatch, and missing scope all prevent rotation.

    Args:
        root: Agent root path (str or Path).
        http_client: SafeHttpClient instance (fake in tests).
        auth_provider: Optional callable → access_token string.
        max_lines: Max pending lines (default 10000).

    Returns:
        PopSendRotationOrchestratorResult — always safe, never raises.
    """
    # ── Validate max_lines ───────────────────────────────────────
    if not isinstance(max_lines, int) or max_lines <= 0:
        return PopSendRotationOrchestratorResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESULT,
        )

    # ── 1. Scoped send ───────────────────────────────────────────
    scoped = run_pop_scoped_send(
        root=root,
        http_client=http_client,
        auth_provider=auth_provider,
        max_lines=max_lines,
    )

    result = PopSendRotationOrchestratorResult(
        send_attempted=scoped.send_attempted,
        send_success=scoped.send_success,
        payload_events=scoped.payload_events,
        scope_lines=scoped.scope_lines,
        pending_untouched=scoped.pending_untouched,
        _scoped_send_result=scoped,
    )

    # ── 2. Decision ──────────────────────────────────────────────
    decision = decide_pop_rotation_after_scoped_send(scoped)
    result._decision = decision
    result.rotation_allowed = decision.rotation_allowed

    if not decision.rotation_allowed:
        # Map decision reason to orchestrator reason
        result.status = STATUS_WARNING
        result.reason = decision.reason
        return result

    # ── 3. Rotation apply ────────────────────────────────────────
    try:
        apply_result = apply_pop_rotation_local(
            root=root,
            send_run_result=scoped._send_run_result,
            sent_scope=scoped._sent_scope,
            max_lines=max_lines,
        )
        result._apply_result = apply_result
    except Exception:
        result.status = STATUS_ERROR
        result.reason = REASON_APPLY_FAILED
        return result

    # ── 4. Populate from apply result ────────────────────────────
    result.rotation_applied = apply_result.applied
    result.sent_records = apply_result.sent_records
    result.quarantine_records = apply_result.quarantine_records
    result.dry_run_records = apply_result.dry_run_records
    result.failed_records = apply_result.failed_records
    result.pending_rewritten = apply_result.pending_rewritten
    result.pending_untouched = apply_result.pending_untouched

    if apply_result.status == APPLY_OK:
        result.status = STATUS_OK
        result.reason = REASON_ROTATED_AFTER_SEND
    elif apply_result.status == APPLY_WARNING:
        result.status = STATUS_WARNING
        result.reason = REASON_ROTATED_AFTER_SEND  # still applied, but warnings
    else:
        result.status = STATUS_ERROR
        result.reason = REASON_APPLY_FAILED

    return result


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_send_rotation_orchestrator_result(
    result: PopSendRotationOrchestratorResult,
) -> str:
    """Return a safe aggregated string of the orchestrator result.

    Never prints payload body, line numbers list, file paths, filenames,
    IDs, fingerprints, token, secret, backend URL, or stacktrace.
    """
    lines = [
        f"status:                  {result.status}",
        f"send_attempted:          {str(result.send_attempted).lower()}",
        f"send_success:            {str(result.send_success).lower()}",
        f"rotation_allowed:        {str(result.rotation_allowed).lower()}",
        f"rotation_applied:        {str(result.rotation_applied).lower()}",
        f"pending_untouched:       {str(result.pending_untouched).lower()}",
        f"payload_events:          {result.payload_events}",
        f"scope_lines:             {result.scope_lines}",
        f"sent_records:            {result.sent_records}",
        f"quarantine_records:      {result.quarantine_records}",
        f"dry_run_records:         {result.dry_run_records}",
        f"failed_records:          {result.failed_records}",
        f"pending_rewritten:       {str(result.pending_rewritten).lower()}",
        f"reason:                  {result.reason}",
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
