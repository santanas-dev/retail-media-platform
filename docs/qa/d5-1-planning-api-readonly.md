# D.5.1 — Planning API Read-Only / Dry-Run Endpoints

> **Дата:** 2026-07-01
> **Этап:** D.5.1 — Planning API Implementation
> **Предыдущий:** D.5 Design Gate (commit `853fcad`)
> **Результат:** ✅ GO для D.5.2 Portal Read-Only Planning Visibility

---

## Endpoints Added (5)

| Method | Path | Permission | RLS | Audit |
|---|---|---|---|---|
| GET | `/api/planning/availability` | `planning.read` | advertiser через campaign_id | `planning.availability.checked` |
| POST | `/api/planning/check-conflicts` | `planning.read` | advertiser через placement_id | `planning.conflict.checked` |
| GET | `/api/planning/occupancy` | `planning.read` | store через store_id | `planning.occupancy.viewed` |
| POST | `/api/planning/scenario` | `planning.read` | advertiser через campaign_id | `planning.scenario.simulated` |
| GET | `/api/planning/inventory-units/availability` | `planning.read` | advertiser через campaign_id | `planning.availability.checked` |

Все endpoints **read-only / dry-run**. Ни один не создаёт бронирований.

---

## Permission: `planning.read`

Добавлена в seed (`backend/app/domains/identity/seed.py`):
- resource: `planning`
- action: `read`
- description: "View availability, occupancy, and conflict data"

Роли с доступом:
- `system_admin`
- `security_admin`
- `ad_manager`
- `approver`
- `analyst`
- `advertiser` (scoped через RLS)
- `operations`

---

## RLS / Scope Model

### Advertiser Scope
- Реализован через `_ensure_advertiser_scope()` в router
- Принимает `campaign_id` или `placement_id`
- Использует прямые SELECT-запросы (не зависит от campaign service/router)
- Резолвит `campaign → advertiser_id` или `placement → campaign → advertiser_id`
- Вызывает `assert_object_in_advertiser_scope()` — возвращает 404 (не 403)

### Store Scope
- `GET /api/planning/occupancy` с `store_id` проверяет `assert_object_in_store_scope()`
- Пользователь с store/branch scope видит только свои магазины

---

## Audit Events

| Action | Endpoint | Details |
|---|---|---|
| `planning.availability.checked` | availability, inventory-units/availability | campaign_id, store_id, channel_id, inventory_unit_id, date range, result summary |
| `planning.conflict.checked` | check-conflicts | campaign_id, placement_id, inventory_unit_id, date range, has_conflict + count |
| `planning.occupancy.viewed` | occupancy | inventory_unit_id, store_id, channel_id, date range, occupancy_percent |
| `planning.scenario.simulated` | scenario | campaign_id, placement_id, dry_run, error count |

Все audit details безопасны — без secrets, tokens, passwords.

---

## Read-Only Guarantees

- ✅ Никаких INSERT/UPDATE/DELETE в router
- ✅ Никаких CampaignBooking/BookingItem конструкторов
- ✅ Никаких Placement/Campaign/InventoryUnit/CapacityRule изменений
- ✅ Никаких generated_manifests записей
- ✅ Никаких Device Gateway вызовов
- ✅ Никаких publication flow вызовов
- ✅ Никаких portal изменений
- ✅ Scenario всегда `dry_run=True`

---

## Файлы

| Файл | Действие | Строк |
|---|---|---|
| `backend/app/domains/planning/router.py` | 🆕 | 293 |
| `backend/app/domains/identity/seed.py` | 🔄 +1 permission, +7 role assignments | +10 |
| `backend/app/main.py` | 🔄 +2 строки (import + include_router) | +2 |
| `backend/tests/test_planning_api_d5_1.py` | 🆕 | 52 tests |

---

## Test Results

| Слой | Тестов | Статус |
|---|---|---|
| D.5.1 targeted | **52/52** | ✅ |
| D.4 targeted | 44/44 | ✅ |
| D.3 targeted | 38/38 | ✅ |
| D.2 targeted | 30/30 | ✅ |
| D.1 targeted | 39/39 | ✅ |
| Inventory existing | 20/20 | ✅ |
| **Planning suite** | **224/224** | ✅ |
| Backend collection | **1630** (0 errors) | ✅ |

### Test Breakdown (52)

| Категория | Тестов |
|---|---|
| Permissions | 5 |
| Availability API | 6 |
| Conflict API | 5 |
| Occupancy API | 6 |
| Scenario API | 5 |
| Inventory Units Availability | 2 |
| Advertiser Scope | 4 |
| Audit | 4 |
| Read-Only Boundaries | 8 |
| Route Registration | 3 |
| Code Source Verification | 4 |

---

## Что не менялось

- Inventory existing API (`/api/inventory/*`)
- Campaigns CRUD
- Placements API
- Bookings CRUD
- Device Gateway (15+11 endpoints)
- Universal Manifest
- Publication flow
- generated_manifests
- Portal existing pages
- Docker/.env
- Миграции / БД

---

## GO ✅ для D.5.2 — Portal Read-Only Planning Visibility
