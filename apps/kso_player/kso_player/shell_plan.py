"""KSO Player Shell Plan — profile-driven window/shell configuration.

Converts a PlayerProfile into a safe shell plan that describes window
geometry, flags, and safety constraints for the display layer.

The shell plan is a PURE data structure — it does NOT launch Chromium,
does NOT create windows, does NOT access X11. It is consumed by the
display layer (future: local_chromium_demo_runner, production systemd).

Pipeline:
    PlayerProfile → build_shell_plan() → ShellPlan
    ShellPlan → display layer (Chromium command, X11 overlay, etc.)

Profiles:
    portrait_idle_overlay_768 — non-fullscreen overlay, window at (0,400),
                                768×240, idle-only, kill-switch required

    landscape_split_1920 (future) — fullscreen kiosk, 1440×1080

NO Chromium, NO X11, NO HTTP, NO backend.
"""

from dataclasses import dataclass, field
from typing import FrozenSet, Optional

from kso_player.profiles import PlayerProfile, get_profile

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

# Shell plan modes
PLAN_MODE_VISIBLE = "visible"
PLAN_MODE_HIDDEN = "hidden"
PLAN_MODE_HOLD = "hold"

# Window type
WINDOW_TYPE_KIOSK = "kiosk"         # Chromium --kiosk mode (fullscreen, no chrome)
WINDOW_TYPE_APP = "app"             # Chromium --app mode (windowed, no chrome)
WINDOW_TYPE_OVERLAY = "overlay"     # X11 override-redirect overlay (custom)
WINDOW_TYPE_UNKNOWN = "unknown"

# Chromium flags that must NOT appear for non-fullscreen profiles
_FORBIDDEN_FULLSCREEN_FLAGS = frozenset({
    "--kiosk",
    "--start-fullscreen",
    "--start-maximized",
    "--fullscreen",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════


@dataclass
class ShellPlan:
    """Profile-driven shell configuration plan.

    Describes window geometry, visibility mode, and safety flags.
    Consumed by the display layer — does NOT perform any I/O.
    """

    # ── Profile identity ──────────────────────────────────────────
    profile_code: str = ""
    profile_name: str = ""

    # ── Geometry ──────────────────────────────────────────────────
    root_width: int = 0
    root_height: int = 0
    window_x: int = 0
    window_y: int = 0
    window_width: int = 0
    window_height: int = 0
    creative_x: int = 0
    creative_y: int = 0
    creative_width: int = 0
    creative_height: int = 0

    # ── Window flags ──────────────────────────────────────────────
    window_type: str = WINDOW_TYPE_UNKNOWN
    fullscreen: bool = False
    kiosk: bool = False
    always_on_top: bool = False
    no_focus_steal: bool = True

    # ── Safety flags ──────────────────────────────────────────────
    kill_switch_required: bool = True
    hide_on_start_if_state_not_idle: bool = True
    idle_only: bool = True
    no_ukm5_db: bool = True

    # ── State-based visibility ────────────────────────────────────
    visible_plan: str = PLAN_MODE_HIDDEN  # current plan visibility
    show_on_states: FrozenSet[str] = field(default_factory=frozenset)
    hide_on_states: FrozenSet[str] = field(default_factory=frozenset)
    hide_sla_ms: int = 500

    # ── Forbidden zones (must not intersect window) ────────────────
    forbidden_zones: FrozenSet[tuple] = field(default_factory=frozenset)

    # ── Chromium flags ────────────────────────────────────────────
    # Flags that MUST NOT appear for this profile
    forbidden_chromium_flags: FrozenSet[str] = field(
        default_factory=lambda: _FORBIDDEN_FULLSCREEN_FLAGS
    )

    def is_visible(self) -> bool:
        """Return True if the current visibility plan is visible."""
        return self.visible_plan == PLAN_MODE_VISIBLE

    def is_hidden(self) -> bool:
        """Return True if the current visibility plan is hidden/hold."""
        return self.visible_plan in (PLAN_MODE_HIDDEN, PLAN_MODE_HOLD)

    def __repr__(self) -> str:
        return (
            f"ShellPlan("
            f"profile={self.profile_code!r}, "
            f"window={self.window_width}x{self.window_height}"
            f"+{self.window_x}+{self.window_y}, "
            f"type={self.window_type!r}, "
            f"fullscreen={self.fullscreen}, "
            f"kiosk={self.kiosk}, "
            f"visible={self.visible_plan!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Shell plan builder
# ══════════════════════════════════════════════════════════════════════


def build_shell_plan(
    profile_code: str,
    initial_state: str = "unknown",
) -> ShellPlan:
    """Build a shell plan from a registered player profile.

    Args:
        profile_code: Registered profile code (e.g. 'portrait_idle_overlay_768').
        initial_state: Initial KSO state for visibility decision.
                       Default: 'unknown' (safe — always hidden).

    Returns:
        ShellPlan describing window geometry, flags, and visibility.

    Raises:
        ValueError: If profile_code is not registered.
    """
    profile = get_profile(profile_code)
    if profile is None:
        raise ValueError(f"Unknown profile: {profile_code!r}")

    # ── Determine window type ────────────────────────────────────
    if profile.no_fullscreen:
        window_type = WINDOW_TYPE_OVERLAY
        fullscreen = False
        kiosk = False
    else:
        window_type = WINDOW_TYPE_KIOSK
        fullscreen = True
        kiosk = True

    # ── Window geometry matches overlay zone for non-fullscreen ──
    # For fullscreen profiles: window covers root
    if profile.no_fullscreen:
        window_x = profile.overlay_x
        window_y = profile.overlay_y
        window_width = profile.overlay_width
        window_height = profile.overlay_height
        always_on_top = True  # overlay must stay above UKM5
    else:
        window_x = 0
        window_y = 0
        window_width = profile.root_width
        window_height = profile.root_height
        always_on_top = False

    # ── Creative canvas offset within window ─────────────────────
    creative_x = profile.creative_x - window_x
    creative_y = profile.creative_y - window_y

    # ── Determine visibility from initial state ──────────────────
    if profile.allows_state(initial_state):
        visible_plan = PLAN_MODE_VISIBLE
    elif profile.idle_only and not profile.allows_state(initial_state):
        visible_plan = PLAN_MODE_HIDDEN
    else:
        visible_plan = PLAN_MODE_HOLD

    # ── Forbidden Chromium flags for non-fullscreen ──────────────
    if profile.no_fullscreen:
        forbidden_flags = _FORBIDDEN_FULLSCREEN_FLAGS
    else:
        forbidden_flags = frozenset()

    return ShellPlan(
        profile_code=profile.code,
        profile_name=profile.name,
        root_width=profile.root_width,
        root_height=profile.root_height,
        window_x=window_x,
        window_y=window_y,
        window_width=window_width,
        window_height=window_height,
        creative_x=creative_x,
        creative_y=creative_y,
        creative_width=profile.creative_width,
        creative_height=profile.creative_height,
        window_type=window_type,
        fullscreen=fullscreen,
        kiosk=kiosk,
        always_on_top=always_on_top,
        no_focus_steal=profile.no_fullscreen,  # overlay must not steal focus
        kill_switch_required=True,
        hide_on_start_if_state_not_idle=profile.idle_only,
        idle_only=profile.idle_only,
        no_ukm5_db=profile.no_ukm5_db,
        visible_plan=visible_plan,
        show_on_states=profile.show_on_states,
        hide_on_states=profile.hide_on_states,
        hide_sla_ms=profile.hide_sla_ms,
        forbidden_zones=profile.forbidden_zones or frozenset(),
        forbidden_chromium_flags=forbidden_flags,
    )


def validate_shell_plan_for_state(
    plan: ShellPlan,
    state: str,
) -> ShellPlan:
    """Return a copy of the shell plan with visibility updated for a state.

    Pure function — does not mutate the original plan.

    Args:
        plan: Existing ShellPlan.
        state: Current KSO state (idle, busy, payment, etc.).

    Returns:
        New ShellPlan with updated visible_plan.
    """
    from kso_player.profiles import get_profile

    profile = get_profile(plan.profile_code)
    if profile is None:
        # Fallback: use plan's own state rules
        allows = state.strip().lower() in plan.show_on_states
        hides = state.strip().lower() in plan.hide_on_states
    else:
        allows = profile.allows_state(state)
        hides = not allows

    if allows:
        new_visibility = PLAN_MODE_VISIBLE
    elif hides:
        new_visibility = PLAN_MODE_HIDDEN
    else:
        new_visibility = PLAN_MODE_HOLD  # safe default

    # Create updated plan (dataclass is not frozen — we can replace)
    return ShellPlan(
        profile_code=plan.profile_code,
        profile_name=plan.profile_name,
        root_width=plan.root_width,
        root_height=plan.root_height,
        window_x=plan.window_x,
        window_y=plan.window_y,
        window_width=plan.window_width,
        window_height=plan.window_height,
        creative_x=plan.creative_x,
        creative_y=plan.creative_y,
        creative_width=plan.creative_width,
        creative_height=plan.creative_height,
        window_type=plan.window_type,
        fullscreen=plan.fullscreen,
        kiosk=plan.kiosk,
        always_on_top=plan.always_on_top,
        no_focus_steal=plan.no_focus_steal,
        kill_switch_required=plan.kill_switch_required,
        hide_on_start_if_state_not_idle=plan.hide_on_start_if_state_not_idle,
        idle_only=plan.idle_only,
        no_ukm5_db=plan.no_ukm5_db,
        visible_plan=new_visibility,
        show_on_states=plan.show_on_states,
        hide_on_states=plan.hide_on_states,
        hide_sla_ms=plan.hide_sla_ms,
        forbidden_zones=plan.forbidden_zones,
        forbidden_chromium_flags=plan.forbidden_chromium_flags,
    )
