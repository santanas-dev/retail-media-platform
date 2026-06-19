# Mini-Design: KSO Sidecar PoP Pickup

**Статус:** 📝 Design-only. Код не пишем.
**Шаг:** 26.14
**Дата:** 19 июня 2026
**Основание:** `apps/kso_player/docs/pop_local_writer_design.md`, `apps/kso_sidecar_agent/run_cycle.py`, `docs/kso_sidecar_run_cycle_design.md`

---

## 1. Goal

Спроектировать **PoP pickup step** — будущий шаг run-cycle, в котором sidecar забирает локальные player events из `pop/pending/player_events.jsonl`, валидирует их, классифицирует по статусу и готовит eligible-события к отправке в backend.

**Это дизайн, не реализация.** Код pickup будет написан отдельным шагом.

---

## 2. Architecture Overview

```
┌──────────────┐  write                    ┌──────────────────────┐  read+move   ┌──────────────┐
│  KSO Player   │ ──────────→ pop/pending/ │                      │ ───────────→ │  Backend     │
│  (pop-write)  │            player_events  │  Sidecar PoP Pickup  │              │  (future)    │
└──────────────┘            .jsonl          │  (run-cycle step)     │              └──────────────┘
                                            └──────────────────────┘
```

- **Player** — только пишет draft/dry-run события в `pop/pending/`. Не знает о backend/sidecar.
- **Sidecar PoP Pickup** — отдельный шаг run-cycle: читает `pop/pending/`, валидирует, классифицирует, перемещает.
- **Backend** — получает только eligible-события. Draft-события не являются PoP.

---

## 3. Directory Layout (Planned)

```
{root}/
  pop/
    pending/
      player_events.jsonl       # player пишет сюда (append-only)
    sent/                        # sidecar перемещает после успешной отправки backend
    quarantine/                  # невалидные/небезопасные события
    dry_run/                     # draft/dry-run события (не факт показа)
```

**Пока только дизайн.** Папки создаются кодом pickup (будущий шаг), не сейчас.

---

## 4. Event Status Classification

Player пишет события с `event_status: draft`. Это **dry-run**: плеер не показывал рекламу, это только симуляция.

### Статусы и их семантика

| Статус | Что значит | Отправлять как PoP? | Куда поместить |
|---|---|---|---|
| `draft` | Dry-run симуляция. Не факт показа. | ❌ НЕТ | `dry_run/` или оставить в `pending/` |
| `completed` | Реальный показ состоялся (будущее). | ✅ Да (с проверками) | `sent/` после отправки |
| `blocked` | Safety gate заблокировал показ. | ❌ НЕТ (diagnostic) | `dry_run/` или `quarantine/` |
| `failed` | Ошибка при воспроизведении. | ❌ НЕТ (diagnostic) | `dry_run/` или `quarantine/` |

### Ключевое правило

**`event_status: draft` НЕЛЬЗЯ отправлять в backend как подтверждение показа рекламы.**

- Текущий `pop-write` CLI создаёт draft-события из dry-run пайплайна
- Эти события — симуляция, не факт показа
- Факт показа появится только после будущего real playback с `event_status: completed`

---

## 5. Eligible Events for Backend

Событие eligible для отправки в backend как PoP только при ВСЕХ условиях:

1. **`event_status` = `completed`** — реальный показ состоялся (не draft, не dry-run)
2. **Schema valid** — все поля соответствуют `ALLOWED_RECORD_KEYS`
3. **Forbidden fields absent** — нет token, secret, receipt_data, card, paths, filename, sha256, manifest_item_id
4. **Manifest mapping exists** — `selected_order` можно сопоставить с item в current manifest
5. **Manifest unchanged** — manifest не менялся после события (или есть безопасная проверка)
6. **Media cache complete** — все media файлы присутствуют и верифицированы
7. **safety_state допустимый** — только `idle` (для PoP); `payment`/`transaction`/`receipt` → не PoP

### Что НЕ является eligible

- `event_status: draft` → НЕ PoP (dry-run симуляция)
- `event_status: blocked` → НЕ PoP (safety заблокировал)
- `event_status: failed` → НЕ PoP (ошибка)
- Событие без manifest mapping → НЕ PoP
- Событие с forbidden substrings → НЕ PoP, quarantine

---

## 6. Manifest Mapping via selected_order

Player не пишет `manifest_item_id`, `filename`, `sha256`. Вместо этого используется `selected_order`:

```
Player writes: {"selected_order": 2, ...}
Sidecar reads: current_manifest.json → items[2] → manifest_item_id, content_type
Sidecar sends: {"selected_order": 2, "manifest_item_id": "<from manifest>", ...}
```

### Правила сопоставления

1. Sidecar читает `manifest/current_manifest.json`
2. Сортирует items по `order`
3. Ищет item с `order == selected_order`
4. Если найден → использует `manifest_item_id` из manifest (только для backend payload, не в логах)
5. Если НЕ найден → событие невалидно: quarantine, не отправлять
6. Если manifest изменился (manifest_version_id сменился) после времени события → проверка: `created_at` < `manifest.generated_at`? Если да — событие устарело, не отправлять

### Безопасность manifest_item_id

- `manifest_item_id` можно использовать только внутри sidecar для сопоставления с backend
- Запрещено писать `manifest_item_id` в safe output, логи, stdout/stderr
- В backend payload разрешён только если получен из текущего валидного manifest

---

## 7. Atomic Pickup Model (Future Implementation)

### Общий алгоритм

```
1. SIDECAR БЕРЁТ LOCK (file lock на pop/pending/)
2. Читает pop/pending/player_events.jsonl построчно
3. Для каждой строки:
   a. Парсит JSON
   b. Валидирует schema (ALLOWED_RECORD_KEYS)
   c. Проверяет forbidden substrings
   d. Классифицирует по event_status:
      - draft → переместить в dry_run/ (или оставить в pending по политике)
      - completed → проверить manifest mapping; если OK → batch
      - blocked/failed → dry_run/ или quarantine/
      - невалидная строка → quarantine/
   e. Если batch не пуст и manifest актуален → отправка в backend
4. При успешной отправке backend → переместить batch строки в sent/
5. При ошибке backend → НЕ удалять pending, оставить на месте
6. Снять LOCK
```

### Правила перемещения

| Статус | Действие |
|---|---|
| `draft` | `pending/` → `dry_run/` (или оставить, политика настраиваемая) |
| `completed` + manifest OK + backend OK | `pending/` → `sent/` |
| `completed` + manifest mismatch | `pending/` → `quarantine/` |
| `blocked` / `failed` | `pending/` → `dry_run/` |
| Невалидная строка | `pending/` → `quarantine/` |
| Backend send failure | Оставить в `pending/`, повторить в следующем цикле |

### Никаких частичных удалений

- Строка удаляется из pending ТОЛЬКО после подтверждения backend
- При сбое — всё остаётся в pending
- Никаких delete без move + verify

---

## 8. Forbidden in Pickup/Backend Payload

Запрещено читать, хранить, отправлять в любом виде:

| Категория | Запрещённые поля |
|---|---|
| **Secrets** | `token`, `jwt`, `password`, `secret`, `api_key`, `private_key` |
| **Payment** | `payment_card`, `receipt_data`, `card_number`, `pan` |
| **Customer** | `customer_id`, `phone`, `email`, `receipt_number`, `fiscal_data` |
| **Paths** | `local_path`, `file_path`, `media_path`, `creatives/` |
| **Auth** | `authorization`, `bearer`, `device_secret`, `access_token` |
| **Backend** | `backend_base_url`, `127.0.0.1`, `device_code` |
| **Media IDs** | `filename`, `sha256` |
| **Raw data** | `full_manifest`, `media_bytes`, `stacktrace` |

**`manifest_item_id`** — использовать ТОЛЬКО внутри sidecar для сопоставления, НЕ писать в safe output, логи, stdout/stderr.

---

## 9. Fail Silent / Fail Safe Contract

| Правило | Описание |
|---|---|
| Не мешать КСО | Pickup не блокирует плеер, не влияет на транзакции |
| Не ломать player | Ошибка pickup не крашит плеер, не мешает pop-write |
| Не удалять pending при ошибке | Backend failure → pending untouched |
| Unsafe event → не отправлять | Forbidden fields → quarantine, не backend |
| Сомнение → quarantine | Если нельзя уверенно сказать eligible → не отправлять |
| Никаких customer/payment/receipt/card details | Ни при каких условиях |

---

## 10. Dry-Run vs Real Playback (Future Clarification)

Текущий `pop-write` CLI — это **dry-run**:

```
pop-write --state idle → event_status=draft → dry_run/
```

Будущий реальный playback (Шаг 27.x+) создаст события с `event_status: completed`:

```
real playback loop → event_status=completed → eligible for backend PoP
```

**Ключевое различие:**

| Параметр | pop-write (сейчас) | Real playback (будущее) |
|---|---|---|
| `event_status` | `draft` | `completed` |
| Отправка в backend | ❌ | ✅ (после всех проверок) |
| Папка | `dry_run/` | `sent/` (после отправки) |
| Является PoP | ❌ | ✅ |

---

## 11. Roadmap

| Шаг | Описание |
|---|---|
| **26.15** | PoP Pickup Core — реализация `pop_pickup.py`: `read_pending_events()`, `classify_event()`, `validate_event()` |
| **26.16** | PoP Pickup CLI — `pop-pickup` команда |
| **26.17** | PoP Pickup Run-Cycle Integration — pickup как шаг run-cycle |
| **26.18+** | Backend PoP Send — отправка eligible событий в backend |

---

## 12. Security Summary

- ✅ Pickup только читает `pop/pending/`, не пишет в player-области
- ✅ Draft-события НЕ отправляются как PoP
- ✅ Forbidden fields проверяются перед любой отправкой
- ✅ Manifest mapping защищает от рассинхронизации
- ✅ Atomic lock предотвращает гонки
- ✅ Никаких частичных удалений без подтверждения backend
- ✅ Unsafe → quarantine, не backend
- ✅ Fail silent: ошибка не влияет на КСО/плеер
- ✅ Customer/payment/receipt/card details запрещены на всех этапах
