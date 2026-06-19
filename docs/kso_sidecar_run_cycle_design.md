# Mini-Design: KSO Sidecar Run Cycle

**Статус:** Mini-design. Код не пишем.
**Шаг:** 25.27
**Дата:** 19 июня 2026
**Основание:** `docs/kso_sidecar_agent_design.md`, реализованные модули Шагов 25.0–25.26

---

## 1. Goal

Спроектировать единый безопасный **run-cycle** — оркестратор, который выполняет полный цикл синхронизации KSO Sidecar Agent за один проход: preflight → auth → runtime config → heartbeat → manifest → media → cache report → финальный статус.

Run-cycle — это **brain** sidecar-агента. Все существующие CLI-команды (`sync-runtime-config`, `sync-manifest`, `sync-media`, `report-media-cache`, `heartbeat-once`) являются строительными блоками, но они независимы и каждый делает свой auth. Run-cycle объединяет их в одну согласованную последовательность с **единым токеном в памяти**, единой retry-политикой и единым финальным статусом.

---

## 2. Why a Single Orchestrator

Сейчас каждая CLI-команда независимо:
- Читает config
- Читает secret
- Делает auth
- Выполняет свою операцию

Проблемы:
1. **N × auth на цикл** — каждая команда получает новый токен. Backend видит N auth-запросов за цикл.
2. **Нет целостной картины** — нельзя сказать «цикл прошёл успешно» или «цикл degraded».
3. **Нет единого agent_status** — каждая команда не обновляет общий статус агента.
4. **Дублирование кода** — config-read, secret-read, auth повторяются в каждой команде.

Run-cycle решает это: **один токен → одна последовательность → один статус**.

---

## 3. Sequence of a Single Cycle

```
┌─────────────────────────────────────────────┐
│                PREFLIGHT                     │
│  validate_root(root)                         │
│  ensure all dirs exist (init if needed)      │
│  check disk space (optional future)          │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│           READ LOCAL CONFIG                  │
│  local_config.read_config(root)              │
│  → fatal if missing/invalid                  │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│             READ SECRET                      │
│  secret_store.read_secret(root, dev_flag)    │
│  → fatal if missing/empty                    │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│           AUTH (ONCE PER CYCLE)              │
│  DeviceAuthClient.authenticate()             │
│  retry: 429/5xx/network (optional)           │
│  → fatal on 401/403/422                      │
│  TokenState ONLY in memory                   │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│        SYNC RUNTIME CONFIG (non-fatal)       │
│  RuntimeConfigClient.fetch_current()         │
│  RuntimeConfigStore.write_runtime_config()   │
│  ETag/304 → not_modified (ok)                │
│  200 → updated (ok)                          │
│  error → warning, continue                   │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│          HEARTBEAT #1 (non-fatal)            │
│  HeartbeatClient.send_heartbeat()            │
│  status: "ok" / "warning"                    │
│  retry: optional                             │
│  500 → warning, continue                     │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│          SYNC MANIFEST (non-fatal)           │
│  ManifestClient.fetch_current()              │
│  ManifestStore.write_current_manifest()      │
│  served → written (ok)                       │
│  not_modified → skip (ok)                    │
│  no_manifest → skip (warning)                │
│  error → fatal only if no local manifest     │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│           SYNC MEDIA (non-fatal)             │
│  For each manifest item:                     │
│    verify_media_file()                       │
│    if valid → skip                           │
│    if corrupted → quarantine + redownload    │
│    if missing → download                     │
│  MediaClient.fetch_media()                   │
│  MediaCache.write_media_atomic()             │
│  per-item errors → non-fatal, continue       │
│  track: downloaded, cached, missing, failed  │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│        REPORT MEDIA CACHE (non-fatal)        │
│  build_media_cache_report_payload()          │
│  MediaCacheReportClient.send_report()        │
│  200 → sent (ok)                             │
│  500 → retryable, но как non-fatal warning   │
│  401/403 → warning, continue                 │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│         UPDATE AGENT STATUS                   │
│  agent_status.update_status()                │
│  status: ok / warning / error / degraded     │
│  запись атомарная, без token/secret/path     │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│       FINAL HEARTBEAT (non-fatal)            │
│  HeartbeatClient.send_heartbeat()            │
│  status: отражает итог цикла                 │
│  cache_items_count: из media cache           │
│  current_manifest_hash: из локального        │
│  500 → warning                               │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│            CYCLE COMPLETE                     │
│  return RunCycleResult                       │
│  safe summary → log                          │
│  token уничтожается (выход из scope)         │
└─────────────────────────────────────────────┘
```

---

## 4. Fatal vs Non-Fatal Rules

### 4.1 Fatal (прерывают цикл)

| Шаг | Условие | Причина |
|---|---|---|
| Preflight | `root` не существует или не инициализирован | Некуда писать |
| Config | `config/agent_config.json` missing или invalid | Неизвестен backend |
| Secret | `config/device_secret.dev` missing или empty | Невозможно auth |
| Auth | 401/403/422 | Неверные credentials |
| Auth | Token истёк до первого backend-запроса | Нет валидного токена |
| Manifest | Нет локального manifest И backend manifest error | Нет manifest для КСО |
| Disk | Невозможно создать required directories | Некуда писать media |
| Security | Forbidden values в config/secret/runtime config | Нарушение безопасности |

Fatal → `sys.exit(1)`, agent_status = `"error"`.

### 4.2 Non-Fatal (продолжают цикл)

| Шаг | Условие | Влияние на статус |
|---|---|---|
| Runtime config | 304 Not Modified | ok (уже актуальный) |
| Runtime config | 500 / network error | warning |
| Heartbeat #1 | 500 / timeout | warning |
| Manifest | not_modified (304/ETag) | ok |
| Manifest | no_manifest (204) | warning |
| Media | 404 на отдельный item | warning |
| Media | sha256 mismatch | warning |
| Media | 500 на download | warning |
| Report | 500 | warning |
| Report | 401 (token expired mid-cycle) | warning |
| Heartbeat #2 | 500 | warning |

Non-fatal ошибки **не прерывают цикл** — агент продолжает и фиксирует итоговый статус.

---

## 5. Cycle Statuses

| Статус | Условие |
|---|---|
| `ok` | Все шаги успешны: manifest есть, media cache complete, report sent |
| `warning` | Цикл завершён, но есть non-fatal ошибки: часть media не скачалась, report 500, etc. Локальный manifest пригоден, КСО может работать |
| `degraded` | Backend недоступен (все запросы упали), НО есть валидный локальный manifest + complete media cache. Агент может оставаться в local-ready state |
| `error` | Fatal ошибка: нет config, нет secret, auth failed, manifest absent. КСО не может работать |

### 5.1 Degraded Behaviour

Если backend недоступен, но локально есть:
- `config/runtime_config.json` (валидный)
- `manifest/current_manifest.json` (валидный)
- `media/current/` — complete (все файлы на месте, sha256 совпадают)

То агент может:
- **Оставаться в `degraded`** — не удалять старый manifest/media
- **Не перезаписывать** manifest/media пустыми/partial данными
- **Не создавать** пустые файлы
- КСО ПО читает ТОЛЬКО готовые файлы из `manifest/current_manifest.json` и `media/current/`
- Если файлы в `media/current/` валидны — КСО может показывать старый контент
- Если manifest отсутствует или invalid — КСО не может работать → `error`

### 5.2 Offline Mode (будущее)

Полноценный offline mode (копить PoP, отложенная отправка) — **отдельный будущий шаг**. На этом шаге только degraded detection.

---

## 6. Token Lifecycle

```
┌──────────────────────────────────────────────────────┐
│  run_once(root, options)                              │
│    │                                                   │
│    ├─ auth = DeviceAuthClient.authenticate()           │
│    │    → TokenState(token="...", expires_at=...)      │
│    │    → В ПАМЯТИ. НЕ на диске.                       │
│    │                                                   │
│    ├─ rc_client.fetch_current(token_state)    ← reuse │
│    ├─ hb_client.send_heartbeat(token_state)   ← reuse │
│    ├─ mf_client.fetch_current(token_state)    ← reuse │
│    ├─ md_client.fetch_media(token_state)      ← reuse │
│    ├─ rp_client.send_report(token_state)      ← reuse │
│    ├─ hb_client.send_heartbeat(token_state)   ← reuse │
│    │                                                   │
│    └─ return RunCycleResult(...)                       │
│         token_state выходит из scope → GC               │
└──────────────────────────────────────────────────────┘
```

**Правила:**
- Token **не пишется на диск** — только в памяти (`TokenState` dataclass)
- Token **не передаётся в subprocess** — run-cycle работает в одном процессе
- Token **не выводится в stdout/stderr/logs**
- `Authorization` header **не логируется**
- Если token истёк **до первого backend-запроса** — fatal error
- Если токен истекает **mid-cycle** (report 401) — non-fatal warning, остальные шаги завершены

---

## 7. Retry Policy

### 7.1 Auth Retry

| Параметр | Значение |
|---|---|
| Когда | `--retry-auth` флаг |
| Retryable | 429, 5xx, network error, timeout |
| Non-retryable | 401, 403, 422 |
| Max attempts | 3 (default, настраивается) |
| Backoff | Exponential + jitter (существующий `RetryBackoffManager`) |

### 7.2 Heartbeat Retry

| Параметр | Значение |
|---|---|
| Когда | `--retry-heartbeat` флаг (будущий) |
| Retryable | 429, 5xx, network error, timeout |
| Non-retryable | 400, 401, 403, 422 |
| Max attempts | 3 |

### 7.3 Media Download Retry

**Отдельный будущий шаг.** На этом шаге media download без retry — ошибка на отдельный item = non-fatal skip.

### 7.4 Report Retry

**Отдельный будущий шаг.** На этом шаге report без retry — ошибка = non-fatal warning.

### 7.5 Global Rules

- **Нет бесконечного retry** — каждый шаг имеет `max_attempts`
- **Нет retry на 401/403/422** — не спамим backend с неверными credentials
- **Jitter обязателен** — чтобы не создавать thundering herd
- **Sleep между retry** через `time.sleep()` (подменяемый в тестах)

---

## 8. Agent Status Fields (будущее расширение)

Текущий `agent_status.json`:

```json
{
  "status": "running",
  "updated_at": "2026-06-19T10:00:00Z",
  "offline_mode": false,
  "cached_items": 0,
  "invalid_hash_items": 0,
  "errors": []
}
```

**Предлагаемое расширение** (поля для run-cycle):

```json
{
  "status": "ok",
  "updated_at": "2026-06-19T10:00:00Z",
  "offline_mode": false,
  "cached_items": 5,
  "invalid_hash_items": 0,
  "errors": [],

  "_cycle": {
    "last_cycle_at": "2026-06-19T10:00:00Z",
    "last_cycle_status": "ok",
    "last_cycle_duration_ms": 1234,
    "last_auth_status": "ok",
    "runtime_config_status": "updated",
    "manifest_status": "updated",
    "manifest_items_total": 5,
    "media_items_total": 5,
    "media_items_cached": 5,
    "media_items_missing": 0,
    "media_items_failed": 0,
    "media_cache_complete": true,
    "media_report_status": "sent",
    "last_error_code": null,
    "last_error_message": null
  }
}
```

**Правила для `_cycle`:**
- Не писать `token`, `secret`, `access_token`, `device_secret`
- Не писать `Authorization`, `Bearer`
- Не писать `local_path`, `file_path`, `media_path`, `creatives/`
- `last_error_code` — safe короткая строка (напр. `"AUTH_FAIL"`, `"MANIFEST_404"`)
- `last_error_message` — safe, без forbidden substrings, ≤ 200 chars
- Все поля опциональны — отсутствие `_cycle` означает «цикл ещё не запускался»

---

## 9. Safe Output / Logging

**Запрещено в stdout, stderr, и логах:**
- `access_token` / JWT
- `device_secret`
- `Authorization: Bearer ...`
- Request body целиком
- Response body целиком
- Полный manifest (только counts + hash prefix)
- Report items list целиком (только counts)
- Media bytes
- `local_path`, `file_path`, `media_path`, `creatives/`
- Stacktrace (в normal CLI output; допустимо в debug-режиме)

**Разрешено:**
- `manifest_version_id` (первые 12 символов)
- `manifest_hash` (первые 12 символов)
- Counts: `items_total`, `cached_count`, `missing_count`, etc.
- Статусы: `ok`, `warning`, `error`, `degraded`
- `backend_status`
- `duration_ms`

---

## 10. Future Files

### 10.1 `apps/kso_sidecar_agent/kso_sidecar_agent/run_cycle.py`

Основной модуль оркестратора. Предлагаемая структура:

```python
# Data classes
@dataclass
class RunCycleOptions:
    """Options for a single run cycle."""
    dev_secret_store: bool = False
    retry_auth: bool = False
    auth_max_attempts: int = 3
    retry_heartbeat: bool = False
    heartbeat_max_attempts: int = 3
    skip_media: bool = False
    skip_report: bool = False
    max_cycle_sec: int = 120


@dataclass
class RunCycleResult:
    """Result of a single run cycle."""
    status: str                      # ok | warning | error | degraded
    duration_ms: float
    auth_status: str
    runtime_config_status: str
    manifest_status: str
    manifest_items_total: int
    media_items_total: int
    media_items_cached: int
    media_items_missing: int
    media_items_failed: int
    media_cache_complete: bool
    media_report_status: str
    heartbeat1_sent: bool
    heartbeat2_sent: bool
    error_code: Optional[str]
    error_message: Optional[str]
    cycle_at: str                    # ISO8601
```

**Функции:**

```python
def run_once(root, options, now=None) -> RunCycleResult:
    """Execute one full run cycle. Returns result, never raises (все ошибки в result)."""

def _preflight(root) -> None:
    """Validate root + ensure dirs. Raises on fatal."""

def _build_context(root, options, now) -> RunCycleContext:
    """Read config, secret, build HTTP client, authenticate once."""

def _sync_runtime_config(ctx) -> str:
    """Returns 'updated' | 'not_modified' | 'error'."""

def _sync_manifest(ctx) -> Tuple[str, int]:
    """Returns (status, items_count)."""

def _sync_media(ctx, manifest_items) -> dict:
    """Returns {downloaded, cached, missing, failed, complete}."""

def _send_report(ctx, payload) -> str:
    """Returns 'sent' | 'failed' | 'skipped'."""

def _send_heartbeat(ctx, status, extra=None) -> bool:
    """Returns True if sent."""

def _update_cycle_status(root, result) -> None:
    """Atomically update agent_status.json with cycle result."""

def _determine_cycle_status(result_parts) -> str:
    """Determine ok | warning | error | degraded from step results."""
```

### 10.2 `apps/kso_sidecar_agent/tests/test_run_cycle.py`

Тесты для run-cycle. **Только stdlib fake HTTP server на 127.0.0.1.** Реальный backend не вызывается.

---

## 11. Future CLI

```bash
python3 -m kso_sidecar_agent.cli run-once \
  --root /tmp/kso-agent-root \
  --dev-secret-store

# Опциональные флаги:
#   --retry-auth              Retry для auth
#   --auth-max-attempts 3     Макс. попыток auth
#   --retry-heartbeat         Retry для heartbeat
#   --heartbeat-max-attempts 3
#   --skip-media              Пропустить media sync
#   --skip-report             Пропустить cache report
#   --max-cycle-sec 120       Макс. длительность цикла
```

**Вывод (успех):**
```
run_cycle:           ok
duration_ms:         1234
auth:                ok
runtime_config:      updated
manifest:            updated (5 items)
media:               complete (5/5 cached)
media_report:        sent
heartbeat:           sent
```

**Вывод (warning):**
```
run_cycle:           warning
duration_ms:         2345
auth:                ok
runtime_config:      not_modified
manifest:            updated (5 items)
media:               incomplete (3/5 cached, 2 missing)
media_report:        sent
heartbeat:           sent
```

**Никогда не выводит:** token, secret, Authorization, request/response body, full manifest, report items list, media bytes, paths.

---

## 12. Future Tests

### 12.1 Success Flow

| Тест | Описание |
|---|---|
| `test_run_once_full_success` | Все шаги успешны: auth→rc→hb1→manifest→media→report→hb2 |
| `test_token_reused_by_all_clients` | Один TokenState передан всем клиентам, auth вызван 1 раз |
| `test_auth_called_once` | `POST /auth/token` ровно 1 раз за цикл |
| `test_runtime_config_updated` | 200 → статус `updated` |
| `test_runtime_config_not_modified` | 304 → статус `not_modified`, цикл продолжается |
| `test_manifest_served` | 200 → written, items count правильный |
| `test_manifest_not_modified` | 304 → skip, старый manifest сохранён |
| `test_media_all_downloaded` | Все items скачаны, `cache_complete=true` |
| `test_media_existing_skipped` | Существующие валидные файлы не перекачиваются |
| `test_report_sent` | 200 → `media_report_status=sent` |
| `test_heartbeats_sent` | Два heartbeat (начало и конец цикла) |

### 12.2 Degraded / Warning Flow

| Тест | Описание |
|---|---|
| `test_backend_down_but_local_cache_complete` | Все запросы падают, но локальный manifest+media валидны → `degraded` |
| `test_media_partial_failure` | Часть media не скачалась → `warning`, `cache_complete=false` |
| `test_report_500_warning` | Report 500 → `warning`, цикл продолжается |
| `test_heartbeat_500_warning` | Heartbeat 500 → `warning` |
| `test_no_manifest_warning` | Backend вернул `no_manifest` → `warning`, старый manifest сохранён |

### 12.3 Error Flow

| Тест | Описание |
|---|---|
| `test_config_missing_fatal` | Нет config → `error` |
| `test_secret_missing_fatal` | Нет secret → `error` |
| `test_auth_401_fatal` | Auth 401 → `error` |
| `test_auth_403_fatal` | Auth 403 → `error` |
| `test_auth_500_retry_then_ok` | Auth 500 → retry → success |
| `test_auth_retry_exhausted_fatal` | Auth 500 × N → exhausted → `error` |
| `test_no_manifest_and_backend_error_fatal` | Нет локального manifest И backend error → `error` |

### 12.4 Security

| Тест | Описание |
|---|---|
| `test_no_token_in_output` | Token не в stdout/stderr |
| `test_no_secret_in_output` | Secret не в stdout/stderr |
| `test_no_authorization_in_output` | Authorization не в stdout/stderr |
| `test_no_paths_in_output` | `local_path`/`file_path`/`media_path`/`creatives/` не в output |
| `test_no_full_manifest_in_output` | Полный manifest не в output |
| `test_no_report_items_in_output` | Report items не в output |
| `test_token_not_on_disk` | Token не записан в `config/`, `status/`, `logs/` |
| `test_agent_status_safe` | `_cycle` поля не содержат forbidden substrings |
| `test_no_real_backend` | Реальный backend не вызывается |
| `test_no_partial_files` | В `media/current/` нет `.download`/`.tmp` после цикла |

---

## 13. Risks

| Риск | Mitigation |
|---|---|
| Token истекает mid-cycle | Heartbeat и report — последние шаги; если report 401 — non-fatal warning |
| Backend недоступен весь цикл | Degraded detection: если есть локальный manifest+media → `degraded` |
| Media download зависает | `request_timeout_sec` в `HttpClientConfig`, `max_cycle_sec` общий таймаут |
| Цикл длится дольше интервала | `max_cycle_sec` — abort если превышен; loop scheduler (будущий шаг) |
| Конфликт с КСО ПО | Атомарная запись manifest/media; КСО читает только `current_manifest.json` и `media/current/` |
| Partial files в `media/current/` | `write_media_atomic` гарантирует: staging → verify → `os.replace` |
| Большой manifest (1000+ items) | `max_cycle_sec` общий таймаут; можно `--skip-media` для быстрого цикла |

---

## 14. What We Are NOT Implementing on This Step

- ❌ `run_cycle.py` (код оркестратора)
- ❌ `run-once` CLI command
- ❌ Run loop (повторяющиеся циклы)
- ❌ Systemd service / daemon
- ❌ Scheduler / cron
- ❌ Playback / PoP
- ❌ Offline mode (полноценный)
- ❌ Media download retry
- ❌ Report retry
- ❌ Новые backend endpoints
- ❌ Backend changes
- ❌ Миграции БД
- ❌ Real backend calls
- ❌ `_cycle` поля в `agent_status.json` (agent_status пока не меняем)
- ❌ `RunCycleOptions`, `RunCycleResult`, `RunCycleContext` dataclasses (код)

**Всё это — будущие шаги.** Данный документ — только проектирование.

---

## 15. Compatibility with Existing Commands

Run-cycle **не заменяет** существующие CLI-команды. Они остаются доступны для:
- Ручной диагностики (`auth-check`, `doctor`, `manifest-status`, `media-cache-status`)
- Ручной синхронизации (`sync-runtime-config`, `sync-manifest`, `sync-media`)
- Ручной отправки (`heartbeat-once`, `report-media-cache`)

Run-cycle — это **надстройка**, которая вызывает те же клиенты (`DeviceAuthClient`, `RuntimeConfigClient`, etc.) в правильном порядке с единым токеном.

---

## 16. Summary

| Аспект | Решение |
|---|---|
| Auth | Один раз в начале цикла, token только в памяти |
| Порядок | preflight → config → secret → auth → rc → hb1 → manifest → media → report → status → hb2 |
| Fatal | config/secret/auth/manifest absent |
| Non-fatal | rc 304, manifest not_modified, media partial, report 500, hb 500 |
| Статусы | ok, warning, error, degraded |
| Degraded | Backend down, но локальный cache пригоден |
| Token | В памяти, не на диске, не в subprocess |
| Retry | Auth/heartbeat — опционально; media/report — будущие шаги |
| Security | Без token/secret/auth/path/body в output |
| Тесты | Только fake HTTP server, без реального backend |
