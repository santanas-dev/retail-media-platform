"""Fullscreen Idle Screensaver 768 — fullscreen screensaver profile for UKM5 fleet.

Target: 768×1024 portrait screens with UKM5 fullscreen Chromium kiosk.
Fullscreen idle-only screensaver — hides on ANY touch/scanner input.
NOT the Zone C overlay — this is a separate fullscreen mode.

Safety:
    - Idle-only display (hides on busy/payment/scan/cart/error/unknown/stale)
    - Hides on touch/pointer/mouse/click/keydown/input/wheel
    - Hide SLA: <= 500 ms, target <= 200 ms
    - Scanner keyboard wedge: hide immediately, value NOT logged
    - Kill-switch overrides everything
    - No UKM5 DB access
    - No receipt/payment/fiscal/customer data in state contract
    - No scanner value saved/logged
    - No key events saved/logged
    - No backend URL/token/secrets
"""

from kso_player.profiles import PlayerProfile, register_profile

# ══════════════════════════════════════════════════════════════════════
# Profile constants
# ══════════════════════════════════════════════════════════════════════

PROFILE_CODE = "portrait_fullscreen_idle_screensaver_768"
PROFILE_NAME = "Portrait Fullscreen Idle Screensaver (768×1024)"

# ── Geometry ────────────────────────────────────────────────────────
ROOT_WIDTH = 768
ROOT_HEIGHT = 1024

WINDOW_X = 0
WINDOW_Y = 0
WINDOW_WIDTH = 768
WINDOW_HEIGHT = 1024

# Fullscreen: creative canvas = entire screen
CREATIVE_X = 0
CREATIVE_Y = 0
CREATIVE_WIDTH = 768
CREATIVE_HEIGHT = 1024

# ── State rules ─────────────────────────────────────────────────────
# Only idle state permits screensaver display
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

# ── Interaction hide triggers ─────────────────────────────────────
# DOM events that trigger immediate hide
DOM_HIDE_TRIGGERS = frozenset({
    "touchstart",
    "pointerdown",
    "mousedown",
    "click",
    "keydown",
    "input",
    "wheel",
})

# Priority-ordered hide triggers (0 = highest priority)
HIDE_TRIGGER_PRIORITY = {
    "kill_switch": 0,
    "state_change": 1,
    "keydown": 2,
    "input": 2,
    "touchstart": 3,
    "pointerdown": 3,
    "mousedown": 3,
    "click": 4,
    "wheel": 5,
}

# Hide SLA targets per trigger (ms)
HIDE_TARGET_MS = {
    "kill_switch": 200,
    "state_change": 500,
    "keydown": 200,
    "input": 200,
    "touchstart": 200,
    "pointerdown": 200,
    "mousedown": 200,
    "click": 200,
    "wheel": 300,
}

# Passthrough intent per trigger (True = input should reach UKM5 after hide)
# NOTE: "keydown"/"input" marked False because Chromium overlay CANNOT pass through
# keyboard input. This is a known blocker (B-FS-2).
HIDE_TRIGGER_PASSTHROUGH = {
    "kill_switch": False,
    "state_change": True,
    "keydown": False,
    "input": False,
    "touchstart": True,
    "pointerdown": True,
    "mousedown": True,
    "click": True,
    "wheel": True,
}

# Scanner-related triggers (keyboard wedge)
SCANNER_TRIGGERS = frozenset({"keydown", "input"})

# ── Input mode ───────────────────────────────────────────────────────
# How this profile handles input pass-through.
# Valid values:
#   "wake_only"          — A: test only, loses first scan, NOT production-ready
#   "focus_return"       — B: deprecated, loses first scan, NOT recommended
#   "x11_click_through"  — D: X11 override-redirect + XFixes, production target
#   "state_only"         — E: state-based hide, pilot-ready
INPUT_MODE = "wake_only"  # Default: NOT production-ready (blocked by B-FS-1, B-FS-2)

PRODUCTION_READY_MODES = frozenset({
    "x11_click_through",
})

PILOT_READY_MODES = frozenset({
    "state_only",
    "x11_click_through",
})

TEST_ONLY_MODES = frozenset({
    "wake_only",
    "focus_return",
})

def is_production_ready(mode: str | None = None) -> bool:
    """Check if the given input mode is safe for production use."""
    if mode is None:
        mode = INPUT_MODE
    return mode in PRODUCTION_READY_MODES

def is_pilot_ready(mode: str | None = None) -> bool:
    """Check if the given input mode is acceptable for pilot rollout."""
    if mode is None:
        mode = INPUT_MODE
    return mode in PILOT_READY_MODES

def is_test_only(mode: str | None = None) -> bool:
    """Check if the given input mode is for testing only."""
    if mode is None:
        mode = INPUT_MODE
    return mode in TEST_ONLY_MODES

# ── Safety ──────────────────────────────────────────────────────────
IDLE_ONLY = True
NO_FULLSCREEN = False  # This IS a fullscreen profile
NO_UKM5_DB = True
HIDE_SLA_MS = 500

# ── Forbidden zones ────────────────────────────────────────────────
# Fullscreen screensaver covers everything — NO forbidden zones needed
# (it's an idle screensaver; UKM5 is not visible underneath)
FORBIDDEN_ZONES = frozenset()

# ── State contract ──────────────────────────────────────────────────
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

# Fields FORBIDDEN in state contract
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

REQUIRED_STATE_FIELDS = frozenset({
    "schema_version",
    "device_code",
    "state",
    "source",
    "updated_at_utc",
})

# ── Scanner safety ─────────────────────────────────────────────────
# Fields that MUST NOT appear in logs when scanner event is detected
FORBIDDEN_LOG_FIELDS = frozenset({
    "event_key",
    "event_code",
    "event_keycode",
    "event_data",
    "event_value",
    "input_value",
    "scanner_value",
    "barcode",
    "key_value",
})

# ── Interaction log fields (safe-only) ──────────────────────────────
SAFE_LOG_FIELDS = frozenset({
    "input_event_detected",
    "hide_trigger",
    "hide_target_ms",
    "hide_actual_ms",
    "scanner_risk",
    "passthrough_attempted",
})

# ══════════════════════════════════════════════════════════════════════
# Profile instance
# ══════════════════════════════════════════════════════════════════════

portrait_fullscreen_idle_screensaver_768 = PlayerProfile(
    code=PROFILE_CODE,
    name=PROFILE_NAME,
    root_width=ROOT_WIDTH,
    root_height=ROOT_HEIGHT,
    overlay_x=WINDOW_X,
    overlay_y=WINDOW_Y,
    overlay_width=WINDOW_WIDTH,
    overlay_height=WINDOW_HEIGHT,
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

register_profile(portrait_fullscreen_idle_screensaver_768)


# ══════════════════════════════════════════════════════════════════════
# Validation helpers
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

    for field in REQUIRED_STATE_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    for field in FORBIDDEN_STATE_FIELDS:
        if field in data:
            errors.append(f"forbidden field present: {field}")

    if "schema_version" in data and data["schema_version"] != 1:
        errors.append(
            f"unsupported schema_version: {data['schema_version']}"
        )

    if "state" in data:
        state = str(data["state"]).strip().lower()
        if state not in VALID_STATES:
            errors.append(f"invalid state: {state}")
    else:
        errors.append("missing state field")

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
