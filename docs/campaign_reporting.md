# Campaign Delivery Reporting Core

**Шаг 22** — backend-ядро отчётности по фактической доставке рекламной кампании.

## Overview

Связывает цепочку campaign → booking → schedule → publication → manifest → device sync → PoP в единый отчёт. Не frontend, не BI, не billing, не внешний кабинет рекламодателя.

## Endpoints

Все под `/api/campaign-reports/{campaign_id}/...`, permission `campaign_reports.read`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/{campaign_id}/summary` | Сводка по кампании |
| `GET` | `/{campaign_id}/by-store` | По магазинам |
| `GET` | `/{campaign_id}/by-channel` | По каналам |
| `GET` | `/{campaign_id}/by-device` | По устройствам |
| `GET` | `/{campaign_id}/by-creative` | По creative/rendition |
| `POST` | `/{campaign_id}/snapshots` | Создать снапшот |
| `GET` | `/{campaign_id}/snapshots` | Список снапшотов |
| `GET` | `/{campaign_id}/snapshots/{id}` | Детали снапшота |

## Query Params

- `date_from`, `date_to` — фильтр по периоду (default: campaign dates)
- `store_id`, `channel_id` — фильтр (by-device)
- `limit` (default 100, max 500)
- `offset` (default 0)

## Metrics

### Planning / Publication
- `planned_stores`, `planned_devices`
- `published_targets`, `published_devices`
- `publication_rate`

### Manifest / Sync
- `manifest_available_devices`, `manifest_applied_devices`, `manifest_failed_devices`
- `manifest_apply_rate`

### Media Cache
- `cache_ready_devices`, `cache_missing_devices`, `cache_failed_devices`, `cache_invalid_hash_devices`

### PoP
- `actual_play_count`, `unique_devices_with_pop`, `unique_stores_with_pop`, `last_pop_at`

### Delivery Health
- `devices_ok`, `devices_warning`, `devices_critical`, `delivery_risk_status`

## Delivery Status

| Status | Condition |
|---|---|
| `not_started` | No published targets AND no PoP events |
| `delivering` | PoP events exist (even without published targets) |
| `publishing` | Published targets, no applied manifests |
| `delivering` | Applied manifests + PoP |
| `partially_delivered` | Some devices applied/cache/PoP |
| `delivered` | All metrics ≥ planned |
| `delivery_with_errors` | manifest_failed or cache_invalid_hash |
| `failed` | Published targets but 0 applied manifests (period ended) |

PoP fallback: если `published_targets == 0`, но `unique_devices_with_pop > 0`, статус `delivering` (или `delivery_with_errors` при ошибках sync/cache). Отчёт не может быть `not_started` при наличии фактических показов.

## PoP Fallback

Все разрезы используют PoP как fallback, когда нет published targets:

- **by-store**: UNION stores из `publication_targets` + stores из PoP-устройств
- **by-device**: UNION devices из `publication_targets` + PoP-устройства; `DISTINCT ON` гарантирует 0 дублей, одна строка на устройство
- **by-channel**: per-channel агрегация PoP через `gateway_devices.channel_id`
- **by-creative**: основной путь через `poe.campaign_rendition_id`, fallback через `poe.manifest_item_id → manifest_items → campaign_renditions`. **Ограничение:** PoP не приписывается к creative чужой кампании (проверка `poe.campaign_id == cr.campaign_id`)

## Snapshot Date Parameters

`POST /{campaign_id}/snapshots` по умолчанию берёт период из `campaigns.planned_start_date` / `planned_end_date`. Для снапшота за другой период передать даты в body:

```json
{
  "period_from": "2026-06-01T00:00:00Z",
  "period_to": "2026-12-31T23:59:59Z"
}
```

## Planned Metrics

`planned_devices` и `planned_stores` зависят от `campaign_targets`. Если таблица пуста, planned-метрики = 0 — это допустимо и не является ошибкой отчётности.

## Permissions

- `campaign_reports.read` — GET endpoints
- `campaign_reports.manage` — POST snapshot

Роли: System Administrator, Security Administrator (read only), Operations, Analyst, Ad Manager.
Advertiser/Device Service/Approver — не имеют доступа.

## Security

- No secrets in responses
- No device credentials, tokens, passwords
- No MinIO object keys, file paths
- No stacktraces
- date_from ≤ date_to, limit ≤ 500, offset ≥ 0

## Performance

- Raw SQL через CTE (один запрос для summary)
- No N+1
- Bulk агрегация
- Снапшоты для сохранения срезов

## Таблица

`campaign_delivery_snapshots` — миграция 022. Сохраняет все метрики + details_json (агрегаты, без secrets).

## Files

```
backend/alembic/versions/022_campaign_delivery_reporting.py
backend/app/domains/campaign_reports/__init__.py
backend/app/domains/campaign_reports/models.py
backend/app/domains/campaign_reports/schemas.py
backend/app/domains/campaign_reports/service.py
backend/app/domains/campaign_reports/router.py
backend/app/main.py  (+1 import, +1 router registration)
docs/campaign_reporting.md
```
