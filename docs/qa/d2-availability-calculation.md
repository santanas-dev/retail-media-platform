# D.2 — Availability Calculation

> **Дата:** 2026-07-01
> **Этап:** D.2 — Availability Calculation
> **Предыдущий:** D.1.1 (commit `5c421a4`)
> **Результат:** ✅ — GO для D.3 (Conflict Detection)

---

## Что реализовано

### `check_availability(db, query: AvailabilityQuery) → AvailabilityResult`

Полный расчёт доступности инвентаря:

1. **Валидация:** date range, requested capacity, scope selectors
2. **Поиск InventoryUnit:** фильтрация по inventory_unit_id, channel_id, store_id, display_surface_id, logical_carrier_id; только `is_sellable=True`
3. **Загрузка существующих бронирований:** CampaignBooking.status ∈ {approved, active, published} + BookingItem в date range
4. **Capacity:** из CapacityRule.max_spots_per_loop
5. **SOV/Spots расчёт:**
   - `available_sov = max(0, 100 - booked_sov)`
   - `available_spots = max(0, capacity - booked_spots)`
6. **Occupancy:** booked_sov % или booked_spots / capacity * 100
7. **Конфликты:** если requested > available → PlanningConflict
8. **Read-only:** нет db.add, нет INSERT/UPDATE/DELETE

---

## Поддержанные Inventory Unit Filters

| Фильтр | Поле AvailabilityQuery |
|---|---|
| inventory_unit_id | inventory_unit_id |
| channel_id | channel_id |
| store_id | store_id |
| display_surface_id | display_surface_id |
| logical_carrier_id | logical_carrier_id |
| is_sellable | Неявно: только True |

---

## Учитываемые статусы бронирований

| Статус | Учитывается |
|---|---|
| approved | ✅ |
| active | ✅ |
| published | ✅ |
| draft | ❌ |
| rejected | ❌ |
| cancelled | ❌ |

---

## Расчёт capacity / SOV / spots / occupancy

| Параметр | Формула |
|---|---|
| Доступный SOV | `max(0, 100 - Σ booked_share_of_voice)` |
| Доступные spots | `max(0, capacity_max_spots - Σ booked_spots)` |
| Occupancy (SOV) | `round(booked_sov, 1)` |
| Occupancy (spots) | `round(booked_spots / capacity * 100, 1)` |
| Occupancy (нет данных) | `None` + warning |

---

## Формирование конфликтов

| Тип | Условие |
|---|---|
| `share_of_voice_exceeded` | requested_sov > available_sov |
| `capacity_exceeded` | requested_spots > available_spots |

Каждый конфликт содержит: conflict_type, severity=error, inventory_unit_id, date_from, date_to, message.

---

## Test Results

| Слой | Результат |
|---|---|
| **D.2 targeted (NEW)** | **30/30** ✅ |
| D.1 targeted | 39/39 ✅ |
| Inventory existing | 20/20 ✅ |
| **D.2 + D.1 + Inventory** | **90/90** ✅ |
| Backend collection | **1496** (0 errors) |

---

## Сохранность подтверждена

- CampaignBooking / BookingItem — не создаются ✅
- Placement / Campaign — не меняются ✅
- Publication flow — не меняется ✅
- generated_manifests — не пишутся ✅
- Device Gateway — не импортируется ✅
- Universal Manifest — не импортируется ✅
- Portal — не импортируется ✅

---

## Файлы изменены

| Файл | Действие |
|---|---|
| `backend/app/domains/planning/service.py` | 🔄 D.1 skeleton → D.2 full implementation |
| `backend/tests/test_planning_availability_d2.py` | 🆕 30 тестов |
| `backend/tests/test_planning_d1.py` | 🔄 D.2 compatibility fixes |

---

## GO/NO-GO для D.3

**GO ✅ для D.3 — Conflict Detection.**
