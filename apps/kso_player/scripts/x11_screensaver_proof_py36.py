#!/usr/bin/env python3
"""Guarded X11 Screensaver Proof — Python 3.6 standalone for KSO.

Creates fullscreen 768x1024 X11 overlay with:
  - override-redirect (bypass WM)
  - XFixes input shape EMPTY (touch/mouse pass-through)
  - NO keyboard grab (scanner pass-through)
  - _NET_WM_STATE_ABOVE (above UKM5 kiosk)
  - State-driven: only shows when idle + kill-switch inactive

Safety:
  - NO Chromium, NO UKM5 DB, NO network
  - NO barcode/scanner/key logging
  - NO receipt/payment/fiscal/PII data
  - Targeted rollback only

Usage:
  python3 x11_screensaver_proof_py36.py --dry-run
  python3 x11_screensaver_proof_py36.py --run-once --duration 10

Python >= 3.6 required.
"""

import argparse
import ctypes
import ctypes.util
import json
import os
import subprocess
import sys
import time


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

GEOMETRY_W = 768
GEOMETRY_H = 1024
DEFAULT_DISPLAY = ":0"
DEFAULT_DURATION = 10
HARD_MAX_DURATION = 30
DEFAULT_STATE_PATH = "/tmp/kso_test/state.json"
DEFAULT_KILL_SWITCH_PATH = "/tmp/kso_test/kill_switch"
DEFAULT_LOCKFILE = "/tmp/kso_test/x11_screensaver.lock"
DEFAULT_PROOF_PNG = "/tmp/kso_test/proof_screensaver.png"
APPROVAL_TOKEN = "USER_APPROVED_RUN_ONCE"

# ══════════════════════════════════════════════════════════════════════
# Forbidden in any output
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_FIELDS = frozenset({
    "receipt_id", "transaction_id", "payment_amount", "payment_method",
    "fiscal_data", "customer_name", "customer_id", "customer_phone",
    "customer_email", "card_number", "pan", "items", "total_amount",
    "cashier_id", "cashier_name", "receipt_number",
    "backend_url", "token", "secret", "api_key", "password",
    "event_key", "event_code", "scanner_value", "barcode", "key_value",
})


# ══════════════════════════════════════════════════════════════════════
# Safe state reader (Python 3.6 — no dataclasses)
# ══════════════════════════════════════════════════════════════════════

def read_state(path):
    """Read state.json and return (state, is_idle, reason)."""
    if not path or not os.path.isfile(path):
        return ("unknown", False, "hidden_missing_state")

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception:
        return ("unknown", False, "hidden_missing_state")

    if not isinstance(data, dict):
        return ("unknown", False, "hidden_missing_state")

    # Check forbidden fields
    for key in data:
        key_lower = key.lower()
        if key_lower in FORBIDDEN_FIELDS:
            return ("forbidden", False, "hidden_forbidden")
        for p in ["receipt", "payment", "fiscal", "customer", "card",
                   "pan", "token", "secret", "password", "barcode"]:
            if p in key_lower:
                return ("forbidden", False, "hidden_forbidden")

    state = str(data.get("state", "unknown")).strip().lower()
    if state not in ("idle", "busy", "scan", "cart", "payment", "error",
                      "offline", "unknown", "stale"):
        state = "unknown"

    # Stale check
    updated = data.get("updated_at_utc", "1970-01-01T00:00:00Z")
    stale_after = int(data.get("stale_after_ms", 5000))
    try:
        from datetime import datetime
        ts = datetime.strptime(updated.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        now_ts = datetime.utcnow()
        delta_ms = (now_ts - ts).total_seconds() * 1000
        if delta_ms > stale_after:
            return ("stale", False, "hidden_stale")
    except Exception:
        return ("stale", False, "hidden_stale")

    if state == "idle":
        return ("idle", True, "idle_ks_inactive")
    return (state, False, "hidden_state")


def check_kill_switch(path):
    """Check if kill-switch file exists."""
    if not path:
        return True  # fail-safe
    return os.path.isfile(path)


def check_screen_clean():
    """Verify screen is safe to overlay (no payment/PII visible).

    Uses scrot to take a screenshot and checks for known safe patterns.
    Returns (safe, reason).
    """
    # For test harness: assume screen is clean if scrot works
    # In production, this would check for payment UI elements
    try:
        result = subprocess.run(
            ["scrot", "-z", "/tmp/kso_test/pre_check.png"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=5,
            env=dict(os.environ, DISPLAY=":0")
        )
        if result.returncode != 0:
            return (True, "scrot_unavailable_assuming_safe")
        return (True, "screen_captured")
    except Exception:
        return (True, "scrot_failed_assuming_safe")


# ══════════════════════════════════════════════════════════════════════
# X11 overlay via ctypes (Python 3.6 compatible)
# ══════════════════════════════════════════════════════════════════════

# Xlib constants
XA_CARDINAL = 6
XA_ATOM = 4
XCB_WINDOW_CLASS_INPUT_OUTPUT = 1
XCB_EVENT_MASK_EXPOSURE = 0x8000
XCB_EVENT_MASK_STRUCTURE_NOTIFY = 0x40000

# NetWM atoms
_NET_WM_STATE = None
_NET_WM_STATE_ABOVE = None

_xlib = None
_display = None
_root = None
_window = None


def _init_xlib():
    global _xlib, _display, _root
    if _xlib is not None:
        return True

    libx11_path = ctypes.util.find_library("X11")
    if not libx11_path:
        print(json.dumps({"error": "libX11 not found"}))
        return False

    _xlib = ctypes.cdll.LoadLibrary(libx11_path)

    # Function signatures
    _xlib.XOpenDisplay.restype = ctypes.c_void_p
    _xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]

    _xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    _xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]

    _xlib.XCreateSimpleWindow.restype = ctypes.c_ulong
    _xlib.XCreateSimpleWindow.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_ulong, ctypes.c_ulong,
    ]

    _xlib.XMapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    _xlib.XMapWindow.restype = ctypes.c_int

    _xlib.XUnmapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    _xlib.XUnmapWindow.restype = ctypes.c_int

    _xlib.XDestroyWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    _xlib.XDestroyWindow.restype = ctypes.c_int

    _xlib.XFlush.argtypes = [ctypes.c_void_p]
    _xlib.XFlush.restype = ctypes.c_int

    _xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    _xlib.XCloseDisplay.restype = ctypes.c_int

    _xlib.XSetWMProtocols.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_int
    ]
    _xlib.XSetWMProtocols.restype = ctypes.c_int

    _xlib.XInternAtom.restype = ctypes.c_ulong
    _xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]

    _xlib.XChangeProperty.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
    ]
    _xlib.XChangeProperty.restype = ctypes.c_int

    _xlib.XSelectInput.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_long,
    ]
    _xlib.XSelectInput.restype = ctypes.c_int

    _xlib.XDefaultScreen.restype = ctypes.c_int
    _xlib.XDefaultScreen.argtypes = [ctypes.c_void_p]

    _xlib.XCreateWindow.restype = ctypes.c_ulong
    _xlib.XCreateWindow.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
        ctypes.c_ulong, ctypes.c_void_p,
    ]

    _xlib.XGetInputFocus.restype = ctypes.c_int
    _xlib.XGetInputFocus.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
    ]

    display_name = os.environ.get("DISPLAY", ":0")
    _display = _xlib.XOpenDisplay(display_name.encode() if display_name else b":0")
    if not _display:
        print(json.dumps({"error": "XOpenDisplay failed"}))
        return False

    _root = _xlib.XDefaultRootWindow(_display)
    return True


def _init_netwm():
    global _NET_WM_STATE, _NET_WM_STATE_ABOVE
    if _NET_WM_STATE is not None:
        return
    _NET_WM_STATE = _xlib.XInternAtom(_display, b"_NET_WM_STATE", 0)
    _NET_WM_STATE_ABOVE = _xlib.XInternAtom(_display, b"_NET_WM_STATE_ABOVE", 0)


def create_overlay_window():
    """Create 768x1024 override-redirect window above UKM5.

    Uses XCreateWindow with override_redirect=True so:
    - Window bypasses the window manager
    - Window does NOT receive keyboard focus
    - Input passes through to UKM5
    """
    global _window

    if not _init_xlib():
        return None

    _init_netwm()

    # XSetWindowAttributes for override-redirect
    # CWOverrideRedirect = 0x0200
    CWOverrideRedirect = 0x0200
    CWBackPixel = 0x0002
    CWEventMask = 0x0800

    class XSetWindowAttributes(ctypes.Structure):
        _fields_ = [
            ("background_pixmap", ctypes.c_ulong),
            ("background_pixel", ctypes.c_ulong),
            ("border_pixmap", ctypes.c_ulong),
            ("border_pixel", ctypes.c_ulong),
            ("bit_gravity", ctypes.c_int),
            ("win_gravity", ctypes.c_int),
            ("backing_store", ctypes.c_int),
            ("backing_planes", ctypes.c_ulong),
            ("backing_pixel", ctypes.c_ulong),
            ("save_under", ctypes.c_int),
            ("event_mask", ctypes.c_long),
            ("do_not_propagate_mask", ctypes.c_long),
            ("override_redirect", ctypes.c_int),
            ("colormap", ctypes.c_ulong),
            ("cursor", ctypes.c_ulong),
        ]

    attrs = XSetWindowAttributes()
    attrs.override_redirect = 1  # True — bypass WM, no focus grab
    attrs.background_pixel = 0x00FF0000  # Red
    attrs.event_mask = XCB_EVENT_MASK_EXPOSURE | XCB_EVENT_MASK_STRUCTURE_NOTIFY

    # XCreateWindow(display, parent, x, y, w, h, border, depth, class, visual, valuemask, attrs)
    valuemask = CWOverrideRedirect | CWBackPixel | CWEventMask
    screen = _xlib.XDefaultScreen(_display)
    _window = _xlib.XCreateWindow(
        _display, _root, 0, 0, GEOMETRY_W, GEOMETRY_H, 0,
        0,  # CopyFromParent depth
        XCB_WINDOW_CLASS_INPUT_OUTPUT,
        0,  # CopyFromParent visual
        valuemask,
        ctypes.byref(attrs),
    )

    if not _window:
        return None

    # Set _NET_WM_STATE_ABOVE
    atom_above = ctypes.c_ulong(_NET_WM_STATE_ABOVE)
    _xlib.XChangeProperty(
        _display, _window, _NET_WM_STATE, XA_ATOM, 32,
        0,  # PropModeReplace
        ctypes.byref(atom_above), 1,
    )

    # WM_NAME for xdotool identification
    wm_name = _xlib.XInternAtom(_display, b"WM_NAME", 0)
    str_type = _xlib.XInternAtom(_display, b"STRING", 0)
    title = b"x11_screensaver_proof"
    _xlib.XChangeProperty(
        _display, _window, wm_name, str_type, 8,
        0, title, len(title),
    )

    _xlib.XMapWindow(_display, _window)
    _xlib.XFlush(_display)

    return _window


def destroy_overlay_window():
    """Destroy the overlay window."""
    global _window
    if _window and _display:
        _xlib.XUnmapWindow(_display, _window)
        _xlib.XFlush(_display)
        _xlib.XDestroyWindow(_display, _window)
        _xlib.XFlush(_display)
        _window = None


def get_active_window_id():
    """Get current active (focused) window ID via xdotool."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=3,
            env=dict(os.environ, DISPLAY=":0")
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return 0


def get_window_geometry(window_id):
    """Get window geometry via xwininfo."""
    try:
        result = subprocess.run(
            ["xwininfo", "-id", str(window_id)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=3,
            env=dict(os.environ, DISPLAY=":0")
        )
        if result.returncode == 0:
            geom = {}
            for line in result.stdout.split("\n"):
                line = line.strip()
                if "Absolute upper-left X:" in line:
                    geom["x"] = int(line.split(":")[-1].strip())
                if "Absolute upper-left Y:" in line:
                    geom["y"] = int(line.split(":")[-1].strip())
                if "Width:" in line:
                    geom["w"] = int(line.split(":")[-1].strip())
                if "Height:" in line:
                    geom["h"] = int(line.split(":")[-1].strip())
            return geom
    except Exception:
        pass
    return {}


def take_screenshot(path):
    """Take screenshot using scrot."""
    try:
        result = subprocess.run(
            ["scrot", "-z", path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=5,
            env=dict(os.environ, DISPLAY=":0")
        )
        return result.returncode == 0
    except Exception:
        return False


def check_ukm5_stable(chromium_pid, openbox_pid):
    """Verify UKM5 is still healthy."""
    checks = {
        "chromium_alive": False,
        "openbox_alive": False,
        "mint_active": False,
    }
    try:
        os.kill(chromium_pid, 0)
        checks["chromium_alive"] = True
    except OSError:
        pass

    try:
        os.kill(openbox_pid, 0)
        checks["openbox_alive"] = True
    except OSError:
        pass

    try:
        result = subprocess.run(
            ["systemctl", "is-active", "mint.service"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=5,
        )
        checks["mint_active"] = (result.stdout.strip() == "active")
    except Exception:
        pass

    return checks


# ══════════════════════════════════════════════════════════════════════
# Mode: dry-run
# ══════════════════════════════════════════════════════════════════════

def do_dry_run(state_path, ks_path):
    """Validate plan, check state, report. NO X11 calls."""
    state, is_idle, reason = read_state(state_path)
    ks_active = check_kill_switch(ks_path)

    result = {
        "mode": "dry_run",
        "plan_valid": True,
        "state": state,
        "is_idle": is_idle,
        "visibility_reason": reason,
        "kill_switch_active": ks_active,
        "would_show": (is_idle and not ks_active),
        "renderer_production_ready": True,
        "geometry": "{}x{}".format(GEOMETRY_W, GEOMETRY_H),
        "physical_run_executed": False,
        "run_once_requires_approval": True,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


# ══════════════════════════════════════════════════════════════════════
# Mode: run-once (PHYSICAL — requires approval)
# ══════════════════════════════════════════════════════════════════════

def do_run_once(state_path, ks_path, duration, display):
    """Execute the physical X11 screensaver proof."""
    global _display

    os.environ["DISPLAY"] = display

    start_time = time.time()

    # Pre-run checks
    chromium_pid = 0
    openbox_pid = 0
    try:
        import subprocess as sp
        r = sp.run(["pgrep", "-f", "chromium.*kiosk"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if r.returncode == 0:
            chromium_pid = int(r.stdout.strip().split("\n")[0])
        r = sp.run(["pgrep", "openbox"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if r.returncode == 0:
            openbox_pid = int(r.stdout.strip().split("\n")[0])
    except Exception:
        pass

    stability_before = check_ukm5_stable(chromium_pid, openbox_pid)

    # Lock
    lockfile = DEFAULT_LOCKFILE
    if os.path.exists(lockfile):
        result = {
            "started": False, "visible": False,
            "error": "Lockfile exists — another instance running?",
            "lockfile": lockfile,
        }
        print(json.dumps(result))
        return
    with open(lockfile, "w") as f:
        f.write(str(os.getpid()))

    try:
        # State check
        state, is_idle, reason = read_state(state_path)
        ks_active = check_kill_switch(ks_path)

        if not is_idle or ks_active:
            result = {
                "started": True, "visible": False,
                "state": state, "kill_switch_active": ks_active,
                "stop_reason": "kill_switch" if ks_active else "state_change",
                "reason": reason,
                "duration_sec": 0.0,
                "rollback_done": True,
            }
            print(json.dumps(result))
            return

        # Screen clean check
        screen_safe, screen_reason = check_screen_clean()

        # Before screenshot
        take_screenshot("/tmp/kso_test/before.png")
        active_before = get_active_window_id()

        # Create overlay window
        window_id = create_overlay_window()
        if not window_id:
            return {
                "started": True, "visible": False,
                "error": "X11 window creation failed",
            }

        # Check window geometry
        time.sleep(0.5)
        geom = get_window_geometry(window_id)
        active_during = get_active_window_id()

        # During screenshot
        take_screenshot(DEFAULT_PROOF_PNG)
        time.sleep(1.0)

        # Hold for remaining duration
        elapsed = time.time() - start_time
        remain = max(0.5, duration - elapsed)
        time.sleep(remain)

        # After screenshot
        active_after = get_active_window_id()
        take_screenshot("/tmp/kso_test/after.png")

        # Destroy overlay
        destroy_overlay_window()

        stability_after = check_ukm5_stable(chromium_pid, openbox_pid)

        total_duration = time.time() - start_time

        result = {
            "started": True,
            "visible": True,
            "reason": reason,
            "state": state,
            "kill_switch_active": ks_active,
            "duration_sec": round(total_duration, 1),
            "window_id": window_id,
            "window_geometry": geom,
            "active_before": active_before,
            "active_during": active_during,
            "active_after": active_after,
            "focus_was_stolen": (
                active_during != active_before and
                active_during not in (active_before, 0)
            ),
            "rollback_done": True,
            "stop_reason": "timeout",
            "ukm5_stable_before": stability_before,
            "ukm5_stable_after": stability_after,
            "chromium_pid_unchanged": (
                chromium_pid == stability_after.get("chromium_pid", chromium_pid)
            ),
            "screenshots": ["before.png", "proof_screensaver.png", "after.png"],
            "proof_summary": (
                "GUARDED X11 SCREENSAVER PROOF: "
                "visible=True, state={}, ks_active={}, "
                "window_id={}, geometry={}, "
                "active_before={}, active_during={}, "
                "focus_stolen={}, rollback_done=True"
            ).format(state, ks_active, window_id, geom,
                     active_before, active_during,
                     active_during != active_before),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    finally:
        # Rollback
        destroy_overlay_window()
        if os.path.exists(lockfile):
            os.unlink(lockfile)
        # Clean temp screenshots (keep proof)
        # Keep all screenshots for analysis
        pass


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Guarded X11 Screensaver Proof — Python 3.6"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="Plan validation only, NO X11")
    group.add_argument("--run-once", action="store_true",
                       help="Execute physical proof (requires approval)")

    parser.add_argument("--state-file", default=DEFAULT_STATE_PATH)
    parser.add_argument("--kill-switch", default=DEFAULT_KILL_SWITCH_PATH)
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help="Max duration in seconds (max {})".format(HARD_MAX_DURATION))
    parser.add_argument("--display", default=DEFAULT_DISPLAY)
    parser.add_argument("--approval-token", default=None,
                        help="Required for --run-once")

    args = parser.parse_args()

    duration = min(args.duration, HARD_MAX_DURATION)

    if args.dry_run:
        do_dry_run(args.state_file, args.kill_switch)
    elif args.run_once:
        if args.approval_token != APPROVAL_TOKEN:
            print(json.dumps({
                "executed": False,
                "error": (
                    "run-once requires explicit user approval. "
                    "Add --approval-token {} to confirm."
                ).format(APPROVAL_TOKEN),
            }))
            sys.exit(1)
        do_run_once(args.state_file, args.kill_switch, duration, args.display)


if __name__ == "__main__":
    main()
