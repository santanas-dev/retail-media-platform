"""Interaction hide rules for fullscreen idle screensaver profiles.

Pure functions — no side effects, no I/O, no network, no Chromium, no X11.

Design: docs/audit/fullscreen-idle-screensaver-interaction-design.md
"""

from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class HideDecision:
    """Immutable decision: should the screensaver be hidden right now?"""
    hide: bool
    reason: str          # "kill_switch" | "state_change" | "keydown" | "touchstart" | ...
    target_ms: int       # hide target milliseconds
    passthrough: bool    # True if input should be forwarded to UKM5
    scanner_risk: bool   # True if a scanner (keyboard wedge) may have lost input
    input_mode: str = "wake_only"  # Current profile input mode

    def __post_init__(self):
        """Validate hide decision fields."""
        valid_reasons = frozenset({
            "kill_switch", "state_change", "keydown", "input",
            "touchstart", "pointerdown", "mousedown", "click", "wheel",
            "none",  # "none" when hide=False
        })
        valid_modes = frozenset({
            "wake_only", "focus_return", "x11_click_through", "state_only",
        })
        if self.reason not in valid_reasons:
            raise ValueError(f"invalid hide reason: {self.reason}")
        if self.target_ms < 0:
            raise ValueError(f"target_ms must be >= 0, got {self.target_ms}")
        if self.input_mode not in valid_modes:
            raise ValueError(f"invalid input_mode: {self.input_mode}")


# ══════════════════════════════════════════════════════════════════════
# Trigger metadata (derived from profile constants)
# ══════════════════════════════════════════════════════════════════════

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

SCANNER_TRIGGERS = frozenset({"keydown", "input"})

# Valid DOM event names for hide triggers
VALID_DOM_EVENTS = frozenset({
    "touchstart", "pointerdown", "mousedown", "click",
    "keydown", "input", "wheel",
})

# States that force hide (anything except idle)
HIDE_STATES = frozenset({
    "busy", "scan", "cart", "payment", "error",
    "offline", "unknown", "stale",
})


# ══════════════════════════════════════════════════════════════════════
# Pure functions
# ══════════════════════════════════════════════════════════════════════

def resolve_highest_priority_trigger(events: frozenset) -> str | None:
    """Given a set of DOM event names, return the highest-priority trigger.

    Returns None if no valid hide trigger is present.
    """
    best_trigger = None
    best_priority = 999

    for event in events:
        event_str = str(event).strip().lower()
        if event_str in HIDE_TRIGGER_PRIORITY:
            priority = HIDE_TRIGGER_PRIORITY[event_str]
            if priority < best_priority:
                best_priority = priority
                best_trigger = event_str

    return best_trigger


def should_hide(
    dom_events: frozenset | None = None,
    state: str = "unknown",
    kill_switch_active: bool = False,
    input_mode: str = "wake_only",
) -> HideDecision:
    """Determine if the screensaver should hide.

    Priority (highest first):
        1. kill_switch_active
        2. state != "idle"
        3. dom_events (keydown/input > touch/pointer > click > wheel)

    Args:
        dom_events: Set of active DOM event names (e.g. {"touchstart", "keydown"}).
                    Empty/None means no events.
        state: Current UKM5 state ("idle", "busy", "payment", etc.)
        kill_switch_active: Whether kill-switch file exists.
        input_mode: Profile input mode ("wake_only", "state_only", etc.)

    Returns:
        HideDecision with hide=True/False and the triggering reason.
    """
    if dom_events is None:
        dom_events = frozenset()

    # 1. Kill-switch always wins
    if kill_switch_active:
        return HideDecision(
            hide=True,
            reason="kill_switch",
            target_ms=HIDE_TARGET_MS["kill_switch"],
            passthrough=HIDE_TRIGGER_PASSTHROUGH["kill_switch"],
            scanner_risk=False,
            input_mode=input_mode,
        )

    # 2. State-based hide (not idle → hide)
    state_str = str(state).strip().lower()
    if state_str != "idle":
        return HideDecision(
            hide=True,
            reason="state_change",
            target_ms=HIDE_TARGET_MS["state_change"],
            passthrough=HIDE_TRIGGER_PASSTHROUGH["state_change"],
            scanner_risk=False,
            input_mode=input_mode,
        )

    # 3. DOM event-based hide
    trigger = resolve_highest_priority_trigger(dom_events)
    if trigger is not None:
        is_scanner = trigger in SCANNER_TRIGGERS
        return HideDecision(
            hide=True,
            reason=trigger,
            target_ms=HIDE_TARGET_MS[trigger],
            passthrough=HIDE_TRIGGER_PASSTHROUGH[trigger],
            scanner_risk=is_scanner,
            input_mode=input_mode,
        )

    # No reason to hide
    return HideDecision(
        hide=False,
        reason="none",
        target_ms=0,
        passthrough=False,
        scanner_risk=False,
        input_mode=input_mode,
    )


def input_loss_risk(input_mode: str, trigger: str) -> bool:
    """Check if there's a risk of losing the first input with this mode + trigger.

    Returns True if the first input (scan/touch) may be lost.

    Args:
        input_mode: Profile input mode
        trigger: The hide trigger that fired
    """
    # x11_click_through: no loss (input passes through)
    if input_mode == "x11_click_through":
        return False

    # state_only: scanner safe (state observer catches it), touch may be lost
    if input_mode == "state_only":
        return trigger in {"touchstart", "pointerdown", "mousedown", "click", "wheel"}

    # wake_only / focus_return: loses everything
    return True


def validate_interaction_log(log_entry: dict) -> dict:
    """Validate an interaction log entry for forbidden fields.

    Returns:
        {"valid": bool, "errors": [str]}
    """
    errors = []

    if not isinstance(log_entry, dict):
        return {"valid": False, "errors": ["log_entry must be a dict"]}

    # Check for forbidden fields (scanner values, PII, secrets)
    forbidden_patterns = [
        "event_key", "event_code", "event_keycode",
        "event_data", "event_value", "input_value",
        "scanner_value", "barcode", "key_value",
        "receipt", "payment", "fiscal", "customer",
        "card", "pan", "phone", "email",
        "url", "token", "secret", "password",
        "backend", "api_key",
    ]

    for key in log_entry:
        key_lower = key.lower()
        for pattern in forbidden_patterns:
            if pattern in key_lower:
                errors.append(f"forbidden log field: {key}")
                break

    # All keys in log_entry must be in safe log fields
    for key in log_entry:
        if key not in frozenset({
            "input_event_detected",
            "hide_trigger",
            "hide_target_ms",
            "hide_actual_ms",
            "scanner_risk",
            "passthrough_attempted",
            "timestamp",
        }):
            # Allow timestamp with a broader match
            if "timestamp" in key.lower():
                continue
            if key not in errors:  # don't duplicate forbidden errors
                errors.append(f"unexpected log field: {key}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }
