#!/usr/bin/env python3
"""KSO Portrait Overlay Smoke Test — Python 3.6 standalone.
NO dataclasses, NO datetime.fromisoformat, NO network, NO Chromium.
Safe IDLE-ONLY visibility pipeline:
    state.json → kill_switch → visibility → JSON report
MUST: Python >= 3.6 (tested on 3.6.9).
"""

import json
import os
import sys
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════
# Constants — hardcoded profile portrait_idle_overlay_768
# ══════════════════════════════════════════════════════════════════════

PROFILE_CODE = "portrait_idle_overlay_768"
PROFILE_NAME = "Portrait Idle Overlay 768x240"

# Window geometry
ROOT_WIDTH = 768
ROOT_HEIGHT = 1024
WINDOW_X = 0
WINDOW_Y = 400
WINDOW_W = 768
WINDOW_H = 240
CREATIVE_X = 0
CREATIVE_Y = 20
CREATIVE_W = 768
CREATIVE_H = 200

# Flags
WINDOW_TYPE = "overlay"
FULLSCREEN = False
KIOSK = False
ALWAYS_ON_TOP = True
NO_FOCUS_STEAL = True

# State constants
STATE_IDLE = "idle"
STATE_BUSY = "busy"
STATE_SCAN = "scan"
STATE_CART = "cart"
STATE_PAYMENT = "payment"
STATE_ERROR = "error"
STATE_OFFLINE = "offline"
STATE_UNKNOWN = "unknown"
STATE_STALE = "stale"

ALLOWED_STATES = {
    STATE_IDLE, STATE_BUSY, STATE_SCAN, STATE_CART,
    STATE_PAYMENT, STATE_ERROR, STATE_OFFLINE, STATE_UNKNOWN, STATE_STALE,
}

# Default paths
DEFAULT_STATE_PATH = "/tmp/kso_test/state.json"
DEFAULT_KILL_SWITCH_PATH = "/tmp/kso_test/kill_switch"

# Staleness threshold (ms)
STALE_AFTER_MS = 5000

# Forbidden keys — MUST NOT appear in state.json
FORBIDDEN_KEYS = {
    "receipt_id", "receipt_number", "transaction_id",
    "payment_amount", "payment_method", "fiscal_data", "fiscal_sign",
    "fiscal_document", "items", "total_amount", "total_quantity",
    "customer_name", "customer_id", "customer_phone", "customer_email",
    "card_number", "pan", "phone", "email",
    "first_name", "last_name", "full_name",
    "cashier_id", "cashier_name", "operator_id",
    "ukm5_db_host", "ukm5_db_port", "ukm5_db_user",
    "ukm5_db_password", "ukm5_db_name",
    "mysql_connection", "redis_connection", "connection_string", "dsn",
    "secret", "token", "password", "api_key",
    "backend_url", "backend_base_url",
    "local_path", "file_path", "filesystem_path", "absolute_path",
}

FORBIDDEN_PATTERNS = (
    "receipt", "transaction", "payment", "fiscal",
    "customer", "card", "pan", "phone", "email",
    "cashier", "operator", "ukm5", "mysql", "redis",
    "secret", "token", "password", "api_key",
    "backend_url", "file_path", "filesystem_path",
)

# ══════════════════════════════════════════════════════════════════════
# Timestamp parsing — Python 3.6 compatible (NO fromisoformat)
# ══════════════════════════════════════════════════════════════════════

def parse_iso_timestamp(ts_str):
    """Parse ISO-8601 timestamp string to datetime.
    
    Handles formats:
        - "2024-06-24T14:30:00Z"
        - "2024-06-24T14:30:00.573421Z"
        - "2024-06-24T14:30:00+00:00"
        - "2024-06-24T14:30:00.573421+00:00"
    
    Python 3.6 compatible — uses strptime, NOT fromisoformat.
    Returns naive UTC datetime or None on failure.
    """
    if not ts_str or not isinstance(ts_str, str):
        return None
    
    ts = ts_str.strip()
    
    # Strip timezone suffix
    if ts.endswith('Z'):
        ts = ts[:-1]
    elif '+' in ts[10:]:  # +00:00 offset
        ts = ts.rsplit('+', 1)[0]
    
    # Try with microseconds first
    if '.' in ts:
        try:
            return datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%f')
        except ValueError:
            pass
    
    # Try without microseconds
    try:
        return datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return None


def is_timestamp_stale(ts_str, stale_ms):
    """Return True if timestamp is older than stale_ms milliseconds."""
    ts = parse_iso_timestamp(ts_str)
    if ts is None:
        return True  # unparseable → treat as stale
    
    now = datetime.utcnow()
    delta = now - ts
    delta_ms = delta.total_seconds() * 1000
    return delta_ms > stale_ms


# ══════════════════════════════════════════════════════════════════════
# State reading
# ══════════════════════════════════════════════════════════════════════

def has_forbidden_fields(data):
    """Return True if dict contains any forbidden keys."""
    if not isinstance(data, dict):
        return False
    for key in data:
        key_s = str(key)
        if key_s in FORBIDDEN_KEYS:
            return True
        key_l = key_s.lower()
        for pat in FORBIDDEN_PATTERNS:
            if pat in key_l:
                return True
    return False


def read_state(path):
    """Read state.json, return safe dict with effective_state.
    
    Returns:
        dict with keys: state, effective_state, device_code, source, updated_at_utc
        On ANY error: returns unknown state.
    """
    unknown = {
        "state": STATE_UNKNOWN,
        "effective_state": STATE_UNKNOWN,
        "device_code": "unknown",
        "source": "observer",
        "updated_at_utc": "1970-01-01T00:00:00Z",
    }
    
    if not path or not isinstance(path, str):
        return unknown
    
    # Check file
    try:
        if not os.path.exists(path):
            return unknown
        if not os.path.isfile(path):
            return unknown
    except (OSError, IOError):
        return unknown
    
    # Read
    try:
        with open(path, 'r') as f:
            raw = f.read()
    except (OSError, IOError, UnicodeDecodeError):
        return unknown
    
    # Parse JSON
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return unknown
    
    if not isinstance(data, dict):
        return unknown
    
    # Check forbidden
    if has_forbidden_fields(data):
        return unknown
    
    # Extract safe fields
    state = str(data.get("state", STATE_UNKNOWN)).strip().lower()
    if state not in ALLOWED_STATES:
        state = STATE_UNKNOWN
    
    updated_at = str(data.get("updated_at_utc", "1970-01-01T00:00:00Z"))
    stale_ms = int(data.get("stale_after_ms", STALE_AFTER_MS))
    device_code = str(data.get("device_code", "unknown"))
    source = str(data.get("source", "observer"))
    
    # Determine effective state
    if state == STATE_UNKNOWN:
        effective = STATE_UNKNOWN
    elif is_timestamp_stale(updated_at, stale_ms):
        effective = STATE_STALE
    else:
        effective = state
    
    return {
        "state": state,
        "effective_state": effective,
        "device_code": device_code,
        "source": source,
        "updated_at_utc": updated_at,
    }


# ══════════════════════════════════════════════════════════════════════
# Kill switch
# ══════════════════════════════════════════════════════════════════════

def check_kill_switch(path):
    """Check kill-switch file. Fail-safe: errors → active (hidden)."""
    if not path or not isinstance(path, str):
        return True  # no path → fail-safe hidden
    
    try:
        return os.path.exists(path)
    except (OSError, IOError):
        return True  # error → fail-safe hidden


# ══════════════════════════════════════════════════════════════════════
# Visibility resolution
# ══════════════════════════════════════════════════════════════════════

def resolve_visibility(state_data, kill_switch_active):
    """Determine visibility: kill_switch > state != idle > idle.
    
    Returns: 'visible' or 'hidden'
    """
    if kill_switch_active:
        return "hidden"
    
    effective = state_data.get("effective_state", STATE_UNKNOWN)
    if effective == STATE_IDLE:
        return "visible"
    
    return "hidden"


def determine_reason(state_data, kill_switch_active, visible):
    """Return human-readable reason code."""
    if kill_switch_active:
        return "kill_switch_active"
    effective = state_data.get("effective_state", STATE_UNKNOWN)
    if visible == "visible":
        return "idle_visible"
    if effective == STATE_STALE:
        return "stale_hidden"
    if effective == STATE_UNKNOWN:
        return "unknown_hidden"
    return "state_hidden ({})".format(effective)


# ══════════════════════════════════════════════════════════════════════
# Main smoke runner
# ══════════════════════════════════════════════════════════════════════

def run_smoke(state_path=None, kill_switch_path=None):
    """Run full smoke pipeline, return dict result (safe JSON-able)."""
    
    if state_path is None:
        state_path = DEFAULT_STATE_PATH
    if kill_switch_path is None:
        kill_switch_path = DEFAULT_KILL_SWITCH_PATH
    
    # Phase 1: Read state
    state_data = read_state(state_path)
    
    # Phase 2: Check kill-switch
    ks_active = check_kill_switch(kill_switch_path)
    
    # Phase 3: Resolve visibility
    visible = resolve_visibility(state_data, ks_active)
    
    # Phase 4: Determine reason
    reason = determine_reason(state_data, ks_active, visible)
    
    return {
        "smoke_version": 2,
        "profile_code": PROFILE_CODE,
        "profile_name": PROFILE_NAME,
        "state": state_data["state"],
        "effective_state": state_data["effective_state"],
        "device_code": state_data["device_code"],
        "source": state_data["source"],
        "visible_plan": visible,
        "reason": reason,
        "kill_switch_active": ks_active,
        "window": {
            "root": "{}x{}".format(ROOT_WIDTH, ROOT_HEIGHT),
            "position": {"x": WINDOW_X, "y": WINDOW_Y},
            "size": "{}x{}".format(WINDOW_W, WINDOW_H),
        },
        "creative": {
            "position": {"x": CREATIVE_X, "y": CREATIVE_Y},
            "size": "{}x{}".format(CREATIVE_W, CREATIVE_H),
        },
        "flags": {
            "window_type": WINDOW_TYPE,
            "fullscreen": FULLSCREEN,
            "kiosk": KIOSK,
            "always_on_top": ALWAYS_ON_TOP,
            "no_focus_steal": NO_FOCUS_STEAL,
        },
    }


# ══════════════════════════════════════════════════════════════════════
# Test case generators (for dry smoke 6 cases)
# ══════════════════════════════════════════════════════════════════════

def write_idle_state(path):
    """Write a fresh idle state.json."""
    now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    data = {
        "schema_version": 1,
        "device_code": "a-05954",
        "state": "idle",
        "source": "smoke_test",
        "updated_at_utc": now,
        "stale_after_ms": STALE_AFTER_MS,
    }
    with open(path, 'w') as f:
        json.dump(data, f)


def write_busy_state(path):
    """Write a busy (scanning) state.json."""
    now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    data = {
        "schema_version": 1,
        "device_code": "a-05954",
        "state": "scan",
        "source": "smoke_test",
        "updated_at_utc": now,
        "stale_after_ms": STALE_AFTER_MS,
    }
    with open(path, 'w') as f:
        json.dump(data, f)


def write_stale_state(path):
    """Write a stale (old timestamp) state.json."""
    data = {
        "schema_version": 1,
        "device_code": "a-05954",
        "state": "idle",
        "source": "smoke_test",
        "updated_at_utc": "2020-01-01T00:00:00Z",
        "stale_after_ms": STALE_AFTER_MS,
    }
    with open(path, 'w') as f:
        json.dump(data, f)


def write_micros_state(path):
    """Write idle state with microseconds timestamp (the problematic format)."""
    # Python 3.6 strftime doesn't do %f directly in all builds,
    # so construct manually
    now = datetime.utcnow()
    ts = now.strftime('%Y-%m-%dT%H:%M:%S') + '.{:06d}Z'.format(now.microsecond)
    data = {
        "schema_version": 1,
        "device_code": "a-05954",
        "state": "idle",
        "source": "smoke_test",
        "updated_at_utc": ts,
        "stale_after_ms": STALE_AFTER_MS,
    }
    with open(path, 'w') as f:
        json.dump(data, f)


# ══════════════════════════════════════════════════════════════════════
# CLI / test runner
# ══════════════════════════════════════════════════════════════════════

def run_all_tests():
    """Run 6 dry smoke test cases. Returns list of result dicts."""
    results = []
    state_path = DEFAULT_STATE_PATH
    ks_path = DEFAULT_KILL_SWITCH_PATH
    
    # Ensure directory exists
    state_dir = os.path.dirname(state_path)
    if state_dir and not os.path.exists(state_dir):
        os.makedirs(state_dir)
    
    # Ensure clean start
    for p in [state_path, ks_path]:
        if os.path.exists(p):
            os.remove(p)
    
    def record(case_name, ks_file_exists=False):
        """Run smoke and record result."""
        if ks_file_exists and not os.path.exists(ks_path):
            open(ks_path, 'w').close()
        elif not ks_file_exists and os.path.exists(ks_path):
            os.remove(ks_path)
        
        result = run_smoke(state_path, ks_path)
        result["_case"] = case_name
        results.append(result)
        return result
    
    # Case 1: NO state file → unknown → hidden
    if os.path.exists(state_path):
        os.remove(state_path)
    record("1_no_state_file")
    
    # Case 2: idle state + no kill-switch → visible
    write_idle_state(state_path)
    record("2_idle_visible")
    
    # Case 3: idle state + kill-switch → hidden
    record("3_idle_kill_switch_hidden", ks_file_exists=True)
    
    # Case 4: busy (scan) state → hidden
    write_busy_state(state_path)
    record("4_busy_hidden")
    
    # Case 5: stale state → hidden
    write_stale_state(state_path)
    record("5_stale_hidden")
    
    # Case 6: idle + microseconds timestamp → visible
    write_micros_state(state_path)
    record("6_idle_micros_visible")
    
    # Cleanup
    if os.path.exists(ks_path):
        os.remove(ks_path)
    
    return results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="KSO Portrait Overlay Smoke Test (Python 3.6)"
    )
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_PATH,
        help="Path to state.json (default: {})".format(DEFAULT_STATE_PATH),
    )
    parser.add_argument(
        "--kill-switch",
        default=DEFAULT_KILL_SWITCH_PATH,
        help="Path to kill-switch flag (default: {})".format(DEFAULT_KILL_SWITCH_PATH),
    )
    parser.add_argument(
        "--test-all",
        action="store_true",
        help="Run all 6 dry smoke test cases",
    )
    parser.add_argument(
        "--write-idle",
        action="store_true",
        help="Write idle state.json and smoke",
    )
    
    args = parser.parse_args()
    
    if args.test_all:
        results = run_all_tests()
        print(json.dumps(results, indent=2, ensure_ascii=False))
        
        # Summary
        passed = sum(1 for r in results
                     if (r["_case"].startswith("1_") and r["visible_plan"] == "hidden") or
                        (r["_case"].startswith("2_") and r["visible_plan"] == "visible") or
                        (r["_case"].startswith("3_") and r["visible_plan"] == "hidden") or
                        (r["_case"].startswith("4_") and r["visible_plan"] == "hidden") or
                        (r["_case"].startswith("5_") and r["visible_plan"] == "hidden") or
                        (r["_case"].startswith("6_") and r["visible_plan"] == "visible"))
        print("\n{} / {} cases passed".format(passed, len(results)))
        sys.exit(0 if passed == 6 else 1)
    
    if args.write_idle:
        write_idle_state(args.state_file)
        print("Wrote idle state to {}".format(args.state_file))
    
    result = run_smoke(args.state_file, args.kill_switch)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["visible_plan"] == "visible" else 0)
