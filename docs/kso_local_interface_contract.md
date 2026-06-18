# KSO Local Interface Contract

**Документ для поставщика КСО ПО.** Описывает локальное взаимодействие между KSO Sidecar Agent и КСО ПО через общую файловую систему.

**Статус:** Проект контракта. Пути примерные — финальные зависят от ОС КСО.
**Дата:** 18 июня 2026

---

## 1. Базовая модель взаимодействия

```
┌──────────────────────────────────────────────────────────────┐
│                      КСО ТЕРМИНАЛ                             │
│                                                               │
│  ┌──────────────────┐       ┌───────────────────────────┐    │
│  │     КСО ПО       │       │    SIDECAR AGENT           │    │
│  │                  │       │                           │    │
│  │  ┌────────────┐  │ read  │  ┌─────────────────┐      │    │
│  │  │Idle Screen │◄─┼───────┼──┤ media/current/   │      │    │
│  │  │(показывает)│  │       │  └─────────────────┘      │    │
│  │  └────────────┘  │       │                           │    │
│  │                  │ write │  ┌─────────────────┐      │    │
│  │  ┌────────────┐  ├───────┼─►│ pop/events.log  │      │    │
│  │  │PoP Log     │  │       │  └─────────────────┘      │    │
│  │  └────────────┘  │       │                           │    │
│  │                  │ write │  ┌─────────────────┐      │    │
│  │  ┌────────────┐  ├───────┼─►│ status/         │      │    │
│  │  │KSO Status  │  │       │  │ kso_status.json │      │    │
│  │  └────────────┘  │       │  └─────────────────┘      │    │
│  └──────────────────┘       │                           │    │
│                              │         HTTPS ────────────┼───►
│                              │         (outbound only)   │    │
│                              └───────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘

ПОТОК ДАННЫХ:

1. Agent (outbound-only) → скачивает manifest + media из backend
2. Agent → кладёт готовые файлы в media/current/
3. КСО ПО → читает media/current/, показывает на idle screen
4. КСО ПО → пишет факт показа в pop/events.log (JSONL)
5. КСО ПО → пишет своё состояние в status/kso_status.json
6. Agent → читает pop/events.log и kso_status.json
7. Agent → отправляет PoP и heartbeat в backend
```

**Ключевые принципы:**

- Agent и КСО ПО **не запускают друг друга**. Они независимые процессы.
- Agent **не управляет** экраном КСО. Он только готовит файлы.
- КСО ПО **само решает**, когда и как показывать контент из `media/current/`.
- Agent **не пишет** в файлы КСО ПО. КСО ПО **не пишет** в файлы agent (кроме оговорённых).

---

## 2. Локальная структура папок

### Linux

```
/var/lib/kso-adapter/                  # root-папка (владелец: kso-agent)
│
├── config/                             # Конфигурация (agent пишет, КСО ПО не читает)
│   ├── device.json                     # device_code, device_id (без device_secret!)
│   └── runtime_config.json             # Текущий runtime config с kso_safety
│
├── manifest/                           # Манифест (agent пишет, КСО ПО — read-only)
│   ├── current_manifest.json           # Текущий активный manifest
│   └── current_manifest.sha256         # SHA256 манифеста (для проверки целостности)
│
├── media/                              # Медиафайлы
│   ├── current/                        # ГОТОВЫЕ к показу (КСО ПО читает)
│   │   ├── <item_id_1>.jpg
│   │   ├── <item_id_2>.mp4
│   │   └── manifest.json               # Краткий manifest для КСО ПО (только media-список)
│   ├── staging/                        # В процессе загрузки (КСО ПО НЕ читает)
│   └── quarantine/                     # Повреждённые файлы (SHA256 mismatch)
│
├── pop/                                # События показов (PoP)
│   ├── events.log                      # Неотправленные события (КСО ПО пишет, agent читает)
│   ├── events.processing               # В процессе отправки (agent lock-файл)
│   └── sent/                           # Отправленные (ротация)
│       └── events.2026-06-18.log
│
├── status/                             # Статус (обоюдный мониторинг)
│   ├── agent_status.json               # Статус agent (agent пишет, КСО ПО — read-only)
│   └── kso_status.json                 # Статус КСО (КСО ПО пишет, agent читает)
│
└── logs/                               # Логи agent (agent пишет, КСО ПО — read-only)
    ├── agent.log
    └── agent.error.log
```

### Windows

```
C:\ProgramData\KSOAdapter\
├── config\
│   ├── device.json
│   └── runtime_config.json
├── manifest\
│   ├── current_manifest.json
│   └── current_manifest.sha256
├── media\
│   ├── current\
│   ├── staging\
│   └── quarantine\
├── pop\
│   ├── events.log
│   ├── events.processing
│   └── sent\
├── status\
│   ├── agent_status.json
│   └── kso_status.json
└── logs\
    ├── agent.log
    └── agent.error.log
```

**Важно:**

- Пути **примерные**. Финальные зависят от ОС КСО и требований поставщика.
- `local_path` и `file_path` **никогда** не отправляются в backend.
- Абсолютные пути не должны появляться в API-запросах.

---

## 3. Права доступа

| Путь | Agent (kso-agent) | КСО ПО (kso-app) | Примечание |
|---|---|---|---|
| `config/` | read/write | **нет доступа** | `device.json` содержит `device_code` (не `device_secret`!) |
| `manifest/` | read/write | read-only | Только чтение манифеста |
| `media/current/` | read/write | read-only | КСО ПО только читает готовые файлы |
| `media/staging/` | read/write | **нет доступа** | Временные файлы, не готовы к показу |
| `media/quarantine/` | read/write | **нет доступа** | Повреждённые файлы |
| `pop/events.log` | read/write | append-only | КСО ПО дописывает события в конец |
| `pop/events.processing` | read/write | **нет доступа** | Блокировка agent |
| `status/agent_status.json` | write | read-only | Статус agent для мониторинга |
| `status/kso_status.json` | read-only | write | Статус КСО для agent |
| `logs/` | write | read-only | Логи без секретов |

---

## 4. Atomic Write Rules

### Media: загрузка и публикация

```
1. Agent скачивает media → сохраняет в media/staging/<item_id>.tmp
2. Agent проверяет SHA256 файла в staging
3. Если SHA256 совпадает:
   └── rename media/staging/<item_id>.tmp → media/current/<item_id>.ext
       (атомарная операция в пределах одной ФС)
4. Если SHA256 НЕ совпадает:
   └── rename media/staging/<item_id>.tmp → media/quarantine/<item_id>.bad
   └── логировать ошибку
   └── начать загрузку заново

Agent НЕ пишет напрямую в media/current/ — только через rename из staging.
КСО ПО читает ТОЛЬКО media/current/.
КСО ПО НЕ читает staging и quarantine.
```

### Manifest: обновление

```
1. Agent записывает новый manifest в manifest/current_manifest.json.tmp
2. Agent вычисляет SHA256 → записывает в manifest/current_manifest.sha256.tmp
3. Agent выполняет rename:
   └── manifest/current_manifest.json.tmp → manifest/current_manifest.json
   └── manifest/current_manifest.sha256.tmp → manifest/current_manifest.sha256
   (оба rename атомарны в пределах ФС)
4. КСО ПО может проверить целостность через .sha256
```

### PoP events: запись и чтение

```
1. КСО ПО пишет события в pop/events.log (append-only)
   └── каждая строка — один JSON-объект
   └── дописывать ТОЛЬКО в конец файла
   └── никогда не перезаписывать существующие строки
   └── никогда не удалять строки

2. Agent читает pop/events.log:
   └── запоминает последний прочитанный offset
   └── при следующем чтении — читает только новые строки после offset
   └── НЕ блокирует файл (КСО ПО может писать одновременно)

3. Agent отправляет события:
   └── rename pop/events.log → pop/events.processing (атомарно)
   └── КСО ПО начинает писать в новый pop/events.log (agent не удалял старый, а переименовал)
   └── agent читает events.processing, отправляет batch в backend
   └── при успехе: rename events.processing → pop/sent/events.<дата>.log
   └── при ошибке: rename events.processing → pop/events.log.retry (дописать обратно в начало нового events.log)

4. Ротация:
   └── agent следит за размером pop/events.log
   └── при превышении порога → принудительный flush (даже вне расписания)
```

### Status: запись

```
1. КСО ПО пишет status/kso_status.json:
   └── записать в kso_status.json.tmp
   └── rename → kso_status.json (атомарно)
   └── agent всегда видит консистентный файл

2. Agent пишет status/agent_status.json:
   └── аналогично через .tmp → rename
```

---

## 5. Файлы, которые пишет Agent

### `config/runtime_config.json`

```json
{
  "config_hash": "sha256-hex...",
  "generated_at": "2026-06-18T10:00:00Z",
  "heartbeat_interval_sec": 60,
  "manifest_refresh_interval_sec": 60,
  "media_download_timeout_sec": 30,
  "media_cache_max_mb": 1024,
  "pop_batch_max_events": 500,
  "pop_flush_interval_sec": 300,
  "offline_mode_enabled": true,
  "max_offline_duration_sec": 86400,
  "manifest_ttl_sec": 86400,
  "diagnostics_enabled": false,
  "diagnostics_sample_interval_sec": 300,
  "media_prefetch_enabled": false,
  "media_prefetch_max_items": 10,
  "local_storage_reserved_mb": 512,
  "allowed_mime_types": ["image/jpeg", "image/png", "video/mp4", "video/webm"],
  "max_media_file_mb": 500,
  "log_level": "info",
  "kso_safety": {
    "stop_on_service_mode": true,
    "stop_on_transaction": true,
    "stop_on_payment": true,
    "stop_on_error_screen": true,
    "fail_behavior": "fail_silent",
    "screen_zone": "idle_screen",
    "max_overlay_area_percent": 100,
    "max_cpu_percent": 30,
    "max_memory_mb": 512
  }
}
```

**Назначение для КСО ПО:** read-only. Можно читать для получения актуальных лимитов и настроек безопасности.

### `manifest/current_manifest.json`

```json
{
  "manifest_version_id": "uuid",
  "manifest_hash": "sha256-hex...",
  "generated_at": "2026-06-18T10:00:00Z",
  "valid_until": "2026-06-19T10:00:00Z",
  "campaign_id": "uuid",
  "items": [
    {
      "manifest_item_id": "uuid",
      "filename": "uuid.jpg",
      "content_type": "image/jpeg",
      "sha256": "sha256-hex...",
      "size_bytes": 245760,
      "duration_ms": 10000,
      "order": 1
    }
  ]
}
```

**Назначение для КСО ПО:** read-only. Содержит полный список media для показа. Поле `duration_ms` подсказывает длительность показа. Поле `order` задаёт порядок.

### `status/agent_status.json`

```json
{
  "status": "ok",
  "uptime_seconds": 86400,
  "version": "1.0.0",
  "last_backend_contact_at": "2026-06-18T10:00:00Z",
  "last_manifest_sync_at": "2026-06-18T09:55:00Z",
  "last_cache_report_at": "2026-06-18T09:55:00Z",
  "cached_items": 5,
  "invalid_hash_items": 0,
  "offline_mode": false,
  "offline_duration_sec": 0,
  "errors": []
}
```

**Поля:**
- `status`: `ok` | `warning` | `error` | `stopped`
- `errors`: массив строк с описанием последних ошибок (без секретов и stacktrace)

**Назначение для КСО ПО:** read-only. Можно использовать для мониторинга здоровья agent.

---

## 6. Файлы, которые пишет КСО ПО

### `status/kso_status.json`

```json
{
  "state": "idle",
  "updated_at": "2026-06-18T10:00:00Z",
  "screen": "idle_screen",
  "can_show_ads": true
}
```

**Allowed states:**

| State | Описание | can_show_ads |
|---|---|---|
| `idle` | КСО не используется, idle screen активен | `true` |
| `transaction` | Покупатель сканирует товары | `false` |
| `payment` | Открыт экран оплаты | `false` |
| `error` | Экран ошибки КСО | `false` |
| `service_mode` | Сервисный режим / обслуживание | `false` |
| `unknown` | Не удалось определить состояние | `false` |

**Правила:**
- КСО ПО обновляет этот файл **немедленно** при смене состояния.
- `updated_at` — ISO8601 с точностью до секунды.
- Agent читает этот файл перед каждым обновлением `media/current/`.
- Если файла нет или state `unknown` — agent считает показ запрещённым.

### `pop/events.log`

Формат: **JSONL** (JSON Lines) — один JSON-объект на строку, завершается `\n`.

```jsonl
{"device_event_id":"550e8400-e29b-41d4-a716-446655440001","manifest_item_id":"550e8400-e29b-41d4-a716-446655440002","started_at":"2026-06-18T10:00:00Z","ended_at":"2026-06-18T10:00:10Z","duration_ms":10000,"result":"completed"}
{"device_event_id":"550e8400-e29b-41d4-a716-446655440003","manifest_item_id":"550e8400-e29b-41d4-a716-446655440004","started_at":"2026-06-18T10:00:10Z","ended_at":"2026-06-18T10:00:15Z","duration_ms":5000,"result":"interrupted"}
```

**Поля:**

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `device_event_id` | UUID | ✅ | Уникальный ID события на устройстве (дедупликация) |
| `manifest_item_id` | UUID | ✅ | ID media item из manifest |
| `started_at` | ISO8601 | ✅ | Начало показа |
| `ended_at` | ISO8601 | ✅ | Конец показа |
| `duration_ms` | int | ✅ | Длительность фактического показа в мс |
| `result` | string | ✅ | `completed` / `interrupted` / `skipped` / `failed` |

**Allowed `result` values:**

| Result | Когда использовать | Считается ли PoP? |
|---|---|---|
| `completed` | Показ завершён полностью (дошёл до конца или duration_ms ≥ planned) | ✅ Да |
| `interrupted` | Показ прерван (транзакция, выход из idle, ошибка) | ✅ Да (частичный) — backend посчитает |
| `skipped` | Файл не показан из-за safety check (не idle, ошибка, и т.д.) | ❌ Нет — не считается показом |
| `failed` | Ошибка воспроизведения (файл повреждён, кодек не поддерживается) | ❌ Нет |

---

## 7. Что запрещено писать в PoP и Status

**Категорически запрещено** включать в любые файлы в `pop/` и `status/`:

### Персональные данные

- ❌ ФИО покупателя
- ❌ Телефон
- ❌ Email
- ❌ Номер карты лояльности
- ❌ Дата рождения

### Платёжные данные

- ❌ Номер банковской карты (PAN)
- ❌ CVV / CVC
- ❌ Срок действия карты
- ❌ Сумма транзакции
- ❌ Код авторизации

### Чеховые данные

- ❌ Номер чека
- ❌ Состав чека (SKU, названия товаров, цены, количество)
- ❌ Скидки
- ❌ НДС

### Медиа-данные

- ❌ Фото / видео покупателя
- ❌ Скриншоты экрана КСО
- ❌ Данные с камеры
- ❌ Аудиозаписи с микрофона

### Технические секреты

- ❌ `device_secret`
- ❌ JWT-токены
- ❌ Пароли
- ❌ API-ключи
- ❌ Stacktrace (допустимы только сообщения об ошибках)
- ❌ `local_path` / `file_path` / `filesystem_path`

### Разрешённые данные в PoP

**Только:**
- `device_event_id` (UUID)
- `manifest_item_id` (UUID)
- `started_at`, `ended_at` (ISO8601)
- `duration_ms` (int)
- `result` (enum string)

**Ничего больше.** Никаких дополнительных полей.

---

## 8. KSO Safety Rules (локальные)

### Правило для КСО ПО

**Показывать рекламный контент из `media/current/` можно ТОЛЬКО когда ВСЕ условия выполнены:**

```
ПЕРЕД НАЧАЛОМ ПОКАЗА:
├── kso_status.state == "idle"
├── kso_status.can_show_ads == true
├── runtime config kso_safety.stop_on_transaction → state != "transaction"
├── runtime config kso_safety.stop_on_payment → state != "payment"
├── runtime config kso_safety.stop_on_error_screen → state != "error"
├── runtime config kso_safety.stop_on_service_mode → state != "service_mode"
├── manifest не истёк (current_manifest.json.valid_until > сейчас)
├── media файл существует в media/current/
└── media sha256 проверен (опционально, через manifest)

ЕСЛИ ХОТЬ ОДНО УСЛОВИЕ НЕ ВЫПОЛНЕНО → НЕ ПОКАЗЫВАТЬ
```

### Правило для Agent

```
Agent НЕ обновляет media/current/ если:
├── kso_status.state != "idle"
├── kso_status.can_show_ads == false
└── runtime config kso_safety.fail_behavior == "fail_closed" и есть любая ошибка
```

### Поведение при неизвестном состоянии

Если `kso_status.json` отсутствует или `state == "unknown"`:
- Agent **не обновляет** `media/current/`
- Agent **продолжает** heartbeat, config/manifest sync, PoP flush
- Agent пишет в `agent_status.json`: `status: "warning"`, ошибка: "KSO state unknown"
- КСО ПО **не показывает** рекламу (соблюдает safety rules)

### Fail behavior

- `fail_silent` (рекомендуется): Agent тихо останавливает обновление media/current/, но продолжает sync/heartbeat/PoP. КСО ПО может показывать то, что уже есть в кэше (если не истёк manifest).
- `fail_closed`: Agent полностью останавливается. `agent_status.status = "stopped"`. КСО ПО не показывает рекламу.

---

## 9. PoP Delivery Semantics

### Что считается показом (PoP)

**Показ засчитывается только если media реально начал воспроизводиться на экране КСО.**

Не считается показом:
- Загрузка файла в кэш
- Проверка SHA256
- Pre-buffering видео
- Нахождение файла в `media/current/` (само по себе не показ)

### Семантика result

| Ситуация | result | Считается PoP? |
|---|---|---|
| Показ завершён полностью (дошёл до конца) | `completed` | ✅ Да |
| Показ прерван: началась транзакция | `interrupted` | ✅ Да (частичный) |
| Показ прерван: КСО перешёл в ошибку | `interrupted` | ✅ Да |
| Файл не показан: КСО был не в idle | `skipped` | ❌ Нет |
| Файл не показан: ошибка воспроизведения | `failed` | ❌ Нет |
| Файл не показан: manifest истёк | `skipped` | ❌ Нет |

### Дедупликация

- `device_event_id` генерируется **КСО ПО** (UUID v4) для каждого события
- Agent сохраняет отправленные `device_event_id` в памяти (не на диск)
- При повторной отправке того же ID backend игнорирует дубль
- При перезапуске agent: дубли возможны, backend дедуплицирует по `device_event_id`

### Сохранность очереди между перезапусками

- PoP-события хранятся в `pop/events.log` на диске
- При перезапуске agent читает offset из `state/` и продолжает с того же места
- Если КСО ПО писало события пока agent был остановлен — они не потеряны
- При crash agent: неподтверждённые события в `events.processing` будут обработаны при рестарте

---

## 10. Atomicity Guarantees (гарантии)

| Операция | Гарантия |
|---|---|
| Публикация media в current/ | Атомарный `rename()` в пределах одной ФС |
| Обновление manifest | Атомарный `rename()` |
| Запись PoP КСО ПО | `append()` — атомарно для строк ≤ PIPE_BUF (обычно 4KB) |
| Чтение PoP agent | Без блокировки — читает по offset |
| Flush PoP | `rename events.log → events.processing` — КСО ПО сразу начинает писать в новый файл |
| Запись status | Через `.tmp` → `rename()` |

**Что НЕ гарантируется (пока):**
- Атомарность при разных ФС (staging и current на разных разделах)
- Блокировки между процессами (полагаемся на append-only и rename)

---

## 11. Open Questions for Vendor

| # | Вопрос | Важность |
|---|---|---|
| 1 | Поддерживает ли КСО ПО чтение media-файлов из указанной папки? | Обязательный |
| 2 | Может ли КСО ПО писать PoP-события в JSONL-файл (append-only)? | Обязательный |
| 3 | Может ли КСО ПО писать текущее состояние в `status/kso_status.json`? | Обязательный |
| 4 | Какие форматы media поддерживает idle screen КСО? (JPEG, PNG, MP4, WebM, GIF?) | Обязательный |
| 5 | Есть ли ограничения по размеру media-файлов для idle screen? | Обязательный |
| 6 | Поддерживаются ли атомарные `rename()` операции на ФС КСО? | Важный |
| 7 | Можно ли выделить отдельного сервисного пользователя (`kso-agent`) с ограниченными правами? | Важный |
| 8 | Где физически разместить папку: `/var/lib/kso-adapter/` (Linux) или `C:\ProgramData\KSOAdapter\` (Windows)? Есть ли ограничения? | Важный |
| 9 | Как КСО ПО определяет переход между idle → transaction → payment → error → service_mode? Есть ли API/колбэки/события? | Обязательный |
| 10 | Кто отвечает за очистку старых media-файлов из `media/current/` когда manifest обновляется? | Важный |
| 11 | Допустима ли append-only запись в общий файл из КСО ПО? Или нужен отдельный механизм IPC? | Важный |
| 12 | Как часто КСО ПО обновляет `kso_status.json`? Мгновенно при смене состояния или периодически? | Важный |

---

## 12. Что НЕ в этом документе

- ❌ Код agent / SDK
- ❌ Backend endpoint'ы
- ❌ Установщик / auto-update
- ❌ Remote commands / push
- ❌ Overlay / управление экраном КСО
- ❌ Сбор чековых / платёжных / персональных данных
- ❌ КСО-плеер (это только интерфейсный контракт)

---

## 13. Связанные документы

- `docs/kso_player_architecture.md` — полная архитектура Sidecar Agent
- `docs/kso_player_runtime_contract.md` — backend-контракт (11 endpoint'ов, runtime config)
- `docs/kso_vendor_integration_questions.md` — общие вопросы поставщику КСО
