"""Local non-secret agent config store.

Manages config/agent_config.json:
  - backend_base_url (required, http/https only)
  - device_code (required, alphanumeric + ._-)
  - tls_verify (bool, default true)
  - request_timeout_sec (1-120, default 10)
  - local_interface_version ("1.0" only)

Strictly NO secrets: no device_secret, no JWT, no tokens, no passwords.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

from kso_sidecar_agent.atomic_io import atomic_write_json, read_json
from kso_sidecar_agent.paths import CONFIG_FILE

# ── Forbidden substrings ──────────────────────────────────────────────

FORBIDDEN_CONFIG_SUBSTRINGS = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path",
]

# ── Allowed values ────────────────────────────────────────────────────

ALLOWED_VERSIONS = frozenset({"1.0"})
DEVICE_CODE_RE = re.compile(r"^[a-zA-Z0-9._\-]{3,64}$")
FORBIDDEN_QUERY_PARAMS = {"token", "jwt", "password", "secret", "api_key",
                           "private_key", "key", "credential", "authorization"}


# ── Validation ────────────────────────────────────────────────────────

def _check_forbidden(value: str, field: str) -> None:
    """Raise ValueError if any forbidden substring found (case-insensitive)."""
    lower = value.lower()
    for forbidden in FORBIDDEN_CONFIG_SUBSTRINGS:
        if forbidden in lower:
            raise ValueError(
                f"Config field '{field}' contains forbidden substring '{forbidden}'"
            )


def _validate_backend_base_url(url: str) -> str:
    if not url or not isinstance(url, str):
        raise ValueError("backend_base_url is required")
    _check_forbidden(url, "backend_base_url")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"backend_base_url must be http:// or https://, got '{parsed.scheme}'"
        )
    if parsed.username or parsed.password:
        raise ValueError("backend_base_url must not contain username/password")
    if not parsed.hostname:
        raise ValueError("backend_base_url must contain a hostname")

    # Reject forbidden query parameters
    if parsed.query:
        from urllib.parse import parse_qs
        qs = parse_qs(parsed.query)
        for param in FORBIDDEN_QUERY_PARAMS:
            if param in qs:
                raise ValueError(
                    f"backend_base_url query contains forbidden param '{param}'"
                )

    return url


def _validate_device_code(code: str) -> str:
    if not code or not isinstance(code, str):
        raise ValueError("device_code is required")
    _check_forbidden(code, "device_code")
    if not DEVICE_CODE_RE.match(code):
        raise ValueError(
            f"device_code must be 3-64 chars of [a-zA-Z0-9._-], got '{code}'"
        )
    return code


def _validate_request_timeout_sec(val: int) -> int:
    if not isinstance(val, (int, float)):
        raise ValueError(f"request_timeout_sec must be int, got {type(val).__name__}")
    val = int(val)
    if val < 1 or val > 120:
        raise ValueError(f"request_timeout_sec must be 1-120, got {val}")
    return val


def _validate_version(version: str) -> str:
    if not isinstance(version, str):
        raise ValueError(f"local_interface_version must be a string")
    if version not in ALLOWED_VERSIONS:
        raise ValueError(
            f"local_interface_version must be one of {sorted(ALLOWED_VERSIONS)}, "
            f"got '{version}'"
        )
    return version


def validate_config(data: dict) -> dict:
    """Validate and return a normalized config dict. Raises ValueError on failure."""
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")

    return {
        "backend_base_url": _validate_backend_base_url(
            data.get("backend_base_url", "")
        ),
        "device_code": _validate_device_code(data.get("device_code", "")),
        "tls_verify": bool(data.get("tls_verify", True)),
        "request_timeout_sec": _validate_request_timeout_sec(
            data.get("request_timeout_sec", 10)
        ),
        "local_interface_version": _validate_version(
            data.get("local_interface_version", "1.0")
        ),
    }


# ── Public API ────────────────────────────────────────────────────────

def write_config(root: str | Path, data: dict) -> dict:
    """Validate and atomically write config/agent_config.json.

    Returns the validated/normalized config dict.
    """
    validated = validate_config(data)

    root = Path(root)
    config_path = root / CONFIG_FILE

    if not config_path.parent.is_dir():
        raise FileNotFoundError(
            f"Agent root not initialized: {root}.\n"
            f"Run 'init-local-root --root {root}' first."
        )

    if config_path.is_symlink():
        raise ValueError(f"Refusing to write to symlink: {config_path}")

    atomic_write_json(config_path, validated)
    return validated


def read_config(root: str | Path) -> dict:
    """Read and validate config/agent_config.json. Raises FileNotFoundError if missing."""
    root = Path(root)
    path = root / CONFIG_FILE
    data = read_json(path)
    return validate_config(data)


def config_status(root: str | Path) -> dict:
    """Return config health info. Does NOT raise on invalid config."""
    root = Path(root)
    path = root / CONFIG_FILE

    if not path.exists():
        return {"present": False, "ok": False, "error": "MISSING"}

    try:
        data = read_json(path)
        validated = validate_config(data)
    except (ValueError, FileNotFoundError) as e:
        return {"present": True, "ok": False, "error": str(e)}

    # Check for placeholder values
    placeholder_fields = _check_placeholder_values(validated)

    parsed = urlparse(validated["backend_base_url"])
    return {
        "present": True,
        "ok": True,
        "backend_scheme": parsed.scheme,
        "backend_host": parsed.hostname,
        "device_code": validated["device_code"],
        "tls_verify": validated["tls_verify"],
        "request_timeout_sec": validated["request_timeout_sec"],
        "local_interface_version": validated["local_interface_version"],
        "has_placeholders": len(placeholder_fields) > 0,
        "placeholder_fields": placeholder_fields,
    }


PLACEHOLDER_PATTERNS = [
    "<TEST_BACKEND_BASE_URL>",
    "<TEST_KSO_DEVICE_CODE>",
    "<DEVICE_SECRET_VALUE>",
    "<AGENT_ROOT>",
    "<REPLACE_ME>",
    "changeme",
    "placeholder",
]


def _check_placeholder_values(data: dict) -> list[str]:
    """Return list of field names that contain placeholder values."""
    placeholder_fields: list[str] = []
    for field in ("backend_base_url", "device_code"):
        val = data.get(field, "")
        val_lower = str(val).lower()
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.lower() in val_lower:
                placeholder_fields.append(field)
                break
    return placeholder_fields


def validate_no_placeholders(root: str | Path) -> dict:
    """Check if config has been filled (no placeholders). Returns safe summary without values."""
    root = Path(root)
    path = root / CONFIG_FILE

    result = {
        "present": False,
        "ok": False,
        "filled": False,
        "placeholder_fields": [],
        "all_required_present": False,
    }

    if not path.exists():
        return result

    result["present"] = True

    try:
        data = read_json(path)
        validated = validate_config(data)
        result["ok"] = True
    except (ValueError, FileNotFoundError) as e:
        result["error"] = str(e)
        return result

    # Check placeholders
    placeholder_fields = _check_placeholder_values(validated)
    result["placeholder_fields"] = placeholder_fields
    result["filled"] = len(placeholder_fields) == 0

    # All required fields present and filled
    result["all_required_present"] = (
        result["filled"]
        and bool(validated.get("backend_base_url"))
        and bool(validated.get("device_code"))
    )

    return result
