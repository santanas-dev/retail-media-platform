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
```

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
