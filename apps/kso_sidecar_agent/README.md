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
