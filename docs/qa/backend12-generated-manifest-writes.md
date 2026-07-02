# BACKEND.1.2 — GeneratedManifest Writes Feature Flag Gate: QA Report

**Date:** 2026-07-02
**Status:** ✅ COMPLETE
**Git HEAD:** `78e434a` (parent: BACKEND.1.1)
**Phase:** BACKEND.1 — Backend Debt Closure

---

## Проблема, которую закрывает BACKEND.1.2

```
publish_batch() → ManifestVersion.published ✅
но GeneratedManifest НЕ создаётся ❌
→ /kso/{device_code}/manifest → "no_manifest"
```

BACKEND.1.1 защитил публикацию feature flag. BACKEND.1.2 закрывает разрыв: после успешной публикации создаётся `GeneratedManifest` → legacy KSO endpoint видит манифест.

---

## Что сделано

### 1. Feature flag

**Config:** `backend/app/core/config.py`

```python
ENABLE_GENERATED_MANIFEST_WRITE: bool = False  # BACKEND.1.2 — OFF by default
```

- Default: **`False`** (OFF)
- Включается только вместе с `ENABLE_REAL_PUBLICATION=true`

### 2. Bridge-функция

**Service:** `backend/app/domains/publications/service.py`

`create_generated_manifests_for_published_batch(db, batch, user_id) → (int, list[dict])`

Алгоритм:
1. Проверяет `ENABLE_GENERATED_MANIFEST_WRITE` → если OFF, возвращает `(0, [])`
2. Получает published `ManifestVersion` для батча
3. Для каждого target резолвит `device_code` через `PublicationTarget.store_id → KsoDevice`
4. **Идемпотентность:** проверяет `manifest_code = "pub-{batch_id}-{device_code}"` → skip если существует
5. Из `ManifestVersion.manifest_json.schedule.items` строит `ManifestSourceItem`
6. Прогоняет через `build_kso_safe_manifest_projection()` (KSO-валидация)
7. Создаёт `GeneratedManifest(status="published")` с `manifest_body_json = projection.manifest`

### 3. Интеграция в publish flow

**Router:** `backend/app/domains/publications/router.py`

После `service.publish_batch()` → вызов `service.create_generated_manifests_for_published_batch()` → ответ с метаданными.

### 4. Response format

```json
{
  "batch": {...},
  "generated_manifest_created": true,       // было false в BACKEND.1.1
  "generated_manifest_count": 1,             // новое поле
  "generated_manifest_details": [            // новое поле
    {"manifest_code": "pub-...", "device_code": "...", "created": true, "existing": false}
  ],
  "next_step": "legacy_kso_manifest_available"  // или "generated_manifest_write_disabled"
}
```

### 5. Идемпотентность

- `manifest_code = "pub-{batch_id}-{device_code}"` — детерминированный ключ
- Перед INSERT → SELECT проверка → skip если exists
- Без DELETE/DROP/TRUNCATE
- Повторный publish того же батча не создаёт дублей

---

## Legacy KSO compatibility

| Проверка | Статус |
|---|---|
| `/kso/{device_code}/manifest` endpoint не менялся | ✅ source inspection |
| При отсутствии GeneratedManifest → `"no_manifest"` | ✅ сохранено |
| При наличии GeneratedManifest → `"served"` + `manifest_body_json` | ✅ через bridge |
| `kso_manifest_projection` не менялся | ✅ source inspection |
| KSO adapter не менялся | ✅ source inspection |
| Device Gateway не менялся | ✅ source inspection |

---

## Что НЕ менялось

| Constraint | Status |
|---|---|
| Миграции | ✅ 0 |
| DB schema | ✅ 0 DDL |
| Docker/.env | ✅ 0 |
| Portal | ✅ untouched |
| KSO adapter | ✅ untouched |
| Device Gateway | ✅ untouched |
| Universal Manifest builder | ✅ untouched |
| Production switch | ✅ NO-GO |
| ClickHouse | ✅ 0 |
| DROP/DELETE/TRUNCATE | ✅ 0 |

---

## Tests

### BACKEND.1.2 targeted: 43/43 ✅

| Group | Count |
|---|---|
| Feature Flag | 7 |
| Idempotency | 4 |
| Legacy KSO Compatibility | 5 |
| Payload / Format | 6 |
| Permissions / Security | 8 |
| Boundaries | 9 |
| Regression | 4 |
| **Total** | **43** |

### Regression: 125/125 ✅

- BACKEND.1.1: 38/38
- Publication batch workflow: 25/25
- Campaign publication batch: 49/49
- Production manifest API: 13/13

**Grand total: 168/168 — 0 failures**

---

## Files changed

| File | Change |
|---|---|
| `backend/app/core/config.py` | +1 line: `ENABLE_GENERATED_MANIFEST_WRITE` |
| `backend/app/domains/publications/service.py` | +191 lines: bridge function |
| `backend/app/domains/publications/router.py` | +14 / -2 lines: bridge call + response |
| `backend/app/domains/publications/schemas.py` | +2 lines: `generated_manifest_count`, `details` |
| `backend/tests/test_generated_manifest_write_backend12.py` | 🆕 43 tests |
| `backend/tests/test_publication_feature_flag_backend11.py` | test_28 updated |

---

## Decisions

### GO/NO-GO for BACKEND.1.3 (Booking Write API)

**✅ GO**

Rationale:
- Publication → GeneratedManifest цепочка закрыта под двумя feature flags
- Legacy KSO endpoint видит манифест (при ON)
- Идемпотентность обеспечена
- 168 тестов, 0 ошибок
- Booking — независимый домен, можно делать параллельно с BACKEND.1.4 (E2E)

### Key risk for BACKEND.1.3

Booking write API — первая запись в inventory-таблицы (`campaign_bookings`, `booking_items`). Нужен свой feature flag, permission checks, RLS, валидация конфликтов.

---

## Next step

**BACKEND.1.3 — Booking Write API**
- `ENABLE_BOOKING_WRITES` feature flag
- CRUD endpoints для `CampaignBooking` + `BookingItem`
- RLS, permission `bookings.manage`
- Конфликт-валидация
- 35+ тестов
