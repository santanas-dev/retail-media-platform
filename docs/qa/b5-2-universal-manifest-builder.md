# B.5.2 — Universal Manifest Builder from Orchestrator Draft

> **Дата:** 2026-07-01
> **Этап:** B.5.2 — Manifest Builder
> **Результат:** ✅ — GO для B.5.3

---

## Что создано

### `backend/app/domains/manifests/universal_builder.py`

**Builder functions (3):**

| Function | Описание |
|---|---|
| `build_universal_manifest_from_draft(context, payload_draft)` | Pure function: OrchestratorContext + AdapterPayloadDraft → UniversalManifestV1 |
| `validate_universal_manifest(manifest)` | Обёртка над B.5.1 helpers |
| `build_universal_manifest_preview(db, placement_id, current_user)` | Dry-run preview: resolve chain → adapter → manifest (через B.4 orchestrator) |

### `backend/tests/test_universal_manifest_builder_b5_2.py`

**38 тестов, 9 классов:**

| Класс | Тестов | Фокус |
|---|---|---|
| `TestBuilderBasic` | 7 | Build success, defaults (version, unsigned, dry_run, draft, manifest_id) |
| `TestMappingCampaign` | 2 | Campaign code + ID mapping |
| `TestMappingPlacement` | 3 | Placement code, channel_code, dates |
| `TestMappingTargets` | 3 | Targets list, channel-agnostic, fallback target |
| `TestMappingCapability` | 3 | proof_type, resolution/formats, no-proof_type skip |
| `TestMappingAdapter` | 2 | Adapter payload, isolation from main schema |
| `TestMappingSchedulePlayback` | 3 | Schedule from dates, no-dates, playback proof_type |
| `TestValidation` | 5 | No critical issues, no-secrets, token/password detection, channel mismatch |
| `TestDeferredContent` | 2 | Missing content doesn't crash, warning created |
| `TestBuilderWarnings` | 2 | No-devices warning, adapter warnings preserved |
| `TestB52ImportBoundary` | 6 | No DB writes, no generated_manifests, no publications, no kso_placement, no device_gateway, no API |

---

## Mapping: Orchestrator Draft → UniversalManifestV1

| Блок | Источник | Примечание |
|---|---|---|
| `manifest_version` | Константа `"1.0"` | |
| `manifest_id` | `m-{date}-{hash8}` | Детерминированный ключ |
| `generated_at` | `datetime.now(utc)` | |
| `campaign` | context.placement_code (proxy) | campaign_code полноценно — после creative integration |
| `placement` | context.placement_code, channel_code, dates | |
| `targets[]` | context.devices[].surfaces[] | target_type=surface, device_code, capability |
| `content[]` | context.creative_codes | Placeholder если нет данных |
| `schedule` | context.start_date/end_date | |
| `playback` | surface.proof_type | |
| `adapter_payload` | payload_draft.channel_code, adapter_name, payload | Изолирован |
| `security` | `signature_status=unsigned` | Подпись — deferred |
| `capability` | surface.proof_type, resolution, formats | Из первого surface с данными |
| `metadata` | `dry_run=true, source=orchestrator_draft` | warnings из контекста |

## Missing Content Handling

Если `context.creative_codes` отсутствует → `content=[]` + `warning: "content_not_available_in_orchestrator_context"`.
Builder не падает. Creative integration — deferred item (будет в фазе B.5.3+ или F).

## Secret Checks

- `validate_no_secrets()` вызывается в тестах для каждого манифеста
- Token в `storage_ref` → detected
- Password в `adapter_payload` → detected
- Safe manifest → no issues
- Канал mismatch → Pydantic model_validator ловит

## Import Boundary

| Запрещённый импорт | Статус |
|---|---|
| `publications.service` | ❌ |
| `generated_manifests` | ❌ |
| `KsoPlacement` / `kso_placements` | ❌ |
| `device_gateway` | ❌ |
| `publish_batch` | ❌ |
| `generate_manifests` | ❌ |
| `FastAPI` / `APIRouter` | ❌ |

## Test Results

| Слой | Результат |
|---|---|
| B.5.2 targeted | **38/38** ✅ |
| B.5.1 targeted | **37/37** ✅ |
| Backend collection | **1204** (0 errors) |

## Сохранность

Legacy `GeneratedManifest`, `generated_manifests` FK, publication flow, `generate_manifests()`, `publish_batch()`, KSO projection, Placement API, portal — **не менялись**.

## GO/NO-GO для B.5.3

**GO ✅ для B.5.3 — Schema Validation + No-Secrets Checks.**
