"""
Display name sanitizer for demo data hygiene.

Maps test/seed/legacy/mock display names to business-neutral values
without touching database records. Safe for Jinja2 templates via |sanitize filter.

Rules:
- Never mutate IDs, codes, or DB records
- Patterns are additive — add new ones as they appear
- Empty/None values → "Нет данных" or "—" depending on context
"""

import re
from typing import Optional


# ── Known display name mappings ──────────────────────────────────────
# These are exact matches for names stored in the DB.
_DISPLAY_NAME_MAP: dict[str, str] = {
    # Creatives
    "test-creative-seed": "Рекламный макет",
    "Synthetic Creative": "Рекламный макет",
    "Test Banner Creative": "Рекламный макет",
    # Campaigns
    "Test Campaign": "Кампания поставщика",
    "test-camp-seed": "Кампания поставщика",
    # Devices
    "test-dev-seed": "Экран КСО",
    "Synthetic KSO Device": "Экран КСО",
    "test-dev-02": "Экран КСО",
    "test-dev-03": "Экран КСО",
    # Publications
    "test-manifest-seed": "Пакет публикации",
    # Places
    "test-place-seed": "Магазин",
    # Users
    "synthetic_seed_user": "Служебная учётная запись",
    "Synthetic Seed User": "Служебная учётная запись",
    "test_admin": "Администратор",
    "Test Admin": "Администратор",
}

# ── Code/name prefix patterns ────────────────────────────────────────
# These map prefixes found in codes (like "test-", "legacy_") to display labels.
_CODE_PREFIX_MAP: dict[str, str] = {
    "test-": "Код ",
    "legacy_": "",
    "legacy-": "",
}

# ── Generic user display name patterns ───────────────────────────────
_USER_DISPLAY_PATTERNS = [
    (re.compile(r"^Test\s+(\w+)$", re.IGNORECASE), lambda m: f"{m.group(1).capitalize()}"),
    (re.compile(r"^RLS\s+Test\s+(\w+)$", re.IGNORECASE), lambda m: f"{m.group(1).capitalize()}"),
    (re.compile(r"^Media\s+Test\s+(\w+)$", re.IGNORECASE), lambda m: f"{m.group(1).capitalize()}"),
    (re.compile(r"^Test\s+", re.IGNORECASE), lambda m: ""),
    (re.compile(r"^Test$", re.IGNORECASE), lambda m: ""),  # Bare "Test" as display name
]

# ── UUID-like pattern (used to collapse raw UUIDs into "Код") ────────
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# ── Generic seed/test patterns ───────────────────────────────────────
_GENERIC_TEST_RE = re.compile(r"(?:^|[_-])test[_-]", re.IGNORECASE)
# Broader test-word match for sanitize_any (catches emails, @test., bare "test")
_GENERIC_TEST_WORD_RE = re.compile(r"\btest\b", re.IGNORECASE)
_GENERIC_SEED_RE = re.compile(r"[_-]seed\b", re.IGNORECASE)
_SEED_SUFFIX_RE = re.compile(r"-seed$", re.IGNORECASE)
_GENERIC_LEGACY_RE = re.compile(r"\blegacy[_-]", re.IGNORECASE)


def sanitize_display_name(value: Optional[str], default: str = "—") -> str:
    """Sanitize a display name for demo UI.

    - None/empty → *default*
    - Known test/seed names → mapped business value
    - UUIDs → "Код"
    - Generic test-/seed patterns → cleaned version
    - Otherwise → original value
    """
    if not value:
        return default

    # Exact match
    if value in _DISPLAY_NAME_MAP:
        return _DISPLAY_NAME_MAP[value]

    # UUID → "Код"
    if _UUID_RE.match(value):
        return "Код"

    # "None" as literal string
    if value.strip() == "None":
        return "Нет данных"

    return value


def sanitize_code(code: Optional[str], default: str = "—") -> str:
    """Sanitize a technical code for demo UI.

    Strips known test/seed prefixes and shortens UUIDs.
    """
    if not code:
        return default

    if _UUID_RE.match(code):
        return "Код"

    # Strip known prefixes
    for prefix, replacement in _CODE_PREFIX_MAP.items():
        if code.lower().startswith(prefix):
            stripped = code[len(prefix):]
            # Also strip seed suffix from the prefix-stripped result
            stripped = _SEED_SUFFIX_RE.sub("", stripped)
            if _UUID_RE.match(stripped):
                return "Код"
            if not stripped:
                return "Код"
            return f"{replacement}{stripped[:12]}"

    # Generic: strip test-/seed- and -seed suffix
    cleaned = _GENERIC_TEST_RE.sub("", code)
    cleaned = _GENERIC_SEED_RE.sub("", cleaned)
    cleaned = _SEED_SUFFIX_RE.sub("", cleaned)
    cleaned = _GENERIC_LEGACY_RE.sub("", cleaned)

    if cleaned != code:
        if _UUID_RE.match(cleaned):
            return "Код"
        return cleaned[:16]

    return code


def sanitize_user_display_name(value: Optional[str], default: str = "Пользователь") -> str:
    """Sanitize user display names — handles 'Test *' patterns."""
    if not value:
        return default

    # Exact match
    if value in _DISPLAY_NAME_MAP:
        return _DISPLAY_NAME_MAP[value]

    # Pattern-based
    for pattern, replacer in _USER_DISPLAY_PATTERNS:
        m = pattern.match(value)
        if m:
            result = replacer(m)
            return result if result else default

    return value


def sanitize_any(value: Optional[str], default: str = "—") -> str:
    """Generic sanitizer that works on any string value.

    Used as Jinja2 filter: {{ item.name | sanitize }}
    """
    sanitized = sanitize_display_name(value, default)
    # Also check for generic test/seed patterns (broader for UI)
    sanitized = _GENERIC_TEST_WORD_RE.sub("", sanitized)
    sanitized = _GENERIC_SEED_RE.sub("", sanitized)
    # Clean up broken email patterns like "@.local"
    sanitized = re.sub(r"@\.\w+", "@...", sanitized)
    return sanitized.strip() or default
