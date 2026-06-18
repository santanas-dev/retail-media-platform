"""Write kso_status.json — atomic write via temp file + rename."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


STATE_SCREEN_MAP: dict[str, str] = {
    "idle": "idle_screen",
    "transaction": "scanning_screen",
    "payment": "payment_screen",
    "error": "error_screen",
    "service_mode": "service_screen",
    "unknown": "unknown",
}


def write_state(root: str | Path, state: str) -> None:
    """Write status/kso_status.json atomically.

    Fields correspond strictly to kso_local_interface_contract.md.
    No secrets, no tokens, no customer data.
    """
    root = Path(root)
    status_dir = root / "status"
    status_dir.mkdir(parents=True, exist_ok=True)

    target = status_dir / "kso_status.json"
    tmp = status_dir / "kso_status.json.tmp"

    data = {
        "state": state,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "screen": STATE_SCREEN_MAP.get(state, "unknown"),
        "can_show_ads": state == "idle",
    }

    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)  # atomic rename
