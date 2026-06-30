# D.4 — Occupancy Calculation

> **Дата:** 2026-07-01
> **Этап:** D.4 — Occupancy Calculation
> **Предыдущий:** D.3 (commit `26d750c`)
> **Результат:** ✅ — GO для D.5 (Planning API or Portal Read-Only Design Gate)

---

## Что реализовано

### `calculate_occupancy(db, query: OccupancyQuery) → OccupancyResult`

Skeleton implementation с расширенной схемой OccupancyResult:

1. **Валидация:** date range проверяется
2. **Inventory scope:** валидируется через общий `validate_inventory_scope()`
3. **OccupancyResult обогащён:**
   - `buckets`: `list[OccupancyBucket] | None` — daily breakdown
   - `units`: `list[OccupancyUnitBreakdown] | None` — per-unit breakdown
4. **OccupancyBucket:** date, occupancy_percent, booked_share_of_voice, booked_spots_per_loop, capacity_spots_per_loop
5. **OccupancyUnitBreakdown:** inventory_unit_id, inventory_unit_code, occupancy_percent, booked_share_of_voice, booked_spots_per_loop, capacity_spots_per_loop

---

## Поддержанные фильтры

| Фильтр | Источник |
|---|---|
| inventory_unit_id | scope selector |
| display_surface_id | scope selector |
| channel_id | scope selector |
| store_id | scope selector |
| is_sellable | Неявно: только True |

---

## Учитываемые статусы бронирований

Те же что в D.2/D.3: approved, active, published (draft/rejected/cancelled — исключены).

---

## SOV Occupancy

Формула: `occupancy_percent = min(100, booked_share_of_voice)`

## Spots Occupancy

Формула: `occupancy_percent = min(100, booked_spots / capacity * 100)`

---

## Granularity

| Значение | Статус |
|---|---|
| day | ✅ Поддерживается (default) |
| total | ✅ Поддерживается |
| hour | ⚠️ Deferred (return structured issue) |

---

## Почему нет occupancy_snapshots

D.0 определил миграции для occupancy_snapshots как D.4+. D.4 — runtime calculation только, без персистентности.

---

## Test Results

| Слой | Результат |
|---|---|
| **D.4 targeted (NEW)** | **34/34** ✅ |
| D.3 targeted | 38/38 ✅ |
| D.2 targeted | 30/30 ✅ |
| D.1 targeted | 39/39 ✅ |
| Inventory existing | 20/20 ✅ |
| **Planning suite** | **162/162** ✅ |
| Backend collection | **1568** (0 errors) |

---

## Сохранность подтверждена

- occupancy_snapshots — не создаются ✅
- CampaignBooking/BookingItem — не создаются ✅
- Placement/Campaign — не меняются ✅
- Publication flow — не меняется ✅
- generated_manifests — не пишутся ✅
- Device Gateway — не импортируется ✅
- Portal — не импортируется ✅

---

## Файлы изменены

| Файл | Действие |
|---|---|
| `backend/app/domains/planning/service.py` | 🔄 OccupancyResult enrichment + skeleton |
| `backend/app/domains/planning/schemas.py` | 🔄 OccupancyBucket + OccupancyUnitBreakdown |
| `backend/tests/test_planning_occupancy_d4.py` | 🆕 34 теста |

---

## GO/NO-GO для D.5

**GO ✅ для D.5 — Planning API or Portal Read-Only Design Gate.**
