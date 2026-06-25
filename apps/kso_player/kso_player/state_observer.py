"""KSO Player State Observer — safe idle-only state contract.

The state observer reads a local JSON state file and produces an immutable
PlayerStateSnapshot. The snapshot enforces safety rules:

    - Only 'idle' permits display
    - All other states (busy, payment, error, unknown, stale, ...) → hide
    - Stale/unknown always hide
    - Forbidden fields (receipt, payment, fiscal, customer, PII) → reject

Safety:
    - NO network (HTTP, sockets, subprocess)
    - NO UKM5 DB access (MySQL, Redis, camera_agent — NONE)
    - NO receipt/payment/fiscal/personal data
    - NO Chromium, NO X11
    - File read errors → safe default (unknown, hidden)

The observer is a PURE contract — it does NOT run loops, does NOT poll
filesystem on a timer, does NOT drive any runtime.

Pipeline:
    state.json → read_state_snapshot() → PlayerStateSnapshot
    PlayerStateSnapshot + kill_switch → resolve_visibility() → visible/hidden
    visible/hidden → ShellPlan.visible_plan
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, FrozenSet


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

DEFAULT_STATE_PATH = "/run/verny/kso/state.json"

# Allowed states (only 'idle' permits ad display)
STATE_IDLE = "idle"
STATE_BUSY = "busy"
STATE_SCAN = "scan"
STATE_CART = "cart"
STATE_PAYMENT = "payment"
STATE_ERROR = "error"
STATE_OFFLINE = "offline"
STATE_UNKNOWN = "unknown"
STATE_STALE = "stale"

ALLOWED_STATES: FrozenSet[str] = frozenset({
    STATE_IDLE,
    STATE_BUSY,
    STATE_SCAN,
    STATE_CART,
    STATE_PAYMENT,
    STATE_ERROR,
    STATE_OFFLINE,
    STATE_UNKNOWN,
    STATE_STALE,
})

# States that allow showing ads
SHOW_STATES: FrozenSet[str] = frozenset({STATE_IDLE})

# States that force hiding
HIDE_STATES: FrozenSet[str] = frozenset({
    STATE_BUSY,
    STATE_SCAN,
    STATE_CART,
    STATE_PAYMENT,
    STATE_ERROR,
    STATE_OFFLINE,
    STATE_UNKNOWN,
    STATE_STALE,
})

# Default staleness threshold (5 seconds)
DEFAULT_STALE_AFTER_MS = 5_000

# ── Forbidden fields ────────────────────────────────────────────────
# These fields MUST NOT appear in state.json. Their presence means the
# state source is leaking receipt/payment/fiscal/customer data.
# The observer rejects any data containing these keys.

FORBIDDEN_STATE_KEYS: FrozenSet[str] = frozenset({
    # Receipt / transaction data
    "receipt_id",
    "receipt_number",
    "transaction_id",
    "payment_amount",
    "payment_method",
    "fiscal_data",
    "fiscal_sign",
    "fiscal_document",
    "items",
    "total_amount",
    "total_quantity",
    # Customer / personal data
    "customer_name",
    "customer_id",
    "customer_phone",
    "customer_email",
    "card_number",
    "pan",
    "phone",
    "email",
    "first_name",
    "last_name",
    "full_name",
    # Cashier / operator
    "cashier_id",
    "cashier_name",
    "operator_id",
    # DB / secrets
    "ukm5_db_host",
    "ukm5_db_port",
    "ukm5_db_user",
    "ukm5_db_password",
    "ukm5_db_name",
    "mysql_connection",
    "redis_connection",
    "connection_string",
    "dsn",
    "secret",
    "token",
    "password",
    "api_key",
    "backend_url",
    "backend_base_url",
    # File paths (must not leak local paths)
    "local_path",
    "file_path",
    "filesystem_path",
    "absolute_path",
})

# Forbidden substrings in state keys (lowercase check)
FORBIDDEN_KEY_PATTERNS: tuple = (
    "receipt", "transaction", "payment", "fiscal",
    "customer", "card", "pan", "phone", "email",
    "cashier", "operator", "ukm5", "mysql", "redis",
    "secret", "token", "password", "api_key",
    "backend_url", "file_path", "filesystem_path",
)


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PlayerStateSnapshot:
    """Immutable snapshot of the KSO terminal state.

    Contains ONLY safe fields — no receipt, payment, fiscal, customer data.
    Any forbidden field triggers rejection at construction time.

    Fields:
        schema_version: State schema version (currently 1).
        device_code: KSO device identifier (e.g. 'a-05954').
        state: Current terminal state (must be in ALLOWED_STATES).
        source: Origin of the state data (e.g. 'state_adapter', 'stub').
        updated_at_utc: ISO-8601 UTC timestamp of last state update.
        stale_after_ms: Time after which the state is considered stale.
    """

    schema_version: int
    device_code: str
    state: str
    source: str
    updated_at_utc: str
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS

    # ── Derived properties ──────────────────────────────────────────

    @property
    def is_idle(self) -> bool:
        """Return True if the KSO terminal is in idle state."""
        return self.state == STATE_IDLE

    @property
    def is_stale(self) -> bool:
        """Return True if the state timestamp is older than stale_after_ms."""
        return _is_timestamp_stale(self.updated_at_utc, self.stale_after_ms)

    @property
    def effective_state(self) -> str:
        """Return the effective state: 'stale' if stale, otherwise the real state."""
        if self.state == STATE_UNKNOWN:
            return STATE_UNKNOWN
        if self.is_stale:
            return STATE_STALE
        return self.state

    @property
    def allows_display(self) -> bool:
        """Return True if this state permits ad display (idle, not stale)."""
        return self.effective_state == STATE_IDLE

    def __repr__(self) -> str:
        return (
            f"PlayerStateSnapshot("
            f"device={self.device_code!r}, "
            f"state={self.state!r}, "
            f"effective={self.effective_state!r}, "
            f"source={self.source!r})"
        )

    # ── Validation ──────────────────────────────────────────────────

    def __post_init__(self):
        """Validate snapshot invariants at construction time."""
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise ValueError(
                f"schema_version must be positive int, got {self.schema_version!r}"
            )
        if not self.device_code or not isinstance(self.device_code, str):
            raise ValueError(f"device_code must be non-empty string")
        if self.state not in ALLOWED_STATES:
            raise ValueError(
                f"Invalid state {self.state!r}. Allowed: {sorted(ALLOWED_STATES)}"
            )
        if not self.source or not isinstance(self.source, str):
            raise ValueError(f"source must be non-empty string")
        if not self.updated_at_utc or not isinstance(self.updated_at_utc, str):
            raise ValueError(f"updated_at_utc must be non-empty ISO-8601 string")
        if not isinstance(self.stale_after_ms, int) or self.stale_after_ms < 0:
            raise ValueError(
                f"stale_after_ms must be non-negative int, got {self.stale_after_ms!r}"
            )


# ══════════════════════════════════════════════════════════════════════
# Pre-built safe snapshots
# ══════════════════════════════════════════════════════════════════════

_UNKNOWN_SNAPSHOT = PlayerStateSnapshot(
    schema_version=1,
    device_code="unknown",
    state=STATE_UNKNOWN,
    source="observer",
    updated_at_utc="1970-01-01T00:00:00Z",
    stale_after_ms=DEFAULT_STALE_AFTER_MS,
)


# ══════════════════════════════════════════════════════════════════════
# Validation helpers (pure functions)
# ══════════════════════════════════════════════════════════════════════


def _is_timestamp_stale(updated_at_utc: str, stale_after_ms: int) -> bool:
    """Return True if the given timestamp is older than stale_after_ms."""
    try:
        from kso_player.timestamp_utils import parse_iso_utc
        ts_naive = parse_iso_utc(updated_at_utc)
        if ts_naive is None:
            return True  # unparseable → treat as stale/hidden
        ts = ts_naive.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta_ms = (now - ts).total_seconds() * 1000
        return delta_ms > stale_after_ms
    except (ValueError, TypeError, AttributeError):
        # Unparseable timestamp → treat as stale
        return True


def _has_forbidden_fields(data: dict) -> bool:
    """Return True if the dict contains any forbidden keys.

    Checks exact key names AND key substrings (forbidden patterns).
    Case-insensitive for substring checks.
    """
    for key in data:
        key_str = str(key)
        # Exact match
        if key_str in FORBIDDEN_STATE_KEYS:
            return True
        # Substring match (case-insensitive)
        key_lower = key_str.lower()
        for pattern in FORBIDDEN_KEY_PATTERNS:
            if pattern in key_lower:
                return True
    return False


def _extract_safe_fields(data: dict) -> dict:
    """Extract only the 6 safe fields from raw state JSON.

    Silently drops any unknown keys. This ensures ONLY the snapshot
    fields pass through, even if upstream tries to add extra data.
    """
    return {
        "schema_version": data.get("schema_version", 1),
        "device_code": str(data.get("device_code", "unknown")),
        "state": str(data.get("state", STATE_UNKNOWN)).strip().lower(),
        "source": str(data.get("source", "observer")),
        "updated_at_utc": str(data.get("updated_at_utc", "1970-01-01T00:00:00Z")),
        "stale_after_ms": int(data.get("stale_after_ms", DEFAULT_STALE_AFTER_MS)),
    }


def from_dict(data: dict) -> PlayerStateSnapshot:
    """Create a PlayerStateSnapshot from a validated dict.

    Args:
        data: Dict with the 6 safe state fields.

    Returns:
        PlayerStateSnapshot (frozen, validated).

    Raises:
        ValueError: If data contains forbidden fields or invalid values.
    """
    if not isinstance(data, dict):
        raise ValueError("state data must be a dict")

    # Reject forbidden fields FIRST (before extraction)
    if _has_forbidden_fields(data):
        raise ValueError(
            "state data contains forbidden fields "
            "(receipt, payment, fiscal, customer, PII, DB, secrets)"
        )

    # Extract only safe fields
    safe = _extract_safe_fields(data)

    # Construct — __post_init__ validates state, timestamps, etc.
    return PlayerStateSnapshot(**safe)


def _utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string (for test injection)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ══════════════════════════════════════════════════════════════════════
# Safe file reader
# ══════════════════════════════════════════════════════════════════════


def read_state_snapshot(
    path: Optional[str] = DEFAULT_STATE_PATH,
) -> PlayerStateSnapshot:
    """Read a state JSON file and return a validated PlayerStateSnapshot.

    Safety rules (fail-safe):
        - File does not exist → UNKNOWN (hide)
        - File is not a regular file → UNKNOWN (hide)
        - Broken JSON → UNKNOWN (hide)
        - Permission error → UNKNOWN (hide)
        - Any OSError/IOError → UNKNOWN (hide)
        - Forbidden fields present → UNKNOWN (hide)
        - Valid data, stale timestamp → STALE (hide)
        - Valid data, idle → IDLE (may show)

    NO network, NO DB, NO subprocess, NO Chromium, NO UKM5.

    Args:
        path: Filesystem path to the state JSON file.
              Default: /run/verny/kso/state.json

    Returns:
        PlayerStateSnapshot (always valid, always safe)
    """
    if path is None or not isinstance(path, str) or path.strip() == "":
        return _UNKNOWN_SNAPSHOT

    # ── Check file existence ────────────────────────────────────
    try:
        if not os.path.exists(path):
            return _UNKNOWN_SNAPSHOT
        if not os.path.isfile(path):
            return _UNKNOWN_SNAPSHOT
    except (PermissionError, OSError, IOError):
        return _UNKNOWN_SNAPSHOT

    # ── Read file ───────────────────────────────────────────────
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except (PermissionError, OSError, IOError, UnicodeDecodeError):
        return _UNKNOWN_SNAPSHOT

    # ── Parse JSON ──────────────────────────────────────────────
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return _UNKNOWN_SNAPSHOT

    if not isinstance(data, dict):
        return _UNKNOWN_SNAPSHOT

    # ── Reject forbidden fields ─────────────────────────────────
    if _has_forbidden_fields(data):
        return _UNKNOWN_SNAPSHOT

    # ── Build snapshot ──────────────────────────────────────────
    try:
        return from_dict(data)
    except (ValueError, TypeError):
        return _UNKNOWN_SNAPSHOT


# ══════════════════════════════════════════════════════════════════════
# Visibility resolution
# ══════════════════════════════════════════════════════════════════════


def resolve_visibility(
    snapshot: PlayerStateSnapshot,
    kill_switch_active: bool,
) -> str:
    """Determine whether the player should be visible or hidden.

    Priority (highest first):
        1. kill_switch_active → HIDDEN
        2. state != idle → HIDDEN (includes stale, unknown, all others)
        3. idle + kill_switch inactive → VISIBLE

    Pure function — no side effects, no I/O.

    Args:
        snapshot: Immutable state snapshot.
        kill_switch_active: Current kill-switch status.

    Returns:
        'visible' or 'hidden'
    """
    # Guard 1: kill-switch overrides everything
    if kill_switch_active:
        return "hidden"

    # Guard 2: only idle allows display
    if not snapshot.allows_display:
        return "hidden"

    # All guards passed → visible
    return "visible"
