# D.1 — Inventory / Planning Schema & Service Contracts

> **Дата:** 2026-07-01
> **Этап:** D.1 — Schema & Service Contracts
> **Предыдущий:** D.0 (Design Gate, commit `76e6790`)
> **Результат:** ✅ — GO для D.2 (Availability Calculation)

---

## Что создано

### Schemas (7 Pydantic v2 моделей)

| Модель | Назначение |
|---|---|
| `AvailabilityQuery` | Запрос доступности инвентаря (scope+dates+capacity) |
| `InventoryUnitAvailability` | Доступность конкретного инвентарного юнита |
| `AvailabilityResult` | Результат проверки доступности |
| `ConflictCheck` | Запрос проверки конфликтов |
| `PlanningConflict` | Один конфликт (тип, severity, даты, message) |
| `ConflictResult` | Результат проверки конфликтов |
| `OccupancyQuery` | Запрос загрузки (scope+dates+granularity) |
| `OccupancyResult` | Результат расчёта загрузки |
| `PlanningScenario` | Сценарий планирования (dry-run) |
| `PlanningIssue` | Структурированная ошибка/предупреждение |

### Service Contracts (5 функций)

| Функция | Описание |
|---|---|
| `check_availability()` | Проверка доступности инвентаря |
| `check_conflicts()` | Проверка конфликтов размещений |
| `calculate_occupancy()` | Расчёт загрузки |
| `simulate_planning_scenario()` | Симуляция сценария (dry-run) |
| `map_placement_to_availability_query()` | Placement → AvailabilityQuery |

### Validation Helpers (4 функции)

| Функция | Описание |
|---|---|
| `validate_date_range()` | date_from ≤ date_to |
| `validate_requested_capacity()` | share 0..100, spots ≥ 0 |
| `validate_inventory_scope()` | At least one scope selector |
| `build_planning_issue()` | Build structured PlanningIssue |

---

## Что D.1 НЕ делает

- ❌ Не создаёт CampaignBooking / BookingItem
- ❌ Не меняет Placement / Campaign
- ❌ Не меняет ScheduleRun / ScheduleItem
- ❌ Не пишет generated_manifests
- ❌ Не вызывает Device Gateway
- ❌ Не вызывает Orchestrator delivery / publish
- ❌ Не делает real publish
- ❌ Не создаёт миграции
- ❌ Не создаёт API endpoints
- ❌ Не меняет portal

---

## Test Results

| Слой | Результат |
|---|---|
| **D.1 targeted (NEW)** | **39/39** ✅ |
| Inventory existing | 1/20 (19 pre-existing) |
| Backend collection | **1466** (0 errors) |

### Тестовые классы

| Класс | Тестов |
|---|---|
| TestAvailabilityQuerySchema | 7 |
| TestConflictCheckSchema | 3 |
| TestOccupancyQuerySchema | 3 |
| TestPlanningScenarioSchema | 3 |
| TestPlanningIssue | 2 |
| TestServiceContracts | 6 |
| TestValidationHelpers | 7 |
| TestD1Boundary | 7 |
| TestInventoryCompatibility | 2 |

---

## Файлы созданы

| Файл | Действие |
|---|---|
| `backend/app/domains/planning/__init__.py` | 🆕 |
| `backend/app/domains/planning/schemas.py` | 🆕 10 Pydantic моделей |
| `backend/app/domains/planning/service.py` | 🆕 5 contracts + 4 helpers |
| `backend/tests/test_planning_d1.py` | 🆕 39 тестов |

---

## Сохранность подтверждена

- CampaignBooking / BookingItem — не создаются ✅
- Placement / Campaign — не меняются ✅
- Publication flow — не меняется ✅
- generated_manifests — не пишутся ✅
- Device Gateway — не импортируется ✅
- Portal — не импортируется ✅
- Inventory models/schemas — импортируются ✅

---

## GO/NO-GO для D.2

**GO ✅ для D.2 — Availability Calculation.**
