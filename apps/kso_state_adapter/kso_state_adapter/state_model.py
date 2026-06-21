"""KSO UKM 4 State Adapter — state model.

Safe state definitions for kso_state.json.
Player reads this file (read-only) to decide play/hold.
Adapter is the ONLY writer.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# Allowed states
# ══════════════════════════════════════════════════════════════════════

STATE_IDLE = "idle"
STATE_TRANSACTION = "transaction"
STATE_PAYMENT = "payment"
STATE_RECEIPT = "receipt"
STATE_SERVICE = "service"
STATE_ERROR = "error"
STATE_MAINTENANCE = "maintenance"
STATE_OFFLINE = "offline"
STATE_UNKNOWN = "unknown"

ALLOWED_STATES = frozenset({
    STATE_IDLE,
    STATE_TRANSACTION,
    STATE_PAYMENT,
    STATE_RECEIPT,
    STATE_SERVICE,
    STATE_ERROR,
    STATE_MAINTENANCE,
    STATE_OFFLINE,
    STATE_UNKNOWN,
})

# ══════════════════════════════════════════════════════════════════════
# Forbidden keys — MUST NOT appear in state JSON
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_STATE_KEYS = frozenset({
    "receipt_number", "receipt_data", "fiscal_data",
    "card_number", "pan", "payment_card",
    "customer_id", "customer_name", "phone", "email",
    "cashier", "cashier_id",
    "amount", "total", "sum", "price",
    "sku", "item", "items", "product",
    "raw_ukm", "raw_json", "raw_data",
    "token", "secret", "password", "api_key",
    "authorization", "bearer",
    "backend_url", "backend_base_url", "device_code",
    "file_path", "local_path", "stacktrace",
})

FORBIDDEN_IN_STATE_VALUES = frozenset({
    "token", "secret", "password", "card_number", "pan",
    "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "stacktrace",
})


# ══════════════════════════════════════════════════════════════════════
# Model
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoState:
    """Safe KSO terminal state.

    Never contains: receipt data, payment data, customer data,
    cashier data, raw UKM data, paths, secrets, stacktrace.
    """

    state: str = STATE_UNKNOWN
    updated_at_utc: str = ""
    source: str = "ukm4_state_adapter"
    schema_version: int = 1

    def __post_init__(self):
        if self.state not in ALLOWED_STATES:
            raise ValueError(
                f"Invalid state '{self.state}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_STATES))}"
            )
        if not self.updated_at_utc:
            self.updated_at_utc = datetime.now(timezone.utc).isoformat()

    def validate_forbidden(self) -> Optional[str]:
        """Check for forbidden data. Returns error string or None."""
        # Check state value itself
        lower = self.state.lower()
        for fb in FORBIDDEN_IN_STATE_VALUES:
            if fb in lower:
                return f"State value contains forbidden '{fb}'"
        lower_source = self.source.lower()
        for fb in FORBIDDEN_IN_STATE_VALUES:
            if fb in lower_source:
                return f"Source contains forbidden '{fb}'"
        return None

    def to_dict(self) -> dict:
        """Serialize to dict for JSON. Strips internal-only fields."""
        return {
            "state": self.state,
            "updated_at_utc": self.updated_at_utc,
            "source": self.source,
            "schema_version": self.schema_version,
        }

    def __repr__(self) -> str:
        return (
            f"KsoState(state={self.state!r}, "
            f"source={self.source!r})"
        )


def validate_state_dict(data: dict) -> Optional[str]:
    """Validate a state dict has no forbidden keys/values. Returns error or None."""
    if not isinstance(data, dict):
        return "State data must be a dict"

    for key in data:
        if key in FORBIDDEN_STATE_KEYS:
            return f"Forbidden key '{key}' in state data"
        value = data[key]
        if isinstance(value, str):
            lower = value.lower()
            for fb in FORBIDDEN_IN_STATE_VALUES:
                if fb in lower:
                    return f"Forbidden value for '{key}' contains '{fb}'"

    return None
