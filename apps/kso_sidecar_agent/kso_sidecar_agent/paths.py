"""Folder constants matching docs/kso_local_interface_contract.md."""

from pathlib import Path

# Subdirectories under the adapter root
SUB_DIRS = [
    "config",
    "manifest",
    "media/current",
    "media/staging",
    "media/quarantine",
    "pop",
    "status",
    "logs",
]

# Agent-owned status file
AGENT_STATUS_FILE = "status/agent_status.json"

# Agent config file (non-secret)
CONFIG_FILE = "config/agent_config.json"

# Dev-only secret store file
DEV_SECRET_FILE = "config/device_secret.dev"

# Runtime config file (local cache)
RUNTIME_CONFIG_FILE = "config/runtime_config.json"

# ── Agent status template ────────────────────────────────────────────

AGENT_STATUS_TEMPLATE = {
    "status": "stopped",
    "updated_at": "",  # filled at creation time
    "offline_mode": False,
    "cached_items": 0,
    "invalid_hash_items": 0,
    "errors": [],
}


def default_agent_status(updated_at: str) -> dict:
    """Return a fresh agent status dict with the given timestamp."""
    data = dict(AGENT_STATUS_TEMPLATE)
    data["updated_at"] = updated_at
    return data
