"""
UI.2.1 — Language & Status Localization.

Unified Russian localization layer for UI values: statuses, enums,
technical codes, feature flag errors, readiness messages, etc.

Usage in templates:
    {{ value | label }}
    {{ value | label("severity") }}
    {{ value | label("emergency_action") }}
    {{ value | label("feature_flag_error") }}
    {{ value | label("readiness") }}
    {{ value | label("device_status") }}
    {{ value | label("priority") }}
"""

from typing import Optional, Dict, Any

# ══════════════════════════════════════════════════════════════════════
# Dictionary 1: STATUS_LABELS — campaign/placement/manifest/booking
# ══════════════════════════════════════════════════════════════════════

STATUS_LABELS: Dict[str, str] = {
    # Lifecycle statuses
    "draft": "Черновик",
    "pending": "На согласовании",
    "pending_approval": "На согласовании",
    "pending_review": "Ожидает проверки",
    "in_review": "На проверке",
    "manual_review": "Ручная проверка",
    "approved": "Согласовано",
    "rejected": "Отклонено",
    "validation_failed": "Ошибка проверки",
    "rework": "На доработке",
    "active": "Активно",
    "inactive": "Неактивно",
    "archived": "Архив",
    "cancelled": "Отменено",
    "error": "Ошибка",
    "failed": "Ошибка",
    "success": "Успешно",

    # Publication/manifest statuses
    "published": "Опубликовано",
    "generated": "Сформировано",
    "manifest_generated": "Пакет показа готов",
    "reserved": "Зарезервировано",
    "confirmed": "Подтверждено",

    # Readiness / delivery
    "served": "Доступен для КСО",
    "no_manifest": "Пакет не найден",
    "no_plan": "Нет плана",
    "unknown": "Не определено",
    "disabled": "Отключено",
    "enabled": "Включено",
    "dry_run": "Симуляция",
    "ok": "OK",
    "silent": "Нет связи",
    "warning": "Предупреждение",

    # PoP event statuses
    "accepted": "Принято",
    "pending": "Ожидает",
    "confirmed_status": "Подтверждено",

    # Creative scan statuses
    "clean": "Чисто",
    "infected": "Заблокирован",
    "not_configured": "Не настроена",
    "uploaded": "Загружен",
    "paused": "Приостановлено",
    "completed": "Завершено",
}

# ══════════════════════════════════════════════════════════════════════
# Dictionary 2: DEVICE_STATUS_LABELS
# ══════════════════════════════════════════════════════════════════════

DEVICE_STATUS_LABELS: Dict[str, str] = {
    "online": "Онлайн",
    "offline": "Офлайн",
    "active": "Активно",
    "inactive": "Неактивно",
    "maintenance": "Обслуживание",
    "blocked": "Заблокировано",
    "unknown": "Не определено",
}

# ══════════════════════════════════════════════════════════════════════
# Dictionary 3: SEVERITY_LABELS
# ══════════════════════════════════════════════════════════════════════

SEVERITY_LABELS: Dict[str, str] = {
    "low": "Низкая",
    "normal": "Обычная",
    "medium": "Средняя",
    "high": "Высокая",
    "critical": "Критическая",
}

# ══════════════════════════════════════════════════════════════════════
# Dictionary 4: PRIORITY_LABELS
# ══════════════════════════════════════════════════════════════════════

PRIORITY_LABELS: Dict[str, str] = {
    "low": "Низкий",
    "normal": "Обычный",
    "medium": "Средний",
    "high": "Высокий",
    "critical": "Критический",
}

# ══════════════════════════════════════════════════════════════════════
# Dictionary 5: EMERGENCY_ACTION_LABELS
# ══════════════════════════════════════════════════════════════════════

EMERGENCY_ACTION_LABELS: Dict[str, str] = {
    "stop_campaign": "Остановить кампанию",
    "stop_placement": "Остановить размещение",
    "stop_device": "Остановить устройство",
    "show_message": "Показать сообщение",
    "restore_campaign": "Вернуть кампанию",
    "restore_device": "Вернуть устройство",
    "stop_channel": "Остановить канал",
    "stop_store": "Остановить магазин",
    "resume": "Возобновить",
    "emergency_message": "Экстренное сообщение",
}

# ══════════════════════════════════════════════════════════════════════
# Dictionary 6: FEATURE_FLAG_ERROR_LABELS
# ══════════════════════════════════════════════════════════════════════

FEATURE_FLAG_ERROR_LABELS: Dict[str, str] = {
    "booking_writes_disabled": "Создание и изменение бронирований отключено техническим переключателем",
    "real_publication_disabled": "Публикация отключена техническим переключателем",
    "generated_manifest_write_disabled": "Создание пакетов показа отключено техническим переключателем",
}

# ══════════════════════════════════════════════════════════════════════
# Dictionary 7: READINESS_LABELS — device readiness reasons
# ══════════════════════════════════════════════════════════════════════

READINESS_LABELS: Dict[str, str] = {
    "No heartbeat received": "Нет связи с устройством",
    "heartbeat missing": "Нет связи с устройством",
    "package missing": "Пакет показа не найден",
    "manifest missing": "Пакет показа не найден",
    "ready": "Готово",
    "partial": "Частично готово",
    "blocked": "Заблокировано",
    "missing": "Не найдено",
}

# ══════════════════════════════════════════════════════════════════════
# Category registry: maps category names to their dictionaries
# ══════════════════════════════════════════════════════════════════════

CATEGORIES: Dict[str, Dict[str, str]] = {
    "status": STATUS_LABELS,
    "device_status": DEVICE_STATUS_LABELS,
    "severity": SEVERITY_LABELS,
    "priority": PRIORITY_LABELS,
    "emergency_action": EMERGENCY_ACTION_LABELS,
    "feature_flag_error": FEATURE_FLAG_ERROR_LABELS,
    "readiness": READINESS_LABELS,
}


def label(
    value: Any,
    category: Optional[str] = None,
    fallback: Optional[str] = None,
) -> str:
    """Return the Russian label for a value.

    Args:
        value: The raw value to localize.
        category: If given, look up in a specific dictionary.
                  One of: status, device_status, severity, priority,
                  emergency_action, feature_flag_error, readiness.
                  When None, searches all categories bottom-up.
        fallback: What to return if value is not found.
                  Defaults to the original value as a string.

    Returns:
        Russian label string, always escaped (no safe HTML).
    """
    if value is None:
        return fallback if fallback is not None else "Не указано"

    if value == "":
        return fallback if fallback is not None else "Не указано"

    key = str(value)

    if category is not None:
        cat_dict = CATEGORIES.get(category)
        if cat_dict is not None and key in cat_dict:
            return cat_dict[key]
    else:
        # Search all categories in order
        for cat_dict in CATEGORIES.values():
            if key in cat_dict:
                return cat_dict[key]

    # Unknown value — safe fallback
    if fallback is not None:
        return fallback
    return key


def label_filter(value: Any, category: Optional[str] = None) -> str:
    """Jinja filter wrapper for the label() function.

    Usage in Jinja2:
        {{ item.status | label }}
        {{ item.severity | label("severity") }}
        {{ action_type | label("emergency_action") }}
    """
    return label(value, category=category)
