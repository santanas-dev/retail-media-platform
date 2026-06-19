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

## Playback Session Core

**In-memory only** — выбор следующего media item для показа.
Не проигрывает media, не использует UI/overlay, не интегрирован с КСО.

### `select_next_item(playlist, safety_decision, state=None)`

Fail-closed логика выбора следующего item:

1. Safety gate не разрешил → блокировка
2. Playlist not ready → блокировка
3. Нет items → блокировка
4. Иначе → выбор по order:
   - Без state: первый item (order=0)
   - С state: item после `current_index`, с зацикливанием

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
```
