# D.3 — Conflict Detection

> **Дата:** 2026-07-01
> **Этап:** D.3 — Conflict Detection
> **Предыдущий:** D.2 (commit `7c76865`)
> **Результат:** ✅ — GO для D.4 (Occupancy Calculation)

---

## Что реализовано

### `check_conflicts(db, query: ConflictCheck) → ConflictResult`

Полноценная проверка конфликтов с использованием availability engine:

1. **Валидация:** date range, SOV 0-100, spots ≥ 0
2. **Placement mapping:** placement_id → PlacementTarget.display_surface_id
3. **Scope validation:** требуется хотя бы inventory_unit_id или display_surface_id
4. **Availability delegation:** ConflictCheck → AvailabilityQuery → check_availability()
5. **Conflict enrichment:** каждый AvailabilityResult.conflict обогащается:
   - existing_campaign_id
   - existing_booking_id
   - existing_booking_item_id
6. **Результат:** ConflictResult (has_conflict, conflicts[], warnings[], errors[])

---

## Поддержанные conflict types

| Тип | Условие |
|---|---|
| share_of_voice_exceeded | requested_sov > available_sov |
| capacity_exceeded | requested_spots > available_spots |
| (date_overlap) | Встроен в availability calculation через ranges_overlap |

## Issue codes

| Code | Severity |
|---|---|
| PLACEMENT_NOT_FOUND | error |
| PLACEMENT_TARGET_NOT_FOUND | warning |
| NO_CONFLICT_SCOPE | error |

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

## Date Overlap

- `ranges_overlap(a_from, a_to, b_from, b_to)` — **inclusive** на обоих концах
- D1-D10 и D10-D10 → overlap = True
- Используется в check_availability() для фильтрации пересекающихся BookingItem

---

## Placement Mapping

1. `query.placement_id` → `Placement` lookup
2. `PlacementTarget` → `display_surface_id`
3. `display_surface_id` → AvailabilityQuery
4. Если placement не найден → PLACEMENT_NOT_FOUND error
5. Если target без display_surface → PLACEMENT_TARGET_NOT_FOUND warning
6. Без scope → NO_CONFLICT_SCOPE error

---

## Test Results

| Слой | Результат |
|---|---|
| **D.3 targeted (NEW)** | **38/38** ✅ |
| D.2 targeted | 30/30 ✅ |
| D.1 targeted | 39/39 ✅ |
| Inventory existing | 20/20 ✅ |
| **Planning suite** | **128/128** ✅ |
| Backend collection | **1534** (0 errors) |

### Тестовые классы D.3

| Класс | Тестов | Фокус |
|---|---|---|
| TestD2FilterCoverage | 5 | Все 5 фильтров покрыты |
| TestValidation | 3 | Date/SOV/spots validation |
| TestDateOverlap | 5 | Inclusive, aggregation |
| TestBookingStatuses | 6 | 3 consume, 3 ignored |
| TestConflictTypes | 3 | SOV/capacity/overlap |
| TestPlacementMapping | 4 | Placement→target→surface |
| TestCheckConflictsService | 4 | ConflictResult, scope, has_conflict |
| TestReadOnlyBoundary | 8 | No DB write, no bad imports |

---

## Сохранность подтверждена

- CampaignBooking/BookingItem — не создаются ✅
- Placement/Campaign — не меняются ✅
- Publication flow — не меняется ✅
- generated_manifests — не пишутся ✅
- Device Gateway — не импортируется ✅
- Universal Manifest — не импортируется ✅
- Portal — не импортируется ✅

---

## Файлы изменены

| Файл | Действие |
|---|---|
| `backend/app/domains/planning/service.py` | 🔄 Skeleton → полный check_conflicts() |
| `backend/tests/test_planning_conflicts_d3.py` | 🆕 38 тестов |

---

## GO/NO-GO для D.4

**GO ✅ для D.4 — Occupancy Calculation.**
