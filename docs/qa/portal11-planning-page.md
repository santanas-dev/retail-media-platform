# PORTAL.1.1 — Planning Page: QA Report

**Date:** 2026-07-03
**Status:** ✅ COMPLETE
**Previous:** PORTAL.1.0 — Design Gate
**Phase:** PORTAL.1 — Portal Functional Completion

---

## Что добавлено

### Новая страница: `/planning`

Три блока с данными:
- **Доступность** — available units, total capacity, occupied, occupancy %
- **Конфликты** — conflict type, reason, inventory unit, period, severity
- **Заполняемость** — occupancy %, used/available capacity, daily breakdown

### Фильтры
- `date_from`, `date_to` (обязательные)
- `store_id`, `channel_id`, `inventory_unit_id`, `campaign_id`

---

## Используемые backend endpoints

| Endpoint | Method | BackendClient |
|---|---|---|
| `/api/planning/availability` | GET | `get_planning_availability()` |
| `/api/planning/check-conflicts` | POST | `check_planning_conflicts()` |
| `/api/planning/occupancy` | GET | `get_planning_occupancy()` |

Все уже существовали до PORTAL.1.1. Backend не менялся.

---

## RBAC

- `/planning` → `planning.read`
- Nav link в sidebar под «Аналитика»
- `device_service` excluded

---

## Security

- No secrets в template
- No traceback, no raw JSON dump
- No localStorage, no CDN, no `<script>`
- `_safe_error()` helper: truncate to 300 chars

---

## Boundaries

| Constraint | Status |
|---|---|
| Backend API | ✅ untouched |
| Миграции | ✅ 0 |
| DB schema | ✅ 0 |
| Docker/.env | ✅ 0 |
| Booking UI | ❌ нет |
| Publication actions | ❌ нет |
| Production switch | ❌ нет |

---

## Tests

### PORTAL.1.1: 42/42 ✅
- Route/RBAC: 7, BackendClient: 5, Rendering: 8, Data: 5, Security: 7, Boundaries: 7, Regression: 3

---

## Files

| File | Change |
|---|---|
| `apps/portal-web/main.py` | +16 lines: `_safe_error()` helper + route |
| `apps/portal-web/rbac.py` | +1 line: `/planning` → `planning.read` |
| `apps/portal-web/templates/base.html` | +3 lines: nav link |
| `apps/portal-web/templates/pages/planning.html` | 🆕 template |
| `apps/portal-web/tests/test_planning_page_portal11.py` | 🆕 42 tests |

---

## Next step

### GO for PORTAL.1.2 — Booking Workflow Page
