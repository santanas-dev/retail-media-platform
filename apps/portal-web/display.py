"""
UI.2.2 — Business Codes / UUID Cleanup.

Display helpers to replace full UUIDs with business-readable codes
or short safe references in the portal UI.

Usage:
    {{ value | short_uuid }}
    {{ value | display_ref("Префикс") }}
    {{ entity | display_code }}
    {{ campaign | display_campaign }}
    {{ device | display_device }}
    {{ booking | display_booking }}
    {{ package | display_package }}
    {{ creative | display_creative }}
"""

import re
from typing import Any, Optional, Union, Dict

# ══════════════════════════════════════════════════════════════════════
# UUID detection
# ══════════════════════════════════════════════════════════════════════

UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


def is_uuid(value: Any) -> bool:
    """Return True if value looks like a full UUID string."""
    if not isinstance(value, str):
        return False
    return bool(UUID_RE.match(value))


# ══════════════════════════════════════════════════════════════════════
# Short UUID
# ══════════════════════════════════════════════════════════════════════

def short_uuid(value: Any, length: int = 8) -> str:
    """Return first `length` characters of a UUID, or the original value.

    Returns empty string for None/empty.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if is_uuid(s):
        return s[:length]
    return s


# ══════════════════════════════════════════════════════════════════════
# Display reference — smart truncation with prefix
# ══════════════════════════════════════════════════════════════════════

def display_ref(
    value: Any,
    prefix: Optional[str] = None,
    max_len: int = 12,
) -> str:
    """Return a human-readable reference for a value.

    If the value is a UUID, shorten it to `max_len` chars.
    If a prefix is given, prepend it: "Бронь a1b2c3d4".

    None/empty → "—".
    """
    if value is None:
        return "—"
    s = str(value).strip()
    if not s:
        return "—"

    if is_uuid(s):
        short = s[:max_len]
    else:
        short = s if len(s) <= max_len else s[:max_len]

    if prefix:
        return f"{prefix} {short}"
    return short


# ══════════════════════════════════════════════════════════════════════
# Display code — pick best business code
# ══════════════════════════════════════════════════════════════════════

def _get_attr(obj: Any, *names: str) -> Optional[str]:
    """Try to get an attribute from dict or object."""
    for name in names:
        if isinstance(obj, dict):
            val = obj.get(name)
            if val is not None and val != "":
                return str(val)
        elif hasattr(obj, name):
            val = getattr(obj, name, None)
            if val is not None and val != "":
                return str(val)
    return None


def display_code(
    entity: Any,
    preferred_fields: Optional[list] = None,
    fallback_prefix: Optional[str] = None,
) -> str:
    """Return the best business code for an entity.

    Tries each field in preferred_fields, picks the first non-empty.
    If preferred_fields is None, tries common code field patterns:
    *_code, code, name, id.
    If all fail and the entity has a UUID id, returns short UUID with prefix.
    Falls back to "—" for None/empty.

    Args:
        entity: Dict or object with code/id fields.
        preferred_fields: Ordered list of field names to try.
        fallback_prefix: Prefix for short UUID fallback (e.g. "Кампания").
    """
    if entity is None:
        return "—"

    if preferred_fields is None:
        # Auto-discover: try all *_code fields, then code, name, id
        preferred_fields = _auto_code_fields(entity)

    for field in preferred_fields:
        val = _get_attr(entity, field)
        if val is not None:
            if is_uuid(val):
                short = short_uuid(val)
                if fallback_prefix:
                    return f"{fallback_prefix} {short}"
                return short
            return val

    # Try id as UUID
    entity_id = _get_attr(entity, "id")
    if entity_id and is_uuid(entity_id):
        short = short_uuid(entity_id)
        if fallback_prefix:
            return f"{fallback_prefix} {short}"
        return short

    return "—"


def _auto_code_fields(entity: Any) -> list:
    """Discover *_code fields on an entity."""
    fields = []
    if isinstance(entity, dict):
        keys = entity.keys()
    elif hasattr(entity, "__dict__"):
        keys = entity.__dict__.keys()
    else:
        keys = []
    for key in keys:
        if key.endswith("_code") and key != "url_code":
            fields.append(key)
    fields.extend(["code", "name", "id"])
    return fields


# ══════════════════════════════════════════════════════════════════════
# Entity-specific display helpers
# ══════════════════════════════════════════════════════════════════════

def display_campaign(campaign: Any) -> str:
    """Display campaign reference: campaign_code > code > name > short UUID."""
    return display_code(
        campaign,
        preferred_fields=["campaign_code", "code", "external_code", "name"],
        fallback_prefix="Кампания",
    )


def display_device(device: Any) -> str:
    """Display device reference: device_code > code > external_code > short UUID."""
    return display_code(
        device,
        preferred_fields=["device_code", "code", "external_code"],
        fallback_prefix="Устройство",
    )


def display_booking(booking: Any) -> str:
    """Display booking reference: booking_code > code > short UUID."""
    return display_code(
        booking,
        preferred_fields=["booking_code", "code"],
        fallback_prefix="Бронь",
    )


def display_package(package: Any) -> str:
    """Display package reference: manifest_code > package_code > code > short UUID."""
    return display_code(
        package,
        preferred_fields=["manifest_code", "package_code", "code"],
        fallback_prefix="Пакет",
    )


def display_creative(creative: Any) -> str:
    """Display creative reference: creative_code > code > name > short UUID."""
    return display_code(
        creative,
        preferred_fields=["creative_code", "code", "name", "filename"],
        fallback_prefix="Креатив",
    )


def display_store(store: Any) -> str:
    """Display store reference: store_code > code > name > short UUID."""
    return display_code(
        store,
        preferred_fields=["store_code", "code", "name"],
        fallback_prefix="Магазин",
    )


# ══════════════════════════════════════════════════════════════════════
# Jinja filter wrappers
# ══════════════════════════════════════════════════════════════════════

def short_uuid_filter(value: Any, length: int = 8) -> str:
    return short_uuid(value, length)


def display_ref_filter(value: Any, prefix: Optional[str] = None) -> str:
    return display_ref(value, prefix=prefix)


def display_code_filter(entity: Any, fallback_prefix: Optional[str] = None) -> str:
    return display_code(entity, fallback_prefix=fallback_prefix)


def display_campaign_filter(campaign: Any) -> str:
    return display_campaign(campaign)


def display_device_filter(device: Any) -> str:
    return display_device(device)


def display_booking_filter(booking: Any) -> str:
    return display_booking(booking)


def display_package_filter(package: Any) -> str:
    return display_package(package)


def display_creative_filter(creative: Any) -> str:
    return display_creative(creative)


def display_store_filter(store: Any) -> str:
    return display_store(store)
