# C.4 — Manifest Pull Dry-Run / Delivery Validation

> **Дата:** 2026-07-01
> **Этап:** C.4 — Manifest Pull / Delivery Validation (аудит + тесты)
> **Предыдущий:** C.3 (commit `68d0db2`, 44 tests)
> **Результат:** ✅ — GO для C.5

---

## Проверенные manifest endpoints (3)

| # | Endpoint | Тип | Auth |
|---|---|---|---|
| 1 | `GET /api/device-gateway/manifest/current` | Legacy | `authenticate_device()` |
| 2 | `GET /api/device-gateway/kso/{device_code}/manifest` | Legacy KSO | `authenticate_device()` + device_code match |
| 3 | `GET /api/device-gateway/manifest/universal/current` | Universal (C.1) | `authenticate_device()` |

---

## Legacy KSO Delivery

```
Device (JWT + device_code in URL)
    │
    │  GET /api/device-gateway/kso/{device_code}/manifest
    │────────────────────────────────────────────────────→
    │                                                     authenticate_device()
    │                                                     device.device_code ≠ device_code → 403
    │                                                     GeneratedManifest WHERE status="published"
    │                                                     SHA-256 canonical JSON
    │  {status, manifest_version_id, manifest_hash, manifest}
    │◄────────────────────────────────────────────────────
```

**Ключевые свойства:**
- Читает из `GeneratedManifest` (legacy), не UniversalManifestV1
- Проверяет device_code match (device A не может запросить manifest device B)
- Фильтрует по `status = "published"`
- Вычисляет `manifest_hash` через SHA-256
- Возвращает `{status: "no_manifest"}` если нет published manifest
- Нет вызовов `generate_manifests()` / `publish_batch()`
- Read-only: нет `db.add`, нет `db.commit`

---

## Universal Manifest Delivery (C.1)

```
Device (JWT only — no device_code in URL)
    │
    │  GET /api/device-gateway/manifest/universal/current
    │─────────────────────────────────────────────────────→
    │                                                      authenticate_device()
    │                                                      disabled/retired → 403
    │                                                      
    │                                                      _resolve_placement_for_gateway_device()
    │                                                       ├─ 1. display_surface → PlacementTarget
    │                                                       ├─ 2. logical_carrier → PlacementTarget
    │                                                       └─ 3. physical_device → LogicalCarrier → ...
    │                                                      
    │                                                      build_universal_manifest_preview()
    │                                                       ├─ OrchestratorContext
    │                                                       ├─ AdapterPayloadDraft
    │                                                       └─ UniversalManifestV1 (dry_run=True)
    │                                                      
    │                                                      validate_no_secrets()
    │                                                      SHA-256 canonical JSON
    │                                                      
    │  {status, manifest_version, manifest_id,
    │   manifest_hash, manifest (UniversalManifestV1)}
    │◄─────────────────────────────────────────────────────
```

**Ключевые свойства:**
- Device identity только из JWT (нет query param `device_code`)
- Dry-run/preview mode (`metadata.dry_run = True`)
- Не пишет в БД (`db.add` отсутствует)
- Не импортирует: KsoPlacement, GeneratedManifest, publications.service, kso_manifest_projection
- Не вызывает: generate_manifests(), publish_batch()
- `_touch_device()` — единственная запись (last_seen_at)
- `validate_no_secrets()` перед вычислением хеша

---

## No-Manifest Behavior

| Причина | Endpoint | Response |
|---|---|---|
| Placement not found | Universal | `{status: "no_manifest", reason: "no_matching_surface"}` |
| Unsupported channel | Universal | `{status: "no_manifest", reason: "unsupported_channel"}` |
| Builder generic exception | Universal | `{status: "no_manifest", reason: "manifest_build_failed"}` |
| No published manifest | KSO | `{status: "no_manifest"}` |

**Без traceback, без internal IDs, без секретов.**

---

## ETag/304

| Endpoint | Hash | Not-Modified |
|---|---|---|
| Universal | SHA-256 canonical JSON (sort_keys, no separators) | `current_manifest_hash == hash` → `{status: "not_modified"}` |
| Legacy manifest/current | `current_manifest_hash` query param | Server-side comparison |
| KSO | `manifest_hash` в теле ответа | Клиентская логика |

**ETag безопасность:**
- `validate_no_secrets()` вызывается ДО хеширования
- Сanonical JSON: `sort_keys=True, separators=(",",":")`
- No secrets in hash source

---

## Access Boundaries

| Проверка | KSO | Universal | Legacy /current |
|---|---|---|---|
| Device A → device B manifest | ❌ 403 (device_code mismatch) | ❌ (device from JWT only) | ❌ (device from JWT only) |
| User session token | ❌ (device auth only) | ❌ (device auth only) | ❌ (device auth only) |
| Disabled/retired device | ❌ 401 | ❌ 403 | ❌ 401 |
| Query param device_code | N/A (path param) | Нет query | Нет query |

---

## Safety: Read-Only + No Publication Flow

| Check | Universal | KSO | Legacy /current |
|---|---|---|---|
| `db.add` отсутствует | ✅ | ✅ | ✅ |
| `db.commit` только touch_device | ✅ | ✅ (нет) | ✅ |
| GeneratedManifest импорт | ❌ | ✅ (read) | ❌ |
| generate_manifests() вызов | ❌ | ❌ | ❌ |
| publish_batch() вызов | ❌ | ❌ | ❌ |
| KsoPlacement импорт | ❌ | ❌ | ❌ |
| KSO projection импорт | ❌ | ❌ | ✅ (для KSO channel) |
| PoP ingestion импорт | ❌ | ❌ | ❌ |
| Credential management | ❌ | ❌ | ❌ |
| Placement status change | ❌ | ❌ | ❌ |

---

## Test Results

| Слой | Результат |
|---|---|
| **C.4 targeted (NEW)** | **60/60** ✅ |
| C.3 targeted | 44/44 ✅ |
| C.2 targeted | 39/39 ✅ |
| C.1 + C.1.1 targeted | 39/39 ✅ |
| Legacy device gateway auth | 13/13 ✅ |
| **Gateway suite** | **195/195** ✅ |
| Backend collection | **1426** (0 errors) |

### Test classes

| Класс | Тестов | Фокус |
|---|---|---|
| TestManifestAuth | 5 | Device auth, no user session |
| TestLegacyKsoManifest | 7 | GeneratedManifest, device_code match, no secrets |
| TestLegacyManifestCurrent | 3 | Service layer, ETag, session update |
| TestUniversalManifestDelivery | 14 | Builder, resolver, error handling, schema |
| TestManifestETag | 5 | Hash computation, not_modified, secret scan |
| TestNoManifestBehavior | 4 | Structured reasons, no traceback |
| TestAccessBoundaries | 4 | Device isolation, no query params |
| TestManifestReadOnly | 6 | No DB writes, no state changes |
| TestUniversalManifestSafety | 7 | No publication/KSO/PoP imports |
| TestManifestBoundary | 5 | Other endpoints unchanged |

---

## Сохранность подтверждена

- KSO endpoint — не менялся ✅
- Legacy manifest/current — не менялся ✅
- Universal manifest/universal/current — не менялся ✅
- GeneratedManifest — не менялся ✅
- Publication flow — не менялся ✅
- PoP ingestion — не менялся ✅
- Admin API — не менялся ✅
- Auth model global — не менялся ✅
- Heartbeat — не менялся ✅
- Config/current — не менялся ✅
- Миграции — не созданы ✅
- БД — не менялась ✅
- Portal — не менялся ✅

---

## Файлы изменены

| Файл | Действие |
|---|---|
| `backend/tests/test_manifest_delivery_c4.py` | 🆕 60 тестов |

---

## GO/NO-GO для C.5

**GO ✅ для C.5 — Gateway Audit / Security Tests & Closure.**
