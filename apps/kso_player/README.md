# KSO Player — Core Skeleton

**Статус:** 🏗 Skeleton. Первый безопасный каркас будущего KSO Player.

## Что это

KSO Player — будущий UI-плеер для показа контента на КСО-терминалах.
На этом шаге реализован **только core skeleton**: чтение локального manifest/media,
проверка готовности, построение safe playlist и CLI-команда `playlist-status`.

## Что сейчас работает

- `build_playlist(root)` — построение playlist из локального manifest + media cache
- `format_playlist_summary(playlist)` — safe агрегированный вывод
- `playlist-status` CLI — проверка готовности playlist (read-only)

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

## Что НЕ работает (будет отдельными шагами)

- ❌ UI / окно / overlay
- ❌ Playback (воспроизведение)
- ❌ Интеграция с КСО
- ❌ PoP (proof-of-play)
- ❌ Backend / auth / secret / token
- ❌ HTTP / сеть
- ❌ Запись / удаление / перемещение файлов
- ❌ Loop / service / systemd
- ❌ Чтение state КСО

## Безопасность

Player — **read-only**:

- Читает только `manifest/current_manifest.json` и `media/current/`
- Не делает HTTP
- Не читает secret / token / config / device_code / backend URL
- Не пишет / не удаляет / не перемещает файлы
- Не возвращает absolute paths, media_path, creatives/, backend URLs
- Вывод только агрегированный — без полного manifest и media bytes

## Структура

```
kso_player/
  __init__.py
  cli.py           # CLI: playlist-status
  playlist.py      # PlayerPlaylistItem, PlayerPlaylist, build_playlist()
  safe_output.py   # format_playlist_summary()
tests/
  test_playlist.py
  test_cli.py
```
