# Mini-Design: Шаг 23 — KSO Player Runtime Contract

**Статус:** ✅ Утверждён (Шаг 23). Реализован в Шаге 23.1.

## 1. Goal

Описать backend-контракт для будущего КСО-плеера / КСО-адаптера: полный lifecycle, все endpoint'ы, правила безопасности, offline-режим, обработка ошибок. **Не реализуем** сам плеер, Android-клиент, frontend, новые endpoints.

## 2. Lifecycle КСО-плеера

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. COLD START                                                   │
│    ├── читает device_code / device_secret из локального хранилища│
│    ├── POST /api/device-gateway/auth/token → JWT                │
│    ├── сохраняет JWT в память (не на диск)                      │
│    └── переходит к WARM LOOP                                    │
│                                                                 │
│ 2. WARM LOOP (каждые N секунд)                                  │
│    ├── POST /api/device-gateway/heartbeat                       │
│    ├── GET /api/device-gateway/config/current (ETag/304)         │
│    ├── GET /api/device-gateway/manifest/current (hash/304)       │
│    ├── для каждого нового manifest_item:                        │
│    │   ├── GET /api/device-gateway/media/{mi_id}/metadata        │
│    │   ├── если sha256 не совпадает с локальным кэшем:           │
│    │   │   └── GET /api/device-gateway/media/{mi_id} (download)  │
│    │   ├── проверяет sha256 скачанного файла                    │
│    │   └── POST /api/device-gateway/media/cache/report          │
│    ├── POST /api/device-gateway/manifest/{mv_id}/apply           │
│    ├── PLAYBACK (только если KSO safety разрешает)              │
│    └── POST /api/device-gateway/pop/events (batch)               │
│                                                                 │
│ 3. SHUTDOWN                                                      │
│    ├── flush PoP queue                                           │
│    ├── POST /api/device-gateway/pop/events (final batch)         │
│    └── завершение                                                │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Endpoint Compatibility Matrix

| Endpoint | Method | Auth | Used by KSO | Готов | Comment |
|---|---|---|---|---|---|
| `/api/device-gateway/auth/token` | POST | device_secret | ✅ cold start | ✅ ready | `device_code` + `device_secret` → JWT |
| `/api/device-gateway/heartbeat` | POST | JWT | ✅ warm loop | ✅ ready | `status`: ok/warning/error |
| `/api/device-gateway/config/current` | GET | JWT | ✅ warm loop | ✅ ready | ETag/304. `config_hash`, `config: dict` |
| `/api/device-gateway/manifest/current` | GET | JWT | ✅ warm loop | ✅ ready | hash-based 304. `status`: served/not_modified/no_manifest |
| `/api/device-gateway/manifest/{id}` | GET | JWT | ✅ fallback | ✅ ready | Полный manifest по ID |
| `/api/device-gateway/media/{id}/metadata` | GET | JWT | ✅ перед download | ✅ ready | `sha256`, `content_type`, `size_bytes`, `duration_ms` |
| `/api/device-gateway/media/{id}` | GET | JWT | ✅ download | ✅ ready | Streaming download + ETag/304 |
| `/api/device-gateway/manifest/{id}/apply` | POST | JWT | ✅ после sync | ✅ ready | `status`: applied/failed |
| `/api/device-gateway/media/cache/report` | POST | JWT | ✅ после download | ✅ ready | `status`: cached/missing/failed/invalid_hash |
| `/api/device-gateway/pop/events` | POST | JWT | ✅ playback | ✅ ready | `device_event_id` для дедупликации |
| `/api/device-gateway/pop/events/batch` | POST | JWT | ✅ offline flush | ✅ ready | Массив событий |

**Вывод:** все 11 endpoint'ов готовы. Новые не нужны.

## 4. Runtime Config Fields (для КСО-плеера)

Текущий `config: dict` из `GET /config/current`. Ключи, релевантные КСО-плееру:

| Key | Тип | Диапазон | Назначение |
|---|---|---|---|
| `heartbeat_interval_sec` | int | 10–3600 | Интервал heartbeat |
| `manifest_refresh_interval_sec` | int | 10–3600 | Интервал проверки manifest |
| `media_download_timeout_sec` | int | 1–300 | Таймаут загрузки media |
| `media_cache_max_mb` | int | 100–10240 | Макс. размер локального кэша |
| `pop_batch_max_events` | int | 1–1000 | Макс. событий в PoP batch |
| `pop_flush_interval_sec` | int | 30–3600 | Интервал отправки PoP batch |
| `offline_mode_enabled` | bool | — | Разрешён ли offline-режим |
| `allowed_mime_types` | list[str] | image/jpeg, image/png, video/mp4, video/webm | Допустимые MIME |
| `max_media_file_mb` | int | 1–2000 | Макс. размер одного media-файла |
| `clock_skew_tolerance_sec` | int | 0–3600 | Допустимое расхождение часов |
| `log_level` | str | debug/info/warning/error | Уровень логирования плеера |
| `kso_safety` | dict | — | **Настройки безопасности КСО** |

### kso_safety sub-object

| Key | Тип | Default | Назначение |
|---|---|---|---|
| `idle_only` | bool | true | Показ только когда КСО в idle |
| `stop_on_transaction` | bool | true | Остановка при транзакции |
| `stop_on_payment` | bool | true | Остановка при оплате |
| `stop_on_error_screen` | bool | true | Остановка при экране ошибки |

### Предлагаемые расширения config (GAP) → ✅ Реализованы в Шаге 23.1

| Key | Тип | Диапазон | Default | Назначение |
|---|---|---|---|---|
| `max_offline_duration_sec` | int | 0–604800 | 86400 | Макс. длительность offline-показа (0 = запрещён) |
| `manifest_ttl_sec` | int | 60–604800 | 86400 | TTL manifest после последнего успешного получения |
| `player_build_min_version` | str (max 64) | — | null | Мин. версия плеера (semver) |
| `player_build_recommended_version` | str (max 64) | — | null | Рекомендуемая версия плеера |
| `diagnostics_enabled` | bool | — | false | Включена ли диагностика плеера |
| `diagnostics_sample_interval_sec` | int | 30–86400 | 300 | Интервал сбора диагностики |
| `media_prefetch_enabled` | bool | — | false | Предзагрузка media |
| `media_prefetch_max_items` | int | 0–100 | 10 | Макс. элементов для предзагрузки |
| `local_storage_reserved_mb` | int | 0–102400 | 512 | Квота локального хранилища плеера |

### kso_safety extensions (GAP → ✅)

| Key | Тип | Диапазон/Enum | Default | Назначение |
|---|---|---|---|---|
| `stop_on_service_mode` | bool | — | true | Остановка при служебном режиме КСО |
| `fail_behavior` | str | `fail_silent` / `fail_closed` | fail_silent | Поведение при ошибке плеера |
| `screen_zone` | str | `idle_screen` / `side_panel` / `full_screen_idle_only` | idle_screen | Зона показа |
| `max_overlay_area_percent` | int | 1–100 | 100 | Макс. площадь оверлея (%) |
| `max_cpu_percent` | int | 1–100 | 30 | Макс. CPU для плеера |
| `max_memory_mb` | int | 16–4096 | 512 | Макс. RAM для плеера |

## 5. KSO Safety Rules

### Принцип: fail-closed

Реклама не должна мешать работе КСО. При любой неопределённости — **останавливаем показ**.

### Обязательные проверки перед показом

```
ПЕРЕД КАЖДЫМ ПОКАЗОМ:
├── KSO в idle?              → если idle_only=true и нет → STOP
├── Активна транзакция?      → если stop_on_transaction → STOP
├── Активна оплата?          → если stop_on_payment → STOP
├── Экран ошибки КСО?        → если stop_on_error_screen → STOP
├── Служебный режим КСО?     → если stop_on_service_mode → STOP
├── CPU > max_cpu_percent?   → STOP (не нагружать КСО)
├── RAM > max_memory_mb?     → STOP
└── ВСЁ OK → SHOW
```

### Что плеер НЕ делает

- Не показывает рекламу поверх критичных экранов (оплата, возврат, ошибка)
- Не блокирует интерфейс КСО
- Не влияет на кассовый сценарий
- Не перехватывает ввод пользователя
- При ошибке плеера — молча отключается (`fail_silent`)
- Не крашит основное приложение КСО

## 6. Offline Mode

### Правила

| Ситуация | Действие |
|---|---|
| Backend недоступен, `offline_mode_enabled=true` | Продолжать показ по последнему валидному manifest |
| Backend недоступен, `offline_mode_enabled=false` | Остановить показ немедленно |
| Offline показ дольше `max_offline_duration_sec` | Остановить показ |
| Manifest TTL истёк (`manifest_ttl_sec`) | Остановить показ (даже в offline) |
| Восстановление связи | Отправить накопленный PoP batch, обновить config/manifest |

### Offline PoP queue

- Копить события локально (очередь)
- При восстановлении связи — отправить batch'ами по `pop_batch_max_events`
- `device_event_id` гарантирует дедупликацию при повторах
- Если очередь переполнена — FIFO, старые события теряются (логировать)

## 7. Media Rules

- Media **только** через `GET /api/device-gateway/media/{id}`
- Никаких presigned URL, MinIO keys
- SHA256 обязателен: проверять после скачивания
- Hash mismatch → `POST /media/cache/report` со `status=invalid_hash`, не показывать
- Размер файла ≤ `max_media_file_mb` из config (проверять ДО скачивания через metadata)
- MIME тип ∈ `allowed_mime_types` из config
- Локальные пути НЕ отправлять в backend
- Кэш: LRU, не превышать `media_cache_max_mb`

## 8. PoP Rules

### Что считается показом

Показ засчитывается, когда медиа-файл **начал воспроизводиться** (playback started). Не считается показом: загрузка, кэширование, pre-buffering.

### Обязательные поля в PoP event

| Поле | Обязательно | Назначение |
|---|---|---|
| `device_event_id` | ✅ UUID | Уникальный ID события на устройстве (дедупликация) |
| `manifest_item_id` | ✅ UUID | Какой media item показан |
| `played_at` | Рекомендуется | ISO8601 timestamp показа |
| `duration_ms` | Опционально | Длительность показа |
| `play_status` | Опционально | `completed` / `interrupted` / `error` |

### Что НЕ отправлять

- ❌ Персональные данные покупателя
- ❌ Фото/видео/скриншоты экрана КСО
- ❌ Чековые данные
- ❌ Данные банковских карт
- ❌ Геолокацию (кроме store_id — уже есть в device)

## 9. Security Rules

### Device secret

- `device_secret` хранить **только в защищённом локальном хранилище** (Keychain/Keystore)
- Никогда не логировать
- Не передавать в других запросах (только auth)

### JWT

- Short-lived (проверять `exp`)
- При 401 — перевыпустить через `/auth/token`
- Refresh до истечения (за 30 сек до `exp`)
- Не сохранять на диск (только в памяти)

### TLS

- TLS 1.2+ обязателен
- Certificate validation обязательно (no `--insecure`)
- Только исходящие соединения от КСО к backend
- Никаких входящих соединений на КСО

### Данные

- Никаких human-токенов в плеере
- Никаких данных рекламодателя
- Никаких платёжных данных
- Никаких локальных путей в API-запросах
- Логи без secrets (маскировать `device_secret`, JWT)

## 10. Error Handling

### Retry policy

| Ошибка | Retry | Backoff |
|---|---|---|
| 401 Unauthorized | re-auth немедленно | — |
| 429 Rate Limit | да | exponential: 1s → 2s → 4s → 8s → 16s, затем фикс 30s |
| 5xx Server Error | да (до 3 раз) | 5s → 10s → 30s |
| 4xx Client Error | нет (кроме 401/429) | — |
| Connection timeout | да (до 3 раз) | 5s → 10s → 30s |

### Degradation

- Heartbeat fail →不影响 показ (отправить позже)
- Config/manifest fail → использовать последний валидный (если не истёк TTL)
- Media download fail → пропустить item, отправить `cache/report` со `status=failed`
- PoP send fail → копить в offline-очередь

## 11. Backend Compatibility Summary

### Готово ✅ (11 endpoints)
Все device-facing endpoint'ы реализованы и протестированы в Шагах 1–22.

### GAP'ы (Step 23.1 — реализованы #1–8)

| # | GAP | Статус |
|---|---|---|
| 1 | `max_offline_duration_sec` | ✅ Реализован |
| 2 | `manifest_ttl_sec` | ✅ Реализован |
| 3 | `stop_on_service_mode` (kso_safety) | ✅ Реализован |
| 4 | `fail_behavior` (kso_safety) | ✅ Реализован |
| 5 | `screen_zone` (kso_safety) | ✅ Реализован |
| 6 | `player_build_min_version` | ✅ Реализован |
| 7 | `local_storage_reserved_mb` | ✅ Реализован |
| 8 | `max_cpu_percent` / `max_memory_mb` (kso_safety) | ✅ Реализован |
| 9 | Нет endpoint для player diagnostics/health | Future |
| 10 | Нет механизма push-уведомлений (poll-only manifest) | Future |

## 12. Verification Plan (будущий шаг)

1. Device auth → JWT получен, `exp` в будущем
2. Heartbeat → 200, статус зафиксирован
3. Config/current → 200, `config_hash` не пустой, `kso_safety` присутствует
4. Config/current + If-None-Match → 304
5. Manifest/current → 200 (served) или 200 (no_manifest)
6. Manifest/current + hash → 304 (not_modified)
7. Media metadata → 200, sha256 совпадает
8. Media download → 200, sha256 файла совпадает с metadata
9. Cache report → 200
10. Manifest apply → 200
11. PoP single → 200 (accepted)
12. PoP batch → 200
13. Campaign report → PoP отображается в actual_play_count

## 13. Commit

Не делаем — только mini-design на утверждение.
