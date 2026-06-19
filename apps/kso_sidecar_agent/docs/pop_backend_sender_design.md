# Mini-Design: KSO Sidecar PoP Backend Sender

**Статус:** 📝 Design-only. Код HTTP sender пока не пишем.
**Шаг:** 26.22
**Дата:** 19 июня 2026
**Основание:** `pop_backend_payload_design.md`, `pop_payload.py`, `http_client.py`, `device_auth_client.py`, `retry_backoff.py`, backend `proof_of_play_events` (013), `proof_of_play_batches` (014)

---

## 1. Goal

Спроектировать **безопасную отправку** eligible PoP payload в backend через `POST /device-gateway/pop/events/batch`.

**Это дизайн, не реализация.** Код HTTP sender будет написан отдельным шагом (26.23+). Rotation/move файлов — шаг 26.24+.

---

## 2. Position in Pipeline

```
Player pop-write → pop/pending/player_events.jsonl
       ↓
Sidecar pop_pickup → classify (draft/eligible/diagnostic/quarantine/invalid)
       ↓
Sidecar pop_batch → in-memory eligible batch
       ↓
Sidecar pop_payload → manifest mapping → PopPayloadEnvelope
       ↓
Sidecar pop_backend_sender → HTTP POST /pop/events/batch  ← THIS DESIGN
       ↓ (только после backend подтверждения)
Sidecar pop_rotation → move pending → sent/quarantine/dry_run  ← БУДУЩИЙ ШАГ
```

**Sender работает только после payload builder.** Он отправляет только eligible completed events. Он не отправляет draft/blocked/failed.

---

## 3. Endpoint Policy

### Выбранный endpoint

```
POST /device-gateway/pop/events/batch
Content-Type: application/json
Authorization: Bearer <access_token>
```

**Предпочтительно использовать batch endpoint** (один запрос на группу событий). Это снижает нагрузку на backend и упрощает атомарность.

Одиночный `POST /device-gateway/pop/events` — запасной вариант, не основной.

### Allowlist

Путь `/api/device-gateway/pop/events` и `/api/device-gateway/pop/events/batch` уже покрыт префиксом `_ALLOWED_PREFIXES` в `http_client.py`:
```python
_ALLOWED_PREFIXES = (
    ...
    "/api/device-gateway/pop/",
)
```

**Запрещены произвольные URL.** Sender использует только allowlisted paths.

### Payload (структура)

Payload формируется `build_pop_backend_payload()` — `PopPayloadEnvelope`:

```json
{
  "batch_id": "<UUID>",
  "sent_at": "<ISO8601>",
  "events": [
    {
      "device_event_id": "<UUID>",
      "manifest_item_id": "<UUID>",
      "manifest_version_id": "<UUID>",
      "campaign_id": "<UUID|null>",
      "publication_target_id": "<UUID|null>",
      "schedule_item_id": "<UUID|null>",
      "played_at": "<ISO8601>",
      "duration_ms": 15000,
      "play_status": "completed"
    }
  ]
}
```

**Критически важно:**
- payload body НЕ печатать в safe output, логах, stdout/stderr
- batch_id НЕ печатать в safe output
- device_event_id НЕ печатать в safe output
- manifest_item_id НЕ печатать в safe output
- campaign_id/creative_id/schedule_item_id НЕ печатать в safe output

### Response (backend)

```json
{
  "proof_batch_id": "<UUID>",
  "status": "processed|duplicate_batch|rejected",
  "results": [
    {
      "device_event_id": "<UUID>",
      "status": "accepted|duplicate|rejected",
      "proof_event_id": "<UUID|null>",
      "rejection_reason": "<str|null>"
    }
  ],
  "summary": {
    "accepted": 3,
    "duplicate": 0,
    "rejected": 1
  }
}
```

**Response body НЕ печатать в safe output.** Только агрегаты из `summary`.

---

## 4. Auth / HTTP Model

### Auth цепочка

Sender использует существующую device auth цепочку sidecar:

```
config/agent_config.json → backend_base_url, device_code
config/device_secret.dev → device_secret (dev-only)
        ↓
DeviceAuthClient → POST /auth/token → JWT (memory-only)
        ↓
Authorization: Bearer <jwt> → POST /pop/events/batch
```

### Токен

- Хранится **только in-memory** (в `TokenState`)
- **НЕ пишется на диск**
- **НЕ логируется**
- **НЕ выводится в safe output**
- `Authorization` header НЕ логируется

### Safe HTTP Client

- Используется существующий `SafeHttpClient` (stdlib `urllib.request`)
- `post_json(path, payload, headers)` — уже реализован
- Path validation через allowlist
- Header validation — запрещены forbidden substrings
- TLS verify по умолчанию
- `backend_base_url` НЕ печатается в логах/safe output
- Timeout обязателен (default 10s, 1–120s)

### Retry / Backoff

- Используется существующий `RetryBackoffManager`
- Retry ТОЛЬКО для retryable ошибок:
  - 429 Too Many Requests
  - 5xx Server Error
  - Network error / timeout / connection refused
- **НЕ retry для:**
  - 400 Bad Request — payload/schema issue
  - 401 Unauthorized — token expired/invalid
  - 403 Forbidden — access denied
  - 404 Not Found — endpoint missing
  - 409 Conflict — duplicate batch (обрабатывается отдельно)
  - 422 Unprocessable Entity — validation error
- Exponential backoff + jitter (±25%)
- Max attempts: 3 (default), configurable до 10
- **Бесконечный retry запрещён**

### 401/403 Policy

При 401 или 403:
- НЕ retry бесконечно
- Нужна auth refresh policy:
  - Попытаться обновить токен через `DeviceAuthClient` (один раз)
  - Если refresh успешен → повторить отправку (один раз)
  - Если refresh неуспешен → abort, pending untouched
- Auth refresh policy будет реализована в будущем шаге (или как часть sender)

---

## 5. Success Policy

### Что считается успехом

Backend вернул **2xx** и response schema valid:

1. `status: "processed"` — все события приняты
2. Response `summary.accepted` + `summary.duplicate` + `summary.rejected` обработаны безопасно
3. `accepted_count > 0` или `duplicate_count > 0` при `rejected_count == 0`

### После успеха

- **Pending НЕ трогать в sender.** Rotation/move в `sent/` будет отдельным шагом (26.24+)
- Sender только сообщает результат: `status: ok`, `accepted_events: N`
- Файлы остаются на месте до rotation step

---

## 6. Partial Success Policy

### Часть accepted, часть rejected

Если backend вернул `status: "processed"` но `summary.rejected > 0`:

- **SENDER НЕ удаляет события молча**
- Accepted события → будут перемещены в `sent/` на rotation step
- Rejected события → будут перемещены в `quarantine/` на rotation step
- Sender возвращает `status: warning` с разбивкой по accepted/duplicate/rejected

### Duplicate

- `duplicate` можно считать безопасным результатом ТОЛЬКО если backend явно подтверждает это в response
- Если backend response непонятен или не содержит `summary` → считать `warning`, pending не трогать
- Duplicate события не являются ошибкой показа

### Непонятный response

- Backend response не содержит ожидаемых полей (`status`, `summary`, `results`)
- Response не парсится как JSON
- Любая неоднозначность → `status: error`, pending не удалять

---

## 7. Failure Policy

| Ошибка | Действие sender | Pending |
|---|---|---|
| Network error / timeout | Retry (до 3 попыток). Если исчерпаны → abort | ✅ untouched |
| DNS / connection refused | Retry. Если исчерпаны → abort | ✅ untouched |
| 401 Unauthorized | Auth refresh (1 попытка) → retry (1 попытка). Если неуспешно → abort | ✅ untouched |
| 403 Forbidden | НЕ retry. Abort immediately | ✅ untouched |
| 400 Bad Request | НЕ retry. Payload/schema issue. Quarantine на rotation | ✅ untouched |
| 422 Unprocessable | НЕ retry. Validation error. Quarantine на rotation | ✅ untouched |
| 409 Conflict (duplicate batch) | Отдельная обработка. Проверить response. Если backend accepted duplicate → ok | ✅ untouched |
| 5xx (500/502/503/504) | Retry (до 3 попыток). Если исчерпаны → abort | ✅ untouched |
| 429 Too Many Requests | Retry с увеличенной задержкой. Если исчерпаны → abort | ✅ untouched |
| Unknown response | Abort. Не рисковать | ✅ untouched |

### Главное правило

> **Нет подтверждения backend → pending не удалять и не перемещать.**

Sender работает в режиме fail-safe: при сомнении — не отправлять или не подтверждать отправку.

---

## 8. Idempotency

### batch_id

- Генерируется один раз в `build_pop_backend_payload()` (UUID v4)
- Один и тот же batch_id при повторной отправке → backend должен определить duplicate
- Backend использует `device_batch_id` в `proof_of_play_batches` для dedup

### device_event_id

- Генерируется для каждого события в `build_pop_backend_payload()` (UUID v4)
- Уникальный ID события в рамках устройства
- Backend использует `device_event_id` в `proof_of_play_events` для dedup

### Правила

- Повторная отправка того же payload не должна создавать дубли в backend
- Backend должен уметь duplicate detection по `batch_id` и `device_event_id`
- Если backend вернул `duplicate` — это не ошибка, считать accepted
- **idempotency ids НЕ печатать в safe logs**

---

## 9. Safe Sender Result

### Future `PopSendResult`

```python
@dataclass
class PopSendResult:
    """Safe result of backend send. No payload body, no secrets, no IDs."""

    status: str                     # ok | warning | error
    attempted_events: int = 0
    accepted_events: int = 0
    duplicate_events: int = 0
    rejected_events: int = 0
    retryable: bool = False
    pending_should_remain: bool = True  # всегда True при ошибке
    message: str = ""
    http_status: int = 0
    elapsed_ms: float = 0.0
```

### Safe output

```
send_status:           ok
attempted_events:      3
accepted_events:       2
duplicate_events:      1
rejected_events:       0
http_status:           200
elapsed_ms:            145.3
```

Или при ошибке:

```
send_status:           error
attempted_events:      3
accepted_events:       0
duplicate_events:      0
rejected_events:       0
http_status:           503
elapsed_ms:            12005.0
message:               HTTP 503 (backoff exhausted after 3 attempts)
```

### Запрещено в safe output

- payload body
- raw backend response
- token / jwt
- backend URL
- batch_id
- device_event_id
- manifest_item_id
- campaign_id / creative_id / schedule_item_id
- filename / sha256
- paths

---

## 10. Forbidden

### Запрещено в sender logs/result/safe output/errors

```
token, jwt, password, secret, api_key, private_key
payment_card, receipt_data, card_number, pan
customer_id, phone, email, receipt_number, fiscal_data
local_path, file_path
authorization, bearer
device_secret, access_token
media_path, creatives/
backend_base_url, 127.0.0.1, device_code
filename, manifest_item_id, device_event_id, batch_id
campaign_id, creative_id, schedule_item_id
sha256, full_manifest, media_bytes, stacktrace
```

Слово `receipt` как safety_state допустимо. Данные чека, номера чеков, карта, покупатель, фискальные данные запрещены.

### Запрещено отправлять в backend

- Customer / payment / receipt / card данные
- Secrets / tokens (кроме Authorization header)
- File paths / local paths
- Media bytes

---

## 11. Fail Safe Contract

| Правило | Описание |
|---|---|
| **Не мешать КСО** | Sender не блокирует плеер, не влияет на транзакции |
| **Не ломать player** | Ошибка sender не крашит плеер, не мешает pop-write |
| **Не удалять pending при ошибке** | Backend failure → pending untouched |
| **Не перемещать события** | Sender только отправляет; rotation — отдельный шаг |
| **Сомнение → не отправлять** | Невалидный response, непонятный статус → abort |
| **Unsafe event → не отправлять** | Forbidden fields → quarantine, не backend |
| **Никаких customer/payment/receipt/card details** | Ни при каких условиях |
| **Backend send failure → degraded, но КСО работает** | Offline-ready режим |

---

## 12. What Sender Does NOT Do

Sender НЕ:
- ❌ Читает media bytes
- ❌ Логирует payload body
- ❌ Двигает pending до подтверждения backend
- ❌ Создаёт sent/quarantine/dry_run
- ❌ Удаляет или изменяет pending file
- ❌ Делает произвольные HTTP-запросы (только allowlisted paths)
- ❌ Хранит token на диске
- ❌ Делает бесконечные retry
- ❌ Отправляет draft/blocked/failed события
- ❌ Отправляет customer/payment/receipt/card данные

---

## 13. Integration Points

### С существующими модулями

| Модуль | Использование |
|---|---|
| `http_client.py` | `SafeHttpClient.post_json()` — отправка payload |
| `device_auth_client.py` | `DeviceAuthClient` — получение JWT |
| `retry_backoff.py` | `RetryBackoffManager` — retry/backoff для transient ошибок |
| `pop_payload.py` | `build_pop_backend_payload()` — сборка payload |
| `pop_pickup.py` | `classify_pop_event()` — классификация (уже используется в payload builder) |
| `local_config.py` | Чтение `agent_config.json` — backend_base_url, device_code |
| `run_cycle.py` | Будущая интеграция в run-cycle как шаг `pop_flush` |

### Allowlist path

Путь `/api/device-gateway/pop/events/batch` уже покрыт префиксом в `http_client.py`:
```python
_ALLOWED_PREFIXES = (
    "/api/device-gateway/media/",
    "/api/device-gateway/manifest/",
    "/api/device-gateway/pop/",      # ← покрывает pop/events/batch
)
```

---

## 14. Roadmap

| Шаг | Описание |
|---|---|
| **26.22** | PoP Backend Sender Mini-Design (этот документ) |
| **26.23** | PoP Backend Sender Core — `pop_sender.py`: `send_pop_payload()` |
| **26.24** | PoP Backend Sender CLI — `pop-send` команда |
| **26.25** | PoP Rotation — move pending → sent/quarantine/dry_run |
| **26.26** | PoP Flush Step — интеграция в run-cycle |
| **26.27+** | Auth refresh policy, real playback integration |

---

## 15. Security Summary

- ✅ Sender отправляет только eligible completed events
- ✅ Draft/blocked/failed НЕ отправляются
- ✅ Auth токен только in-memory, не на диске
- ✅ Safe HTTP client с allowlist — запрещены произвольные URL
- ✅ Retry только для transient ошибок, не для auth/validation
- ✅ Payload body не логируется и не выводится
- ✅ manifest_item_id/batch_id/device_event_id не печатаются
- ✅ Pending не удаляется при ошибке backend
- ✅ Rotation/move — отдельный шаг, sender только отправляет
- ✅ Fail safe: ошибка не ломает КСО/плеер
- ✅ Customer/payment/receipt/card details запрещены на всех этапах
- ✅ Idempotency через batch_id + device_event_id
