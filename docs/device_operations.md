# Device Operations / Delivery Health Core

## Overview

Шаг 15 — внутренняя операционная витрина для поддержки и эксплуатации: понять, какие устройства живые, получают manifest, скачивают media и присылают PoP. Read-only, все данные из существующих таблиц, без новых миграций.

**НЕ является:** рекламной отчётностью, BI, SLA, billing, кабинетом рекламодателя.

## Endpoints

Все под `/api/device-operations/`, permission `devices.gateway.read`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/device-operations/overview` | Сводка по всем устройствам |
| `GET` | `/api/device-operations/devices` | Список устройств + health |
| `GET` | `/api/device-operations/devices/{device_id}` | Детализация одного устройства |
| `GET` | `/api/device-operations/stores` | Агрегация по магазинам |
| `GET` | `/api/device-operations/channels` | Агрегация по каналам |

## Health Status

Вычисляется на лету, не хранится в БД:

| Статус | Логика |
|---|---|
| `disabled` | device.status ∈ {disabled, retired} |
| `offline` | last_activity_at > DEVICE_HEALTH_OFFLINE_MINUTES (30 min) |
| `critical` | error_rate ≥ DEVICE_HEALTH_ERROR_RATE_CRITICAL (0.50) |
| `warning` | missing pipeline stages (manifest/media/PoP) or error_rate ≥ WARNING (0.20) |
| `healthy` | всё остальное |

**last_activity_at** = max(last_seen_at, last_heartbeat, last_manifest_request, last_media_request, last_PoP_event, last_device_event).

## Problem Types

- `no_heartbeat`, `no_manifest`, `no_media`, `no_pop` — отсутствие активности за период
- `manifest_validation_failed`, `media_validation_failed`, `media_storage_error` — ошибки
- `pop_rejected_high`, `duplicate_events_high` — доля > 30%
- `batch_rejected`, `disabled_device`, `retired_device`

## Filters

| Параметр | Default | Max |
|---|---|---|
| `date_from` | 24h ago | — |
| `date_to` | now | — |
| `period` | 24h | 30 days |
| `limit` | 100 | 500 |
| `offset` | 0 | — |

Дополнительные: `channel_id`, `store_id`, `device_status`, `health_status`, `problem_type`.

## Config

```ini
DEVICE_HEALTH_OFFLINE_MINUTES = 30
DEVICE_HEALTH_MANIFEST_GRACE_MINUTES = 60
DEVICE_HEALTH_MEDIA_GRACE_MINUTES = 120
DEVICE_HEALTH_POP_GRACE_MINUTES = 180
DEVICE_HEALTH_ERROR_RATE_WARNING = 0.20
DEVICE_HEALTH_ERROR_RATE_CRITICAL = 0.50
DEVICE_HEALTH_MAX_PERIOD_DAYS = 30
DEVICE_HEALTH_DEFAULT_PERIOD_HOURS = 24
```

## Security

- Только human user token
- Device token → 401
- Advertiser/device_service → 403
- Никаких секретов в ответах (device_secret, secret_hash, токены)
- `details_json` не возвращается в recent событиях
- Без stacktrace

## Что НЕ в Шаге 15

- ❌ Frontend, графики, BI, ClickHouse
- ❌ Excel/PDF, рекламные отчёты
- ❌ SLA, compensation, billing
- ❌ Кабинет рекламодателя
- ❌ Push alerts, incident management
- ❌ Автоматическое изменение статусов устройств
