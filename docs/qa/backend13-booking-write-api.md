# BACKEND.1.3 — Booking Write API Feature Flag Gate: QA Report

**Date:** 2026-07-02
**Status:** ✅ COMPLETE
**Git HEAD:** `1e04ccd` (parent: BACKEND.1.2)
**Phase:** BACKEND.1 — Backend Debt Closure

---

## Проблема

Booking/reservation API уже реализован, но не защищён feature flag. Любой с `bookings.manage` может создавать/изменять бронирования без ограничений.

BACKEND.1.3 добавляет `ENABLE_BOOKING_WRITES=false` (default OFF) на все write-эндпоинты.

---

## Что обнаружено при code inspection

Booking API **уже полностью реализован**:

### Эндпоинты (inventory/router.py)
| Endpoint | Permission | BACKEND.1.3 guard |
|---|---|---|
| `GET /bookings` | `bookings.read` | ❌ read-only |
| `GET /bookings/{id}` | `bookings.read` | ❌ read-only |
| `POST /bookings` | `bookings.manage` | ✅ `_check_booking_writes_enabled()` |
| `PUT /bookings/{id}` | `bookings.manage` | ✅ |
| `POST /bookings/{id}/reserve` | `bookings.manage` | ✅ |
| `POST /bookings/{id}/confirm` | `bookings.approve` | ✅ |
| `POST /bookings/{id}/cancel` | `bookings.manage` | ✅ |
| `PUT /bookings/{id}/items` | `bookings.manage` | ✅ |
| `GET /bookings/{id}/items` | `bookings.read` | ❌ read-only |

### Сервис (inventory/service.py)
- `create_booking()` — валидация кампании, дат
- `reserve_booking()` — capacity check (`_validate_capacity`), требует items
- `confirm_booking()` — re-validates capacity, sets `approved_by`
- `cancel_booking()` — status → cancelled, no DELETE
- `update_booking()` — только draft bookings

### Planning integration
- `_BOOKING_STATUSES_THAT_CONSUME = {"approved", "active", "published"}`
- `check_availability()` reads `CampaignBooking` + `BookingItem`
- `check_conflicts()` reads overlapping bookings
- `calculate_occupancy()` accounts for bookings

### Модели
- `CampaignBooking`: id, campaign_id FK, status, date_from/to, created_by, approved_by
- `BookingItem`: id, booking_id FK, inventory_unit_id FK, booked_spots_per_loop, unique(booking_id, inventory_unit_id)

---

## Что сделано

### 1. Feature flag
```python
ENABLE_BOOKING_WRITES: bool = False  # config.py — default OFF
```

### 2. Guard function
```python
def _check_booking_writes_enabled():
    if not settings.ENABLE_BOOKING_WRITES:
        raise 422 {"error": "booking_writes_disabled", ...}
```

Вызывается в каждом write-эндпоинте **до** вызова сервиса.

### 3. OFF behavior
- 6 write endpoints → HTTP 422 structured error
- 3 read endpoints → работают без изменений
- Никаких side effects

### 4. ON behavior
- Все write-эндпоинты работают как прежде
- Capacity checks, permission checks, audit — без изменений

---

## Boundaries

| Constraint | Status |
|---|---|
| Миграции | ✅ 0 |
| DB schema | ✅ 0 DDL |
| Docker/.env | ✅ 0 |
| Portal | ✅ untouched |
| Publication flow | ✅ untouched |
| GeneratedManifest | ✅ untouched |
| KSO adapter | ✅ untouched |
| Device Gateway | ✅ untouched |
| Production switch | ✅ NO-GO |
| DROP/DELETE/TRUNCATE | ✅ 0 |

---

## Tests

### BACKEND.1.3 targeted: 57/57 ✅

| Group | Count |
|---|---|
| Feature Flag OFF | 8 |
| Feature Flag ON | 10 |
| Permissions / Security | 9 |
| Boundaries | 12 |
| Capacity / Overbooking | 6 |
| Audit / No-secrets | 4 |
| Regression | 8 |
| **Total** | **57** |

### Full regression: 315/315 ✅

- BACKEND.1.3: 57
- BACKEND.1.1: 38
- BACKEND.1.2: 43
- Publication: 25
- Planning D1: + D2: + D3: + D4:  152

---

## Files changed

| File | Change |
|---|---|
| `backend/app/core/config.py` | +1: `ENABLE_BOOKING_WRITES` |
| `backend/app/domains/inventory/router.py` | +20: import + guard + calls in 6 endpoints |
| `backend/tests/test_booking_write_api_backend13.py` | 🆕 57 tests |

---

## Decisions

### GO/NO-GO for BACKEND.1.4 (E2E Backend Scenario Tests)

**✅ GO**

Все три критических backend-долга закрыты:
- Publication → protected by `ENABLE_REAL_PUBLICATION`
- GeneratedManifest → created under `ENABLE_GENERATED_MANIFEST_WRITE`
- Booking → write endpoints gated by `ENABLE_BOOKING_WRITES`

315 тестов, 0 ошибок. Backend готов к E2E сценарным тестам.

---

## Next step

**BACKEND.1.4 — E2E Backend Scenario Tests**
- Campaign → Booking → Publication → GeneratedManifest → KSO manifest delivery
- Все под feature flags
- ~20 integration/E2E тестов
