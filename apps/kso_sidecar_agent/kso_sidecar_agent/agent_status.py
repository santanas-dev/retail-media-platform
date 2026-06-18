"""Safe read/update of status/agent_status.json.

Strict validation: allowed statuses, bounds, forbidden substrings in errors.
Follows docs/kso_local_interface_contract.md.
"""

from datetime import datetime, timezone
from pathlib import Path

from kso_sidecar_agent.atomic_io import atomic_write_json, read_json
from kso_sidecar_agent.paths import AGENT_STATUS_FILE, AGENT_STATUS_TEMPLATE

# ── Allowed values ────────────────────────────────────────────────────

ALLOWED_STATUSES = frozenset({
    "stopped",
    "starting",
    "running",
    "warning",
    "error",
    "offline",
})

MAX_ERRORS = 20
MAX_ERROR_LENGTH = 200

FORBIDDEN_STATUS_SUBSTRINGS = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path",
]


# ── Validation ────────────────────────────────────────────────────────

def _validate_status(status: str) -> None:
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Allowed: {', '.join(sorted(ALLOWED_STATUSES))}"
        )


def _validate_errors(errors: list) -> list:
    """Validate and sanitize error list. Raises ValueError on forbidden content."""
    if not isinstance(errors, list):
        raise ValueError("'errors' must be a list of strings")

    cleaned = []
    for item in errors:
        if not isinstance(item, str):
            raise ValueError(f"Error entry must be a string, got {type(item).__name__}")
        if len(item) > MAX_ERROR_LENGTH:
            item = item[:MAX_ERROR_LENGTH]

        # Reject forbidden substrings
        lower = item.lower()
        for forbidden in FORBIDDEN_STATUS_SUBSTRINGS:
            if forbidden in lower:
                raise ValueError(
                    f"Error message contains forbidden substring '{forbidden}'"
                )

        cleaned.append(item)
        if len(cleaned) >= MAX_ERRORS:
            break

    return cleaned


# ── Public API ────────────────────────────────────────────────────────

def read_status(root: str | Path) -> dict:
    """Read and return agent_status.json as a dict."""
    root = Path(root)
    path = root / AGENT_STATUS_FILE
    return read_json(path)


def update_status(
    root: str | Path,
    *,
    status: str,
    offline_mode: bool = False,
    cached_items: int = 0,
    invalid_hash_items: int = 0,
    errors: list[str] | None = None,
) -> dict:
    """Atomically update agent_status.json.

    Validates all fields and writes via atomic_io.
    Returns the written data dict.
    """
    _validate_status(status)

    if cached_items < 0:
        raise ValueError(f"cached_items must be >= 0, got {cached_items}")
    if invalid_hash_items < 0:
        raise ValueError(f"invalid_hash_items must be >= 0, got {invalid_hash_items}")

    error_list = _validate_errors(errors or [])

    data = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "offline_mode": bool(offline_mode),
        "cached_items": int(cached_items),
        "invalid_hash_items": int(invalid_hash_items),
        "errors": error_list,
    }

    root = Path(root)
    path = root / AGENT_STATUS_FILE

    if not path.parent.is_dir():
        raise FileNotFoundError(
            f"Agent root not initialized: {root}.\n"
            f"Run 'init-local-root --root {root}' first."
        )

    if path.is_symlink():
        raise ValueError(f"Refusing to write to symlink: {path}")

    atomic_write_json(path, data)
    return data


def validate_status_file(root: str | Path) -> dict:
    """Validate an existing agent_status.json. Returns {"ok": True} or {"ok": False, "error": ...}."""
    root = Path(root)
    path = root / AGENT_STATUS_FILE

    if not path.exists():
        return {"ok": False, "error": "MISSING"}

    try:
        data = read_json(path)
    except (ValueError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"Invalid JSON: {e}"}  # noqa: json is imported below
    except OSError as e:
        return {"ok": False, "error": f"Cannot read: {e}"}

    if not isinstance(data, dict):
        return {"ok": False, "error": "Not a JSON object"}

    # Check required fields
    st = data.get("status")
    if st not in ALLOWED_STATUSES:
        return {"ok": False, "error": f"Invalid status: '{st}'"}

    for field in ("cached_items", "invalid_hash_items"):
        val = data.get(field, -1)
        if not isinstance(val, (int, float)) or val < 0:
            return {"ok": False, "error": f"Invalid {field}: {val}"}

    errs = data.get("errors", [])
    if not isinstance(errs, list):
        return {"ok": False, "error": "'errors' must be a list"}

    # Security scan on all string values
    all_text = str(data).lower()
    for forbidden in FORBIDDEN_STATUS_SUBSTRINGS:
        if forbidden in all_text:
            return {"ok": False, "error": f"Forbidden value '{forbidden}' in file"}

    return {"ok": True, "status": st}


# Needed for validate_status_file's json import
import json  # noqa: E402
