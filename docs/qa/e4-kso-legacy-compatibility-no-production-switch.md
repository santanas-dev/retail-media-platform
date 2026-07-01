# E.4 — Legacy Compatibility / No Production Switch Gate

**Date:** 2026-07-01
**Status:** ✅ COMPLETED
**Commit:** (pending)

---

## Что проверялось

### 1. Legacy KSO Production Endpoint Isolation

`GET /api/device-gateway/kso/{device_code}/manifest` (строки 136-184 в `router.py`):

- ✅ Импортирует **только** `GeneratedManifest` + `hashlib` + `json`
- ✅ **НЕ** импортирует: KsoAdapter, UniversalManifestV1, universal_builder, orchestrator/service, adapters/registry
- ✅ Использует legacy GeneratedManifest path (`GeneratedManifest.device_code`, `status == "published"`)
- ✅ Response shape: `{status, manifest_version_id, manifest_hash, published_at, manifest}`
- ✅ no_manifest: `{"status": "no_manifest"}`
- ✅ ETag/hash behaviour preserved

### 2. Universal KSO Preview Isolation

`GET /api/device-gateway/manifest/universal/current`:

- ✅ Возвращает `UniversalManifestV1` с `adapter_payload` для KSO
- ✅ `adapter_payload.dry_run = True`
- ✅ `manifest.status = DRAFT`
- ✅ `metadata.dry_run = True`
- ✅ **Не пишет** GeneratedManifest
- ✅ **Не пишет** PublicationBatch
- ✅ **Не пишет** ManifestVersion
- ✅ **Не меняет** kso_placements / kso_devices

### 3. Source Boundaries

**KsoAdapter НЕ импортирует:**
- KsoPlacement, KsoDevice, kso_manifest_projection
- GeneratedManifest, publications service
- generate_manifests, publish_batch
- Device Gateway production router/service

**Legacy KSO endpoint НЕ импортирует:**
- KsoAdapter, UniversalManifestV1, universal_builder
- orchestrator/service, adapters/registry

### 4. GeneratedManifest Safety

- ✅ KsoAdapter: 0 DB writes (нет `db.add/insert/update/delete`)
- ✅ universal_builder: 0 DB writes
- ✅ orchestrator/service.py: 0 DB writes (только SELECT)
- ✅ `GeneratedManifest` model не изменён
- ✅ `generate_manifests()` source не изменён
- ✅ `publish_batch()` source не изменён

### 5. Registry Safety

- ✅ `select_adapter("kso")` → KsoAdapter
- ✅ Registry не импортируется legacy endpoint
- ✅ Mock adapter работает
- ✅ Unsupported channel → structured error
- ✅ Duplicate import idempotent

### 6. No Production Switch

Проверено **4 production switch флага** — ни одного не найдено в коде:
- `production_use_universal_manifest`
- `enable_kso_universal_publish`
- `switch_kso_to_universal`
- `use_universal_for_kso_production`

Legacy endpoint не вызывает universal endpoint и не использует KsoAdapter.

---

## Тесты

**E.4 targeted:** 45 tests (все pass)

| Категория | Тестов |
|---|---|
| Legacy endpoint isolation | 8 |
| Universal preview isolation | 9 |
| Source boundaries | 8 |
| GeneratedManifest safety | 6 |
| Registry safety | 5 |
| No production switch | 4 |
| Regression compatibility | 5 |

---

## Результаты suites

| Suite | Tests | Status |
|---|---|---|
| **E.4 targeted** | **45** | ✅ 45/45 |
| E.3 targeted | 52 | ✅ |
| E.2 targeted | 65 | ✅ |
| E.1 targeted | 55 | ✅ |
| B.4 orchestrator | ~110 | ✅ |
| B.5 universal manifest | ~75 | ✅ |
| C gateway universal | ~48 | ✅ |
| E.1+E.2+E.3+E.4+B.4+B.5+C | **450** | ✅ |
| Planning-only | 234 | ✅ |
| Inventory | 20 | ✅ |
| Backend collection | **1877** | 0 errors |

---

## Baseline

| Метрика | До E.4 | После E.4 |
|---|---|---|
| Backend collection | 1832 | 1877 |
| E-series total | 172 | 217 |
| E+B+C combined | 405 | 450 |

---

## GO/NO-GO для E.5 Closure Gate

**GO** ✅ — Phase E полностью проверена на всех уровнях безопасности.
Legacy KSO production полностью изолирован от universal preview.
Никаких production switch-флагов не появилось.
E.5 Closure Gate может завершить Phase E и перейти к Phase F.
