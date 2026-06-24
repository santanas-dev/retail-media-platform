"""KSO Player Local Kill-Switch — file-flag based safety mechanism.

The kill-switch is a local file flag at /run/verny/kso/kill_switch.
When the file exists, the player overlay MUST hide/disable immediately.
This is the fastest safety path — no network, no DB, no UKM5 access.

Safety rules (fail-safe):
    - file EXISTS → kill-switch ACTIVE (player hides)
    - file does NOT exist → kill-switch INACTIVE (player may show)
    - ANY error reading (PermissionError, OSError, etc.) → ACTIVE
    - None/empty path → ACTIVE (safe default: don't trust bad config)

NO Chromium, NO X11, NO HTTP, NO backend, NO UKM5 DB.
"""

import os
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

DEFAULT_KILL_SWITCH_PATH = "/run/verny/kso/kill_switch"

# ══════════════════════════════════════════════════════════════════════
# Core function
# ══════════════════════════════════════════════════════════════════════


def is_kill_switch_active(
    path: Optional[str] = DEFAULT_KILL_SWITCH_PATH,
) -> bool:
    """Check whether the local kill-switch file flag is active.

    Args:
        path: Filesystem path to the kill-switch flag file.
              Default: /run/verny/kso/kill_switch.

    Returns:
        True if kill-switch is active (player MUST hide).
        False if kill-switch is inactive (player may show, subject to state).

    Safety rules:
        - path is None → True (bad config — fail safe)
        - path is empty string → True (bad config — fail safe)
        - file EXISTS → True
        - file does NOT exist → False
        - PermissionError / OSError / any IOError → True
        - Path is a directory → True (unexpected — fail safe)
    """
    # ── Validate path ──────────────────────────────────────────
    if path is None:
        return True  # bad config → safe default: hide

    if not isinstance(path, str) or path.strip() == "":
        return True  # bad config → safe default: hide

    # ── Check file existence ───────────────────────────────────
    try:
        if os.path.isfile(path):
            return True   # kill-switch file exists → ACTIVE
        else:
            return False  # no kill-switch file → INACTIVE
    except (PermissionError, OSError, IOError):
        # Any error reading the path → assume active (fail safe)
        return True
