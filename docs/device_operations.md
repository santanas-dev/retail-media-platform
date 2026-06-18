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
- `date_from` / `date_to` — диапазон дат (date_from ≤ date_to, иначе 422)
- `limit` (default 100, max 500) / `offset` (default 0)

**DB-level constraints (миграция 018):**
- `trigger_type` CHECK: только `manual`
- `status` CHECK: `running` / `completed` / `completed_with_errors` / `failed`
- Все count ≥ 0 (CHECK per column)
- `duration_ms` IS NULL OR ≥ 0
- `error_message` VARCHAR(500)

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

---

## Шаг 18 — Device Runtime Configuration Core

**Создан:** 2026-06-17  
**Статус:** ✅ Реализован  
**Миграция:** `019_device_runtime_config_core.py`

### Сводка

Хранение, вычисление и выдача runtime-настроек устройствам. Конфигурация собирается по иерархии merge (global → channel → store → device), кэшируется через canonical SHA-256 и отдаётся устройству с поддержкой ETag/304 Not Modified.

**НЕ является:** плеером, Android-приложением, frontend, scheduler, push-командами, remote command execution, КСО-интеграцией.

### Таблицы

**`device_runtime_config_profiles`**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID PK | |
| `code` | VARCHAR(64) UNIQUE | `^[a-z0-9_]+$` |
| `name` | VARCHAR(255) | |
| `description` | TEXT | |
| `config_json` | JSONB NOT NULL | ≤65536 байт, только разрешённые ключи |
| `config_hash` | VARCHAR(64) | Canonical SHA-256 от config_json |
| `version` | INT DEFAULT 1 | Инкремент при каждом изменении config_json |
| `enabled` | BOOL DEFAULT true | |
| `created_by` | UUID FK → users | NULL для seed |
| `updated_by` | UUID FK → users | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**`device_runtime_config_assignments`**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID PK | |
| `profile_id` | UUID FK → profiles | ON DELETE RESTRICT |
| `scope_type` | VARCHAR(10) | `global` / `channel` / `store` / `device` |
| `channel_id` | UUID FK | Только для scope_type=channel |
| `store_id` | UUID FK | Только для scope_type=store |
| `gateway_device_id` | UUID FK | Только для scope_type=device |
| `priority` | INT DEFAULT 0 | Чем выше, тем приоритетнее |
| `enabled` | BOOL DEFAULT true | |
| `created_by` | UUID FK → users | NULL для seed |
| `updated_by` | UUID FK → users | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**`device_runtime_config_requests`**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID PK | |
| `gateway_device_id` | UUID FK → devices | |
| `config_profile_ids` | UUID[ ] | Профили, участвовавшие в merge |
| `effective_config_hash` | VARCHAR(64) | Хэш выданного конфига |
| `response_status` | VARCHAR(20) | `ok` / `not_modified` / `not_found` |
| `requested_at` | TIMESTAMPTZ | |
| `ip_address` | INET | |
| `user_agent` | TEXT | |

### Иерархия Merge

Приоритет от низшего к высшему:

```
global → channel → store → device
```

На каждом уровне поля из конфига перезаписывают значения предыдущих уровней. `device`-level assignment имеет наивысший приоритет.

### Разрешённые config-ключи

| Ключ | Тип | Границы |
|------|-----|---------|
| `heartbeat_interval_sec` | int | 10–3600 |
| `manifest_refresh_interval_sec` | int | 10–3600 |
| `media_download_timeout_sec` | int | 1–300 |
| `media_cache_max_mb` | int | 100–10240 |
| `pop_batch_max_events` | int | 1–1000 |
| `pop_flush_interval_sec` | int | 30–3600 |
| `max_media_file_mb` | int | 1–2000 |
| `clock_skew_tolerance_sec` | int | 0–3600 |
| `log_level` | str | `debug` / `info` / `warning` / `error` |
| `allowed_mime_types` | str[ ] | Subset из [`image/jpeg`, `image/png`, `video/mp4`, `video/webm`] |
| `kso_safety` | object | Optional, только boolean поля: `idle_only`, `stop_on_transaction`, `stop_on_payment`, `stop_on_error_screen` |
| `details_json` | object | Произвольные метаданные |

### Default Config (Seed)

**Профиль:** `default_runtime_config`

```json
{
  "heartbeat_interval_sec": 300,
  "manifest_refresh_interval_sec": 600,
  "media_download_timeout_sec": 30,
  "media_cache_max_mb": 1024,
  "pop_batch_max_events": 100,
  "pop_flush_interval_sec": 60,
  "max_media_file_mb": 500,
  "clock_skew_tolerance_sec": 30,
  "log_level": "info",
  "allowed_mime_types": ["image/jpeg", "image/png", "video/mp4", "video/webm"]
}
```

**Assignment:** global (priority=0).

### Endpoints

**Device Gateway** (под `/api/device-gateway/`):

| Метод | Путь | Токен | Описание |
|-------|------|-------|----------|
| `GET` | `/config/current` | Device only | Текущий effective config |

**Admin** (под `/api/device-operations/runtime-configs/`):

| Метод | Путь | Permission | Описание |
|-------|------|------------|----------|
| `GET` | `/profiles` | `devices.gateway.read` | Список профилей |
| `POST` | `/profiles` | `devices.gateway.manage` | Создать профиль |
| `GET` | `/profiles/{id}` | `devices.gateway.read` | Детали профиля |
| `PUT` | `/profiles/{id}` | `devices.gateway.manage` | Обновить профиль |
| `POST` | `/profiles/{id}/enable` | `devices.gateway.manage` | Включить профиль |
| `POST` | `/profiles/{id}/disable` | `devices.gateway.manage` | Выключить профиль |
| `GET` | `/assignments` | `devices.gateway.read` | Список назначений |
| `POST` | `/assignments` | `devices.gateway.manage` | Создать назначение |
| `GET` | `/assignments/{id}` | `devices.gateway.read` | Детали назначения |
| `PUT` | `/assignments/{id}` | `devices.gateway.manage` | Обновить назначение |
| `POST` | `/assignments/{id}/enable` | `devices.gateway.manage` | Включить назначение |
| `POST` | `/assignments/{id}/disable` | `devices.gateway.manage` | Выключить назначение |
| `GET` | `/effective/{device_id}` | `devices.gateway.read` | Preview effective config |
| `GET` | `/requests` | `devices.gateway.read` | Audit config requests |

Фильтры для `/profiles`: `enabled` (bool), `search` (поиск по code/name).  
Фильтры для `/assignments`: `profile_id`, `scope_type`.  
Фильтры для `/requests`: `device_id`, `date_from`, `date_to`.

### Device Endpoint: `GET /config/current`

- **Только device token** (human token → 401, невалидный токен → 401)
- **200** — возвращает `DeviceConfigResponse`: `status`, `gateway_device_id`, `config_hash`, `config` (текущий effective config), `generated_at`
- **304 Not Modified** — при совпадении `If-None-Match` с текущим `config_hash`
- **Device response НЕ содержит** `profile_ids`, `assignment_ids` — только чистый конфиг
- **Audit:** каждый запрос пишется в `device_runtime_config_requests` (до возврата ответа)

### Security

- **Forbidden keys** (recursive, проверяются при create/update):
  `access_token`, `refresh_token`, `token`, `jwt`, `password`, `secret`, `credential`, `credentials`, `authorization`, `cookie`, `api_key`, `private_key`, `public_key`, `stacktrace`, `admin_token`, `secret_token`, `secret_key`, `encryption_key`, `signing_key`

- **No secrets в ответах:** device response не содержит `profile_ids`; admin responses не содержат forbidden keys
- **No raw exception:** все ошибки — safe сообщения без stacktrace
- **Token isolation:** human token → `GET /config/current` = 401, device token → admin endpoints = 401
- **Config size limit:** ≤65536 байт (проверка при create/update)
- **MIME whitelist:** только `image/jpeg`, `image/png`, `video/mp4`, `video/webm`
- **Canonical hash:** SHA-256 от keys-sorted JSON без пробелов — стабилен между запросами
- **Нет DELETE:** мягкое удаление через disable (и профили, и назначения)
- **FK:** все ON DELETE RESTRICT

### DB-level Constraints

- `code` — UNIQUE
- `scope_type` + scope fields — CHECK (только нужные поля для каждого scope)
- `config_json` IS NOT NULL, `config_hash` IS NOT NULL
- `version` ≥ 1, `priority` ≥ 0
- `response_status` CHECK: `ok` / `not_modified` / `not_found`

### Что НЕ в Шаге 18

- ❌ Плеер, Android-приложение, client-side логика
- ❌ Frontend, админка
- ❌ Scheduler, cron, background worker
- ❌ Push-команды, remote command execution
- ❌ КСО-интеграция, POS-интеграция
- ❌ Новые permissions (используются `devices.gateway.read` / `devices.gateway.manage`)

---

## Шаг 20 — Device Content Sync State Core

**Создан:** 2026-06-17  
**Статус:** ✅ Реализован  
**Миграция:** `020_device_content_sync_state.py`

### Сводка

Backend-слой синхронизации состояния контента на устройствах. Устройство сообщает, какой manifest применён и состояние локального media-кэша. Backend хранит текущее состояние и историю отчётов. Admin API показывает состояние синхронизации.

**НЕ является:** плеером, КСО-интеграцией, Android-приложением, frontend, remote commands, push, scheduler.

**НЕ менялись:** health/alerts (Шаг 16–17), PoP, runtime config (Шаг 18–19).

### Таблицы

| Таблица | Назначение |
|---------|-----------|
| `device_manifest_apply_events` | Append-only audit manifest apply |
| `device_current_manifest_states` | Текущее состояние manifest по устройству |
| `device_media_cache_reports` | Audit batch reports media cache |
| `device_media_cache_items` | Текущее состояние media item на устройстве |

Все FK — `ON DELETE RESTRICT`. Без CASCADE.

### Device Endpoints

| Метод | Путь | Токен | Описание |
|-------|------|-------|----------|
| `POST` | `/api/device-gateway/manifest/{manifest_version_id}/apply` | Device only | Сообщить о применении manifest |
| `POST` | `/api/device-gateway/media/cache/report` | Device only | Сообщить состояние media-кэша |

### Admin Endpoints

Все под `/api/device-operations/content-sync/`, permission `devices.gateway.read`:

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/devices` | Список устройств с sync-состоянием |
| `GET` | `/devices/{gateway_device_id}` | Детализация sync-состояния устройства |
| `GET` | `/manifest-events` | История manifest apply |
| `GET` | `/cache-reports` | История cache report |
| `GET` | `/cache-items` | Состояние media items |

### Правила проверки связей

**Свой/чужой manifest:**
- `gateway_device_id` → `PublicationTarget` через `channel_id` + `store_id`
- `PublicationTarget` → `ManifestVersion` через `publication_target_id`
- Manifest не принадлежит устройству → 404

**Manifest items:**
- `manifest_item_id` должен принадлежать `manifest_version_id`
- Чужой item → 404

### SHA256 Mismatch Behaviour

- Не отклоняет весь batch
- Item сохраняется как `invalid_hash`
- `report.invalid_hash_count` увеличивается
- Нужно для диагностики повреждённого кэша
- Но: если `manifest_hash` неверный или manifest чужой — отклонить весь report

### Security

- **No local paths:** запрещены `local_path`, `file_path`, `filesystem_path`, `path` в `details_json`
- **Recursive forbidden keys:** `access_token`, `refresh_token`, `token`, `jwt`, `password`, `secret`, `credential`, `credentials`, `authorization`, `cookie`, `api_key`, `private_key`, `public_key`, `minio`, `presigned`, `presigned_url`, `stacktrace`
- **No secrets** в ответах
- **No raw exception/stacktrace**
- **Token isolation:** device token ↔ device endpoints, human token ↔ admin endpoints
- Device token на admin endpoint → 401
- Human token на device endpoint → 401
- Advertiser/device_service → 403 на admin endpoints
- `expected_sha256` всегда берётся из backend, device не может его переопределить

---

## Шаг 21 — Content Sync Health & Alerts Integration

**Создан:** 2026-06-17  
**Статус:** ✅ Реализован  
**Миграция:** `021_content_sync_alerts.py` (seed only)

### Сводка

Интеграция данных content sync (Шаг 20) в Device Operations health, problem types, store/channel агрегации и alert rules evaluation. Эксплуатация видит реальное состояние применения manifest и локального media-кэша на устройствах.

**НЕ является:** плеером, КСО-интеграцией, Android-приложением, frontend, push, scheduler, remote commands, SLA/billing.

### Новые problem types (7)

| Problem type | Условие | Severity |
|---|---|---|
| `cache_invalid_hash` | device_media_cache_items.status = invalid_hash > 0 | → critical |
| `manifest_apply_failed` | current_manifest_status = failed | → warning |
| `cache_missing_items` | missing items > 0 | → warning (≥50% → critical) |
| `cache_failed_items` | failed items > 0 | → warning (≥50% → critical) |
| `cache_report_stale` | last report старше 120 min, только для устройств с историей | → warning |
| `manifest_not_applied` | manifest доставлен, но не applied (gated: только при manifest-активности) | → warning |
| `applied_manifest_outdated` | applied manifest ≠ latest published (1 target = 1 published) | → warning |

### Новые alert types (7)

Добавлены в `ALLOWED_ALERT_TYPES` (Python-level, без DB CHECK).

| Alert type | Default rule | Severity | Enabled | Window |
|---|---|---|---|---|
| `cache_invalid_hash` | ✅ | critical | ✅ | 60 min |
| `manifest_apply_failed` | ✅ | warning | ✅ | 60 min |
| `cache_report_stale` | ✅ | warning | ❌ | 120 min |
| `manifest_not_applied` | ✅ | warning | ❌ | 120 min |
| `cache_missing_high` | ✅ | warning | ❌ | 120 min |
| `cache_failed_high` | ✅ | warning | ❌ | 120 min |
| `applied_manifest_outdated` | ✅ | warning | ❌ | 240 min |

### API Response additions

**DeviceHealthItem** — новое поле `content_sync: ContentSyncDeviceItem`:
- `current_manifest_status`, `current_manifest_hash`
- `last_manifest_applied_at`, `last_manifest_failed_at`
- `last_cache_report_at`
- `cached_items`, `missing_items`, `failed_items`, `invalid_hash_items`
- `cache_health_status` (healthy/warning/critical/unknown)

**OverviewResponse** — новое поле `content_sync: ContentSyncSummary`:
- `manifest_applied_devices`, `manifest_failed_devices`
- `devices_with_cache_reports`, `devices_with_invalid_hash`
- `devices_with_missing_items`, `devices_with_failed_items`

**StoreHealthItem / ChannelHealthItem** — новые поля:
- `manifest_applied_devices`, `manifest_failed_devices`
- `devices_with_cache_reports`, `devices_with_invalid_hash`
- `devices_with_missing_items`, `devices_with_failed_items`

### Config

```ini
DEVICE_HEALTH_CACHE_REPORT_STALE_MINUTES = 120
DEVICE_HEALTH_CACHE_MISSING_CRITICAL_RATIO = 0.50
DEVICE_HEALTH_CACHE_FAILED_CRITICAL_RATIO = 0.50
```

### Data Sources

- `device_current_manifest_states` — текущее состояние manifest (1 CTE)
- `device_media_cache_reports` — last_cache_report_at + report_count (1 CTE)
- `device_media_cache_items` — текущие counts по status (1 CTE, не сумма reports)
- `manifest_versions` / `publication_targets` — latest published manifest

Все через CTE в существующем bulk-запросе, без N+1.

### Gating

- `cache_report_stale` — только если устройство имеет историю (cache reports или applied manifest)
- `manifest_not_applied` — только если есть manifest-активность (manifest requests)
- `applied_manifest_outdated` — 1 target = 1 published manifest (deterministic)

### Шаг 21.1 — Content Sync Health & Alerts Hardening (2026-06-18)

**applied_manifest_outdated evaluator реализован:**
- SQL CTE `device_target` + `device_latest_published` для маппинга device→latest_published_manifest
- `_compute_health_status` — `applied_manifest_outdated` → warning
- `_compute_problem_types` — добавляет `applied_manifest_outdated` если current ≠ latest
- `_evaluate_applied_manifest_outdated` — трёхприоритетный матчинг (display_surface → logical_carrier → physical_device)
- Правило **disabled по умолчанию**; при ручном включении создаёт alerts
- Определение latest published manifest однозначно (1 published manifest на target)

**Disabled rules:**
- 5 disabled default rules не оцениваются в evaluate (не пополняют skipped)
- `applied_manifest_outdated` disabled — alert создаётся только при ручном включении

**Security false positive:**
- `credential_issued` / `credential_revoked` — только event_type, без payload секретов
- Никаких secrets (password, token, api_key, secret, private_key, local_path, file_path) в ответах

**Permissions:**
- Без изменений (read: devices.gateway.read, manage: devices.gateway.manage)
- Advertiser/device_service → 403 (не протестировано — нет активных пользователей с этими ролями, pre-existing)

### Шаг 21.4 — Content Sync Evaluator Dispatch Fix (2026-06-18)

**Баг:** content-sync evaluators (`cache_invalid_hash`, `manifest_apply_failed`, `applied_manifest_outdated`) не вызывались в основном цикле `_do_evaluate`. Они попадали в `else: skipped`, хотя правила были enabled. Причина: `_do_evaluate` не имел `elif`-блоков для этих alert_type.

**Исправление:**
- Добавлены 3 `elif` блока в `_do_evaluate` для `cache_invalid_hash`, `manifest_apply_failed`, `applied_manifest_outdated`
- Создан `_evaluate_applied_manifest_outdated_v2` (V2-обёртка с `run_id` для evaluation history)
- `_evaluate_cache_invalid_hash_v2` и `_evaluate_manifest_apply_failed_v2` уже существовали — добавлены только вызовы

**Результат:**
- `created: 0, skipped: 3` → `created: 4, skipped: 0`
- 1 `cache_invalid_hash` alert + 3 `applied_manifest_outdated` alerts
- Repeated evaluate: без дублей (`created=0, repeated=N`)
- Disabled rules: не оцениваются, не skipped
- Правило `applied_manifest_outdated` disabled по умолчанию; alert создаётся только при ручном включении

**Row duplication:** `/api/device-operations/devices` — 62 строки, 62 уникальных device_code, без дублей. CTE `DISTINCT ON` из 21.2 сохранён.

### Что НЕ в Шаге 21

- ❌ Новые endpoints
- ❌ Новые permissions
- ❌ Device endpoints изменения
- ❌ КСО-плеер, Android player, frontend, push, scheduler
- ❌ SLA/billing/auto-remediation
- ❌ Изменение таблиц (только seed миграция)
