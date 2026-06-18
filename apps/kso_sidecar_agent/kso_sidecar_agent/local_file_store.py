"""Create the local folder structure + agent_status.json.

Follows docs/kso_local_interface_contract.md.
This is a DEV SKELETON. No secrets, no backend calls, no media.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from kso_sidecar_agent import agent_status, local_config, manifest_store, runtime_config_store, secret_store
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

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_data = default_agent_status(now)

    status_path = root / AGENT_STATUS_FILE
    atomic_write_json(status_path, status_data)


def doctor(root: str | Path, dev_secret_store: bool = False) -> dict:
    """Check folder structure, agent_status.json, and agent_config.json health.

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
        "config_ok": False,
        "config_error": "",
        "config_details": {},
        "runtime_config_ok": False,
        "runtime_config_error": "",
        "manifest_ok": False,
        "manifest_error": "",
        "manifest_details": {},
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

    # Validate agent_status.json
    validation = agent_status.validate_status_file(root)
    if validation["ok"]:
        result["agent_status_ok"] = True
        result["agent_status"] = validation.get("status", "")
    else:
        result["agent_status_error"] = validation["error"]

    # Validate config
    config_status = local_config.config_status(root)
    result["config_ok"] = config_status["ok"]
    if not config_status["ok"]:
        result["config_error"] = config_status.get("error", "MISSING")
    else:
        result["config_details"] = config_status

    # Check runtime config (warning, not fatal)
    rc_status = runtime_config_store.runtime_config_status(root)
    result["runtime_config_ok"] = rc_status["ok"]
    if not rc_status["ok"]:
        result["runtime_config_error"] = rc_status.get("error", "MISSING")

    # Check dev secret store if enabled
    if dev_secret_store:
        try:
            ds = secret_store.check_secret_store(root, dev_secret_store=True)
            result["dev_secret_store_checked"] = True
            result["dev_secret_store"] = ds
            if ds["present"] and ds["permissions_ok"] is False:
                result["dev_secret_store"]["warning"] = (
                    "Dev secret file has insecure permissions (expected 0600)"
                )
        except RuntimeError:
            pass  # dev mode not enabled — skip

    # Check manifest (warning, not fatal)
    mstatus = manifest_store.manifest_store_status(root)
    result["manifest_ok"] = mstatus["validation_status"] == "ok"
    if not result["manifest_ok"]:
        result["manifest_error"] = mstatus["validation_status"]
    result["manifest_details"] = mstatus

    return result
