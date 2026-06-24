"""KSO Player Local Portrait Smoke Harness — safe, no-Chromium smoke test.

Orchestrates the full decision pipeline locally without a physical KSO:
    state.json → state_observer → kill_switch → shell_plan → visible/hidden

NO Chromium, NO X11, NO network, NO subprocess, NO backend, NO UKM5 DB.

Usage as CLI:
    python -m kso_player.portrait_smoke \\
        --state-file /tmp/idle.json \\
        --kill-switch /tmp/kill_switch

Usage as library:
    from kso_player.portrait_smoke import run_portrait_smoke
    result = run_portrait_smoke(profile_code="portrait_idle_overlay_768")
    print(result.to_json())

Output is ALWAYS safe JSON — no secrets, tokens, file paths, media refs,
receipt/payment/fiscal/customer/PII data.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Optional

from kso_player.shell_plan import (
    build_shell_plan,
    apply_state_snapshot,
    PLAN_MODE_VISIBLE,
)
from kso_player.state_observer import (
    read_state_snapshot,
    PlayerStateSnapshot,
    STATE_IDLE,
    STATE_STALE,
    STATE_UNKNOWN,
)
from kso_player.kill_switch import (
    DEFAULT_KILL_SWITCH_PATH,
    is_kill_switch_active,
)


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

DEFAULT_PROFILE = "portrait_idle_overlay_768"

# Smoke reason codes
REASON_IDLE_VISIBLE = "idle_visible"
REASON_STATE_HIDDEN = "state_hidden"
REASON_KILL_SWITCH_HIDDEN = "kill_switch_hidden"
REASON_STALE_HIDDEN = "stale_hidden"
REASON_UNKNOWN_HIDDEN = "unknown_hidden"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════


@dataclass
class SmokeResult:
    """Safe smoke test result — NO forbidden fields, NO secrets.

    Contains only geometry, state, visibility decision, and reason.
    Safe for printing to stdout, logs, and test assertions.
    """

    # ── Identity ────────────────────────────────────────────────────
    profile_code: str = ""
    profile_name: str = ""

    # ── State ───────────────────────────────────────────────────────
    state: str = STATE_UNKNOWN
    effective_state: str = STATE_UNKNOWN

    # ── Visibility ──────────────────────────────────────────────────
    visible_plan: str = "hidden"
    reason: str = REASON_UNKNOWN_HIDDEN
    kill_switch_active: bool = False

    # ── Window geometry ─────────────────────────────────────────────
    root_width: int = 0
    root_height: int = 0
    window_x: int = 0
    window_y: int = 0
    window_width: int = 0
    window_height: int = 0

    # ── Creative canvas (relative to window) ────────────────────────
    creative_x: int = 0
    creative_y: int = 0
    creative_width: int = 0
    creative_height: int = 0

    # ── Safety flags ────────────────────────────────────────────────
    window_type: str = "overlay"
    fullscreen: bool = False
    kiosk: bool = False
    always_on_top: bool = False
    no_focus_steal: bool = True

    @property
    def is_visible(self) -> bool:
        """Return True if the smoke result says visible."""
        return self.visible_plan == "visible"

    @property
    def is_hidden(self) -> bool:
        """Return True if the smoke result says hidden."""
        return self.visible_plan != "visible"

    def to_dict(self) -> dict:
        """Return a safe dict for JSON serialization.

        NEVER includes: secrets, tokens, file paths, media refs,
        receipt/payment/fiscal/customer/PII data, backend URLs.
        """
        return {
            "profile_code": self.profile_code,
            "profile_name": self.profile_name,
            "state": self.state,
            "effective_state": self.effective_state,
            "visible_plan": self.visible_plan,
            "reason": self.reason,
            "kill_switch_active": self.kill_switch_active,
            "window": {
                "root": f"{self.root_width}x{self.root_height}",
                "position": {"x": self.window_x, "y": self.window_y},
                "size": f"{self.window_width}x{self.window_height}",
            },
            "creative": {
                "position": {"x": self.creative_x, "y": self.creative_y},
                "size": f"{self.creative_width}x{self.creative_height}",
            },
            "flags": {
                "window_type": self.window_type,
                "fullscreen": self.fullscreen,
                "kiosk": self.kiosk,
                "always_on_top": self.always_on_top,
                "no_focus_steal": self.no_focus_steal,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Return safe JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def __repr__(self) -> str:
        return (
            f"SmokeResult("
            f"profile={self.profile_code!r}, "
            f"state={self.state!r}, "
            f"effective={self.effective_state!r}, "
            f"visible={self.visible_plan!r}, "
            f"reason={self.reason!r}, "
            f"ks={self.kill_switch_active}, "
            f"window={self.window_width}x{self.window_height}"
            f"+{self.window_x}+{self.window_y})"
        )


# ══════════════════════════════════════════════════════════════════════
# Smoke runner (pure orchestration)
# ══════════════════════════════════════════════════════════════════════


def run_portrait_smoke(
    profile_code: str = DEFAULT_PROFILE,
    state_path: Optional[str] = None,
    kill_switch_path: Optional[str] = None,
) -> SmokeResult:
    """Run local smoke test for a portrait overlay profile.

    Pipeline:
        1. Read PlayerStateSnapshot from state_path
        2. Check kill-switch at kill_switch_path
        3. Build ShellPlan for profile
        4. Apply state + kill-switch → visible/hidden
        5. Return safe SmokeResult

    NO Chromium, NO X11, NO network, NO subprocess, NO UKM5 DB.

    Args:
        profile_code: Player profile code (default: portrait_idle_overlay_768).
        state_path: Path to state.json. None → default /run/verny/kso/state.json.
        kill_switch_path: Path to kill-switch flag. None → default /run/verny/kso/kill_switch.

    Returns:
        SmokeResult with safe fields only.
    """
    # ── Step 1: Read state ─────────────────────────────────────
    if state_path is not None:
        snapshot = read_state_snapshot(state_path)
    else:
        snapshot = read_state_snapshot()  # use default path

    # ── Step 2: Check kill-switch ──────────────────────────────
    if kill_switch_path is not None:
        ks_active = is_kill_switch_active(kill_switch_path)
    else:
        ks_active = is_kill_switch_active()  # use default path

    # ── Step 3: Build shell plan ───────────────────────────────
    plan = build_shell_plan(
        profile_code,
        initial_state=STATE_UNKNOWN,  # safe default; overridden by snapshot
        kill_switch_active=ks_active,
    )

    # ── Step 4: Apply state + kill-switch ──────────────────────
    resolved = apply_state_snapshot(plan, snapshot, kill_switch_active=ks_active)

    # ── Step 5: Determine reason ───────────────────────────────
    reason = _determine_reason(snapshot, ks_active, resolved.visible_plan)

    return SmokeResult(
        profile_code=resolved.profile_code,
        profile_name=resolved.profile_name,
        state=snapshot.state,
        effective_state=snapshot.effective_state,
        visible_plan=resolved.visible_plan,
        reason=reason,
        kill_switch_active=ks_active,
        root_width=resolved.root_width,
        root_height=resolved.root_height,
        window_x=resolved.window_x,
        window_y=resolved.window_y,
        window_width=resolved.window_width,
        window_height=resolved.window_height,
        creative_x=resolved.creative_x,
        creative_y=resolved.creative_y,
        creative_width=resolved.creative_width,
        creative_height=resolved.creative_height,
        window_type=resolved.window_type,
        fullscreen=resolved.fullscreen,
        kiosk=resolved.kiosk,
        always_on_top=resolved.always_on_top,
        no_focus_steal=resolved.no_focus_steal,
    )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _determine_reason(
    snapshot: PlayerStateSnapshot,
    kill_switch_active: bool,
    visible_plan: str,
) -> str:
    """Determine the reason code from state, kill-switch, and visibility."""
    if kill_switch_active:
        return REASON_KILL_SWITCH_HIDDEN
    if visible_plan == PLAN_MODE_VISIBLE:
        return REASON_IDLE_VISIBLE
    if snapshot.effective_state == STATE_STALE:
        return REASON_STALE_HIDDEN
    if snapshot.effective_state == STATE_UNKNOWN:
        return REASON_UNKNOWN_HIDDEN
    return REASON_STATE_HIDDEN


# ══════════════════════════════════════════════════════════════════════
# CLI (safe, no-Chromium, no-network)
# ══════════════════════════════════════════════════════════════════════

def _cli_main() -> None:
    """CLI entry point for `python -m kso_player.portrait_smoke`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Portrait overlay player local smoke harness (NO Chromium, NO network)",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"Player profile code (default: {DEFAULT_PROFILE})",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to state.json (default: /run/verny/kso/state.json)",
    )
    parser.add_argument(
        "--kill-switch",
        default=None,
        help="Path to kill-switch flag (default: /run/verny/kso/kill_switch)",
    )

    args = parser.parse_args()

    result = run_portrait_smoke(
        profile_code=args.profile,
        state_path=args.state_file,
        kill_switch_path=args.kill_switch,
    )

    print(result.to_json())
    sys.exit(0 if result.is_visible else 0)


if __name__ == "__main__":
    _cli_main()
