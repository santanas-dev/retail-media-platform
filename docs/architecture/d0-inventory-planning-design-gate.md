# D.0 — Inventory / Planning Design Gate

> **Дата:** 2026-07-01
> **Этап:** D.0 — Pre-D Inventory / Planning Design Gate
> **Предыдущий:** C.5 (Device Gateway Closure, commit `a67a3cf`)
> **Результат:** ✅ — GO для D.1 (Inventory/Planning Schema Contracts)

---

## 1. Executive Summary

**Ключевое открытие:** Inventory domain **уже существует на ~70%** — 4 таблицы, ORM модели, сервисный слой, API endpoints. Planning domain **отсутствует как отдельный слой**, но его функции (конфликты, доступность, загрузка) сегодня не реализованы. Phase D фокусируется на восполнении пробелов без переписывания существующего inventory.

**Текущее состояние:** Есть inventory_units, capacity_rules, bookings, schedule_runs, schedule_items. Нет planning layer, occupancy calculation, conflict detection, availability by surface, планировочных сценариев.

**Рекомендация:** D.1 — формализовать service contracts для Planning domain, интеграцию с Placement, proposal для Gap-таблиц. Без миграций в D.1.

---

## 2. Current State After Phase C

| Слой | Статус |
|---|---|
| Channel Registry (B.1) | ✅ 5 device_types, 6 capability_profiles |
| Device Model (B.2) | ✅ Full PD→LC→DS→CP chain |
| Placement (B.3) | ✅ 12 service functions, 7 endpoints |
| Orchestrator (B.4) | ✅ Contracts, MockAdapter, Simulation |
| Universal Manifest (B.5) | ✅ Schema, Builder, Validation |
| Device Gateway (C) | ✅ 26 endpoints, 195 tests |
| Inventory (partial) | ⚠️ 70% есть, 30% gap |

---

## 3. Existing Inventory/Planning Code

### Уже есть — Inventory Domain (`domains/inventory/`)

| Модель | Таблица | Статус |
|---|---|---|
| `InventoryUnit` | `inventory_units` | ✅ ORM, API, tests |
| `CapacityRule` | `inventory_capacity_rules` | ✅ ORM |
| `CampaignBooking` | `campaign_bookings` | ✅ ORM, связан с campaign_id |
| `BookingItem` | `booking_items` | ✅ ORM, linked to inventory_unit |

**InventoryUnit поля:** code, name, channel_id, store_id, logical_carrier_id, display_surface_id, capability_profile_id, status, is_sellable

**CapacityRule поля:** inventory_unit_id, day_of_week (0-6), time_from, time_to, max_slots, slot_duration_seconds

**CampaignBooking поля:** campaign_id, status (draft/approved/rejected), date_from, date_to, approval flow (created_by, approved_by, approved_at)

**BookingItem поля:** booking_id, inventory_unit_id, booked_spots_per_loop, booked_share_of_voice, reservation_type, date_from, date_to

### Уже есть — Scheduling Domain (`domains/scheduling/`)

| Модель | Таблица | Статус |
|---|---|---|
| `Schedule` | `schedules` | ✅ ORM, API |
| `ScheduleSlot` | `schedule_slots` | ✅ ORM, linked to kso_placements (legacy) |
| `ScheduleRun` | `schedule_runs` | ✅ ORM |
| `ScheduleItem` | `schedule_items` | ✅ ORM, linked to inventory_unit |

### Чего нет — Planning Gap

| Функция | Статус |
|---|---|
| Occupancy calculation per surface/date | ❌ Gap |
| Conflict detection (overlapping bookings) | ❌ Gap |
| Availability by date/channel/store/surface | ❌ Gap |
| Planning scenarios / dry-run | ❌ Gap |
| Priority-based scheduling | ❌ Gap |
| Placement-to-Inventory linking | ❌ Gap |
| Advertiser/Store scope visibility | ❌ Gap |
| Inventory calendar view | ❌ Gap |

---

## 4. Existing Campaign/Placement/Scheduling Flow

```
Campaign (draft)
  │
  ├─ campaign_channels ← каналы кампании
  ├─ campaign_targets ← целевые поверхности (legacy KSO)
  │
  ▼
Placement (created after campaign submit)
  │
  ├─ placement_targets ← display_surfaces (universal)
  ├─ channel_id ← канал размещения
  │
  ▼
[GAP: Нет Planning проверки перед Placement]
  │
  ▼
Orchestrator (B.4)
  │
  ├─ AdapterContract
  ├─ AdapterPayloadDraft
  │
  ▼
UniversalManifestV1 (B.5, dry-run/preview)
```

**Gap:** Placement создаётся без проверки доступности инвентаря, без occupancy check, без конфликта с существующими размещениями.

---

## 5. Inventory/Planning Responsibility

**Inventory domain должен:**
1. Предоставлять список `InventoryUnit` с доступными ресурсами
2. Рассчитывать ёмкость (capacity) для inventory_unit по дням/времени
3. Отслеживать бронирования (bookings) и их статус

**Planning domain должен (новый):**
1. Рассчитывать `occupancy` для каждой display_surface на каждый день
2. Детектить конфликты (пересечение по времени, превышение ёмкости)
3. Проверять `availability` перед созданием Placement
4. Предлагать `planning scenarios` (dry-run: "что если разместить здесь")
5. Генерировать `occupancy_snapshots` для аналитики

---

## 6. What Inventory / Planning Is Not

- **Не** Device Gateway (не делает device auth, не общается с устройствами)
- **Не** Publication/Publish (не пишет generated_manifests, не вызывает generate_manifests/publish_batch)
- **Не** Universal Manifest builder
- **Не** KSO Adapter
- **Не** PoP Analytics
- **Не** Portal UI (планировочный UI позже, как read-only в portal или admin)

---

## 7. Proposed Domain Boundaries

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PLANNING (NEW)                                │
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐    │
│  │ availability  │   │  conflict    │   │     occupancy        │    │
│  │   checker     │   │  detector    │   │     calculator       │    │
│  └──────┬───────┘   └──────┬───────┘   └──────────┬───────────┘    │
│         │                  │                       │                │
│         └──────────────────┼───────────────────────┘                │
│                            │                                        │
│                   ┌────────▼────────┐                               │
│                   │ planning engine  │                              │
│                   └────────┬────────┘                               │
└────────────────────────────┼────────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    ┌─────▼─────┐    ┌───────▼───────┐   ┌──────▼──────┐
    │ Inventory │    │  Placement    │   │  Campaign   │
    │  Units    │    │  (B.3)        │   │  Booking    │
    └───────────┘    └───────────────┘   └─────────────┘
```

---

## 8. Data Model Assessment

### Существующие таблицы

| Таблица | Использование в Planning |
|---|---|
| `inventory_units` | ✅ Базовый юнит инвентаря |
| `inventory_capacity_rules` | ✅ Ёмкость по дням/времени |
| `campaign_bookings` | ✅ Бронирования кампаний |
| `booking_items` | ✅ Привязка booking ↔ inventory_unit |
| `schedule_items` | ✅ Сгенерированные слоты |
| `placements` | ✅ Размещения (universal) |
| `placement_targets` | ✅ Связь placement ↔ display_surface |

### Предлагаемые новые таблицы (D.2+, не сейчас)

| Таблица | Назначение | Приоритет |
|---|---|---|
| `occupancy_snapshots` | Снапшот загрузки (surface+date+hour+slots) | D.4 |
| `planning_scenarios` | Dry-run сценарий (какие placements затронуты) | D.5 |
| `planning_conflicts` | Зафиксированные конфликты | D.3 |

---

## 9. Proposed Phase D Data Model

**D.1 (Contracts only — no migrations):**

- Pydantic schemas для:
  - `AvailabilityQuery` (channel_id, store_id, display_surface_id, date_from, date_to)
  - `AvailabilityResult` (available_slots, booked_slots, total_slots)
  - `ConflictCheck` (placement_ids, overlapping dates/times)
  - `ConflictResult` (has_conflict, details)
  - `OccupancySnapshot` (surface_id, date, hour, slot_fill_rate, total_capacity)
  - `PlanningScenario` (dry_run: source_placement + proposed_changes)

**D.2 (Availability calculation):**

- Service functions без API:
  - `get_surface_capacity(surface_id, date)` → total_slots
  - `get_booked_slots(surface_id, date)` → booked_count
  - `get_available_slots(surface_id, date)` → available

**D.3 (Conflict detection):**

- Service functions:
  - `check_placement_conflicts(placement)` → list[Conflict]
  - `check_date_overlap(a, b)` → bool

**D.4 (Occupancy):**

- `occupancy_snapshots` таблица (migration)
- `calculate_daily_occupancy(surface_id, date)` → OccupancySnapshot

---

## 10. API Decision

**D.1: ❌ API не нужен. Schema + contracts only.**

**D.2–D.3: ❌ API не нужен. Service layer only.**

**D.4+: Возможно API позже:**
- `GET /api/inventory/availability` — read-only для portal
- `POST /api/planning/check` — admin dry-run
- `GET /api/planning/occupancy` — admin portal only
- `POST /api/planning/reserve` — только после approval gate

---

## 11. Security / RLS / Audit Design

**Scope:**
- Advertiser: видит только свои кампании/бронирования
- Internal user: видит инвентарь согласно store/channel permissions
- Admin: полный доступ

**Audit events (planned):**
- `inventory.availability.checked` — кто и когда запросил доступность
- `inventory.reservation.created` — создание бронирования
- `inventory.reservation.cancelled` — отмена
- `planning.conflict.detected` — обнаружен конфликт
- `planning.scenario.created` — создан сценарий

**Безопасность:**
- Нет device credentials в inventory/planning
- Нет Gateway auth вызовов
- Нет секретов в ответах
- Advertiser scope enforced через RLS

---

## 12. Integration With Placement

**Как Placement должен использовать Planning:**
1. Перед созданием Placement: `availability_check(placement)`
2. Если конфликт: `warn` или `block` в зависимости от policy
3. Placement.targets должны проверять `surface.availability`
4. Приоритет: `placement.priority` влияет на кто получает конфликтный слот

**Что не ломать:**
- Placement API (7 endpoints) — не менять
- Placement service (12 функций) — не менять
- Placement model — не менять

---

## 13. Integration With Campaign Workflow

**Campaign → Planning flow:**
1. Campaign draft: инвентарь **не блокируется**
2. Campaign submit: `availability_preview()` — показать доступность
3. Campaign approve: `reserve_inventory()` — зарезервировать слоты
4. Campaign placement: `create_placement()` — сейчас без планирования, позже с проверкой

**Что не ломать:**
- Campaign submit/approve flow
- Maker-checker
- Campaign status lifecycle

---

## 14. Integration With Orchestrator / Gateway

**Planning не должен:**
- Вызывать Device Gateway API
- Делать device auth
- Писать generated_manifests
- Вызывать generate_manifests/publish_batch
- Импортировать PublicationBatch/ManifestVersion

**Planning может позже:**
- Быть источником `availability` для Orchestrator Context
- Передавать `conflict_info` в Orchestrator для адаптера

---

## 15. Test Strategy

**D.1:** Schema validation tests (Pydantic models)

**D.2–D.3:**
- Availability for empty inventory
- Availability with existing conflicting booking
- Overlapping date ranges
- Channel mismatch
- Surface capacity conflict
- Priority handling
- Advertiser scope

**D.4:**
- Daily occupancy calculation
- No Gateway calls
- No generated_manifests writes
- No publication flow changes

---

## 16. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Placement API требует planning до создания | 🟡 Medium | Planning — advisory (warn/block опционально) |
| CampaignBooking использует legacy booking_items | 🟡 Medium | Booking → Placement через planning bridge |
| Occupancy calculation требует много данных | 🟢 Low | Кеширование/снапшоты, не real-time |
| Advertiser scope конфликтует с inventory visibility | 🟡 Medium | Inventory доступен только через planning API с RLS |
| Миграции для новых таблиц (D.4) | 🟢 Low | Отдельный approval gate |

---

## 17. What Phase D Must Not Break

- Device Gateway (26 endpoints)
- Universal Manifest schema/builder
- Placement API (7 endpoints)
- Campaign submit/approve flow
- Publication flow / generated_manifests
- KSO legacy projection
- PoP ingestion
- Portal
- Admin API
- Auth model

---

## 18. Recommended Phase D Implementation Split

| Этап | Содержание | Миграции? | API? |
|---|---|---|---|
| **D.0** | Design Gate | ❌ | ❌ |
| **D.1** | Planning schemas + service contracts | ❌ | ❌ |
| **D.2** | Availability calculation | ❌ | ❌ |
| **D.3** | Conflict detection | ❌ | ❌ |
| **D.4** | Occupancy snapshots | ✅ (1 table) | ❌ |
| **D.5** | Planning API or portal read-only | TBD | ✅ (read-only) |
| **D.6** | Closure gate | Только docs | ❌ не надо |

---

## 19. GO / NO-GO for D.1

**GO ✅ для D.1 — Inventory/Planning Schema & Service Contracts.**

**Условия:**
- Только Pydantic схемы + service contracts
- Без миграций
- Без API endpoints
- Без изменений Placement/Campaign/Publication
- Без записи в БД
