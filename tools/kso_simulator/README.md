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

## Связанные документы

- `docs/kso_local_interface_contract.md` — контракт локального интерфейса
- `docs/kso_simulator_design.md` — mini-design симулятора
- `docs/kso_player_architecture.md` — архитектура KSO Sidecar Agent
