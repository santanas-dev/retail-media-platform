"""X11 Click-through Renderer Contract — production fullscreen idle screensaver.

Pure contract module — no X11 runtime dependency. All X11 calls go through an
adapter interface so unit tests run without an X server.

Design: docs/audit/x11-click-through-renderer-contract.md
Prerequisite: 38.1.5 — X11 Input Pass-through Design
Profile: portrait_fullscreen_idle_screensaver_768
"""

from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════
# Renderer identity
# ══════════════════════════════════════════════════════════════════════

RENDERER_TYPE = "x11_click_through"
RENDERER_NAME = "X11 Click-through Renderer (768×1024)"
RENDERER_VERSION = "0.1.0"

# ══════════════════════════════════════════════════════════════════════
# Geometry
# ══════════════════════════════════════════════════════════════════════

ROOT_WIDTH = 768
ROOT_HEIGHT = 1024
WINDOW_X = 0
WINDOW_Y = 0
WINDOW_WIDTH = 768
WINDOW_HEIGHT = 1024

# ══════════════════════════════════════════════════════════════════════
# X11 window properties — MANDATORY for production
# ══════════════════════════════════════════════════════════════════════

OVERRIDE_REDIRECT = True       # Bypass WM — required for click-through
ALWAYS_ON_TOP = True           # _NET_WM_STATE_ABOVE — stay above UKM5
INPUT_REGION_EMPTY = True      # XFixes empty input shape — pointer passthrough
NO_FOCUS_STEAL = True          # Never take keyboard focus
NO_KEYBOARD_GRAB = True        # Never grab keyboard
NO_POINTER_GRAB = True         # Never grab pointer

# ══════════════════════════════════════════════════════════════════════
# Hide SLA
# ══════════════════════════════════════════════════════════════════════

HIDE_SLA_MS = 500
TARGET_HIDE_MS = 200

# ══════════════════════════════════════════════════════════════════════
# Safety flags
# ══════════════════════════════════════════════════════════════════════

KILL_SWITCH_REQUIRED = True
STATE_ONLY_VISIBILITY_REQUIRED = True
NO_CHROMIUM = True             # This renderer does NOT use Chromium
NO_UKM5_DB = True
NO_BACKEND_URL = True          # No backend URL in renderer config
NO_SECRETS = True              # No tokens/secrets in renderer config

# ══════════════════════════════════════════════════════════════════════
# Forbidden fields in any renderer output/config
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_FIELDS = frozenset({
    "receipt_id", "transaction_id", "payment_amount", "payment_method",
    "fiscal_data", "customer_name", "customer_id", "customer_phone",
    "customer_email", "card_number", "pan", "items", "total_amount",
    "cashier_id", "cashier_name", "receipt_number",
    "backend_url", "backend_host", "backend_port",
    "token", "secret", "api_key", "password", "access_token",
    "refresh_token", "bearer", "jwt",
    "event_key", "event_code", "event_keycode", "event_data",
    "event_value", "input_value", "scanner_value", "barcode", "key_value",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class X11ClickThroughCapabilities:
    """What this renderer can do — static capability declaration."""

    renderer_type: str = RENDERER_TYPE
    version: str = RENDERER_VERSION

    # Geometry
    root_width: int = ROOT_WIDTH
    root_height: int = ROOT_HEIGHT
    window_x: int = WINDOW_X
    window_y: int = WINDOW_Y
    window_width: int = WINDOW_WIDTH
    window_height: int = WINDOW_HEIGHT

    # X11 properties
    override_redirect: bool = OVERRIDE_REDIRECT
    always_on_top: bool = ALWAYS_ON_TOP
    input_region_empty: bool = INPUT_REGION_EMPTY
    no_focus_steal: bool = NO_FOCUS_STEAL
    no_keyboard_grab: bool = NO_KEYBOARD_GRAB
    no_pointer_grab: bool = NO_POINTER_GRAB

    # SLA
    hide_sla_ms: int = HIDE_SLA_MS
    target_hide_ms: int = TARGET_HIDE_MS

    # Safety
    kill_switch_required: bool = KILL_SWITCH_REQUIRED
    state_only_visibility_required: bool = STATE_ONLY_VISIBILITY_REQUIRED
    no_chromium: bool = NO_CHROMIUM
    no_ukm5_db: bool = NO_UKM5_DB

    # Input loss assessment
    scanner_loss_free: bool = True   # No scanner input loss
    touch_loss_free: bool = True     # No touch input loss
    keyboard_loss_free: bool = True  # No keyboard input loss

    def is_production_ready(self) -> bool:
        """Production-ready if all pass-through properties are enabled."""
        return (
            self.input_region_empty
            and self.no_keyboard_grab
            and self.no_pointer_grab
            and self.no_focus_steal
            and self.override_redirect
            and self.scanner_loss_free
            and self.touch_loss_free
        )


@dataclass(frozen=True)
class X11RendererPlan:
    """A concrete renderer plan — validated, immutable, safe for logging."""

    capabilities: X11ClickThroughCapabilities = field(
        default_factory=X11ClickThroughCapabilities
    )
    display: str = ":0"

    # Whether this plan has been validated
    validated: bool = False
    validation_errors: tuple = ()

    def __post_init__(self):
        if not self.display:
            raise ValueError("display must be specified (e.g. ':0')")

    def to_safe_dict(self) -> dict:
        """Return a dict safe for logging — no secrets, no forbidden fields."""
        c = self.capabilities
        return {
            "renderer_type": c.renderer_type,
            "version": c.version,
            "geometry": f"{c.root_width}x{c.root_height}",
            "window": f"({c.window_x},{c.window_y}) {c.window_width}x{c.window_height}",
            "override_redirect": c.override_redirect,
            "always_on_top": c.always_on_top,
            "input_region_empty": c.input_region_empty,
            "no_focus_steal": c.no_focus_steal,
            "no_keyboard_grab": c.no_keyboard_grab,
            "no_pointer_grab": c.no_pointer_grab,
            "hide_sla_ms": c.hide_sla_ms,
            "target_hide_ms": c.target_hide_ms,
            "kill_switch_required": c.kill_switch_required,
            "production_ready": c.is_production_ready(),
            "scanner_loss_free": c.scanner_loss_free,
            "touch_loss_free": c.touch_loss_free,
            "display": self.display,
            "validated": self.validated,
        }


@dataclass(frozen=True)
class X11RendererValidationResult:
    """Result of validating a renderer plan."""

    valid: bool
    production_ready: bool
    errors: tuple = ()
    warnings: tuple = ()

    def __bool__(self) -> bool:
        return self.valid


# ══════════════════════════════════════════════════════════════════════
# Validation — pure functions
# ══════════════════════════════════════════════════════════════════════

def validate_renderer_plan(plan: X11RendererPlan) -> X11RendererValidationResult:
    """Validate a renderer plan against the production contract.

    A valid production renderer MUST:
        - Have empty input region
        - NOT grab keyboard
        - NOT grab pointer
        - NOT steal focus
        - Use override-redirect
        - Have correct geometry (768×1024)
        - Have display set
        - Have no forbidden fields in output
    """
    errors = []
    warnings = []
    c = plan.capabilities

    # Mandatory geometry
    if c.root_width != 768 or c.root_height != 1024:
        errors.append(f"geometry must be 768×1024, got {c.root_width}×{c.root_height}")
    if c.window_x != 0 or c.window_y != 0:
        errors.append(f"window origin must be (0,0), got ({c.window_x},{c.window_y})")
    if c.window_width != 768 or c.window_height != 1024:
        errors.append(f"window size must be 768×1024, got {c.window_width}×{c.window_height}")

    # Input pass-through — all three required for production
    if not c.input_region_empty:
        errors.append("input_region must be empty for pass-through")
    if not c.no_keyboard_grab:
        errors.append("keyboard grab must be disabled")
    if not c.no_pointer_grab:
        errors.append("pointer grab must be disabled")
    if not c.no_focus_steal:
        errors.append("focus stealing must be disabled")

    # Window management
    if not c.override_redirect:
        errors.append("override_redirect must be True for click-through")

    # Display
    if not plan.display:
        errors.append("display must be set (e.g. ':0')")

    # Safety
    if not c.kill_switch_required:
        errors.append("kill_switch must be required")
    if not c.no_chromium:
        errors.append("renderer must NOT use Chromium")
    if not c.no_ukm5_db:
        errors.append("renderer must NOT access UKM5 DB")

    # Hide SLA
    if c.hide_sla_ms > 500:
        errors.append(f"hide_sla_ms must be <= 500, got {c.hide_sla_ms}")
    if c.target_hide_ms > 200:
        warnings.append(f"target_hide_ms > 200 ({c.target_hide_ms}), should be <= 200")

    # Production readiness
    production_ready = (
        c.is_production_ready()
        and len(errors) == 0
    )

    return X11RendererValidationResult(
        valid=len(errors) == 0,
        production_ready=production_ready,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def validate_safe_output(data: dict) -> X11RendererValidationResult:
    """Validate that a renderer output dict contains no forbidden fields."""
    errors = []

    if not isinstance(data, dict):
        return X11RendererValidationResult(
            valid=False, production_ready=False,
            errors=("data must be a dict",)
        )

    for key in data:
        key_lower = key.lower()
        if key_lower in FORBIDDEN_FIELDS:
            errors.append(f"forbidden field in output: {key}")
        for forbidden in [
            "receipt", "payment", "fiscal", "customer",
            "card", "pan", "phone", "email",
            "backend_url", "backend", "token", "secret",
            "api_key", "password", "jwt", "bearer",
            "event_key", "event_code", "scanner_value", "barcode",
        ]:
            if forbidden in key_lower:
                if key not in errors:
                    errors.append(f"forbidden-like field in output: {key}")
                break

    return X11RendererValidationResult(
        valid=len(errors) == 0,
        production_ready=len(errors) == 0,
        errors=tuple(errors),
    )


# ══════════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════════

def create_default_renderer_plan(display: str = ":0") -> X11RendererPlan:
    """Create a default X11 click-through renderer plan.

    The default plan is production-ready (all pass-through properties enabled).
    """
    return X11RendererPlan(
        capabilities=X11ClickThroughCapabilities(),
        display=display,
    )


def create_wake_only_renderer_plan(display: str = ":0") -> X11RendererPlan:
    """Create a NON-production wake-only plan (input capture enabled).

    This plan captures input — NOT production-ready. Exists for comparison.
    """
    caps = X11ClickThroughCapabilities(
        input_region_empty=False,
        no_keyboard_grab=False,
        no_pointer_grab=False,
        no_focus_steal=False,
        override_redirect=False,
        scanner_loss_free=False,
        touch_loss_free=False,
        keyboard_loss_free=False,
    )
    return X11RendererPlan(capabilities=caps, display=display)
