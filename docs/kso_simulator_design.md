# Mini-Design: KSO Local Simulator

**Статус:** ⏳ На утверждении. Код не пишем.
**Шаг:** 24.3
**Дата:** 18 июня 2026

---

## 1. Goal

Спроектировать локальный симулятор КСО ПО (`kso-simulator`) для тестирования будущего KSO Sidecar Agent **без настоящей КСО**. Симулятор работает строго по контракту `docs/kso_local_interface_contract.md`.

**Зачем:**
- У нас нет ответов поставщика КСО — нельзя писать реальный плеер
- Но можно протестировать agent локально: все файловые интерфейсы, PoP-цикл, safety rules
- Симулятор + agent = полный локальный integration test без КСО-железа

---

## 2. Scope (Что делает simulator)

| # | Функция | Описание |
|---|---|---|
| 1 | Читает `media/current/` | Берёт список файлов из папки |
| 2 | Читает `manifest/current_manifest.json` | Получает `items[]`, `valid_until`, `sha256` |
| 3 | Пишет `status/kso_status.json` | Обновляет состояние КСО (idle/transaction/payment/...) |
| 4 | Пишет `pop/events.log` (JSONL) | Добавляет события показов (append-only) |
| 5 | Переключает состояния | CLI: `set-state idle|transaction|payment|error|service_mode|unknown` |
| 6 | Имитирует показ | «Показывает» media item → пишет PoP-событие |
| 7 | Имитирует прерывание | При смене state → текущий показ `interrupted` |
| 8 | Валидирует safety rules | Не пишет PoP если state != idle, не показывает при ошибках |

---

## 3. Out of Scope (Что НЕ делает)

- ❌ Настоящий UI / рендеринг / overlay
- ❌ Кассовая логика / оплата / сканирование
- ❌ Чтение чеков / персональных данных
- ❌ Камера / микрофон / банковский терминал
- ❌ Remote commands / auto-update
- ❌ Сетевые запросы к backend
- ❌ Знание `device_secret` / JWT
- ❌ КСО-плеер / Android player

---

## 4. Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    LOCAL HOST                              │
│                                                            │
│  ┌─────────────────────┐    ┌──────────────────────────┐  │
│  │   kso-simulator     │    │   sidecar-agent           │  │
│  │   (CLI process)     │    │   (future, тестируем)     │  │
│  │                     │    │                          │  │
│  │  cli.py             │    │  HTTPS → backend          │  │
│  │  ├─ set-state       │    │                          │  │
│  │  ├─ show-once       │    │  reads pop/events.log    │  │
│  │  ├─ run-idle-loop   │    │  reads kso_status.json   │  │
│  │  └─ write-pop       │    │  writes media/current/   │  │
│  │                     │    │  writes manifest/        │  │
│  │  ┌────────────────┐ │    │  writes agent_status.json│  │
│  │  │ local_fs.py    │ │    └────────────┬─────────────┘  │
│  │  │ state_writer   │ │                 │                │
│  │  │ pop_writer     │ │                 │                │
│  │  │ manifest_reader│ │                 │                │
│  │  └───────┬────────┘ │                 │                │
│  └──────────┼──────────┘                 │                │
│             │                            │                │
│             │    ОБЩАЯ ПАПКА             │                │
│             └────────┬───────────────────┘                │
│                      │                                     │
│           ┌──────────▼──────────┐                          │
│           │  /tmp/kso-adapter/  │  (или другой root)      │
│           │  ├── media/current/ │                          │
│           │  ├── manifest/      │                          │
│           │  ├── pop/events.log │                          │
│           │  ├── status/        │                          │
│           │  └── config/        │                          │
│           └─────────────────────┘                          │
└───────────────────────────────────────────────────────────┘
```

**Принцип:** simulator и agent — два независимых процесса, общаются только через общую папку. Симулятор имитирует КСО ПО, agent — настоящий.

---

## 5. Placement

**Предлагаемый путь:** `tools/kso_simulator/`

**Обоснование:**
- `tools/` — устоявшаяся конвенция для dev-утилит, не входящих в production-код
- Не `apps/` (подразумевает production-компонент)
- Не `players/` (это не плеер)
- Не `backend/` (это не backend)
- Легко найти: `tools/` — первое место, куда смотрят разработчики

**Структура (будет создана при реализации):**

```
tools/kso_simulator/
├── README.md                     # Как запустить, примеры команд
├── pyproject.toml                # Python-зависимости (click, uuid)
├── kso_simulator/
│   ├── __init__.py
│   ├── cli.py                    # CLI: click commands
│   ├── local_fs.py               # Операции с папками: read manifest, list media
│   ├── state_writer.py           # Запись status/kso_status.json
│   ├── pop_writer.py             # Запись pop/events.log (JSONL append)
│   ├── manifest_reader.py        # Чтение manifest + валидация
│   ├── playback_simulator.py     # Логика «показа»: duration, interruption, safety
│   └── safety.py                 # Safety rules: проверка состояний
└── tests/
    ├── test_state_writer.py
    ├── test_pop_writer.py
    ├── test_manifest_reader.py
    └── test_safety.py
```

---

## 6. CLI Commands

### `kso-sim init`

```
kso-sim init --root ./runtime/kso-adapter
```

Создаёт структуру папок по контракту (`media/current/`, `manifest/`, `pop/`, `status/`, `config/`). Пишет начальный `status/kso_status.json` со `state: "unknown"`.

### `kso-sim set-state`

```
kso-sim set-state idle       --root ./runtime/kso-adapter
kso-sim set-state transaction
kso-sim set-state payment
kso-sim set-state error
kso-sim set-state service_mode
kso-sim set-state unknown
```

Пишет `status/kso_status.json` с новым состоянием. Если предыдущее состояние допускало показ (idle), а новое — нет, simulator проверяет: был ли активный показ? Если да — дописывает `interrupted` в `pop/events.log`.

### `kso-sim show-once`

```
kso-sim show-once --manifest-item-id <uuid> --duration-ms 10000
```

Имитирует однократный показ media item:
1. Проверяет safety (state == idle? can_show_ads == true?)
2. Если нет — выводит причину отказа, НЕ пишет PoP
3. Если да — ждёт указанную длительность (реальную или ускоренную)
4. Пишет `completed` в `pop/events.log`

**Опции:**
- `--time-scale 10` — ускорить время в 10× (10 сек → 1 сек реального времени)
- `--result interrupted` — форсировать результат (для тестов)
- `--result skipped` — форсировать skipped
- `--result failed` — форсировать failed

### `kso-sim run-idle-loop`

```
kso-sim run-idle-loop --interval 15
```

Бесконечный цикл (пока не прерван Ctrl+C):
1. Устанавливает state = idle
2. Читает `manifest/current_manifest.json`
3. Для каждого item по порядку:
   - Имитирует показ (show-once)
   - Пишет `completed` PoP
   - Ждёт интервал между показами
4. Если manifest зациклен — повторяет с первого item
5. Слушает сигнал (файловый или сигнал ОС) для смены состояния

**Опции:**
- `--time-scale 60` — ускорение для быстрых тестов
- `--max-iterations 10` — ограничить количество циклов

### `kso-sim write-pop`

```
kso-sim write-pop --manifest-item-id <uuid> --result completed --duration-ms 5000
```

Прямая запись PoP-события в `pop/events.log` (без проверки состояний). Для отладки.

### `kso-sim interrupt-current`

```
kso-sim interrupt-current --reason transaction_started
```

Если активен `run-idle-loop` — посылает сигнал прерывания. Текущий показ завершается с `result: "interrupted"`, state меняется на `transaction`.

### `kso-sim status`

```
kso-sim status --root ./runtime/kso-adapter
```

Выводит текущее состояние:
- `kso_status.json` → state, can_show_ads
- Количество media в `current/`
- Количество строк в `pop/events.log`
- `agent_status.json` (если есть)

---

## 7. Local File Contract (строго по `kso_local_interface_contract.md`)

### Читаемые файлы

| Файл | Читает | Формат | Использование |
|---|---|---|---|
| `manifest/current_manifest.json` | simulator | JSON | Список items для показа, `valid_until`, `sha256` |
| `manifest/current_manifest.sha256` | simulator | hex | Проверка целостности манифеста |
| `media/current/*` | simulator | binary | Проверка наличия файла + размера |
| `status/agent_status.json` | simulator | JSON | Мониторинг agent (read-only) |

### Записываемые файлы

| Файл | Пишет | Формат | Atomicity |
|---|---|---|---|
| `status/kso_status.json` | simulator | JSON (`.tmp` → `rename`) | Атомарно |
| `pop/events.log` | simulator | JSONL (append-only) | Атомарно для строк ≤ 4KB |

### KSO state values (строго из контракта)

```json
{"state": "idle", "updated_at": "ISO8601", "screen": "idle_screen", "can_show_ads": true}
```

| State | can_show_ads | screen |
|---|---|---|
| `idle` | `true` | `idle_screen` |
| `transaction` | `false` | `scanning_screen` |
| `payment` | `false` | `payment_screen` |
| `error` | `false` | `error_screen` |
| `service_mode` | `false` | `service_screen` |
| `unknown` | `false` | `unknown` |

### PoP event values (строго из контракта)

```jsonl
{"device_event_id":"uuid","manifest_item_id":"uuid","started_at":"ISO8601","ended_at":"ISO8601","duration_ms":5000,"result":"completed"}
```

**Allowed `result` values:**
- `completed` — показ завершён полностью
- `interrupted` — показ прерван (транзакция, ошибка)
- `skipped` — файл не показан (safety block)
- `failed` — ошибка воспроизведения

**`device_event_id`:** simulator генерирует UUID v4 для каждого события.

---

## 8. Safety Behavior

### Правила показа (симулятор их соблюдает)

```
ПЕРЕД КАЖДЫМ show-once / run-idle-loop:
├── state == "idle"?              → если нет → отказ, PoP НЕ пишем
├── can_show_ads == true?         → если нет → отказ, PoP НЕ пишем
├── manifest существует?          → если нет → отказ, PoP НЕ пишем
├── manifest.valid_until > now?   → если нет (истёк) → отказ, PoP НЕ пишем
├── media файл существует?        → если нет → отказ + PoP result="failed"
├── sha256 media совпадает?       → если нет → отказ + PoP result="failed"
└── ВСЁ OK → начать показ
```

### Прерывание показа

```
ВО ВРЕМЯ ПОКАЗА (run-idle-loop):
├── Если state меняется на transaction → текущий показ прерывается
│   └── PoP: result="interrupted", ended_at=now
├── Если state меняется на payment → аналогично
├── Если state меняется на error → аналогично
├── Если state меняется на service_mode → аналогично
└── Если state меняется на unknown → аналогично

ВАЖНО: interrupted пишется ТОЛЬКО если показ реально начался (был в idle + can_show_ads).
Если показ ещё не начался (safety check failed до старта) — interrupted НЕ пишем.
```

### Особые случаи

| Ситуация | Действие |
|---|---|
| `manifest/current_manifest.json` отсутствует | Нет показа. PoP НЕ пишем. |
| `manifest.valid_until < now` | Manifest истёк. Нет показа. PoP НЕ пишем. |
| `media/current/` пуст | Нет показа. PoP НЕ пишем. |
| Media файл отсутствует, но есть в manifest | `result: "failed"`, пишем PoP |
| SHA256 media ≠ manifest.sha256 | `result: "failed"`, пишем PoP |
| `kso_status.json` отсутствует | Считаем state = `unknown` → нет показа |
| `can_show_ads = false` даже при state = `idle` | Нет показа (явный запрет от КСО ПО) |

---

## 9. Test Scenarios (будущая реализация)

### Базовые

| # | Сценарий | Ожидаемый результат |
|---|---|---|
| 1 | `set-state idle` → `show-once` | PoP `completed`, duration = заданной |
| 2 | `set-state payment` → `show-once` | Отказ, PoP НЕ пишем, сообщение в stdout |
| 3 | `set-state error` → `show-once` | Отказ, PoP НЕ пишем |
| 4 | `set-state service_mode` → `show-once` | Отказ, PoP НЕ пишем |
| 5 | `set-state unknown` → `show-once` | Отказ, PoP НЕ пишем |

### Прерывания

| # | Сценарий | Ожидаемый результат |
|---|---|---|
| 6 | `run-idle-loop` → через 3 сек `interrupt-current` | Текущий показ → `interrupted`, duration < planned |
| 7 | `run-idle-loop` → `set-state transaction` | Текущий показ → `interrupted`, state = transaction |
| 8 | `run-idle-loop` → `set-state payment` | Текущий показ → `interrupted` |

### Edge cases

| # | Сценарий | Ожидаемый результат |
|---|---|---|
| 9 | Manifest отсутствует → `show-once` | Отказ, "no manifest" |
| 10 | `valid_until` в прошлом → `show-once` | Отказ, "manifest expired" |
| 11 | Media файл отсутствует → `show-once` | `result: "failed"`, PoP записан |
| 12 | SHA256 не совпадает → `show-once` | `result: "failed"`, PoP записан |
| 13 | `write-pop` с result=`skipped` | PoP записан (ручной режим) |
| 14 | 100 `show-once` подряд | Все `completed`, `device_event_id` уникальны |

### JSONL format

| # | Сценарий | Ожидаемый результат |
|---|---|---|
| 15 | 3 `show-once` → проверить `pop/events.log` | 3 строки, каждая — валидный JSON |
| 16 | `pop/events.log` уже существует → `show-once` | Новая строка в конец, старые не тронуты |
| 17 | Пустой `pop/events.log` → agent читает | 0 событий для отправки |

### Безопасность

| # | Сценарий | Ожидаемый результат |
|---|---|---|
| 18 | Проверить все файлы в `pop/` и `status/` | Нет `device_secret`, JWT, token, customer data |
| 19 | `pop/events.log` — только разрешённые поля | Нет `local_path`, `file_path`, PII |

---

## 10. Risks

| Риск | Mitigation |
|---|---|
| Симулятор не полностью повторяет поведение КСО ПО | Документируем расхождения. При появлении реальной КСО — дорабатываем. |
| Форматы JSON могут разойтись с реальным КСО | Строго привязаны к `kso_local_interface_contract.md`. При изменении контракта — обновляем симулятор. |
| Append-only JSONL может дать сбой при concurrent write | Simulator пишет только из одного процесса. Agent читает по offset без блокировки — OK. |
| `time-scale` может скрыть timing-баги | Всегда есть возможность запустить с `--time-scale 1` (реальное время). |

---

## 11. Security

Simulator **не должен:**

- ❌ Хранить `device_secret`, JWT, токены, пароли
- ❌ Писать `local_path` / `file_path` в PoP
- ❌ Писать customer/payment/receipt данные
- ❌ Делать сетевые запросы (localhost или внешние)
- ❌ Читать файлы за пределами `--root`

Simulator **должен:**

- ✅ Писать только в `--root` (изолированная папка)
- ✅ Использовать строго форматы из контракта
- ✅ Валидировать `result` перед записью (только allowed значения)
- ✅ Генерировать UUID v4 для `device_event_id`

---

## 12. Next Implementation Step (после утверждения)

**Шаг 24.4 — KSO Simulator: Implementation**
- Создать `tools/kso_simulator/`
- `pyproject.toml` + `click` CLI
- `local_fs.py` — структура папок
- `state_writer.py` — `kso_status.json`
- `pop_writer.py` — JSONL append
- `manifest_reader.py` — парсинг манифеста
- `safety.py` — проверки состояний
- `playback_simulator.py` — логика показа
- Тесты для всех сценариев (раздел 9)

---

## 13. Commit

Не делаем — только mini-design на утверждение.
