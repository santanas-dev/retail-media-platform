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

---

## Шаг 16 — Alert Rules Core

### Overview

Внутренний механизм технических alert-правил по доставке рекламы на устройства. Read/write через `/api/device-operations/alert-rules` и `/api/device-operations/alerts`.

**НЕ является:** SLA, billing, incident management, push-уведомлениями, Telegram/email.

### Таблицы

| Таблица | Назначение |
|---|---|
| `device_alert_rules` | Определения правил (что и как мониторить) |
| `device_alerts` | Экземпляры сработавших алертов |
| `device_alert_events` | История изменений статуса алертов |

### Alert Types

`device_offline`, `no_manifest`, `no_media`, `no_pop`, `manifest_validation_failed`, `media_validation_failed`, `media_storage_error`, `pop_rejected_high`, `duplicate_events_high`, `batch_rejected`.

### Status Lifecycle

```
open → acknowledged → resolved
  ↑                      │
  └──────────────────────┘ (reopen)
```

### Endpoints

**Rules** (all under `/api/device-operations/`):

| Method | Path | Permission |
|---|---|---|
| `GET` | `/alert-rules` | `devices.gateway.read` |
| `POST` | `/alert-rules` | `devices.gateway.manage` |
| `PUT` | `/alert-rules/{id}` | `devices.gateway.manage` |
| `POST` | `/alert-rules/{id}/enable` | `devices.gateway.manage` |
| `POST` | `/alert-rules/{id}/disable` | `devices.gateway.manage` |

**Alerts:**

| Method | Path | Permission |
|---|---|---|
| `GET` | `/alerts` | `devices.gateway.read` |
| `GET` | `/alerts/{id}` | `devices.gateway.read` |
| `POST` | `/alerts/{id}/acknowledge` | `devices.gateway.manage` |
| `POST` | `/alerts/{id}/resolve` | `devices.gateway.manage` |
| `GET` | `/alerts/{id}/events` | `devices.gateway.read` |
| `POST` | `/alerts/evaluate` | `devices.gateway.manage` |

### Deduplication

`dedup_key = {alert_type}:device:{gateway_device_id}`. Partial unique index `WHERE status IN ('open', 'acknowledged')`. Один dedup_key → один активный alert.

### Default Rules (seed в миграции)

| Rule | Severity | Window | Enabled |
|---|---|---|---|
| `device_offline` | critical | 30 min | ✅ |
| `media_storage_error` | critical | 60 min | ✅ |
| `manifest_validation_failed` | warning | 60 min | ✅ |
| `media_validation_failed` | warning | 60 min | ✅ |
| `pop_rejected_high` | warning | 120 min, min_total=10 | ✅ |
| `duplicate_events_high` | warning | 120 min, min_total=10 | ✅ |
| `batch_rejected` | warning | 120 min | ✅ |
| `no_manifest` | warning | 120 min | ❌ (disabled) |
| `no_media` | warning | 120 min | ❌ (disabled) |
| `no_pop` | warning | 120 min | ❌ (disabled) |

### Config

```ini
DEVICE_ALERT_DETAILS_MAX_BYTES = 65536  # 64 KB
```

### Security

- Forbidden keys: access_token, refresh_token, token, jwt, password, secret, credential, credentials, authorization, cookie, api_key, private_key, public_key, stacktrace
- Recursive validation threshold_json, scope_json, details_json
- Device token → 401
- Без новых permissions

### Что НЕ в Шаге 16

- ❌ Frontend, графики, BI
- ❌ Telegram/email/push уведомления
- ❌ Cron/scheduler/Celery
- ❌ Incident management, escalation matrix
- ❌ SLA, billing, compensation
- ❌ Автоматическое изменение статусов устройств
