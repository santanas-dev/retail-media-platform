# F.5 — Portal Reports Read-Only

**Status:** COMPLETED  
**Date:** 2026-07-10  
**Commit:** (see report)

## Overview

F.5 добавляет portal-страницу аналитики показов, использующую F.4 Analytics API. Server-side rendering (Jinja2). Без JS/CDN/localStorage.

---

## Portal page: `/reports/analytics`

**Название:** «Аналитика показов»  
**Permission:** `reports.read`  
**RBAC mapping:** `"/reports/analytics": "reports.read"`

### Блоки

| Блок | API endpoint | Описание |
|---|---|---|
| A. Сводка доставки | `GET /api/analytics/delivery/summary` | KPI-карточки: delivered, events, success, failure |
| B. План / факт | `GET /api/analytics/planned-vs-delivered` | delivered, expected, status |
| C. Здоровье устройств | `GET /api/analytics/device-health` | Таблица: device, status, last_seen |
| D. Детализация | встроено в delivery/summary | 6 таблиц: campaign, placement, store, device, channel, day |

### Фильтры

- `date_from` / `date_to` — диапазон дат
- `channel_code` — выбор канала (КСО / все)

---

## BackendClient methods (3 новых)

| Метод | Endpoint |
|---|---|
| `get_analytics_delivery_summary(...)` | `GET /api/analytics/delivery/summary` |
| `get_analytics_planned_vs_delivered(...)` | `GET /api/analytics/planned-vs-delivered` |
| `get_analytics_device_health(...)` | `GET /api/analytics/device-health` |

Все методы используют существующую `_request()` с auth-заголовком, таймаутами и safe error handling.

---

## Error / empty states

| Ситуация | Поведение |
|---|---|
| Нет `reports.read` | Страница скрыта (RBAC → redirect/403) |
| Backend 403 | «Нет доступа к отчёту» |
| Backend недоступен | «Данные аналитики пока недоступны» |
| Нет событий | «За выбранный период событий показов нет» |
| `expected=None` / `no_plan` | «Плановые показы пока не рассчитаны» |
| placement/store `key="unknown"` | «Не определено» |

---

## Security

- ✅ Нет secrets (password/token/secret/api_key) в HTML
- ✅ Нет raw details_json
- ✅ Нет traceback/internal error
- ✅ Нет JS/CDN/localStorage/sessionStorage
- ✅ Server-side rendering only (Jinja2)
- ✅ Auth через portal session + backend Bearer token

---

## Read-only boundaries

- ❌ Нет create/edit/delete buttons
- ❌ Нет booking/reservation
- ❌ Нет POST-форм, меняющих domain data
- ❌ Нет прямого доступа к БД (только через BackendClient → API)
- ❌ Backend API contract не менялся (4 endpoints)
- ❌ Миграции не создавались
- ❌ ClickHouse не включался

---

## Тесты

| Слой | Тестов |
|---|---|
| F.5 targeted | **44** |
| Portal regression | **858 passed, 20 skipped** |
| Backend analytics (F.4/F.4.1) | нетронут |
| Backend collection | 2145 / 0 errors |

### F.5 test groups

| Группа | Тестов | Темы |
|---|---|---|
| Navigation | 4 | route, nav link, RBAC, active class |
| BackendClient | 5 | 3 methods exist, correct endpoints |
| Page rendering | 13 | title, blocks, 6 breakdown tables, filters |
| Empty/error states | 7 | no data, no plan, unknown, 403, error |
| Security | 5 | no secrets, no CDN, no traceback |
| Read-only | 5 | no CRUD, no booking, no DB, no POST |
| Regression | 5 | existing pages, backend contract, migrations |

---

## GO / NO-GO

**✅ GO для F.6 или Closure Gate**
