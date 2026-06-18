# Mini-Design: KSO Sidecar Manifest Local Store

**Статус:** Mini-design. Код не пишем.
**Шаг:** 25.18
**Дата:** 18 июня 2026
**Основание:**
- `docs/kso_local_interface_contract.md` (секция 5 — `manifest/current_manifest.json`)
- `docs/kso_sidecar_agent_design.md` (компонент LocalFileStore)
- `tools/kso_simulator/kso_simulator/manifest_reader.py` (эталонный reader)
- `apps/kso_sidecar_agent/kso_sidecar_agent/manifest_client.py` (backend-клиент)

---

## 1. Цель

Спроектировать безопасное локальное хранение manifest для KSO Sidecar Agent.

**Проблема:** Backend возвращает manifest в двух разных форматах:
- `GET /api/device-gateway/manifest/current` → `DeviceManifestCurrentResponse`
- `GET /api/device-gateway/manifest/{id}` → `DeviceManifestResponse`

А локальный файл `manifest/current_manifest.json`, который читает КСО ПО и simulator, должен быть **единым**, **безопасным** и не зависеть от того, из какого backend-endpoint'а пришли данные.

**Manifest Local Store** — это слой, который:
1. Нормализует backend-ответ в единый локальный формат.
2. Атомарно записывает `current_manifest.json`.
3. Валидирует все поля перед записью (forbidden keys/values, path traversal, UUID, sha256).

---

## 2. Фактические backend manifest response variants

### 2.1 `GET /manifest/current`

```json
{
  "status": "served",
  "manifest_version_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "manifest_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "published_at": "2026-06-18T10:00:00+00:00",
  "manifest": {
    "items": [
      {
        "id": "11111111-1111-1111-1111-111111111111",
        "schedule_item_id": "22222222-2222-2222-2222-222222222222",
        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "media_path": "creatives/test.mp4",
        "duration_ms": 15000,
        "loop_position": 0,
        "spot_position": 1
      }
    ]
  }
}
```

**Статусы:** `"served"`, `"not_modified"`, `"no_manifest"`

### 2.2 `GET /manifest/{manifest_version_id}`

```json
{
  "manifest_version_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "manifest_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "published_at": "2026-06-18T10:00:00+00:00",
  "manifest_items": [
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "media_path": "creatives/test.mp4",
      "duration_ms": 15000,
      "loop_position": 0,
      "spot_position": 1
    }
  ]
}
```

### 2.3 Отличия

| Поле | `/manifest/current` | `/manifest/{id}` |
|---|---|---|
| `status` | ✅ `served` / `not_modified` / `no_manifest` | ❌ (неявно: всегда 200 = served) |
| `manifest.items` | ✅ вложенный объект | ❌ |
| `manifest_items` | ❌ | ✅ список на верхнем уровне |
| `manifest_hash` | ✅ в `manifest.manifest_hash` | ✅ верхний уровень (extra field) |
| `published_at` | ✅ | ✅ (extra field) |
| Item `id` | ✅ (backend: `manifest_items.id`) | ✅ |
| Item `sha256` | ✅ | ✅ |
| Item `media_path` | ✅ (напр. `creatives/test.mp4`) | ✅ |
| Item `duration_ms` | ✅ | ✅ |
| Item `loop_position` | ✅ | ✅ |
| Item `spot_position` | ✅ | ✅ |
| Item `content_type` | ❌ (нет в backend ответе) | ❌ |
| Item `size_bytes` | ❌ (нет в backend ответе) | ❌ |

---

## 3. Зачем нужна нормализация

1. **Единый выходной формат** — КСО ПО и simulator читают ОДИН файл `current_manifest.json` и не должны знать разницу между `/manifest/current` и `/manifest/{id}`.

2. **Безопасность** — backend использует `media_path` с директориями (`creatives/test.mp4`). Локальный manifest должен содержать только **безопасное имя файла** без директорий.

3. **Отсутствующие поля** — backend не возвращает `content_type` и `size_bytes` в manifest-ответе. На этом шаге заполняем дефолтами (`content_type` — из расширения `media_path`, `size_bytes = 0`). В будущем — из `GET /media/{id}/metadata`.

4. **Разные имена полей** — backend item `id` → локальный `manifest_item_id`. Backend `loop_position`/`spot_position` → локальный `order`.

---

## 4. Локальный формат `manifest/current_manifest.json`

Формат строго соответствует `docs/kso_local_interface_contract.md` (секция 5) и совместим с `tools/kso_simulator/kso_simulator/manifest_reader.py`.

```json
{
  "manifest_version_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "manifest_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "source": "current",
  "generated_at": "2026-06-18T10:00:00+00:00",
  "valid_until": null,
  "fetched_at": "2026-06-18T10:00:05+00:00",
  "campaign_id": null,
  "items": [
    {
      "manifest_item_id": "11111111-1111-1111-1111-111111111111",
      "filename": "11111111-1111-1111-1111-111111111111.mp4",
      "content_type": "video/mp4",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "size_bytes": 0,
      "duration_ms": 15000,
      "order": 0
    }
  ]
}
```

### 4.1 Поля верхнего уровня

| Поле | Тип | Источник | Примечание |
|---|---|---|---|
| `manifest_version_id` | UUID | backend `manifest_version_id` | Валидация UUID |
| `manifest_hash` | 64 hex | backend `manifest_hash` | Валидация 64 hex |
| `source` | string | `"current"` или `"by_id"` | Откуда пришёл manifest |
| `generated_at` | ISO8601 | backend `published_at` | Может быть `null` |
| `valid_until` | ISO8601 \| null | `null` на этом шаге | Будет заполняться из runtime config TTL в будущем |
| `fetched_at` | ISO8601 | `datetime.now(timezone.utc)` | Момент записи локального файла |
| `campaign_id` | UUID \| null | `null` на этом шаге | Будет заполняться из backend в будущем |
| `items` | list[object] | нормализованные backend items | Минимум 1 item? Нет — может быть пустой |

### 4.2 Поля item

| Поле | Тип | Источник | Примечание |
|---|---|---|---|
| `manifest_item_id` | UUID | backend item `id` | Валидация UUID |
| `filename` | string | `manifest_item_id` + расширение | **НЕ** backend `media_path`! |
| `content_type` | string | расширение `media_path` → MIME | Карта расширений |
| `sha256` | 64 hex | backend item `sha256` | Валидация 64 hex |
| `size_bytes` | int ≥ 0 | `0` на этом шаге | Будет из `GET /media/{id}/metadata` |
| `duration_ms` | int ≥ 0 | backend item `duration_ms` | `0` если отсутствует |
| `order` | int ≥ 0 | backend item `loop_position` | Приоритет: `order` > `loop_position` > `spot_position` > `0` |

### 4.3 Правила нормализации полей

#### `manifest_item_id` ← backend `id`

```
backend item.id (UUID) → manifest_item_id (UUID)
```

Если `id` отсутствует или не UUID — reject.

#### `filename` ← `manifest_item_id` + расширение

```
filename = <manifest_item_id>.<extension>
extension = MIME_TO_EXT[content_type]
```

**Запрещено использовать backend `media_path` как filename!**

#### `content_type` ← расширение из backend `media_path`

**Карта расширений:**

| Расширение | content_type |
|---|---|
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.png` | `image/png` |
| `.mp4` | `video/mp4` |
| `.webm` | `video/webm` |
| (неизвестно) | `application/octet-stream` |

Извлекается из `media_path`:
```python
ext = os.path.splitext(media_path)[1].lower()
content_type = EXT_TO_MIME.get(ext, "application/octet-stream")
```

Расширение `.bin` → `application/octet-stream`.

#### `order` ← backend `loop_position` / `spot_position`

Приоритет:
1. `order` (если есть в backend item)
2. `loop_position`
3. `spot_position`
4. `0` (дефолт)

---

## 5. Правило формирования filename

### 5.1 Основное правило

```
<manifest_item_id>.<safe_extension>
```

Примеры:
```
11111111-1111-1111-1111-111111111111.png
22222222-2222-2222-2222-222222222222.jpg
33333333-3333-3333-3333-333333333333.mp4
44444444-4444-4444-4444-444444444444.bin
```

### 5.2 Запрещённые символы в filename

- ❌ `/` — разделитель директорий
- ❌ `\` — Windows-разделитель
- ❌ `..` — parent directory
- ❌ `C:\` — Windows drive prefix
- ❌ Абсолютный путь (начинается с `/`)

UUID гарантированно не содержит запрещённых символов, поэтому `<manifest_item_id>.<ext>` всегда безопасен.

### 5.3 Что НЕ использовать

- ❌ backend `media_path` напрямую (содержит директории `creatives/...`)
- ❌ `local_path` / `file_path` (не генерировать, не писать, не логировать)
- ❌ `basename(media_path)` без дополнительной очистки (может содержать `..` если backend скомпрометирован)

---

## 6. Что делать с `media_path`

Backend `media_path` (например `creatives/test.mp4`) — это внутренний object key в MinIO.

**На этом шаге:**
- `media_path` НЕ попадает в локальный `current_manifest.json`
- `media_path` используется только для извлечения расширения → `content_type`
- После извлечения расширения `media_path` отбрасывается

**В будущем:**
- `media_path` может храниться во внутреннем agent-файле `manifest/internal_manifest.json` (недоступном КСО ПО) для audit/log
- Для media download — использовать `GET /api/device-gateway/media/{manifest_item_id}`, а не `media_path` напрямую
- Agent никогда не раскрывает MinIO object key ни КСО ПО, ни в логах

---

## 7. Обработка статусов

### 7.1 `served`

1. Извлечь `manifest_version_id`, `manifest_hash`, `published_at`, `items`
2. Нормализовать items в локальный формат
3. Пройти security scan (forbidden keys/values)
4. Атомарно записать `current_manifest.json`

### 7.2 `not_modified`

1. **НЕ перезаписывать** `current_manifest.json`
2. Оставить текущий локальный manifest нетронутым
3. Обновить `fetched_at` в памяти (но не менять файл)
4. Это поведение совместимо с ETag/304 для `/manifest/current`

### 7.3 `no_manifest`

1. **НЕ создавать** пустой manifest
2. **Рекомендация:** не удалять старый `current_manifest.json` автоматически — оставить до TTL
3. Старый manifest остаётся доступным КСО ПО до истечения `valid_until` (или до превышения `max_offline_duration_sec` в будущем)

**Причина не удалять сразу:** Если backend временно не может обслужить manifest (новый batch не опубликован), КСО ПО должно продолжать показывать старый контент, пока он не истёк по TTL.

---

## 8. Atomic Write

```
1. Записать нормализованный manifest в manifest/current_manifest.json.tmp
2. fsync() — гарантировать запись на диск (опционально, если ОС поддерживает)
3. os.replace(tmp_path, final_path) — атомарный rename
   ├── НЕ оставляет .tmp файл после rename
   ├── НЕ создаёт partial manifest (КСО ПО видит только завершённый файл)
   └── НЕ следует symlink target
4. Reject symlink:
   ├── Перед записью проверить, что manifest/ не symlink
   └── Если symlink — не писать, error
```

**НЕ делать:**
- Не писать напрямую в `current_manifest.json`
- Не оставлять `current_manifest.json.tmp` (при ошибке — удалить)

---

## 9. Validation / Security

### 9.1 Forbidden substrings (во всех ключах и строковых значениях)

```
token, jwt, password, secret, api_key,
private_key, payment_card, receipt,
local_path, file_path, authorization, bearer,
device_secret, access_token
```

Проверять **рекурсивно** все ключи и строковые значения в нормализованном manifest перед записью.

### 9.2 Обязательные проверки

| Проверка | Поле | Правило |
|---|---|---|
| UUID | `manifest_version_id` | `uuid.UUID(value)` |
| 64 hex | `manifest_hash` | `re.fullmatch(r"[0-9a-fA-F]{64}", value)` |
| ISO8601 | `generated_at`, `valid_until`, `fetched_at` | Опционально на этом шаге (может быть null) |
| UUID | `manifest_item_id` | `uuid.UUID(value)` |
| Safe filename | `filename` | Нет `../`, `\`, `/`, `C:\`, absolute |
| 64 hex | `sha256` | `re.fullmatch(r"[0-9a-fA-F]{64}", value)` |
| ≥ 0 int | `size_bytes`, `duration_ms`, `order` | `isinstance(value, int) and value >= 0` |
| Non-empty str | `content_type` | MIME-like (хотя бы `\w+/\w+`) |
| List | `items` | `isinstance(value, list)` |
| Object | каждый item | `isinstance(value, dict)` |

### 9.3 Что НЕ должно быть в локальном manifest

- ❌ `media_path` с директориями
- ❌ `local_path`, `file_path`, `filesystem_path`
- ❌ `token`, `secret`, `jwt`, `api_key`
- ❌ `authorization`, `bearer`
- ❌ `device_secret`
- ❌ `stacktrace`
- ❌ Любые внутренние backend-поля (`schedule_item_id`, `publication_target_id` — не экспортировать)

### 9.4 Что ДОЛЖНО быть

- ✅ Только поля, перечисленные в локальном формате (секция 4)
- ✅ Все поля валидированы
- ✅ Безопасные filename без директорий
- ✅ Совместимость с `manifest_reader.py`

---

## 10. Будущие файлы (НЕ создавать на этом шаге)

### 10.1 Python-модуль

```
apps/kso_sidecar_agent/kso_sidecar_agent/manifest_store.py
```

**Функции:**
- `normalize_manifest_snapshot(snapshot: ManifestSnapshot, now=None) -> dict`
- `write_current_manifest(root: str, data: dict) -> None`
- `read_current_manifest(root: str) -> dict`
- `manifest_store_status(root: str) -> dict`
- `validate_local_manifest(data: dict) -> None`
- `derive_filename(manifest_item_id: str, content_type: str) -> str`
- `derive_content_type(media_path: str) -> str`
- `EXT_TO_MIME: dict[str, str]` — карта расширений

### 10.2 Тесты

```
apps/kso_sidecar_agent/tests/test_manifest_store.py
```

**Тестовые сценарии:**
- `normalize` current served — все поля на месте
- `normalize` by_id response — все поля на месте
- `not_modified` не перезаписывает файл
- `no_manifest` не создаёт пустой manifest
- `filename` из `manifest_item_id` + расширения
- unsafe `media_path` не попадает в локальный manifest
- path traversal в filename → reject
- forbidden key/value → reject
- atomic write: нет `.tmp` после записи
- atomic write: symlink target → reject
- `manifest_store_status` — нет полного manifest/config dump
- совместимость с `simulator.manifest_reader.read_manifest()`
- нет token/secret/local_path в выходном файле
- `content_type` из расширения: `.jpg` → `image/jpeg`, `.unknown` → `application/octet-stream`
- `order` приоритет: `order` > `loop_position` > `spot_position` > `0`

---

## 11. Будущие CLI-команды (НЕ реализовывать на этом шаге)

```bash
# Показать статус локального manifest
python3 -m kso_sidecar_agent.cli manifest-status --root /tmp/kso-agent-root
# Вывод: present/absent, manifest_version_id, items_count, valid_until, expired

# (sync-manifest будет отдельным шагом после manifest_store)
# python3 -m kso_sidecar_agent.cli sync-manifest --root /tmp/kso-agent-root --dev-secret-store
```

---

## 12. Что НЕ реализуем на этом шаге

- ❌ `manifest_store.py` (код)
- ❌ Запись manifest на диск
- ❌ `sync-manifest` CLI
- ❌ Media download
- ❌ Media cache
- ❌ Media verify (sha256)
- ❌ Playback
- ❌ PoP
- ❌ Backend changes
- ❌ Новые backend endpoints
- ❌ Real backend calls
- ❌ `content_type` из `/media/{id}/metadata` (только из расширения `media_path`)
- ❌ `size_bytes` из реального файла (всегда `0`)
- ❌ `campaign_id` из backend (всегда `null`)
- ❌ `valid_until` из runtime config TTL (всегда `null`)
- ❌ SHA256-файл `current_manifest.sha256` (будет отдельно)

---

## 13. Risks

| Риск | Mitigation |
|---|---|
| Backend меняет формат ответа | Normalizer изолирован в одном модуле — легко адаптировать |
| `content_type` из расширения неточен | В будущем — из `GET /media/{id}/metadata` (реальный MIME) |
| `size_bytes = 0` неудобно КСО ПО | В будущем — из реального файла после download |
| Backend может добавить поле `content_type` | Normalizer должен проверять: есть в backend → использовать, нет → derive из расширения |
| Simulator `manifest_reader.py` меняется | Локальный формат должен строго следовать контракту `kso_local_interface_contract.md` |
| КСО ПО читает manifest во время atomic write | `os.replace()` атомарен — КСО ПО видит либо старый, либо новый файл |

---

## 14. Совместимость

| Компонент | Статус |
|---|---|
| `ManifestClient` (шаг 25.17) | ✅ Совместим — возвращает `ManifestSnapshot` с `items`, `manifest_version_id`, `manifest_hash` |
| `kso_local_interface_contract.md` | ✅ Строго следует формату `manifest/current_manifest.json` |
| `kso_sidecar_agent_design.md` | ✅ Компонент LocalFileStore → Manifest Local Store |
| `simulator/manifest_reader.py` | ✅ Совместим — ожидает те же поля, те же правила валидации |
| Backend | ✅ Не требует изменений — работает с существующими endpoint'ами |

---

## 15. Проверка

- [x] Документ создан
- [x] Нет реальных secrets/tokens
- [x] Не утверждает, что manifest store уже реализован
- [x] Совместим с ManifestClient
- [x] Совместим с local interface contract
- [x] Совместим с simulator manifest_reader.py
- [x] Не требует backend changes
