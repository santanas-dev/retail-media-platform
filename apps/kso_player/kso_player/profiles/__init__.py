"""KSO Player Profiles — player profile contracts.

Each profile defines geometry, state rules, and safety constraints
for a specific target platform configuration.

Profiles are pure contracts — they do NOT alter runtime behavior.
The player shell selects a profile at startup and enforces its constraints.

Current profiles:
    portrait_idle_overlay_768 — v1 target: 768×1024 portrait UKM5 fleet,
        idle-only overlay on product grid zone (y=400-640).

Legacy (archived for v1):
    landscape_split_1920 — original 1920×1080 landscape, ad zone 1440×1080.
"""

from dataclasses import dataclass
from typing import FrozenSet, Optional

# ══════════════════════════════════════════════════════════════════════
# Profile dataclass
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PlayerProfile:
    """Immutable player profile contract.

    All fields are frozen after construction. A profile defines:
    - geometry: root screen, overlay zone, creative canvas
    - state rules: which states allow display, which force hide
    - safety: forbidden zones, hide SLA
    - constraints: idle_only, no_fullscreen, no_ukm5_db
    """

    # ── Identity ────────────────────────────────────────────────────
    code: str
    name: str

    # ── Geometry ────────────────────────────────────────────────────
    root_width: int
    root_height: int

    overlay_x: int
    overlay_y: int
    overlay_width: int
    overlay_height: int

    creative_x: int
    creative_y: int
    creative_width: int
    creative_height: int

    # ── State rules ─────────────────────────────────────────────────
    show_on_states: FrozenSet[str]
    hide_on_states: FrozenSet[str]

    # ── Safety ──────────────────────────────────────────────────────
    idle_only: bool = True
    no_fullscreen: bool = True
    no_ukm5_db: bool = True
    hide_sla_ms: int = 500

    # ── Forbidden zones (rectangles that must NOT intersect overlay) ─
    # Each zone is (x, y, w, h). Overlay zone MUST NOT overlap any.
    forbidden_zones: Optional[FrozenSet[tuple]] = None

    def __post_init__(self):
        """Validate profile constraints after construction."""
        if self.overlay_x < 0 or self.overlay_y < 0:
            raise ValueError("Overlay zone must be within root screen")
        if self.overlay_x + self.overlay_width > self.root_width:
            raise ValueError("Overlay zone exceeds root screen width")
        if self.overlay_y + self.overlay_height > self.root_height:
            raise ValueError("Overlay zone exceeds root screen height")

        if self.creative_x < self.overlay_x:
            raise ValueError("Creative canvas must be within overlay zone")
        if self.creative_y < self.overlay_y:
            raise ValueError("Creative canvas must be within overlay zone")
        if self.creative_x + self.creative_width > self.overlay_x + self.overlay_width:
            raise ValueError("Creative canvas exceeds overlay zone width")
        if self.creative_y + self.creative_height > self.overlay_y + self.overlay_height:
            raise ValueError("Creative canvas exceeds overlay zone height")

        if self.hide_sla_ms <= 0:
            raise ValueError("hide_sla_ms must be positive")

        if self.idle_only:
            if "idle" not in self.show_on_states:
                raise ValueError("idle_only=True requires 'idle' in show_on_states")
            if "idle" in self.hide_on_states:
                raise ValueError("idle_only=True requires 'idle' NOT in hide_on_states")

        if self.no_fullscreen:
            if (self.overlay_x == 0 and self.overlay_y == 0
                    and self.overlay_width == self.root_width
                    and self.overlay_height == self.root_height):
                raise ValueError("no_fullscreen=True requires overlay < root")

        # Validate forbidden zones don't intersect overlay
        if self.forbidden_zones:
            for zone in self.forbidden_zones:
                fx, fy, fw, fh = zone
                if _rects_intersect(
                    self.overlay_x, self.overlay_y,
                    self.overlay_width, self.overlay_height,
                    fx, fy, fw, fh,
                ):
                    raise ValueError(
                        f"Forbidden zone ({fx},{fy},{fw},{fh}) "
                        f"intersects overlay zone ({self.overlay_x},{self.overlay_y},"
                        f"{self.overlay_width},{self.overlay_height})"
                    )

    def allows_state(self, state: str) -> bool:
        """Return True if the given state allows showing ads."""
        s = state.strip().lower()
        if s in self.hide_on_states:
            return False
        if s in self.show_on_states:
            return True
        return False  # unknown state → safe default: hide

    def gap_to_zone(self, zone_x: int, zone_y: int,
                    zone_w: int, zone_h: int) -> int:
        """Minimum pixel distance between overlay zone and another rectangle.

        Returns 0 if they intersect or touch.
        """
        if _rects_intersect(
            self.overlay_x, self.overlay_y,
            self.overlay_width, self.overlay_height,
            zone_x, zone_y, zone_w, zone_h,
        ):
            return 0

        # Horizontal gap
        if self.overlay_x + self.overlay_width <= zone_x:
            h_gap = zone_x - (self.overlay_x + self.overlay_width)
        elif zone_x + zone_w <= self.overlay_x:
            h_gap = self.overlay_x - (zone_x + zone_w)
        else:
            h_gap = 0

        # Vertical gap
        if self.overlay_y + self.overlay_height <= zone_y:
            v_gap = zone_y - (self.overlay_y + self.overlay_height)
        elif zone_y + zone_h <= self.overlay_y:
            v_gap = self.overlay_y - (zone_y + zone_h)
        else:
            v_gap = 0

        if h_gap == 0:
            return v_gap
        if v_gap == 0:
            return h_gap
        # Diagonal gap: use larger component as minimum distance
        return max(h_gap, v_gap)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _rects_intersect(x1: int, y1: int, w1: int, h1: int,
                     x2: int, y2: int, w2: int, h2: int) -> bool:
    """Return True if two rectangles intersect (including touching)."""
    if x1 + w1 <= x2 or x2 + w2 <= x1:
        return False
    if y1 + h1 <= y2 or y2 + h2 <= y1:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════
# Profile registry
# ══════════════════════════════════════════════════════════════════════

_PROFILES: dict = {}


def register_profile(profile: PlayerProfile) -> None:
    """Register a player profile."""
    if profile.code in _PROFILES:
        raise ValueError(f"Profile already registered: {profile.code}")
    _PROFILES[profile.code] = profile


def get_profile(code: str) -> Optional[PlayerProfile]:
    """Get a registered profile by code. Returns None if not found."""
    return _PROFILES.get(code)


def list_profiles() -> tuple:
    """Return tuple of registered profile codes."""
    return tuple(sorted(_PROFILES.keys()))


# ══════════════════════════════════════════════════════════════════════
# Import and register built-in profiles
# ══════════════════════════════════════════════════════════════════════

from kso_player.profiles import portrait_idle_overlay_768  # noqa: E402, F401
