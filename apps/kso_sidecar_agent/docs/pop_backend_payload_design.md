# Mini-Design: KSO Sidecar PoP Backend Payload

**Статус:** 📝 Design-only. Код не пишем.
**Шаг:** 26.19
**Дата:** 19 июня 2026
**Основание:** `apps/kso_sidecar_agent/docs/pop_pickup_design.md`, `apps/kso_sidecar_agent/pop_batch.py`, backend `proof_of_play_events` (013), `proof_of_play_batches` (014)

---

## 1. Goal

Спроектировать **безопасный backend payload** для будущей отправки eligible PoP событий из sidecar в backend через `POST /device-gateway/pop/events/batch`.

**Это дизайн, не реализация.** Код payload builder + HTTP sender будет написан отдельными шагами.

---

## 2. Existing Backend PoP Infrastructure (Analysis)

### Таблицы

**`proof_of_play_events`** (миграция 013):

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | PK |
| `gateway_device_id` | UUID FK | Устройство |
| `device_event_id` | UUID | Уникальный ID события от устройства |
| `manifest_item_id` | UUID FK | Сопоставленный item |
| `manifest_version_id` | UUID FK | Версия манифеста |
| `publication_target_id` | UUID FK | Цель публикации |
| `schedule_item_id` | UUID FK | Элемент расписания |
| `campaign_id` | UUID FK | Кампания |
| `campaign_rendition_id` | UUID FK | Рендиция кампании |
| `rendition_id` | UUID FK | Рендиция |
| `creative_version_id` | UUID FK | Версия креатива |
| `played_at` | timestamptz | Когда показано |
| `received_at` | timestamptz | Когда получено backend |
| `duration_ms` | int | Длительность |
| `play_status` | str | started/completed/interrupted/skipped/failed |
| `validation_status` | str | accepted/rejected/invalid_manifest/duplicate/missing_manifest |
| `media_sha256` | str(64) | SHA256 media (NULL allowed) |
| `expected_sha256` | str(64) | Ожидаемый SHA256 |
| `player_version` | str(64) | Версия плеера |
| `ip_address` | str(45) | IP |
| `user_agent` | str(500) | User-Agent |
| `details_json` | JSONB | Произвольные детали |
| `rejection_reason` | str(100) | Причина отклонения |
| `created_at` | timestamptz | Когда создана запись |

**`proof_of_play_batches`** (миграция 014):

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | PK |
| `gateway_device_id` | UUID FK | Устройство |
| `device_batch_id` | UUID | ID батча от устройства |
| `batch_status` | str | pop_batch_processed/duplicate/rejected |
| `total_events` | int | Всего событий |
| `accepted_count` | int | Принято |
| `duplicate_count` | int | Дубликатов |
| `rejected_count` | int | Отклонено |
| `sent_at` | timestamptz | Когда отправлено |
| `processed_at` | timestamptz | Когда обработано |
| `ip_address` | str(45) | IP |
| `user_agent` | str(500) | User-Agent |
| `details_json` | JSONB | Детали |
| `created_at` | timestamptz | Когда создана запись |

### Эндпоинты

- `POST /device-gateway/pop/events` — одиночное событие
- `POST /device-gateway/pop/events/batch` — батч событий
- `GET /gateway-devices/{DID}/pop-batches` — список батчей устройства

### Batch endpoint (payload)

```json
{
  "batch_id": "UUID",
  "sent_at": "ISO8601",
  "events": [
    {
      "device_event_id": "UUID",
      "manifest_item_id": "UUID",
      "..."
    }
  ]
}
```

### Batch endpoint (response)

```json
{
  "proof_batch_id": "UUID",
  "status": "processed|duplicate_batch|rejected",
  "results": [
    {"device_event_id": "UUID", "status": "accepted|duplicate|rejected",
     "proof_event_id": "UUID|null", "rejection_reason": "str|null"}
  ],
  "summary": {"accepted": N, "duplicate": N, "rejected": N}
}
```

---

## 3. Payload Builder (Future Implementation)

Будущий `build_pop_backend_payload()` должен:

1. Взять in-memory batch из `build_pop_eligible_batch()`
2. Для каждого candidate сопоставить `selected_order` → `manifest_item_id` из current manifest
3. Сгенерировать `device_event_id` (UUID) для каждого события
4. Собрать `batch_id` (UUID)
5. Сформировать JSON payload без forbidden fields
6. Вернуть только safe aggregated result

**НЕ отправляет HTTP.** HTTP sender — отдельный шаг.

---

## 4. Payload Fields

### A. Поля из player event (PopBatchCandidate)

| Поле | Источник | Описание |
|---|---|---|
| `device_event_id` | UUID (генерируется) | Уникальный ID события |
| `played_at` | `started_at` из candidate | Когда начался показ |
| `duration_ms` | `duration_ms` из candidate | Длительность |
| `play_status` | `"completed"` | Только completed попадают |

### B. Поля из manifest mapping (через selected_order)

| Поле | Источник | Описание |
|---|---|---|
| `manifest_item_id` | manifest item → `manifest_item_id` | Только для backend payload |
| `manifest_version_id` | manifest → `manifest_version_id` | ID версии манифеста |
| `campaign_id` | manifest item → если есть | Optional |
| `publication_target_id` | manifest → если есть | Optional |
| `schedule_item_id` | manifest item → если есть | Optional |

### C. Поля из sidecar контекста

| Поле | Источник | Описание |
|---|---|---|
| `batch_id` | UUID (генерируется) | ID батча |
| `sent_at` | Текущее время ISO8601 | Когда отправлено |
| `player_version` | `"kso-player-dry-run"` | Пока dry-run |
| `ip_address` | `null` | Sidecar не собирает IP |
| `user_agent` | `null` | Sidecar не собирает UA |

**Важно:** если в текущем manifest некоторых полей нет (campaign_id, publication_target_id и т.д.) — они optional и могут быть `null`. Не выдумывать данные.

---

## 5. Forbidden in Payload

В backend payload ЗАПРЕЩЕНО:

| Категория | Поля |
|---|---|
| **Secrets** | `token`, `jwt`, `password`, `secret`, `api_key`, `private_key` |
| **Payment** | `payment_card`, `receipt_data`, `card_number`, `pan` |
| **Customer** | `customer_id`, `phone`, `email`, `receipt_number`, `fiscal_data` |
| **Paths** | `local_path`, `file_path`, `media_path`, `creatives/` |
| **Auth** | `authorization`, `bearer`, `device_secret`, `access_token` |
| **Backend** | `backend_base_url`, `127.0.0.1`, `device_code` |
| **Media IDs** | `filename`, `sha256` |
| **Raw data** | `full_manifest`, `media_bytes`, `stacktrace` |

**`manifest_item_id` разрешён только внутри backend payload. Запрещён в safe output, логах, stdout/stderr.**

Слово `receipt` как safety_state допустимо. `receipt_data`, номер чека, карта, покупатель, фискальные данные запрещены.

---

## 6. Eligibility Rules (повтор)

Событие eligible для backend payload только при ВСЕХ условиях:

1. `event_status` = `completed`
2. `event_type` = `would_play`
3. `result` = `would_play`
4. `session_action` = `play`
5. `session_reason` = `ready`
6. `playback_allowed` = `true`
7. `safety_state` = `idle`
8. `selected_order` найден в current manifest
9. Media cache complete
10. Schema valid
11. Forbidden fields absent

Если любое условие не выполнено — не включать в payload.

---

## 7. Что НЕ является eligible

| Статус/состояние | Почему не eligible |
|---|---|
| `event_status: draft` | Dry-run симуляция, не факт показа |
| `event_status: blocked` | Safety gate заблокировал |
| `event_status: failed` | Ошибка показа |
| `safety_state: payment/transaction/receipt` | КСО не в idle |
| `selected_order` не найден в manifest | Нет сопоставления |
| Media cache incomplete | Нет гарантии, что media был |

---

## 8. Safe Output (будущий payload builder)

Payload builder должен возвращать только агрегаты:

```
status: ok|warning|error
payload_events: int
skipped_events: int
invalid_events: int
quarantine_events: int
diagnostic_events: int
draft_events: int
batch_limited: bool
max_events: int
```

**Никогда не возвращать:**
- payload body (raw JSON)
- manifest_item_id
- campaign_id/creative_id/schedule_item_id
- filename
- sha256
- paths
- full manifest
- media bytes

---

## 9. Backend Send Policy (Future)

| Правило | Описание |
|---|---|
| Отправлять только `payload_events` | Eligible completed — единственные |
| НЕ отправлять draft/blocked/failed | Не являются PoP |
| При backend error → pending не удалять | Сохранить для повторной попытки |
| Только после подтверждения backend → move в sent/ | Atomic rotate после 2xx |
| Unsafe event → quarantine | Не отправлять |
| Сомнение → не отправлять | Quarantine, не backend |

---

## 10. Audit / Traceability

- Внутренние счётчики: `payload_events`, `skipped`, `invalid`, `quarantine`
- Safe reason counts без raw данных
- НИКОГДА raw payload в логах
- НИКОГДА manifest_item_id/campaign_id/creative_id в логах
- НИКОГДА filename/hash/path
- Ошибки без stacktrace наружу

---

## 11. Roadmap

| Шаг | Описание |
|---|---|
| **26.20** | PoP Backend Payload Builder Core — `build_pop_backend_payload()` |
| **26.21** | PoP Backend Payload CLI — `pop-build-payload` |
| **26.22+** | HTTP Sender + Run-Cycle Integration |

---

## 12. Security Summary

- ✅ Payload формируется только из eligible completed событий
- ✅ Draft/blocked/failed не включаются
- ✅ manifest_item_id только внутри payload, не в логах
- ✅ Forbidden fields жёстко исключены
- ✅ Safe output — только агрегаты, никогда raw JSON
- ✅ Pending не удаляется при ошибке backend
- ✅ Сомнение → quarantine
- ✅ Customer/payment/receipt/card details запрещены на всех этапах
