# Шаг 20 — Device Content Sync State Core (Mini-Design)

## Статус
⚠️ На утверждении. Код не пишем, ждём подтверждения.

---

## 1. Цель

Backend-слой, через который устройство сообщает:
- какой manifest реально применён (applied/failed);
- какие media items закешированы / отсутствуют / повреждены;
- есть ли расхождение между manifest и локальным cache.

Это **не плеер**, не КСО-интеграция, не Android app, не frontend. Это storage + API.

---

## 2. Что уже есть (relation chain для валидации)

```
GatewayDevice  ──(channel_id, store_id)──▶  PublicationTarget
                                                      │
                                          ManifestVersion (manifest_hash)
                                                      │
                                              ManifestItem (sha256 — expected_sha256 для device)
```

**Валидация «свой/чужой»:** device может отчитываться только по ManifestVersion, чей PublicationTarget совпадает по `channel_id` + `store_id` с GatewayDevice. Этой цепочки достаточно — дополнительные FK не нужны.

---

## 3. Новые таблицы

### 3.1 `device_manifest_apply_events` — аудит попыток применения манифеста

```python
class DeviceManifestApplyEvent(Base):
    __tablename__ = "device_manifest_apply_events"

    id: UUID (PK, gen_random_uuid)
    gateway_device_id: UUID → FK gateway_devices.id (RESTRICT)
    manifest_version_id: UUID → FK manifest_versions.id (RESTRICT)
    manifest_hash: String(64)  — из запроса device, сверяется с manifest_versions.manifest_hash
    status: String(20)  — "applied" | "failed"
    device_reported_at: DateTime (nullable) — timestamp от устройства
    error_code: String(64) (nullable)
    message: String(512) (nullable)
    details_json: JSONB (default '{}')
    reported_at: DateTime — серверное время приёма
```

**Статусы:** `applied`, `failed`.

### 3.2 `device_current_manifest_states` — текущее состояние манифеста на устройстве

```python
class DeviceCurrentManifestState(Base):
    __tablename__ = "device_current_manifest_states"

    id: UUID (PK, gen_random_uuid)
    gateway_device_id: UUID → FK gateway_devices.id (RESTRICT), UNIQUE
    manifest_version_id: UUID → FK manifest_versions.id (RESTRICT, nullable)
    manifest_hash: String(64) (nullable)
    status: String(20)  — "applied" | "failed" | "unknown"
    last_applied_at: DateTime (nullable)
    last_failed_at: DateTime (nullable)
    updated_at: DateTime
    details_json: JSONB (default '{}')
```

**Статусы:** `applied`, `failed`, `unknown`.

**Логика:** upsert по `gateway_device_id`. При `applied` → обновляем `last_applied_at`. При `failed` → обновляем `last_failed_at`. Seed: для всех существующих устройств создаётся запись со статусом `unknown`.

### 3.3 `device_media_cache_reports` — аудит батч-отчётов о кеше

```python
class DeviceMediaCacheReport(Base):
    __tablename__ = "device_media_cache_reports"

    id: UUID (PK, gen_random_uuid)
    gateway_device_id: UUID → FK gateway_devices.id (RESTRICT)
    manifest_version_id: UUID → FK manifest_versions.id (RESTRICT)
    manifest_hash: String(64)
    total_items: Integer
    cached_count: Integer
    missing_count: Integer
    failed_count: Integer
    invalid_hash_count: Integer
    reported_at: DateTime — серверное время приёма
    device_reported_at: DateTime (nullable)
    details_json: JSONB (default '{}')
```

### 3.4 `device_media_cache_items` — состояние каждого media item на устройстве

```python
class DeviceMediaCacheItem(Base):
    __tablename__ = "device_media_cache_items"

    id: UUID (PK, gen_random_uuid)
    gateway_device_id: UUID → FK gateway_devices.id (RESTRICT)
    manifest_item_id: UUID → FK manifest_items.id (RESTRICT)
    manifest_version_id: UUID → FK manifest_versions.id (RESTRICT)
    rendition_id: UUID → FK renditions.id (RESTRICT, nullable)
    expected_sha256: String(64)  — из manifest_items.sha256, НЕ доверяем device
    reported_sha256: String(64) (nullable) — то, что device реально имеет
    status: String(20)  — "cached" | "missing" | "failed" | "invalid_hash" | "evicted"
    file_size_bytes: Integer (nullable)
    cached_at: DateTime (nullable) — timestamp от устройства
    last_seen_at: DateTime — серверное время приёма
    error_code: String(64) (nullable)
    message: String(512) (nullable)
    details_json: JSONB (default '{}')

    __table_args__ = (
        UniqueConstraint("gateway_device_id", "manifest_item_id"),
    )
```

**Статусы:** `cached`, `missing`, `failed`, `invalid_hash`, `evicted`.

**Логика upsert:** уникальность по `(gateway_device_id, manifest_item_id)`. При каждом отчёте — upsert. `expected_sha256` заполняется сервером из `manifest_items.sha256` (не доверяем device).

---

## 4. Device endpoints

Все под `/api/device-gateway`. Только device token. Human token → 401.

### 4.1 `POST /api/device-gateway/manifest/{manifest_version_id}/apply`

**Payload:**
```json
{
  "manifest_hash": "sha256hex — 64 hex chars",
  "status": "applied | failed",
  "device_reported_at": "ISO8601 (optional)",
  "message": "string, max 512 (optional)",
  "error_code": "string, max 64 (optional)",
  "details_json": {}
}
```

**Validation:**
- `manifest_hash`: 64 hex chars, должен совпадать с `manifest_versions.manifest_hash`
- `manifest_version_id`: должен принадлежать PublicationTarget, чей `channel_id` + `store_id` совпадает с GatewayDevice
- `status`: только `applied` или `failed`
- `details_json`: forbidden keys recursive, size limit
- `error_code`: max 64, `message`: max 512

**Side effects:**
- INSERT в `device_manifest_apply_events`
- UPSERT в `device_current_manifest_states` (обновляет `last_applied_at` / `last_failed_at`)

### 4.2 `POST /api/device-gateway/media/cache/report`

**Payload:**
```json
{
  "manifest_version_id": "uuid",
  "manifest_hash": "sha256hex",
  "device_reported_at": "ISO8601 (optional)",
  "items": [
    {
      "manifest_item_id": "uuid",
      "status": "cached | missing | failed | invalid_hash | evicted",
      "reported_sha256": "sha256hex (optional)",
      "file_size_bytes": 123456,
      "cached_at": "ISO8601 (optional)",
      "error_code": "string (optional)",
      "message": "string (optional)",
      "details_json": {}
    }
  ],
  "details_json": {}
}
```

**Validation:**
- `manifest_hash`: 64 hex chars, сверка с `manifest_versions.manifest_hash`
- `manifest_version_id`: принадлежит PublicationTarget данного устройства
- `items`: максимум **1000** элементов (предлагаемый лимит)
- Каждый `manifest_item_id`: должен принадлежать указанному `manifest_version_id` (через `manifest_items.manifest_version_id`)
- Если `status == "cached"`: `reported_sha256` обязателен и должен совпадать с `manifest_items.sha256` (expected_sha256)
- Если sha256 не совпадает → **автоматический статус `invalid_hash`** (не reject всего отчёта — принимаем, но помечаем)
- `file_size_bytes >= 0`
- Нет local file path
- `details_json`: forbidden keys recursive, size limit

**Side effects:**
- INSERT в `device_media_cache_reports` (один на весь отчёт, с агрегацией counts)
- UPSERT каждого item в `device_media_cache_items`

**Логика sha256 mismatch:** принимаем отчёт, но индивидуальный item получает статус `invalid_hash`. Это лучше, чем reject всего батча — device получает полную картину, а не «всё или ничего».

---

## 5. Admin / Internal endpoints

Все под `/api/device-operations/content-sync`. Permission: `devices.gateway.read`.

### 5.1 `GET /api/device-operations/content-sync/devices`

Список устройств с их текущим manifest state. Пагинация, фильтры: `status`, `store_id`, `channel_id`.

### 5.2 `GET /api/device-operations/content-sync/devices/{gateway_device_id}`

Детально по устройству: текущий manifest state + последние N cache items + краткая статистика.

### 5.3 `GET /api/device-operations/content-sync/manifest-events`

Список manifest apply events. Фильтры: `device_id`, `manifest_version_id`, `status`, `date_from`, `date_to`. Пагинация.

### 5.4 `GET /api/device-operations/content-sync/cache-reports`

Список cache reports. Фильтры: `device_id`, `manifest_version_id`, `date_from`, `date_to`. Пагинация.

### 5.5 `GET /api/device-operations/content-sync/cache-items`

Состояние media cache items. Фильтры: `device_id`, `manifest_item_id`, `status`. Пагинация.

---

## 6. Permissions

| Эндпоинт | Токен | Permission |
|----------|-------|-----------|
| Device manifest apply | device token | — (аутентификация устройства) |
| Device cache report | device token | — |
| Admin content-sync (все) | human token | `devices.gateway.read` |

Роли:
- `system_admin` → 200 ✅
- `security_admin` → 200 ✅
- `operations` → 200 ✅
- `analyst` → 200 ✅
- `advertiser` → 403 ❌
- `device_service` human role → 403 ❌
- device token на admin → 401 ❌
- human token на device → 401 ❌
- no token → 401 ❌

---

## 7. Security

- Forbidden keys recursive в `details_json` (переиспользуем существующий `FORBIDDEN_KEYS` + валидатор)
- Не храним local path, filesystem path
- Не храним `token`, `password`, `secret`, `api_key`, `private_key`
- Нет raw stacktrace, raw exception
- `message`: max 512 символов
- `error_code`: max 64 символов
- `details_json`: size limit (как в heartbeat)
- `items` в cache report: max 1000
- `expected_sha256` всегда берётся из `manifest_items.sha256` (серверная сторона), не из запроса device

---

## 8. Файлы

| Файл | Назначение |
|------|-----------|
| `backend/alembic/versions/020_device_content_sync_state.py` | Миграция: 4 таблицы |
| `backend/app/domains/device_operations/models.py` | 4 новых ORM-модели |
| `backend/app/domains/device_operations/schemas.py` | Pydantic-схемы (request + response) |
| `backend/app/domains/device_operations/service.py` | Бизнес-логика (validation, upsert, queries) |
| `backend/app/domains/device_operations/router.py` | Admin endpoints `/content-sync/...` |
| `backend/app/domains/device_gateway/schemas.py` | Device request/response схемы |
| `backend/app/domains/device_gateway/service.py` | Device-side логика (apply manifest, cache report) |
| `backend/app/domains/device_gateway/router.py` | Device endpoints |
| `docs/device_operations.md` | Документация Шага 20 |

**Почему модели в `device_operations`:** контент-синк — это operational-домен (мониторинг состояния устройств). Device gateway содержит только транспортные модели (auth, heartbeat, manifest delivery). Sync state — это analytics/operations data, а не gateway transport.

---

## 9. Проверки (smoke list)

- [ ] `alembic upgrade head` → 020
- [ ] `/health` → 200
- [ ] `POST manifest/{id}/apply` valid → 200, event создан, state обновлён
- [ ] `POST manifest/{id}/apply` wrong hash → 422
- [ ] `POST manifest/{id}/apply` чужой manifest → 404 (device не привязан к этому PublicationTarget)
- [ ] `POST manifest/{id}/apply` failed → 200, `last_failed_at` обновлён
- [ ] `POST media/cache/report` valid → 200
- [ ] Cache item with `cached` + correct sha256 → stored as `cached`
- [ ] Cache item with sha256 mismatch → stored as `invalid_hash` (не reject всего батча)
- [ ] Cache item чужого manifest_item → 400 (item не принадлежит manifest_version_id)
- [ ] Cache report с >1000 items → 422
- [ ] Forbidden key в `details_json` → 400
- [ ] `GET content-sync/devices` → 200
- [ ] `GET content-sync/devices/{id}` → 200
- [ ] `GET content-sync/cache-reports` → 200
- [ ] `GET content-sync/cache-items` → 200
- [ ] Device token на admin endpoints → 401
- [ ] Human token на device endpoints → 401
- [ ] Advertiser role → 403
- [ ] No secrets in responses
- [ ] `git status` clean

---

## 10. Commit message

```
✨ Add Device Content Sync State Core
```

---

## 11. Что НЕ делать в этом шаге

- ❌ КСО-плеер / КСО-адаптер
- ❌ Android player
- ❌ Frontend
- ❌ Auto-download / remote commands / push / scheduler
- ❌ Интеграция с health/alerts (отдельным шагом)
- ❌ Изменение PoP бизнес-логики
- ❌ Изменение runtime config
