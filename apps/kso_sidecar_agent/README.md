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
| `doctor` | Проверить здоровье папок и `agent_status.json` |

## Что НЕ работает (будет отдельными шагами)

- ❌ Device auth (`/auth/token`)
- ❌ Runtime config sync (`/config/current`)
- ❌ Manifest sync (`/manifest/current`)
- ❌ Media download (`/media/{id}`)
- ❌ PoP flush (`/pop/events/batch`)
- ❌ Heartbeat (`/heartbeat`)
- ❌ Offline mode
- ❌ KSO status reading

## Быстрый старт

```bash
cd apps/kso_sidecar_agent

# Версия
python3 -m kso_sidecar_agent.cli version

# Создать структуру папок
python3 -m kso_sidecar_agent.cli init-local-root --root /tmp/kso-agent-root

# Проверить здоровье
python3 -m kso_sidecar_agent.cli doctor --root /tmp/kso-agent-root
```

## Что создаёт init-local-root

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
│   └── agent_status.json    # {status: "stopped", ...}
└── logs/
```

**НЕ создаёт:** `device.json`, `device_secret`, JWT, media-файлы.

## Безопасность

- ❌ Не хранит `device_secret`
- ❌ Не хранит JWT
- ❌ Не ходит в backend
- ❌ Не собирает персональные/платёжные/чековые данные
- ✅ Безопасный logger редактирует forbidden substrings → `[REDACTED]`

## Тесты

```bash
cd apps/kso_sidecar_agent
python3 -m unittest discover -s tests -v
```

## Связанные документы

- `docs/kso_sidecar_agent_design.md` — mini-design агента
- `docs/kso_player_architecture.md` — архитектура (Вариант D)
- `docs/kso_local_interface_contract.md` — контракт локального интерфейса
