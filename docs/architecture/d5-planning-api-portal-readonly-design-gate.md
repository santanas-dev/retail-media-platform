# D.5 — Planning API / Portal Read-Only Design Gate

> **Дата:** 2026-07-01
> **Этап:** D.5 — Design Gate (реализация не начинается)
> **Предыдущий:** D.4.1 (commit `b0e4904`)
> **Результат:** ✅ GO → D.5.1 Planning API (read-only/dry-run)

---

## 1. Executive Summary

D.5 — pure design gate. Проанализированы текущие API, portal, permissions, RLS, audit. Спроектированы options: Planning API и Portal Read-Only. Дана рекомендация.

**Ключевой вывод:** API first, portal after. Backend service layer (D.1–D.4) стабилен и готов к API-обёртке. Portal read-only без API невозможен — portal уже использует backend через BackendClient. Сначала API endpoints, затем portal pages.

---

## 2. Current Phase D State

| Слой | Статус | Тестов |
|---|---|---|
| D.1 — Schemas & Contracts | ✅ | 39/39 |
| D.1.1 — Inventory baseline | ✅ | 20/20 |
| D.2 — Availability | ✅ | 30/30 |
| D.3 — Conflict Detection | ✅ | 38/38 |
| D.4 — Occupancy | ✅ | 44/44 |
| **Planning/Inventory suite** | **✅** | **172/172** |
| Backend collection | ✅ | 1578 (0 errors) |

Service layer полностью read-only, без booking writes, без миграций.

---

## 3. Existing API Surface

### 3.1 Backend Routers (21 total)

| Router | Prefix | Ключевые endpoints |
|---|---|---|
| `inventory/router.py` | `/api` | GET/POST inventory-units, capacity-rules, POST availability, bookings CRUD, forecast, snapshot |
| `campaigns/router.py` | `/api` | CRUD campaigns, submit/approve/reject, channels, targets, placements |
| `channels/placements_router.py` | `/api` | GET/PUT/DELETE placements, targets |
| `identity/router.py` | `/api` | auth, users, roles, permissions, rls-scopes, audit |
| `device_gateway/router.py` | `/api/device-gateway` | 15 device + 11 admin endpoints |
| `media/router.py` | `/api` | creatives upload, moderation |
| `scheduling/router.py` | `/api` | schedules |
| `reports/router.py` | `/api` | reports |
| `publications/router.py` | `/api` | publication packages |

### 3.2 Inventory API (существующий)

Уже существует `POST /api/inventory/availability` с permission `inventory.read`. Использует inventory schemas (старые), **не** планировочные D.1–D.4 schemas. Конфликта имён нет — старый инвентарь использует `inventory.schemas`, а planning — `planning.schemas`.

### 3.3 Permissions Model

| Permission | Resource | Action | Роли с доступом |
|---|---|---|---|
| `campaigns.read` | campaigns | read | admin, manager, approver, viewer, advertiser |
| `campaigns.create` | campaigns | create | admin, manager, advertiser |
| `campaigns.manage` | campaigns | manage | admin, manager |
| `campaigns.approve` | campaigns | approve | admin, approver |
| `inventory.read` | inventory | read | admin, manager, approver, viewer, operator, inventory_manager |
| `inventory.manage` | inventory | manage | admin, inventory_manager |
| `bookings.read` | bookings | read | admin, manager, approver, viewer, advertiser, operator, inventory_manager |
| `bookings.manage` | bookings | manage | admin, manager, advertiser, inventory_manager |
| `bookings.approve` | bookings | approve | admin, approver |

**Нет `planning.*` permissions** — предстоит создать.

### 3.4 RLS (Row-Level Security)

- `UserScopeContext` с advertiser_ids, branch_ids, store_ids, device_codes, campaign_codes
- Admin roles (`system_admin`, `security_admin`) bypass RLS
- `apply_advertiser_rls()` — для campaign-связанных запросов
- `apply_store_rls()` — для store-связанных запросов
- `assert_object_in_advertiser_scope()` — 404 вместо 403
- **InventoryUnit не имеет advertiser_id** — scoping через campaign

### 3.5 Audit

- `audit_business_action()` в `app/domains/audit/service.py`
- Записывает в `admin_audit_events`: actor_user_id, action, target_type, target_ref, details_json
- `FORBIDDEN_DETAILS`: фильтрует secrets/tokens/passwords
- Используется в campaigns, placements
- Для планирования: read-only операции могут не требовать audit (политика portal), но write-like (scenario simulation) — требуют

---

## 4. Existing Portal Surface

### 4.1 Backend Client (`apps/portal-web/backend_client.py`)

1178 строк, httpx-based, все вызовы backend идут через него. Методы:

| Метод | Endpoint |
|---|---|
| `login/me/logout` | `/api/auth/*` |
| `list_campaigns` | `/api/campaigns/test-kso` |
| `list_campaigns_prod` | `/api/campaigns` |
| `create_campaign` | `/api/campaigns/by-code` |
| `get_campaign_by_code` | `/api/campaigns/by-code/{code}` |
| `update_campaign_by_code` | `PATCH /api/campaigns/by-code/{code}` |
| `list_creatives` | `/api/creatives` |
| `upload_creative` | `POST /api/creatives/upload` |
| `list_advertisers` | `/api/advertisers` |
| `list_branches/clusters/stores` | `/api/branches`, `/api/clusters`, `/api/stores` |
| `list_kso_devices` | `/api/devices/kso` |
| moderation methods | `/api/creatives/by-code/{code}/approve`, etc. |

**Нет planning/availability/occupancy методов** — предстоит добавить.

### 4.2 Templates (28 HTML)

| Шаблон | Что показывает |
|---|---|
| `campaigns_detail.html` | Campaign info, creatives, placements, submit/approve actions |
| `placement_detail.html` | Placement info, targets — **read-only**, без кнопок редактирования |
| `inventory.html` | Инвентарь: KPI cards (units, capacity, available, occupancy), forecast |
| `dashboard.html` | Дашборд |
| `campaigns.html`, `campaigns_create.html` | Список и создание кампаний |
| `devices.html`, `device-dashboard.html` | Устройства |
| `creatives.html`, `creative_detail.html` | Креативы |

**Placement detail уже read-only** — portal precedent для planning visibility.

---

## 5. Planning API Option

### 5.1 Proposed Endpoints

Все endpoints **read-only / dry-run**. Ни один не создаёт бронирований.

#### A) `GET /api/planning/availability`

```
Method: GET
Query params: channel_id?, store_id?, display_surface_id?,
              logical_carrier_id?, inventory_unit_id?,
              date_from (required), date_to (required),
              requested_share_of_voice?, requested_spots_per_loop?,
              advertiser_id?, campaign_id?
Response: AvailabilityResult (из planning.schemas)
Permission: planning.read
RLS: advertiser scope через campaign_id (если передан), иначе internal-only
Audit: planning.availability.checked
Risk: Low — read-only, существующий service layer
```

#### B) `POST /api/planning/check-conflicts`

```
Method: POST
Body: ConflictCheck (date_from, date_to, inventory_unit_id?,
      display_surface_id?, placement_id?, requested_sov?, requested_spots?)
Response: ConflictResult
Permission: planning.read
RLS: через placement_id → campaign → advertiser
Audit: planning.conflict.checked
Risk: Low — read-only
```

#### C) `GET /api/planning/occupancy`

```
Method: GET
Query params: channel_id?, store_id?, display_surface_id?,
              logical_carrier_id?, inventory_unit_id?,
              date_from (required), date_to (required),
              granularity? (day|hour)
Response: OccupancyResult (с buckets и units)
Permission: planning.read
RLS: store/channel scope (internal users), advertiser через campaign
Audit: planning.occupancy.viewed (optional — pure read)
Risk: Low — read-only
```

#### D) `POST /api/planning/scenario`

```
Method: POST
Body: PlanningScenario (query + campaign_id? + placement_id?)
Response: PlanningScenario (dry_run=True, enriched with availability/conflict/occupancy)
Permission: planning.read
RLS: advertiser scope через campaign_id
Audit: planning.scenario.simulated
Risk: Medium — симуляция может раскрыть occupancy других рекламодателей
       (mitigation: advertiser scope всегда enforced)
```

#### E) `GET /api/planning/inventory-units/availability`

```
Method: GET
Query params: те же что и availability
Response: упрощённый AvailabilityResult
Permission: planning.read
Risk: Low
```

### 5.2 New Permissions Required

```sql
-- planning domain permissions
INSERT INTO permissions (code, name, resource, action, description) VALUES
('planning.read',  'View planning data', 'planning', 'read',
 'View availability, occupancy, and conflict data'),
('planning.manage', 'Manage planning',     'planning', 'manage',
 'Create/edit planning scenarios (future)');
```

**Для D.5.1 нужен только `planning.read`.** `planning.manage` — deferred.

Роли, получающие `planning.read`:
- `system_admin` (уже имеет все)
- `campaign_manager`
- `advertiser` (scoped через RLS)
- `inventory_manager`
- `approver`

### 5.3 Advertiser Scope Enforcement

```python
# InventoryUnit не имеет advertiser_id → scoping через campaign
# Если передан campaign_id:
#   1. Загрузить campaign
#   2. assert_object_in_advertiser_scope(campaign.advertiser_id, ctx)
#   3. Фильтровать inventory только по campaign placement targets
# Если campaign_id НЕ передан:
#   — internal users: full scope (через store/branch RLS если есть)
#   — advertiser users: только их own campaigns → их own placements → их inventory
```

### 5.4 Store/Channel Scope

```python
# Internal users с store_scope:
#   — apply_store_rls() на InventoryUnit.store_id
#   — или reject если нет store scope
# Internal users с branch_scope:
#   — join stores → filter by branch
```

---

## 6. Portal Read-Only Option

### 6.1 Возможные portal views

| View | Данные | Permissions | Нужен API? |
|---|---|---|---|
| **Campaign detail: planning summary** | Availability + occupancy для campaign placements | `campaigns.read` + `planning.read` | Да — `/api/planning/availability?campaign_id=X` |
| **Placement detail: occupancy card** | OccupancyResult для конкретного placement | `campaigns.read` + `planning.read` | Да — `/api/planning/occupancy?display_surface_id=...` |
| **Inventory page: planning occupancy** | Occupancy по channel/store/surface | `planning.read` | Да — существующий inventory уже показывает KPI |
| **Planning preview page** | Dry-run scenario form + results | `planning.read` | Да — `/api/planning/scenario` |

### 6.2 Portal Architecture

Portal использует `BackendClient` → backend API. **Прямой вызов planning service невозможен** — portal не имеет доступа к SQLAlchemy/моделям. Все данные идут через API.

### 6.3 Placement Detail — Natural Fit

Placement detail уже read-only (шаблон `placement_detail.html`). Идеальное место для planning occupancy card:
- Показать `OccupancyResult` для display_surface_id placement targets
- Без кнопок, без JS, без CDN
- Pure server-side rendering

### 6.4 Implementation Split (portal)

| Шаг | Что |
|---|---|
| D.5.2.1 | BackendClient: `get_planning_occupancy()`, `get_planning_availability()` |
| D.5.2.2 | Placement detail: occupancy card |
| D.5.2.3 | Campaign detail: availability summary |
| D.5.2.4 | Inventory page: планировочная занятость |

---

## 7. Security / RLS / Audit Design

### 7.1 Permission Model

```
Новая permission: planning.read
  resource: planning
  action: read
  description: View availability, occupancy, conflict data

Назначается ролям:
  system_admin       — full access (через admin bypass)
  campaign_manager   — full access
  advertiser         — SCOPED: только свои campaign placement inventory
  inventory_manager  — full access
  approver           — full access
  viewer             — read-only (full)
```

### 7.2 Advertiser Scope (critical)

```python
async def check_planning_availability(
    db: AsyncSession, query: OccupancyQuery, current_user: User
) -> OccupancyResult:
    ctx = await resolve_user_scope_context(db, current_user)

    # Если пользователь — advertiser (scoped)
    if ctx.is_advertiser_scoped:
        # Без campaign_id — вернуть только inventory их кампаний
        # (через campaign → placement target → display_surface → inventory)
        if not query.campaign_id:
            # Найти все inventory, связанные с кампаниями пользователя
            pass  # implementation detail
        else:
            campaign = await get_campaign(query.campaign_id)
            assert_object_in_advertiser_scope(campaign.advertiser_id, ctx)

    # Internal users — store/branch scope
    if ctx.is_store_scoped:
        # apply_store_rls на InventoryUnit.store_id
        pass

    return await calculate_occupancy(db, query)
```

### 7.3 Store/Channel Visibility

```python
# InventoryUnit → store_id → Store → Branch
# Пользователь с branch_scope видит inventory только своих филиалов
# Пользователь с store_scope видит inventory только своих магазинов
# Администратор без scope видит всё
```

### 7.4 Audit Events

| Событие | Когда | Severity |
|---|---|---|
| `planning.availability.checked` | Каждый GET/POST availability | info |
| `planning.conflict.checked` | Каждый POST check-conflicts | info |
| `planning.occupancy.viewed` | Каждый GET occupancy | info (skip если слишком частый) |
| `planning.scenario.simulated` | Каждый POST scenario | info |

**Решение по portal audit:** Portal read-only planning views **не пишут audit** — portal pages рендерятся сервером, запросы к backend API уже пишут audit на backend-стороне. Дублирование не нужно.

### 7.5 Что НЕ пропускаем

- ❌ Device credentials в planning API
- ❌ Gateway auth tokens
- ❌ generated_manifests
- ❌ CampaignBooking creation
- ❌ BookingItem creation
- ❌ Placement mutation
- ❌ Campaign mutation

---

## 8. Data Safety Boundaries

### 8.1 Что D.5 API НЕ делает

| Операция | Статус |
|---|---|
| CampaignBooking создание | ❌ запрещено |
| BookingItem создание | ❌ запрещено |
| Placement изменение | ❌ запрещено |
| Campaign изменение | ❌ запрещено |
| Publication flow | ❌ запрещено |
| generated_manifests запись | ❌ запрещено |
| Device Gateway вызов | ❌ запрещено |
| Real publish | ❌ запрещено |
| ClickHouse/PoP analytics | ❌ запрещено |
| DROP/DELETE/TRUNCATE | ❌ запрещено |
| Миграции | ❌ запрещено |

### 8.2 Что D.5 API делает

| Операция | Статус |
|---|---|
| SELECT из InventoryUnit | ✅ |
| SELECT из CapacityRule | ✅ |
| SELECT из CampaignBooking (только approved/active/published) | ✅ |
| SELECT из BookingItem | ✅ |
| SELECT из Placement/PlacementTarget (для mapping) | ✅ |
| SELECT из Campaign (для advertiser scope) | ✅ |
| Запись audit events | ✅ |

### 8.3 Cross-domain Isolation

```
planning/ → ТОЛЬКО planning.schemas + planning.service
          → НЕ импортирует device_gateway
          → НЕ импортирует publications
          → НЕ импортирует generated_manifests
          → НЕ импортирует universal_builder
          → НЕ импортирует portal
```

---

## 9. Recommendation

### **API first, portal after, D.6 closure gate.**

**Почему API first:**

1. **Backend service layer готов** — D.1–D.4 service функции оттестированы (172 теста), контракты стабильны
2. **Portal требует API** — portal не имеет прямого доступа к БД, все данные через BackendClient → backend API
3. **API — меньший риск** — добавление read-only endpoints с существующими permissions не затрагивает campaign/publication/Gateway
4. **API можно протестировать изолированно** — targeted tests без portal
5. **Portal read-only after API** — когда API готов, portal pages рендерятся поверх существующих endpoints

**Почему НЕ portal first:**
- Portal без API вынужден дублировать planning логику (нарушение single source of truth)
- BackendClient уже зависит от backend API — естественная архитектура
- Portal не имеет доступа к SQLAlchemy сессиям

**Почему НЕ D.6 closure сразу:**
- API — естественное завершение Phase D (Planning domain)
- Без API planning domain остаётся «мёртвым кодом» — сервисы есть, но не вызвать
- API read-only минимален по рискам и усилиям

---

## 10. Recommended Implementation Split

| Шаг | Что | Статус |
|---|---|---|
| **D.5** | Design Gate (этот документ) | ✅ сейчас |
| **D.5.1** | Planning API read-only/dry-run endpoints | → next |
| **D.5.2** | Portal read-only planning visibility | → after API |
| **D.5.3** | Security/regression gate | → after portal |
| **D.6** | Phase D Closure Gate | → final |

### D.5.1 Scope (API)

1. `planning.read` permission + seed
2. `POST /api/planning/check-availability` (основной — POST для сложных query params)
3. `GET /api/planning/occupancy`
4. `POST /api/planning/check-conflicts`
5. `POST /api/planning/scenario`
6. RLS advertiser scope enforcement
7. Audit events для каждого endpoint
8. Targeted tests: 30+ (permissions, scopes, results, no-write, read-only)

### D.5.2 Scope (Portal)

1. BackendClient: `get_planning_occupancy()`, `get_planning_availability()`
2. Placement detail: occupancy card
3. Campaign detail: availability summary
4. Empty states + permission-denied states
5. Pure server-side, no JS/CDN/localStorage

### D.5.3 Scope (Security Gate)

1. All permissions tested
2. All advertiser scopes tested
3. No write side-effects confirmed
4. Backend + portal regression

---

## 11. Test Strategy

### D.5.1 API Tests

```
TestPlanningAPIPermissions:
  - test_planning_read_required
  - test_anonymous_401
  - test_no_permission_403

TestPlanningAPIAdvertiserScope:
  - test_advertiser_sees_own_campaign_inventory
  - test_advertiser_cannot_see_other_campaign_inventory
  - test_advertiser_without_campaign_id_gets_scoped_results
  - test_internal_user_sees_all_inventory
  - test_store_scoped_user_sees_only_store_inventory

TestPlanningAPIAvailability:
  - test_availability_valid_request
  - test_availability_invalid_date_range
  - test_availability_no_inventory
  - test_availability_result_shape

TestPlanningAPIOccupancy:
  - test_occupancy_valid_request
  - test_occupancy_with_granularity
  - test_occupancy_result_shape
  - test_occupancy_buckets

TestPlanningAPIConflicts:
  - test_conflict_valid_request
  - test_conflict_no_scope_error

TestPlanningAPIScenario:
  - test_scenario_dry_run
  - test_scenario_enriched_with_results
  - test_scenario_advertiser_scope

TestPlanningAPIReadOnly:
  - test_no_campaign_booking_created
  - test_no_booking_item_created
  - test_no_placement_changed
  - test_no_campaign_changed
  - test_no_gateway_import
  - test_no_publication_import
  - test_no_generated_manifests
  - test_only_selects

TestPlanningAPIAudit:
  - test_availability_audit_event
  - test_conflict_audit_event
  - test_scenario_audit_event
```

### D.5.2 Portal Tests

```
TestPortalPlanningReadOnly:
  - test_occupancy_card_on_placement_detail
  - test_empty_state_when_no_inventory
  - test_no_crud_buttons
  - test_no_js_cdn_localstorage
  - test_no_raw_uuid_in_ui
  - test_permission_denied_state
  - test_advertiser_scope_in_portal
```

---

## 12. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Advertiser видит чужую occupancy | High | RLS advertiser scope enforced; без campaign_id — только свои |
| Booking creation через API | Critical | Код-ревью: только вызов planning service функций (read-only) |
| Permission escalation | Medium | `planning.read` — минимальная permission, без manage |
| Portal раскрывает internal UUID | Low | sanitize_code фильтр на всех шаблонах |
| Audit spam на occupancy | Low | Skip audit на GET occupancy если слишком частый; только scenario |

---

## 13. What D.5 Must Not Break

| Система | Статус |
|---|---|
| Inventory existing API (`/api/inventory/*`) | ✅ не трогаем |
| Campaigns CRUD | ✅ не трогаем |
| Placements API | ✅ не трогаем |
| Bookings CRUD | ✅ не трогаем |
| Device Gateway (15+11 endpoints) | ✅ не трогаем |
| Universal Manifest | ✅ не трогаем |
| Publication flow | ✅ не трогаем |
| generated_manifests | ✅ не трогаем |
| Portal existing pages | ✅ не трогаем |
| Docker/.env | ✅ не трогаем |
| Миграции | ✅ не создаём |

---

## 14. GO / NO-GO

### GO ✅ для D.5.1 — Planning API read-only/dry-run endpoints

**Причина:**
- Backend service layer стабилен (172 теста)
- API — минимальный риск (read-only endpoints с существующими permissions)
- Portal требует API для planning visibility
- Phase D без API — «мёртвый код» без возможности вызова

**Следующий шаг:** D.5.1 — Planning API (5 endpoints + permissions + RLS + audit + 30+ тестов)
