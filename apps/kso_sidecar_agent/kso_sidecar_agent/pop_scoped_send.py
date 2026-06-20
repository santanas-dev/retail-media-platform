"""KSO Sidecar PoP Scoped Send Runner Core — safe scoped send orchestration.

Builds a send package (payload + sent_scope) from pending snapshot,
sends via existing retry runner, and returns safe aggregate result
with internal sent_scope for future rotation apply.

Pipeline:
  1. build_pop_send_package(root, max_lines)  → payload + sent_scope
  2. if no package → return no-op
  3. run_pop_send_with_retry(http_post, payload)  → send_run_result
  4. return PopScopedSendResult (safe aggregates)

NO rotation apply, NO pending rewrite/delete, NO target file write.
NO real backend in tests. Auth via injected token provider only.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kso_sidecar_agent.pop_send_package import (
    build_pop_send_package,
    PopSendPackageResult,
    DEFAULT_MAX_LINES,
    REASON_NO_PENDING_FILE,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_LOCK_UNAVAILABLE,
    REASON_LIMITED,
    REASON_INVALID_RESULT,
    REASON_BUILT,
    FORBIDDEN_SUBSTRINGS,
)
from kso_sidecar_agent.pop_sender_runner import (
    run_pop_send_with_retry,
    PopSendRunResult,
    RUN_OK,
    RUN_WARNING,
    RUN_ERROR,
    format_pop_send_run_result,
)
from kso_sidecar_agent.pop_rotation_materializer import (
    PopRotationSentScope,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

# ── Send status (for result.send_status field) ────────────────────────

SEND_STATUS_OK = "ok"
SEND_STATUS_WARNING = "warning"
SEND_STATUS_ERROR = "error"
SEND_STATUS_SKIPPED = "skipped"

ALLOWED_SEND_STATUSES = frozenset({
    SEND_STATUS_OK,
    SEND_STATUS_WARNING,
    SEND_STATUS_ERROR,
    SEND_STATUS_SKIPPED,
})

# ── Safe reasons ─────────────────────────────────────────────────────

REASON_BUILT_SCOPED = "built"
REASON_NO_ELIGIBLE_EVENTS_SCOPED = "no_eligible_events"
REASON_PACKAGE_FAILED = "package_failed"
REASON_SEND_FAILED = "send_failed"
REASON_SEND_OK = "send_ok"
REASON_LOCK_UNAVAILABLE_SCOPED = "lock_unavailable"
REASON_LIMITED_SCOPED = "limited"
REASON_INVALID_RESULT_SCOPED = "invalid_result"

ALLOWED_REASONS = frozenset({
    REASON_BUILT_SCOPED,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
    REASON_PACKAGE_FAILED,
    REASON_SEND_FAILED,
    REASON_SEND_OK,
    REASON_LOCK_UNAVAILABLE_SCOPED,
    REASON_LIMITED_SCOPED,
    REASON_INVALID_RESULT_SCOPED,
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopScopedSendResult:
    """Safe result of scoped send (package build + send via retry runner).

    Safe aggregate fields. Internal fields (_send_run_result, _sent_scope)
    are hidden (repr=False) for future rotation apply integration.

    Never contains payload body, raw JSON, line numbers list, file paths,
    filenames, manifest_item_id, device_event_id, batch_id, campaign_id,
    creative_id, sha256, token, backend URL, exception text, stacktrace,
    or secrets.
    """

    status: str = STATUS_OK                          # ok | warning | error
    send_attempted: bool = False
    send_success: bool = False
    package_built: bool = False
    payload_events: int = 0
    scope_lines: int = 0
    send_status: str = SEND_STATUS_SKIPPED           # ok | warning | error | skipped
    pending_untouched: bool = True
    rotation_applied: bool = False
    reason: str = REASON_NO_ELIGIBLE_EVENTS_SCOPED

    # ── Internal-only (repr=False — never exposed) ────────────────────
    _send_run_result: Optional[PopSendRunResult] = field(default=None, repr=False)
    _sent_scope: Optional[PopRotationSentScope] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.status not in (STATUS_OK, STATUS_WARNING, STATUS_ERROR):
            raise ValueError(f"Invalid status '{self.status}'")
        if self.send_status not in ALLOWED_SEND_STATUSES:
            raise ValueError(f"Invalid send_status '{self.send_status}'")
        if self.reason not in ALLOWED_REASONS:
            raise ValueError(
                f"Invalid reason '{self.reason}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_REASONS))}"
            )

    def __repr__(self) -> str:
        return (
            f"PopScopedSendResult(status={self.status!r}, "
            f"send_attempted={self.send_attempted}, "
            f"send_success={self.send_success}, "
            f"package_built={self.package_built}, "
            f"payload_events={self.payload_events}, "
            f"scope_lines={self.scope_lines}, "
            f"send_status={self.send_status!r}, "
            f"pending_untouched={self.pending_untouched}, "
            f"rotation_applied={self.rotation_applied}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_pop_scoped_send(
    root,
    http_client,
    auth_provider: Optional[Callable[[], Optional[str]]] = None,
    max_lines: int = DEFAULT_MAX_LINES,
) -> PopScopedSendResult:
    """Run a full scoped send: build package → send via retry runner.

    Pipeline:
        1. build_pop_send_package(root, max_lines) → package
        2. If no package / no eligible → return safe no-op
        3. Extract payload envelope from package
        4. Obtain access token from auth_provider (if provided)
        5. run_pop_send_with_retry(http_client, payload, token=..., auth_cb=...)
        6. Return PopScopedSendResult with internal sent_scope

    The sent_scope is EXACTLY the one from build_pop_send_package —
    no re-scanning, no rebuilding. Pending untouched.

    NO rotation apply. NO pending rewrite. NO target file write.
    NO real backend in tests.

    Args:
        root: Agent root path (str or Path).
        http_client: SafeHttpClient instance (for retry runner).
        auth_provider: Optional callable → access_token string (or None on failure).
            Used as both initial token and refresh callback.
        max_lines: Max pending lines (default 10000). <= 0 → error.

    Returns:
        PopScopedSendResult — always safe, never raises.
    """
    # ── Validate max_lines ───────────────────────────────────────
    if not isinstance(max_lines, int) or max_lines <= 0:
        return PopScopedSendResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESULT_SCOPED,
        )

    # ── 1. Build package ─────────────────────────────────────────
    package = build_pop_send_package(root, max_lines=max_lines)

    # ── Lock unavailable / other failures during package build ───
    if not package.package_built:
        reason_map = {
            REASON_NO_PENDING_FILE: REASON_NO_ELIGIBLE_EVENTS_SCOPED,
            REASON_NO_ELIGIBLE_EVENTS: REASON_NO_ELIGIBLE_EVENTS_SCOPED,
            REASON_LOCK_UNAVAILABLE: REASON_LOCK_UNAVAILABLE_SCOPED,
            REASON_LIMITED: REASON_LIMITED_SCOPED,
            REASON_INVALID_RESULT: REASON_INVALID_RESULT_SCOPED,
        }
        mapped_reason = reason_map.get(package.reason, REASON_PACKAGE_FAILED)

        return PopScopedSendResult(
            status=STATUS_WARNING if package.reason == REASON_LOCK_UNAVAILABLE
                   or package.reason == REASON_LIMITED else STATUS_OK,
            package_built=package.package_built,
            payload_events=package.payload_events,
            scope_lines=package.scope_lines,
            reason=mapped_reason,
        )

    # ── No eligible events in package ────────────────────────────
    if package.payload_events == 0 or package._payload is None:
        return PopScopedSendResult(
            status=STATUS_OK,
            package_built=False,
            payload_events=0,
            scope_lines=0,
            reason=REASON_NO_ELIGIBLE_EVENTS_SCOPED,
        )

    # ── 2. Obtain access token ───────────────────────────────────
    access_token: Optional[str] = None
    if auth_provider is not None:
        try:
            access_token = auth_provider()
        except Exception:
            access_token = None

    # ── 3. Send via retry runner ─────────────────────────────────
    payload = package._payload
    sent_scope = package._sent_scope

    try:
        send_result = run_pop_send_with_retry(
            http_client=http_client,
            payload_envelope=payload,
            access_token=access_token,
            refresh_auth_callback=auth_provider,
            max_attempts=3,
        )
    except Exception:
        # Catch-all: send failed
        return PopScopedSendResult(
            status=STATUS_ERROR,
            send_attempted=True,
            send_success=False,
            package_built=True,
            payload_events=package.payload_events,
            scope_lines=package.scope_lines,
            send_status=SEND_STATUS_ERROR,
            pending_untouched=True,
            reason=REASON_SEND_FAILED,
        )

    # ── 4. Determine outcome ─────────────────────────────────────
    send_ok = send_result.run_status == RUN_OK
    send_success = send_ok and not send_result.pending_should_remain

    if send_success:
        return PopScopedSendResult(
            status=STATUS_OK,
            send_attempted=True,
            send_success=True,
            package_built=True,
            payload_events=package.payload_events,
            scope_lines=package.scope_lines,
            send_status=SEND_STATUS_OK,
            pending_untouched=True,
            reason=REASON_SEND_OK,
            _send_run_result=send_result,
            _sent_scope=sent_scope,
        )
    elif send_result.run_status == RUN_ERROR:
        return PopScopedSendResult(
            status=STATUS_ERROR,
            send_attempted=True,
            send_success=False,
            package_built=True,
            payload_events=package.payload_events,
            scope_lines=package.scope_lines,
            send_status=SEND_STATUS_ERROR,
            pending_untouched=True,
            reason=REASON_SEND_FAILED,
            _send_run_result=send_result,
            _sent_scope=sent_scope,
        )
    else:
        # RUN_WARNING — send attempted but not fully successful
        return PopScopedSendResult(
            status=STATUS_WARNING,
            send_attempted=True,
            send_success=False,
            package_built=True,
            payload_events=package.payload_events,
            scope_lines=package.scope_lines,
            send_status=SEND_STATUS_WARNING,
            pending_untouched=True,
            reason=REASON_SEND_FAILED,
            _send_run_result=send_result,
            _sent_scope=sent_scope,
        )


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_scoped_send_result(result: PopScopedSendResult) -> str:
    """Return a safe aggregated string of the scoped send result.

    Never prints payload body, line numbers list, file paths, filenames,
    manifest_item_id, device_event_id, batch_id, campaign_id, creative_id,
    sha256, token, backend URL, exception text, stacktrace, or secrets.
    """
    lines = [
        f"status:                  {result.status}",
        f"send_attempted:          {str(result.send_attempted).lower()}",
        f"send_success:            {str(result.send_success).lower()}",
        f"package_built:           {str(result.package_built).lower()}",
        f"payload_events:          {result.payload_events}",
        f"scope_lines:             {result.scope_lines}",
        f"send_status:             {result.send_status}",
        f"pending_untouched:       {str(result.pending_untouched).lower()}",
        f"rotation_applied:        {str(result.rotation_applied).lower()}",
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
