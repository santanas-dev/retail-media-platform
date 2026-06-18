"""Create the local folder structure + agent_status.json.

Follows docs/kso_local_interface_contract.md.
This is a DEV SKELETON. No secrets, no backend calls, no media.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from kso_sidecar_agent import agent_status
from kso_sidecar_agent.atomic_io import atomic_write_json
from kso_sidecar_agent.paths import SUB_DIRS, AGENT_STATUS_FILE, default_agent_status


def init_local_root(root: str | Path) -> None:
    """Create adapter folder structure and agent_status.json.

    Does NOT create device.json or store device_secret.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    for sub in SUB_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)

    # Write agent_status.json atomically
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_data = default_agent_status(now)

    status_path = root / AGENT_STATUS_FILE
    atomic_write_json(status_path, status_data)


def doctor(root: str | Path) -> dict:
    """Check folder structure and agent_status.json health.

    Returns a dict with health summary. Does NOT read secrets or call backend.
    """
    root = Path(root)
    result = {
        "root_exists": root.is_dir(),
        "folders_ok": True,
        "agent_status_ok": False,
        "total_folders": len(SUB_DIRS),
        "missing_folders": [],
        "agent_status_error": "",
    }

    if not root.is_dir():
        result["folders_ok"] = False
        result["missing_folders"] = [str(root)]
        return result

    for sub in SUB_DIRS:
        path = root / sub
        if not path.is_dir():
            result["folders_ok"] = False
            result["missing_folders"].append(sub)

    # Validate agent_status.json via agent_status module
    validation = agent_status.validate_status_file(root)

    if validation["ok"]:
        result["agent_status_ok"] = True
        result["agent_status"] = validation.get("status", "")
    else:
        result["agent_status_error"] = validation["error"]

    return result
