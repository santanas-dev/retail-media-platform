"""KSO UKM 4 State Adapter — atomic state writer.

Writes ONLY {root}/state/kso_state.json atomically.
Player reads this file (read-only).
"""

import json as _json
import os as _os
import tempfile as _tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from kso_state_adapter.state_model import (
    KsoState,
    STATE_UNKNOWN,
    validate_state_dict,
    FORBIDDEN_STATE_KEYS,
    FORBIDDEN_IN_STATE_VALUES,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATE_DIR = "state"
STATE_FILE = "kso_state.json"

STATUS_WRITTEN = "written"
STATUS_ERROR = "error"
STATUS_REJECTED = "rejected"


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def atomic_write_state(root, state: KsoState) -> dict:
    """Atomically write kso_state.json.

    Pipeline:
      1. Validate state model
      2. Validate no forbidden keys/values
      3. Serialize to JSON
      4. Write to tmp file
      5. fsync tmp
      6. rename tmp → kso_state.json
      7. fsync directory

    Args:
        root: Agent root path (str or Path).
        state: KsoState to write.

    Returns:
        dict: {"status": "written"|"error"|"rejected", "reason": str}
    """
    try:
        root = Path(root)
    except (TypeError, ValueError):
        return {"status": STATUS_ERROR, "reason": "invalid_root"}

    if not isinstance(state, KsoState):
        return {"status": STATUS_ERROR, "reason": "invalid_state"}

    # Validate state
    if state.state not in (
        "idle", "transaction", "payment", "receipt",
        "service", "error", "maintenance", "offline", "unknown",
    ):
        return {"status": STATUS_REJECTED, "reason": "invalid_state_value"}

    # Validate no forbidden data
    forbidden = state.validate_forbidden()
    if forbidden:
        return {"status": STATUS_REJECTED, "reason": forbidden}

    # Build dict
    data = state.to_dict()

    # Extra safety: no forbidden keys
    key_check = validate_state_dict(data)
    if key_check:
        return {"status": STATUS_REJECTED, "reason": key_check}

    # Serialize
    try:
        json_str = _json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return {"status": STATUS_ERROR, "reason": "serialization_failed"}

    state_dir = root / STATE_DIR
    state_path = state_dir / STATE_FILE

    try:
        state_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return {"status": STATUS_ERROR, "reason": "cannot_create_state_dir"}

    # Atomic write: tmp → rename
    try:
        fd, tmp_path = _tempfile.mkstemp(
            dir=str(state_dir),
            prefix="." + STATE_FILE + ".",
            suffix=".tmp",
        )
        try:
            _os.write(fd, json_str.encode("utf-8"))
            _os.fsync(fd)
        finally:
            _os.close(fd)

        _os.replace(tmp_path, str(state_path))

        # Fsync directory
        try:
            dir_fd = _os.open(str(state_dir), _os.O_RDONLY)
            _os.fsync(dir_fd)
            _os.close(dir_fd)
        except OSError:
            pass

        return {"status": STATUS_WRITTEN, "reason": "ok"}
    except OSError:
        return {"status": STATUS_ERROR, "reason": "write_failed"}


# ══════════════════════════════════════════════════════════════════════
# Safe formatter
# ══════════════════════════════════════════════════════════════════════

def format_write_result(result: dict) -> str:
    """Format write result safely. No paths, no raw data."""
    status = result.get("status", "unknown")
    reason = result.get("reason", "unknown")
    # Safety scan
    output = f"status: {status}\nreason: {reason}"
    lower = output.lower()
    for fb in FORBIDDEN_STATE_KEYS:
        if fb in lower:
            raise ValueError(f"Output contains forbidden key '{fb}'")
    return output
