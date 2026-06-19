# KSO Sidecar Agent — Skeleton

**Статус:** 🏗 Skeleton. Production-код ещё не реализован.

## Что это

KSO Sidecar Agent — будущий production-агент, который будет работать на КСО-терминале рядом с КСО ПО. Он синхронизирует manifest и media с backend, раскладывает их в локальную папку по контракту `docs/kso_local_interface_contract.md`, и отправляет PoP-события и heartbeat'ы.

**Пока это ТОЛЬКО каркас (skeleton).**

## Что сейчас работает

| Команда | Описание |
|---|---|
| `version` | Показать версию |
| `init-local-root` | Создать структуру папок + `agent_status.json` |
| `set-status` | Обновить статус агента (running/stopped/warning/...) |
| `write-config` | Создать/обновить локальный config |
| `config-status` | Проверить валидность config |
| `doctor` | Проверить здоровье папок, статуса и config |
| `secret-store-check` | Проверить состояние dev secret store |
| `secret-store-set` | Записать dev secret (только через stdin) |
|| `secret-store-delete` | Удалить dev secret |
|| `auth-check` | Проверить device auth (только safe summary, без токена) |
|| `runtime-config-status` | Показать здоровье runtime config |
|| `sync-runtime-config` | Полный пайплайн auth→fetch→save runtime config |
|| `heartbeat-once` | Отправить одиночный heartbeat |
|| `manifest-status` | Показать локальный manifest |
|| `sync-manifest` | Sync manifest: auth→fetch→save |
|| `sync-media` | Sync media: auth→download→media/current |
|| `media-cache-status` | Показать локальный media cache |
|| `report-media-cache` | Send media cache report: auth→build payload→POST /media/cache/report |

## Что НЕ работает (будет отдельными шагами)

- ✅ Device auth + retry/backoff (базовый `auth-check` + `--retry-auth`)
- ✅ Runtime config sync (`/config/current`) — полный пайплайн auth→fetch→save в CLI `sync-runtime-config`
- ✅ Heartbeat (`/heartbeat`) — одиночная отправка с опциональным retry (`heartbeat-once --retry-heartbeat`)
- ✅ Manifest sync (`/manifest/current`, `/manifest/{id}`) — внутренний клиент + локальный store + CLI sync
- ✅ MediaClient (внутренний): `GET /media/{id}/metadata`, `GET /media/{id}` — metadata и content
- ✅ Media cache (локальный): atomic write staging→current, sha256 verify, quarantine, `media-cache-status` CLI
- ✅ Media sync (`sync-media`): auth → read local manifest → download media → `media/current/`
- ✅ MediaCacheReportClient (внутренний): `POST /media/cache/report` — отправка отчёта о состоянии кэша
- ❌ Media retry (retry для media download пока не подключён)
- ❌ PoP flush (`/pop/events/batch`)
- ❌ Offline mode
- ❌ KSO status reading

## Быстрый старт

```bash
cd apps/kso_sidecar_agent

# Инициализация
python3 -m kso_sidecar_agent.cli init-local-root --root /tmp/kso-agent-root

# Записать config (non-secret!)
python3 -m kso_sidecar_agent.cli write-config \
  --root /tmp/kso-agent-root \
  --backend-base-url https://retail-media.example.local \
  --device-code a-05954

# Опциональные параметры config
python3 -m kso_sidecar_agent.cli write-config \
  --root /tmp/kso-agent-root \
  --backend-base-url https://example.com \
  --device-code a-05954 \
  --tls-verify true \
  --request-timeout-sec 10 \
  --local-interface-version 1.0

# Проверить config
python3 -m kso_sidecar_agent.cli config-status --root /tmp/kso-agent-root

# Установить статус
python3 -m kso_sidecar_agent.cli set-status \
  --root /tmp/kso-agent-root --status running

# Полная проверка здоровье
python3 -m kso_sidecar_agent.cli doctor --root /tmp/kso-agent-root
```

### Allowed statuses

`stopped` | `starting` | `running` | `warning` | `error` | `offline`

### agent_config.json (non-secret!)

```json
{
  "backend_base_url": "https://retail-media.example.local",
  "device_code": "a-05954",
  "tls_verify": true,
  "request_timeout_sec": 10,
  "local_interface_version": "1.0"
}
```

**Что НЕ хранится в config:**
- ❌ `device_secret`
- ❌ JWT / refresh token
- ❌ Пароли / API-ключи
- ❌ `private_key` / `payment_card` / `receipt`

**Валидация:**
- `backend_base_url` — только http/https, без username/password, без forbidden query параметров
- `device_code` — 3-64 символа (`[a-zA-Z0-9._-]`)
- `tls_verify` — bool (default true)
- `request_timeout_sec` — 1-120 (default 10)
- Forbidden substrings во всех полях: token, jwt, password, secret, api_key, private_key, payment_card, receipt, local_path, file_path

## agent_status.json

```json
{
  "status": "running",
  "updated_at": "2026-06-18T10:00:00Z",
  "offline_mode": false,
  "cached_items": 0,
  "invalid_hash_items": 0,
  "errors": []
}
```

**Правила:** max 20 errors, каждая ≤200 символов, forbidden substrings — reject. Атомарная запись через `.tmp` → `os.replace()`.

## Dev Secret Store (dev-only)

**Production secret storage ещё не реализован.** Только dev-only fallback.

```bash
# Включить dev режим: флаг --dev-secret-store или KSO_DEV_SECRET_STORE=1
# Secret только через stdin, НЕ через CLI аргументы

printf "dev-value-1234567890" | python3 -m kso_sidecar_agent.cli secret-store-set \
  --root /tmp/kso-agent-root --dev-secret-store --stdin

python3 -m kso_sidecar_agent.cli secret-store-check \
  --root /tmp/kso-agent-root --dev-secret-store

python3 -m kso_sidecar_agent.cli secret-store-delete \
  --root /tmp/kso-agent-root --dev-secret-store
```

**Secret НЕ передаётся через CLI аргументы** (видны в /proc). Только stdin или env.

## TokenState (внутренний модуль)

Внутренний Python-модуль `token_state.py` для будущего Device Auth Client:

- **HTTP auth ещё не реализован** — backend-вызовов нет
- **Access token хранится только в памяти** (`TokenState` dataclass)
- **Access token не пишется на диск** (ни в `config/`, ни в `status/`, ни в `logs/`)
- **Access token не выводится в logs/status/doctor**
- `safe_summary()` возвращает только метаданные (authenticated, device_code, expires_at, status) — без значения токена
- `repr()` и `str()` не раскрывают токен
- CLI-команд для token нет

**Когда Device Auth Client будет реализован (будущие шаги), `TokenState` будет хранить JWT, полученный от `POST /api/device-gateway/auth/token`.**

## SafeHttpClient (внутренний модуль)

Внутренний Python-модуль `http_client.py` — безопасный HTTP-клиент на stdlib:

- **Нет новых зависимостей** — только `urllib.request`
- **Пока не используется для device auth** — backend-вызовы ещё не реализованы
- Не логирует request/response body
- Не логирует Authorization headers
- Не логирует secrets/passwords/api_keys
- Path validation: только `/`, без `..`, без forbidden substrings
- Header validation: reject значений с forbidden substrings
- HTTP ошибки классифицируются как retryable/non-retryable
- Имеет точное allowlist-исключение для `/api/device-gateway/auth/token`

## DeviceAuthClient (базовый)

Внутренний Python-модуль `device_auth_client.py` — базовый клиент для device auth:

- **`DeviceAuthClient`** — выполняет `POST /api/device-gateway/auth/token` и возвращает `TokenState` в память
- **Retry/backoff подключён** — при передаче `retry_manager` делает повторы на transient ошибках (429/5xx/network/timeout)
- **Retry включается явно** — через `--retry-auth` в CLI или `retry_manager=` в API
- **401/403/422 не retry** — не спамим backend при неверных credentials
- **Token refresh не реализован** — будет отдельным шагом
- **Token хранится только в памяти** — не пишется на диск, не логируется, не выводится
- **Secret читается через callable** — не привязан жёстко к dev secret store
- **Для dev используется `--dev-secret-store`** — production secret storage будет отдельным шагом

### CLI: `auth-check`

```bash
# Настроить config и secret
python3 -m kso_sidecar_agent.cli init-local-root --root /tmp/kso-agent-root
python3 -m kso_sidecar_agent.cli write-config \
  --root /tmp/kso-agent-root \
  --backend-base-url http://127.0.0.1:8080 \
  --device-code a-05954
printf "dev-value-1234567890" | python3 -m kso_sidecar_agent.cli secret-store-set \
  --root /tmp/kso-agent-root --dev-secret-store --stdin

# Проверить auth с retry:
python3 -m kso_sidecar_agent.cli auth-check \
  --root /tmp/kso-agent-root --dev-secret-store --retry-auth --auth-max-attempts 5

# Вывод:
#   authenticated:     True
#   device_code:       a-05954
#   device_id:         550e8400-...
#   status:            active
#   expires_in_sec:    3600
```

**Никогда не выводит:** access_token, device_secret.

## RetryBackoffManager (внутренний модуль)

Внутренний Python-модуль `retry_backoff.py` — менеджер retry/backoff для будущих backend-вызовов:

- **`BackoffPolicy`** — конфигурация: max_attempts, base_delay_sec, max_delay_sec, multiplier, jitter_ratio
- **`RetryDecision`** — результат решения: retryable, should_retry, delay_sec, reason (без forbidden substrings)
- **`RetryBackoffManager`** — классификация ошибок, exponential backoff + jitter, принятие решений
- **`execute_with_retries()`** — простой helper для выполнения с повторами
- **Пока не подключён к DeviceAuthClient** — retry для auth будет отдельным шагом
- **Не хранит token/secret** — reason сообщения редактируются: forbidden → `[REDACTED]`
- **Не логирует payload/body**

### Default policy

| Параметр | Значение |
|---|---|
| max_attempts | 3 |
| base_delay_sec | 2.0 |
| max_delay_sec | 60.0 |
| multiplier | 2.0 |
| jitter_ratio | 0.25 ( ±25%) |

### Error classification

| Тип ошибки | Retryable |
|---|---|
| `HttpClientError` (429/5xx/timeout/network) | ✅ |
| `HttpClientError` (400/401/403/404/409/422/TLS) | ❌ |
| `TimeoutError`, `ConnectionError`, `OSError` | ✅ |
| `ValueError`, `RuntimeError` | ❌ |

## RuntimeConfigClient (внутренний модуль)

Внутренний Python-модуль `runtime_config_client.py` — клиент для получения runtime config:

- **`RuntimeConfigClient`** — выполняет `GET /api/device-gateway/config/current` с Authorization header
- **`RuntimeConfigSnapshot`** — результат: status, config_hash, etag, config (в памяти), generated_at
- **Поддержка ETag/304** — `If-None-Match` / `ETag`, при 304 возвращает `not_modified=true`
- **Config пока не пишется на диск** — только в памяти (`RuntimeConfigSnapshot.config`)
- **Retry пока не подключён** — будет отдельным шагом
- **Forbidden keys/values в config → reject** (token, secret, api_key, …)

### Backend endpoint

```
GET /api/device-gateway/config/current
Authorization: Bearer <device_jwt>
If-None-Match: <config_hash>    (optional)

200:
{
  "status": "ok",
  "gateway_device_id": "...",
  "config_hash": "sha256...",
  "config": { ... },
  "generated_at": "2026-06-18T10:00:00+00:00"
}
ETag: "<config_hash>"

304: (empty body)
```

## RuntimeConfigStore (внутренний модуль)

Внутренний Python-модуль `runtime_config_store.py` — локальное сохранение runtime config:

- **`write_runtime_config(root, snapshot)`** — атомарная запись `config/runtime_config.json`
- **`read_runtime_config(root)`** — чтение и валидация
- **`runtime_config_status(root)`** — safe summary без полного config
- **Forbidden keys/values reject** — token, jwt, password, secret, api_key, private_key, payment_card, receipt, local_path, file_path, authorization, bearer
- **Файл `config/runtime_config.json`** — только проверенные данные, без secrets

### CLI: `runtime-config-status`

```bash
python3 -m kso_sidecar_agent.cli runtime-config-status --root /tmp/kso-agent-root
# Runtime config: PRESENT (valid)
#   config_hash:       abc123hash12...
#   etag_present:      True
#   generated_at:      2026-06-18T10:00:00+00:00
#   fetched_at:        2026-06-18T10:01:00+00:00
#   config_keys_count: 2
```

### CLI: `sync-runtime-config`

Полный цикл: auth → config/current → локальное сохранение.

```bash
python3 -m kso_sidecar_agent.cli sync-runtime-config \
  --root /tmp/kso-agent-root --dev-secret-store

# Опционально:
#   --retry-auth           Retry для auth при 5xx/429
#   --auth-max-attempts 5  Максимум попыток auth (default: 3)

# Вывод (updated):
#   runtime_config_sync: updated
#   config_hash:        abc123hash123
#   config_keys_count:  2

# Вывод (not_modified):
#   runtime_config_sync: not_modified
#   etag_present:       true
```

**Никогда не выводит:** access token, device_secret, Authorization header, response body, полный config.

### Doctor integration

`doctor` проверяет `runtime_config.json`:
- Отсутствует → warning (не fatal)
- Валиден → `runtime_config_ok: True`
- Invalid → `runtime_config_ok: False` + error

## MediaCacheReportClient + CLI: `report-media-cache`

Внутренний Python-модуль `media_cache_report_client.py` + CLI-команда для отправки отчёта о состоянии media cache в backend:

- **`MediaCacheReportClient`** (внутренний): `POST /api/device-gateway/media/cache/report` — отправка отчёта
- **`build_media_cache_report_payload(root)`** — строит payload из локального manifest + media cache status
- **CLI `report-media-cache`** — полный пайплайн: config→secret→auth→build payload→POST report

### Backend endpoint

```
POST /api/device-gateway/media/cache/report
Authorization: Bearer ***

Request (MediaCacheReportRequest):
{
  "manifest_version_id": "uuid",
  "manifest_hash": "64 hex chars",
  "device_reported_at": "optional ISO8601",
  "items": [
    {
      "manifest_item_id": "uuid",
      "status": "cached" | "missing" | "failed" | "invalid_hash" | "evicted",
      "reported_sha256": "optional 64 hex (required if cached)",
      "file_size_bytes": "optional int >= 0",
      "cached_at": "optional datetime",
      "error_code": "optional string max 64",
      "message": "optional string max 512",
      "details_json": {}
    }
  ],
  "details_json": {}
}

Response (MediaCacheReportResponse):
{
  "status": "ok",
  "gateway_device_id": "uuid",
  "manifest_version_id": "uuid",
  "total_items": int,
  "cached_count": int,
  "missing_count": int,
  "failed_count": int,
  "invalid_hash_count": int
}
```

### Использование

```bash
# Базовый вызов (auth без retry)
python3 -m kso_sidecar_agent.cli report-media-cache \
  --root /tmp/kso-agent-root --dev-secret-store

# С retry для auth
python3 -m kso_sidecar_agent.cli report-media-cache \
  --root /tmp/kso-agent-root --dev-secret-store \
  --retry-auth --auth-max-attempts 3

# Вывод:
#   media_cache_report:  sent
#   backend_status:      ok
#   items_total:         2
#   cached_count:        0
#   missing_count:       2
#   failed_count:        0
#   invalid_hash_count:  0
```

**Что делает команда:**
- Auth → build local report (manifest + media cache status) → POST /media/cache/report
- **НЕ** запускает sync-media
- **НЕ** скачивает media
- **НЕ** имеет retry для самого report (только auth retry через `--retry-auth`)
- Token хранится только в памяти
- Secret только из dev secret store

**Никогда не выводит:** access token, device_secret, Authorization header, request body, response body, full manifest, report items list, media bytes, local_path, file_path, media_path.

## HeartbeatClient (внутренний модуль)

Внутренний Python-модуль `heartbeat_client.py` — клиент для отправки heartbeat:

- **`HeartbeatClient`** — выполняет `POST /api/device-gateway/heartbeat` с Authorization header
- **`HeartbeatPayload`** — валидирует status (ok/warning/error), message, device_time, версии, storage, manifest_hash
- **`HeartbeatResult`** — safe результат: status, backend_status, heartbeat_id
- **Heartbeat loop пока не реализован** — только одиночная отправка
- **Retry (опционально)** — `HeartbeatClient` принимает `retry_manager` + `sleep_fn`
  - Retry: 429/5xx/network error/timeout
  - НЕ retry: 400/401/403/404/409/422/invalid JSON/TLS error
  - Invalid payload и expired token — reject до HTTP-запроса
  - Retry включается явно через CLI `--retry-heartbeat`
- **Forbidden substrings в payload reject** — token, secret, api_key, …

### Backend endpoint

```
POST /api/device-gateway/heartbeat
Authorization: Bearer <device_jwt>

Request (DeviceHeartbeatRequest):
{
  "status": "ok",
  "message": "agent alive",           // optional, max 200
  "device_time": "2026-...",          // optional
  "app_version": "0.1.0",            // optional, max 128
  "os_version": "linux",             // optional, max 128
  "storage_free_mb": 1024,           // optional, >=0
  "cache_items_count": 0,            // optional, >=0
  "current_manifest_hash": "ab..64", // optional, 64 hex
  "details_json": {}                 // optional
}

Response (DeviceHeartbeatResponse):
{"id": "uuid", "gateway_device_id": "uuid", "status": "ok", ...}
```

### CLI: `heartbeat-once`

```bash
# Базовый вызов (без retry)
python3 -m kso_sidecar_agent.cli heartbeat-once \
  --root /tmp/kso-agent-root --dev-secret-store \
  --status ok --message "agent alive"

# С retry для heartbeat (500/429 → повторы)
python3 -m kso_sidecar_agent.cli heartbeat-once \
  --root /tmp/kso-agent-root --dev-secret-store \
  --retry-heartbeat --heartbeat-max-attempts 3

# Retry и для auth и для heartbeat вместе
python3 -m kso_sidecar_agent.cli heartbeat-once \
  --root /tmp/kso-agent-root --dev-secret-store \
  --retry-auth --retry-heartbeat

# Вывод:
#   heartbeat:         sent
#   status:            ok
#   backend_status:    accepted
#   attempts:          1
```

**Retry-флаги:**
- `--retry-heartbeat` — включить retry для heartbeat (exponential backoff + jitter)
- `--heartbeat-max-attempts N` — макс. попыток (по умолчанию 3)
- `--retry-auth` — retry для auth (существующий флаг, работает отдельно)

**Никогда не выводит:** access token, device_secret, Authorization header, request body, response body.

## ManifestClient + ManifestStore (внутренние модули)

Внутренние Python-модули для получения и локального хранения manifest:

**ManifestClient** (`manifest_client.py`):
- `GET /api/device-gateway/manifest/current` и `GET /api/device-gateway/manifest/{id}`
- `ManifestSnapshot` — safe результат с метаданными
- Retry пока не подключён
- Media download не реализован

**ManifestStore** (`manifest_store.py`):
- `normalize_manifest_snapshot(snapshot)` → локальный формат
- `write_current_manifest(root, snapshot)` — атомарная запись
- `read_current_manifest(root)` — чтение + валидация
- `manifest_store_status(root)` — safe summary (CLI `manifest-status`)
- **Локальный файл:** `manifest/current_manifest.json`
- **Совместим с:** `simulator.manifest_reader` и `kso_local_interface_contract.md`
- **Media_path не пишется** в локальный manifest

### Backend endpoints

```
GET /api/device-gateway/manifest/current
# Response: {"status":"served","manifest_version_id":"uuid",
#            "manifest_hash":"64hex","published_at":"...",
#            "manifest":{"items":[...]}}

GET /api/device-gateway/manifest/{manifest_version_id}
# Response: {"manifest_version_id":"uuid","manifest_items":[...]}
```

### Использование

```python
from kso_sidecar_agent.manifest_client import ManifestClient

client = ManifestClient(http_client=...)
snapshot = client.fetch_current(token_state)
# {status: "served", items_count: 5, ...}

summary = snapshot.safe_summary()
# Только метаданные — без полного manifest и без token
```

**Никогда не выводит:** access token, Authorization header, полный manifest, response body.

### CLI: `sync-manifest`

```bash
python3 -m kso_sidecar_agent.cli sync-manifest \
  --root /tmp/kso-agent-root --dev-secret-store

# Вывод:
#   manifest_sync:        updated
#   manifest_version_id:  a0eebc99-9c0b...
#   manifest_hash:       cccccccccccc...
#   items_count:         5

# С retry для auth:
python3 -m kso_sidecar_agent.cli sync-manifest \
  --root /tmp/kso-agent-root --dev-secret-store --retry-auth
```

**Полный пайплайн:** config → secret → auth → manifest/current → normalize → validate → atomic write.

**Обработка статусов:**
- `served` → normalize, validate, атомарная запись `manifest/current_manifest.json`
- `not_modified` → файл не перезаписывается
- `no_manifest` → пустой manifest не создаётся, старый не удаляется

**Retry:** только для auth при `--retry-auth`. Retry манифест-запроса — отдельным шагом.

**Media download:** не реализован. Manifest не содержит media_path.

## Безопасность

- ❌ Не хранит `device_secret`
- ❌ Не хранит JWT
- ❌ Не ходит в backend
- ❌ Не собирает персональные/платёжные/чековые данные
- ✅ Logger: forbidden → `[REDACTED]`
- ✅ Forbidden words в config/status/errors — reject
- ✅ Атомарная запись: не оставляет `.tmp`

## Тесты

```bash
cd apps/kso_sidecar_agent
python3 -m unittest discover -s tests -v
```

## Связанные документы

- `docs/kso_sidecar_agent_design.md` — mini-design агента
- `docs/kso_player_architecture.md` — архитектура (Вариант D)
- `docs/kso_local_interface_contract.md` — контракт локального интерфейса
