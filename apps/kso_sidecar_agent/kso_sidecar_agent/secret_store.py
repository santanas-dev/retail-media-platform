"""Dev-only secret store skeleton.

Stores device_secret in config/device_secret.dev.
ONLY in dev mode (--dev-secret-store flag or KSO_DEV_SECRET_STORE=1 env).

Security:
- Secret via stdin only, NEVER CLI args
- Secret never logged, never printed to stdout/stderr
- Atomic write, chmod 0600
- Secret length: 16-512 chars
"""

import os
import sys
from pathlib import Path

from kso_sidecar_agent.paths import DEV_SECRET_FILE

MIN_SECRET_LENGTH = 16
MAX_SECRET_LENGTH = 512


# ── Dev mode gate ─────────────────────────────────────────────────────

def _check_dev_mode(dev_secret_store: bool) -> None:
    """Raise RuntimeError if dev secret store is not enabled."""
    if not dev_secret_store and os.environ.get("KSO_DEV_SECRET_STORE") not in ("1", "true", "yes"):
        raise RuntimeError(
            "Dev secret store is disabled.\n"
            "  Pass --dev-secret-store flag or set KSO_DEV_SECRET_STORE=1 env.\n"
            "  Production secret storage is not implemented yet."
        )


# ── Public API ────────────────────────────────────────────────────────

def read_secret(root: str | Path, dev_secret_store: bool = False) -> str:
    """Read device_secret from dev store. Returns empty string if absent."""
    _check_dev_mode(dev_secret_store)

    path = Path(root) / DEV_SECRET_FILE
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").rstrip("\n\r")


def check_secret_store(root: str | Path, dev_secret_store: bool = False) -> dict:
    """Return safe summary of secret store status. NEVER returns secret value."""
    _check_dev_mode(dev_secret_store)

    path = Path(root) / DEV_SECRET_FILE
    result = {
        "present": False,
        "mode": "dev-only",
        "permissions_ok": None,  # True/False/None (unknown)
        "readable_by_agent": False,
    }

    if not path.exists():
        return result

    result["present"] = True

    # Check readability
    try:
        path.read_text()
        result["readable_by_agent"] = True
    except (OSError, PermissionError):
        pass

    # Check permissions if available
    try:
        mode = path.stat().st_mode & 0o777
        result["permissions_ok"] = (mode == 0o600)
    except (OSError, NotImplementedError):
        result["permissions_ok"] = None

    return result


def write_secret(
    root: str | Path,
    secret: str,
    dev_secret_store: bool = False,
) -> None:
    """Write device_secret to dev store atomically.

    Secret is received as a string (from stdin, stripped).
    Never logged, never printed.
    """
    _check_dev_mode(dev_secret_store)

    secret = secret.strip("\n\r")
    if not secret:
        raise ValueError("Secret must not be empty")
    if len(secret) < MIN_SECRET_LENGTH:
        raise ValueError(
            f"Secret too short: {len(secret)} chars (min {MIN_SECRET_LENGTH})"
        )
    if len(secret) > MAX_SECRET_LENGTH:
        raise ValueError(
            f"Secret too long: {len(secret)} chars (max {MAX_SECRET_LENGTH})"
        )

    path = Path(root) / DEV_SECRET_FILE

    # Ensure parent exists
    if not path.parent.is_dir():
        raise FileNotFoundError(
            f"Agent root not initialized.\n"
            f"Run 'init-local-root --root {root}' first."
        )

    if path.is_symlink():
        raise ValueError("Refusing to write to symlink")

    # Atomic write: tmp → rename
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(secret + "\n", encoding="utf-8")

    # Set permissions 0600 (best effort)
    try:
        os.chmod(tmp, 0o600)
    except (OSError, NotImplementedError):
        pass

    try:
        os.replace(tmp, path)
    except OSError:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def delete_secret(root: str | Path, dev_secret_store: bool = False) -> bool:
    """Delete dev secret store file. Returns True if file was deleted."""
    _check_dev_mode(dev_secret_store)

    path = Path(root) / DEV_SECRET_FILE
    if not path.exists():
        return False
    path.unlink()
    return True
