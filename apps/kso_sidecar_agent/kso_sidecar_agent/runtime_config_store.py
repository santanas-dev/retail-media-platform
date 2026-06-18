"""Runtime Config Local Store for KSO Sidecar Agent.

Saves effective runtime config to config/runtime_config.json atomically.
Validates no forbidden keys/values (secrets, paths, tokens).

Does NOT call backend — only reads/writes local file.
Does NOT store tokens, JWTs, Authorization headers, or secrets.
"""

import re as _re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from kso_sidecar_agent.atomic_io import atomic_write_json, read_json
from kso_sidecar_agent.paths import RUNTIME_CONFIG_FILE

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_CONFIG_SUBSTRINGS = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
]

# Fields that MUST be present
REQUIRED_FIELDS = frozenset({"config_hash", "config", "fetched_at"})


def _validate_no_forbidden(data: dict, path: str = "") -> None:
    """Recursively check keys and string values for forbidden substrings."""
    if not isinstance(data, dict):
        return

    for key, value in data.items():
        full_key = f"{path}.{key}" if path else key

        # Check key
        lower_key = key.lower()
        for forbidden in FORBIDDEN_CONFIG_SUBSTRINGS:
            if forbidden in lower_key:
                raise ValueError(
                    f"runtime config key '{full_key}' contains forbidden substring '{forbidden}'"
                )

        # Check string values
        if isinstance(value, str):
            lower_val = value.lower()
            for forbidden in FORBIDDEN_CONFIG_SUBSTRINGS:
                if forbidden in lower_val:
                    raise ValueError(
                        f"runtime config value at '{full_key}' contains forbidden substring '{forbidden}'"
                    )

        # Recurse into nested dicts
        if isinstance(value, dict):
            _validate_no_forbidden(value, full_key)


# ══════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════

def validate_runtime_config_file(data: dict) -> dict:
    """Validate runtime_config.json content. Returns normalized dict or raises.

    Checks:
      - Required fields present (config_hash, config, fetched_at)
      - config_hash is non-empty string
      - config is a dict
      - fetched_at is non-empty string
      - No forbidden substrings in keys or string values
    """
    if not isinstance(data, dict):
        raise ValueError("runtime config must be a JSON object")

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            raise ValueError(f"runtime config missing required field '{field}'")

    config_hash = data.get("config_hash")
    if not isinstance(config_hash, str) or not config_hash.strip():
        raise ValueError("config_hash must be a non-empty string")

    config = data.get("config")
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")

    fetched_at = data.get("fetched_at")
    if not isinstance(fetched_at, str) or not fetched_at.strip():
        raise ValueError("fetched_at must be a non-empty string")

    # Optional fields
    etag = data.get("etag")
    if etag is not None and not isinstance(etag, str):
        raise ValueError("etag must be a string if present")

    generated_at = data.get("generated_at")
    if generated_at is not None and not isinstance(generated_at, str):
        raise ValueError("generated_at must be a string if present")

    # Forbidden substrings
    _validate_no_forbidden(data)

    return {
        "config_hash": config_hash,
        "etag": etag,
        "generated_at": generated_at,
        "fetched_at": fetched_at,
        "config": config,
    }


# ══════════════════════════════════════════════════════════════════════
# Read / Write
# ══════════════════════════════════════════════════════════════════════

def write_runtime_config(
    root: str | Path,
    snapshot: Any,  # RuntimeConfigSnapshot
    now: Optional[float] = None,
) -> dict:
    """Write runtime config from a RuntimeConfigSnapshot to disk atomically.

    If snapshot.not_modified=True:
      - If local file exists → leave unchanged, return status.
      - If local file missing → raise FileNotFoundError (can't create from nothing).

    If snapshot is updated:
      - Validate config has no forbidden keys/values.
      - Write atomically to config/runtime_config.json.

    Returns a status dict with {written, config_hash, ...}.
    Never writes tokens, secrets, or forbidden values.
    """
    root = Path(root)
    path = root / RUNTIME_CONFIG_FILE

    if snapshot.not_modified:
        if not path.exists():
            raise FileNotFoundError(
                f"Cannot write not_modified snapshot: {path} does not exist"
            )
        return {
            "written": False,
            "reason": "not_modified",
            "config_hash": snapshot.config_hash,
        }

    # Extract data from snapshot
    fetched_at_str = (
        datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
        if now
        else datetime.now(timezone.utc).isoformat()
    )

    data = {
        "config_hash": snapshot.config_hash or "",
        "etag": snapshot.etag,
        "generated_at": snapshot.generated_at,
        "fetched_at": fetched_at_str,
        "config": snapshot.config or {},
    }

    # Validate
    validated = validate_runtime_config_file(data)

    # Ensure parent dir exists
    if not path.parent.is_dir():
        raise FileNotFoundError(
            f"Agent root not initialized: {root}.\n"
            f"Run 'init-local-root --root {root}' first."
        )

    if path.is_symlink():
        raise ValueError(f"Refusing to write to symlink: {path}")

    atomic_write_json(path, validated)

    return {
        "written": True,
        "config_hash": validated["config_hash"],
        "fetched_at": validated["fetched_at"],
    }


def read_runtime_config(root: str | Path) -> dict:
    """Read and validate runtime_config.json. Raises FileNotFoundError if missing."""
    path = Path(root) / RUNTIME_CONFIG_FILE
    data = read_json(path)
    return validate_runtime_config_file(data)


# ══════════════════════════════════════════════════════════════════════
# Status
# ══════════════════════════════════════════════════════════════════════

def runtime_config_status(root: str | Path) -> dict:
    """Return safe summary of runtime_config.json. Never returns full config or secrets."""
    path = Path(root) / RUNTIME_CONFIG_FILE

    if not path.exists():
        return {"present": False, "ok": False, "error": "MISSING"}

    try:
        data = read_json(path)
        validated = validate_runtime_config_file(data)
    except (ValueError, FileNotFoundError) as e:
        return {"present": True, "ok": False, "error": str(e)}

    config = validated.get("config", {})
    return {
        "present": True,
        "ok": True,
        "config_hash": validated["config_hash"],
        "etag_present": validated.get("etag") is not None,
        "generated_at": validated.get("generated_at"),
        "fetched_at": validated["fetched_at"],
        "config_keys_count": len(config),
    }
