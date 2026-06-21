"""KSO UKM 4 State Adapter — Safe file-based state source.

Reads a small status file from a path that MUST be within an allowed root.
Supports JSON {"state": "idle"} or plain text idle.
Rejects any file with forbidden data (checks, payments, cards, PII, fiscal).
"""

import json as _json
from pathlib import Path
from typing import List, Optional, Set

from kso_state_adapter.state_model import (
    KsoState,
    ALLOWED_STATES,
    STATE_UNKNOWN,
    STATE_ERROR,
    FORBIDDEN_STATE_KEYS,
    FORBIDDEN_IN_STATE_VALUES,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

DEFAULT_ALLOWED_ROOTS: List[Path] = [
    Path("/run/verny/kso"),
    Path("/var/lib/verny/kso"),
]

MAX_FILE_SIZE_BYTES = 1024

SAFE_JSON_KEYS: Set[str] = {
    "state",
    "updated_at_utc",
    "source",
    "schema_version",
}


class SafeStatusFileError(Exception):
    """Raised when file source encounters a safety violation."""
    pass


class FileRejectedError(SafeStatusFileError):
    """File was found but rejected due to forbidden content."""
    pass


class FileAccessError(SafeStatusFileError):
    """File could not be accessed (missing, outside roots, I/O error)."""
    pass


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

class SafeStatusFileSource:
    """Reads state from a safe status file.

    The file MUST:
    - Be within one of the allowed_root directories
    - Be ≤ MAX_FILE_SIZE_BYTES
    - Contain ONLY safe data (no checks, payments, cards, PII, fiscal)

    Supports two formats:
        Plain text: idle  (single word, lowercase, from ALLOWED_STATES)
        JSON:       {"state": "idle"}

    Only SAFE_JSON_KEYS are allowed in JSON mode.
    Extra keys → FileRejectedError.
    Forbidden keys/values → FileRejectedError.
    File missing/outside roots/too large → FileAccessError.
    """

    def __init__(
        self,
        file_path: Path,
        allowed_roots: Optional[List[Path]] = None,
        max_size: int = MAX_FILE_SIZE_BYTES,
    ):
        self._path = file_path.resolve()
        self._roots = [r.resolve() for r in (allowed_roots or DEFAULT_ALLOWED_ROOTS)]
        self._max_size = max_size
        self.call_count = 0

    def read_state(self) -> KsoState:
        """Read state from file. Raises SafeStatusFileError on any violation.

        Never returns idle for a broken/missing/invalid file.
        """
        self.call_count += 1

        # ── Path safety ────────────────────────────────────────────
        if not self._path.is_file():
            raise FileAccessError("status_file_not_found")

        in_root = False
        for root in self._roots:
            try:
                self._path.relative_to(root)
                in_root = True
                break
            except ValueError:
                pass
        if not in_root:
            raise FileAccessError("status_file_outside_allowed_roots")

        # ── Size safety ────────────────────────────────────────────
        try:
            size = self._path.stat().st_size
        except OSError as e:
            raise FileAccessError(f"stat_failed") from e

        if size > self._max_size:
            raise FileRejectedError("status_file_too_large")

        # ── Read ───────────────────────────────────────────────────
        try:
            raw = self._path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as e:
            raise FileAccessError("read_failed") from e

        if not raw:
            raise FileRejectedError("status_file_empty")

        # ── Safety scan: forbidden substrings in raw content ────────
        raw_lower = raw.lower()
        for fb in FORBIDDEN_STATE_KEYS:
            if fb in raw_lower:
                raise FileRejectedError(
                    f"forbidden_key_detected:{fb}")

        for fb in FORBIDDEN_IN_STATE_VALUES:
            # fb values are strings like "token", "secret", etc.
            # Skip short/collision-prone strings that appear in field names
            if len(fb) < 6:
                continue
            if fb in raw_lower:
                raise FileRejectedError(
                    f"forbidden_value_detected:{fb}")

        # ── Parse ──────────────────────────────────────────────────
        # Try JSON first, then plain text
        state_value = None

        # JSON mode: starts with '{'
        if raw.startswith("{"):
            state_value = self._parse_json(raw)
        else:
            # Plain text: single word
            state_value = self._parse_plain(raw)

        # ── Validate ───────────────────────────────────────────────
        if not state_value:
            raise FileRejectedError("state_value_empty")

        if state_value not in ALLOWED_STATES:
            raise FileRejectedError(
                f"invalid_state:{state_value}")

        return KsoState(state=state_value)

    def _parse_json(self, raw: str) -> Optional[str]:
        """Parse JSON status file. Only SAFE_JSON_KEYS allowed."""
        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError as e:
            raise FileRejectedError("invalid_json") from e

        if not isinstance(data, dict):
            raise FileRejectedError("json_root_not_object")

        # ── Extra keys → reject ────────────────────────────────────
        for key in data:
            if key not in SAFE_JSON_KEYS:
                raise FileRejectedError(
                    f"extra_json_key:{key}")

        # ── Extract state ──────────────────────────────────────────
        state = data.get("state")
        if state is None:
            raise FileRejectedError("json_missing_state_key")

        if not isinstance(state, str):
            raise FileRejectedError("json_state_not_string")

        return state.strip().lower()

    def _parse_plain(self, raw: str) -> Optional[str]:
        """Parse plain text status — single word."""
        # Must be a single word (no spaces, no newlines inside)
        if " " in raw or "\n" in raw:
            raise FileRejectedError("plain_text_not_single_word")
        return raw.lower()
