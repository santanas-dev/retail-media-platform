"""Safe projection helpers for hierarchy data (Step 37.2).

Transforms raw backend API responses into template-safe dictionaries.
Strips all forbidden fields: tokens, secrets, UUIDs, backend URLs,
IP/MAC/hostname/serial, filesystem paths.

All values are safe for direct HTML rendering.
"""
from __future__ import annotations

# Forbidden keys — stripped from ALL data before rendering
_FORBIDDEN_KEYS = frozenset({
    "id", "store_id", "cluster_id", "branch_id", "channel_id",
    "access_token", "refresh_token", "token", "token_hash",
    "password_hash", "password", "authorization",
    "device_secret", "client_secret",
    "ip_address", "mac_address", "hostname", "serial_number",
    "backend_url", "file_path", "filename",
    "sha256", "storage_key", "minio",
})

# Fields displayed in KSO devices table
_DEVICE_SAFE_FIELDS = {
    "device_code", "display_name", "status", "channel",
    "runtime_version", "player_version", "sidecar_version",
    "state_adapter_version", "manifest_version",
    "screen_width", "screen_height", "ad_zone_width", "ad_zone_height",
    "last_seen_at", "store_name",
}

# Fields displayed in stores table
_STORE_SAFE_FIELDS = {
    "name", "code", "format", "status", "is_active",
    "branch_name", "cluster_name", "kso_count", "timezone",
}


def _strip_forbidden(data: dict) -> dict:
    """Return a copy with forbidden keys removed."""
    return {
        k: v for k, v in data.items()
        if k not in _FORBIDDEN_KEYS
    }


def build_store_rows(
    stores: list[dict],
    clusters: list[dict],
    branches: list[dict],
    kso_devices: list[dict],
) -> list[dict]:
    """Build safe store rows for the /stores template.

    Merges branches → clusters → stores → kso count into safe rows.
    Each row: {name, code, format, status, branch_name, cluster_name, kso_count}
    """
    # Index by id
    branch_by_id = {b["id"]: b for b in branches if "id" in b}
    cluster_by_id = {c["id"]: c for c in clusters if "id" in c}

    # Count KSO devices per store
    kso_by_store: dict[str, int] = {}
    for d in kso_devices:
        sid = d.get("store_id", "")
        if sid:
            kso_by_store[sid] = kso_by_store.get(sid, 0) + 1

    rows = []
    for s in stores:
        cid = s.get("cluster_id", "")
        cluster = cluster_by_id.get(cid, {})
        bid = cluster.get("branch_id", "")
        branch = branch_by_id.get(bid, {})

        row = {
            "name": s.get("name", ""),
            "code": s.get("code", ""),
            "format": s.get("format") or "—",
            "status": s.get("status", "—"),
            "branch_name": branch.get("name", "—"),
            "cluster_name": cluster.get("name", "—"),
            "kso_count": kso_by_store.get(s.get("id", ""), 0),
        }
        rows.append(row)

    return rows


def build_device_rows(
    kso_devices: list[dict],
    stores: list[dict],
) -> list[dict]:
    """Build safe KSO device rows for the /devices template.

    Resolves store_id → store_name.
    Each row: {device_code, display_name, status, store_name,
               runtime_version, player_version, sidecar_version,
               state_adapter_version, manifest_version,
               screen_width, screen_height, ad_zone_width, ad_zone_height,
               last_seen_at}
    """
    store_by_id = {s["id"]: s for s in stores if "id" in s}

    rows = []
    for d in kso_devices:
        sid = d.get("store_id", "")
        store = store_by_id.get(sid, {})
        store_name = store.get("name") or store.get("code") or "—"

        row = {
            "device_code": d.get("device_code", ""),
            "display_name": d.get("display_name") or d.get("device_code", ""),
            "status": d.get("status", "—"),
            "channel": d.get("channel", "kso"),
            "store_name": store_name,
            "runtime_version": d.get("runtime_version") or "—",
            "player_version": d.get("player_version") or "—",
            "sidecar_version": d.get("sidecar_version") or "—",
            "state_adapter_version": d.get("state_adapter_version") or "—",
            "manifest_version": d.get("manifest_version") or "—",
            "screen_width": d.get("screen_width", 1920),
            "screen_height": d.get("screen_height", 1080),
            "ad_zone_width": d.get("ad_zone_width", 1440),
            "ad_zone_height": d.get("ad_zone_height", 1080),
            "last_seen_at": _format_dt(d.get("last_seen_at")),
        }
        rows.append(row)

    return rows


def _format_dt(val) -> str:
    """Format datetime string for display, strip T and timezone."""
    if not val:
        return "—"
    s = str(val)
    # ISO 8601: "2026-06-22T12:34:56+00:00" → "2026-06-22 12:34"
    if "T" in s:
        s = s.replace("T", " ").split("+")[0].split("Z")[0]
        if len(s) > 16:
            s = s[:16]
    return s
