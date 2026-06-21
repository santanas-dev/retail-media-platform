"""Demo data and view models for KSO portal UI.

All values are obviously synthetic — prefixed with DEMO:.
No real store codes, KSO codes, campaign names, or identifiers.
No raw IDs, hashes, secrets, backend URLs, storage keys, or file paths.
"""

from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# View Models (safe for rendering, no raw IDs/hashes/secrets)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DemoStore:
    branch: str
    name: str
    fmt: str
    has_kso: bool
    state_adapter: str
    sidecar: str
    player: str
    readiness: str
    heartbeat: str


@dataclass
class DemoDevice:
    store: str
    name: str
    state_adapter: str
    sidecar: str
    player: str
    runtime: str
    heartbeat: str
    manifest: str
    pop: str


@dataclass
class DemoCampaign:
    name: str
    status: str
    period: str
    creatives: str
    stores: str
    publication: str
    shows_plan: str
    shows_fact: str
    pop: str


@dataclass
class DemoCreative:
    name: str
    ctype: str
    fmt: str
    size: str
    duration: str
    status: str
    used_in: str
    updated: str


@dataclass
class DemoSchedule:
    period: str
    campaign: str
    creatives: str
    stores: str
    slot: str
    duration: str
    occupancy: str
    publication: str
    conflicts: str


@dataclass
class DemoPublication:
    campaign: str
    period: str
    approval: str
    manifest: str
    publication: str
    delivery: str
    kso: str
    pop: str
    last_event: str


@dataclass
class DemoPopEvent:
    period: str
    campaign: str
    creative: str
    store_kso: str
    publication: str
    status: str
    shows: str
    last_event: str
    error: str


@dataclass
class DemoApproval:
    obj: str
    atype: str
    status: str
    initiator: str
    approver: str
    sla: str
    last_decision: str
    comment: str
    next_step: str


# ═══════════════════════════════════════════════════════════════════════
# Demo Data (synthetic, DEMO:-prefixed)
# ═══════════════════════════════════════════════════════════════════════

DASHBOARD = {
    "kso_devices": "12",
    "active_campaigns": "3",
    "published_manifests": "5",
    "pop_today": "1 247",
    "devices_hold": "2",
    "devices_errors": "1",
}

DEMO_STORES = [
    DemoStore("DEMO: Северный", "DEMO: Магазин 001", "Супермаркет", True,
              "OK", "OK", "OK", "Готов", "2 мин назад"),
    DemoStore("DEMO: Северный", "DEMO: Магазин 002", "Минимаркет", False,
              "—", "—", "—", "Нет КСО", "—"),
    DemoStore("DEMO: Северный", "DEMO: Магазин 003", "Супермаркет", True,
              "OK", "OK", "Hold", "Hold", "5 мин назад"),
    DemoStore("DEMO: Центральный", "DEMO: Магазин 004", "Гипермаркет", True,
              "OK", "OK", "OK", "Готов", "1 мин назад"),
    DemoStore("DEMO: Центральный", "DEMO: Магазин 005", "Супермаркет", True,
              "OK", "OK", "OK", "Готов", "3 мин назад"),
    DemoStore("DEMO: Урал", "DEMO: Магазин 006", "Минимаркет", True,
              "Ошибка", "OK", "OK", "Ошибка", "10 мин назад"),
]

DEMO_DEVICES = [
    DemoDevice("DEMO: Магазин 001", "DEMO: КСО-01",
               "OK", "OK", "OK", "idle", "2 мин", "v1.0", "1 247"),
    DemoDevice("DEMO: Магазин 003", "DEMO: КСО-02",
               "OK", "OK", "Hold", "hold", "5 мин", "v0.9", "0"),
    DemoDevice("DEMO: Магазин 004", "DEMO: КСО-03",
               "OK", "OK", "OK", "idle", "1 мин", "v1.0", "3 891"),
    DemoDevice("DEMO: Магазин 005", "DEMO: КСО-04",
               "OK", "OK", "OK", "idle", "3 мин", "v1.0", "2 104"),
    DemoDevice("DEMO: Магазин 006", "DEMO: КСО-05",
               "Ошибка", "OK", "OK", "error", "10 мин", "—", "0"),
]

DEMO_CAMPAIGNS = [
    DemoCampaign("DEMO: Весенняя акция", "В эфире",
                 "01.06–30.06.2026", "3", "4 КСО",
                 "Опубликована", "5 000", "1 247", "✅"),
    DemoCampaign("DEMO: Новинки июня", "На согласовании",
                 "15.06–15.07.2026", "2", "6 КСО",
                 "Не опубликована", "8 000", "—", "—"),
    DemoCampaign("DEMO: Сезонное предложение", "Черновик",
                 "01.07–31.07.2026", "1", "2 КСО",
                 "Не опубликована", "3 000", "—", "—"),
]

DEMO_CREATIVES = [
    DemoCreative("DEMO: Тестовый баннер 1", "Изображение", "PNG",
                 "245 KB", "—", "Готов", "1 кампания", "01.06.2026"),
    DemoCreative("DEMO: Тестовое видео 1", "Видео", "MP4",
                 "4.2 MB", "15 сек", "На проверке", "—", "02.06.2026"),
    DemoCreative("DEMO: Тестовый баннер 2", "Изображение", "JPEG",
                 "180 KB", "—", "Готов", "2 кампании", "03.06.2026"),
    DemoCreative("DEMO: Тестовый баннер 3", "Изображение", "PNG",
                 "320 KB", "—", "Ошибка", "—", "04.06.2026"),
]

DEMO_SCHEDULES = [
    DemoSchedule("01.06–30.06.2026", "DEMO: Весенняя акция",
                 "3", "4 КСО", "09:00–21:00", "12 ч",
                 "75%", "Опубликовано", "Нет"),
    DemoSchedule("15.06–15.07.2026", "DEMO: Новинки июня",
                 "2", "6 КСО", "08:00–22:00", "14 ч",
                 "60%", "Готово", "Нет"),
    DemoSchedule("01.07–31.07.2026", "DEMO: Сезонное предложение",
                 "1", "2 КСО", "10:00–20:00", "10 ч",
                 "0%", "Не запланировано", "—"),
]

DEMO_PUBLICATIONS = [
    DemoPublication("DEMO: Весенняя акция", "01.06–30.06.2026",
                    "Согласовано", "v1.0", "Опубликован",
                    "Доставлено", "4 КСО", "✅", "21.06 10:00"),
    DemoPublication("DEMO: Новинки июня", "15.06–15.07.2026",
                    "На согласовании", "v0.9", "Не опубликован",
                    "—", "6 КСО", "—", "20.06 15:30"),
    DemoPublication("DEMO: Сезонное предложение", "01.07–31.07.2026",
                    "—", "—", "Не опубликован",
                    "—", "2 КСО", "—", "—"),
]

DEMO_POP_EVENTS = [
    DemoPopEvent("21.06.2026", "DEMO: Весенняя акция",
                 "DEMO: Тестовый баннер 1", "DEMO: КСО-01",
                 "Опубликовано", "Подтверждено", "847", "21.06 10:15", "—"),
    DemoPopEvent("21.06.2026", "DEMO: Весенняя акция",
                 "DEMO: Тестовое видео 1", "DEMO: КСО-03",
                 "Опубликовано", "Подтверждено", "400", "21.06 10:20", "—"),
    DemoPopEvent("21.06.2026", "DEMO: Весенняя акция",
                 "DEMO: Тестовый баннер 1", "DEMO: КСО-04",
                 "Опубликовано", "Ожидает", "—", "21.06 10:22", "—"),
    DemoPopEvent("21.06.2026", "DEMO: Весенняя акция",
                 "DEMO: Тестовый баннер 2", "DEMO: КСО-05",
                 "Опубликовано", "Ошибка", "0", "21.06 09:45",
                 "Таймаут отправки"),
]

DEMO_APPROVALS = [
    DemoApproval("DEMO: Новинки июня", "Кампания", "На согласовании",
                 "Менеджер А", "Руководитель Б", "2 дня",
                 "—", "—", "Проверка"),
    DemoApproval("DEMO: Тестовое видео 1", "Креатив", "На проверке",
                 "Дизайнер В", "Менеджер А", "1 день",
                 "—", "—", "Проверка"),
    DemoApproval("DEMO: Весенняя акция", "Публикация", "Согласовано",
                 "Менеджер А", "Руководитель Б", "2 дня",
                 "Одобрено", "Всё в порядке", "Публикация"),
    DemoApproval("DEMO: Тестовый баннер 3", "Креатив", "Отклонено",
                 "Дизайнер В", "Менеджер А", "1 день",
                 "Отклонено", "Неверный формат", "Перезагрузка"),
]

DEMO_REPORT_KPI = {
    "shows_plan": "16 000",
    "shows_fact": "1 247",
    "completion": "7.8%",
    "kso_online": "4",
    "campaigns_no_fact": "2",
    "errors_pub_pop": "1",
}

DEMO_REPORT_TABLE = [
    {
        "campaign": "DEMO: Весенняя акция",
        "period": "01.06–30.06.2026",
        "stores_kso": "4 КСО",
        "creatives": "3",
        "shows_plan": "5 000",
        "shows_fact": "1 247",
        "completion": "24.9%",
        "pop": "✅",
        "publication": "Опубликовано",
        "approval": "Согласовано",
    },
    {
        "campaign": "DEMO: Новинки июня",
        "period": "15.06–15.07.2026",
        "stores_kso": "6 КСО",
        "creatives": "2",
        "shows_plan": "8 000",
        "shows_fact": "0",
        "completion": "0%",
        "pop": "—",
        "publication": "На согласовании",
        "approval": "На согласовании",
    },
    {
        "campaign": "DEMO: Сезонное предложение",
        "period": "01.07–31.07.2026",
        "stores_kso": "2 КСО",
        "creatives": "1",
        "shows_plan": "3 000",
        "shows_fact": "0",
        "completion": "0%",
        "pop": "—",
        "publication": "Черновик",
        "approval": "—",
    },
]


def get_dashboard_data() -> dict:
    return dict(DASHBOARD)


def get_stores_data() -> list:
    return DEMO_STORES


def get_devices_data() -> list:
    return DEMO_DEVICES


def get_campaigns_data() -> list:
    return DEMO_CAMPAIGNS


def get_creatives_data() -> list:
    return DEMO_CREATIVES


def get_schedules_data() -> list:
    return DEMO_SCHEDULES


def get_publications_data() -> list:
    return DEMO_PUBLICATIONS


def get_pop_events_data() -> list:
    return DEMO_POP_EVENTS


def get_approvals_data() -> list:
    return DEMO_APPROVALS


def get_report_kpi() -> dict:
    return dict(DEMO_REPORT_KPI)


def get_report_table() -> list:
    return DEMO_REPORT_TABLE


# ═══════════════════════════════════════════════════════════════════════
# Demo Users (for Admin page)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DemoUser:
    display_name: str
    login: str
    roles: str
    status: str
    status_label: str
    rls_scopes: str
    mfa: str
    last_login: str


DEMO_USERS = [
    DemoUser("DEMO: Администратор портала", "admin",
             "system_admin, security_admin", "active", "Активен",
             "Без ограничений", "✅", "Сегодня 09:15"),
    DemoUser("DEMO: Менеджер рекламы", "ad_manager",
             "ad_manager", "active", "Активен",
             "Филиалы: Северный, Центральный", "❌", "Сегодня 08:30"),
    DemoUser("DEMO: Согласующий", "approver",
             "approver", "active", "Активен",
             "Кампании: все", "❌", "Вчера 17:45"),
    DemoUser("DEMO: Аналитик BI", "analyst",
             "analyst", "active", "Активен",
             "Филиалы: все", "❌", "Сегодня 07:00"),
]


def get_users_data() -> list:
    return DEMO_USERS
