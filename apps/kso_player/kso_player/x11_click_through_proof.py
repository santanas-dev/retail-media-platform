"""X11 Click-through Physical Proof Harness — runtime plan and safety validators.

Prepares a safe proof plan for testing X11 click-through fullscreen renderer
on a physical KSO. NO X11 runtime dependency — pure contract module.

Modes:
    --dry-run         Build plan, validate, print. NO X11 calls.
    --preflight-only  Check environment, print readiness. NO X11 calls.
    --run-once        Execute the proof. NOT EXECUTED in this step (38.1.7).

Design: docs/audit/x11-click-through-physical-proof-plan.md
Prerequisite: 38.1.6 — X11 Click-through Renderer Contract
"""

from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

PROOF_TITLE = "X11_CLICK_THROUGH_PROOF"
DISPLAY_DEFAULT = ":0"
GEOMETRY = (768, 1024)
WINDOW_ORIGIN = (0, 0)
DEFAULT_DURATION_SEC = 10
HARD_MAX_DURATION_SEC = 30
LOCKFILE_PATH = "/tmp/x11_click_through_proof.lock"

# ══════════════════════════════════════════════════════════════════════
# Forbidden in any plan/output/command
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_COMMANDS = frozenset({
    "pkill chromium", "pkill -f chromium", "killall chromium",
    "systemctl restart mint", "systemctl stop mint",
    "systemctl restart mysql", "systemctl stop mysql",
    "systemctl restart redis", "systemctl stop redis",
    "systemctl restart chromium", "systemctl stop chromium",
    "restart mint", "stop mint",
})

FORBIDDEN_FIELDS = frozenset({
    "receipt_id", "transaction_id", "payment_amount", "payment_method",
    "fiscal_data", "customer_name", "customer_id", "customer_phone",
    "customer_email", "card_number", "pan", "items", "total_amount",
    "cashier_id", "cashier_name", "receipt_number",
    "backend_url", "token", "secret", "api_key", "password",
    "event_key", "event_code", "event_keycode", "event_data",
    "event_value", "input_value", "scanner_value", "barcode", "key_value",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class X11ProofPlan:
    """Immutable proof plan — describes what WILL happen during physical run."""

    title: str = PROOF_TITLE
    display: str = DISPLAY_DEFAULT
    width: int = GEOMETRY[0]
    height: int = GEOMETRY[1]
    x: int = WINDOW_ORIGIN[0]
    y: int = WINDOW_ORIGIN[1]

    # X11 properties
    override_redirect: bool = True
    input_region_empty: bool = True
    no_keyboard_grab: bool = True
    no_pointer_grab: bool = True
    no_focus_steal: bool = True

    # Timing
    duration_sec: int = DEFAULT_DURATION_SEC

    # Safety
    lockfile: str = LOCKFILE_PATH
    kill_switch_required: bool = True
    rollback_targeted: bool = True

    # Mode
    mode: str = "dry_run"  # "dry_run" | "preflight_only" | "run_once"

    def __post_init__(self):
        if not self.display:
            raise ValueError("display must be set (e.g. ':0')")
        if not self.title:
            raise ValueError("title must be set")
        if self.duration_sec > HARD_MAX_DURATION_SEC:
            raise ValueError(
                f"duration must be <= {HARD_MAX_DURATION_SEC}s, got {self.duration_sec}s"
            )
        if self.duration_sec <= 0:
            raise ValueError(f"duration must be > 0, got {self.duration_sec}")
        valid_modes = frozenset({"dry_run", "preflight_only", "run_once"})
        if self.mode not in valid_modes:
            raise ValueError(f"invalid mode: {self.mode}")

    def is_production_ready(self) -> bool:
        """Production-ready only if all pass-through properties enabled."""
        return (
            self.override_redirect
            and self.input_region_empty
            and self.no_keyboard_grab
            and self.no_pointer_grab
            and self.no_focus_steal
        )

    def to_safe_dict(self) -> dict:
        """Return a dict safe for logging — no secrets, no forbidden fields."""
        return {
            "title": self.title,
            "display": self.display,
            "geometry": f"{self.width}x{self.height}",
            "origin": f"({self.x},{self.y})",
            "override_redirect": self.override_redirect,
            "input_region_empty": self.input_region_empty,
            "no_keyboard_grab": self.no_keyboard_grab,
            "no_pointer_grab": self.no_pointer_grab,
            "no_focus_steal": self.no_focus_steal,
            "duration_sec": self.duration_sec,
            "lockfile": self.lockfile,
            "kill_switch_required": self.kill_switch_required,
            "rollback_targeted": self.rollback_targeted,
            "mode": self.mode,
            "production_ready": self.is_production_ready(),
        }


@dataclass(frozen=True)
class X11ProofPreflight:
    """Preflight check result — environment readiness for physical run."""

    ready: bool
    errors: tuple = ()
    warnings: tuple = ()

    # Environment facts (safe — no secrets)
    display_available: bool = False
    xdotool_available: bool = False
    scrot_available: bool = False
    xwininfo_available: bool = False
    xprop_available: bool = False
    python3_xlib_available: bool = False

    def __bool__(self) -> bool:
        return self.ready


@dataclass(frozen=True)
class X11ProofEvidencePlan:
    """Describes what evidence WILL be collected during physical run.

    This is a PLAN — actual collection happens in run_once mode on KSO.
    """

    screenshots: bool = True         # scrot before/during/after
    window_tree: bool = True         # xwininfo -root -tree
    window_id: bool = True           # xdotool search
    window_props: bool = True        # xprop
    active_window: bool = True       # xdotool getactivewindow
    pixel_proof: bool = True         # pixel-level analysis of screenshots
    scanner_pass_through: bool = True  # evidence: scanner → UKM5 (fact only, no value)
    touch_pass_through: bool = True   # evidence: touch → UKM5 (fact only)

    def evidence_count(self) -> int:
        return sum([
            self.screenshots, self.window_tree, self.window_id,
            self.window_props, self.active_window, self.pixel_proof,
            self.scanner_pass_through, self.touch_pass_through,
        ])

    def to_safe_dict(self) -> dict:
        return {
            "screenshots": self.screenshots,
            "window_tree": self.window_tree,
            "window_id": self.window_id,
            "window_props": self.window_props,
            "active_window": self.active_window,
            "pixel_proof": self.pixel_proof,
            "scanner_pass_through": self.scanner_pass_through,
            "touch_pass_through": self.touch_pass_through,
            "evidence_count": self.evidence_count(),
        }


# ══════════════════════════════════════════════════════════════════════
# Validation — pure functions
# ══════════════════════════════════════════════════════════════════════

def validate_proof_plan(plan: X11ProofPlan) -> dict:
    """Validate a proof plan against safety rules.

    Returns:
        {"valid": bool, "errors": [str]}
    """
    errors = []

    # Geometry
    if plan.width != 768 or plan.height != 1024:
        errors.append(f"geometry must be 768×1024, got {plan.width}×{plan.height}")
    if plan.x != 0 or plan.y != 0:
        errors.append(f"origin must be (0,0), got ({plan.x},{plan.y})")

    # Display
    if not plan.display:
        errors.append("display must be set (e.g. ':0')")

    # X11 pass-through — all required
    if not plan.input_region_empty:
        errors.append("input_region must be empty for pass-through")
    if not plan.no_keyboard_grab:
        errors.append("keyboard grab must be disabled (scanner loss risk)")
    if not plan.no_pointer_grab:
        errors.append("pointer grab must be disabled (touch loss risk)")
    if not plan.no_focus_steal:
        errors.append("focus stealing must be disabled")
    if not plan.override_redirect:
        errors.append("override_redirect must be True for click-through")

    # Safety
    if plan.duration_sec > HARD_MAX_DURATION_SEC:
        errors.append(
            f"duration {plan.duration_sec}s exceeds hard max {HARD_MAX_DURATION_SEC}s"
        )
    if plan.duration_sec <= 0:
        errors.append("duration must be positive")
    if not plan.kill_switch_required:
        errors.append("kill_switch must be required")
    if not plan.rollback_targeted:
        errors.append("rollback must be targeted (only proof process)")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def validate_command_safety(command: str) -> dict:
    """Check if a shell command is safe to execute on KSO.

    Returns:
        {"safe": bool, "violations": [str]}
    """
    violations = []
    cmd_lower = command.lower()

    # Check forbidden commands
    for forbidden in FORBIDDEN_COMMANDS:
        if forbidden.lower() in cmd_lower:
            violations.append(f"forbidden command pattern: {forbidden}")

    # Check for systemd modifications
    systemd_patterns = [
        "systemctl enable", "systemctl disable",
        "systemctl mask", "systemctl unmask",
        "systemctl daemon-reload",
    ]
    for pattern in systemd_patterns:
        if pattern in cmd_lower:
            violations.append(f"forbidden systemd operation: {pattern}")

    # Check for file modifications to UKM5
    ukm5_files = [
        "openbox", ".profile", "xinitrc", "index.html",
        "autostart", "/etc/systemd/system/",
    ]
    for fname in ukm5_files:
        if fname in cmd_lower:
            violations.append(f"forbidden file modification: {fname}")

    # Check for redirection to UKM5 paths
    if ">" in command and any(
        p in cmd_lower for p in ["/home/ukm5", "/etc/", "/var/lib/mint"]
    ):
        violations.append("forbidden write to UKM5 paths")

    return {
        "safe": len(violations) == 0,
        "violations": violations,
    }


def validate_safe_output(data: dict) -> dict:
    """Validate that a proof output dict contains no forbidden fields."""
    errors = []

    if not isinstance(data, dict):
        return {"valid": False, "errors": ["data must be a dict"]}

    for key in data:
        key_lower = key.lower()
        if key_lower in FORBIDDEN_FIELDS:
            errors.append(f"forbidden field in output: {key}")
        for forbidden in [
            "receipt", "payment", "fiscal", "customer",
            "card", "pan", "phone", "email",
            "backend_url", "token", "secret", "api_key",
            "event_key", "event_code", "scanner_value", "barcode",
        ]:
            if forbidden in key_lower and key not in errors:
                errors.append(f"forbidden-like field in output: {key}")
                break

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def is_mode_run_safe(mode: str) -> bool:
    """Check if a mode is safe to run without explicit user approval."""
    return mode in ("dry_run", "preflight_only")


# ══════════════════════════════════════════════════════════════════════
# Factory functions
# ══════════════════════════════════════════════════════════════════════

def create_default_proof_plan(
    mode: str = "dry_run",
    display: str = DISPLAY_DEFAULT,
    duration_sec: int = DEFAULT_DURATION_SEC,
) -> X11ProofPlan:
    """Create a default production-ready proof plan."""
    return X11ProofPlan(
        title=PROOF_TITLE,
        display=display,
        width=GEOMETRY[0],
        height=GEOMETRY[1],
        x=WINDOW_ORIGIN[0],
        y=WINDOW_ORIGIN[1],
        duration_sec=duration_sec,
        mode=mode,
    )


def create_default_evidence_plan() -> X11ProofEvidencePlan:
    """Create a complete evidence plan."""
    return X11ProofEvidencePlan()


def create_preflight_result(
    display_available: bool = False,
    xdotool_available: bool = False,
    scrot_available: bool = False,
    xwininfo_available: bool = False,
    xprop_available: bool = False,
    python3_xlib_available: bool = False,
) -> X11ProofPreflight:
    """Create a preflight result from environment checks."""
    ready = (
        display_available
    )
    errors = []
    warnings = []

    if not display_available:
        errors.append("DISPLAY not available")
    if not xdotool_available:
        warnings.append("xdotool not available — window lookup may fail")
    if not scrot_available:
        warnings.append("scrot not available — screenshots will fail")
    if not xwininfo_available:
        warnings.append("xwininfo not available — geometry check will fail")
    if not xprop_available:
        warnings.append("xprop not available — window property check will fail")

    return X11ProofPreflight(
        ready=ready,
        errors=tuple(errors),
        warnings=tuple(warnings),
        display_available=display_available,
        xdotool_available=xdotool_available,
        scrot_available=scrot_available,
        xwininfo_available=xwininfo_available,
        xprop_available=xprop_available,
        python3_xlib_available=python3_xlib_available,
    )
