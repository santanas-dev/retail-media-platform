"""Create the local folder structure + agent_status.json.

Follows docs/kso_local_interface_contract.md.
This is a DEV SKELETON. No secrets, no backend calls, no media.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from kso_sidecar_agent.paths import SUB_DIRS, default_agent_status


def init_local_root(root: str | Path) -> None:
    """Create adapter folder structure and agent_status.json.

    Does NOT create device.json or store device_secret.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    for sub in SUB_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)

    # Write agent_status.json
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_data = default_agent_status(now)

    status_path = root / "status" / "agent_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(status_data, indent=2, ensure_ascii=False) + "\n"
    status_path.write_text(content, encoding="utf-8")


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

    # Check agent_status.json
    status_path = root / "status" / "agent_status.json"
    if not status_path.exists():
        result["agent_status_error"] = "MISSING"
    else:
        try:
            data = json.loads(status_path.read_text())
            if not isinstance(data, dict):
                result["agent_status_error"] = "Invalid format (not an object)"
            elif "status" not in data:
                result["agent_status_error"] = "Missing 'status' field"
            else:
                result["agent_status_ok"] = True
                result["agent_status"] = data.get("status")
        except json.JSONDecodeError:
            result["agent_status_error"] = "Invalid JSON"
        except OSError:
            result["agent_status_error"] = "Cannot read file"

    return result
