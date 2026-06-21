# KSO UKM 4 State Adapter

**Статус:** 🧭 Core contract. Реальная интеграция с УКМ 4 — будущий шаг.

## Что это

Единственный writer для `{root}/state/kso_state.json`.
Player **только читает** этот файл для решения play/hold.

```
source (УКМ 4 в будущем) → adapter → kso_state.json → player (read-only)
```

## Формат kso_state.json

```json
{
  "state": "idle",
  "updated_at_utc": "2026-01-01T12:00:00Z",
  "source": "ukm4_state_adapter",
  "schema_version": 1
}
```

## Состояния

| Состояние | Player gate | Описание |
|---|---|---|
| `idle` | play | Терминал свободен — реклама разрешена |
| `transaction` | hold | Идёт кассовая операция |
| `payment` | hold | Идёт оплата |
| `receipt` | hold | Идёт печать чека (техническое, не данные чека) |
| `service` | hold | Сервисный режим |
| `error` | hold | Ошибка терминала |
| `maintenance` | hold | Обслуживание |
| `offline` | hold | Офлайн-режим |
| `unknown` | hold | Состояние неизвестно (fail-closed) |

## Fail-closed principle

При любой ошибке источника adapter пишет `error` или `unknown` — **никогда idle**.
Player видит не-idle → hold → реклама не показывается.

## Atomic write

Writer использует atomic replace:
1. tmp-файл в `state/`
2. fsync(tmp)
3. rename(tmp → kso_state.json)
4. fsync(directory)

## CLI

```bash
# One-shot write:
python3 -m kso_state_adapter.cli write-once --root /tmp/root --state idle

# Daemon mode:
python3 -m kso_state_adapter.cli daemon --root /var/lib/verny/kso \
    --source-state unknown --health-file /run/verny/kso/state-adapter-health.json
```

## Что будет позже

- Реальная интеграция с УКМ 4 через API/COM-порт
- Systemd unit template
- Мониторинг source health

## Three-Daemon E2E Smoke

Локальный тест совместной работы трёх daemon core:
`tests/test_kso_three_daemon_e2e_smoke.py` (8 тестов)

Happy path: state adapter (idle) → sidecar (sync) → player (2 цикла) → sidecar (send)
Negative: unknown/error state → hold, state change, sync failure, reject, network error, no resend.
