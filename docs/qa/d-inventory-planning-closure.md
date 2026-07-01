# D — Inventory & Planning Closure Gate

> **Дата:** 2026-07-01
> **Этап:** D.6 — Phase D Closure
> **Предыдущий:** D.5.2 (commit `bc3657b`)
> **Результат:** ✅ GO для E.0 — Pre-E Audit

---

## 1. Executive Summary

Phase D Inventory & Planning реализована как **read-only/dry-run foundation** без создания бронирований. Реализованы: schemas, service functions (availability, conflicts, occupancy, scenario), Planning API (5 endpoints), portal read-only visibility. Booking/reservation workflow отложен на последующие фазы.

---

## 2. D Scope

| Этап | Commit | Что сделано |
|---|---|---|
| D.0 | `76e6790` | Design Gate — ~70% готовности inventory, gap analysis |
| D.1 | `e8fe379` | Schemas (10 Pydantic моделей) + Service Contracts |
| D.1.1 | `5c421a4` | Inventory existing tests baseline fixed (19 импорт-ошибок) |
| D.2 | `7c76865` | `check_availability()` — 30 тестов |
| D.3 | `26d750c` | `check_conflicts()` — 38 тестов |
| D.4 | `f4a93ff` | `calculate_occupancy()` — 34 теста |
| D.4.1 | `b0e4904` | Coverage completion — 44 теста (+10 фильтров) |
| D.5 | `853fcad` | Design Gate — API vs Portal decision |
| D.5.1 | `da90835` | Planning API — 5 endpoints, `planning.read`, RLS, audit |
| D.5.1.1 | `46e241a` | Security/RLS/Regression Gate — +30 тестов |
| D.5.2 | `bc3657b` | Portal Read-Only Planning Visibility |

---

## 3. D Commits (11)

```
bc3657b D.5.2 — Portal Read-Only Planning Visibility
46e241a D.5.1.1 — Planning API Security / RLS / Regression Gate
da90835 D.5.1 — Planning API Read-Only / Dry-Run Endpoints
853fcad D.5 — Planning API / Portal Read-Only Design Gate
b0e4904 D.4.1 — Occupancy Coverage Completion Gate
f4a93ff D.4 — Occupancy Calculation
26d750c D.3 — Conflict Detection
7c76865 D.2 — Availability Calculation
5c421a4 D.1.1 — Inventory Existing Tests Baseline
e8fe379 D.1 — Inventory / Planning Schema & Service Contracts
76e6790 D.0 — Inventory / Planning Design Gate
```

---

## 4. Created Components

### 4.1 Backend — Planning Domain

| Файл | Назначение | Строк |
|---|---|---|
| `backend/app/domains/planning/__init__.py` | Package init | 1 |
| `backend/app/domains/planning/schemas.py` | 10 Pydantic v2 моделей | 196 |
| `backend/app/domains/planning/service.py` | 5 service functions | 465 |
| `backend/app/domains/planning/router.py` | 5 API endpoints | 339 |

### 4.2 Portal — Planning Block

| Файл | Назначение |
|---|---|
| `apps/portal-web/backend_client.py` | +4 planning метода (+95 строк) |
| `apps/portal-web/main.py` | +planning data fetch в campaign detail (+58 строк) |
| `apps/portal-web/templates/pages/campaigns_detail.html` | +Planning block (📊) (+58 строк) |

### 4.3 Tests

| Файл | Тестов |
|---|---|
| `backend/tests/test_planning_d1.py` | 39 |
| `backend/tests/test_planning_availability_d2.py` | 30 |
| `backend/tests/test_planning_conflicts_d3.py` | 38 |
| `backend/tests/test_planning_occupancy_d4.py` | 44 |
| `backend/tests/test_planning_api_d5_1.py` | 52 |
| `backend/tests/test_planning_api_d5_1_1.py` | 30 |
| `backend/tests/test_inventory_engine_441.py` | 20 |
| `apps/portal-web/tests/test_planning_portal_d5_2.py` | 27 |

### 4.4 Documentation (12 QA + 2 Architecture)

| Файл | Фаза |
|---|---|
| `docs/architecture/d0-inventory-planning-design-gate.md` | D.0 |
| `docs/architecture/d5-planning-api-portal-readonly-design-gate.md` | D.5 |
| `docs/qa/d1-inventory-planning-schema-service-contracts.md` | D.1 |
| `docs/qa/d1-1-inventory-existing-tests-baseline.md` | D.1.1 |
| `docs/qa/d2-availability-calculation.md` | D.2 |
| `docs/qa/d3-conflict-detection.md` | D.3 |
| `docs/qa/d4-occupancy-calculation.md` | D.4 |
| `docs/qa/d4-1-occupancy-coverage-completion.md` | D.4.1 |
| `docs/qa/d5-1-planning-api-readonly.md` | D.5.1 |
| `docs/qa/d5-1-1-planning-api-security-rls-regression.md` | D.5.1.1 |
| `docs/qa/d5-2-portal-planning-readonly.md` | D.5.2 |
| `docs/qa/d-inventory-planning-closure.md` | D.6 |

---

## 5. Inventory/Planning Service Summary

| Функция | Назначение | Статус |
|---|---|---|
| `check_availability()` | Расчёт доступности инвентаря | ✅ |
| `check_conflicts()` | Обнаружение конфликтов размещения | ✅ |
| `calculate_occupancy()` | Расчёт занятости по гранулярности day | ✅ |
| `simulate_planning_scenario()` | Dry-run сценарий | ✅ (скелет) |
| `map_placement_to_availability_query()` | Маппинг Placement → AvailabilityQuery | ✅ (скелет) |

Все функции **read-only** — только SELECT, без INSERT/UPDATE/DELETE.

---

## 6. Availability Summary

- Фильтры: inventory_unit_id, channel_id, store_id, display_surface_id, logical_carrier_id
- Non-sellable inventory excluded (is_sellable=True)
- CapacityRule lookup (CAPACITY_RULE_MISSING warning если нет)
- Booking statuses: approved, active, published
- SOV + spots calculation с capping на 100%
- Unit-level availability breakdown
- 30 targeted tests

---

## 7. Conflict Detection Summary

- Inclusive date range overlap
- Placement → PlacementTarget → display_surface resolution
- Enrichment существующих бронирований (campaign_id, booking_id, booking_item_id)
- Delegation в check_availability()
- 38 targeted tests

---

## 8. Occupancy Summary

- OccupancyResult с buckets (day) и units breakdown
- Granularity: day (default), hour (deferred)
- Zero capacity handled safely
- Missing capacity rule gives warning
- Booked over capacity capped at 100%
- 44 targeted tests

---

## 9. Planning API Summary

| Метод | Endpoint | Permission |
|---|---|---|
| GET | `/api/planning/availability` | `planning.read` |
| POST | `/api/planning/check-conflicts` | `planning.read` |
| GET | `/api/planning/occupancy` | `planning.read` |
| POST | `/api/planning/scenario` | `planning.read` |
| GET | `/api/planning/inventory-units/availability` | `planning.read` |

RLS: advertiser scope через campaign_id/placement_id, store scope через store_id.
Audit: 4 события (availability.checked, conflict.checked, occupancy.viewed, scenario.simulated).
82 targeted tests (52+30).

---

## 10. Portal Read-Only Summary

- Campaign detail: блок «Планирование» (📊) с availability/conflicts/occupancy
- Показывается только при `planning.read` permission
- Backend 403 → блок скрыт
- Backend unavailable → «Данные планирования пока недоступны.»
- Нет конфликтов → «Конфликтов не найдено.»
- Нет CRUD-кнопок, нет JS/CDN/localStorage
- 27 targeted tests

---

## 11. Security / RLS / Audit Summary

| Аспект | Статус |
|---|---|
| `planning.read` permission | ✅ в seed, 7 ролей |
| `device_service` без `planning.read` | ✅ |
| `planning.manage` не существует | ✅ |
| Advertiser scope (campaign_id) | ✅ |
| Advertiser scope (placement_id) | ✅ |
| Store scope (store_id) | ✅ |
| Denied → NO audit | ✅ |
| Audit: 4 события | ✅ |
| Audit без secrets | ✅ |
| Portal: без planning.read → скрыто | ✅ |

---

## 12. Read-Only / Data Safety Verification

| Операция | Статус |
|---|---|
| CampaignBooking создание | ❌ не происходит |
| BookingItem создание | ❌ не происходит |
| InventoryUnit изменение | ❌ не происходит |
| CapacityRule изменение | ❌ не происходит |
| Placement изменение | ❌ не происходит |
| Campaign изменение | ❌ не происходит |
| ScheduleRun/ScheduleItem изменение | ❌ не происходит |
| generated_manifests запись | ❌ не происходит |
| Publication flow вызов | ❌ не происходит |
| Device Gateway вызов | ❌ не происходит |
| Portal CRUD buttons/forms | ❌ отсутствуют |
| JS/CDN/localStorage | ❌ отсутствуют |
| Миграции | ❌ не создавались |

Подтверждено: 0 `db.add`/`insert`/`update`/`delete` в planning/router.py и planning/service.py.

---

## 13. Test Results

| Слой | Результат |
|---|---|
| D.1 targeted | 39/39 ✅ |
| D.2 targeted | 30/30 ✅ |
| D.3 targeted | 38/38 ✅ |
| D.4 targeted | 44/44 ✅ |
| D.5.1 targeted | 52/52 ✅ |
| D.5.1.1 targeted | 30/30 ✅ |
| Inventory existing | 20/20 ✅ |
| **Planning suite** | **254/254** ✅ |
| D.5.2 portal targeted | **27/27** ✅ |

---

## 14. Backend Baseline

| Метрика | Значение |
|---|---|
| Collected | **1660** |
| Passed | **1613** |
| Failed (pre-existing) | **47** (KSO readiness) |
| Collection errors | **0** |

Pre-existing failures: KSO readiness tests (не относятся к Planning domain).

---

## 15. Portal Baseline

| Метрика | Значение |
|---|---|
| Collected | **930** |
| Passed | **890** |
| Skipped | 32 |
| Errors (pre-existing) | 8 (live integration) |

---

## 16. Deferred Items

- ❌ Booking/reservation creation workflow
- ❌ Planning approval flow
- ❌ Occupancy snapshots table
- ❌ ClickHouse analytics integration
- ❌ Portal planning CRUD (create/edit/delete bookings)
- ❌ Auto-reservation при campaign submit
- ❌ Integration с real publish
- ❌ Advanced day/hour occupancy granularity
- ❌ Real inventory monetization rules
- ❌ `simulate_planning_scenario()` полноценная реализация
- ❌ `map_placement_to_availability_query()` полноценная реализация

---

## 17. What Next Phase Must Not Break

- Planning API contracts (5 endpoints)
- `planning.read` permission assignments
- RLS advertiser/store scope
- Audit events
- Portal planning block rendering
- Backend read-only boundaries (no writes in planning domain)
- Planning suite: 254/254

---

## 18. GO/NO-GO

### GO ✅ для E.0 — Pre-E Audit (KSO First Channel)

**Phase E начинается с Design Gate / Pre-E Audit**, не с реализации.
E.0 должен оценить готовность к KSO Adapter, не начиная код.

**Причина:** Phase D foundation готов. Следующий логический шаг — вернуться к канальной архитектуре и оценить KSO как первый production channel на универсальной модели.
