"""Read and validate manifest/current_manifest.json.

Strictly follows kso_local_interface_contract.md.
This is a DEV TOOL. No secrets, no tokens, no network.
"""

import json
import re
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ── Forbidden substrings in manifest keys/values (security scan) ────

FORBIDDEN_MANIFEST_SUBSTRINGS: list[str] = [
    "token",
    "jwt",
    "password",
    "secret",
    "api_key",
    "private_key",
    "local_path",
    "file_path",
    "receipt",
    "payment_card",
]

# ── Path traversal protection ───────────────────────────────────────

PATH_TRAVERSAL_PATTERNS = re.compile(
    r"[" + re.escape(r"/\\") + r"]"    # forward/backward slash
    r"|\.\."                              # parent dir
    r"|^[A-Za-z]:"                        # drive prefix like C:
)

# ── Helpers ─────────────────────────────────────────────────────────

def _validate_uuid(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected string UUID, got {type(value).__name__}")
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{field}: '{value}' is not a valid UUID")
    return value


def _validate_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected hex string, got {type(value).__name__}")
    if len(value) != 64:
        raise ValueError(f"{field}: expected 64 hex chars, got {len(value)}")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError(f"{field}: invalid hex characters")
    return value.lower()


def _validate_iso8601(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected ISO8601 string, got {type(value).__name__}")
    if len(value) < 10:
        raise ValueError(f"{field}: '{value}' too short for ISO8601")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise ValueError(f"{field}: '{value}' is not valid ISO8601")


def _validate_non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field}: expected number, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{field}: must be >= 0, got {value}")
    return int(value)


def _validate_filename(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: must be a non-empty string")
    if PATH_TRAVERSAL_PATTERNS.search(value):
        raise ValueError(
            f"{field}: path traversal not allowed in filename '{value}'"
        )
    return value


# ── Security: scan for forbidden keys/values ─────────────────────────

def _security_scan(obj: dict, path: str = "$") -> None:
    """Recursively scan dict keys and values for forbidden substrings."""
    for key, value in obj.items():
        key_lower = str(key).lower()
        for forbidden in FORBIDDEN_MANIFEST_SUBSTRINGS:
            if forbidden in key_lower:
                raise ValueError(
                    f"Forbidden key '{key}' at {path} "
                    f"(contains '{forbidden}')"
                )
        if isinstance(value, str):
            value_lower = value.lower()
            for forbidden in FORBIDDEN_MANIFEST_SUBSTRINGS:
                if forbidden in value_lower:
                    raise ValueError(
                        f"Forbidden value in '{key}' at {path}: "
                        f"'{value}' contains '{forbidden}'"
                    )
        elif isinstance(value, dict):
            _security_scan(value, f"{path}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    _security_scan(item, f"{path}.{key}[{i}]")


# ── Core read ────────────────────────────────────────────────────────

class ManifestInfo:
    """Validated manifest information."""
    __slots__ = (
        "manifest_version_id", "manifest_hash", "generated_at",
        "valid_until", "campaign_id", "items", "items_count",
        "expired", "raw",
    )

    def __init__(self, data: dict) -> None:
        self.raw = data
        self.manifest_version_id: str = _validate_uuid(
            data.get("manifest_version_id"), "manifest_version_id"
        )
        self.manifest_hash: str = _validate_sha256(
            data.get("manifest_hash", ""), "manifest_hash"
        )
        self.generated_at: datetime = _validate_iso8601(
            data.get("generated_at"), "generated_at"
        )
        self.valid_until: datetime = _validate_iso8601(
            data.get("valid_until"), "valid_until"
        )
        self.campaign_id: Optional[str] = None
        if "campaign_id" in data and data["campaign_id"] is not None:
            self.campaign_id = _validate_uuid(data["campaign_id"], "campaign_id")

        items = data.get("items")
        if not isinstance(items, list):
            raise ValueError("'items' must be a list")
        self.items = [_validate_item(it, i) for i, it in enumerate(items)]
        self.items_count = len(self.items)
        self.expired = self.valid_until < datetime.now(timezone.utc)


class ManifestItem:
    """Validated manifest item."""
    __slots__ = (
        "manifest_item_id", "filename", "content_type", "sha256",
        "size_bytes", "duration_ms", "order",
    )


def _validate_item(data: dict, index: int) -> ManifestItem:
    if not isinstance(data, dict):
        raise ValueError(f"items[{index}]: expected object, got {type(data).__name__}")

    item = ManifestItem()
    item.manifest_item_id = _validate_uuid(
        data.get("manifest_item_id"), f"items[{index}].manifest_item_id"
    )
    item.filename = _validate_filename(
        data.get("filename", ""), f"items[{index}].filename"
    )
    content_type = data.get("content_type", "")
    if not isinstance(content_type, str) or not content_type.strip():
        raise ValueError(f"items[{index}].content_type: must be a non-empty string")
    item.content_type = content_type
    item.sha256 = _validate_sha256(
        data.get("sha256", ""), f"items[{index}].sha256"
    )
    item.size_bytes = _validate_non_negative_int(
        data.get("size_bytes", 0), f"items[{index}].size_bytes"
    )
    item.duration_ms = _validate_non_negative_int(
        data.get("duration_ms", 0), f"items[{index}].duration_ms"
    )
    item.order = _validate_non_negative_int(
        data.get("order", 0), f"items[{index}].order"
    )
    return item


# ── Public API ───────────────────────────────────────────────────────

def read_manifest(root: str | Path) -> ManifestInfo:
    """Read and validate manifest/current_manifest.json.

    Returns ManifestInfo on success.
    Raises FileNotFoundError if manifest file is missing.
    Raises ValueError/JSONDecodeError on validation failure.
    """
    root = Path(root)
    path = root / "manifest" / "current_manifest.json"

    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in manifest: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")

    # Security scan before validation
    _security_scan(data)

    return ManifestInfo(data)
