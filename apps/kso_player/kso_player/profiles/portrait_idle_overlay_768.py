"""Portrait Idle Overlay 768 — v1 player profile for UKM5 fleet.

Target: 768×1024 portrait screens with UKM5 fullscreen Chromium kiosk.
Overlay zone: product grid area (y=400-640, 768×240).
Creative canvas: 768×200 centered inside overlay.

Safety:
    - Idle-only display (hides on busy/payment/scan/cart/error/unknown/stale)
    - Hide SLA: < 500 ms
    - Never overlays payment button (y=720-840)
    - Never overlays header (y=0-60) or close button
    - No fullscreen
    - No UKM5 DB access
    - No receipt/payment/fiscal/customer data in state contract
"""

from kso_player.profiles import PlayerProfile, register_profile

# ══════════════════════════════════════════════════════════════════════
# Profile constants
# ══════════════════════════════════════════════════════════════════════

PROFILE_CODE = "portrait_idle_overlay_768"
PROFILE_NAME = "Portrait Idle Overlay (768×1024)"

# ── Geometry ────────────────────────────────────────────────────────
ROOT_WIDTH = 768
ROOT_HEIGHT = 1024

OVERLAY_X = 0
OVERLAY_Y = 400
OVERLAY_WIDTH = 768
OVERLAY_HEIGHT = 240

CREATIVE_X = 0
CREATIVE_Y = 420
CREATIVE_WIDTH = 768
CREATIVE_HEIGHT = 200

# ── State rules ─────────────────────────────────────────────────────
# Only these states permit ad display
SHOW_ON_STATES = frozenset({
    "idle",
})

# These states force immediate hide
HIDE_ON_STATES = frozenset({
    "busy",
    "scan",
    "cart",
    "payment",
    "error",
    "offline",
    "unknown",
    "stale",
})

# ── Safety ──────────────────────────────────────────────────────────
IDLE_ONLY = True
NO_FULLSCREEN = True
NO_UKM5_DB = True
HIDE_SLA_MS = 500

# ── Forbidden zones (UKM5 critical UI elements) ─────────────────────
# Format: (x, y, width, height)
PAYMENT_ZONE = (487, 720, 92, 120)   # Blue payment button
HEADER_ZONE = (0, 0, 768, 60)         # Dark header bar
CLOSE_BTN_ZONE = (725, 4, 6, 20)      # Red close button

FORBIDDEN_ZONES = frozenset({
    PAYMENT_ZONE,
    HEADER_ZONE,
    CLOSE_BTN_ZONE,
})

# ── Gap constants (for validation) ──────────────────────────────────
GAP_TO_PAYMENT_MIN = 80  # Minimum px between overlay bottom and payment top
GAP_TO_HEADER_MIN = 0    # Overlay starts after header (y=400 > 60)

# ── State contract ──────────────────────────────────────────────────
# Valid states that can appear in kso_state.json for this profile
VALID_STATES = frozenset({
    "idle",
    "busy",
    "scan",
    "cart",
    "payment",
    "error",
    "offline",
    "unknown",
    "stale",
})

# Fields FORBIDDEN in kso_state.json for this profile
FORBIDDEN_STATE_FIELDS = frozenset({
    "receipt_id",
    "transaction_id",
    "payment_amount",
    "payment_method",
    "fiscal_data",
    "customer_name",
    "customer_id",
    "customer_phone",
    "customer_email",
    "card_number",
    "pan",
    "items",
    "total_amount",
    "cashier_id",
    "cashier_name",
    "receipt_number",
})

# Required fields in kso_state.json
REQUIRED_STATE_FIELDS = frozenset({
    "schema_version",
    "device_code",
    "state",
    "source",
    "updated_at_utc",
})

# ══════════════════════════════════════════════════════════════════════
# Profile instance
# ══════════════════════════════════════════════════════════════════════

portrait_idle_overlay_768 = PlayerProfile(
    code=PROFILE_CODE,
    name=PROFILE_NAME,
    root_width=ROOT_WIDTH,
    root_height=ROOT_HEIGHT,
    overlay_x=OVERLAY_X,
    overlay_y=OVERLAY_Y,
    overlay_width=OVERLAY_WIDTH,
    overlay_height=OVERLAY_HEIGHT,
    creative_x=CREATIVE_X,
    creative_y=CREATIVE_Y,
    creative_width=CREATIVE_WIDTH,
    creative_height=CREATIVE_HEIGHT,
    show_on_states=SHOW_ON_STATES,
    hide_on_states=HIDE_ON_STATES,
    idle_only=IDLE_ONLY,
    no_fullscreen=NO_FULLSCREEN,
    no_ukm5_db=NO_UKM5_DB,
    hide_sla_ms=HIDE_SLA_MS,
    forbidden_zones=FORBIDDEN_ZONES,
)

# ══════════════════════════════════════════════════════════════════════
# Register profile
# ══════════════════════════════════════════════════════════════════════

register_profile(portrait_idle_overlay_768)


# ══════════════════════════════════════════════════════════════════════
# Validation helpers (pure functions, no side effects)
# ══════════════════════════════════════════════════════════════════════

def validate_state_contract(data: dict) -> dict:
    """Validate a state JSON against this profile's contract.

    Returns:
        {"valid": bool, "errors": [str], "warnings": [str]}
    """
    errors = []
    warnings = []

    if not isinstance(data, dict):
        return {"valid": False, "errors": ["state data must be a dict"], "warnings": []}

    # Check required fields
    for field in REQUIRED_STATE_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    # Check forbidden fields
    for field in FORBIDDEN_STATE_FIELDS:
        if field in data:
            errors.append(f"forbidden field present: {field}")

    # Validate schema_version
    if "schema_version" in data and data["schema_version"] != 1:
        errors.append(
            f"unsupported schema_version: {data['schema_version']}"
        )

    # Validate state
    if "state" in data:
        state = str(data["state"]).strip().lower()
        if state not in VALID_STATES:
            errors.append(f"invalid state: {state}")
    else:
        errors.append("missing state field")

    # Check for fields that smell like receipt/payment/fiscal data
    for key in data:
        key_lower = key.lower()
        for forbidden in ["receipt", "payment", "fiscal", "customer",
                          "card", "pan", "phone", "email", "total",
                          "cashier", "transaction"]:
            if forbidden in key_lower:
                errors.append(f"forbidden-like field: {key}")
                break

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
