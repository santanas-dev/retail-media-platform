# B.5.1 — Universal Manifest Schema Contracts

> **Дата:** 2026-07-01
> **Этап:** B.5.1 — Schema Contracts
> **Результат:** ✅ — GO для B.5.2

---

## Что создано

### `backend/app/domains/manifests/universal_schema.py`

**10 Pydantic v2 моделей:**

| Модель | Описание |
|---|---|
| `ManifestCampaign` | Campaign info (code, name, advertiser) |
| `ManifestPlacement` | Placement info (code, channel_code, dates) |
| `ManifestTarget` | Channel-agnostic target (store, surface, device) |
| `ManifestContentItem` | Creative/rendition item (media_type, storage_ref) |
| `ManifestSchedule` | Schedule block (start, end, timezone) |
| `ManifestPlayback` | Playback config (proof_type, loop, order) |
| `ManifestAdapterPayload` | Isolated channel-specific payload |
| `ManifestSecurity` | Security metadata (signature_status, hash) |
| `ManifestCapability` | Device capability (proof_type, formats, resolution) |
| `ManifestMetadata` | Generation metadata (dry_run, warnings) |
| `UniversalManifestV1` | Top-level manifest — объединяет все блоки |

**Validation helpers (3 функции):**

| Helper | Что проверяет |
|---|---|
| `validate_required_fields()` | manifest_version, campaign, placement, channel_code, targets |
| `validate_no_secrets()` | Рекурсивный поиск forbidden keys и secret patterns |
| `validate_manifest_schema()` | Комбинирует required + no-secrets + signature_status + KSO-refs |

**Structured output:** `ManifestIssue(code, path, message, severity)`

### `backend/tests/test_universal_manifest_schema_b5_1.py`

**37 тестов, 7 классов:**

| Класс | Тестов | Фокус |
|---|---|---|
| `TestMinimalManifest` | 5 | Defaults (version=1.0, unsigned, draft) |
| `TestRequiredFields` | 6 | campaign, placement, channel_code, targets validation |
| `TestNoSecrets` | 8 | token, password, access_key, safe storage_ref, nested |
| `TestChannelAgnostic` | 2 | Multi-channel targets, adapter payload isolation |
| `TestNoKsoReferences` | 3 | No kso_device_code, no generated_manifest imports |
| `TestChannelCodeConsistency` | 3 | Match/mismatch channel_code, no adapter payload ok |
| `TestSerialization` | 3 | model_dump, model_dump_json, roundtrip |
| `TestValidationHelpers` | 4 | Clean manifest, invalid signature_status, dry_run, full schema |
| `TestB51ImportBoundary` | 3 | No generated_manifests/kso_placements imports, no DB writes, no API routes |

---

## Что НЕ сделано (намеренно)

- ❌ Миграции БД
- ❌ DB writes (включая `generated_manifests`)
- ❌ API routes
- ❌ Publication flow changes
- ❌ `build_manifest_from_placement()` changes
- ❌ `generate_manifests()` changes
- ❌ KSO legacy projection changes
- ❌ Orchestrator service/simulation changes
- ❌ Signing implementation
- ❌ Builder (B.5.2)
- ❌ Manifest generation from OrchestratorContext

---

## Test Results

| Слой | Результат |
|---|---|
| B.5.1 targeted | **37/37** ✅ |
| Backend collection | **1166** (0 collection errors) |

---

## Сохранность подтверждена

- Legacy `GeneratedManifest` — не менялся
- `generated_manifests` FK — не менялся
- Publication flow — не менялся
- `build_manifest_from_placement()` — не менялся
- KSO projection — не менялась
- Orchestrator service/simulation — не менялись
- API — не создавался
- Portal — не менялся

---

## GO/NO-GO для B.5.2

**GO ✅ для B.5.2 — Manifest Builder from Orchestrator Draft**

Основание: все контракты созданы, validation helpers работают,
импорты чистые, legacy не затронут, 37/37 тестов.
