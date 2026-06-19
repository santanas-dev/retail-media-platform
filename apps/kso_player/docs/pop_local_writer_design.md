# Mini-Design: KSO Player PoP Local Writer

**Статус:** 📝 Design-only. Код не пишем.
**Шаг:** 26.11
**Дата:** 19 июня 2026
**Основание:** `apps/kso_player/README.md`, Шаги 26.0–26.10 (playlist, safety, session, simulator, events, CLI)

---

## 1. Goal

Спроектировать **безопасный локальный PoP writer** — компонент player, который пишет события playback в локальный JSONL-файл. Writer — это **ручной handoff** от player к sidecar: player пишет события локально, sidecar позже забирает их отдельным шагом run-cycle.

**Это дизайн, не реализация.** Код writer будет написан отдельным шагом.

---

## 2. Role in Architecture

```
┌──────────────┐    write    ┌──────────────────────┐    read     ┌──────────────┐
│  KSO Player   │ ──────────→│  pop/pending/*.jsonl  │←─────────── │  Sidecar     │
│  (read‑only)  │            │  (local handoff)      │             │  Agent       │
└──────────────┘            └──────────────────────┘            └──────┬───────┘
                                                                       │
                                                                  ┌────▼───────┐
                                                                  │  Backend   │
                                                                  │  (future)   │
                                                                  └────────────┘
```

- **Player** — пишет только в `pop/pending/`. Никогда не отправляет в backend.
- **Sidecar** — отдельным шагом run-cycle читает `pop/pending/`, отправляет в backend, перемещает в `pop/sent/` или `pop/quarantine/`.
- **Player не знает о sidecar.** Player не знает о backend. Player только пишет локально.

---

## 3. Directory Layout (Future)

Внутри агентского `root`:

```
{root}/
  manifest/
    current_manifest.json          # (существующий)
  media/
    current/                        # (существующий)
    staging/                        # (существующий)
    quarantine/                     # (существующий)
  pop/                              # 🆕 планируется
    pending/                        # 🆕 player пишет сюда
      player_events.jsonl           # 🆕 append-only JSONL
    sent/                           # 🆕 sidecar перемещает после отправки
    quarantine/                     # 🆕 sidecar перемещает при ошибках отправки
```

**Пока только дизайн.** Папки НЕ создаются кодом на этом шаге.

---

## 4. JSONL Line Format

Одна строка = одно событие. Append-only. Минимальный безопасный формат:

```json
{
  "schema_version": 1,
  "event_type": "would_play",
  "event_status": "draft",
  "created_at": "2026-06-19T00:00:00+00:00",
  "started_at": "2026-06-19T00:00:00+00:00",
  "ended_at": null,
  "duration_ms": 5000,
  "playback_allowed": true,
  "session_action": "play",
  "session_reason": "ready",
  "selected_order": 0,
  "selected_content_type": "image/png",
  "safety_state": "idle",
  "result": "would_play"
}
```

### Поля

| Поле | Тип | Описание |
|---|---|---|
| `schema_version` | int | Версия формата (начинается с 1) |
| `event_type` | str | `would_play` / `blocked` / `not_ready` / `error` |
| `event_status` | str | `draft` — всегда draft (в первом writer) |
| `created_at` | str | ISO8601 UTC — когда событие создано |
| `started_at` | str\|null | ISO8601 UTC — расчётное время начала (null если blocked) |
| `ended_at` | str\|null | ISO8601 UTC — `started_at + duration_ms` (null если blocked) |
| `duration_ms` | int | Длительность в мс (0 если blocked/not_ready/error) |
| `playback_allowed` | bool | Разрешил ли safety gate |
| `session_action` | str | `play` / `hold` / `stop` |
| `session_reason` | str | `ready` / `safety_blocked` / `playlist_not_ready` / `no_items` / `invalid_state` |
| `selected_order` | int\|null | Порядковый номер выбранного item |
| `selected_content_type` | str\|null | MIME-тип выбранного item |
| `safety_state` | str | Состояние КСО (из safety snapshot) |
| `result` | str | Итог: `would_play` / `blocked` / `not_ready` / `error` |

**Важно:** если нужны id — использовать только безопасные локальные ids. В первом writer лучше их не писать.

---

## 5. Forbidden Fields

В PoP ЗАПРЕЩЕНО писать:

| Категория | Запрещённые поля/подстроки |
|---|---|
| **Secrets** | `token`, `jwt`, `password`, `secret`, `api_key`, `private_key` |
| **Payment** | `payment_card`, `receipt_data`, `card_number`, `pan` |
| **Customer** | `customer_id`, `phone`, `email`, `receipt_number`, `fiscal_data` |
| **Paths** | `local_path`, `file_path`, `media_path`, `creatives/` |
| **Auth** | `authorization`, `bearer`, `device_secret`, `access_token` |
| **Backend** | `backend_base_url`, `device_code` |
| **Media IDs** | `filename`, `manifest_item_id`, `sha256` |
| **Raw data** | `full manifest`, `media bytes`, `stacktrace` |

**Слово `receipt` как название safety_state допустимо.** Запрещены именно данные чека: `receipt_data`, номера чеков, фискальные данные, customer/payment/card details.

---

## 6. Atomic Write Design (Future Implementation Rules)

Когда writer будет реализован, он должен следовать этим правилам:

### Правила записи

1. **Append-only JSONL** — одна строка = одно событие. Никогда не перезаписывать существующие строки.
2. **Validate safe schema** — перед записью проверить, что строка не содержит forbidden substrings/fields.
3. **Atomic append** — запись через temp file + rename, или безопасный append с file lock.
4. **flush + fsync** — после каждой записи гарантировать, что данные на диске.
5. **Fail silent** — если строка невалидна → не писать, не крашить player.
6. **Fail safe** — если ошибка записи → не мешать КСО, не крашить, не терять состояние.
7. **Не удалять старые события** — player только пишет. Ротацию/отправку делает sidecar отдельным процессом.

### Обработка ошибок

```
Попытка записи:
  ├─ Строка невалидна (forbidden substrings) → skip, не писать
  ├─ Ошибка fsync → fail silent, не крашить
  ├─ Диск полон → stop writing, не крашить
  └─ Успех → append + flush + fsync
```

---

## 7. Retention / Size Limits (Future)

| Параметр | Значение | Действие при превышении |
|---|---|---|
| `max_line_size` | 4096 байт | Отклонить строку (не писать) |
| `max_file_size` | 10 MB | Прекратить запись в текущий файл |
| `max_pending_files` | 5 | Прекратить запись, ждать sidecar |

**Player не должен падать из-за переполнения PoP.** При превышении лимитов — stop writing, но не удалять файлы без retention-политики (это ответственность sidecar).

---

## 8. Safety Contract (KSO Integrity)

PoP writer НЕ влияет на КСО. Это жёсткое правило:

| Что writer НЕ делает | Почему |
|---|---|
| Не блокирует оплату | КСО-транзакции не пересекаются с writer |
| Не читает чек | Writer не имеет доступа к receipt data |
| Не читает карту | Writer не имеет доступа к payment card |
| Не читает покупателя | Writer не хранит customer data |
| Не вмешивается в transaction/payment/service/error | Writer только наблюдает и пишет |
| Не делает HTTP | Никаких сетевых вызовов |
| Fail silent при любой ошибке | Ошибка writer не должна влиять на плеер |

---

## 9. Roadmap (Future Steps)

| Шаг | Описание |
|---|---|
| **26.12** | PoP Local Writer Core — реализация `pop_writer.py`: `write_event_draft()`, валидация, atomic append |
| **26.13** | PoP Writer CLI — `pop-write` команда |
| **26.14** | PoP Writer Integration — интеграция с `event-dry-run` (опциональный `--pop-write` флаг) |
| **26.15+** | Sidecar PoP Reader — отдельный шаг run-cycle для чтения `pop/pending/` и отправки в backend |

---

## 10. Security Summary

- ✅ Writer пишет только в `pop/pending/`
- ✅ Writer не отправляет данные в backend
- ✅ Writer не делает HTTP
- ✅ Writer не читает secret / token / config / device_code / backend URL
- ✅ Writer не пишет forbidden fields (token, secret, card, receipt data, paths, filenames, sha256, manifest IDs, media bytes)
- ✅ Writer не влияет на КСО (fail silent)
- ✅ Player не знает о sidecar
- ✅ Sidecar забирает события отдельным шагом
- ✅ Все поля только безопасные (aggregated data, no raw data)
