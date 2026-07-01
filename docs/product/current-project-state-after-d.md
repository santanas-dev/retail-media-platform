# Current Project State After Phase D

> **Дата:** 2026-07-01
> **После:** Phase D Inventory & Planning Closure
> **HEAD:** `bc3657b`

---

## Что закрыто после Phase D

Phase D Inventory & Planning реализована как **read-only/dry-run foundation**.

### Planning Domain (backend)

- **Planning schemas** — 10 Pydantic v2 моделей (AvailabilityQuery, AvailabilityResult, ConflictCheck, ConflictResult, OccupancyQuery, OccupancyResult, OccupancyBucket, OccupancyUnitBreakdown, PlanningScenario, PlanningIssue)
- **Service functions** — `check_availability()`, `check_conflicts()`, `calculate_occupancy()`, `simulate_planning_scenario()` (скелет), `map_placement_to_availability_query()` (скелет)
- **Planning API** — 5 read-only endpoints с `planning.read` permission, RLS (advertiser + store scope), audit events
- **Фильтры** — inventory_unit_id, channel_id, store_id, display_surface_id, logical_carrier_id
- **Non-sellable inventory** — исключается (is_sellable=True)

### Portal Planning Visibility

- Campaign detail: блок «Планирование» (📊) с availability, conflicts, occupancy
- Показывается только при `planning.read` permission
- BackendClient: 4 planning метода

### Security

- `planning.read` permission (7 ролей)
- Advertiser scope через campaign_id/placement_id
- Store scope через store_id
- 4 audit события
- Denied requests не пишут audit

---

## Какие planning capabilities есть

| Capability | Статус |
|---|---|
| Проверка доступности инвентаря | ✅ API + portal |
| Обнаружение конфликтов размещения | ✅ API + portal |
| Расчёт занятости | ✅ API + portal |
| Dry-run сценарий | ✅ API (скелет) |
| Фильтрация по 5 измерениям | ✅ |
| Advertiser scope enforcement | ✅ |
| Store scope enforcement | ✅ |
| Audit trail | ✅ |

---

## Что planning пока не делает

- ❌ Создание бронирований (CampaignBooking/BookingItem)
- ❌ Reservation workflow
- ❌ Planning approval flow
- ❌ Occupancy snapshots
- ❌ ClickHouse аналитика
- ❌ Portal planning CRUD
- ❌ Auto-reservation при campaign submit
- ❌ Integration с real publish

---

## Backend Baseline

| Метрика | Значение |
|---|---|
| Collected | 1660 |
| Passed | 1613 |
| Failed (pre-existing) | 47 (KSO readiness) |
| Collection errors | 0 |

### Key Suites

| Suite | Tests |
|---|---|
| Planning (D.1–D.5.1.1) | 254/254 |
| Inventory existing | 20/20 |
| Device Gateway | 195/195 |
| Campaigns | ~200+ |
| Other domains | ~950+ |

---

## Portal Baseline

| Метрика | Значение |
|---|---|
| Collected | 930 |
| Passed | 890 |
| Skipped | 32 |
| Errors (pre-existing) | 8 (live integration) |

---

## Deferred Items

- Booking/reservation creation workflow
- Planning approval flow
- Occupancy snapshots table
- ClickHouse analytics integration
- Portal planning CRUD
- Auto-reservation при campaign submit
- Integration с real publish
- Advanced day/hour occupancy granularity
- `simulate_planning_scenario()` полноценная реализация

---

## Следующий этап

**E.0 — Pre-E Audit (KSO First Channel)**: Design Gate перед реализацией KSO Adapter на универсальной модели.
