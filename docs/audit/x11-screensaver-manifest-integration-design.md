# X11 Screensaver — Manifest Creative Integration Design

> **Статус:** 📐 Design (38.2)
>
> Дата: 2026-06-24
> Ревизия: 1
>
> **Назначение:** Связать доказанный X11 guarded screensaver runner с safe manifest/player creative pipeline.
> Runner получает safe creative payload вместо красного proof-screen.
> **НЕ:** физический запуск на КСО, создание X11 окон, изменение УКМ5.

---

## 1. Существующие компоненты (до 38.2)

| Компонент | Модуль | Назначение |
|---|---|---|
| `PlayerPlaylistItem` | `playlist.py` | Safe playlist item: media_ref, slot_order, content_type, duration_ms |
| `PlayerPlaylist` | `playlist.py` | Playlist: ready/items/reason |
| `KsoRenderPlanResult` | `render_plan.py` | Render plan: render_action, media_type, duration_bucket |
| `PlaybackEventDraft` | `events.py` | Event draft: would_play, blocked, not_ready |
| `ScreensaverRunResult` | `x11_screensaver_runner.py` | Runner result: visible, state, focus_restored |
| `x11_screensaver_proof_py36.py` | `scripts/` | Physical KSO proof harness (Python 3.6) |

---

## 2. Новые компоненты (38.2)

| Компонент | Модуль | Назначение |
|---|---|---|
| `ScreensaverCreativePayload` | `screensaver_creative.py` | Safe creative payload для runner: creative_code, media_ref, content_type, duration_ms |
| `build_screensaver_creative()` | `screensaver_creative.py` | Adapter: `PlayerPlaylistItem` → `ScreensaverCreativePayload` |
| `build_screensaver_creative_from_playlist()` | `screensaver_creative.py` | Playlist-level adapter: pick item by slot_order |
| `validate_screensaver_creative()` | `screensaver_creative.py` | Safety validator: content_type, forbidden patterns |
| `decide_creative_visibility()` | `screensaver_creative.py` | Visibility: idle + valid creative + kill inactive → visible |
| `ScreensaverPoPDraft` | `screensaver_creative.py` | Safe local PoP event: screen_visible/hidden, creative_code |
| `build_screensaver_pop_draft()` | `screensaver_creative.py` | Event builder: creative → safe PoP draft |
| `validate_screensaver_pop_safety()` | `screensaver_creative.py` | PoP safety check |

---

## 3. Data flow

```
manifest/current_manifest.json
  → build_playlist() → PlayerPlaylist
    → build_screensaver_creative_from_playlist() → ScreensaverCreativePayload
      → validate_screensaver_creative() → valid/invalid
      → decide_creative_visibility() → visible/hidden
        → (future) X11 screensaver runner.show(creative)
        → build_screensaver_pop_draft() → ScreensaverPoPDraft
```

---

## 4. Safe Creative Payload

### 4.1 Разрешённые поля

| Поле | Тип | Описание |
|---|---|---|
| `creative_code` | str | Stable identifier (не UUID), например `scr-slot-000` |
| `media_ref` | str | Local-safe alias: `slot-000` (без пути) |
| `content_type` | str | `image/png`, `image/jpeg`, `video/mp4`, или `test` |
| `duration_ms` | int | 1 000 – 120 000 (clamped) |
| `slot_order` | int | Порядковый номер в playlist |
| `valid_from` | str? | ISO8601 UTC, опционально |
| `valid_to` | str? | ISO8601 UTC, опционально |

### 4.2 Запрещённые поля/паттерны

```
UUID, manifest_item_id, filename, sha256
file_path, storage_ref, minio, s3://
backend_url, backend_host, backend_port
token, secret, api_key, password, jwt, bearer
device_secret, device_token, access_token
receipt, payment, fiscal, customer, card, pan
barcode, scanner, key_value, event_key, event_code
http://, https://, file://, 127.0.0.1, localhost
/mnt/, /media/, /var/lib/
```

---

## 5. Visibility Rules

| Приоритет | Условие | Результат |
|---|---|---|
| P0 | kill_switch_active | hidden |
| P0 | state ≠ idle | hidden |
| P1 | playlist empty/not-ready | hidden (fallback) |
| P1 | creative invalid | hidden |
| P1 | creative expired | hidden |
| P2 | idle + valid creative + kill inactive | **visible** |

---

## 6. PoP Event Contract

### 6.1 Event types

| Тип | Описание |
|---|---|
| `screen_visible` | Creative показан на экране |
| `screen_hidden` | Creative скрыт (kill-switch/state/...) |
| `playback_started` | Начало показа creative |
| `playback_completed` | Конец показа creative |

### 6.2 Safe fields

| Поле | Разрешено? |
|---|---|
| `event_type` | ✅ |
| `creative_code` | ✅ |
| `visible` | ✅ |
| `state` | ✅ |
| `kill_switch_active` | ✅ |
| `reason` | ✅ |
| `duration_ms` | ✅ |
| `started_at_utc` | ✅ |
| `ended_at_utc` | ✅ |
| barcode | ❌ |
| scanner_value | ❌ |
| receipt/payment/fiscal | ❌ |
| customer/card/PII | ❌ |
| backend_url/token/secret | ❌ |
| file_path/sha256/minio | ❌ |

---

## 7. Безопасность

- **НЕ отправляется на backend** — PoP draft только локальный
- **НЕ содержит чувствительных данных** — forbidden fields отвергаются на уровне валидации
- **НЕ читает БД УКМ5**
- **НЕ логирует barcode/key payload/scanner input**
- **НЕ создаёт X11 окна** — pure contract модуль

---

## 8. Файлы

- `apps/kso_player/kso_player/screensaver_creative.py` — creative payload, adapter, validator, PoP
- `apps/kso_player/tests/test_screensaver_creative.py` — 98 тестов
- `docs/audit/x11-screensaver-manifest-integration-design.md` — этот документ

## Журнал

### 38.2.1 — Preserve Backend creative_code (2026-06-24)

- `PlayerPlaylistItem.creative_code`: Optional[str] — safe code from backend manifest
- `_parse_kso_safe_item()`: extracts `creativeCode` from manifest item with forbidden-substring check
- `build_screensaver_creative()`: backend creative_code wins; synthetic fallback marked `is_synthetic=True`
- `ScreensaverCreativePayload.is_synthetic`: explicit flag — True only when auto-generated
- +17 тестов: preservation chain, fallback marking, identity rules, PoP
- КСО не менялась. Physical run не запускался.

### 38.2.2 — Sidecar Media Cache Bridge for X11 Runner (2026-06-24)

- Создан `screensaver_media_availability.py`: ScreensaverMediaAvailability, check_screensaver_media_availability()
- Bridge: creative → manifest lookup → media/current/ file check → ready/blocked
- `decide_creative_visibility()`: +`media_availability` gate (3 новых причины скрытия)
- `ScreensaverPoPDraft`: +`media_available` флаг, +`SCREENSAVER_EVENT_BLOCKED`
- `build_screensaver_pop_draft()`: +`media_available` параметр
- Security: symlink rejected BEFORE existence, absolute paths rejected, forbidden substrings
- Synthetic test creatives allowed without real media
- +59 тестов: availability, fallback, forbidden fields, identity, full chain
- КСО не менялась. Physical run/X11/Chromium не запускались.

### 2026-06-24 — Шаг 38.2 (Connect Screensaver Runner to Manifest Creatives)

- Создан `screensaver_creative.py`: ScreensaverCreativePayload, adapter, validator, visibility, PoP
- Adapter: PlayerPlaylistItem → ScreensaverCreativePayload (strips UUID/sha256/paths)
- Validator: content_type only image/video/test, forbidden patterns rejected
- Visibility: idle + valid creative + kill inactive → visible
- PoP: ScreensaverPoPDraft — screen_visible/hidden/playback_started/completed
- +98 тестов: payload, adapter, validation, visibility, PoP safety, integration
- КСО не менялась. Physical run/X11/Chromium не запускались.
