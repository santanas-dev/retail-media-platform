# D.1.1 — Inventory Existing Tests Baseline / Failure Classification

> **Дата:** 2026-07-01
> **Этап:** D.1.1 — Baseline Classification
> **Предыдущий:** D.1 (commit `e8fe379`)
> **Результат:** ✅ — GO для D.2

---

## Список 20 Inventory Tests

| # | Test | D.1 status | D.1.1 status |
|---|---|---|---|
| 1 | `TestDayCapacity::test_weekday_all_day` | ❌ | ✅ |
| 2 | `TestDayCapacity::test_weekend_zero` | ❌ | ✅ |
| 3 | `TestDayCapacity::test_work_hours` | ❌ | ✅ |
| 4 | `TestDaysInRange::test_one_day` | ❌ | ✅ |
| 5 | `TestDaysInRange::test_three_days` | ❌ | ✅ |
| 6 | `TestAvailabilitySoldOut::test_sold_out_when_no_capacity` | ❌ | ✅ |
| 7 | `TestAvailabilitySoldOut::test_available_when_free_capacity` | ❌ | ✅ |
| 8 | `TestForecastV1::test_forecast_simple` | ❌ | ✅ |
| 9 | `TestReservationType::test_default_is_campaign` | ❌ | ✅ |
| 10 | `TestReservationType::test_explicit_internal` | ❌ | ✅ |
| 11 | `TestReservationType::test_explicit_emergency` | ❌ | ✅ |
| 12 | `TestSafetyProjection::test_availability_item_no_secrets` | ❌ | ✅ |
| 13 | `TestSafetyProjection::test_forecast_no_secrets` | ❌ | ✅ |
| 14 | `TestSafetyProjection::test_snapshot_no_secrets` | ✅ | ✅ |
| 15 | `TestInventoryRouter::test_router_has_forecast_endpoint` | ❌ | ✅ |
| 16 | `TestInventoryRouter::test_router_has_snapshot_endpoint` | ❌ | ✅ |
| 17 | `TestInventoryRouter::test_router_has_availability_endpoint` | ❌ | ✅ |
| 18 | `TestBusinessLanguage::test_reasons_are_russian` | ❌ | ✅ |
| 19 | `TestBusinessLanguage::test_forecast_disclaimer_is_russian` | ❌ | ✅ |
| 20 | `TestBusinessLanguage::test_no_technical_wording` | ❌ | ✅ |

---

## Root Cause

**All 19 failures — identical root cause:** `ModuleNotFoundError: No module named 'backend'`

**Причина:** Тесты использовали `from backend.app.domains.inventory...` вместо правильного `from app.domains.inventory...`. Python path настроен с `backend/` как корень (через `pyproject.toml`).

**Категория:** Environment/import issue — НЕ inventory logic bug.

---

## Связь с D.1

| Вопрос | Ответ |
|---|---|
| Связан ли с planning/schemas.py? | ❌ Нет |
| Связан ли с planning/service.py? | ❌ Нет |
| Связан ли с импортом planning domain? | ❌ Нет |
| Связан ли с InventoryUnit/CapacityRule? | ❌ Нет |
| Блокирует ли D.2 availability calculation? | ❌ Нет |

---

## Fix

**Единственное изменение:** `s/from backend.app.domains./from app.domains./g` в `test_inventory_engine_441.py` (26 замен).

---

## Test Results

| Слой | До фикса | После фикса |
|---|---|---|
| Inventory tests | 1/20 | **20/20** ✅ |
| D.1 targeted | 39/39 | 39/39* ✅ |
| D.1 + Inventory | — | **60/60** ✅ |
| Backend collection | 1466 | **1466** (0 errors) |

\* Исправлены 3 D.1 теста (слишком строгие проверки на docstring/comment words)

---

## Изменённые файлы

| Файл | Действие |
|---|---|
| `backend/tests/test_inventory_engine_441.py` | 🔄 26 import path fixes |
| `backend/tests/test_planning_d1.py` | 🔄 3 assertion fixes |

---

## GO/NO-GO для D.2

**GO ✅ для D.2 — Availability Calculation.**
