"""Guarded X11 Screensaver Runner — state-driven safe runtime for fullscreen idle screensaver.

Pure contract module — no X11 runtime dependency. The runner describes the lifecycle
and safety rules; the actual X11 window creation/hiding happens via the renderer
contract when running on physical KSO.

Lifecycle:
    build_plan → validate_plan → acquire_lockfile → check_kill_switch →
    read_safe_state_snapshot → decide_visibility → show_if_allowed →
    periodic_state_check → hide_on_unsafe_state → timeout →
    targeted_rollback → release_lockfile → safe_summary_output

Design: docs/audit/x11-screensaver-runner-design.md
Prerequisite: 38.1.6/38.1.7/38.1.8 — X11 click-through proof confirmed
"""

from dataclasses import dataclass, field

from kso_player.kill_switch import DEFAULT_KILL_SWITCH_PATH, is_kill_switch_active
from kso_player.state_observer import (
    PlayerStateSnapshot,
    STATE_IDLE,
    STATE_UNKNOWN,
    ALLOWED_STATES,
    read_state_snapshot,
    resolve_visibility,
)
from kso_player.x11_click_through_renderer import (
    X11ClickThroughCapabilities,
    X11RendererPlan,
    X11RendererValidationResult,
    validate_renderer_plan,
    validate_safe_output as validate_renderer_safe_output,
    create_default_renderer_plan,
    FORBIDDEN_FIELDS as RENDERER_FORBIDDEN_FIELDS,
)
from kso_player.interaction_hide import (
    HideDecision,
    should_hide,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

RUNNER_NAME = "x11_screensaver_runner"
RUNNER_VERSION = "0.1.0"

# Default paths
DEFAULT_STATE_PATH = "/run/verny/kso/state.json"
DEFAULT_LOCKFILE_PATH = "/run/verny/kso/x11_screensaver.lock"

# Timing defaults
DEFAULT_MAX_DURATION_SEC = 30
HARD_MAX_DURATION_SEC = 60
DEFAULT_POLL_INTERVAL_SEC = 0.5

# Modes
MODE_DRY_RUN = "dry_run"
MODE_PREFLIGHT_ONLY = "preflight_only"
MODE_RUN_ONCE = "run_once"

VALID_MODES = frozenset({MODE_DRY_RUN, MODE_PREFLIGHT_ONLY, MODE_RUN_ONCE})

APPROVAL_TOKEN = "USER_APPROVED_RUN_ONCE"

# Hide reasons
STOP_REASON_NONE = "none"
STOP_REASON_KILL_SWITCH = "kill_switch"
STOP_REASON_STATE_CHANGE = "state_change"
STOP_REASON_TIMEOUT = "timeout"
STOP_REASON_ERROR = "error"
STOP_REASON_DRY_RUN = "dry_run"
STOP_REASON_PREFLIGHT = "preflight"
STOP_REASON_FORBIDDEN = "forbidden"
STOP_REASON_STALE = "state_stale"
STOP_REASON_MISSING_STATE = "missing_state"

# Visibility reasons
VISIBILITY_NONE = "none"
VISIBILITY_IDLE_OK = "idle_ks_inactive"
VISIBILITY_HIDDEN_KS = "hidden_kill_switch"
VISIBILITY_HIDDEN_STATE = "hidden_state"
VISIBILITY_HIDDEN_FORBIDDEN = "hidden_forbidden"
VISIBILITY_HIDDEN_STALE = "hidden_stale"
VISIBILITY_HIDDEN_MISSING = "hidden_missing_state"

# — Forbidden commands — must NOT appear in any runner output/plan —
FORBIDDEN_COMMANDS = frozenset({
    "pkill chromium", "pkill -f chromium", "killall chromium",
    "systemctl restart mint", "systemctl stop mint",
    "systemctl restart mysql", "systemctl stop mysql",
    "systemctl restart redis", "systemctl stop redis",
    "systemctl restart chromium", "systemctl stop chromium",
    "systemctl enable", "systemctl disable",
    "systemctl mask", "systemctl unmask",
    "restart mint", "stop mint",
    "reboot", "shutdown", "poweroff", "halt",
})

# — Forbidden fields in any runner output (extends renderer's list) —
RUNNER_FORBIDDEN_FIELDS = frozenset({
    "receipt_id", "transaction_id", "payment_amount", "payment_method",
    "fiscal_data", "customer_name", "customer_id", "customer_phone",
    "customer_email", "card_number", "pan", "items", "total_amount",
    "cashier_id", "cashier_name", "receipt_number",
    "backend_url", "backend_host", "backend_port",
    "token", "secret", "api_key", "password", "access_token",
    "refresh_token", "bearer", "jwt",
    "event_key", "event_code", "event_keycode", "event_data",
    "event_value", "input_value", "scanner_value", "barcode", "key_value",
    "device_secret", "device_token",
})


# ══════════════════════════════════════════════════════════════════════
# Safe Result Model
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ScreensaverRunResult:
    """Immutable result of a single runner invocation.

    Contains ONLY safe fields — no receipt, payment, fiscal, customer,
    card, scanner, token, secret, or backend URL data.
    """

    started: bool = False
    visible: bool = False
    reason: str = VISIBILITY_NONE
    state: str = STATE_UNKNOWN
    kill_switch_active: bool = False
    duration_sec: float = 0.0
    window_id: int | None = None
    rollback_done: bool = False
    stop_reason: str = STOP_REASON_NONE
    proof_summary: str = ""
    mode: str = MODE_DRY_RUN
    renderer_plan_valid: bool = False
    renderer_production_ready: bool = False
    hide_decision: HideDecision | None = None

    def __post_init__(self):
        # Validate state
        if self.state not in ALLOWED_STATES:
            object.__setattr__(self, "state", STATE_UNKNOWN)
        # Validate mode
        if self.mode not in VALID_MODES:
            object.__setattr__(self, "mode", MODE_DRY_RUN)

    @property
    def safe_for_logging(self) -> bool:
        """Return True if this result is safe for logging/output."""
        return validate_runner_safe_output(self.to_safe_dict())["valid"]

    def to_safe_dict(self) -> dict:
        """Return a dict safe for logging — no forbidden fields."""
        result = {
            "runner": RUNNER_NAME,
            "version": RUNNER_VERSION,
            "started": self.started,
            "visible": self.visible,
            "reason": self.reason,
            "state": self.state,
            "kill_switch_active": self.kill_switch_active,
            "duration_sec": self.duration_sec,
            "rollback_done": self.rollback_done,
            "stop_reason": self.stop_reason,
            "proof_summary": self.proof_summary,
            "mode": self.mode,
            "renderer_plan_valid": self.renderer_plan_valid,
            "renderer_production_ready": self.renderer_production_ready,
        }
        if self.window_id is not None:
            result["window_id"] = self.window_id
        if self.hide_decision is not None:
            result["hide_trigger"] = self.hide_decision.reason
            result["hide_target_ms"] = self.hide_decision.target_ms
            result["scanner_risk"] = self.hide_decision.scanner_risk
        return result


@dataclass(frozen=True)
class ScreensaverRunPlan:
    """Immutable runner execution plan — safe for logging, no X11 calls."""

    runner_name: str = RUNNER_NAME
    version: str = RUNNER_VERSION
    mode: str = MODE_DRY_RUN
    display: str = ":0"
    max_duration_sec: int = DEFAULT_MAX_DURATION_SEC
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC

    state_path: str = DEFAULT_STATE_PATH
    kill_switch_path: str = DEFAULT_KILL_SWITCH_PATH
    lockfile_path: str = DEFAULT_LOCKFILE_PATH

    approval_provided: bool = False
    renderer_plan: X11RendererPlan | None = None

    def __post_init__(self):
        if not self.display:
            raise ValueError("display must be set (e.g. ':0')")
        if self.max_duration_sec <= 0:
            raise ValueError(
                f"max_duration_sec must be > 0, got {self.max_duration_sec}"
            )
        if self.max_duration_sec > HARD_MAX_DURATION_SEC:
            raise ValueError(
                f"max_duration_sec must be <= {HARD_MAX_DURATION_SEC}, "
                f"got {self.max_duration_sec}"
            )
        if self.mode not in VALID_MODES:
            raise ValueError(f"invalid mode: {self.mode}")

    def to_safe_dict(self) -> dict:
        """Return a dict safe for logging — no forbidden fields."""
        d = {
            "runner_name": self.runner_name,
            "version": self.version,
            "mode": self.mode,
            "display": self.display,
            "max_duration_sec": self.max_duration_sec,
            "poll_interval_sec": self.poll_interval_sec,
            "approval_provided": self.approval_provided,
        }
        if self.renderer_plan is not None:
            d["renderer_plan"] = self.renderer_plan.to_safe_dict()
        return d


# ══════════════════════════════════════════════════════════════════════
# Validation — pure functions
# ══════════════════════════════════════════════════════════════════════


def validate_runner_plan(plan: ScreensaverRunPlan) -> dict:
    """Validate a runner plan against safety rules.

    Returns:
        {"valid": bool, "errors": [str]}
    """
    errors = []

    if not plan.display:
        errors.append("display must be set (e.g. ':0')")
    if plan.max_duration_sec <= 0:
        errors.append("max_duration_sec must be > 0")
    if plan.max_duration_sec > HARD_MAX_DURATION_SEC:
        errors.append(
            f"max_duration_sec exceeds hard max {HARD_MAX_DURATION_SEC}"
        )
    if plan.poll_interval_sec <= 0:
        errors.append("poll_interval_sec must be > 0")
    if plan.mode not in VALID_MODES:
        errors.append(f"invalid mode: {plan.mode}")

    # run_once requires approval
    if plan.mode == MODE_RUN_ONCE and not plan.approval_provided:
        errors.append(
            "run_once requires approval token (--approval-token "
            f"{APPROVAL_TOKEN})"
        )

    # Validate renderer plan if present
    if plan.renderer_plan is not None:
        rv = validate_renderer_plan(plan.renderer_plan)
        if not rv.valid:
            errors.extend(f"renderer: {e}" for e in rv.errors)

    # Safety: no autostart paths
    autostart_patterns = ["autostart", "systemd", "fleet", "rc.local",
                          ".profile", "xinitrc", "crontab", "cron.d"]
    for pattern in autostart_patterns:
        if pattern in plan.mode.lower():
            errors.append(f"mode must not contain autostart-like pattern: {pattern}")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_runner_safe_output(data: dict) -> dict:
    """Validate runner output for forbidden fields.

    Returns:
        {"valid": bool, "errors": [str]}
    """
    errors = []

    if not isinstance(data, dict):
        return {"valid": False, "errors": ["data must be a dict"]}

    for key in data:
        key_lower = key.lower()

        # Exact forbidden match
        if key_lower in RUNNER_FORBIDDEN_FIELDS:
            errors.append(f"forbidden field in output: {key}")

        # Substring check for sensitive patterns
        forbidden_patterns = [
            "receipt", "payment", "fiscal", "customer",
            "card", "pan", "phone", "email",
            "backend_url", "backend", "token", "secret",
            "api_key", "password", "jwt", "bearer",
            "event_key", "event_code", "scanner_value",
            "barcode", "device_secret",
        ]
        for pattern in forbidden_patterns:
            if pattern in key_lower:
                if key not in errors:
                    errors.append(f"forbidden-like field in output: {key}")
                break

    return {"valid": len(errors) == 0, "errors": errors}


def validate_command_safety(command: str) -> dict:
    """Check if a shell command is safe for runner execution.

    Returns:
        {"safe": bool, "violations": [str]}
    """
    violations = []
    cmd_lower = command.lower()

    for forbidden in FORBIDDEN_COMMANDS:
        if forbidden.lower() in cmd_lower:
            violations.append(f"forbidden command pattern: {forbidden}")

    # Check for autostart modifications
    autostart = [
        "systemctl enable", "systemctl disable",
        "systemctl mask", "systemctl unmask",
        "systemctl daemon-reload",
        "/etc/systemd/system/", "/etc/rc.local",
        "~/.profile", "~/.xinitrc", "~/.bashrc",
        "openbox/autostart", "crontab -e",
    ]
    for pattern in autostart:
        if pattern.lower() in cmd_lower:
            violations.append(f"forbidden autostart operation: {pattern}")

    return {"safe": len(violations) == 0, "violations": violations}


# ══════════════════════════════════════════════════════════════════════
# State-driven lifecycle functions (pure — no X11 runtime)
# ══════════════════════════════════════════════════════════════════════


def build_plan(
    mode: str = MODE_DRY_RUN,
    display: str = ":0",
    max_duration_sec: int = DEFAULT_MAX_DURATION_SEC,
    state_path: str = DEFAULT_STATE_PATH,
    kill_switch_path: str = DEFAULT_KILL_SWITCH_PATH,
    lockfile_path: str = DEFAULT_LOCKFILE_PATH,
    approval_token: str | None = None,
) -> ScreensaverRunPlan:
    """Build a runner execution plan.

    Args:
        mode: dry_run, preflight_only, or run_once
        display: X11 display (e.g. ':0')
        max_duration_sec: Maximum runtime in seconds (≤ 60)
        state_path: Path to KSO state JSON file
        kill_switch_path: Path to kill-switch flag file
        lockfile_path: Path to runner lockfile
        approval_token: Required for run_once

    Returns:
        ScreensaverRunPlan (immutable)
    """
    approval_provided = (approval_token == APPROVAL_TOKEN)

    renderer_plan = create_default_renderer_plan(display=display)

    return ScreensaverRunPlan(
        mode=mode,
        display=display,
        max_duration_sec=min(max_duration_sec, HARD_MAX_DURATION_SEC),
        state_path=state_path,
        kill_switch_path=kill_switch_path,
        lockfile_path=lockfile_path,
        approval_provided=approval_provided,
        renderer_plan=renderer_plan,
    )


def decide_visibility(
    state_snapshot: PlayerStateSnapshot,
    kill_switch_active: bool,
) -> tuple[bool, str]:
    """Decide whether the screensaver should be visible.

    Pure function — no I/O, no X11.

    Priority:
        1. kill_switch_active → HIDDEN
        2. state != idle → HIDDEN (stale, unknown, all others)
        3. idle + kill_switch inactive → VISIBLE

    Args:
        state_snapshot: Immutable state snapshot
        kill_switch_active: Kill-switch status

    Returns:
        (should_show: bool, reason: str)
    """
    if kill_switch_active:
        return False, VISIBILITY_HIDDEN_KS

    if not state_snapshot.allows_display:
        if state_snapshot.effective_state == "stale":
            return False, VISIBILITY_HIDDEN_STALE
        if state_snapshot.effective_state == "unknown":
            return False, VISIBILITY_HIDDEN_MISSING
        if state_snapshot.state == "forbidden":
            return False, VISIBILITY_HIDDEN_FORBIDDEN
        return False, VISIBILITY_HIDDEN_STATE

    return True, VISIBILITY_IDLE_OK


def check_forbidden_state_fields(data: dict) -> bool:
    """Check if state data contains forbidden fields.

    Returns True if forbidden fields FOUND (meaning: hide!).
    """
    if not isinstance(data, dict):
        return True  # Bad data → forbid

    for key in data:
        key_lower = key.lower()
        if key_lower in RUNNER_FORBIDDEN_FIELDS:
            return True
        # Substring patterns
        for pattern in [
            "receipt", "payment", "fiscal", "customer",
            "card", "pan", "phone", "email",
            "backend_url", "token", "secret", "password",
        ]:
            if pattern in key_lower:
                return True

    return False


def simulate_run(
    plan: ScreensaverRunPlan,
    snapshot: PlayerStateSnapshot | None = None,
    kill_switch_active: bool | None = None,
) -> ScreensaverRunResult:
    """Simulate a full runner lifecycle — NO X11 calls.

    Pure function that exercises all lifecycle phases and returns
    the result that a physical run WOULD produce. Safe for testing.

    Args:
        plan: Validated runner plan
        snapshot: State snapshot (if None, uses unknown state)
        kill_switch_active: Kill-switch status override

    Returns:
        ScreensaverRunResult describing what WOULD happen
    """
    # 0. Check approval FIRST (before validation)
    if plan.mode == MODE_RUN_ONCE and not plan.approval_provided:
        return ScreensaverRunResult(
            started=False,
            visible=False,
            reason=VISIBILITY_NONE,
            state=STATE_UNKNOWN,
            stop_reason=STOP_REASON_ERROR,
            proof_summary="APPROVAL REQUIRED: --approval-token USER_APPROVED_RUN_ONCE",
            mode=plan.mode,
        )

    plan_validation = validate_runner_plan(plan)

    if not plan_validation["valid"]:
        return ScreensaverRunResult(
            started=False,
            visible=False,
            reason=VISIBILITY_NONE,
            state=STATE_UNKNOWN,
            stop_reason=STOP_REASON_ERROR,
            proof_summary=f"plan invalid: {'; '.join(plan_validation['errors'])}",
            mode=plan.mode,
        )

    # 1. Acquire lockfile (simulated — always True in simulation)
    lockfile_ok = True

    # 2. Check kill-switch
    if kill_switch_active is None:
        kill_switch_active = is_kill_switch_active(plan.kill_switch_path)

    # 3. Read state snapshot
    if snapshot is None:
        snapshot = read_state_snapshot(plan.state_path)

    # Check for forbidden fields in raw state
    state_has_forbidden = check_forbidden_state_fields(
        {"state": snapshot.state, "device_code": snapshot.device_code}
    )

    # Validate renderer plan
    rv: X11RendererValidationResult
    if plan.renderer_plan is not None:
        rv = validate_renderer_plan(plan.renderer_plan)
    else:
        rv = X11RendererValidationResult(valid=False, production_ready=False,
                                         errors=("no renderer plan",))

    # 4. Decide visibility
    should_show, reason = decide_visibility(snapshot, kill_switch_active)

    if state_has_forbidden:
        should_show = False
        reason = VISIBILITY_HIDDEN_FORBIDDEN

    # 5. Hide decision
    hide_decision = should_hide(
        dom_events=frozenset(),
        state=snapshot.effective_state,
        kill_switch_active=kill_switch_active,
        input_mode="x11_click_through",
    )

    # 6. Build result
    if plan.mode == MODE_DRY_RUN:
        return ScreensaverRunResult(
            started=True,
            visible=False,  # dry-run never shows
            reason=reason,
            state=snapshot.effective_state,
            kill_switch_active=kill_switch_active,
            duration_sec=0.0,
            rollback_done=True,
            stop_reason=STOP_REASON_DRY_RUN,
            proof_summary=(
                f"DRY RUN: plan valid, renderer_plan_valid={rv.valid}, "
                f"production_ready={rv.production_ready}, "
                f"state={snapshot.effective_state}, "
                f"visibility_decision={reason}, "
                f"lockfile_ok={lockfile_ok}"
            ),
            mode=plan.mode,
            renderer_plan_valid=rv.valid,
            renderer_production_ready=rv.production_ready,
            hide_decision=hide_decision if hide_decision.hide else None,
        )

    if plan.mode == MODE_PREFLIGHT_ONLY:
        return ScreensaverRunResult(
            started=True,
            visible=False,  # preflight never shows
            reason=reason,
            state=snapshot.effective_state,
            kill_switch_active=kill_switch_active,
            duration_sec=0.0,
            rollback_done=True,
            stop_reason=STOP_REASON_PREFLIGHT,
            proof_summary=(
                f"PREFLIGHT: plan valid, renderer_plan_valid={rv.valid}, "
                f"production_ready={rv.production_ready}, "
                f"state={snapshot.effective_state}, "
                f"display={plan.display}, "
                f"lockfile_ok={lockfile_ok}"
            ),
            mode=plan.mode,
            renderer_plan_valid=rv.valid,
            renderer_production_ready=rv.production_ready,
            hide_decision=hide_decision if hide_decision.hide else None,
        )

    if plan.mode == MODE_RUN_ONCE:
        if not plan.approval_provided:
            return ScreensaverRunResult(
                started=False,
                visible=False,
                reason=VISIBILITY_NONE,
                state=STATE_UNKNOWN,
                stop_reason=STOP_REASON_ERROR,
                proof_summary="APPROVAL REQUIRED: --approval-token USER_APPROVED_RUN_ONCE",
                mode=plan.mode,
            )

        # run_once simulation: would show if idle + no kill-switch
        if should_show and rv.valid:
            return ScreensaverRunResult(
                started=True,
                visible=True,
                reason=reason,
                state=snapshot.effective_state,
                kill_switch_active=kill_switch_active,
                duration_sec=float(plan.max_duration_sec),
                window_id=52428801,  # placeholder — real run produces real ID
                rollback_done=True,
                stop_reason=STOP_REASON_TIMEOUT,
                proof_summary=(
                    f"RUN ONCE (simulated): screen visible, "
                    f"renderer={rv.production_ready}, "
                    f"state={snapshot.effective_state}, "
                    f"kill_switch={kill_switch_active}"
                ),
                mode=plan.mode,
                renderer_plan_valid=rv.valid,
                renderer_production_ready=rv.production_ready,
                hide_decision=None,
            )
        else:
            hide_stop_reason = STOP_REASON_KILL_SWITCH if kill_switch_active else STOP_REASON_STATE_CHANGE
            if state_has_forbidden:
                hide_stop_reason = STOP_REASON_FORBIDDEN
            elif snapshot.effective_state == "stale":
                hide_stop_reason = STOP_REASON_STALE
            elif snapshot.effective_state == "unknown":
                hide_stop_reason = STOP_REASON_MISSING_STATE

            return ScreensaverRunResult(
                started=True,
                visible=False,
                reason=reason,
                state=snapshot.effective_state,
                kill_switch_active=kill_switch_active,
                duration_sec=0.0,
                rollback_done=True,
                stop_reason=hide_stop_reason,
                proof_summary=(
                    f"RUN ONCE (simulated): screen HIDDEN, "
                    f"reason={hide_stop_reason}, "
                    f"renderer_plan_valid={rv.valid}, "
                    f"state={snapshot.effective_state}"
                ),
                mode=plan.mode,
                renderer_plan_valid=rv.valid,
                renderer_production_ready=rv.production_ready,
                hide_decision=hide_decision if hide_decision.hide else None,
            )

    # Fallback (should not reach)
    return ScreensaverRunResult(
        started=False,
        visible=False,
        reason=VISIBILITY_NONE,
        state=STATE_UNKNOWN,
        stop_reason=STOP_REASON_ERROR,
        proof_summary="unknown mode",
        mode=plan.mode,
    )


# ══════════════════════════════════════════════════════════════════════
# Safety validators for forbidden operations
# ══════════════════════════════════════════════════════════════════════


# Fields that MUST NOT appear in screensaver runner output/logs
RUNNER_SAFE_LOG_FIELDS = frozenset({
    "runner", "version", "started", "visible", "reason", "state",
    "kill_switch_active", "duration_sec", "window_id",
    "rollback_done", "stop_reason", "proof_summary", "mode",
    "renderer_plan_valid", "renderer_production_ready",
    "hide_trigger", "hide_target_ms", "scanner_risk",
})

# Commands that the runner must NEVER execute
FORBIDDEN_RUNNER_COMMANDS = frozenset({
    *FORBIDDEN_COMMANDS,
    "systemctl enable",
    "systemctl disable",
    "systemctl mask",
    "systemctl unmask",
    "systemctl daemon-reload",
})

# UKM5 files that must NEVER be modified
FORBIDDEN_UKM5_FILES = frozenset({
    "openbox", ".profile", "xinitrc", "index.html",
    "autostart", "/etc/systemd/system/",
    "/home/ukm5/.profile", "/home/ukm5/.xinitrc",
})
