# D.5.2 — Portal Read-Only Planning Visibility

> **Дата:** 2026-07-01
> **Этап:** D.5.2 — Portal Planning Visibility
> **Предыдущий:** D.5.1.1 (commit `46e241a`)
> **Результат:** ✅ GO для D.6 Closure Gate

---

## Portal Pages / Blocks Added

### Campaign Detail — Planning Block

Блок «Планирование» (📊) на странице `/campaigns/{campaign_code}` с тремя подсекциями:

| Подсекция | Данные |
|---|---|
| **Доступность** | available/unavailable, units_count, warnings_count |
| **Конфликты** | has_conflict, count («Конфликтов не найдено.» если нет) |
| **Занятость** | occupancy_percent, booked_spots, capacity_spots |

Блок показывается **только** при наличии `planning.read` permission и данных кампании.

---

## Используемые API

| Portal Block | Backend API | BackendClient Method |
|---|---|---|
| Доступность | `GET /api/planning/availability?campaign_id=...` | `get_planning_availability()` |
| Конфликты | `POST /api/planning/check-conflicts` | `check_planning_conflicts()` |
| Занятость | `GET /api/planning/occupancy` | `get_planning_occupancy()` |
| (future) | `POST /api/planning/scenario` | `simulate_planning_scenario()` |

---

## States

| Состояние | Отображение |
|---|---|
| Нет `planning.read` | Блок не показывается |
| Backend недоступен | «Данные планирования пока недоступны.» |
| 403 от backend | Блок не показывается |
| Нет конфликтов | «Конфликтов не найдено.» |
| Есть конфликты | «Обнаружено конфликтов: N» |
| Нет данных занятости | Секция скрыта |

---

## Что НЕ добавлено

- ❌ CRUD-кнопки (создать/редактировать/удалить бронирование)
- ❌ Формы бронирования
- ❌ JS / CDN / localStorage
- ❌ Raw UUID в шаблоне
- ❌ Secrets / tokens / passwords
- ❌ CampaignBooking / BookingItem создание
- ❌ Campaign / Placement изменение

---

## BackendClient Methods (4)

| Метод | Endpoint |
|---|---|
| `get_planning_availability()` | `GET /api/planning/availability` |
| `check_planning_conflicts()` | `POST /api/planning/check-conflicts` |
| `get_planning_occupancy()` | `GET /api/planning/occupancy` |
| `simulate_planning_scenario()` | `POST /api/planning/scenario` |

---

## Файлы

| Файл | Действие | Строк |
|---|---|---|
| `apps/portal-web/backend_client.py` | 🔄 +4 planning methods (+95 строк) | +95 |
| `apps/portal-web/main.py` | 🔄 +planning data fetch + context (+58 строк) | +58 |
| `apps/portal-web/templates/pages/campaigns_detail.html` | 🔄 +planning block (+58 строк) | +58 |
| `apps/portal-web/tests/test_planning_portal_d5_2.py` | 🆕 | 27 tests |
| `docs/qa/d5-2-portal-planning-readonly.md` | 🆕 | этот документ |

---

## Test Results

| Слой | Результат |
|---|---|
| D.5.2 portal targeted | **27/27** ✅ |
| Portal regression | **890 passed**, 32 skipped, 8 pre-existing errors |
| Backend planning suite | **254/254** ✅ |
| Planning API contract | без изменений ✅ |

---

## Что не менялось

- Campaign submit/approve flow
- Placement API
- Publication flow
- Device Gateway
- Universal Manifest
- generated_manifests
- Backend planning logic
- Docker/.env

---

## GO ✅ для D.6 — Phase D Closure Gate
