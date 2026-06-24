#!/usr/bin/env python3
"""Visual Proof Harness — automated overlay visibility verification.

Python 3.6+ standalone. NO dataclasses, NO kso_player imports.

Pipeline:
    1. scrot BEFORE
    2. Launch Chromium --app (checked: NO forbidden flags)
    3. xwininfo -root -tree → find new window
    4. xdotool search → window ID + geometry
    5. windowraise (safe, single window)
    6. scrot DURING
    7. Kill overlay (targeted, NOT pkill chromium)
    8. scrot AFTER
    9. Safe JSON summary

Output NEVER contains: secrets, tokens, backend URLs, checks, payments,
fiscal data, PII, UKM5 DB references.
"""

import argparse
import json
import os
import subprocess
import sys
import time

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

PROFILE_CODE = "portrait_idle_overlay_768"
WINDOW_X = 0
WINDOW_Y = 400
WINDOW_W = 768
WINDOW_H = 240
ROOT_W = 768
ROOT_H = 1024

# Payment zone bottom edge
PAYMENT_Y_START = 720
# Header zone bottom edge
HEADER_Y_END = 60

# Unique title for xdotool search
OVERLAY_TITLE = "VISUAL_PROOF_OVERLAY"

# Chromium flags that MUST NOT appear
FORBIDDEN_FLAGS = frozenset({
    "--kiosk",
    "--fullscreen",
    "--start-fullscreen",
    "--start-maximized",
})

# Forbidden substrings in output (case-insensitive)
FORBIDDEN_OUTPUT = (
    "receipt", "transaction", "payment", "fiscal",
    "customer", "card", "pan", "phone", "email",
    "cashier", "secret", "token", "password", "api_key",
    "backend_url", "file_path", "filesystem_path",
    "ukm5", "mysql", "redis",
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def run(cmd, timeout=10):
    """Run command, return (stdout, stderr, returncode). Safe — no shell=True."""
    try:
        p = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, text=True
        )
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except (subprocess.TimeoutExpired, OSError, ValueError) as e:
        return "", str(e), -1


def has_forbidden_substrings(text):
    """Check output for forbidden substrings (case-insensitive)."""
    if not text:
        return False
    lower = text.lower()
    for pat in FORBIDDEN_OUTPUT:
        if pat in lower:
            return True
    return False


def sanitize_output(data):
    """Recursively sanitize dict — reject any value with forbidden substrings."""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            sv = str(v)
            if has_forbidden_substrings(sv):
                return {"_error": "forbidden_content_in_value", "_key": str(k)}
            result[k] = sanitize_output(v)
        return result
    if isinstance(data, list):
        return [sanitize_output(item) for item in data]
    return data


# ══════════════════════════════════════════════════════════════════════
# Chromium command builder
# ══════════════════════════════════════════════════════════════════════

def build_chromium_cmd(html_path, user_data_dir, display=":0"):
    """Build Chromium --app command. Returns (cmd_list, errors list).

    VERIFIES: NO --kiosk, --fullscreen, --start-fullscreen, --start-maximized.
    """
    errors = []

    cmd = [
        "chromium-browser",
        "--app=file://{}".format(html_path),
        "--window-position={},{}".format(WINDOW_X, WINDOW_Y),
        "--window-size={},{}".format(WINDOW_W, WINDOW_H),
        "--disable-features=DialMediaRouteProvider",
        "--disable-translate",
        "--disable-save-password-bubble",
        "--no-first-run",
        "--disable-session-crashed-bubble",
        "--noerrdialogs",
        "--disable-infobars",
        "--disable-component-update",
        "--test-type",
        "--user-data-dir={}".format(user_data_dir),
    ]

    # Verify NO forbidden flags
    for flag in FORBIDDEN_FLAGS:
        if flag in cmd:
            errors.append("FORBIDDEN_FLAG_FOUND: {}".format(flag))

    # Verify geometry
    pos_found = any("--window-position" in arg for arg in cmd)
    size_found = any("--window-size" in arg for arg in cmd)
    if not pos_found:
        errors.append("MISSING: --window-position")
    if not size_found:
        errors.append("MISSING: --window-size")

    # Wrap with DISPLAY
    full_cmd = ["env", "DISPLAY={}".format(display)] + cmd

    return full_cmd, errors


# ══════════════════════════════════════════════════════════════════════
# Overlay HTML builder (safe, static, no external URLs)
# ══════════════════════════════════════════════════════════════════════

def build_overlay_html(path):
    """Write a bright test overlay HTML with unique title."""
    html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ margin:0; padding:0; background:#ff3366; color:#fff;
         width:{w}px; height:{h}px; overflow:hidden;
         display:flex; align-items:center; justify-content:center;
         font-family:Arial,sans-serif; }}
  .box {{ text-align:center; padding:20px; }}
  .title {{ font-size:32px; font-weight:bold; }}
  .sub {{ font-size:18px; margin-top:8px; opacity:0.9; }}
</style></head>
<body><div class="box">
  <div class="title">RED Visual Proof - Zone C</div>
  <div class="sub">y={y}-{ybot} | {w}x{h} | bright red bg</div>
</div></body>
</html>""".format(
        title=OVERLAY_TITLE,
        w=WINDOW_W, h=WINDOW_H,
        y=WINDOW_Y, ybot=WINDOW_Y + WINDOW_H,
    )

    with open(path, 'w') as f:
        f.write(html)
    return path


# ══════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════

def run_visual_proof(screenshot_dir="/tmp/kso_test", display=":0"):
    """Run the full visual proof pipeline. Returns safe dict result.

    Pipeline:
        1. Build overlay HTML + Chromium command
        2. Check forbidden flags
        3. scrot BEFORE
        4. Capture windows BEFORE
        5. Launch Chromium --app
        6. Wait for render
        7. xwininfo + xdotool → find overlay window
        8. windowraise if found
        9. scrot DURING
        10. Kill overlay (targeted)
        11. scrot AFTER
        12. Safe JSON summary
    """

    result = {
        "harness": "visual_proof",
        "profile_code": PROFILE_CODE,
        "window_geometry": {
            "x": WINDOW_X, "y": WINDOW_Y,
            "w": WINDOW_W, "h": WINDOW_H,
            "root": "{}x{}".format(ROOT_W, ROOT_H),
        },
        "forbidden_flags_check": None,
        "overlay_pid": None,
        "overlay_alive": False,
        "window_found": False,
        "window_id": None,
        "window_geometry_actual": None,
        "window_overlaps_payment": None,
        "window_overlaps_header": None,
        "windowraise_attempted": False,
        "screenshot_before": None,
        "screenshot_during": None,
        "screenshot_after": None,
        "overlay_killed": False,
        "errors": [],
        "visual_confirmed": False,
    }

    os.makedirs(screenshot_dir, exist_ok=True)

    # ── Step 1: Build overlay HTML ───────────────────────────────
    html_path = os.path.join(screenshot_dir, "overlay.html")
    build_overlay_html(html_path)

    # ── Step 2: Build + check command ────────────────────────────
    user_data_dir = os.path.join(screenshot_dir, "chromium-proof")
    cmd, flag_errors = build_chromium_cmd(html_path, user_data_dir, display)
    result["forbidden_flags_check"] = "ok" if not flag_errors else "FAIL"
    result["errors"].extend(flag_errors)

    if flag_errors:
        return result  # Do NOT launch if forbidden flags found

    # ── Step 3: scrot BEFORE ─────────────────────────────────────
    before_path = os.path.join(screenshot_dir, "before.png")
    _, _, rc = run(["scrot", before_path], timeout=10)
    if rc == 0:
        # Check screenshot doesn't contain forbidden content
        # (we can't inspect PNG content, but path is safe)
        result["screenshot_before"] = before_path

    # ── Step 4: Capture windows BEFORE ───────────────────────────
    stdout, _, _ = run(["xwininfo", "-root", "-tree"], timeout=5)
    before_windows = stdout

    stdout, _, _ = run(["xdotool", "search", "--class", "Chromium"], timeout=5)
    before_wids = set(stdout.split()) if stdout else set()

    # ── Step 5: Launch Chromium ──────────────────────────────────
    try:
        with open(os.path.join(screenshot_dir, "overlay.log"), 'w') as log_f:
            proc = subprocess.Popen(
                cmd, stdout=log_f, stderr=subprocess.STDOUT,
                preexec_fn=os.setpgrp  # Detach from terminal
            )
        result["overlay_pid"] = proc.pid
    except (OSError, ValueError) as e:
        result["errors"].append("LAUNCH_FAILED: {}".format(str(e)))
        return result

    # ── Step 6: Wait for render ──────────────────────────────────
    time.sleep(4)

    # Check alive
    try:
        os.kill(proc.pid, 0)
        result["overlay_alive"] = True
    except (OSError, ProcessLookupError):
        result["overlay_alive"] = False
        result["errors"].append("OVERLAY_DIED_BEFORE_CHECK")

    # ── Step 7: Find overlay window ──────────────────────────────
    if result["overlay_alive"]:
        # xdotool search by title
        stdout, _, _ = run(
            ["xdotool", "search", "--name", OVERLAY_TITLE], timeout=5
        )
        found_wids = [w for w in stdout.split() if w] if stdout else []

        if found_wids:
            result["window_found"] = True
            wid = found_wids[0]
            result["window_id"] = wid

            # xwininfo geometry
            stdout, _, _ = run(["xwininfo", "-id", wid], timeout=5)
            if stdout:
                geom = _parse_xwininfo(stdout)
                result["window_geometry_actual"] = geom

                # Check overlaps
                if geom:
                    wy = geom.get("absolute_y", 0)
                    wh = geom.get("height", 0)
                    result["window_overlaps_payment"] = (wy + wh) > PAYMENT_Y_START
                    result["window_overlaps_header"] = wy < HEADER_Y_END
        else:
            # Fallback: search by PID
            stdout, _, _ = run(
                ["xdotool", "search", "--pid", str(proc.pid)], timeout=5
            )
            pid_wids = [w for w in stdout.split() if w] if stdout else []
            if pid_wids:
                # Filter: window NOT in before_wids
                new_wids = [w for w in pid_wids if w not in before_wids]
                if new_wids:
                    result["window_found"] = True
                    result["window_id"] = new_wids[0]
                    result["errors"].append(
                        "WINDOW_FOUND_BY_PID_NOT_TITLE"
                    )

    # ── Step 8: windowraise (safe, single window) ────────────────
    if result["window_found"] and result["window_id"]:
        result["windowraise_attempted"] = True
        run(["xdotool", "windowraise", result["window_id"]], timeout=3)
        time.sleep(0.5)

    # ── Step 9: scrot DURING ─────────────────────────────────────
    during_path = os.path.join(screenshot_dir, "overlay-proof.png")
    _, _, rc = run(["scrot", during_path], timeout=10)
    if rc == 0:
        result["screenshot_during"] = during_path

    # ── Step 10: Kill overlay (targeted) ─────────────────────────
    try:
        proc.terminate()
        time.sleep(1)
        try:
            os.kill(proc.pid, 0)
            proc.kill()  # Force if still alive
            time.sleep(1)
        except (OSError, ProcessLookupError):
            pass
        result["overlay_killed"] = True
    except (OSError, ProcessLookupError):
        result["overlay_killed"] = True  # Already dead

    # Verify NO chromium with overlay.html left
    stdout, _, _ = run(["pgrep", "-f", "chromium-browser.*overlay.html"], timeout=5)
    if stdout.strip():
        result["errors"].append("OVERLAY_NOT_CLEANED: residual process")

    # ── Step 11: scrot AFTER ─────────────────────────────────────
    after_path = os.path.join(screenshot_dir, "after.png")
    _, _, rc = run(["scrot", after_path], timeout=10)
    if rc == 0:
        result["screenshot_after"] = after_path

    # ── Step 12: Determine visual confirmation ───────────────────
    result["visual_confirmed"] = (
        result["overlay_alive"]
        and result["window_found"]
        and result["screenshot_during"] is not None
        and not result["window_overlaps_payment"]
        and not result["window_overlaps_header"]
        and result["overlay_killed"]
        and not result["errors"]
    )

    # ── Clean temp HTML ──────────────────────────────────────────
    try:
        os.remove(html_path)
    except OSError:
        pass

    return result


# ══════════════════════════════════════════════════════════════════════
# xwininfo parser
# ══════════════════════════════════════════════════════════════════════

def _parse_xwininfo(text):
    """Parse xwininfo output into simple dict. Safe — no forbidden fields."""
    result = {}
    for line in text.split('\n'):
        line = line.strip()
        if 'Absolute upper-left X:' in line:
            result['absolute_x'] = int(line.split(':')[-1].strip())
        elif 'Absolute upper-left Y:' in line:
            result['absolute_y'] = int(line.split(':')[-1].strip())
        elif 'Width:' in line and 'Depth' not in line:
            result['width'] = int(line.split(':')[-1].strip())
        elif 'Height:' in line and 'Depth' not in line:
            result['height'] = int(line.split(':')[-1].strip())
        elif 'Corners:' in line:
            result['corners'] = line.split(':', 1)[-1].strip()
    return result if result else None


# ══════════════════════════════════════════════════════════════════════
# Safe JSON output
# ══════════════════════════════════════════════════════════════════════

def safe_json_output(result):
    """Sanitize and serialize result as JSON. Rejects forbidden content."""
    safe = sanitize_output(result)
    return json.dumps(safe, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Visual Proof Harness — overlay visibility verification"
    )
    parser.add_argument(
        "--screenshot-dir",
        default="/tmp/kso_test",
        help="Directory for screenshots (default: /tmp/kso_test)",
    )
    parser.add_argument(
        "--display",
        default=":0",
        help="X11 display (default: :0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate command only, do NOT launch Chromium",
    )
    args = parser.parse_args()

    if args.dry_run:
        # Dry-run: validate command only
        html_path = os.path.join(args.screenshot_dir, "overlay.html")
        user_data_dir = os.path.join(args.screenshot_dir, "chromium-proof")
        cmd, errors = build_chromium_cmd(html_path, user_data_dir, args.display)

        # Build safe summary (do NOT include full command — it contains
        # Chromium flag names like "password" in --disable-save-password-bubble)
        dry_result = {
            "harness": "visual_proof",
            "mode": "dry_run",
            "command_valid": len(errors) == 0,
            "forbidden_flags_check": "ok" if not errors else "FAIL",
            "errors": errors,
            "flags_count": len(cmd),
            "has_window_position": any("--window-position" in a for a in cmd),
            "has_window_size": any("--window-size" in a for a in cmd),
            "no_forbidden_flags": all(f not in str(cmd) for f in ["--kiosk", "--fullscreen", "--start-fullscreen", "--start-maximized"]),
            "window_geometry": {
                "x": WINDOW_X, "y": WINDOW_Y,
                "w": WINDOW_W, "h": WINDOW_H,
            },
        }
        print(safe_json_output(dry_result))
        sys.exit(0 if not errors else 1)

    # Full run
    result = run_visual_proof(
        screenshot_dir=args.screenshot_dir,
        display=args.display,
    )
    print(safe_json_output(result))
    sys.exit(0 if result["visual_confirmed"] else 1)


if __name__ == "__main__":
    main()
