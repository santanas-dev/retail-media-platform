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

## Шаг 17 — Alert Evaluation Run History

### Overview

История запусков проверки alert rules: кто, когда, какие правила, сколько alerts создано/repeated/reopened. Audit-only, ручной запуск через `POST /alerts/evaluate`.

### Таблицы

| Таблица | Назначение |
|---|---|
| `device_alert_evaluation_runs` | Записи о каждом запуске evaluate |
| `device_alert_evaluation_rule_results` | Per-rule результаты в рамках запуска |

+ `device_alert_events.evaluation_run_id` — связь alert events с запуском.

### Endpoints

| Method | Path | Permission |
|---|---|---|
| `GET` | `/alert-evaluations` | `devices.gateway.read` |
| `GET` | `/alert-evaluations/{id}` | `devices.gateway.read` |
| `GET` | `/alert-evaluations/{id}/rules` | `devices.gateway.read` |

`POST /alerts/evaluate` теперь возвращает `evaluation_run_id` в ответе.

### Run Statuses

`running` → `completed` / `completed_with_errors` / `failed`

### Error Policy

- Ошибка одного rule не валит весь evaluate
- Failed rule → rule_result со status=failed
- Часть failed → run status `completed_with_errors`
- Всё failed → run status `failed`
- Error messages: safe, без stacktrace, без секретов, ≤500 символов

### Security

- `evaluation_run_id` заполняется только для событий evaluate (created/repeated/reopened)
- Acknowledge/resolve события: `evaluation_run_id = NULL`
- Старые события: `evaluation_run_id = NULL`
- Без новых permissions
- Без секретов в ответах

### Что НЕ в Шаге 17

- ❌ Cron/scheduler/Celery
- ❌ Background worker
- ❌ Telegram/email/push
- ❌ SLA/billing/compensation

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

---

## Step 17 — Alert Evaluation Run History Core

**Создан:** 2026-06-17  
**Статус:** ✅ Реализован  
**Миграция:** `017_alert_evaluation_runs.py`

### Сводка

История запусков проверки алертов. Каждый вызов `POST /alerts/evaluate` создаёт запись evaluation run с per-rule результатами. Alert events получают ссылку на evaluation_run_id для трассируемости.

### Таблицы

**`device_alert_evaluation_runs`**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID PK | |
| `triggered_by` | UUID FK → users | Кто запустил |
| `trigger_type` | VARCHAR(20) | Только `manual` |
| `status` | VARCHAR(30) | `running` / `completed` / `completed_with_errors` / `failed` |
| `started_at` | TIMESTAMPTZ | |
| `finished_at` | TIMESTAMPTZ | NULL пока running |
| `evaluated_rules_count` | INT | Сколько правил проверено |
| `created_count` | INT | Новых алертов |
| `repeated_count` | INT | Repeated событий |
| `reopened_count` | INT | Переоткрытых алертов |
| `skipped_count` | INT | Пропущенных правил |
| `failed_rules_count` | INT | Упавших правил |
| `duration_ms` | INT | |
| `details_json` | JSONB NOT NULL DEFAULT {} | |
| `error_message` | VARCHAR(500) | Safe error text |
| `created_at` | TIMESTAMPTZ | |

**`device_alert_evaluation_rule_results`**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID PK | |
| `run_id` | UUID FK → runs | |
| `rule_id` | UUID FK → rules | |
| `rule_code` | VARCHAR(100) | |
| `alert_type` | VARCHAR(50) | |
| `status` | VARCHAR(20) | `completed` / `skipped` / `failed` |
| `checked_devices_count` | INT DEFAULT 0 | |
| `matched_devices_count` | INT DEFAULT 0 | |
| `created_count` | INT DEFAULT 0 | |
| `repeated_count` | INT DEFAULT 0 | |
| `reopened_count` | INT DEFAULT 0 | |
| `skipped_count` | INT DEFAULT 0 | |
| `error_message` | VARCHAR(500) | Safe error text |
| `details_json` | JSONB NOT NULL DEFAULT {} | |
| `created_at` | TIMESTAMPTZ | |

**Изменения существующих таблиц:**

- `device_alert_events.evaluation_run_id` — nullable FK → `device_alert_evaluation_runs(id)`, ON DELETE RESTRICT
  - NULL для старых событий и событий acknowledge/resolve
  - Заполняется только для created/repeated/reopened событий из evaluate

### Endpoints

| Метод | Путь | Permissions | Описание |
|-------|------|-------------|----------|
| `POST` | `/alerts/evaluate` | `devices.gateway.manage` | Запуск оценки (создаёт run) |
| `GET` | `/alert-evaluations` | `devices.gateway.read` | Список evaluation runs |
| `GET` | `/alert-evaluations/{id}` | `devices.gateway.read` | Детали run |
| `GET` | `/alert-evaluations/{id}/rules` | `devices.gateway.read` | Per-rule результаты run |

**Фильтры для `GET /alert-evaluations`:**
- `status` — running / completed / completed_with_errors / failed
- `trigger_type` — manual
- `triggered_by` — UUID пользователя
- `date_from` / `date_to` — диапазон дат
- `limit` (default 100, max 500) / `offset` (default 0)

### Evaluate Response

```json
{
  "status": "ok",
  "evaluation_run_id": "uuid",
  "evaluated_rules": 7,
  "created": 3,
  "repeated": 5,
  "reopened": 1,
  "skipped": 0,
  "failed_rules": 0
}
```

### Error Handling

- Per-rule изоляция: ошибка одного правила не валит весь run
- Run status: `completed` (все ок) / `completed_with_errors` (часть правил упала) / `failed` (критическая ошибка)
- `error_message` — safe, max 500 символов, без stacktrace/SQL/credentials
- `running` run не должен зависнуть: при падении evaluate статус обновляется на `failed`

### Alert Event связь

- `evaluation_run_id` заполняется только для событий из evaluate (created / repeated / reopened)
- Старые события: NULL
- События acknowledge / resolve: NULL
- FK: ON DELETE RESTRICT

### Security

- Forbidden keys в `details_json` (recursive): access_token, refresh_token, token, jwt, password, secret, credential, credentials, authorization, cookie, api_key, private_key, public_key, stacktrace
- Используется `DEVICE_ALERT_DETAILS_MAX_BYTES` (64 KB)
- `triggered_by` — только UUID, без разворачивания user object
- `error_message` — safe, без stacktrace / SQL / credentials

### Что НЕ в Шаге 17

- ❌ Cron, scheduler, background worker, Celery
- ❌ Telegram / email / push
- ❌ Escalation, incident management
- ❌ SLA, billing, compensation
- ❌ Frontend
- ❌ Новые permissions (используются существующие `devices.gateway.read` / `devices.gateway.manage`)
