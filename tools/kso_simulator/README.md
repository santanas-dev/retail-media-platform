# KSO Simulator

KSO Simulator — dev-утилита для локальной разработки и отладки KSO Sidecar Agent.

## Что это

Локальный симулятор поведения КСО ПО, работающий строго по контракту `docs/kso_local_interface_contract.md`. Предназначен для тестирования будущего KSO Sidecar Agent без настоящей КСО.

**Это НЕ КСО-плеер.** Это dev-инструмент, имитирующий файловое взаимодействие КСО ПО с агентом.

## Что делает

- Создаёт структуру папок по контракту
- Переключает состояния КСО (idle/transaction/payment/error/service_mode/unknown)
- Пишет PoP-события в `pop/events.log` (JSONL, append-only)
- Показывает текущий статус папок и файлов

## Что НЕ делает

- НЕ показывает рекламу (нет рендеринга)
- НЕ ходит в backend (нет сети)
- НЕ знает device_secret или JWT
- НЕ собирает персональные/платёжные/чековые данные
- НЕ является КСО-плеером или Android-плеером

## Быстрый старт

```bash
cd tools/kso_simulator

# Создать структуру папок
python -m kso_simulator init --root /tmp/kso-adapter

# Установить состояние idle
python -m kso_simulator set-state idle --root /tmp/kso-adapter

# Посмотреть статус
python -m kso_simulator status --root /tmp/kso-adapter

# Установить состояние payment (блокирует показ)
python -m kso_simulator set-state payment --root /tmp/kso-adapter

# Записать completed PoP (требует state=idle)
python -m kso_simulator write-pop \
  --root /tmp/kso-adapter \
  --manifest-item-id 550e8400-e29b-41d4-a716-446655440000 \
  --result completed \
  --duration-ms 10000

# Записать interrupted PoP (можно в любом state)
python -m kso_simulator write-pop \
  --root /tmp/kso-adapter \
  --manifest-item-id 550e8400-e29b-41d4-a716-446655440001 \
  --result interrupted \
  --duration-ms 3000 \
  --reason "transaction_started"

# Записать failed PoP (например, битый файл)
python -m kso_simulator write-pop \
  --root /tmp/kso-adapter \
  --manifest-item-id 550e8400-e29b-41d4-a716-446655440002 \
  --result failed \
  --duration-ms 0 \
  --reason "sha256_mismatch"

# Посмотреть статус манифеста
python -m kso_simulator manifest-status --root /tmp/kso-adapter

# Вывести список media items
python -m kso_simulator list-items --root /tmp/kso-adapter
```

### Тестовый manifest

Для работы `manifest-status` и `list-items` нужен файл `manifest/current_manifest.json`.
Пример минимального валидного manifest:

```json
{
  "manifest_version_id": "550e8400-e29b-41d4-a716-446655440000",
  "manifest_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "generated_at": "2026-06-18T10:00:00Z",
  "valid_until": "2026-12-31T23:59:59Z",
  "items": [
    {
      "manifest_item_id": "550e8400-e29b-41d4-a716-446655440001",
      "filename": "promo_01.jpg",
      "content_type": "image/jpeg",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "size_bytes": 245760,
      "duration_ms": 10000,
      "order": 1
    }
  ]
}
```

Сохраните этот JSON в `<root>/manifest/current_manifest.json` перед вызовом manifest-команд.

Manifest reader **не скачивает media**, **не ходит в backend**, **не проверяет sha256 файлов**.
Он только читает и валидирует структуру манифеста.

### Проверка media-файлов (verify-media)

Команда `verify-media` проверяет локальные файлы из `media/current/` на соответствие manifest:

```bash
cd tools/kso_simulator

# Создать тестовый media-файл с известным sha256 (пустой файл)
mkdir -p /tmp/kso-adapter/media/current
touch /tmp/kso-adapter/media/current/promo_01.jpg

# Посчитать его sha256 (все нули — e3b0c44298fc...)
sha256sum /tmp/kso-adapter/media/current/promo_01.jpg

# Проверить соответствие
python -m kso_simulator verify-media --root /tmp/kso-adapter
```

**Пример вывода (all ok):**
```
Total items:       1
  present:         1
  missing:         0
  hash_ok:         1
  hash_mismatch:   0
  invalid_items:   0

ID                                       filename                       status               expected_sha   actual_sha
------------------------------------------------------------------------------------------------------------------------
550e8400...                              promo_01.jpg                   ok                   e3b0c44298fc... e3b0c44298fc...
```

**Пример вывода (missing file):**
```
Total items:       2
  present:         1
  missing:         1
  ...

ID                                       filename                       status               expected_sha   actual_sha
------------------------------------------------------------------------------------------------------------------------
550e8400...                              promo_01.jpg                   ok                   e3b0c44298fc... e3b0c44298fc...
550e8400...                              missing_file.jpg               missing              e3b0c44298fc... -
```

**Пример вывода (hash mismatch):**
```
ID                                       filename                       status               expected_sha   actual_sha
------------------------------------------------------------------------------------------------------------------------
550e8400...                              promo_01.jpg                   hash_mismatch        e3b0c44298fc... a1b2c3d4e5f6...
```

**Особенности:**
- Expired manifest не блокирует проверку — выводит WARNING и проверяет файлы
- Symlink файлы — reject (статус `symlink_rejected`)
- Path traversal filenames — reject на этапе чтения manifest
- Не ходит в сеть, не использует device_secret/JWT
- Не выводит полные local_path

### Симуляция показа (show-once)

Команда `show-once` имитирует один безопасный показ media item: проверяет состояние КСО (idle), читает manifest, сверяет sha256 media-файла, и если всё безопасно — пишет PoP `completed`. На реальных КСО эту логику выполняет КСО ПО.

```bash
cd tools/kso_simulator

# Подготовка: init, idle state, manifest + media файл
python3 -m kso_simulator.cli init --root /tmp/kso-adapter
python3 -m kso_simulator.cli set-state idle --root /tmp/kso-adapter
# (создать manifest/current_manifest.json и media/current/promo_01.jpg)

# Успешный показ
python3 -m kso_simulator.cli show-once \
  --root /tmp/kso-adapter \
  --manifest-item-id 66111111-a111-1111-a111-111111111111
# → SHOW_COMPLETED manifest_item_id=... duration_ms=10000

# Переопределить duration
python3 -m kso_simulator.cli show-once \
  --root /tmp/kso-adapter \
  --manifest-item-id 66111111-a111-1111-a111-111111111111 \
  --duration-ms 5000
# → SHOW_COMPLETED ... duration_ms=5000
```

**Safe failure cases (PoP completed НЕ пишется):**

| Ситуация | Вывод | PoP |
|---|---|---|
| KSO не в idle (payment/error/transaction) | `SHOW_BLOCKED reason=kso_not_idle` | ❌ нет |
| can_show_ads=false | `SHOW_BLOCKED reason=kso_not_idle` | ❌ нет |
| Manifest не найден / invalid | `SHOW_FAILED reason=manifest_invalid` | ❌ нет |
| Item не найден в manifest | `SHOW_FAILED reason=item_not_found` | ❌ нет |
| Media файл отсутствует | `SHOW_FAILED reason=media_missing` | ❌ нет |
| SHA256 не совпадает | `SHOW_FAILED reason=hash_mismatch` | ❌ нет |

**Safety rules:**
- `completed` PoP пишется только если: state=idle, can_show_ads=true, manifest валиден, item найден, media sha256 совпал
- Во всех остальных случаях — fail-silent: без PoP, без stacktrace, без сети
- Не меняет состояние КСО

### Idle Loop (run-idle-loop)

Команда `run-idle-loop` идёт по manifest items (сортируя по `order`), вызывая безопасную `show-once` логику для каждого. Имитирует цикличный показ на idle-экране КСО.

```bash
cd tools/kso_simulator

# Одиночный проход по первому item
python3 -m kso_simulator.cli run-idle-loop --root /tmp/kso-adapter

# 3 попытки с интервалом 100ms
python3 -m kso_simulator.cli run-idle-loop \
  --root /tmp/kso-adapter \
  --iterations 3 \
  --interval-ms 100

# Остановка при первом blocked/failed
python3 -m kso_simulator.cli run-idle-loop \
  --root /tmp/kso-adapter \
  --iterations 10 \
  --stop-on-blocked
```

**Пример: idle → completed (2 items, 3 iterations):**
```
ITEM_COMPLETED manifest_item_id=66111111... duration_ms=10000
ITEM_COMPLETED manifest_item_id=66222222... duration_ms=5000
ITEM_COMPLETED manifest_item_id=66111111... duration_ms=10000

LOOP_DONE iterations=3 attempted=3 completed=3 blocked=0 failed=0
```

**Пример: payment → blocked:**
```
ITEM_BLOCKED reason=kso_not_idle

LOOP_DONE iterations=1 attempted=1 completed=0 blocked=1 failed=0
```

**Параметры:**
- `--root` — путь к kso-adapter (обязателен)
- `--iterations` — макс. попыток показа (default: 1)
- `--interval-ms` — пауза между итерациями в мс (default: 1000)
- `--stop-on-blocked` — остановиться при первом non-completed

**Особенности:**
- Читает manifest один раз перед началом цикла
- Идёт по items согласно полю `order`
- Использует ту же safety-логику что и `show-once`
- При blocked/failed — не пишет PoP, переходит к следующему item (если не `--stop-on-blocked`)
- Не бесконечный по умолчанию (`--iterations` обязателен для >1)

## Создаваемые файлы

После `init` создаётся:

```
<root>/
├── config/
├── manifest/
├── media/
│   ├── current/
│   ├── staging/
│   └── quarantine/
├── pop/
├── status/
│   └── kso_status.json    # {state: "unknown", can_show_ads: false}
└── logs/
```

## Безопасность

Simulator **не использует и не хранит:**
- `device_secret`
- JWT-токены
- Пароли
- API-ключи
- Персональные данные
- Платёжные данные
- Чековые данные

Simulator **не делает** сетевых запросов.

## Тесты

```bash
cd tools/kso_simulator

# Запустить все smoke-тесты
python3 -m unittest discover -s tests -v
```

Тесты используют только stdlib (`unittest`, `tempfile`, `subprocess`), без новых зависимостей. Создают временные папки и не пишут в проект.

**Покрытие:**
- init/status (создание папок, kso_status.json)
- set-state (idle, payment, invalid)
- manifest + media (status, list, verify)
- show-once (idle → completed, payment → blocked)
- run-idle-loop (idle → 2 completed, transaction → 2 blocked)
- negative/security (path traversal, forbidden words, no local path)

## Связанные документы

- `docs/kso_local_interface_contract.md` — контракт локального интерфейса
- `docs/kso_simulator_design.md` — mini-design симулятора
- `docs/kso_player_architecture.md` — архитектура KSO Sidecar Agent
