# Mini-Design: KSO Sidecar PoP Local Rotation

**Статус:** 📝 Design-only. Код rotation пока не пишем.
**Шаг:** 26.27
**Дата:** 19 июня 2026
**Основание:** `pop_pickup_design.md`, `pop_backend_sender_design.md`, `pop_sender_runner.py`, `pop_writer.py`, `pop_payload.py`, `pop_pickup.py`

---

## 1. Goal

Спроектировать **безопасную локальную rotation/move политику** для PoP events после подтверждённой отправки в backend.

Rotation выполняется **только после backend confirmation** (successful send + processed/accepted). До этого pending остаётся нетронутым.

**Это дизайн, не реализация.** Код rotation будет написан отдельным шагом (26.28+).

---

## 2. Core Principle

> **Если `pending_should_remain=true` — pending file нельзя удалять, перезаписывать, обрезать или перемещать.**
>
> **Если backend confirmation не уверенный — pending остаётся нетронутым.**

Этот принцип вытекает из всей текущей архитектуры:
- `PopSendResult.pending_should_remain` — флаг, управляющий правом на rotation
- `PopSendRunResult` — агрегирует финальное состояние после retry runner
- `409 duplicate_batch` → `pending_should_remain=true` (hardened в 26.24.1)
- `partial_success` → `pending_should_remain=true`
- Любая ошибка/неясность → `pending_should_remain=true`

---

## 3. Directory Layout (Planned)

```
{root}/
  pop/
    pending/
      player_events.jsonl       # player writes here (append-only)
      player_events.lock         # future lock file (TBD)
    sent/                        # ✅ backend-confirmed events
    quarantine/                  # ⚠ unsafe/schema/manifest mismatch
    dry_run/                     # 📝 draft/diagnostic (NOT PoP)
    failed/                      # ❌ exhausted retry, could not send
```

### Назначение папок

| Папка | Назначение | Когда попадает |
|---|---|---|
| `pending/` | Исходные события от player | Player `pop-write` (append-only) |
| `sent/` | Только безопасно подтверждённые backend события | После `run_status=ok` + `pending_should_remain=false` |
| `quarantine/` | Unsafe/schema/manifest mismatch | Invalid JSON, forbidden fields, manifest mapping missing, media cache incomplete, non-idle safety_state |
| `dry_run/` | Draft/diagnostic события (не PoP) | `event_status=draft`, `blocked`, `failed` |
| `failed/` | События, которые нельзя отправить после retry exhaustion | `retry_exhausted=true`, но события не должны теряться |

---

## 4. Lock Contract (Future)

### Файл блокировки

`pop/pending/player_events.lock` — файловая блокировка.

### Правила

- Player `pop-write` и sidecar rotation **должны использовать один lock**
- Если lock получить нельзя — rotation **пропускается** (не блокирует)
- Пока lock не реализован с двух сторон, **destructive rotation запрещена**
- Append (player write) и rotation (sidecar move) **не должны выполняться одновременно**
- Ошибка lock → pending untouched

### Модель

```
SIDECAR ROTATION:
  1. Попытаться взять lock (неблокирующий try-lock)
  2. Если lock недоступен → skip rotation, вернуть rotation_status=skipped
  3. Выполнить атомарную rotation
  4. Снять lock

PLAYER POP-WRITE:
  1. Попытаться взять lock
  2. Если lock недоступен → ждать (или fail silent)
  3. Append строку
  4. flush + fsync
  5. Снять lock
```

---

## 5. Atomic Rotation Model

### Принцип

**НЕ редактировать JSONL in-place.** Вместо этого:

1. **Взять lock**
2. **Прочитать `pending/player_events.jsonl` построчно**
3. **Классифицировать каждую строку** (через pop_pickup)
4. **Сформировать выходные наборы:**
   - `retained_pending` — строки, остающиеся в pending
   - `sent_lines` — подтверждённые completed события
   - `quarantine_lines` — unsafe/schema/mismatch
   - `dry_run_lines` — draft/diagnostic
   - `failed_lines` — retry-exhausted (опционально)
5. **Записать новые файлы через `.tmp`:**
   - `sent/events_<timestamp>.jsonl.tmp` → atomic rename
   - `quarantine/events_<timestamp>.jsonl.tmp` → atomic rename
   - `dry_run/events_<timestamp>.jsonl.tmp` → atomic rename
   - `pending/player_events.jsonl.tmp` → atomic rename
6. **flush + fsync** для каждого файла
7. **Atomic rename** → заменить `.tmp` на целевое имя
8. **Только после успешной записи всех целевых файлов** заменить pending
9. **При любой ошибке на шагах 1-8** → pending untouched, частичные `.tmp` удалить
10. **Снять lock**

### Почему так

- Если краш на шаге 5-7 → `.tmp` файлы останутся, pending нетронут
- Если краш на шаге 8 → `.tmp` уже переименованы, pending ещё старый
- Никаких частичных удалений без полного подтверждения всех записей

---

## 6. Success Rotation Policy

### Когда можно переносить в `sent/`

Только при **ВСЕХ** условиях:

1. `PopSendRunResult.run_status = ok`
2. `PopSendRunResult.pending_should_remain = false`
3. `PopSendRunResult.accepted_events > 0`
4. Backend response содержит подтверждение (2xx + `status: "processed"`)
5. События были в составе отправленного payload (batch candidates)

**Важно:**
- Только те события, которые вошли в payload
- Только при точном сопоставлении с batch candidates (по `selected_order`)
- Без вывода IDs в logs/safe output

### Пример

```
run_status=ok, accepted_events=3, pending_should_remain=false
→ 3 completed eligible события из pending → sent/
→ остальные строки (если есть) → остаются в pending
```

---

## 7. Partial Success Policy

### Проблема

Backend может вернуть `status: "processed"` но `summary.accepted=2, rejected=1`. Без event-level mapping нельзя определить, какие именно события accepted, а какие rejected.

### Политика

- **Accepted события можно переносить в `sent/` только если backend явно вернул line/event-level подтверждение** (например, `results[i].status = "accepted"` с `device_event_id`)
- **Rejected события — в `quarantine/` только если backend явно указал, какие именно события rejected**
- **Если backend даёт только агрегаты** (`summary.accepted=2, summary.rejected=1`) **без event-level mapping — pending не трогать**
- **Partial success без точной привязки → `pending_should_remain=true`**

### Реализация (будущая)

На rotation step:
1. Сравнить `device_event_id` из ответа backend с `device_event_id` в payload
2. Только события с явным `status: "accepted"` в `results[]` → `sent/`
3. Только события с явным `status: "rejected"` в `results[]` → `quarantine/`
4. Если `results[]` отсутствует или неполный → pending untouched

---

## 8. 409 Duplicate Batch Policy

### Текущая политика (зафиксирована в 26.24.1)

| Параметр | Значение |
|---|---|
| `send_status` | `warning` |
| `reason` | `duplicate_batch` |
| `retryable` | `false` |
| `pending_should_remain` | **`true`** |
| `run_status` (runner) | `warning` |

### Правило

- **409 НЕ разрешает удалять или перемещать pending**
- Backend видел `batch_id`, но **без явного accepted/processed подтверждения** в response body
- Duplicate-safe removal возможен только будущим отдельным шагом, если backend contract явно подтвердит:
  - `status: "processed"` или `status: "duplicate_batch"` с `summary.accepted > 0`
  - Или `results[]` с event-level подтверждением accepted
- **Без такого подтверждения 409 не считается успехом rotation**

---

## 9. Draft / Diagnostic Policy

### Draft

- `event_status: draft` → **НЕ PoP**
- Может быть перемещён в `dry_run/` только отдельной будущей cleanup policy
- В текущей реализации pop-write создаёт draft-события (dry-run симуляция)
- При rotation: draft-строки → `dry_run/`

### Diagnostic (blocked/failed)

- `event_status: blocked` → не PoP (safety gate заблокировал)
- `event_status: failed` → не PoP (ошибка воспроизведения)
- **Blocked/failed нельзя отправлять как PoP**
- Diagnostic rotation не должна мешать real completed events
- При rotation: blocked/failed → `dry_run/`

---

## 10. Quarantine Policy

### Что идёт в quarantine

| Причина | Описание |
|---|---|
| Invalid JSON | Строка не парсится как JSON |
| Invalid schema | Неизвестные ключи, невалидные значения |
| Forbidden fields/values | token, secret, receipt_data, … |
| Manifest mapping missing | `selected_order` не найден в current manifest |
| Manifest unavailable | Manifest отсутствует или невалиден |
| Media cache incomplete | Не все media файлы присутствуют |
| Safety state не idle | `transaction`, `payment`, `receipt`, `error`, … |
| Unknown event_status | Не `draft`, не `completed`, не `blocked`, не `failed` |
| Любые сомнительные события | Если нельзя уверенно классифицировать |

### Принцип

> **При сомнении: quarantine или pending untouched, но не sent.**

---

## 11. Failed Policy

### Назначение `failed/`

События, которые:
- Были eligible (completed + idle + manifest mapping + media complete)
- Были отправлены в backend
- Backend не принял после всех retry (`retry_exhausted=true`)
- Нельзя просто потерять — нужен audit trail

### Отличие от quarantine

| Папка | Причина | Действие |
|---|---|---|
| `quarantine/` | Событие невалидно/небезопасно ДО отправки | Не отправлять, исследовать |
| `failed/` | Отправка была, но backend не принял после retry | Сохранить для audit, повторить позже |

---

## 12. Safe Rotation Result (Future)

### `PopRotationResult`

```python
@dataclass
class PopRotationResult:
    rotation_status: str        # ok | warning | error | skipped
    pending_lines_before: int
    pending_lines_after: int
    sent_lines: int
    quarantine_lines: int
    dry_run_lines: int
    failed_lines: int
    pending_untouched: bool     # True если pending не менялся
    reason: str                 # safe reason
```

### Запрещено в result/output

- raw JSON events
- file paths
- payload body
- batch_id / device_event_id / manifest_item_id / campaign_id / creative_id / schedule_item_id
- filename / sha256
- stacktrace

### Safe output (пример)

```
rotation_status:         ok
pending_lines_before:    5
pending_lines_after:     2
sent_lines:              3
quarantine_lines:        0
dry_run_lines:           0
failed_lines:            0
pending_untouched:       false
reason:                  processed_3_events
```

---

## 13. Forbidden in Rotation Logs/Output

Запрещено в logs, safe output, errors, result fields:

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

---

## 14. Fail Safe Contract

| Правило | Описание |
|---|---|
| **Не мешать КСО** | Rotation не блокирует плеер, не влияет на транзакции |
| **Не ломать player** | Ошибка rotation не крашит плеер, не мешает pop-write |
| **Pending untouched при ошибке** | Любая ошибка на любом шаге → pending остаётся как было |
| **Не удалять pending при warning/error** | Только ok → можно трогать |
| **Не удалять pending при 409** | 409 → `pending_should_remain=true` |
| **Не удалять pending при partial без mapping** | Нет event-level mapping → pending untouched |
| **Permission error / disk full** | Pending untouched, rotation aborted |
| **Сомнение → quarantine или pending** | Никогда не sent |
| **Никаких customer/payment/receipt/card данных** | Ни при каких условиях |

---

## 15. Roadmap

| Шаг | Описание |
|---|---|
| **26.27** | PoP Local Rotation Mini-Design (этот документ) |
| **26.28** | Rotation Core — `pop_rotation.py`: классификация + атомарное перемещение |
| **26.29** | Rotation CLI — `pop-rotate` команда |
| **26.30** | Rotation Run-Cycle Integration |
| **26.31+** | Lock contract с двух сторон, cleanup policy, failed retry |

---

## 16. Security Summary

- ✅ Rotation выполняется только после backend confirmation
- ✅ `pending_should_remain=true` → pending нетронут при любых условиях
- ✅ 409 duplicate НЕ разрешает удалять pending
- ✅ Atomic model: ошибка на любом шаге → pending untouched
- ✅ Partial success без event-level mapping → pending untouched
- ✅ Draft/blocked/failed не являются PoP и не идут в sent
- ✅ Quarantine для unsafe/сомнительных событий
- ✅ Lock contract предотвращает гонки player↔sidecar
- ✅ Forbidden поля исключены из всех safe output/logs
- ✅ Fail safe: rotation не мешает КСО/плееру
- ✅ Customer/payment/receipt/card details запрещены на всех этапах
