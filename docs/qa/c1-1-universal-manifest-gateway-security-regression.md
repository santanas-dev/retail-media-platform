# C.1.1 — Universal Manifest Gateway Security & Regression Gate

> **Дата:** 2026-07-01
> **Этап:** C.1.1 — Security & Regression Gate (расширение C.1)
> **Предыдущий:** C.1 (commit `01932b1`, 12 tests)
> **Результат:** ✅ — GO для C.2

---

## Coverage Gap (что было закрыто)

C.1 имел **12 тестов** (запрошено минимум 20). C.1.1 добавляет **27 тестов**, доводя общий счёт до **39**.

| Категория | C.1 | C.1.1 | Итого |
|---|---|---|---|
| Auth/Security | 2 | 2 | **4** |
| Router auth method | 0 | 2 | **2** |
| Manifest resolution | 4 | 3 | **7** |
| ETag/304 | 1 | 4 | **5** |
| Placement resolution | 1 | 0 | **1** |
| Secret/no-leak | 0 | 3 | **3** |
| Safety (code inspection) | 4 | 4 | **8** |
| Legacy endpoints preserved | 0 | 7 | **7** |
| DB write boundary | 0 | 2 | **2** |

---

## Security Cases Closed

### Auth & Access Control

| Case | Test | Result |
|---|---|---|
| Disabled device denied | `test_disabled_device_denied` | ✅ |
| Retired device denied | `test_retired_device_denied` | ✅ |
| Active device accepted | `test_active_device_accepted` | ✅ |
| Lost device accepted | `test_lost_device_accepted` | ✅ |
| Endpoint uses `authenticate_device` (not user session) | `test_endpoint_uses_authenticate_device_not_get_current_user` | ✅ |
| No `require_permission()` on route | `test_endpoint_does_not_require_user_permission` | ✅ |

### Secret / Token Leak Prevention

| Case | Test | Result |
|---|---|---|
| Response schema: no secret/credential/token fields | `test_secret_keywords_not_in_response_schema` | ✅ |
| Service function: no secret params | `test_service_function_has_no_secret_params` | ✅ |
| Response dict keys disjoint from secrets | `test_no_device_credential_in_response_dict_keys` | ✅ |
| Manifest body: no token/secret/password/credential strings | `test_no_secrets_in_response` | ✅ |

### Manifest Resolution Robustness

| Case | Test | Result |
|---|---|---|
| No placement → no_manifest | `test_no_manifest_when_no_placement` | ✅ |
| Placement exists → manifest returned | `test_manifest_returned_when_placement_exists` | ✅ |
| Dry-run marker present | `test_response_has_dry_run_preview_marker` | ✅ |
| Builder raises PlacementNotFound → no_manifest | `test_no_manifest_when_builder_raises_placement_not_found` | ✅ |
| Builder raises UnsupportedChannel → no_manifest | `test_no_manifest_when_unsupported_channel` | ✅ |
| Builder raises generic exception → no_manifest | `test_builder_generic_exception_returns_no_manifest` | ✅ |

### ETag / 304

| Case | Test | Result |
|---|---|---|
| Same hash → not_modified | `test_not_modified_when_hash_matches` | ✅ |
| ETag (hash) present in ok response | `test_etag_present_in_ok_response` | ✅ |
| Different manifest → different ETag | `test_different_manifest_produces_different_etag` | ✅ |
| no_manifest response: no hash leaked | `test_no_manifest_response_table_without_hash` | ✅ |
| Different client hash → fresh manifest | `test_different_hash_returns_fresh_manifest` | ✅ |

---

## Legacy Endpoint Preservation

Каждый legacy endpoint проверен на неизменность:

| Endpoint | Test | Result |
|---|---|---|
| `/kso/{device_code}/manifest` | `test_kso_endpoint_exists_and_uses_generated_manifest` | ✅ |
| `/manifest/current` (legacy) | `test_legacy_manifest_current_endpoint_unchanged` | ✅ |
| `/heartbeat` | `test_heartbeat_endpoint_unchanged` | ✅ |
| `/pop/events` | `test_pop_event_endpoint_unchanged` | ✅ |
| `/pop/events/batch` | `test_pop_batch_endpoint_unchanged` | ✅ |
| Admin routes | `test_admin_routes_not_affected` | ✅ |
| `authenticate_device()` global | `test_auth_model_global_unchanged` | ✅ |

---

## Import Boundary Checks

C.1 service функции НЕ импортируют:

| Check | Test | Result |
|---|---|---|
| `KsoPlacement` | `test_resolver_does_not_use_kso_models` | ✅ |
| `GeneratedManifest` | `test_service_does_not_import_publications_service` | ✅ |
| `publications.service` | `test_service_does_not_import_publications_service` | ✅ |
| `kso_manifest_projection` | `test_service_does_not_import_kso_projection` | ✅ |
| Portal routes | `test_service_does_not_import_portal_routes` | ✅ |
| `generate_manifests` | `test_universal_manifest_endpoint_does_not_use_generated_manifests` | ✅ |
| `publish_batch` | `test_universal_manifest_endpoint_does_not_call_publish_batch` | ✅ |

---

## DB Write Boundary

| Check | Test | Result |
|---|---|---|
| No `db.add()` calls | `test_no_db_write_calls_in_service` | ✅ |
| Resolver only SELECT | `test_resolver_only_reads` | ✅ |

---

## Test Results

| Слой | Результат |
|---|---|
| **C.1.1 targeted (NEW)** | **39/39** ✅ |
| B.5.1 schema | 37/37 ✅ |
| B.5.2 builder | 38/38 ✅ |
| B.5.3 validation | 40/40 ✅ |
| Legacy device gateway auth | 13/13 ✅ |
| KSO manifest gateway (integration) | 1 error — backend offline (pre-existing) |
| Backend collection | **1283** (0 errors) |

### Delta от C.1

| Метрика | C.1 | C.1.1 | Δ |
|---|---|---|---|
| C.1 targeted tests | 12 | **39** | +27 |
| Backend collection | 1256 | **1283** | +27 |

---

## Сохранность подтверждена

- KSO endpoint — не менялся ✅
- GeneratedManifest — не менялся ✅
- Publication flow — не менялся ✅
- `generate_manifests()` — не менялся ✅
- `publish_batch()` — не менялся ✅
- KSO projection — не менялся ✅
- PoP ingestion — не менялся ✅
- Admin API — не менялся ✅
- Auth model global — не менялся ✅
- `authenticate_device()` — не менялся ✅
- Portal — не менялся ✅
- Миграции — не созданы ✅
- БД — не менялась ✅
- `generated_manifests` — не затронута ✅

---

## Файлы изменены

| Файл | Действие |
|---|---|
| `backend/tests/test_device_gateway_universal_c1.py` | 🔄 Расширен: 12 → 39 тестов (+27) |

---

## GO/NO-GO для C.2

**GO ✅ для C.2 — Device Registration Validation.**

Все security cases закрыты. Legacy endpoints проверены и не затронуты. Coverage gap закрыт (12→39 тестов). Backend collection стабилен (1283, 0 errors).
