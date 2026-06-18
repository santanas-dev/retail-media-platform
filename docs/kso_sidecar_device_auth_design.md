# Mini-Design: KSO Sidecar — Device Auth Client

**Статус:** Mini-design. Код не пишем.
**Шаг:** 25.6
**Дата:** 18 июня 2026

---

## 1. Goal

Спроектировать безопасный Device Auth Client для KSO Sidecar Agent. Client должен аутентифицировать устройство на backend, получать JWT access token и хранить его только в памяти.

---

## 2. Входные данные (Inputs)

### 2.1 Из `config/agent_config.json` (non-secret)

| Поле | Источник | Назначение |
|---|---|---|
| `backend_base_url` | `local_config.read_config()` | Базовый URL backend |
| `device_code` | `local_config.read_config()` | Идентификатор устройства |
| `tls_verify` | `local_config.read_config()` | TLS certificate validation |
| `request_timeout_sec` | `local_config.read_config()` | HTTP timeout |

### 2.2 Из Secret Store

| Данные | Источник | Назначение |
|---|---|---|
| `device_secret` | `secret_store.read_secret()` | Секрет для аутентификации |

### 2.3 Что запрещено брать

- ❌ `device_secret` из `agent_config.json`
- ❌ JWT / access token из файлов
- ❌ Token из environment variables
- ❌ `password` / `api_key` / `private_key` из config

---

## 3. Backend Endpoint Contract

**Фактический endpoint (из router.py):**

```
POST /api/device-gateway/auth/token
```

### 3.1 Request Payload

```json
{
  "device_code": "a-05954",
  "device_secret": "<открытый текст>"
}
```

Поля из `schemas.py`:
```python
class DeviceAuthRequest(BaseModel):
    device_code: str
    device_secret: str
```

### 3.2 Response (200 OK)

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 3600,
  "device_id": "550e8400-e29b-41d4-a716-446655440000",
  "device_code": "a-05954",
  "status": "active"
}
```

Поля из `schemas.py`:
```python
class DeviceAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int          # секунды
    device_id: UUID
    device_code: str
    status: str              # active / disabled / retired
```

### 3.3 JWT Claims (из service.py)

```python
claims = {
    "sub": f"device:{device.id}",
    "type": "device",
    "aud": "device-gateway",
    "device_id": str(device.id),
    "device_code": device.device_code,
    "session_id": str(session.id),
    "iat": int(now.timestamp()),
    "exp": int(expires_at.timestamp()),
}
```

- Алгоритм: `HS256` (shared secret)
- `expires_in` = `settings.DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES * 60` секунд
- Backend хранит только `sha256(access_token)` — не сам токен

### 3.4 Error Responses

| Код | Причина | Контекст backend |
|---|---|---|
| **401** | Invalid device credentials | device_code не найден, device disabled/retired, нет active credential, неверный secret |
| **422** | Validation error | Отсутствуют `device_code` или `device_secret` |
| **5xx** | Server error | Ошибка БД, ошибка JWT encode, и т.д. |

**Важно:** Backend всегда возвращает `detail: "Invalid device credentials"` при 401 — не раскрывает причину (утечка информации).

---

## 4. Token Lifecycle

### 4.1 Obtain

```
COLD START:
1. Прочитать config → backend_base_url, device_code, tls_verify, request_timeout_sec
2. Прочитать device_secret из secret store
3. POST /api/device-gateway/auth/token → access_token + expires_in
4. Сохранить access_token + вычисленное expires_at в памяти (объект TokenState)
5. Логировать: "Device authenticated" (без токена!)
```

### 4.2 Reuse

```
ПЕРЕД КАЖДЫМ BACKEND-ЗАПРОСОМ:
1. Если expires_at > now + 30s → использовать текущий токен
2. Иначе → refresh (re-auth)
```

### 4.3 Refresh (Re-auth)

```
REFRESH:
1. Вызвать ту же POST /api/device-gateway/auth/token
2. Если 200 → обновить TokenState в памяти
3. Если 401 → credential expired/revoked → alert, status=error
4. Если 5xx → retry с backoff
```

### 4.4 Expiry Handling

```
ЕСЛИ ТОКЕН ИСТЁК:
1. При запросе к backend → 401
2. Попробовать re-auth ОДИН раз
3. Если re-auth успешен → продолжать с новым токеном
4. Если re-auth 401 → больше не пытаться. Status=error. Alert.
5. Если re-auth 5xx → retry с backoff (до 3 попыток)
```

### 4.5 Хранение

| Где | Token? | Secret? |
|---|---|---|
| Память процесса (`TokenState` dataclass) | ✅ Только здесь | ❌ |
| `config/agent_config.json` | ❌ | ❌ |
| `status/agent_status.json` | ❌ | ❌ |
| `logs/agent.log` | ❌ (safe_logger → [REDACTED]) | ❌ |
| Диск (любой файл) | ❌ | ❌ (кроме dev secret store) |
| Environment variables | ❌ | ❌ |
| Doctor output | ❌ | ❌ |
| Crash/error messages | ❌ | ❌ |

---

## 5. Error Handling Matrix

| Код | Ситуация | Действие | Повтор? |
|---|---|---|---|
| **200** | OK | Сохранить токен, продолжить | — |
| **400** | Bad request | Логировать ошибку, НЕ retry | ❌ |
| **401** | Bad credentials | 1-й раз: re-check secret store, retry ONCE. 2-й раз: STOP. Status=error. Alert. | ⚠️ 1 раз |
| **403** | Forbidden (revoked) | Немедленный STOP. Status=error. Alert. | ❌ |
| **404** | Not found (bad URL) | Логировать, НЕ retry без исправления config | ❌ |
| **422** | Validation error | Логировать ошибку валидации, НЕ retry | ❌ |
| **429** | Rate limited | Retry с backoff (соблюдать Retry-After если есть) | ✅ |
| **5xx** | Server error | Exponential backoff + jitter, max 5 попыток | ✅ |
| **Timeout** | Сеть недоступна | Backoff + retry, после N попыток: status=offline | ✅ |
| **TLS error** | Сертификат не валиден | fail-closed. НЕ переходить на tls_verify=false автоматически. Status=error. | ❌ |

### При постоянном 401 / 403

```
1. 401 на auth → возможно device_secret неверен или credential revoked
2. Повторить ОДИН раз с перечитыванием secret из store
3. Если снова 401 → STOP. Обновить agent_status → "error"
4. Логировать: "Device authentication failed after retry"
5. Остальные loops (heartbeat, PoP, etc.) не работают без валидного токена
6. Администратор должен вручную проверить/обновить credential
```

---

## 6. Retry / Backoff Strategy

### 6.1 Для auth (startup)

```
- max_attempts: 3
- base_delay: 2s
- max_delay: 60s
- multiplier: 2x
- jitter: ±25%
- После исчерпания: status=error, STOP
```

### 6.2 Для auth (background refresh)

```
- max_attempts: 3
- base_delay: 5s
- max_delay: 120s
- multiplier: 2x
- jitter: ±25%
- После исчерпания: status=warning, попробовать снова через 5 минут
```

### 6.3 Общие правила

- НЕ спамить backend (rate limiting на стороне клиента)
- НЕ логировать `device_secret` или `access_token` в retry messages
- Логировать: "Auth attempt N failed (HTTP {code}), retrying in {delay}s"
- Соблюдать `Retry-After` header если backend возвращает 429

---

## 7. Security Rules

### 7.1 Network

| Правило | Реализация |
|---|---|
| Outbound-only | Agent только инициирует соединения к backend |
| TLS 1.2+ | Минимальная версия TLS |
| Certificate validation | `tls_verify=true` по умолчанию |
| `tls_verify=false` | Только dev/test, с warning в лог |
| Certificate pinning | Не в v1 (опционально в production) |

### 7.2 Token & Secret

| Правило | Реализация |
|---|---|
| Token только в памяти | `TokenState` dataclass, не на диске |
| Secret только из secret store | `secret_store.read_secret()` |
| Не логировать token | safe_logger → [REDACTED] |
| Не логировать secret | safe_logger → [REDACTED] |
| Не писать token в status | Валидация agent_status reject forbidden |
| Не писать token в doctor output | Doctor не читает token |
| Не включать token в exceptions | Безопасные error messages |
| Не делать full request/response dump | Логировать только status code и длительность |

### 7.3 Safe Logging

Уже реализовано в `safe_logger.py`:
- token → [REDACTED]
- jwt → [REDACTED]
- password → [REDACTED]
- secret → [REDACTED]
- api_key → [REDACTED]

Дополнительно для auth client:
- Не логировать URL с query параметрами (могут содержать токены в будущем)
- Не логировать response body
- Логировать: `"POST /auth/token → 200 (234ms)"`

---

## 8. Будущая реализация — предлагаемые файлы

```
apps/kso_sidecar_agent/kso_sidecar_agent/
├── http_client.py          # Base HTTP client (TLS, timeout, retry)
├── token_state.py          # TokenState dataclass + memory management
├── device_auth_client.py   # DeviceAuthClient (orchestrate auth flow)
```

### `http_client.py`

Base HTTP client:
- `HttpClient` класс с TLS, timeout, retry
- Метод `post(url, json_data, headers)` → response
- Метод `get(url, headers)` → response
- Соблюдать `tls_verify`
- Обрабатывать timeout

### `token_state.py`

```python
@dataclass
class TokenState:
    access_token: str = ""
    token_type: str = "bearer"
    expires_at: float = 0.0   # unix timestamp
    device_id: str = ""
    device_code: str = ""

    def is_valid(self) -> bool: ...
    def is_expiring_soon(self, margin_sec: int = 30) -> bool: ...
    def clear(self) -> None: ...
```

### `device_auth_client.py`

- `DeviceAuthClient` оркестрирует auth flow:
  - `async authenticate() -> TokenState`
  - `async ensure_token() -> str`
  - `async refresh() -> TokenState`
  - `invalidate()` — сбросить токен при 401

---

## 9. Будущие CLI-команды (НЕ реализовывать сейчас)

```bash
# Проверить статус auth (без вывода токена)
python3 -m kso_sidecar_agent.cli auth-check \
  --root /tmp/kso-agent-root --dev-secret-store

# Вывод:
#   authenticated: true/false
#   device_code: a-05954
#   expires_at: 2026-06-18T11:00:00Z
#   status: active

# Протестировать auth (dev only, с fake backend или --dry-run)
python3 -m kso_sidecar_agent.cli auth-test \
  --root /tmp/kso-agent-root --dev-secret-store
```

**Правила CLI:**
- Команды НЕ печатают `access_token`
- `auth-check` показывает только: `authenticated`, `device_code`, `expires_at`, `status`
- `auth-test` делает реальный запрос и показывает success/failure

---

## 10. Будущие тесты (НЕ реализовывать сейчас)

| # | Тест | Проверка |
|---|---|---|
| 1 | Config missing → safe error | `auth-check` без config → понятная ошибка |
| 2 | Secret missing → safe error | `auth-check` без secret → понятная ошибка |
| 3 | Successful auth (fake backend) | Mock HTTP → token получен, TokenState заполнен |
| 4 | Token kept in memory only | После auth → grep runtime root → нет токена |
| 5 | Token not in agent_status.json | После auth → статус чист |
| 6 | Token not in logs | После auth → логи clean |
| 7 | 401: limited retry | Fake 401 × 3 → client останавливается |
| 8 | 403: fatal | Fake 403 → немедленный stop |
| 9 | 422: no infinite retry | Fake 422 → один вызов, ошибка |
| 10 | 5xx: retry with backoff | Fake 500 → retry × 3 |
| 11 | TLS verify false warning | auth-test с tls_verify=false → warning |
| 12 | Timeout safe error | Fake timeout → retry → error |
| 13 | No full response dump | Логи содержат только status + duration |
| 14 | Grep runtime root clean | `grep -r <token_pattern> <root>/` → empty |
| 15 | Token refresh works | Token истёк → auto re-auth |

---

## 11. Risks

| # | Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|---|
| 1 | Неправильный `backend_base_url` | Средняя | Высокое | Doctor проверяет URL формат. Config-status валидация. |
| 2 | Неверный `device_secret` | Средняя | Высокое | 401 → retry once → stop. Alert. |
| 3 | Credential revoked на backend | Средняя | Среднее | 401/403 → stop. Администратор обновляет. |
| 4 | Часы КСО сильно отстают/спешат | Средняя | Среднее | JWT `exp` проверяется локально (до отправки). NTP sync. |
| 5 | TLS MITM | Низкая | Критическое | TLS verify=true. Certificate pinning в v2. |
| 6 | Backend недоступен (сеть) | Средняя | Среднее | Retry с backoff. Offline mode. |
| 7 | Случайное логирование токена | Низкая | Высокое | safe_logger → [REDACTED]. Code review. |
| 8 | Случайная запись token на диск | Низкая | Высокое | TokenState в памяти. Тесты на отсутствие в файлах. |
| 9 | Бесконечный retry loop | Низкая | Среднее | Max 3-5 попыток. Rate limiting. |
| 10 | Слишком частые auth-запросы | Низкая | Низкое | Только при старте + refresh перед expiry + после 401. |

---

## 12. Что НЕ реализуем на этом шаге

- ❌ Код `http_client.py`, `token_state.py`, `device_auth_client.py`
- ❌ HTTP-запросы к backend
- ❌ Auth flow
- ❌ Token storage / refresh
- ❌ Изменения backend
- ❌ Миграции
- ❌ Новые endpoint'ы
- ❌ Installer / service
- ❌ Production secret storage

---

## 13. Связанные документы

- `docs/kso_sidecar_agent_design.md` — общий design agent, §7 Backend Matrix, §9 Secrets
- `docs/kso_sidecar_secret_storage_design.md` — дизайн secret storage
- `apps/kso_sidecar_agent/kso_sidecar_agent/local_config.py` — реализованный config
- `apps/kso_sidecar_agent/kso_sidecar_agent/secret_store.py` — реализованный dev secret store
- `apps/kso_sidecar_agent/kso_sidecar_agent/safe_logger.py` — реализованный safe logger
- Backend: `app/domains/device_gateway/router.py` (line 70), `schemas.py` (lines 126-138), `service.py` (lines 354-463)

---

*Документ создан: 18 июня 2026. Следующий шаг: утверждение → реализация `http_client.py` → `token_state.py` → `device_auth_client.py`.*
