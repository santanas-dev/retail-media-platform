# F.2 — PoP Mapping & Normalization Service

**Date:** 2026-07-01
**Status:** ✅ COMPLETED
**Commit:** (pending)

---

## Что сделано

Реализован read-only normalization service, приводящий два PoP контура к единой модели `PopEventNormalized`.

## Реальные модели и поля

### KsoProofOfPlayEvent (`proof_of_play/models.py`)
| Поле | Тип | Normalized |
|---|---|---|
| event_code | String(128) UNIQUE | source_event_id |
| device_code | String(64) FK | device_code |
| placement_code | String(64) FK | — (code-based) |
| campaign_code | String(64) FK | — (code-based) |
| creative_code | String(64) FK | — |
| manifest_code | String(64) FK | generated_manifest_id |
| media_ref | String(128) | — |
| event_type | String(32) default="impression" | event_type |
| status | String(32) default="accepted" | playback_status |
| played_at | DateTime | event_time (priority 1) |
| duration_ms | Integer | — |
| received_at | DateTime | event_time (priority 2) |
| created_at | DateTime | event_time (priority 3) |

### ProofOfPlayEvent (`device_gateway/models.py`)
| Поле | Тип | Normalized |
|---|---|---|
| device_event_id | UUID | source_event_id |
| gateway_device_id | UUID FK | gateway_device_id |
| manifest_item_id | UUID FK | — |
| manifest_version_id | UUID FK | manifest_id |
| campaign_id | UUID FK | campaign_id |
| creative_version_id | UUID FK | creative_id |
| play_status | String(20) | playback_status |
| validation_status | String(20) | — |
| played_at | DateTime | event_time (priority 1) |
| received_at | DateTime | event_time (priority 2) |
| details_json | JSONB | is_dry_run detection |

## Как работает нормализация

### Legacy KSO
- `source_type="legacy_kso"`, `channel_code="kso"`
- `correlation_status="matched"` если есть campaign_code И placement_code
- `playback_status`: accepted→success, rejected→failure, duplicate→duplicate
- `is_dry_run=False` всегда
- `delivered_impressions=1`

### Enterprise Gateway
- `source_type="enterprise_gateway"`
- `correlation_status="matched"` если campaign_id И manifest_item_id И gateway_device_id
- `playback_status` из `play_status`
- `is_dry_run` из `details_json.dry_run`
- `delivered_impressions=1`

### Scope filtering
Post-normalization: campaign_id, placement_id, store_id, gateway_device_id, physical_device_id, channel_code. `channel_id` → warning (не поддерживается в normalized модели).

### Dry-run exclusion
`exclude_dry_run_events()` + `DeliveryMetricQuery.exclude_dry_run=True` (default).

## Тесты

**F.2 targeted:** 54 tests

| Категория | Тестов |
|---|---|
| Model/field discovery | 3 |
| Legacy KSO normalization | 11 |
| Enterprise Gateway normalization | 9 |
| Query behavior | 7 |
| Dry-run exclusion | 4 |
| No-secrets | 5 |
| Error/warning shape | 4 |
| Read-only boundaries | 7 |
| Regression | 4 |

## Baselines

| Метрика | До F.2 | После F.2 |
|---|---|---|
| Backend collection | 1919 | 1973 |
| F.1 tests | 42 | 42 (адаптирован 1) |
| F.2 tests | — | 54 |

## GO/NO-GO для F.3

**GO** ✅ — F.3 Delivery Aggregation Service может начинаться.
