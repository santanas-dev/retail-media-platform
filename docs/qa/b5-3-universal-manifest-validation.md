# B.5.3 — Universal Manifest Schema Validation + No-Secrets Checks

> **Дата:** 2026-07-01
> **Этап:** B.5.3 — Validation Layer
> **Результат:** ✅ — GO для B.5.4

---

## Что сделано

### Campaign Proxy Fix

**Проблема:** `_build_campaign()` использовал `context.placement_code` как `campaign_code` — proxy.

**Решение:**
- `ManifestCampaign.campaign_code` сделан optional (`str | None`)
- `_build_campaign()` больше не подставляет placement_code
- Builder добавляет warning `campaign_data_incomplete`
- `validate_campaign()` проверяет proxy (error) и incomplete (warning/error по статусу)

### Усиленные Validators (7 новых)

| Validator | Что проверяет |
|---|---|
| `validate_campaign()` | Proxy detection, campaign_data_incomplete (warning/error по статусу) |
| `validate_targets()` | target_type valid, playable targets must have surface/device |
| `validate_capability()` | proof_type required, format ⊂ supported_formats, proof_type match |
| `validate_content()` | Preview: warning; Final: media_type + storage_ref required |
| `validate_schedule()` | start ≤ end |
| `validate_adapter_payload()` | Required for final, non-empty payload warning |
| `validate_manifest_for_preview()` | Lenient composition |
| `validate_manifest_for_final_publish()` | Strict composition (future path) |

### Усиленные No-Secrets Patterns

| Pattern | Пример |
|---|---|
| `token` / `secret` / `password` / `passwd` | Keys and values |
| `access_key` / `api_key` | Nested payload |
| `Bearer ` | Auth headers |
| `X-Amz-Signature` / `X-Amz-Credential` | AWS signed URLs |
| `sp=rl` / `sig=` / `se=` | Azure SAS tokens |
| `?token=` / `&token=` | URL query params |
| `sk-` / `pk-` | API key prefixes |

**Разрешённые controlled fields:** `security.signature_status`, `security.signature_algorithm`

### Preview vs Final Validation

| Режим | Campaign | Content | Adapter | Capability |
|---|---|---|---|---|
| **Preview** | Warning | Optional | Optional | Optional |
| **Final** | Error | Required | Required | Full |

### Campaign Proxy Detection

- `campaign_code == placement_code` → error `campaign_equals_placement_code`
- `campaign_code is None` → warning `campaign_data_incomplete` (preview) / error (final)
- Builder тест: `campaign_data_incomplete` в `metadata.warnings`

## Test Results

| Слой | Тестов | Результат |
|---|---|---|
| B.5.3 targeted | **40** | ✅ |
| B.5.2 targeted | **38** | ✅ |
| B.5.1 targeted | **37** | ✅ |
| Backend collection | **1244** | 0 errors |

### B.5.3 Test Classes

| Класс | Тестов |
|---|---|
| TestRequiredFields | 4 |
| TestCampaignValidation | 4 |
| TestTargetValidation | 3 |
| TestCapabilityValidation | 4 |
| TestContentValidation | 4 |
| TestScheduleValidation | 2 |
| TestAdapterPayloadValidation | 1 |
| TestNoSecretsEnhanced | 8 |
| TestSerialization | 3 |
| TestPreviewVsFinal | 2 |
| TestB53ImportBoundary | 5 |

## Import Boundaries

| Проверка | Статус |
|---|---|
| `universal_builder` — нет publications | ✅ |
| `universal_schema` — нет publications | ✅ |
| Нет generated_manifests | ✅ |
| Нет kso_placements | ✅ |
| Нет device_gateway | ✅ |
| Нет API routes | ✅ |

## Сохранность

Legacy `GeneratedManifest`, FK, publication flow, `generate_manifests()`, `publish_batch()`, KSO projection, Placement API, portal — **не менялись**.

## GO/NO-GO для B.5.4

**GO ✅ для B.5.4 — Legacy Compatibility Analysis.**
