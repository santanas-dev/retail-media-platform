"""KSO Sidecar PoP Sender — safe backend response classification + HTTP send.

Pure logic + single-attempt HTTP core:
  - classify_pop_send_response() → classifies a backend response
  - send_pop_payload_batch() → sends payload via safe HTTP client (single attempt)
  - format_pop_send_result() → safe aggregated output

No retry runner, no auth refresh, no CLI, no run cycle, no file move/rotation.
Only returns safe PopSendResult — never raw response, payload, IDs, or secrets.
"""

import dataclasses as _dc
import json as _json
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

SEND_OK = "ok"
SEND_WARNING = "warning"
SEND_ERROR = "error"

# ── Safe reason values ────────────────────────────────────────────────

REASON_PROCESSED = "processed"
REASON_PARTIAL_SUCCESS = "partial_success"
REASON_DUPLICATE_BATCH = "duplicate_batch"
REASON_DUPLICATE_EVENTS = "duplicate_events"
REASON_BAD_REQUEST = "bad_request"
REASON_UNAUTHORIZED = "unauthorized"
REASON_FORBIDDEN = "forbidden"
REASON_NOT_FOUND = "not_found"
REASON_VALIDATION_ERROR = "validation_error"
REASON_RATE_LIMITED = "rate_limited"
REASON_SERVER_ERROR = "server_error"
REASON_NETWORK_ERROR = "network_error"
REASON_TIMEOUT = "timeout"
REASON_UNKNOWN_RESPONSE = "unknown_response"
REASON_INVALID_RESPONSE = "invalid_response"
REASON_NO_PAYLOAD = "no_payload"

ALLOWED_REASONS = frozenset({
    REASON_PROCESSED,
    REASON_PARTIAL_SUCCESS,
    REASON_DUPLICATE_BATCH,
    REASON_DUPLICATE_EVENTS,
    REASON_BAD_REQUEST,
    REASON_UNAUTHORIZED,
    REASON_FORBIDDEN,
    REASON_NOT_FOUND,
    REASON_VALIDATION_ERROR,
    REASON_RATE_LIMITED,
    REASON_SERVER_ERROR,
    REASON_NETWORK_ERROR,
    REASON_TIMEOUT,
    REASON_UNKNOWN_RESPONSE,
    REASON_INVALID_RESPONSE,
    REASON_NO_PAYLOAD,
})

# ── Forbidden substrings in output ────────────────────────────────────

FORBIDDEN_IN_OUTPUT = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
    "backend_base_url", "127.0.0.1", "device_code",
    "filename", "sha256",
    "full_manifest", "media_bytes", "stacktrace",
})

# ── Forbidden keys/values in response JSON ────────────────────────────

FORBIDDEN_RESPONSE_KEYS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives",
    "backend_base_url", "device_code",
    "filename", "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes", "stacktrace",
    "absolute_path",
})

# ── Allowed count fields from backend response ────────────────────────

ALLOWED_COUNT_KEYS = frozenset({
    "accepted_events", "accepted_count",
    "duplicate_events", "duplicate_count",
    "rejected_events", "rejected_count",
    "attempted_events", "attempted_count",
    "status", "batch_status",
})

# ── Allowed top-level response keys ───────────────────────────────────

ALLOWED_RESPONSE_KEYS = frozenset({
    "status", "batch_status",
    "results",
    "summary",
    "proof_batch_id",
    "accepted_events", "accepted_count",
    "duplicate_events", "duplicate_count",
    "rejected_events", "rejected_count",
    "attempted_events", "attempted_count",
    "total_events",
})


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden_in_value(value) -> bool:
    """Return True if value contains any forbidden substring."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            return True
    return False


def _safe_int(value, default=0) -> int:
    """Safely extract int from value. Rejects bools and non-numbers."""
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, value)
    if isinstance(value, float) and not isinstance(value, bool):
        return max(0, int(value))
    try:
        if isinstance(value, str):
            return max(0, int(value))
    except (ValueError, TypeError):
        return default
    return default


def _extract_counts(response_json: dict) -> dict:
    """Safely extract count fields from backend response JSON.

    Only reads allowed count keys. Never extracts IDs, paths, or secrets.
    Returns dict with safe count fields.
    """
    counts = {}
    if not isinstance(response_json, dict):
        return counts

    # ── Check for forbidden keys/values in response ──────────────
    for key in response_json:
        if key in FORBIDDEN_RESPONSE_KEYS:
            # Forbidden key found — response is suspicious, minimal counts
            return counts
        if _check_forbidden_in_value(key):
            return counts
        val = response_json.get(key)
        if isinstance(val, str) and _check_forbidden_in_value(val):
            return counts

    # ── Extract from summary if present ──────────────────────────
    summary = response_json.get("summary")
    if isinstance(summary, dict):
        for key in ("accepted", "accepted_events", "accepted_count"):
            if key in summary:
                counts["accepted_events"] = _safe_int(summary[key])
                break
        for key in ("duplicate", "duplicate_events", "duplicate_count"):
            if key in summary:
                counts["duplicate_events"] = _safe_int(summary[key])
                break
        for key in ("rejected", "rejected_events", "rejected_count"):
            if key in summary:
                counts["rejected_events"] = _safe_int(summary[key])
                break
        for key in ("attempted", "attempted_events", "attempted_count"):
            if key in summary:
                counts["attempted_events"] = _safe_int(summary[key])
                break

    # ── Extract from top-level if not in summary ────────────────
    for key in ("accepted_events", "accepted_count"):
        if "accepted_events" not in counts and key in response_json:
            counts["accepted_events"] = _safe_int(response_json[key])
            break
    for key in ("duplicate_events", "duplicate_count"):
        if "duplicate_events" not in counts and key in response_json:
            counts["duplicate_events"] = _safe_int(response_json[key])
            break
    for key in ("rejected_events", "rejected_count"):
        if "rejected_events" not in counts and key in response_json:
            counts["rejected_events"] = _safe_int(response_json[key])
            break

    # ── Derive attempted from total_events or sum ────────────────
    has_any = (
        "accepted_events" in counts
        or "duplicate_events" in counts
        or "rejected_events" in counts
    )
    if has_any and "attempted_events" not in counts:
        total = response_json.get("total_events")
        if isinstance(total, int) and not isinstance(total, bool) and total > 0:
            counts["attempted_events"] = max(0, total)
        else:
            counts["attempted_events"] = (
                counts.get("accepted_events", 0)
                + counts.get("duplicate_events", 0)
                + counts.get("rejected_events", 0)
            )

    return counts


def _validate_response_schema(response_json) -> bool:
    """Check if response JSON has a plausible backend schema.

    Returns True if response looks like a valid PoP batch response.
    Checks for:
      - 'status' or 'batch_status' at top level
      - At least one of: 'results', 'summary', accepted/rejected count fields
      - No forbidden keys/values
    """
    if not isinstance(response_json, dict):
        return False

    # Forbidden keys → invalid
    for key in response_json:
        if key in FORBIDDEN_RESPONSE_KEYS:
            return False
        if _check_forbidden_in_value(key):
            return False
        val = response_json.get(key)
        if isinstance(val, str) and _check_forbidden_in_value(val):
            return False

    # Must have status or batch_status
    has_status = "status" in response_json or "batch_status" in response_json

    # Must have results or summary or count fields
    has_data = (
        "results" in response_json
        or "summary" in response_json
        or any(k in response_json for k in ALLOWED_COUNT_KEYS if k not in ("status", "batch_status"))
    )

    return has_status or has_data


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopSendResult:
    """Safe result of PoP backend send classification.

    Never contains payload body, raw backend response, IDs,
    backend URL, token, filename, sha256, paths, or secrets.
    """

    send_status: str = SEND_WARNING          # ok | warning | error
    attempted_events: int = 0
    accepted_events: int = 0
    duplicate_events: int = 0
    rejected_events: int = 0
    http_status: Optional[int] = None
    elapsed_ms: Optional[float] = None
    retryable: bool = False
    auth_refresh_required: bool = False
    pending_should_remain: bool = True       # True until confirmed processed
    reason: str = REASON_NO_PAYLOAD

    def __post_init__(self) -> None:
        if self.reason not in ALLOWED_REASONS:
            raise ValueError(
                f"Invalid reason '{self.reason}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_REASONS))}"
            )

    def __repr__(self) -> str:
        """Repr only shows safe fields — no raw response, no IDs, no secrets."""
        return (
            f"PopSendResult(send_status={self.send_status!r}, "
            f"attempted_events={self.attempted_events}, "
            f"accepted_events={self.accepted_events}, "
            f"duplicate_events={self.duplicate_events}, "
            f"rejected_events={self.rejected_events}, "
            f"http_status={self.http_status}, "
            f"elapsed_ms={self.elapsed_ms}, "
            f"retryable={self.retryable}, "
            f"auth_refresh_required={self.auth_refresh_required}, "
            f"pending_should_remain={self.pending_should_remain}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Response classifier
# ══════════════════════════════════════════════════════════════════════

def classify_pop_send_response(
    http_status: Optional[int] = None,
    response_json: Optional[Any] = None,
    error_type: Optional[str] = None,
    elapsed_ms: Optional[float] = None,
    attempted_events: int = 0,
) -> PopSendResult:
    """Classify a future backend response after PoP batch send.

    Pure logic — no HTTP, no backend calls, no file I/O, no retry runner.
    Takes the HTTP status, response JSON, optional error_type, and timing
    and returns a safe PopSendResult with classification and counts.

    Rules (in priority order):
        1. Network/timeout errors (via error_type) → error, retryable
        2. HTTP 2xx with valid response → ok/warning based on counts
        3. HTTP 4xx → classified by specific status code
        4. HTTP 5xx → error, retryable
        5. Unknown → error, pending_should_remain

    Args:
        http_status: HTTP status code (or None for network errors).
        response_json: Parsed backend response JSON body (or None).
        error_type: One of 'network', 'timeout', or None for HTTP responses.
        elapsed_ms: Request elapsed time in milliseconds.
        attempted_events: Number of events in the sent payload.

    Returns:
        PopSendResult — always safe, never raises.
        pending_should_remain=False only for confirmed 'processed'.
    """
    # ── Default result (fail-safe) ────────────────────────────────
    result = PopSendResult(
        attempted_events=max(0, attempted_events),
        http_status=http_status,
        elapsed_ms=elapsed_ms,
    )

    # ── Network / timeout errors (no HTTP status) ─────────────────
    if error_type is not None:
        if error_type == "network":
            result.send_status = SEND_ERROR
            result.reason = REASON_NETWORK_ERROR
            result.retryable = True
            result.pending_should_remain = True
        elif error_type == "timeout":
            result.send_status = SEND_ERROR
            result.reason = REASON_TIMEOUT
            result.retryable = True
            result.pending_should_remain = True
        else:
            result.send_status = SEND_ERROR
            result.reason = REASON_UNKNOWN_RESPONSE
            result.retryable = False
            result.pending_should_remain = True
        return result

    # ── No HTTP status → unknown ──────────────────────────────────
    if http_status is None:
        result.send_status = SEND_ERROR
        result.reason = REASON_UNKNOWN_RESPONSE
        result.retryable = False
        result.pending_should_remain = True
        return result

    # ── Validate response JSON schema ─────────────────────────────
    schema_valid = _validate_response_schema(response_json) if response_json is not None else False

    # ── Extract safe counts ───────────────────────────────────────
    counts = {}
    if isinstance(response_json, dict):
        counts = _extract_counts(response_json)

    accepted = counts.get("accepted_events", 0)
    duplicate = counts.get("duplicate_events", 0)
    rejected = counts.get("rejected_events", 0)
    attempted_from_resp = counts.get("attempted_events", 0)

    result.accepted_events = accepted
    result.duplicate_events = duplicate
    result.rejected_events = rejected
    if attempted_from_resp > 0:
        result.attempted_events = attempted_from_resp

    # ── 2xx ───────────────────────────────────────────────────────
    if 200 <= http_status < 300:
        # FIRST: check response for forbidden fields — fail safe
        if isinstance(response_json, dict):
            for key in response_json:
                if key in FORBIDDEN_RESPONSE_KEYS:
                    result.send_status = SEND_WARNING
                    result.reason = REASON_INVALID_RESPONSE
                    result.retryable = False
                    result.pending_should_remain = True
                    return result
                if _check_forbidden_in_value(key):
                    result.send_status = SEND_WARNING
                    result.reason = REASON_INVALID_RESPONSE
                    result.retryable = False
                    result.pending_should_remain = True
                    return result
                val = response_json.get(key)
                if isinstance(val, str) and _check_forbidden_in_value(val):
                    result.send_status = SEND_WARNING
                    result.reason = REASON_INVALID_RESPONSE
                    result.retryable = False
                    result.pending_should_remain = True
                    return result

            # Also check summary values
            summary = response_json.get("summary")
            if isinstance(summary, dict):
                for skey, sval in summary.items():
                    if isinstance(sval, str) and _check_forbidden_in_value(sval):
                        result.send_status = SEND_WARNING
                        result.reason = REASON_INVALID_RESPONSE
                        result.retryable = False
                        result.pending_should_remain = True
                        return result

        # Check response status field
        resp_status = None
        if isinstance(response_json, dict):
            resp_status = response_json.get("status") or response_json.get("batch_status")

        # ── Priority: partial (rejected events present) ──────
        if rejected > 0 and accepted > 0:
            result.send_status = SEND_WARNING
            result.reason = REASON_PARTIAL_SUCCESS
            result.retryable = False
            result.pending_should_remain = True
            return result

        if rejected > 0 and accepted == 0:
            result.send_status = SEND_WARNING
            result.reason = REASON_PARTIAL_SUCCESS
            result.retryable = False
            result.pending_should_remain = True
            return result

        # ── Priority: all duplicate (no accepted, no rejected) ──
        # But check explicit batch status first
        if resp_status in ("duplicate_batch", "duplicate"):
            result.send_status = SEND_WARNING
            result.reason = REASON_DUPLICATE_BATCH
            result.retryable = False
            result.pending_should_remain = False
            result.duplicate_events = result.attempted_events
            return result

        if duplicate > 0 and accepted == 0 and rejected == 0:
            result.send_status = SEND_OK
            result.reason = REASON_DUPLICATE_EVENTS
            result.retryable = False
            result.pending_should_remain = False
            result.duplicate_events = result.attempted_events
            return result

        if resp_status in ("processed", "pop_batch_processed"):
            result.send_status = SEND_OK
            result.reason = REASON_PROCESSED
            result.retryable = False
            result.auth_refresh_required = False
            result.pending_should_remain = False
            # Only fallback if no counts were extracted at all
            if accepted == 0 and duplicate == 0 and rejected == 0 and not counts:
                result.accepted_events = result.attempted_events
            return result

        if resp_status in ("duplicate_batch", "duplicate"):
            result.send_status = SEND_WARNING
            result.reason = REASON_DUPLICATE_BATCH
            result.retryable = False
            result.pending_should_remain = False
            result.duplicate_events = result.attempted_events
            return result

        if resp_status in ("rejected", "pop_batch_rejected"):
            result.send_status = SEND_ERROR
            result.reason = REASON_VALIDATION_ERROR
            result.retryable = False
            result.pending_should_remain = True
            return result

        if accepted > 0 and rejected == 0:
            result.send_status = SEND_OK
            result.reason = REASON_PROCESSED
            result.retryable = False
            result.pending_should_remain = False
            return result

        if not schema_valid:
            result.send_status = SEND_WARNING
            result.reason = REASON_INVALID_RESPONSE
            result.retryable = False
            result.pending_should_remain = True
            return result

        # 2xx with empty/unrecognized body
        result.send_status = SEND_WARNING
        result.reason = REASON_INVALID_RESPONSE
        result.retryable = False
        result.pending_should_remain = True
        return result

    # ── 4xx ───────────────────────────────────────────────────────
    if 400 <= http_status < 500:
        if http_status == 400:
            result.send_status = SEND_ERROR
            result.reason = REASON_BAD_REQUEST
            result.retryable = False
            result.pending_should_remain = True
            return result

        if http_status == 401:
            result.send_status = SEND_WARNING
            result.reason = REASON_UNAUTHORIZED
            result.retryable = True
            result.auth_refresh_required = True
            result.pending_should_remain = True
            return result

        if http_status == 403:
            result.send_status = SEND_ERROR
            result.reason = REASON_FORBIDDEN
            result.retryable = False
            result.pending_should_remain = True
            return result

        if http_status == 404:
            result.send_status = SEND_ERROR
            result.reason = REASON_NOT_FOUND
            result.retryable = False
            result.pending_should_remain = True
            return result

        if http_status == 409:
            # Duplicate batch — backend already saw this batch_id,
            # but without explicit processed/accepted confirmation from backend
            # we must NOT assume the batch can be safely removed.
            # pending_should_remain=True by default.
            # Safe duplicate removal: only if a future backend response contract
            # explicitly confirms acceptance with count fields.
            result.send_status = SEND_WARNING
            result.reason = REASON_DUPLICATE_BATCH
            result.retryable = False
            result.pending_should_remain = True
            return result

        if http_status == 422:
            result.send_status = SEND_ERROR
            result.reason = REASON_VALIDATION_ERROR
            result.retryable = False
            result.pending_should_remain = True
            return result

        if http_status == 429:
            result.send_status = SEND_WARNING
            result.reason = REASON_RATE_LIMITED
            result.retryable = True
            result.pending_should_remain = True
            return result

        # Other 4xx
        result.send_status = SEND_ERROR
        result.reason = REASON_BAD_REQUEST
        result.retryable = False
        result.pending_should_remain = True
        return result

    # ── 5xx ───────────────────────────────────────────────────────
    if 500 <= http_status < 600:
        result.send_status = SEND_ERROR
        result.reason = REASON_SERVER_ERROR
        result.retryable = True
        result.pending_should_remain = True
        return result

    # ── Unknown status ────────────────────────────────────────────
    result.send_status = SEND_ERROR
    result.reason = REASON_UNKNOWN_RESPONSE
    result.retryable = False
    result.pending_should_remain = True
    return result


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_send_result(result: PopSendResult) -> str:
    """Return a safe aggregated string of the send result.

    Never prints raw backend response, payload body, batch_id,
    device_event_id, manifest_item_id, campaign_id, filename,
    sha256, paths, backend URL, token, or secrets.
    """
    lines = [
        f"send_status:              {result.send_status}",
        f"attempted_events:         {result.attempted_events}",
        f"accepted_events:          {result.accepted_events}",
        f"duplicate_events:         {result.duplicate_events}",
        f"rejected_events:          {result.rejected_events}",
    ]
    if result.http_status is not None:
        lines.append(f"http_status:              {result.http_status}")
    if result.elapsed_ms is not None:
        lines.append(f"elapsed_ms:               {result.elapsed_ms:.1f}")
    lines.append(f"retryable:                {str(result.retryable).lower()}")
    lines.append(f"auth_refresh_required:    {str(result.auth_refresh_required).lower()}")
    lines.append(f"pending_should_remain:    {str(result.pending_should_remain).lower()}")
    lines.append(f"reason:                   {result.reason}")

    output = "\n".join(lines)

    # Safety scan: ensure no forbidden substrings in output
    lower = output.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            raise ValueError(
                f"Safe output contains forbidden substring '{fb}'"
            )

    return output


# ══════════════════════════════════════════════════════════════════════
# Endpoint
# ══════════════════════════════════════════════════════════════════════

# This path is covered by _ALLOWED_PREFIXES in http_client.py:
#   "/api/device-gateway/pop/" → allows "/api/device-gateway/pop/events/batch"
POP_BATCH_ENDPOINT = "/api/device-gateway/pop/events/batch"


# ══════════════════════════════════════════════════════════════════════
# Payload serialization
# ══════════════════════════════════════════════════════════════════════

def _envelope_to_request_payload(envelope) -> dict:
    """Convert PopPayloadEnvelope to a JSON-safe dict for POST body.

    Uses dataclasses.asdict for safe nested conversion.
    Never logs the result — the dict is only for HTTP body, not for output.
    """
    events = []
    for evt in envelope.events:
        event_dict = _dc.asdict(evt)
        events.append(event_dict)

    return {
        "batch_id": envelope.batch_id,
        "sent_at": envelope.sent_at,
        "events": events,
    }


# ══════════════════════════════════════════════════════════════════════
# HTTP Sender (single-attempt, no retry, no auth refresh)
# ══════════════════════════════════════════════════════════════════════

def send_pop_payload_batch(
    http_client,
    payload_envelope,
    access_token: Optional[str] = None,
    now: Optional[str] = None,
) -> PopSendResult:
    """Send an in-memory PopPayloadEnvelope to backend via safe HTTP client.

    Single-attempt only — no retry loop, no auth refresh, no CLI.
    Uses existing SafeHttpClient.post_json() with allowlisted path.

    Pipeline:
        1. Validate envelope (non-None, has events)
        2. Build Authorization header if token provided
        3. Build request payload from envelope
        4. POST to POP_BATCH_ENDPOINT
        5. Classify response via classify_pop_send_response()
        6. Return safe PopSendResult

    Args:
        http_client: SafeHttpClient instance (or duck-typed equivalent).
        payload_envelope: PopPayloadEnvelope from build_pop_backend_payload().
        access_token: Optional JWT access token (in-memory only, never logged).
        now: Optional ISO8601 timestamp override for sent_at.

    Returns:
        PopSendResult — always safe, never raises, never exposes secrets/IDs.

    Never logs: token, Authorization header, payload body, batch_id,
    device_event_id, manifest_item_id, campaign_id, endpoint URL.
    """
    # ── No payload → bail out without HTTP ────────────────────────
    if payload_envelope is None:
        return PopSendResult(
            send_status=SEND_WARNING,
            attempted_events=0,
            reason=REASON_NO_PAYLOAD,
            pending_should_remain=True,
        )

    events = getattr(payload_envelope, "events", None)
    if not events:
        return PopSendResult(
            send_status=SEND_WARNING,
            attempted_events=0,
            reason=REASON_NO_PAYLOAD,
            pending_should_remain=True,
        )

    attempted_events = len(events)

    # ── Build headers ─────────────────────────────────────────────
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    # ── Build request payload ─────────────────────────────────────
    try:
        request_payload = _envelope_to_request_payload(payload_envelope)
    except Exception:
        return PopSendResult(
            send_status=SEND_ERROR,
            attempted_events=attempted_events,
            reason=REASON_BAD_REQUEST,
            retryable=False,
            pending_should_remain=True,
        )

    # ── POST to backend ──────────────────────────────────────────
    start = _time.monotonic()
    try:
        response = http_client.post_json(POP_BATCH_ENDPOINT, request_payload, headers)
    except Exception as e:
        elapsed_ms = (_time.monotonic() - start) * 1000

        # Check for HttpClientError (has status_code, retryable attrs)
        status_code = getattr(e, "status_code", 0)
        retryable = getattr(e, "retryable", False)

        if status_code > 0:
            # HTTP-level error (4xx/5xx)
            return classify_pop_send_response(
                http_status=status_code,
                response_json=None,
                elapsed_ms=elapsed_ms,
                attempted_events=attempted_events,
            )

        # Network / timeout / connection error (status_code == 0, retryable)
        msg = str(e).lower() if hasattr(e, "__str__") else ""
        if "timeout" in msg:
            return classify_pop_send_response(
                error_type="timeout",
                elapsed_ms=elapsed_ms,
                attempted_events=attempted_events,
            )
        return classify_pop_send_response(
            error_type="network",
            elapsed_ms=elapsed_ms,
            attempted_events=attempted_events,
        )

    elapsed_ms = response.elapsed_ms

    # ── Classify response ────────────────────────────────────────
    result = classify_pop_send_response(
        http_status=response.status_code,
        response_json=response.json_body,
        elapsed_ms=elapsed_ms,
        attempted_events=attempted_events,
    )

    return result
