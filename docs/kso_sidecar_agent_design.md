# Mini-Design: KSO Sidecar Agent

**Статус:** Mini-design. Код не пишем.
**Шаг:** 25
**Дата:** 18 июня 2026
**Основание:** docs/kso_player_architecture.md (Вариант D)

---

## 1. Goal

Спроектировать реальный KSO Sidecar Agent — лёгкий фоновый процесс, который работает на стороне КСО-терминала рядом с КСО ПО. Agent синхронизирует manifest и media с backend, читает PoP-события и статус от КСО ПО через локальную файловую систему по контракту `docs/kso_local_interface_contract.md`.

**Agent НЕ показывает рекламу сам.** Он готовит файлы для КСО ПО, а КСО ПО само решает, когда и как показывать контент на idle-экране.

---

## 2. Scope (Входит)

| # | Функция | Описание |
|---|---|---|
| 1 | Device Auth | Аутентификация как device через `device_code` + `device_secret`, получение JWT |
| 2 | Runtime Config Sync | `GET /config/current` с ETag/304 |
| 3 | Manifest Sync | `GET /manifest/current` с hash/304 |
| 4 | Media Download | `GET /media/{id}` + `GET /media/{id}/metadata`, проверка sha256 |
| 5 | Local File Store | Раскладка manifest/media/config в локальную папку по контракту |
| 6 | KSO Status Reader | Чтение `status/kso_status.json` от КСО ПО |
| 7 | PoP Queue Reader | Чтение `pop/events.log` (JSONL, append-only) от КСО ПО |
| 8 | PoP Batch Sender | `POST /pop/events/batch` |
| 9 | Heartbeat | `POST /heartbeat` с status=ok/warning/error |
| 10 | Manifest Apply Report | `POST /manifest/{id}/apply` |
| 11 | Cache Report | `POST /media/cache/report` |
| 12 | Offline Mode | Работа без backend, копить PoP |
| 13 | Safety Guards | Не обновлять media при не-idle, соблюдать kso_safety |
| 14 | Structured Logging | Без secrets, без customer/payment/receipt данных |

---

## 3. Out of Scope (НЕ входит)

- ❌ Показ рекламы / рендеринг / overlay / UI
- ❌ Android player / КСО-плеер
- ❌ Installer / auto-update
- ❌ Remote commands / push-уведомления
- ❌ Inbound сетевые порты
- ❌ Вмешательство в кассовый процесс / оплату / сканирование
- ❌ Сбор персональных / платёжных / чековых данных
- ❌ Новые backend endpoint'ы
- ❌ Миграции БД
- ❌ Frontend / админка
- ❌ Управление сертификацией КСО

---

## 4. Placement (Где разместить код)

### Сравнение вариантов

| Вариант | Путь | Характер | Рекомендация |
|---|---|---|---|
| A | `apps/kso_sidecar_agent/` | Production-сервис, часть монорепо | ✅ **Рекомендуется** |
| B | `tools/kso_sidecar_agent/` | Dev-утилита (как simulator) | ❌ Неверно: это production |
| C | `services/kso_sidecar_agent/` | Альтернативное имя | ⚠️ Допустимо, но `apps/` ближе к `players/` |

**Рекомендация: `apps/kso_sidecar_agent/`**

Обоснование:
- Agent — production-компонент, не dev-утилита. `tools/` зарезервирован для simulator и других dev-инструментов.
- `apps/` уже используется для KSO-специфичных компонентов в архитектуре.
- В будущем рядом могут быть `apps/kso_windows_service/`, `apps/kso_installer/`.

**Альтернатива:** `players/kso_sidecar_agent/` — если проект рассматривает agent как один из «плееров», но поскольку agent не плеер, `apps/` точнее.

---

## 5. Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        KSO TERMINAL                                  │
│                                                                      │
│  ┌──────────────────┐          ┌────────────────────────────────┐   │
│  │     КСО ПО       │          │      SIDECAR AGENT              │   │
│  │                  │          │                                 │   │
│  │  ┌────────────┐  │  read    │  ┌───────────────────────────┐ │   │
│  │  │Idle Screen │◄─┼──────────┼──┤ LocalFileStore            │ │   │
│  │  │(читает     │  │          │  │ media/current/            │ │   │
│  │  │ media из   │  │          │  │ manifest/current.json     │ │   │
│  │  │ кэша)      │  │          │  └───────────────────────────┘ │   │
│  │  └────────────┘  │          │                                 │   │
│  │                  │  write   │  ┌───────────────────────────┐ │   │
│  │  ┌────────────┐  ├──────────┼─►│ PoPQueueReader             │ │   │
│  │  │PoP Log     │  │          │  │ pop/events.log             │ │   │
│  │  └────────────┘  │          │  └───────────────────────────┘ │   │
│  │                  │  write   │  ┌───────────────────────────┐ │   │
│  │  ┌────────────┐  ├──────────┼─►│ KSOStatusReader            │ │   │
│  │  │KSO Status  │  │          │  │ status/kso_status.json     │ │   │
│  │  └────────────┘  │          │  └───────────────────────────┘ │   │
│  └──────────────────┘          │                                 │   │
│                                 │  ┌───────────────────────────┐ │   │
│                                 │  │      SCHEDULER             │ │   │
│                                 │  │  (asyncio event loop)     │ │   │
│                                 │  └──┬───┬───┬───┬───┬────────┘ │   │
│                                 │     │   │   │   │   │           │   │
│                                 │  ┌──┘   │   │   │   └──────┐   │   │
│                                 │  │  ┌───┘   │   └────┐     │   │   │
│                                 │  ▼  ▼       ▼        ▼     ▼   │   │
│                                 │ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌──┐│   │
│                                 │ │Auth│ │Cfg │ │Mft │ │Med │ │PoP││   │
│                                 │ │Clnt│ │Clnt│ │Clnt│ │Clnt│ │Snd││   │
│                                 │ └────┘ └────┘ └────┘ └────┘ └──┘│   │
│                                 │                                 │   │
│                                 │  ┌───────────────────────────┐ │   │
│                                 │  │  SafeLogger               │ │   │
│                                 │  │  logs/agent.log           │ │   │
│                                 │  └───────────────────────────┘ │   │
│                                 │                                 │   │
│                                 │        HTTPS (outbound-only)    │   │
│                                 └─────────────┬───────────────────┘   │
│                                               │                       │
└───────────────────────────────────────────────┼───────────────────────┘
                                                │
                                     ┌──────────▼──────────┐
                                     │      BACKEND        │
                                     │   (уже готов)       │
                                     └─────────────────────┘
```

### Компоненты

| Компонент | Назначение | Ключевые зависимости |
|---|---|---|
| **AgentCLI** | Точка входа, парсинг аргументов, запуск scheduler | argparse, asyncio |
| **DeviceAuthClient** | `POST /auth/token`, refresh за 30с до exp, хранение JWT в памяти | aiohttp |
| **RuntimeConfigClient** | `GET /config/current` (ETag/304), парсинг kso_safety + интервалов | aiohttp |
| **ManifestClient** | `GET /manifest/current` (hash/304), `GET /manifest/{id}` (fallback), `POST /manifest/{id}/apply` | aiohttp |
| **MediaClient** | `GET /media/{id}/metadata`, `GET /media/{id}` (stream), sha256-проверка, `POST /media/cache/report` | aiohttp, hashlib |
| **LocalFileStore** | Атомарная запись manifest/config/media в локальные папки по контракту | aiofiles, pathlib |
| **CacheManager** | LRU-вытеснение медиа при превышении `media_cache_max_mb` | pathlib |
| **KSOStatusReader** | Чтение `status/kso_status.json`, определение state + can_show_ads | json |
| **PoPQueueReader** | Чтение `pop/events.log` (offset-based, JSONL), парсинг новых строк | aiofiles, json |
| **PoPBatchSender** | `POST /pop/events/batch`, отправка накопленных PoP-событий | aiohttp |
| **HeartbeatSender** | `POST /heartbeat` с текущим статусом агента | aiohttp |
| **RetryBackoffManager** | Exponential backoff + jitter для повторных попыток | asyncio, random |
| **SafeLogger** | Структурное логирование: без secrets, без customer/payment/receipt данных | logging / structlog |

---

## 6. Runtime Lifecycle

### 6.1 Cold Start

```
1. Чтение аргументов: --device-code, --device-secret, --base-url
2. Создание структуры папок (LocalFileStore)
3. Device Auth: POST /auth/token → JWT
4. Config Sync: GET /config/current → runtime config + интервалы
5. Запуск параллельных loop'ов (WARM START)
```

### 6.2 Warm Loops (параллельные, asyncio tasks)

| Loop | Интервал | Endpoint | Примечание |
|---|---|---|---|
| **Auth Refresh** | За 30с до exp JWT | `POST /auth/token` | JWT в памяти, не на диске |
| **Heartbeat** | `heartbeat_interval_sec` (def: 60s) | `POST /heartbeat` | status: ok/warning/error |
| **Config Refresh** | `manifest_refresh_interval_sec` (def: 60s) | `GET /config/current` | ETag/304 |
| **Manifest Refresh** | `manifest_refresh_interval_sec` | `GET /manifest/current` | hash/304 |
| **Media Sync** | При новом manifest | `GET /media/{id}/metadata` + `GET /media/{id}` | sha256, staging→current |
| **Cache Report** | После media sync | `POST /media/cache/report` | Batch per manifest cycle |
| **Manifest Apply** | После успешной раскладки | `POST /manifest/{id}/apply` | status: applied/failed |
| **PoP Flush** | `pop_flush_interval_sec` (def: 300s) | `POST /pop/events/batch` | Offset-based |
| **Diagnostics** | `diagnostics_sample_interval_sec` (def: 300s) | Локально | Только если `diagnostics_enabled` |

### 6.3 Graceful Shutdown

```
1. SIGTERM / SIGINT → остановить все loop'ы
2. Flush PoP: отправить всё из pop/events.log
3. Дождаться ответа или timeout
4. Сохранить текущий offset в state.json
5. Выход
```

---

## 7. Backend Endpoint Compatibility Matrix

Все endpoint'ы имеют префикс `/api/device-gateway`.

| # | Endpoint | HTTP | Назначение | Token | ETag/304 | 401 | 403 | 404 | 409 | 422 | 5xx |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `/auth/token` | POST | Получение JWT | ❌ | ❌ | — | — | — | — | 422 | Retry + backoff |
| 2 | `/heartbeat` | POST | Heartbeat | JWT | ❌ | Re-auth | Fatal | — | — | — | Retry |
| 3 | `/config/current` | GET | Runtime config | JWT | ✅ ETag | Re-auth | Fatal | — | — | — | Retry |
| 4 | `/manifest/current` | GET | Текущий manifest | JWT | ✅ hash/304 | Re-auth | Fatal | — | — | — | Retry |
| 5 | `/manifest/{id}` | GET | Manifest по ID | JWT | ❌ | Re-auth | Fatal | Log warn | — | — | Retry |
| 6 | `/media/{id}/metadata` | GET | Media metadata + sha256 | JWT | ✅ cached sha | Re-auth | Fatal | Log warn | — | — | Retry |
| 7 | `/media/{id}` | GET | Скачивание media file | JWT | ✅ cached sha | Re-auth | Fatal | Log warn | — | — | Retry |
| 8 | `/manifest/{id}/apply` | POST | Apply report | JWT | ❌ | Re-auth | Fatal | Log warn | 409 → ok (idempotent) | 422 | Retry |
| 9 | `/media/cache/report` | POST | Cache report | JWT | ❌ | Re-auth | Fatal | — | — | 422 | Retry |
| 10 | `/pop/events` | POST | Одиночный PoP | JWT | ❌ | Re-auth | Fatal | — | — | 422 | Retry |
| 11 | `/pop/events/batch` | POST | Batch PoP | JWT | ❌ | Re-auth | Fatal | — | — | 422 | Retry |

### Легенда кодов ответа

| Код | Действие агента |
|---|---|
| **200/201** | OK |
| **304** | Использовать кэшированное значение |
| **401** | Re-auth → если после re-auth всё ещё 401 → 3 попытки → fatal stop, alert |
| **403** | Fatal: неверные права устройства. Останов. Alert в heartbeat. |
| **404** | Для manifest/media: warn, пропустить item. Для apply: warn. |
| **409** | Для apply: OK (уже применён, идемпотентно). |
| **422** | Log validation error. Не retry этот payload. |
| **5xx** | Retry с exponential backoff + jitter. Max 5 попыток. |

### Что НЕ логировать из ответов backend

- ❌ `device_secret`
- ❌ JWT (access token)
- ❌ `local_path` / `file_path`
- ❌ `stacktrace` (только error message)
- ❌ Полные тела ответов с чувствительными полями

### Локальное кэширование

| Данные | Кэш | Срок |
|---|---|---|
| JWT | Память | До exp |
| Runtime config | `config/current.json` | До нового ETag |
| Manifest | `manifest/current.json` | До нового hash |
| Media files | `media/cache/` | LRU, до `media_cache_max_mb` |
| PoP events | `pop/events.log` | До успешной отправки |

---

## 8. Local File Contract

Agent строго следует `docs/kso_local_interface_contract.md`.

### 8.1 Файлы, которые пишет Agent

| Файл | Описание |
|---|---|
| `config/device.json` | `device_code`, `device_id` (без `device_secret`!) |
| `config/runtime_config.json` | Текущий runtime config с `kso_safety` |
| `manifest/current_manifest.json` | Текущий активный manifest |
| `manifest/current_manifest.sha256` | SHA256 манифеста для проверки целостности |
| `media/current/*` | Медиафайлы, готовые к показу |
| `media/current/manifest.json` | Краткий manifest для КСО ПО |
| `status/agent_status.json` | Статус агента для мониторинга КСО ПО |

### 8.2 Файлы, которые читает Agent

| Файл | Источник | Описание |
|---|---|---|
| `status/kso_status.json` | КСО ПО | Текущее состояние КСО (idle/transaction/...) |
| `pop/events.log` | КСО ПО | PoP-события (JSONL, append-only) |

### 8.3 Atomic Write Rules

- **Media:** скачать в `media/staging/` → проверить sha256 → rename в `media/current/`
- **Manifest:** записать `.tmp` → вычислить `.sha256.tmp` → атомарный rename обоих
- **Config:** записать `.tmp` → rename

### 8.4 PoP Queue: Lock / Rotation

1. КСО ПО пишет в `pop/events.log` (append-only)
2. Agent читает по offset (запомненному в `state/`)
3. При flush: rename `events.log` → `pop/events.processing`
4. КСО ПО начинает писать в новый `events.log`
5. Agent отправляет batch из `events.processing`
6. Успех: rename → `pop/sent/events.<date>.log`
7. Ошибка: append обратно в начало нового `events.log`

### 8.5 Cleanup

- Старые media: LRU-вытеснение при превышении `media_cache_max_mb`
- Quarantine: файлы с sha256 mismatch → `media/quarantine/`
- PoP sent: ротация по дате, удаление старше 30 дней (конфигурируемо)
- `media/staging/` и `tmp/`: очищать при старте

---

## 9. Secrets / Secure Storage

**Правило: secrets никогда не на диске, кроме `device_secret`.**

| Секрет | Хранение | Защита |
|---|---|---|
| `device_code` | `config/device.json` (0600) | Не секрет сам по себе, но ограничить доступ |
| `device_secret` | Отдельный файл (0400) или OS keychain | Никогда не логировать, не передавать кроме `/auth/token` |
| JWT access token | **Только память** | Никогда не писать на диск |
| Refresh token | **Только память** (если будет) | Никогда не писать на диск |

### Стратегия по ОС

| ОС | Механизм | Приоритет |
|---|---|---|
| **Linux** | Файл с правами 0400, владелец `kso-agent` | Минимальный вариант |
| **Linux** (systemd) | `LoadCredential=` / `${CREDENTIALS_DIRECTORY}` | Рекомендуется |
| **Windows** | DPAPI / Windows Credential Manager | Рекомендуется |
| **Windows** | Файл с ACL (только SYSTEM + kso-agent) | Минимальный вариант |

### Что НЕ хранить в runtime_config.json

- ❌ `device_secret`
- ❌ JWT / refresh token
- ❌ Пароли
- ❌ API-ключи

---

## 10. Offline Mode

### 10.1 Правила перехода

| Ситуация | Действие |
|---|---|
| Backend доступен | Полный цикл |
| Backend недоступен, `offline_mode_enabled=true` | Продолжать по последнему валидному manifest |
| Backend недоступен, `offline_mode_enabled=false` | Остановить sync, ждать |
| Offline > `max_offline_duration_sec` | Очистить `media/current/`, остановить показ |
| Manifest TTL истёк (`manifest_ttl_sec`) | Очистить `media/current/`, остановить показ |

### 10.2 PoP в Offline

1. КСО ПО продолжает писать события в `pop/events.log`
2. Agent накапливает их (не отправляет)
3. При восстановлении сети: flush всей очереди одним batch
4. Если очередь > 10 000 событий: FIFO, старые теряются, alert

### 10.3 Восстановление после Offline

```
1. Auth refresh (мог истечь JWT)
2. Config refresh (мог измениться config)
3. Manifest refresh (мог выйти новый)
4. Media sync (если manifest изменился)
5. Flush PoP queue (отправить накопленное)
6. Heartbeat с status=ok
```

### 10.4 Дедупликация PoP

- Каждое событие имеет `device_event_id` (UUID v4 от КСО ПО)
- Backend дедуплицирует по `device_event_id`
- Agent не дедуплицирует сам, но сохраняет последний отправленный `device_event_id` в памяти
- При перезапуске agent: возможны дубли → backend отфильтрует

---

## 11. Retry / Backoff

### 11.1 Что retry

| Операция | Стратегия | Max попыток |
|---|---|---|
| Все HTTP-запросы (кроме auth) | Exponential backoff + jitter | 5 |
| Auth (POST /auth/token) | Exponential backoff + jitter | 3 |
| Media download | Exponential backoff + jitter | 3 |
| PoP batch send | Exponential backoff + jitter | 5 |
| Sha256 mismatch (media) | Re-download | 3 |

### 11.2 Что НЕ retry

- 403 Forbidden → fatal
- 422 Unprocessable → не retry этот payload
- Ошибка декодирования manifest/config → не retry, ждать следующего цикла
- Path traversal / symlink в media → не retry, quarantine

### 11.3 Параметры backoff

```
base_delay: 1 сек
max_delay:  300 сек (5 минут)
jitter:     ±25% случайно
multiplier: 2x
```

### 11.4 Постоянный 401

```
1. POST /auth/token (re-auth)
2. Если 401 → подождать 5с, повторить (до 3 раз)
3. Если всё ещё 401 → STOP. alert в heartbeat (status=error)
4. Не пытаться бесконечно — возможно, device деактивирован
```

---

## 12. Safety Guards

### 12.1 Принцип: fail-closed / fail-silent

При любой неопределённости — останавливаем обновление `media/current/`. КСО ПО перестаёт видеть новые файлы → прекращает показ.

### 12.2 Обязательные проверки перед обновлением media/current/

```
ЕСЛИ kso_status.state != "idle"           → НЕ обновлять media/current/
ЕСЛИ kso_status.can_show_ads == false     → НЕ обновлять media/current/
ЕСЛИ kso_safety.stop_on_transaction       → проверить state != transaction
ЕСЛИ kso_safety.stop_on_payment           → проверить state != payment
ЕСЛИ kso_safety.stop_on_error_screen      → проверить state != error
ЕСЛИ kso_safety.stop_on_service_mode      → проверить state != service_mode
ЕСЛИ CPU > max_cpu_percent                → пропустить цикл
ЕСЛИ RAM > max_memory_mb                  → очистить старый кэш
```

### 12.3 Что Agent НЕ делает

- ❌ Не открывает inbound порты
- ❌ Не выполняет remote commands
- ❌ Не управляет экраном КСО
- ❌ Не вмешивается в кассовый процесс
- ❌ Не собирает персональные / платёжные / чековые данные
- ❌ Не хранит JWT на диске

### 12.4 Fail behavior из runtime config

| `fail_behavior` | Действие при ошибке |
|---|---|
| `fail_silent` (рекомендуется) | Тихо остановить обновление media/current/, продолжать sync/heartbeat/PoP |
| `fail_closed` | Полностью остановить агент. `agent_status.status = "stopped"` |

---

## 13. Logging Rules

### 13.1 Что разрешено логировать

- ✅ URL endpoint'ов (без query параметров с токенами)
- ✅ HTTP status codes
- ✅ Длительность запросов
- ✅ Кол-во синхронизированных media items
- ✅ Кол-во отправленных PoP-событий
- ✅ Ошибки валидации (без payload)
- ✅ Переходы между online/offline

### 13.2 Что запрещено логировать

- ❌ `device_secret`
- ❌ JWT (access token)
- ❌ Полные HTTP-заголовки (Authorization)
- ❌ `local_path` / `file_path` / `filesystem_path`
- ❌ Персональные данные (ФИО, телефон, email, карты лояльности)
- ❌ Платёжные данные (PAN, CVV, сумма, авторизация)
- ❌ Чековые данные (номер чека, SKU, цены, скидки)
- ❌ `stacktrace` в production (только error message)

### 13.3 Структура логов

```
Формат: JSON Lines (одна запись = одна строка)
Поля: timestamp, level, component, message, device_id, session_id, duration_ms, status_code
```

### 13.4 Ротация

- `logs/agent.log` — ротация по размеру (10 MB) или daily
- `logs/agent.error.log` — только WARNING и ERROR
- `logs/archive/` — ротированные файлы, удалять старше 30 дней

### 13.5 Уровни из runtime config

- `log_level` из `GET /config/current`: debug/info/warning/error
- `diagnostics_enabled`: если true → дополнительно: CPU%, RAM MB, disk usage

---

## 14. Testing Strategy (будущие тесты)

### 14.1 Unit Tests

- Каждый компонент изолированно с mock-объектами
- `DeviceAuthClient` с fake HTTP
- `RuntimeConfigClient` с захардкоженным config
- `ManifestClient` с локальным JSON
- `PoPQueueReader` с тестовым `events.log`

### 14.2 Local File Tests

- `LocalFileStore`: atomic write, rename, symlink reject
- `CacheManager`: LRU с лимитом `media_cache_max_mb`
- `KSOStatusReader`: парсинг валидного/невалидного `kso_status.json`

### 14.3 No-Network Simulator Tests

- Agent + KSO Simulator на одной машине
- Полный цикл: agent синхронизирует manifest/media → simulator «показывает» → agent читает PoP
- Без реального backend: fake-сервер с известными ответами

### 14.4 Integration Tests

- Agent + реальный backend (dev-окружение)
- Cold start → config → manifest → media → PoP → campaign report

### 14.5 Offline Tests

- Отключение сети во время цикла
- Накопление PoP → восстановление → flush
- Превышение `max_offline_duration_sec` → остановка показа

### 14.6 PoP Queue Durability Tests

- `kill -9` agent во время flush → рестарт → PoP не потеряны
- Дубликаты через `device_event_id` → backend дедупликация

### 14.7 Security Leakage Tests

- `grep -r device_secret logs/` → должно быть пусто
- `grep -r "eyJ" logs/` (JWT pattern) → должно быть пусто
- `grep -r local_path pop/` → должно быть пусто

---

## 15. Risk Matrix

| # | Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|---|
| 1 | Неизвестная ОС КСО | Высокая | Высокое | Кроссплатформенный Python/Go. Абстракция над ФС. |
| 2 | Нет API состояний КСО (idle/payment/...) | Высокая | Среднее | Чтение через файл `kso_status.json`. Если КСО не умеет — отдельный вопрос поставщику. |
| 3 | Поставщик не умеет JSONL | Средняя | Среднее | Альтернативный формат (CSV? разделяемый буфер?). Обсудить с поставщиком. |
| 4 | Нет прав на сервис (root/admin) | Средняя | Высокое | Агент как user-level процесс. Минимальные права. |
| 5 | Ограничения сертификации кассового ПО | Средняя | Высокое | Минимальный attack surface. Agent не трогает кассовый процесс. |
| 6 | Слабое хранилище secrets (нет keychain) | Средняя | Среднее | 0400-файл как минимум. Документировать требования. |
| 7 | Переполнение диска media-кэшем | Средняя | Среднее | LRU + `media_cache_max_mb`. Мониторинг + alert. |
| 8 | Долгий offline (> суток) | Низкая | Среднее | `max_offline_duration_sec`. Stop показ. Очистить media/current/. |
| 9| Рассинхрон manifest / media | Средняя | Среднее | Sha256-проверка каждого файла. Quarantine при mismatch. |
| 10 | Ложный PoP (КСО ПО написало событие, но показа не было) | Средняя | Низкое | Backend flush даёт audit trail. Ответственность КСО ПО. |
| 11 | Agent crash во время atomic rename | Низкая | Низкое | `.tmp` → `rename()` атомарен в пределах ФС. Не консистентности. |
| 12 | Memory leak при долгой работе | Низкая | Среднее | Мониторинг RAM. Graceful restart при превышении `max_memory_mb`. |

---

## 16. Что НЕ делаем на этом шаге

Настоящий документ — **только mini-design**. В рамках Шага 25 мы **НЕ реализуем**:

- ❌ Код agent (ни одной строки)
- ❌ Installer / auto-update
- ❌ Remote commands
- ❌ Overlay / UI
- ❌ Android player
- ❌ Изменения backend
- ❌ Новые endpoint'ы
- ❌ Миграции БД
- ❌ Управление кассой
- ❌ Сбор чековых / платёжных / персональных данных

---

## 17. Связанные документы

- `docs/kso_player_architecture.md` — архитектура Sidecar Agent (Вариант D)
- `docs/kso_local_interface_contract.md` — контракт локального интерфейса
- `docs/kso_simulator_design.md` — mini-design симулятора
- `docs/kso_vendor_integration_questions.md` — вопросы поставщику КСО
- `docs/kso_player_runtime_contract.md` — backend-контракт (11 endpoint'ов)
- Backend: `app/domains/device_gateway/` — 12 device-facing endpoint'ов

---

*Документ создан: 18 июня 2026. Следующий шаг: утверждение → реализация skeleton.*
