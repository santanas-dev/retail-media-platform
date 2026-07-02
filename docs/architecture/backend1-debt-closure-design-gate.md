# BACKEND.1.0 — Backend Debt Closure Design Gate

**Date:** 2026-07-02 | **Phase:** BACKEND.1.0 (design gate) | **Status:** READY FOR REVIEW

---

## 1. Executive Summary

AUDIT.0 выявил три критических backend-долга. Code inspection показал, что реальная картина **сложнее**, чем предполагалось в аудите:

- **Publication `publish_batch()` УЖЕ РАБОТАЕТ** — код написан, статусы обновляются, ManifestVersion помечается published. Проблема не в публикации как таковой, а в разрыве цепочки: ManifestVersion (publications domain) → GeneratedManifest (manifests domain) → KSO device endpoint.
- **GeneratedManifest writes ОТСУТСТВУЮТ** — UniversalManifestBuilder явно говорит: «No generated_manifests». KSO adapter — dry-run only. Device Gateway endpoint `/kso/{device_code}/manifest` читает `generated_manifests`, но никто туда не пишет.
- **Booking API ОТСУТСТВУЕТ** — CampaignBooking + BookingItem модели готовы, но нет write-сервиса и API.

**Корректировка AUDIT.0:** Publication real publish работает. Реальная проблема — GeneratedManifest generation + Booking writes.

---

## 2. Audit Findings Referenced

| Документ | Ключевые выводы |
|---|---|
| `full-project-audit.md` | 7 критических блокеров: C1 (publish), C2 (manifest), C3 (booking) |
| `backend-compliance-audit.md` | Backend 85% готов; публикации DRY_RUN, манифесты DRY_RUN |
| `tz-compliance-matrix.md` | Publications: 7 DRY_RUN фич; Manifest: 0 реальных генераций |
| `technical-debt-register.md` | BFD-01 (publish), BFD-02 (manifest), BFD-03 (booking) — все CRITICAL/HIGH |

**Уточнение после code inspection:** BFD-01 (публикация) — НЕ DRY_RUN. `publish_batch()` полностью реализован. Проблема в том, что публикация НЕ создаёт GeneratedManifest.

---

## 3. Actual Backend Debt (corrected)

| ID | Долг | Реальный статус | Code evidence |
|---|---|---|---|
| BFD-01 | Publication real publish | ✅ **WORKS** | `publications/service.py:802 publish_batch()` — fully implemented |
| BFD-02 | Manifest real generation | ❌ **MISSING** | `universal_builder.py:6` — "No generated_manifests" |
| BFD-03 | Booking/reservation | ❌ **NO WRITE API** | Models exist (`CampaignBooking` + `BookingItem`); no write service |

**Реальная проблема — цепочка разорвана:**
```
publish_batch() → ManifestVersion.published ✅
  ↛ GeneratedManifest INSERT ❌ (нет)
    ↛ /kso/{device_code}/manifest → "no_manifest" ❌
```

---

## 4. BACKEND.1 Scope

### IN SCOPE

| Step | Что делаем | Приоритет |
|---|---|---|
| **BACKEND.1.1** | Publication publish verification + feature flag gate | P0 |
| **BACKEND.1.2** | GeneratedManifest writes from published ManifestVersion | P0 |
| **BACKEND.1.3** | Booking/reservation write API | P1 |
| **BACKEND.1.4** | Backend E2E scenario tests (publication → manifest → KSO) | P1 |
| **BACKEND.1.5** | Security / regression gate | P2 |
| **BACKEND.1.6** | Backend debt closure gate | P2 |

### EXPLICITLY OUT OF SCOPE

- 🚫 KSO production switch (separate design gate)
- 🚫 Legacy KSO endpoint change (`/kso/{device_code}/manifest`)
- 🚫 KSO adapter production mode (remains dry-run)
- 🚫 Portal changes (PORTAL.1 — separate phase)
- 🚫 UI/UX redesign (UI.1 — separate phase)
- 🚫 ClickHouse pipeline
- 🚫 mTLS
- 🚫 Real emergency execution
- 🚫 Store pilot
- 🚫 Production switch
- 🚫 Credential rotation
- 🚫 Prometheus/Grafana deployment (configs exist)
- 🚫 Docker/.env changes

---

## 5. Feature Flag Strategy

### Flags

```python
# In app/core/config.py or a feature_flags module
FEATURE_FLAGS = {
    "ENABLE_REAL_PUBLICATION": False,        # default: False (BACKEND.1.1)
    "ENABLE_GENERATED_MANIFEST_WRITE": False, # default: False (BACKEND.1.2)
    "ENABLE_BOOKING_WRITES": False,           # default: False (BACKEND.1.3)
}
```

**Требования:**
- Все три — `False` by default
- Меняются ТОЛЬКО через env: `RETAIL_MEDIA_ENABLE_REAL_PUBLICATION=true`
- Никаких изменений Docker/.env без approval
- Tests проверяют BOTH режимы: flag=off → legacy/dry-run behaviour; flag=on → new behaviour
- Flag=off гарантирует: ни один GeneratedManifest не создаётся, ни один booking не пишется
- Flag=off НЕ ломает существующие 2458 тестов
- Атомарность: если flag=off, все dependent операции возвращают 422 или skip

---

## 6. BACKEND.1.1 — Publication Publish Verification + Feature Flag

### Current State

`publish_batch()` — полностью реализован (publications/service.py:802-880):
- Проверяет статус (не cancelled, не published, должен быть "manifest_generated")
- Проверяет approved ApprovalRequest
- Проверяет approved ManifestVersions
- Обновляет статусы: ManifestVersion→published, PublicationTarget→published, Batch→published
- Пишет audit event: "batch_published"
- Коммитит в БД

### Что делаем в BACKEND.1.1

1. **Feature flag gate:** обернуть `publish_batch()` в проверку `ENABLE_REAL_PUBLICATION`
   - flag=False → 422 с сообщением "Real publication disabled. Set ENABLE_REAL_PUBLICATION=true"
   - flag=True → существующее поведение
2. **Tests:** добавить тесты на flag=off (422) и flag=on (200 + published status)
3. **Verify:** существующие publication тесты не ломаются при flag=off
4. **Document:** статус-машина публикации: draft → manifest_generated → approved → published

### Статусы PublicationBatch

```
draft → manifest_generated → approved → published
  ↓         ↓                    ↓
cancelled  cancelled           cancelled
```

**Transition rules:**
- `draft → manifest_generated`: после `generate_manifests()`
- `manifest_generated → approved`: после approval request approved
- `approved → published`: после `publish_batch()` (BACKEND.1.1)
- Любой статус → cancelled: отмена

---

## 7. BACKEND.1.2 — GeneratedManifest Writes

### Current State

- `GeneratedManifest` модель существует (manifests/models.py)
- FK: device_code → kso_devices, placement_code → kso_placements, campaign_code → campaigns
- Device Gateway endpoint `/kso/{device_code}/manifest` ЧИТАЕТ `generated_manifests`
- UniversalManifestBuilder явно говорит: "No generated_manifests. No KsoPlacement."
- KSO adapter: dry-run only, строит payload но не пишет в БД

### Что делаем в BACKEND.1.2

1. **Manifest generator service** — новый или расширенный модуль:
   ```
   generate_real_manifest(batch_id, target_id) → GeneratedManifest
   ```
   - Принимает опубликованный ManifestVersion
   - Строит KSO-safe payload (используя KSO adapter payload builder)
   - Пишет в `generated_manifests` таблицу
   - Под feature flag `ENABLE_GENERATED_MANIFEST_WRITE`

2. **Интеграция с publish_batch():** после публикации batch'а:
   - Для каждого ManifestVersion → создать GeneratedManifest
   - Или: publish_batch() триггерит manifest generation для каждого target
   - Backend.1.2 делает это явным шагом (не автоматическим сайд-эффектом)

3. **Статусы GeneratedManifest:**
   ```
   generated → published
   ```
   - generated: создан, но не доставлен устройству
   - published: device gateway отдал устройству

4. **Manifest payload:**
   - Использовать существующий `manifest_body_json` (JSON field)
   - Строить через KSO adapter payload builder (уже существует, но dry-run)
   - ВАЖНО: adapter остаётся dry-run в режиме preview, BACKEND.1.2 добавляет write-режим ТОЛЬКО для generated_manifests

5. **Legacy KSO endpoint:**
   - `/kso/{device_code}/manifest` — НЕ МЕНЯТЬ
   - Он уже читает `generated_manifests` — просто начнёт возвращать данные
   - Без отдельного approval gateway НЕ переключается

### Feature Flag Behaviour

| Flag | generate_real_manifest() | /kso/{device_code}/manifest |
|---|---|---|
| OFF | 422 "Manifest generation disabled" | Returns "no_manifest" (как сейчас) |
| ON | Creates GeneratedManifest | Returns manifest data |

---

## 8. BACKEND.1.3 — Booking/Reservation Write API

### Current State

- `CampaignBooking` + `BookingItem` модели готовы
- Поля: status, date_from, date_to, booked_spots_per_loop, booked_share_of_voice, reservation_type
- Unique constraint: (booking_id, inventory_unit_id)
- Planning API: 5 read-only endpoints (availability, conflict, occupancy, scenario, store_capacity)
- **Нет write-сервиса для создания booking**

### Что делаем в BACKEND.1.3

1. **Booking write service:**
   ```
   create_booking(campaign_id, items, date_from, date_to) → CampaignBooking
   update_booking(booking_id, items) → CampaignBooking
   cancel_booking(booking_id) → CampaignBooking
   approve_booking(booking_id) → CampaignBooking
   ```

2. **Booking creation flow:**
   - Клиент вызывает planning availability → получает доступные слоты
   - Клиент вызывает create_booking с выбранными inventory_unit_id + spots
   - Сервис проверяет: availability (re-check перед записью), no overbooking, valid date range
   - Сервис создаёт CampaignBooking + BookingItem'ы
   - Статус: draft → submitted → approved → active → completed/expired

3. **Overbooking prevention:**
   - Перед записью: пересчитать availability с учётом pending/approved booking'ов
   - Использовать существующий `check_availability()` из planning service
   - При конфликте: 409 Conflict с деталями

4. **API endpoints:**
   ```
   POST   /api/bookings                      — create booking
   GET    /api/bookings/{booking_id}         — get booking
   PUT    /api/bookings/{booking_id}         — update booking
   POST   /api/bookings/{booking_id}/submit  — submit for approval
   POST   /api/bookings/{booking_id}/approve — approve
   POST   /api/bookings/{booking_id}/cancel  — cancel
   GET    /api/bookings?campaign_id=X        — list by campaign
   ```

5. **Permission:** `bookings.manage` (новая) + `bookings.approve` (существующая)

### Feature Flag Behaviour

| Flag | Booking API |
|---|---|
| OFF | 422 "Booking writes disabled" |
| ON | Full CRUD |

---

## 9. Dependency Order

### Рекомендованный порядок

```
BACKEND.1.1 (Publication verify + flag)  →  BACKEND.1.2 (Manifest generation)
                                               ↓
BACKEND.1.3 (Booking writes) ─────────────────┤
                                               ↓
                                        BACKEND.1.4 (E2E scenario tests)
                                               ↓
                                        BACKEND.1.5 (Security gate)
                                               ↓
                                        BACKEND.1.6 (Closure gate)
```

### Обоснование

1. **BACKEND.1.1 ПЕРВЫМ** — publication publish уже работает. Нужен только feature flag + тесты. Быстрый win, минимальный риск. Разблокирует цепочку для BACKEND.1.2.

2. **BACKEND.1.2 ВТОРЫМ** — зависит от BACKEND.1.1 (нужен published batch для генерации манифеста). Самый критический gap: без него KSO endpoint не получает данные.

3. **BACKEND.1.3 ТРЕТЬИМ** — НЕ зависит от 1.1/1.2. Может идти параллельно, но лучше последовательно — меньше риск конфликтов. Booking — новый write-путь, требует больше тестов.

4. **BACKEND.1.4 после 1.1+1.2+1.3** — E2E тесты полного сценария: booking → publication → manifest → device gateway.

---

## 10. API Impact

### Новые endpoints

| Endpoint | Метод | Фаза | Permission |
|---|---|---|---|
| (нет новых для 1.1 — только feature flag на существующий) | — | 1.1 | publications.publish |
| `/api/manifests/generate` | POST | 1.2 | publications.manage |
| `/api/bookings` | POST | 1.3 | bookings.manage |
| `/api/bookings/{id}` | GET/PUT | 1.3 | bookings.read/manage |
| `/api/bookings/{id}/submit` | POST | 1.3 | bookings.manage |
| `/api/bookings/{id}/approve` | POST | 1.3 | bookings.approve |
| `/api/bookings/{id}/cancel` | POST | 1.3 | bookings.manage |

### Изменённые endpoints

| Endpoint | Изменение | Фаза |
|---|---|---|
| `POST /api/publication-batches/{id}/publish` | +feature flag gate | 1.1 |
| `GET /api/planning/availability` | +учёт pending booking'ов | 1.3 |

---

## 11. Data Model Impact

### BACKEND.1.1 — НЕТ изменений

Модели не меняются. Только feature flag на уровне сервиса.

### BACKEND.1.2 — НЕТ изменений

`GeneratedManifest` модель уже существует. Только добавление write-сервиса.

### BACKEND.1.3 — НЕТ изменений

`CampaignBooking` + `BookingItem` модели уже существуют. Только добавление write-сервиса.

**Итого: 0 миграций, 0 ALTER TABLE, 0 новых таблиц во всех трёх шагах.**

---

## 12. Migration Decision

**NO MIGRATIONS.** Все необходимые таблицы уже созданы:
- `publication_batches`, `publication_targets`, `manifest_versions`, `manifest_items`, `publication_events` ✅
- `generated_manifests` ✅
- `campaign_bookings`, `booking_items` ✅
- `inventory_units`, `inventory_capacity_rules` ✅

Seed остаётся без изменений.

---

## 13. Security / RLS / Audit Impact

### RLS

| Операция | Scope check |
|---|---|
| `publish_batch()` | Уже проверяет advertiser scope (через campaign_id) |
| `generate_manifest()` | Должен проверять: user может publish (publications.publish) |
| `create_booking()` | Должен проверять: campaign принадлежит advertiser'у пользователя |

### Audit

| Действие | Событие | Фаза |
|---|---|---|
| Batch published | `publication_batch.publish` (уже есть) | 1.1 |
| Manifest generated | `manifest.generate` (новое) | 1.2 |
| Booking created | `booking.create` (новое) | 1.3 |
| Booking approved | `booking.approve` (новое) | 1.3 |

### No-secrets

- GeneratedManifest.manifest_body_json: проверять KSO forbidden keys (уже реализовано в KSO adapter)
- Booking payload: не содержит credentials/токенов

---

## 14. Legacy KSO Compatibility

| Компонент | Статус | BACKEND.1 impact |
|---|---|---|
| `/kso/{device_code}/manifest` | Читает `generated_manifests` | **НЕ МЕНЯТЬ** — начнёт возвращать данные когда таблица заполнится |
| KSO adapter | Dry-run | **НЕ МЕНЯТЬ** — остаётся dry-run для preview |
| Legacy KSO manifest projection | `kso_manifest_projection` | **НЕ МЕНЯТЬ** |
| Legacy KSO PoP | `KsoProofOfPlayEvent` | **НЕ МЕНЯТЬ** |
| Legacy KSO production flow | Отдельный endpoint | **НЕ МЕНЯТЬ** |

**Гарантия:** BACKEND.1 не переключает KSO production endpoint. Не меняет поведение legacy KSO. Только добавляет данные в `generated_manifests`, которые `/kso/{device_code}/manifest` начнёт отдавать.

---

## 15. Testing Strategy

### BACKEND.1.1 — 25+ tests

- Feature flag OFF: publish_batch возвращает 422
- Feature flag ON: publish_batch работает (200 + published статус)
- Status transition: draft→manifest_generated→approved→published
- Нельзя publish без approval
- Нельзя publish cancelled batch
- Нельзя publish уже published batch
- Audit event: batch_published
- No-secrets in response
- Existing tests не ломаются при flag=OFF

### BACKEND.1.2 — 30+ tests

- Feature flag OFF: generate_manifest возвращает 422
- Feature flag ON: GeneratedManifest создаётся
- Manifest payload: нет forbidden keys
- Manifest payload: валидный JSON
- `/kso/{device_code}/manifest` возвращает manifest после генерации
- `/kso/{device_code}/manifest` возвращает "no_manifest" без генерации
- Device Gateway manifest_current использует generated_manifests
- No duplicate manifest_code
- FK constraints: campaign_code, placement_code, device_code
- Rollback: удаление GeneratedManifest не ломает публикацию

### BACKEND.1.3 — 35+ tests

- Feature flag OFF: create_booking возвращает 422
- Feature flag ON: booking создаётся
- Overbooking prevention: 409 при конфликте
- Availability check учитывает pending booking'и
- Нельзя забронировать больше capacity
- Booking status flow: draft→submitted→approved→active
- Cancel booking: освобождает capacity
- Booking items: unique constraint per inventory_unit
- Permission checks: bookings.manage, bookings.approve
- Audit events: booking.create, booking.approve

### BACKEND.1.4 — 20+ tests

- Full E2E: create booking → approve booking → create publication batch → generate manifests → publish batch → verify GeneratedManifest → pull from device gateway
- Dry-run path untouched при flag=OFF
- No secrets in full chain
- All audit events logged

### Регрессия

- Backend collection: 2458 + ~110 new = ~2570 / 0 errors
- Emergency suite: unchanged (414/414)
- H.2-H.4 suites: unchanged

---

## 16. Risk Register

| # | Risk | Severity | Mitigation | Feature Flag | Blocks? |
|---|---|---|---|---|---|
| R1 | Accidental production switch | 🔴 CRITICAL | Feature flags OFF by default; no env changes без approval | ✅ | Store pilot |
| R2 | GeneratedManifest corruption | 🔴 CRITICAL | Payload validation (KSO forbidden keys); checksum/hash | ✅ | KSO endpoint |
| R3 | Legacy KSO breakage | 🔴 CRITICAL | НЕ меняем legacy endpoint/KSO adapter/projection | N/A | Store pilot |
| R4 | Overbooking | 🟠 HIGH | Re-check availability перед записью; 409 на конфликт | ✅ | Portal |
| R5 | Publication without approved creative | 🟠 HIGH | publish_batch уже проверяет approved ApprovalRequest + approved ManifestVersions | ✅ | Store pilot |
| R6 | Manifest for invalid placement | 🟠 HIGH | FK constraint проверяет campaign_code/placement_code/device_code | ✅ | KSO endpoint |
| R7 | Stale manifest | 🟡 MEDIUM | Manifest versioning; status=published → device может кэшировать по hash | N/A | — |
| R8 | Rollback failure | 🟡 MEDIUM | Feature flag OFF возвращает систему в dry-run; GeneratedManifest DELETE не ломает batch | ✅ | — |
| R9 | RLS bypass — advertiser видит чужие booking'и | 🟠 HIGH | Scope check при create_booking (campaign → advertiser) | ✅ | Portal |
| R10 | Booking race condition | 🟡 MEDIUM | DB-level unique constraint + optimistic locking | ✅ | — |

---

## 17. Recommended BACKEND.1 Split

```
BACKEND.1.0 ✅ Design gate (this document)

BACKEND.1.1 — Publication feature flag + verification
  ├── feature flag: ENABLE_REAL_PUBLICATION
  ├── gate publish_batch() behind flag
  ├── tests: flag=off (422) + flag=on (200)
  └── ~25 tests

BACKEND.1.2 — GeneratedManifest writes
  ├── feature flag: ENABLE_GENERATED_MANIFEST_WRITE
  ├── manifest generator service
  ├── integration: published ManifestVersion → GeneratedManifest
  ├── /kso/{device_code}/manifest validation
  └── ~30 tests

BACKEND.1.3 — Booking write API
  ├── feature flag: ENABLE_BOOKING_WRITES
  ├── booking CRUD service
  ├── overbooking prevention
  ├── booking approval workflow
  └── ~35 tests

BACKEND.1.4 — E2E scenario tests
  ├── full chain: booking → publication → manifest → device gateway
  ├── feature flag ON/OFF scenarios
  └── ~20 tests

BACKEND.1.5 — Security / regression gate
  ├── security review (no-secrets, RLS, audit)
  ├── full regression: backend collection + emergency suite
  └── ~0 new tests (validation gate)

BACKEND.1.6 — Backend debt closure gate
  ├── final compliance check
  ├── GO/NO-GO for PORTAL.1
  └── docs
```

---

## 18. GO/NO-GO

| Gate | Decision |
|---|---|
| **BACKEND.1.0 (design gate)** | ✅ **COMPLETE** |
| **BACKEND.1.1 (publication flag)** | 🟢 **GO** — minimal risk, быстрый win |
| **BACKEND.1.2 (manifest generation)** | 🟢 **GO** — after 1.1, критический gap |
| **BACKEND.1.3 (booking writes)** | 🟢 **GO** — after 1.1+1.2, может параллельно |
| **Production switch** | 🚫 **NO-GO** |
| **KSO production switch** | 🚫 **NO-GO** |
| **Store pilot** | 🚫 **NO-GO** |
| **Portal** | 🚫 **NO-GO** (после BACKEND.1) |

---

## ✅ GO для BACKEND.1.1 — Publication Feature Flag Gate
