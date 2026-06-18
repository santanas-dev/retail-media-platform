# Mini-Design: KSO Sidecar Media Cache

**Статус:** Mini-design. Код не пишем.
**Шаг:** 25.21
**Дата:** 18 июня 2026
**Основание:**
- `docs/kso_local_interface_contract.md` (секции 2, 3, 4 — `media/current/`, `media/staging/`, `media/quarantine/`)
- `docs/kso_sidecar_agent_design.md` (компоненты MediaClient, CacheManager)
- `apps/kso_sidecar_agent/kso_sidecar_agent/manifest_client.py` (ManifestSnapshot)
- `apps/kso_sidecar_agent/kso_sidecar_agent/manifest_store.py` (нормализация, атомарная запись)
- `backend/app/domains/device_gateway/router.py` (фактические media endpoints)
- `backend/app/domains/device_gateway/service.py` (MEDIA_DELIVERY_ALLOWED_MIME, логика скачивания)
- `tools/kso_simulator/kso_simulator/media_verifier.py` (эталонная sha256-проверка)
- `apps/kso_sidecar_agent/kso_sidecar_agent/paths.py` (константы путей)

---

## 1. Цель

Спроектировать безопасное скачивание и локальное хранение media-файлов для KSO Sidecar Agent.

**Проблема:** Manifest уже сохранён локально в `manifest/current_manifest.json`, каждый item содержит `manifest_item_id`, `filename`, `content_type`, `sha256`, `size_bytes`, `duration_ms`, `order`. Но сами media-файлы ещё не скачаны. Без них КСО ПО нечего показывать.

**Media Cache** — это слой, который:
1. Скачивает media-файлы через backend device-gateway (JWT-аутентификация).
2. Сохраняет их атомарно: staging → verify sha256 → rename в `media/current/`.
3. НЕ отдаёт КСО ПО битые/частично скачанные файлы.
4. Проверяет sha256, размер, content-type.
5. НЕ раскрывает backend object key (`media_path`), presigned URL, MinIO-credentials.

---

## 2. Фактические backend media endpoints

### 2.1 `GET /api/device-gateway/media/{manifest_item_id}/metadata`

**Method:** `GET`
**Auth:** Device JWT (`Authorization: Bearer <token>`)
**Query:** `?client_cached_sha256=<sha256>` (опционально, для 304)

```json
// 200
{
  "status": "ok",
  "manifest_item_id": "11111111-1111-1111-1111-111111111111",
  "media": {
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "content_type": "video/mp4",
    "size_bytes": 1234567,
    "duration_ms": 15000
  }
}

// 304 (если client_cached_sha256 совпадает)
{
  "status": "not_modified",
  "manifest_item_id": "...",
  "sha256": "..."
}
```

**Примечание:** Metadata endpoint возвращает **реальные** `size_bytes` (из MinIO `stat_object`) и `content_type` (из БД `rendition.mime_type` / `creative_version.mime_type`). На этом шаге manifest store заполняет `size_bytes = 0` и `content_type` из расширения — metadata endpoint даёт точные значения.

### 2.2 `GET /api/device-gateway/media/{manifest_item_id}`

**Method:** `GET`
**Auth:** Device JWT
**Query:** `?client_cached_sha256=<sha256>` (опционально, для 304)
**Response:** `StreamingResponse` с media-файлом

**Response headers (200):**
- `Content-Type: <mime_type>`
- `Content-Length: <size_bytes>`
- `X-Content-SHA256: <sha256>`
- `ETag: <minio_etag>`
- `Cache-Control: private, max-age=86400`

**304:** Если `client_cached_sha256` совпадает с `mi.sha256` — backend возвращает `304 Not Modified` (без тела).

### 2.3 `POST /api/device-gateway/media/cache/report`

**Method:** `POST`
**Auth:** Device JWT

```json
// Request
{
  "manifest_version_id": "a0eebc99-...",
  "items": [
    {
      "manifest_item_id": "11111111-...",
      "cache_status": "cached",
      "local_sha256": "aaaa...",
      "local_size_bytes": 1234567
    }
  ]
}

// Response
{
  "status": "ok",
  "gateway_device_id": "...",
  "manifest_version_id": "...",
  "total_items": 5,
  "cached_count": 4,
  "missing_count": 1,
  "failed_count": 0,
  "invalid_hash_count": 0
}
```

### 2.4 Allowed MIME types (backend-side)

Из `backend/app/domains/device_gateway/service.py`:

```python
MEDIA_DELIVERY_ALLOWED_MIME = frozenset({
    "image/jpeg",
    "image/png",
    "video/mp4",
    "video/webm",
})
```

**Рекомендация для sidecar:** Использовать тот же набор. `application/octet-stream` НЕ разрешать к проигрыванию (только как fallback при неизвестном расширении — но тогда файл в `media/current/` не публикуется без явного `content_type` из разрешённого списка).

---

## 3. Связь manifest → media download

### 3.1 Source of truth

Локальный `manifest/current_manifest.json` — единственный источник для:
- `manifest_item_id` — какой файл скачивать
- `filename` — под каким именем сохранять (уже безопасное, `<uuid>.<ext>`)
- `sha256` — с чем сравнивать после скачивания
- `size_bytes` — ожидаемый размер (сейчас 0, будет из metadata)
- `content_type` — MIME-тип (сейчас из расширения, будет из metadata)
- `duration_ms` — длительность (для КСО ПО)
- `order` — порядок показа

### 3.2 Алгоритм для каждого item

```
1. Взять manifest_item_id из current_manifest.json
2. Проверить: файл уже в media/current/<filename> с правильным sha256?
   ├── Да + sha256 совпадает → пропустить (уже в кэше)
   └── Нет → скачивать
3. Сделать GET /api/device-gateway/media/{manifest_item_id}?client_cached_sha256=<local_sha256>
   ├── 304 → файл актуален (локальный sha256 совпал с backend)
   └── 200 → стримить тело
4. Сохранить поток в media/staging/<filename>.download
5. Во время записи: считать sha256 (потоково, как в `simulator/media_verifier.py`)
6. После записи: fsync, закрыть файл
7. Сравнить sha256:
   ├── Совпадает → os.replace(staging, media/current/<filename>)
   └── НЕ совпадает → os.replace(staging, media/quarantine/<filename>.bad)
8. Очистить staging (.download файл не должен оставаться)
```

---

## 4. Локальные каталоги

Строго соответствуют `docs/kso_local_interface_contract.md` и `apps/kso_sidecar_agent/kso_sidecar_agent/paths.py`:

```
{root}/
├── media/
│   ├── current/          # ГОТОВЫЕ файлы (КСО ПО читает)
│   │   ├── <uuid>.jpg
│   │   ├── <uuid>.mp4
│   │   └── manifest.json  # Краткий manifest для КСО ПО (будущее)
│   ├── staging/          # В процессе загрузки (КСО ПО НЕ читает)
│   │   └── <uuid>.download
│   └── quarantine/       # Повреждённые файлы (КСО ПО НЕ читает)
│       └── <uuid>.bad
├── manifest/
│   └── current_manifest.json
├── config/
└── ...
```

### 4.1 Правила доступа

| Каталог | Agent | КСО ПО | Назначение |
|---|---|---|---|
| `media/current/` | read/write | **read-only** | Готовые к показу файлы |
| `media/staging/` | read/write | **нет доступа** | Временные .download файлы |
| `media/quarantine/` | read/write | **нет доступа** | Повреждённые .bad файлы |

### 4.2 Filename conventions

| Где | Формат имени | Пример |
|---|---|---|
| `media/current/` | `<manifest_item_id>.<ext>` | `11111111-1111-1111-1111-111111111111.mp4` |
| `media/staging/` | `<manifest_item_id>.<ext>.download` | `11111111-1111-1111-1111-111111111111.mp4.download` |
| `media/quarantine/` | `<manifest_item_id>.<ext>.bad` | `11111111-1111-1111-1111-111111111111.mp4.bad` |

Filename **уже безопасен** — он сформирован из UUID + расширения в manifest_store. Дополнительно:
- ❌ Не использовать backend `media_path` как filename
- ❌ Не генерировать filename из невалидированных источников
- ❌ Не допускать `../`, `\\`, `/`, `C:\`, абсолютные пути
- ❌ Reject symlink target

---

## 5. Atomic download/write

```
ШАГ 1: Создать staging-файл
  path = media/staging/<filename>.download

ШАГ 2: Открыть поток от backend
  GET /api/device-gateway/media/{manifest_item_id}
  (опционально с ?client_cached_sha256=... → 304 если не изменился)

ШАГ 3: Потоковая запись + sha256
  sha = hashlib.sha256()
  with open(path, 'wb') as f:
      for chunk in response.iter_content(chunk_size=65536):
          f.write(chunk)
          sha.update(chunk)
  f.flush()
  os.fsync(f.fileno())

ШАГ 4: Проверка размера
  actual_size = os.path.getsize(path)
  if expected_size > 0 and actual_size != expected_size:
      → os.replace(path, media/quarantine/<filename>.bad)
      → ошибка: size mismatch

ШАГ 5: Проверка sha256
  if sha.hexdigest() != manifest_item.sha256:
      → os.replace(path, media/quarantine/<filename>.bad)
      → ошибка: sha256 mismatch

ШАГ 6: Проверка content-type (если возможно)
  (на этом шаге — опционально; в будущем — через python-magic или заголовок Content-Type)

ШАГ 7: Публикация
  os.replace(path, media/current/<filename>)
  (атомарно в пределах одной ФС)
```

### 5.1 Что НЕ оставлять

- ❌ Partial files в `media/current/` (только через rename)
- ❌ `.download` файлы в `media/staging/` после публикации (перемещены или удалены)
- ❌ `.tmp` файлы (не использовать; использовать `.download`)
- ❌ Symlink targets (reject)

### 5.2 Очистка staging при старте

При инициализации agent: удалить все `media/staging/*.download` (прерванные загрузки с прошлого запуска).

---

## 6. Validation / Security

### 6.1 Forbidden substrings (во всех ключах и строковых значениях)

```python
FORBIDDEN_MEDIA_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
})
```

### 6.2 Обязательные проверки

| Проверка | Где | Правило |
|---|---|---|
| Filename safe | staging/current filename | Нет `../`, `\\`, `/`, `C:\`, absolute |
| SHA256 format | manifest item | 64 hex chars |
| SHA256 match | после скачивания | `hashlib.sha256(file) == item.sha256` |
| Size match | после скачивания | `os.path.getsize(file) == item.size_bytes` (если > 0) |
| Content-Type allowed | перед публикацией | Из `MEDIA_DELIVERY_ALLOWED_MIME` |
| Symlink reject | перед записью | `path.resolve() != path` или `path.is_symlink()` |
| Response body | в ошибках/логах | ❌ не дампить |
| Authorization header | в ошибках/логах | ❌ не выводить |
| Token/secret | stdout/stderr | ❌ не выводить |
| Stacktrace | stdout/stderr | ❌ не выводить |

### 6.3 Что НЕ должно быть в локальных файлах

- ❌ `media_path` / `object_key` (внутренний MinIO key)
- ❌ `local_path` / `file_path` / `filesystem_path`
- ❌ `token`, `secret`, `jwt`, `api_key`
- ❌ `authorization`, `bearer`
- ❌ `device_secret`
- ❌ `stacktrace`
- ❌ `presigned_url`
- ❌ MinIO credentials

### 6.4 Allowed content types (sidecar)

Использовать тот же набор, что и backend:

```python
MEDIA_CACHE_ALLOWED_MIME = frozenset({
    "image/jpeg",
    "image/png",
    "video/mp4",
    "video/webm",
})
```

**Правило:** Если `content_type` не в этом списке — файл НЕ публиковать в `media/current/`. Переместить в `media/quarantine/`.

`application/octet-stream` — разрешить только если нет другого способа определить тип. Для production: запретить к проигрыванию.

---

## 7. Handling edge cases

### 7.1 Partial download

- Если соединение оборвано во время скачивания → `.download` файл остаётся в `media/staging/`
- При следующей попытке: удалить старый `.download`, начать заново
- Partial файл НИКОГДА не попадает в `media/current/`

### 7.2 Corrupted media (sha256 mismatch)

- Файл → `media/quarantine/<filename>.bad`
- Логировать: `media_sha256_mismatch` (без полного sha256 в логах — только первые 12 символов)
- Инкрементировать `invalid_hash_items` в `agent_status.json`
- **НЕ удалять** quarantine-файлы автоматически (для audit)
- При следующем sync — попробовать скачать заново

### 7.3 Missing media (404)

- Backend вернул 404 → item не опубликован / не привязан к устройству
- Логировать: `media_not_found`
- **НЕ крашить** sync — продолжить со следующим item
- В кэш-отчёте: status = `missing`

### 7.4 Stale media

- Manifest обновился → старые файлы в `media/current/` больше не в manifest
- **На этом шаге:** не удалять автоматически (будет отдельная политика очистки)
- В будущем: LRU-вытеснение при превышении `media_cache_max_mb`
- В будущем: удаление файлов, отсутствующих в новом manifest, после TTL

### 7.5 Existing valid file (не скачивать повторно)

```
ЕСЛИ файл существует в media/current/<filename>
  И sha256(файла) == manifest_item.sha256
  → НЕ скачивать (уже в кэше)
```

Проверка: вычислить `sha256(file)` и сравнить с `item.sha256`. Если совпадает — пропустить.

### 7.6 Corrupted existing file

```
ЕСЛИ файл существует в media/current/<filename>
  НО sha256(файла) != manifest_item.sha256
  → Удалить текущий файл
  → Скачать заново
  → Опубликовать только после успешной проверки
```

### 7.7 Not modified (304)

```
GET /media/{id}?client_cached_sha256=<local_sha256>
→ 304 Not Modified
→ Оставить существующий файл нетронутым
→ Перейти к следующему item
```

---

## 8. Status model

### 8.1 `agent_status.json` — поля для media cache

```json
{
  "cached_items": 4,
  "invalid_hash_items": 1,
  "last_cache_report_at": "2026-06-18T10:00:00Z"
}
```

### 8.2 Safe media cache status (отдельная функция)

```json
{
  "media_cache_present": true,
  "items_total": 5,
  "items_cached": 4,
  "items_missing": 1,
  "items_corrupted": 0,
  "cache_complete": false,
  "last_sync_at": "2026-06-18T10:00:00Z"
}
```

**Запрещено выводить:**
- Полный manifest
- Полный список файлов
- `media_path`
- `local_path`
- `file_path`

---

## 9. Рекомендация: device-gateway vs presigned URL

**Backend сейчас:** отдаёт media через `GET /api/device-gateway/media/{manifest_item_id}` с JWT-аутентификацией. MinIO object key (`media_path`) никогда не покидает backend. Это **правильная архитектура**.

**Рекомендация (для будущего):**
- ✅ Device скачивает media через backend device-gateway endpoint
- ✅ Только JWT-аутентификация (device token)
- ❌ Device НЕ получает MinIO/S3 presigned URL
- ❌ Device НЕ получает storage credentials (access key, secret key)
- ❌ Device НЕ получает `media_path` / object key
- ❌ Device НЕ обращается к MinIO напрямую

**Почему:** Если device получает presigned URL — он раскрывает внутреннюю инфраструктуру (endpoint MinIO, bucket name, object key). Device должен видеть только `/api/device-gateway/media/{id}`.

---

## 10. Будущие файлы (НЕ создавать на этом шаге)

### 10.1 Python-модули

```
apps/kso_sidecar_agent/kso_sidecar_agent/media_client.py
apps/kso_sidecar_agent/kso_sidecar_agent/media_cache.py
```

**`media_client.py` — функции:**
- `fetch_media_metadata(token_state, manifest_item_id, client_cached_sha256=None) -> MediaMetadata`
- `fetch_media_stream(token_state, manifest_item_id, client_cached_sha256=None) -> Iterator[bytes]`
- `MediaMetadata` dataclass: `manifest_item_id`, `sha256`, `content_type`, `size_bytes`, `duration_ms`, `status`

**`media_cache.py` — функции:**
- `compute_sha256(filepath: Path) -> str` — как в `simulator/media_verifier.py`
- `write_media_atomic(root, manifest_item, stream) -> Path` — staging → verify → current
- `verify_media_file(root, manifest_item) -> bool` — проверить существующий файл в `media/current/`
- `sync_media_cache(root, token_state, manifest_items) -> MediaCacheResult`
- `media_cache_status(root) -> dict` — safe summary
- `clean_staging(root) -> None` — удалить `.download` файлы
- `submit_cache_report(token_state, cache_status) -> None` — отправить отчёт backend
- `MediaCacheResult` dataclass: `cached`, `missing`, `corrupted`, `errors`

### 10.2 Тесты

```
apps/kso_sidecar_agent/tests/test_media_client.py
apps/kso_sidecar_agent/tests/test_media_cache.py
```

**Тестовые сценарии:**

`test_media_client.py`:
- `fetch_media_metadata` success (200)
- `fetch_media_metadata` not_modified (304)
- `fetch_media_metadata` not found (404)
- `fetch_media_stream` success
- `fetch_media_stream` not_modified (304)
- Auth errors: 401, 403, 422
- Server error: 500
- Network error
- No token/secret/Authorization в stdout/stderr
- No response body dump

`test_media_cache.py`:
- Successful download → file appears in `media/current/`
- sha256 OK → file in cache
- sha256 mismatch → file in `media/quarantine/`, not in `media/current/`
- Partial download → file not in `media/current/`
- Size mismatch → file in `media/quarantine/`
- Unsafe filename → reject
- Symlink target → reject
- Staging cleanup on start
- Existing valid file not re-downloaded
- Corrupted existing file replaced after successful new download
- Missing media endpoint → safe error, next item processed
- 401/403/404/422/500 → safe errors
- 304 → leave existing file untouched
- No token/secret/Authorization in output
- No response body dump
- No `local_path` in output
- Compatible with simulator `media_verifier.py`

### 10.3 Константы в `paths.py`

Добавить (в будущем):

```python
MEDIA_CURRENT_DIR = "media/current"
MEDIA_STAGING_DIR = "media/staging"
MEDIA_QUARANTINE_DIR = "media/quarantine"
```

---

## 11. Будущие CLI-команды (НЕ реализовывать на этом шаге)

```bash
# Статус media cache
python3 -m kso_sidecar_agent.cli media-cache-status --root /tmp/kso-agent-root
# Вывод: items_total, items_cached, items_missing, items_corrupted, cache_complete

# Полный sync: manifest → media download → cache report
python3 -m kso_sidecar_agent.cli sync-media \
  --root /tmp/kso-agent-root \
  --dev-secret-store
# Пайплайн: config → secret → auth → manifest/current → для каждого item:
#   проверить кэш → скачать если нужно → sha256 → publish → cache report
```

**Важно:** `sync-media` должен быть отдельным будущим шагом **после** реализации `media_client.py` и `media_cache.py`.

---

## 12. Retry policy (future)

На этом шаге retry для media download **не проектируем**. Будет отдельным шагом.

Ожидаемое поведение (для справки):
- 429, 5xx, network error → retry с exponential backoff
- 401, 403, 404, 422 → без retry
- 304 → не скачивать (файл актуален)

---

## 13. Совместимость

| Компонент | Статус |
|---|---|
| `ManifestClient` (шаг 25.17) | ✅ Возвращает `ManifestSnapshot` с `items`, каждый содержит `manifest_item_id`, `filename`, `sha256` |
| `ManifestStore` (шаги 25.19–25.19.1) | ✅ Пишет `manifest/current_manifest.json` с нормализованными items |
| `kso_local_interface_contract.md` | ✅ Строго следует структуре `media/current/`, `media/staging/`, `media/quarantine/` |
| `kso_sidecar_agent_design.md` | ✅ Компоненты MediaClient, CacheManager |
| `simulator/media_verifier.py` | ✅ Совместим — та же логика sha256: `hashlib.sha256()`, `update()` в цикле, `hexdigest()` |
| `simulator/manifest_reader.py` | ✅ Совместим — читает `current_manifest.json`, ожидает `filename` |
| Backend | ✅ Не требует изменений — работает с существующими endpoint'ами `GET /media/{id}`, `GET /media/{id}/metadata`, `POST /media/cache/report` |
| `paths.py` | ✅ Добавить `MEDIA_CURRENT_DIR`, `MEDIA_STAGING_DIR`, `MEDIA_QUARANTINE_DIR` |

---

## 14. Что НЕ реализуем на этом шаге

- ❌ `media_client.py` (код)
- ❌ `media_cache.py` (код)
- ❌ `sync-media` CLI
- ❌ `media-cache-status` CLI
- ❌ Скачивание файлов
- ❌ Запись media на диск
- ❌ Sha256-проверка локальных файлов
- ❌ Отправка cache report backend'у
- ❌ LRU-вытеснение
- ❌ Очистка старых media
- ❌ Playback
- ❌ PoP
- ❌ Backend changes
- ❌ Новые backend endpoints
- ❌ Real backend calls
- ❌ Retry для media download

---

## 15. Risks

| Риск | Mitigation |
|---|---|
| Backend меняет формат metadata ответа | MediaClient изолирован — легко адаптировать |
| `size_bytes` из metadata не совпадает с actual file size | Проверять оба: `Content-Length` из заголовков + `os.path.getsize()` после записи |
| Staging и current на разных ФС → rename не атомарен | Ограничение: требуем одну ФС для `media/`. Если КСО-терминал использует разные разделы — документировать как ограничение |
| Большие video-файлы → долгое скачивание | Стримить с ограничением размера чанка. В будущем: timeout из runtime config |
| КСО ПО читает файл во время rename | `os.replace()` атомарен в пределах одной ФС — КСО ПО видит либо старый, либо новый файл |
| Backend 5xx во время скачивания | `.download` остаётся в staging → при следующем sync начать заново |
| Диск заполнен | Проверять свободное место перед скачиванием (в будущем: `storage_free_mb` в runtime config) |
| Скомпрометированный backend возвращает зловредный файл | Sha256 в manifest — source of truth. Если sha256 в manifest валидный, но файл зловредный — проблема на стороне backend, не sidecar |

---

## 16. Проверка

- [x] Документ создан
- [x] Нет реальных secrets/tokens
- [x] Не утверждает, что media cache уже реализован
- [x] Совместим с ManifestStore
- [x] Совместим с local interface contract
- [x] Совместим с simulator media_verifier
- [x] Не требует backend changes
- [x] Backend endpoints зафиксированы из реального кода
