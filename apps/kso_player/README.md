# KSO Player — Core Skeleton

**Статус:** 🏗 Skeleton. Первый безопасный каркас будущего KSO Player.

## Что это

KSO Player — будущий UI-плеер для показа контента на КСО-терминалах.
На этом шаге реализован **только core skeleton**: чтение локального manifest/media,
проверка готовности и построение safe playlist.

## Что сейчас работает

- `build_playlist(root)` — построение playlist из локального manifest + media cache
- `format_playlist_summary(playlist)` — safe агрегированный вывод

## Что НЕ работает (будет отдельными шагами)

- ❌ UI / окно / overlay
- ❌ Playback (воспроизведение)
- ❌ Интеграция с КСО
- ❌ PoP (proof-of-play)
- ❌ CLI (следующий шаг — `playlist-status`)
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

## Быстрый старт

```bash
cd apps/kso_player

# Построить playlist
python3 -c "
from kso_player import build_playlist, format_playlist_summary
pl = build_playlist('/tmp/kso-agent-root')
print(format_playlist_summary(pl))
"
```

## Структура

```
kso_player/
  __init__.py
  playlist.py      # PlayerPlaylistItem, PlayerPlaylist, build_playlist()
  safe_output.py   # format_playlist_summary()
tests/
  test_playlist.py
```
