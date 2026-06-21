# KSO Player — Core Skeleton

**Статус:** 🏗 Skeleton. Первый безопасный каркас будущего KSO Player.

## Что это

KSO Player — будущий UI-плеер для показа контента на КСО-терминалах.
На этом шаге реализован **только core skeleton**: чтение локального manifest/media,
проверка готовности, построение safe playlist, CLI-команда `playlist-status`
и safety gate (fail-closed).

## Что сейчас работает

- `build_playlist(root)` — построение playlist из локального manifest + media cache
- `format_playlist_summary(playlist)` — safe агрегированный вывод
- `playlist-status` CLI — проверка готовности playlist (read-only)
- `safety-check` CLI — проверка playlist + safety gate (read-only, state вручную)
- `playback-dry-run` CLI — полный сухой прогон: playlist → safety → session
- `decide_playback_safety(snapshot, playlist)` — safety gate: разрешить/запретить playback
- `format_safety_decision(decision)` — safe вывод решения
- `select_next_item(playlist, safety_decision, state=None)` — выбор следующего media item
- `format_session_decision(decision)` — safe вывод session decision

## Safety Gate

**Fail-closed:** плеер может показывать рекламу **только** когда КСО явно в idle-состоянии.
Во всех остальных случаях — stop или hold.

### Состояния КСО

| Состояние | Действие | Описание |
|---|---|---|
| `idle` | play (если playlist ready) | Единственное состояние, где playback разрешён |
| `unknown` | hold | Состояние неизвестно — ждать |
| `transaction` | stop | Активная транзакция |
| `payment` | stop | Активный платёж |
| `receipt` | stop | Показ чека |
| `service` | stop | Сервисный режим |
| `error` | stop | Ошибка КСО |
| `maintenance` | stop | Обслуживание |
| `offline` | stop | КСО офлайн |

### Правила принятия решения

- `idle` + playlist ready → `allowed=true`, `action=play`
- Любое другое состояние → `allowed=false`, `action=stop`
- `unknown` → `action=hold`
- Playlist not ready → `action=hold` (даже в idle)
- Отсутствие snapshot → `action=stop`
- Невалидное состояние → `action=stop` (fail closed)

**Это пока core logic без интеграции с реальным КСО.**

## CLI: `playlist-status`

```bash
cd apps/kso_player

# Проверить готовность playlist
python3 -m kso_player.cli playlist-status --root /tmp/kso-agent-root

# Help
python3 -m kso_player.cli --help
python3 -m kso_player.cli playlist-status --help
```

### Пример вывода (ready)

```
playlist_ready: true
status: ready
reason: ready
items_total: 2
items_ready: 2
items_missing: 0
items_failed: 0
```

### Пример вывода (not ready)

```
playlist_ready: false
status: not_ready
reason: media_incomplete
items_total: 2
items_ready: 1
items_missing: 1
items_failed: 0
```

### Exit codes

| Код | Значение |
|---|---|
| 0 | Playlist ready (все items проверены) |
| 1 | Playlist not_ready или error |
| 2 | Invalid CLI args |

## CLI: `safety-check`

```bash
cd apps/kso_player

# Проверить: можно ли играть в idle?
python3 -m kso_player.cli safety-check --root /tmp/kso-agent-root --state idle

# Проверить с другими состояниями
python3 -m kso_player.cli safety-check --root /tmp/kso-agent-root --state payment
python3 -m kso_player.cli safety-check --root /tmp/kso-agent-root --state transaction

# Help
python3 -m kso_player.cli safety-check --help
```

**Важно:** команда принимает `--state` вручную и **не читает реальное состояние КСО**.
Интеграция с реальным КСО будет отдельным шагом.

### Пример вывода (idle + ready)

```
playlist_ready: true
status: ready
reason: ready
items_total: 2
items_ready: 2
items_missing: 0
items_failed: 0
state: idle
playback_allowed: true
action: play
reason: ready
```

### Пример вывода (payment + ready)

```
playlist_ready: true
status: ready
reason: ready
items_total: 2
items_ready: 2
items_missing: 0
items_failed: 0
state: payment
playback_allowed: false
action: stop
reason: payment_active
```

### Exit codes (safety-check)

| Код | Значение |
|---|---|
| 0 | Playback allowed (idle + playlist ready) |
| 1 | Playback blocked (любое не-idle состояние или playlist not ready) |
| 2 | Invalid CLI args |

## CLI: `playback-dry-run`

```bash
cd apps/kso_player

# Полный сухой прогон: playlist → safety → session
python3 -m kso_player.cli playback-dry-run --root /tmp/kso-agent-root --state idle

# Проверить с другими состояниями
python3 -m kso_player.cli playback-dry-run --root /tmp/kso-agent-root --state payment

# Help
python3 -m kso_player.cli playback-dry-run --help
```

**Важно:** это сухой прогон без реального playback. Media не проигрывается.
State передаётся вручную, реальное состояние КСО не читается.
Следующий шаг — playback simulator core.

### Пример вывода (idle + ready)

```
playlist_ready: true
playback_allowed: true
safety_action: play
safety_reason: ready
session_action: play
session_reason: ready
selected_order: 0
selected_content_type: image/png
selected_duration_ms: 5000
```

### Пример вывода (payment + ready)

```
playlist_ready: true
playback_allowed: false
safety_action: stop
safety_reason: payment_active
session_action: stop
session_reason: safety_blocked
```

### Exit codes (playback-dry-run)

| Код | Значение |
|---|---|
| 0 | session_action=play |
| 1 | session_action=hold/stop |
| 2 | Invalid CLI args |

## Playback Session Core

**In-memory only** — выбор следующего media item для показа.
Не проигрывает media, не использует UI/overlay, не интегрирован с КСО.

### `select_next_item(playlist, safety_decision, state=None)`

Fail-closed логика выбора следующего item:

1. Safety gate не разрешил → блокировка
2. Playlist not ready → блокировка
3. Нет items → блокировка
4. Session state невалиден → блокировка (hold / invalid_state)
5. Иначе → выбор по order:
   - Без state (None): первый item (order=0)
   - С валидным state: item после `current_index`, с зацикливанием

**Если session state повреждён или невалиден — fail closed: hold / invalid_state.**

### Session state (`PlaybackSessionState`)

В памяти, не пишется на диск:
- `current_index` — какой item был последним
- `cycle_count` — сколько полных циклов пройдено
- Без путей, без secret/token, без customer/payment данных

### Пример вывода (allowed)

```
session_action: play
session_reason: ready
selected_order: 0
selected_content_type: image/png
selected_duration_ms: 10000
```

### Пример вывода (blocked)

```
session_action: stop
session_reason: safety_blocked
```

**Не выводится:** filename, manifest_item_id, sha256, absolute paths, media bytes.

**Следующий шаг:** CLI `playback-dry-run`.

## Playback Simulator Core

**Simulation only** — моделирует один шаг плеера без реального playback.
Не проигрывает media, не делает sleep, не пишет PoP, не использует UI.

### `simulate_playback_step(playlist, safety_decision, session_state=None, now=None)`

Оборачивает полный пайплайн: playlist → safety → session → simulated result.

**Simulated status:**
- `would_play` — всё разрешено, выбрали бы этот item
- `blocked` — safety или session заблокировали playback
- `not_ready` — playlist не готов
- `error` — неожиданная ошибка

**Timestamps:** `started_at` и `would_end_at` — ISO8601 UTC, рассчитываются без реальной задержки.

### Пример вывода (would_play)

```
simulation_status: would_play
session_action: play
session_reason: ready
selected_order: 0
selected_content_type: image/png
selected_duration_ms: 5000
```

### Пример вывода (blocked)

```
simulation_status: blocked
session_action: stop
session_reason: safety_blocked
```

**Не выводится:** filename, manifest_item_id, sha256, absolute paths, media bytes.

**Следующий шаг:** simulator CLI.

## CLI: `simulate-step`

```bash
cd apps/kso_player

# Симулировать один шаг playback
python3 -m kso_player.cli simulate-step --root /tmp/kso-agent-root --state idle

# Проверить с заблокированным состоянием
python3 -m kso_player.cli simulate-step --root /tmp/kso-agent-root --state payment

# Help
python3 -m kso_player.cli simulate-step --help
```

**Важно:** это симуляция без реального playback. Media не проигрывается, sleep не делается, PoP не пишется.
State передаётся вручную, реальное состояние КСО не читается.

### Пример вывода (idle + ready)

```
playlist_ready: true
playback_allowed: true
simulation_status: would_play
session_action: play
session_reason: ready
selected_order: 0
selected_content_type: image/png
selected_duration_ms: 5000
```

### Пример вывода (payment + ready)

```
playlist_ready: true
playback_allowed: false
simulation_status: blocked
session_action: stop
session_reason: safety_blocked
```

### Exit codes (simulate-step)

| Код | Значение |
|---|---|
| 0 | simulation_status=would_play |
| 1 | simulation_status=blocked/not_ready/error |
| 2 | Invalid CLI args |

## Playback Event Model

**In-memory only** — draft-модель события playback.
Это НЕ PoP, ничего не пишется на диск, ничего не отправляется в backend.

### `build_playback_event_draft(simulation_result, safety_decision=None, now=None)`

Создаёт `PlaybackEventDraft` из результата симуляции. Всегда `event_status: draft`.

**Event types:**
- `would_play` — simulation_status=would_play
- `blocked` — simulation_status=blocked
- `not_ready` — simulation_status=not_ready
- `error` — неожиданный/невалидный результат

### Пример вывода (would_play)

```
event_type: would_play
event_status: draft
playback_allowed: true
session_action: play
session_reason: ready
selected_order: 0
selected_content_type: image/png
selected_duration_ms: 5000
```

### Пример вывода (blocked)

```
event_type: blocked
event_status: draft
playback_allowed: false
session_action: stop
session_reason: safety_blocked
```

**Не выводится:** filename, manifest_item_id, sha256, absolute paths, media bytes,
customer/payment/card/receipt details.

**Следующий шаг:** CLI event-dry-run или PoP draft writer design.

## CLI: `event-dry-run`

```bash
cd apps/kso_player

# Построить in-memory event draft
python3 -m kso_player.cli event-dry-run --root /tmp/kso-agent-root --state idle

# Help
python3 -m kso_player.cli event-dry-run --help
```

**Важно:** это только in-memory draft. НЕ пишет PoP, НЕ пишет JSONL, НЕ отправляет в backend.
State передаётся вручную, реальное состояние КСО не читается.

### Пример вывода (idle + ready)

```
playlist_ready: true
playback_allowed: true
simulation_status: would_play
event_type: would_play
event_status: draft
session_action: play
session_reason: ready
selected_order: 0
selected_content_type: image/png
selected_duration_ms: 5000
```

### Пример вывода (payment + ready)

```
playlist_ready: true
playback_allowed: false
simulation_status: blocked
event_type: blocked
event_status: draft
session_action: stop
session_reason: safety_blocked
```

### Exit codes (event-dry-run)

| Код | Значение |
|---|---|
| 0 | event_type=would_play |
| 1 | event_type=blocked/not_ready/error |
| 2 | Invalid CLI args |

## PoP Local Writer Design

📝 **Mini-design создан:** `docs/pop_local_writer_design.md`. Описывает безопасную локальную запись PoP/events в `pop/pending/player_events.jsonl`. Writer пишет только локально, не отправляет в backend. Sidecar будет забирать события отдельным шагом.

## PoP Local Writer Core

📝 **Реализован:** `pop_writer.py`. Безопасный append-only JSONL writer для KSO Player.

### `write_pop_event(root, event_draft, safety_state, now=None) -> PopWriteResult`

- Строит safe JSONL record из `PlaybackEventDraft`
- Валидирует safety_state (только 9 допустимых состояний)
- Проверяет forbidden substrings во всех строковых значениях
- Создаёт `pop/pending/` при необходимости
- Пишет одну JSON-строку + `\n` в `player_events.jsonl`
- flush + fsync после каждой записи
- Fail silent: некорректная запись → skipped, ошибка диска → error (не крашит)

### Пример JSONL записи

```json
{"created_at":"...","duration_ms":5000,"ended_at":"...","event_status":"draft",
"event_type":"would_play","playback_allowed":true,"result":"would_play",
"safety_state":"idle","schema_version":1,"selected_content_type":"image/png",
"selected_order":0,"session_action":"play","session_reason":"ready","started_at":"..."}
```

**Это ещё НЕ sidecar pickup и НЕ backend send.** Sidecar будет забирать события отдельным шагом run-cycle. CLI появится отдельным шагом.

## CLI: `pop-write`

```bash
cd apps/kso_player

# Построить event draft + записать в локальный JSONL
python3 -m kso_player.cli pop-write --root /tmp/kso-agent-root --state idle

# Help
python3 -m kso_player.cli pop-write --help
```

**Важно:** это локальная запись JSONL. НЕ отправляет в backend, НЕ делает sidecar pickup, НЕ ротирует sent/quarantine.
State передаётся вручную, реальное состояние КСО не читается.

### Pipeline

```
build_playlist → decide_playback_safety → simulate_playback_step
  → build_playback_event_draft → write_pop_event → safe output
```

### Пример вывода (idle + ready)

```
playlist_ready: true
playback_allowed: true
simulation_status: would_play
event_type: would_play
event_status: draft
pop_write_status: written
pop_write_reason: written
line_size_bytes: 312
```

### Пример вывода (payment + ready)

```
playlist_ready: true
playback_allowed: false
simulation_status: blocked
event_type: blocked
event_status: draft
pop_write_status: written
pop_write_reason: written
```

### Exit codes (pop-write)

| Код | Значение |
|---|---|
| 0 | JSONL event written (включая blocked/not_ready) |
| 1 | write skipped/error |
| 2 | Invalid CLI args |

### Файл

Пишет `{root}/pop/pending/player_events.jsonl` (append-only, flush + fsync).

### File Lock (🔒 26.28)

`pop-write` использует lock-файл `pop/pending/player_events.lock` для защиты от конфликтов с будущей sidecar rotation:

- Lock создаётся атомарно (`O_CREAT | O_EXCL`) перед записью
- Lock удаляется после записи (даже при ошибке — `finally` блок)
- Если lock уже занят → запись skipped, reason=`lock_unavailable`
- Lock marker v2 JSON: `{"schema_version":2, "component":"player", "operation":"pop_write", "created_at_utc":"ISO8601", "pid":NNN, "boot_id_hash":"sha256_hex"}`
- `pid` и `boot_id_hash` — internal only, never logged
- v1 lock (`"locked\n"`) → detect-only / lock_unavailable, never deleted
- Stale lock cleanup — будущий отдельный шаг (27.3 design)

---

## KSO Player Display Cycle PoP Core

🎬 **Реализован:** `display_cycle.py` + CLI `display-cycle-once` (20 тестов).

Связывает player render decision с локальной записью Proof of Play.

### `run_kso_display_cycle_once(root, confirm_pop_write=False) -> KsoDisplayCycleResult`

Шаги:
1. `build_kso_render_plan()` — gate + playlist + safety + session
2. Если render → gate (state) + `simulate_playback_step()` + `build_playback_event_draft()`
3. Если `confirm_pop_write=True` → `write_pop_event()` → локальный JSONL

### Ключевое правило: PoP НЕ пишется без `confirm_pop_write=True`

По умолчанию `confirm_pop_write=False` → только render decision, **PoP не пишется**.

### Когда PoP пишется

Только при ВСЕХ условиях:
- `state = idle` (через `state/kso_state.json`)
- State fresh (≤ stale_seconds)
- Manifest: KSO safe body (без gateway wrapper)
- MediaRef: safe (media/current/slot-NNN)
- Media: файл существует
- ContentType: поддерживаемый (image/png, image/jpeg, video/mp4)
- DurationMs: валидный (≥ 0)
- `confirm_pop_write=True`

### Что считается completed PoP

**Это core-level PoP integration, НЕ final production proof.**
Future Chromium runtime loop должен вызывать display cycle **только после
истечения display duration**. Сейчас это core contract — simulated completion,
без реального browser pixel signal.

### Draft vs Completed

- `display-cycle-once` → пишет **draft** PoP (`event_status=draft`) — sidecar видит CLASS_DRAFT, не eligible
- `display-complete-once` → пишет **completed** PoP (`event_status=completed`) — sidecar видит CLASS_ELIGIBLE (с manifest + media), готов к send

### CLI

```bash
# Только render decision (PoP НЕ пишется)
python3 -m kso_player.cli display-cycle-once --root /tmp/kso-root

# Render + draft PoP запись
python3 -m kso_player.cli display-cycle-once --root /tmp/kso-root --confirm-pop-write

# Только render decision (completed PoP НЕ пишется)
python3 -m kso_player.cli display-complete-once --root /tmp/kso-root

# Render + completed PoP запись
python3 -m kso_player.cli display-complete-once --root /tmp/kso-root --confirm-display-completed
```

### Safe output

```
status: ok
render_ready: true
render_action: render
pop_write_requested: false
pop_written: false
completed_pop_write_requested: false
completed_pop_written: false
reason: render_ready_no_pop_confirm
```

Запрещено: paths, mediaRef values, raw JSON, IDs, hashes, backend URLs, secrets, stacktrace.

### Что НЕ делается

- ❌ PoP не пишется без `confirm-pop-write`
- ❌ Backend не вызывается
- ❌ Chromium не запускается
- ❌ Systemd не используется
- ❌ Sidecar не трогается
- ❌ kso_state.json НЕ пишется (read-only из `runtime_gate`)

## KSO Player Runtime Gate

🚦 **Реализован:** `runtime_gate.py`. Безопасное read-only ядро принятия решения play/hold.

### `evaluate_kso_runtime_gate(root, stale_seconds=30) -> KsoRuntimeGateResult`

- Читает `state/kso_state.json` (НЕ пишет)
- Writer: **будущий UKM 4 State Adapter**
- Player — read-only consumer

### Правила

| Условие | play_allowed | action |
|---|---|---|
| state=`idle` + JSON valid + timestamp fresh | **true** | play |
| Любое не-idle состояние | false | hold |
| Missing state file | false | hold |
| Invalid JSON / schema mismatch | false | hold |
| Invalid/missing timestamp | false | hold |
| Stale timestamp (>30s) | false | hold |
| Future timestamp | false | hold |
| Read failure | false | hold |

### Что НЕ реализовано

- ❌ Chromium kiosk launch
- ❌ UI / window
- ❌ systemd unit
- ❌ State adapter (writer)

---

## KSO Player Local Playback Decision

🎛 **Реализован:** `runtime_decision.py`. Полный пайплайн принятия решения play/hold.

### `evaluate_kso_playback_runtime_decision(root, stale_seconds=30)`

Трёхшаговая цепочка:
1. **Runtime gate** — читает `state/kso_state.json` → idle + fresh?
2. **Local content** — `build_playlist()` → manifest + media готовы?
3. **Session/safety** — `decide_playback_safety()` + `select_next_item()` → есть playable item?

### Результат

| Условие | play_allowed | reason |
|---|---|---|
| idle + контент готов + item выбран | **true** | `ready_to_play` |
| Не-idle / stale / invalid state | false | `state_gate_hold` |
| Manifest/media отсутствует | false | `local_content_not_ready` |
| Safety/session не разрешает | false | `session_or_safety_hold` |

### pop_event_should_be_written

- `true` — только когда `play_allowed=true`
- Флаг решения — **сам PoP event пока не пишется** (следующий шаг интеграции)

---

## KSO Player Local Render Plan

🖼 **Реализован:** `render_plan.py`. План отображения для будущего Chromium-рендерера.

### `build_kso_render_plan(root, stale_seconds=30) -> KsoRenderPlanResult`

Строится поверх runtime decision:
1. Runtime decision → play_allowed?
2. Если да → selected item → media_type (image/video/unknown) + duration_bucket
3. `render_action=render` или `hold`

### Render

| Условие | render_action | media_type |
|---|---|---|
| idle + image/png | render | image |
| idle + image/jpeg | render | image |
| idle + video/mp4 | render | video |

### Hold

| Причина | reason |
|---|---|
| Non-idle / stale state | `decision_hold` |
| Missing manifest | `decision_hold` |
| audio/text/application | `unsupported_media_type` |
| No selected item | `no_selected_item` |

### Duration buckets

- `short` — < 10s
- `medium` — 10–60s
- `long` — > 60s

### Внутренние поля (repr=False, не выводятся)

- `_selected_item` — PlayerPlaylistItem
- `_duration_seconds` — float

---

## KSO Player Local HTML Shell

🧱 **Реализован:** `player_shell/` — статический HTML/CSS/JS для будущего Chromium kiosk.

### Состав

| Файл | Назначение |
|---|---|
| `index.html` | HTML shell с CSP `connect-src 'none'` |
| `styles.css` | Стили для зоны 1440×1080 |
| `player.js` | `window.KsoPlayerShell` API |

### Режимы

- **Hold** — нейтральный экран «Advertising temporarily unavailable»
- **Render** — рекламная зона с placeholder

### JS API

```js
window.KsoPlayerShell.setHold("hold")           // блокировка
window.KsoPlayerShell.setRenderPlan(plan)        // render = {mediaType, durationBucket}
window.KsoPlayerShell.clear()                    // сброс
```

### Безопасность

- Полностью локальный — нет внешних URL, CDN, analytics
- CSP: `default-src 'self'`, `connect-src 'none'`, `form-action 'none'`
- Нет fetch/XHR/WebSocket/iframe/form
- Никогда не принимает: paths, filenames, IDs, хеши, auth data
- Shell не знает backend/token/secret

---

## KSO Player Shell Command

🎮 **Реализован:** `shell_command.py`. Мост между render plan и HTML shell.

### Pipeline

```
runtime_gate → runtime_decision → render_plan → shell_command
```

### `build_kso_shell_command(root, stale_seconds=30)`

| Render plan | shell_mode | command | поля |
|---|---|---|---|
| render | render | `setRenderPlan` | mediaType, durationBucket |
| hold (любая причина) | hold | `hold` | — |

### Safe fields только

- `mediaType`: `image` | `video` | `unknown`
- `durationBucket`: `short` | `medium` | `long` | `unknown`

**НЕ передаются:** paths, filenames, media src, manifest IDs, campaign IDs, hashes.

---

## KSO Player Local Shell Snapshot

📦 **Реализован:** `shell_snapshot.py`. Безопасный JSON snapshot поверх shell command.

### Pipeline

```
runtime_gate → runtime_decision → render_plan → shell_command → shell_snapshot
```

### `build_kso_shell_snapshot(root, stale_seconds=30) → KsoShellSnapshotResult`

Строит безопасный JSON snapshot для передачи в `window.KsoPlayerShell.applySnapshot()`.

| Shell command | snapshot_mode | shell_method | payload |
|---|---|---|---|
| `setRenderPlan` | `render` | `setRenderPlan` | `{mediaType, durationBucket}` |
| `hold` | `hold` | `setHold` | `{reason: "hold"}` |

### Serialized JSON (render)

```json
{"schemaVersion":1,"mode":"render","method":"setRenderPlan","payload":{"mediaType":"image","durationBucket":"short"}}
```

### Serialized JSON (hold)

```json
{"schemaVersion":1,"mode":"hold","method":"setHold","payload":{"reason":"hold"}}
```

### Safe fields только

- `schemaVersion`: 1
- `mode`: `hold` | `render`
- `method`: `setHold` | `setRenderPlan`
- `payload`: `{mediaType, durationBucket}` или `{reason: "hold"}`

**НЕ передаются:** media src, paths, filenames, manifest IDs, campaign IDs, creative IDs, schedule item IDs, hashes, timestamps, raw JSON.

### `serialize_kso_shell_snapshot(result) → str`

Безопасная JSON-сериализация. Fallback: если в результате детектируется forbidden substring — возвращает minimal safe hold snapshot.

### `format_kso_shell_snapshot_result(result) → str`

Безопасный human-readable вывод. Никогда не содержит путей, имён файлов, ID, хешей.

### JS API: `window.KsoPlayerShell.applySnapshot(snapshot)`

Добавлена в `player.js`. Принимает safe JSON snapshot:

- Валидирует `schemaVersion`, `mode`, `method`, `payload`
- `mode=hold` / `method=setHold` → `setHold("hold")`
- `mode=render` / `method=setRenderPlan` → `setRenderPlan(payload)`
- Invalid / extra keys / unknown → `setHold` (fail-closed)
- **НЕ использует:** `eval`, `new Function`, `innerHTML`, `fetch`, `XMLHttpRequest`, `WebSocket`, external URLs

### Что НЕ реализовано

- ❌ Real media rendering (mediaRef — alias only, no src injection yet)
- ❌ Chromium kiosk launch
- ❌ Real media rendering
- ❌ PoP write из snapshot

---

## KSO Player Safe Local Media Reference

🔗 **Реализован:** `media_reference.py`. Безопасный локальный media alias для shell.

### Pipeline

```
render_plan._selected_item → media_reference → mediaRef в shell_snapshot
```

### `build_kso_safe_media_reference(selected_item) → KsoSafeMediaReferenceResult`

Строит безопасный локальный alias из `PlayerPlaylistItem`:

- **Формат:** `media/current/slot-{order:03d}` (например `media/current/slot-000`)
- **НЕ раскрывает:** реальный filename, manifest_item_id, campaign_id, creative_id, sha256
- **НЕ является:** абсолютным путём, backend URL, ID, хешем

### Whitelist validation

| Правило | Допустимо | Запрещено |
|---|---|---|
| Символы | `a-z`, `0-9`, `/`, `_`, `-` | Всё остальное |
| Unsafe substrings | — | `..`, `~`, `\`, `://`, `file:`, `http:`, `https:`, `%2e`, `%2f` |

### Обновлённый shell snapshot (render)

```json
{"schemaVersion":1,"mode":"render","method":"setRenderPlan","payload":{"mediaType":"image","durationBucket":"short","mediaRef":"media/current/slot-000"}}
```

### Hold snapshot (без изменений)

```json
{"schemaVersion":1,"mode":"hold","method":"setHold","payload":{"reason":"hold"}}
```

### Если media reference unsafe → hold

- Неподдерживаемый media type → `unsafe_media_reference`
- Нет selected item → `unsafe_media_reference`
- Whitelist validation fail → `unsafe_media_reference`

### JS API: mediaRef в applySnapshot

- `payload.mediaRef` — разрешён для render, опционален
- Whitelist: `^[a-z0-9/_-]+$`
- Отклоняет unsafe substrings → `setHold`
- **НЕ вставляет** `<img src>` / `<video src>` — только alias в `currentPlan.mediaRef`
- **НЕ использует:** `innerHTML`, `eval`, `fetch`, `XMLHttpRequest`, `WebSocket`

### Что НЕ реализовано

- ❌ Chromium kiosk launch
- ❌ PoP write из snapshot

---

## KSO Player Shell Safe Media Renderer

🖥️ **Реализован:** безопасный DOM-рендеринг в `player.js`. Shell отображает `<img>` / `<video>` из safe mediaRef.

### Как работает

`setRenderPlan(plan)` с валидным mediaRef:

| mediaType | Создаёт | Атрибуты |
|---|---|---|
| `image` | `<img>` (document.createElement) | `src`, `alt` |
| `video` | `<video>` (document.createElement) | `src`, `muted`, `autoplay`, `loop`, `playsinline` |

### Безопасность DOM

- Только `document.createElement()` + `setAttribute()` + `appendChild()`
- Очистка media slot через `replaceChildren()` (без innerHTML)
- **НЕ использует:** `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval`, `new Function`, `fetch`, `XMLHttpRequest`, `WebSocket`
- `src` — только из уже провалидированного whitelist mediaRef

### CSS

- `img`/`video`: `max-width: 100%`, `max-height: 100%`, `object-fit: contain`
- `background: #000` на media slot
- Никаких внешних ресурсов, `@import`, remote fonts

### Что НЕ реализовано

- ❌ Проверка существования файла (не открываем, не читаем)
- ❌ Chromium kiosk launch
- ❌ Backend / HTTP / PoP write

---

## KSO Player Shell Bootstrap

🚀 **Реализован:** `bootstrap.js` + `bootstrap_snapshot.js`. Автостарт shell при загрузке страницы.

### Script include order

```html
<script src="player.js"></script>              <!-- 1. API -->
<script src="bootstrap_snapshot.js"></script>   <!-- 2. Default snapshot -->
<script src="bootstrap.js"></script>            <!-- 3. Apply snapshot -->
```

### Как работает

1. `player.js` создаёт `window.KsoPlayerShell`
2. `bootstrap_snapshot.js` устанавливает `window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT` (default: hold)
3. `bootstrap.js` проверяет snapshot → `applySnapshot()` или `setHold("hold")`
4. Default snapshot — safe hold (без mediaRef, без render)

### Production model

- В `/opt` лежит **default hold snapshot** (`bootstrap_snapshot.js` — безопасный, без mediaRef)
- В `/var/lib/verny/kso/runtime/player_shell/` future writer будет атомарно заменять этот файл
- Если writer ещё не запущен — shell остаётся в hold
- Writer никогда не пишет в `/opt` — только в runtime copy

### Default snapshot

```js
window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT = {
  schemaVersion: 1, mode: "hold", method: "setHold",
  payload: { reason: "hold" }
};
```


### Безопасность

- **НЕ содержит:** `fetch`, `XMLHttpRequest`, `WebSocket`, `eval`, `new Function`, `innerHTML`
- **НЕ содержит:** external URLs, backend, token, secret, password
- **НЕ пишет** файлы, НЕ читает media bytes, НЕ делает HTTP
- CSP: `connect-src 'none'`

### Что НЕ реализовано

- ❌ Dynamic snapshot writer (файл snapshot не создаётся на этом шаге)
- ❌ Fetch JSON / external script
- ❌ Chromium kiosk launch

---

## KSO Player Runtime Shell Workspace

📂 **Реализован:** `runtime_shell_workspace.py`. Подготовка runtime-копии HTML shell.

### `prepare_kso_runtime_shell_workspace(source_shell_dir, runtime_shell_dir)`

Копирует whitelist shell-файлы из immutable source в mutable runtime директорию.

### Copy whitelist (5 файлов)

| Файл | Назначение |
|---|---|
| `index.html` | HTML shell |
| `styles.css` | Стили |
| `player.js` | `window.KsoPlayerShell` API |
| `bootstrap_snapshot.js` | Default hold snapshot |
| `bootstrap.js` | Автостарт |

### Игнорируются

- Extra files (README.txt, .env, .hidden и т.д.)
- Subdirectories
- Unknown files
- .token, .secret, .key, .pem, .log
- manifest, media, pop, state files

### Atomic copy

Каждый файл копируется атомарно: `.tmp → flush/fsync → rename → fsync dir`

### Source shell НЕ модифицируется

Source shell остаётся неизменяемым — все операции на runtime copy.

### Что НЕ реализовано

- ❌ Chromium kiosk launch
- ❌ Dynamic snapshot writer
- ❌ Systemd / service

---

## KSO Player Runtime Snapshot Writer

📝 **Реализован:** `runtime_snapshot_writer.py` + CLI `shell-snapshot-write`.

### Pipeline

```
state/kso_state.json → runtime_gate → runtime_decision →
  render_plan → shell_command → shell_snapshot → bootstrap_snapshot.js
```

### `write_kso_runtime_bootstrap_snapshot(root, runtime_shell_dir, stale_seconds=30)`

Строит текущий shell snapshot и атомарно пишет `bootstrap_snapshot.js`
в runtime shell directory.

**Куда пишет:** `{runtime_shell_dir}/bootstrap_snapshot.js`
**Куда НЕ пишет:** `/opt`, state, manifest, media, pop

### Когда hold

| Триггер | |
|---|---|
| Non-idle state | hold |
| Missing state | hold |
| Stale state | hold |
| Missing manifest | hold |
| Unsupported media type | hold |

### Когда render

| Условие | |
|---|---|
| idle + image + manifest ready | render (`setRenderPlan` + mediaRef) |
| idle + video + manifest ready | render (`setRenderPlan` + mediaRef) |

### Atomic write

```
bootstrap_snapshot.js.tmp → flush/fsync → rename → fsync directory
```

### CLI

```bash
python3 -m kso_player.cli shell-snapshot-write \
  --root /tmp/kso-root \
  --runtime-shell-dir /tmp/kso-runtime/player_shell
```

| Exit code | |
|---|---|
| 0 | Snapshot записан |
| 1 | Warning / error |
| 2 | Invalid args |

### Что НЕ реализовано

- ❌ Chromium kiosk launch

---

## KSO Player Local Visual Demo Prepare

🧪 **Реализован:** `local_visual_demo_prepare.py` + CLI `local-demo-prepare`.

Это первый вертикальный demo prepare: полная подготовка runtime shell → media symlink alias → bootstrap snapshot.
После выполнения команды runtime shell готов для ручного запуска Chromium.

### Pipeline

```
source shell → atomic copy → runtime shell
state → gate → decision → render plan → shell snapshot → bootstrap_snapshot.js
render plan → media filename → safe symlink → media/current/slot-XXX
```

### `prepare_kso_local_visual_demo(root, source_shell_dir, runtime_shell_dir, stale_seconds=30)`

1. **Workspace** — атомарное копирование 5 whitelist файлов из source в runtime
2. **Snapshot** — построение shell snapshot через полный пайплайн (state → gate → ... → snapshot)
3. **Media alias** — для render: safe symlink `media/current/slot-{order:03d}` → реальный media файл
4. **Write** — атомарная запись `bootstrap_snapshot.js` в runtime shell

### Когда Render

| Условие | |
|---|---|
| idle + image + manifest ready | render + media alias ready |
| idle + video + manifest ready | render + media alias ready |

### Когда Hold

| Условие | |
|---|---|
| Non-idle / stale / missing state | hold |
| Missing manifest | hold |
| Unsupported media type | hold |
| Media alias не удалось создать | **hold** (safe fallback) |
| Source shell missing | error |

### Media alias

- **Формат:** `{runtime_shell_dir}/media/current/slot-{order:03d}`
- **Тип:** safe symlink → реальный файл в `{root}/media/current/`
- **Безопасность:** alias name только из safe mediaRef, путь валидируется на отсутствие `..`, `/`, `\\`
- Если source media нельзя безопасно определить → hold snapshot

### CLI

```bash
python3 -m kso_player.cli local-demo-prepare \
  --root /tmp/kso-root \
  --source-shell-dir /opt/verny/kso/player_shell \
  --runtime-shell-dir /var/lib/verny/kso/runtime/player_shell
```

| Exit code | |
|---|---|
| 0 | Demo prepared |
| 1 | Error |
| 2 | Invalid args |

### Atomic write

```
bootstrap_snapshot.js.tmp → flush/fsync → rename → fsync directory
```

### Что НЕ реализовано

- ❌ Chromium kiosk launch
- ❌ Systemd / service
- ❌ PoP write
- ❌ State adapter / kso_state.json write
- ❌ Backend / auth / secret / media bytes

---

## KSO Player Guarded Local Chromium Demo Runner

🚀 **Реализован:** `local_chromium_demo_runner.py` + CLI `local-chromium-demo`.

Guarded demo runner: готовит runtime shell + snapshot + media alias → при явном `--confirm-launch` запускает Chromium.

### Pipeline

```
prepare demo → build Chromium command (internal)
  ├── confirm_launch=false → launch_ready=true, launched=false
  └── confirm_launch=true  → subprocess.Popen(command), launched=true
```

### `prepare_and_maybe_launch_kso_local_chromium_demo(...)`

| Параметр | |
|---|---|
| `root` | Agent root path |
| `source_shell_dir` | Immutable shell source (e.g. `/opt`) |
| `runtime_shell_dir` | Mutable runtime shell |
| `chromium_bin` | Chromium binary (default: `chromium`) |
| `confirm_launch` | Запускать Chromium? (по умолчанию `false`) |
| `process_launcher` | Injectable callable (для тестов) |

### Guard

По умолчанию `confirm_launch=false` — Chromium **НЕ** запускается.
Только prepare + `launch_ready=true`, `launched=false`.
Запуск — исключительно при явном `--confirm-launch`.

### Chromium command

- **Linux only**, список аргументов (не shell string)
- `--app=file://` с локальным index.html
- `--window-size=1440,1080 --window-position=0,0`
- `--no-first-run --disable-background-networking --disable-sync --disable-translate --disable-default-apps`
- `--user-data-dir` в runtime shell / chromium-profile
- **Запрещены:** `--disable-web-security`, `--allow-file-access-from-files`, `shell=True`

### CLI

```bash
# Только prepare (без запуска)
python3 -m kso_player.cli local-chromium-demo \
  --root /tmp/kso-root \
  --source-shell-dir /opt/verny/kso/player_shell \
  --runtime-shell-dir /var/lib/verny/kso/runtime/player_shell \
  --chromium-bin chromium

# С запуском Chromium
python3 -m kso_player.cli local-chromium-demo \
  ... \
  --confirm-launch
```

| Exit code | |
|---|---|
| 0 | Demo prepared (или launched) |
| 1 | Error |
| 2 | Invalid args |

### Безопасность вывода

CLI и result НЕ содержат: пути, file URL, полную команду, mediaRef, IDs, raw JSON, stacktrace.

### Что НЕ реализовано

- ❌ Systemd / production service
- ❌ State adapter
- ❌ PoP write
- ❌ Backend / auth / secret / media bytes

---

## First Local Visual Smoke Demo

🧪 **Реализован:** `local_demo_fixture.py` + CLI `local-demo-fixture`.

Первый локальный smoke demo КСО-плеера: генератор demo root + полный smoke flow
до render-снапшота.

### Demo fixture

`prepare_kso_local_demo_fixture(root)` создаёт минимальный demo root
в **KSO safe manifest формате** (v1+):

| Файл | Содержимое |
|---|---|
| `state/kso_state.json` | idle state от будущего UKM 4 adapter |
| `manifest/current_manifest.json` | KSO safe format: schemaVersion, channel=kso, items[].mediaRef |
| `media/current/slot-000` | Валидный 1×1 синий PNG (mediaRef target) |

Манифест использует KSO safe format — **без** filename, sha256, manifest_item_id.
MediaRef: `media/current/slot-000`.

Это **НЕ** production state adapter. Demo-only: имитирует idle state.

### Smoke flow

```bash
# 1. Создать demo root
python3 -m kso_player.cli local-demo-fixture --root /tmp/kso-demo-root

# 2. Подготовить runtime shell + snapshot (без запуска Chromium)
python3 -m kso_player.cli local-chromium-demo \
  --root /tmp/kso-demo-root \
  --source-shell-dir ./player_shell \
  --runtime-shell-dir /tmp/kso-demo-runtime/player_shell \
  --chromium-bin chromium
# → prepared: true, launch_ready: true, launched: false

# 3. Опционально: запустить Chromium
python3 -m kso_player.cli local-chromium-demo \
  --root /tmp/kso-demo-root \
  --source-shell-dir ./player_shell \
  --runtime-shell-dir /tmp/kso-demo-runtime/player_shell \
  --chromium-bin chromium \
  --confirm-launch
# → launched: true (Chromium 1440×1080, левая зона)
```

### Verify pipeline

```bash
# Проверить, что snapshot будет render:
python3 -m kso_player.cli playlist-status --root /tmp/kso-demo-root
# → playlist_ready: true
```

### Что НЕ реализовано

- ❌ Systemd / production service
- ❌ Production state adapter (UKM 4)
- ❌ PoP write
- ❌ Backend / auth / secret / media bytes

---

## Local Manifest Format

Player поддерживает два формата манифеста:

### KSO Safe Manifest (v1+) — основной

Формат, получаемый от backend gateway через sidecar:

```json
{
  "schemaVersion": 1,
  "generatedAt": "ISO8601",
  "channel": "kso",
  "storeCode": "safe_code",
  "deviceCode": "safe_code",
  "items": [
    {
      "slotOrder": 0,
      "contentType": "image/png",
      "durationMs": 5000,
      "mediaRef": "media/current/slot-000",
      "validFrom": "ISO8601",
      "validTo": "ISO8601"
    }
  ]
}
```

Player:
- Читает `media/current/slot-{slotOrder:03d}` как локальный media alias.
- Проверяет существование файла — без sha256, без чтения bytes.
- **НЕ** принимает gateway wrapper (`{"status": "...", "manifest": {...}}`) — уходит в hold.

### Legacy Manifest — backward compat

Старый формат (demo fixture до шага 28.3):

```json
{
  "manifest_id": "...",
  "schema_version": 1,
  "items": [
    {
      "manifest_item_id": "UUID",
      "order": 0,
      "content_type": "image/png",
      "duration_ms": 5000,
      "filename": "ad_demo.png",
      "sha256": "..."
    }
  ]
}
```

Player поддерживает оба формата. Детекция автоматическая по наличию `mediaRef` vs `filename`.

### Future Sidecar Delivery

Sidecar скачивает gateway response (`GET /api/device-gateway/manifest/current`).
В production sidecar сохраняет **только** `response["manifest"]` (safe manifest body)
в `manifest/current_manifest.json`. Player никогда не получает gateway wrapper.

---

## Что НЕ работает (будет отдельными шагами)

- ❌ UI / окно / overlay
- ❌ Playback (воспроизведение)
- ❌ Интеграция с реальным КСО (state reading)
- ❌ PoP (proof-of-play)
- ❌ Backend / auth / secret / token
- ❌ HTTP / сеть
- ❌ Запись / удаление / перемещение файлов
- ❌ Loop / service / systemd
- ❌ Чтение state КСО

## Безопасность

Player — **read-only**, safety gate — **pure logic**:

- Читает только `manifest/current_manifest.json` и `media/current/` (playlist)
- Safety gate не читает и не пишет файлы
- Не делает HTTP
- Не читает secret / token / config / device_code / backend URL
- Не пишет / не удаляет / не перемещает файлы
- Не возвращает absolute paths, media_path, creatives/, backend URLs
- Вывод только агрегированный — без полного manifest и media bytes
- Customer/payment/receipt data не хранится и не выводится

## KSO End-to-End Local Delivery Smoke

🧪 **E2E интеграционный тест:** `../kso_sidecar_agent/tests/test_kso_e2e_local_delivery_smoke.py` (12 тестов).

Проверяет полный локальный путь доставки рекламы на КСО без реального backend, Chromium, systemd и PoP:

```
fake gateway → sidecar sync → local manifest/current_manifest.json
+ media/current/slot-NNN → player: gate → playlist → render_plan → shell_snapshot
```

### Happy path

Sidecar `sync_kso_manifest_and_media()` + player pipeline:
- Fake gateway → `status=served` + KSO safe manifest + PNG bytes
- Sidecar пишет `manifest/current_manifest.json` (safe body, без wrapper)
- Sidecar пишет `media/current/slot-000`
- Player `evaluate_kso_runtime_gate()` → `play_allowed` (state=idle)
- Player `build_playlist()` → `ready=true`
- Player `build_kso_render_plan()` → `render_action=render`
- Player `build_kso_shell_snapshot()` → `snapshot_mode=render`, `shell_method=setRenderPlan`

### Что НЕ вызывается

- ❌ Real backend (fake gateway + fake media responses)
- ❌ Chromium запуск
- ❌ Systemd
- ❌ PoP event запись
- ❌ kso_state.json пишется только test fixture

## How to see KSO ad locally

🖥 **Реализован:** `visible-runtime-once` CLI — одна команда для локального показа рекламы.

### Quick start

```bash
# Подготовить demo fixture + показать в Chromium
python3 -m kso_player.cli visible-runtime-once \
  --root /tmp/kso-demo-root \
  --source-shell-dir ./player_shell \
  --runtime-shell-dir /tmp/kso-demo-runtime/player_shell \
  --chromium-bin chromium \
  --prepare-demo-fixture \
  --confirm-launch
```

### Без запуска Chromium (prepare only)

```bash
python3 -m kso_player.cli visible-runtime-once \
  --root /tmp/kso-demo-root \
  --source-shell-dir ./player_shell \
  --runtime-shell-dir /tmp/kso-demo-runtime/player_shell \
  --chromium-bin chromium \
  --prepare-demo-fixture
```

Вывод:
```
status: ok
fixture_ready: true
render_ready: true
shell_prepared: true
snapshot_written: true
launch_ready: true
launched: false
reason: ready
```

### Как это работает

1. `--prepare-demo-fixture` → создаёт idle state + KSO safe manifest + media
2. Player строит render plan → shell snapshot → `bootstrap_snapshot.js`
3. Runtime shell копируется из source через whitelist
4. Chromium command строится с безопасными флагами (`--app=file://...`)
5. `--confirm-launch` → Chromium запускается через subprocess.Popen

### Важные замечания

- Это **local visual runtime** — не production systemd сервис
- **НЕ пишет completed PoP автоматически** (для этого отдельная команда `display-complete-once`)
- Production KSO будет использовать Linux + Chromium kiosk + systemd в будущем шаге
- Chromium открывает **только локальный runtime shell** — без внешних URL, без сети

## Структура

```
kso_player/
  __init__.py
  cli.py           # CLI: playlist-status
  playlist.py      # PlayerPlaylistItem, PlayerPlaylist, build_playlist()
  safety.py        # PlaybackSafetySnapshot, PlaybackSafetyDecision, decide_playback_safety()
  session.py       # PlaybackSessionState, PlaybackSessionDecision, select_next_item()
  safe_output.py   # format_playlist_summary(), format_safety_decision(), format_session_decision()
tests/
  test_playlist.py
  test_cli.py
  test_safety.py
  test_safety_cli.py
  test_session.py
  test_playback_dry_run_cli.py
  test_simulate_step_cli.py
  test_simulator.py