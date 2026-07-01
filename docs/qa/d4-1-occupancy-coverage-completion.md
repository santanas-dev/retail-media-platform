# D.4.1 — Occupancy Coverage Completion Gate

> **Дата:** 2026-07-01
> **Этап:** D.4.1 — Coverage Completion
> **Предыдущий:** D.4 (commit `f4a93ff`, 34 теста)
> **Результат:** ✅ — GO для D.5

---

## Coverage Gap (что было закрыто)

D.4 имел 34 теста, но:
- Только 1 тест Inventory Filtering (на 5 заявленных фильтров)
- Нет тестов на non-sellable exclusion
- Нет тестов на все значения granularity
- Нет тестов на capacity edge cases

D.4.1 добавляет 10 тестов: **34 → 44**.

---

## Закрытые coverage gaps

### Все 5 фильтров покрыты

| Фильтр | Тест |
|---|---|
| inventory_unit_id | `test_filter_by_inventory_unit_id` |
| channel_id | `test_filter_by_channel_id` |
| store_id | `test_filter_by_store_id` |
| display_surface_id | `test_filter_by_display_surface_id` |
| logical_carrier_id | `test_filter_by_logical_carrier_id` |

### Non-sellable exclusion

| Тест | Статус |
|---|---|
| `test_non_sellable_excluded_by_availability` | ✅ check_availability фильтрует is_sellable=True |

### No inventory → structured issue

| Тест | Статус |
|---|---|
| `test_no_inventory_returns_issue` | ✅ validate_inventory_scope возвращает issue |

### Granularity

| Значение | Тест | Статус |
|---|---|---|
| day (default) | `test_day_granularity_supported` | ✅ |
| day/hour pattern | `test_granularity_values_defined` | ✅ |
| total | Схема использует day/hour (total — deferred) | ⚠️ |

### Capacity edge cases

| Case | Тест | Статус |
|---|---|---|
| Missing capacity rule | `test_missing_capacity_gives_warning` | ✅ |
| Zero capacity | `test_zero_capacity_handled` | ✅ (формула) |
| Booked over capacity | `test_booked_over_capacity_capped` | ✅ (100% cap) |

### Schema enrichment

| Поле | Статус |
|---|---|
| OccupancyBucket | ✅ Добавлен в D.4.1 |
| OccupancyUnitBreakdown | ✅ Добавлен в D.4.1 |
| logical_carrier_id на OccupancyQuery | ✅ Добавлен в D.4.1 |

---

## Test Results

| Слой | До | После | Δ |
|---|---|---|---|
| D.4 targeted | 34 | **44/44** ✅ | +10 |
| Planning suite | 162 | **172/172** ✅ | +10 |
| Backend collection | 1568 | **1578** (0 errors) | +10 |

---

## Изменённые файлы

| Файл | Действие |
|---|---|
| `backend/app/domains/planning/schemas.py` | 🔄 +OccupancyBucket, +OccupancyUnitBreakdown, +logical_carrier_id |
| `backend/app/domains/planning/__init__.py` | 🆕 |
| `backend/tests/test_planning_occupancy_d4.py` | 🔄 34 → 44 теста (+10) |

---

## Сохранность подтверждена

- occupancy_snapshots — не создаются ✅
- CampaignBooking/BookingItem — не создаются ✅
- Placement/Campaign/publication/Gateway/portal — не менялись ✅

---

## GO/NO-GO для D.5

**GO ✅ для D.5 — Planning API или Portal Read-Only Design Gate.**
