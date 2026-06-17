# Device Gateway Foundation

## Overview

Шаг 10 — безопасный фундамент Device Gateway через который устройства обращаются к backend (pull model). На этом шаге: без manifest delivery, без media delivery, без PoP, без плеера.

**Принцип:** устройства всегда сами инициируют соединение с сервером.

---

## Security Principles

| Principle | Implementation |
|-----------|---------------|
| Devices initiate connections | Only device → backend, never backend → device |
| No tokens in URLs | All tokens in `Authorization: Bearer` header |
| No presigned URLs | Media delivery — future step |
| No passwords in manifest | Enforced in Step 9 |
| device_service has no admin API access | Empty permission matrix |
| No shared device password | Each device has its own `device_secret` |
| Secrets never stored plaintext | Only `secret_hash` (bcrypt) in DB |
| Secret shown once | On credential creation, then only hash in DB |
| Device token ≠ user token | Separate JWT secret, separate claim type |
| Separate JWT secret in production | `DEVICE_JWT_SECRET` must be set explicitly in staging/production |

**mTLS/device certificates:** deferred to a separate production-hardening step.

---

## Tables

### `gateway_devices` — device identity

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| device_code | VARCHAR(64) UNIQUE | Device login (lowercase `^[a-z0-9_-]+$`) |
| device_name | VARCHAR(255) | |
| physical_device_id | UUID FK, nullable | |
| logical_carrier_id | UUID FK, nullable | |
| display_surface_id | UUID FK, nullable | |
| channel_id | UUID FK NOT NULL | |
| store_id | UUID FK NOT NULL | |
| status | VARCHAR(20) | pending, active, disabled, lost, retired |
| last_seen_at | TIMESTAMPTZ | Updated on heartbeat |
| registered_at | TIMESTAMPTZ | |
| disabled_at | TIMESTAMPTZ | |
| comment | TEXT | |

### `device_credentials` — device secrets

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| gateway_device_id | UUID FK | |
| credential_type | VARCHAR(20) | shared_secret, certificate |
| secret_hash | VARCHAR(255) | bcrypt hash — plaintext NEVER stored |
| fingerprint | VARCHAR(64) | SHA-256 of secret (irreversible) |
| status | VARCHAR(20) | active, revoked, expired |

Only one active `shared_secret` per device. Rotation with overlapping keys — future step.

### `device_sessions` — short-lived device access tokens

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| gateway_device_id | UUID FK | |
| credential_id | UUID FK | Links session to credential |
| access_token_hash | VARCHAR(64) | SHA-256 of JWT |
| expires_at | TIMESTAMPTZ NOT NULL | |
| revoked_at | TIMESTAMPTZ | |
| client_ip | VARCHAR(45) | From `request.client.host` |

Revoking a credential revokes all sessions for that credential.

### `device_heartbeats` — heartbeat history

| Column | Type |
|--------|------|
| id | UUID PK |
| gateway_device_id | UUID FK |
| status | ok, warning, error |
| device_time, app_version, os_version, storage_free_mb, cache_items_count, current_manifest_hash | optional |
| details_json | JSONB (validated: no forbidden keys, max 64KB) |

### `device_events` — audit log

| Column | Type |
|--------|------|
| id | UUID PK |
| gateway_device_id | UUID FK, nullable |
| event_type | device_registered, credential_issued, credential_revoked, device_login_success, device_login_failed, heartbeat_received, device_disabled, device_reactivated, invalid_token, validation_failed |
| severity | info, warning, error |

---

## Auth Flow

```
1. Admin: POST /api/gateway-devices → creates device
2. Admin: POST /api/gateway-devices/{id}/credentials → creates credential
3. Response: device_secret (plaintext) — shown ONCE
4. Device stores: {device_code, device_secret}
5. Device: POST /api/device-gateway/auth/token
   → backend verifies bcrypt(secret, secret_hash)
   → creates session, returns JWT
6. Device uses JWT for /api/device-gateway/*
```

### Device JWT Claims

```json
{
  "sub": "device:<uuid>",
  "type": "device",
  "aud": "device-gateway",
  "device_id": "<uuid>",
  "device_code": "...",
  "session_id": "<uuid>",
  "iat": ...,
  "exp": ...
}
```

### Token Validation (get_current_device)

1. Decode JWT with `DEVICE_JWT_SECRET`
2. Verify `type == "device"` and `aud == "device-gateway"`
3. Extract `device_id` from `sub: "device:<uuid>"`
4. Load GatewayDevice, verify status in (pending, active, lost)
5. Load DeviceSession, verify not revoked/expired
6. Verify token hash matches `access_token_hash`
7. Verify credential still active
8. **Device token will never work on human API** (type check fails for `get_current_user`)
9. **User token will never work on device API** (type check fails for `get_current_device`)

---

## Status Machine

```
pending ──(heartbeat)──→ active
lost    ──(heartbeat)──→ active
active  ──(no heartbeat)──→ lost (future cron)
active  ──(admin disable)──→ disabled
disabled ──(admin reactivate)──→ pending
any     ──(admin retire)──→ retired
```

Auth/token allowed: pending, active, lost
Auth/token denied: disabled, retired

---

## API Endpoints

### Admin API (human, role-based)

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/gateway-devices | devices.gateway.manage |
| GET | /api/gateway-devices | devices.gateway.read |
| GET | /api/gateway-devices/{id} | devices.gateway.read |
| PUT | /api/gateway-devices/{id} | devices.gateway.manage |
| POST | /api/gateway-devices/{id}/credentials | devices.gateway.credentials |
| POST | /api/gateway-devices/{id}/credentials/{cid}/revoke | devices.gateway.credentials |
| GET | /api/gateway-devices/{id}/heartbeats | devices.gateway.read |
| GET | /api/gateway-devices/{id}/events | devices.gateway.read |

### Device API (machine, device JWT)

| Method | Path | Auth |
|--------|------|------|
| POST | /api/device-gateway/auth/token | device_code + device_secret |
| GET | /api/device-gateway/me | Device JWT |
| POST | /api/device-gateway/heartbeat | Device JWT |

---

## Permissions (3 new, total 47)

| Permission | Admin | Ops | SecAdmin | Analyst | AdMgr | Approver | Advertiser | DeviceSvc |
|------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| devices.gateway.read | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| devices.gateway.manage | ✅ | ✅ | ✅ | — | — | — | — | — |
| devices.gateway.credentials | ✅ | ✅ | ✅ | — | — | — | — | — |

---

## Config

```
DEVICE_JWT_SECRET         — separate from SECRET_KEY in production
DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES = 60
DEVICE_HEARTBEAT_TIMEOUT_MINUTES = 15
DEVICE_HEARTBEAT_DETAILS_MAX_BYTES = 65536
```

---

## What's NOT in Step 10

- ❌ Manifest delivery
- ❌ Media delivery
- ❌ PoP / Player
- ❌ Device registration self-service
- ❌ Push commands / Remote control / MDM
- ❌ mTLS / certificates
- ❌ Presigned URLs
- ❌ Refresh tokens for devices


---

## Manifest Delivery (Step 11)

### Overview

Authorized devices pull **published manifests** that belong to their target (display_surface / logical_carrier). Pull model only — no push, no media delivery, no PoP.

### Device Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/device-gateway/manifest/current?current_manifest_hash=...` | Latest published manifest for device |
| `GET` | `/api/device-gateway/manifest/{manifest_version_id}` | Specific manifest (404 if not device's) |

Both endpoints require device JWT token (Bearer). User tokens return 401.

### Admin Endpoint

| Method | Path | Permission |
|--------|------|------------|
| `GET` | `/api/gateway-devices/{id}/manifest-requests?request_status=&date_from=&date_to=&limit=` | `devices.gateway.read` |

### Response Formats

**Manifest served:**
```json
{
  "status": "served",
  "manifest_version_id": "uuid",
  "manifest_hash": "sha256",
  "published_at": "ISO8601",
  "manifest": { ... }
}
```

**Not modified:**
```json
{
  "status": "not_modified",
  "manifest_version_id": "uuid",
  "manifest_hash": "sha256"
}
```

**No manifest:**
```json
{
  "status": "no_manifest"
}
```

### Match Logic

Priority-based matching between `gateway_device` and `publication_targets`:

1. `gateway_device.display_surface_id` → match `publication_targets.display_surface_id`
2. `gateway_device.logical_carrier_id` → match `publication_targets.logical_carrier_id`
3. `gateway_device.physical_device_id` → find logical_carriers → match publication_targets

All matches additionally require: `channel_id` and `store_id` equality.
No match → `{"status": "no_manifest"}`.

### Published Only

Only manifests where ALL three statuses are `published`:
- `publication_batches.status = "published"`
- `publication_targets.status = "published"`
- `manifest_versions.status = "published"`

### Forbidden Key Validation

Manifest JSON is checked recursively for forbidden keys. If found → **500 Manifest validation failed** (manifest is NOT modified/sanitized). Hash integrity is preserved.

Forbidden keys: `access_token`, `refresh_token`, `token`, `jwt`, `password`, `secret`, `credential`, `credentials`, `authorization`, `cookie`, `api_key`, `private_key`, `public_key`.

### Audit (`device_manifest_requests`)

Every manifest request is logged with status: `served`, `not_modified`, `not_found`, `forbidden`, `validation_failed`.

### New Table

- `device_manifest_requests` — audit log only, not PoP

### Config

- `DEVICE_MANIFEST_REQUEST_DETAILS_MAX_BYTES` = 65536 (default)


## Step 12: Device Media Delivery Core

### Overview

Шаг 12 — позволяет авторизованному устройству безопасно скачать медиафайлы, указанные в его published manifest. Pull-модель: устройство запрашивает media через backend по `manifest_item_id`, backend проверяет права, валидирует object key и MIME, отдаёт файл через StreamingResponse из MinIO. Без presigned URLs, без PoP, без плеера.

### Endpoints

**Device:**
- `GET /api/device-gateway/media/{manifest_item_id}/metadata` — безопасные метаданные (sha256, content_type, size_bytes, duration_ms)
- `GET /api/device-gateway/media/{manifest_item_id}` — download media через StreamingResponse (64 KB chunks)

**Admin:**
- `GET /api/gateway-devices/{device_id}/media-requests` — аудит запросов media

### Authentication

Только device JWT (`Authorization: Bearer ***`). User token → 401. Device token на human API → 401.

### Match Logic

Используется та же `_match_publication_targets`, что в Шаге 11:
- `display_surface_id` → `logical_carrier_id` → `physical_device_id`
- Всегда дополнительно проверяются `channel_id` и `store_id`
- Device получает media только своего `publication_target`

### Publication Chain Validation

- `publication_batch.status` = `published`
- `publication_target.status` = `published`
- `manifest_version.status` = `published`
- Draft/approved/cancelled → 404

### Object Key Validation

- Не пустой, длина ≤ 500
- Начинается строго с `creatives/`
- Не абсолютный, не содержит `..`, `\`, `?`, `#`, `%`
- Допустимые символы: латиница, цифры, `/`, `_`, `-`, `.`

### MIME Allowlist

Разрешены: `image/jpeg`, `image/png`, `video/mp4`, `video/webm`
Запрещены: SVG, HTML, JS, ZIP, любые неизвестные типы

MIME берётся из `renditions.mime_type` (приоритет) → `creative_versions.mime_type` (fallback). Проверяется консистентность с MinIO `stat_object.content_type`.

### Not Modified

- Metadata: `?client_cached_sha256=<sha256>` → 200 `{"status": "not_modified"}`
- Download: `?client_cached_sha256=<sha256>` → 304 Not Modified (без тела)

### StreamingResponse

- MinIO `get_object` → `response.stream(amt=64KB)`
- Headers: `Content-Type`, `Content-Length`, `X-Content-SHA256`, `ETag`, `Cache-Control: private, max-age=86400`
- MinIO connection закрывается через `BackgroundTask` (`close()` + `release_conn()`)

### Security

- Device token только в Authorization header
- User token не работает на media endpoints
- Device token не работает на human API
- Presigned URLs не используются
- MinIO credentials не раскрываются
- Ошибки безопасные (без bucket/stacktrace)
- `details_json` не содержит secret/token/password

### Device Statuses

- `active`, `pending`, `lost` — могут скачивать
- `disabled`, `retired` — не могут (401/403)

### Audit (`device_media_requests`)

Статусы: `served`, `not_modified`, `not_found`, `forbidden`, `validation_failed`, `storage_error`

Каждый запрос логируется с:
- `gateway_device_id`, `manifest_item_id`, `manifest_version_id`, `publication_target_id`
- `media_path`, `expected_sha256`, `client_cached_sha256`, `response_size_bytes`
- `ip_address`, `user_agent`, `message`, `details_json`

### Device Events

Новые event_type: `media_served`, `media_not_modified`, `media_not_found`, `media_forbidden`, `media_validation_failed`, `media_storage_error`

### New Table

- `device_media_requests` — аудит запросов media

### Config

- `DEVICE_MEDIA_REQUEST_DETAILS_MAX_BYTES` = 65536 (default)


## Step 13: PoP Ingest Core

### Overview

Шаг 13 — авторизованное устройство отправляет proof-of-play события: факт воспроизведения/показа media из его опубликованного manifest. Система валидирует, дедуплицирует, сохраняет в `proof_of_play_events`. Без отчётов, BI, SLA, компенсаций, batch endpoint.

### Endpoints

**Device:**
- `POST /api/device-gateway/pop/events` — submit single PoP event

**Admin:**
- `GET /api/gateway-devices/{device_id}/pop-events` — audit list (filters: `validation_status`, `play_status`, `manifest_item_id`, `date_from`, `date_to`, `limit`, `offset`)

### Authentication

Только device JWT (`Authorization: Bearer **`). User token → 401. Device token на human API → 401.

### Payload

```json
{
  "device_event_id": "uuid",
  "manifest_item_id": "uuid",
  "played_at": "ISO8601",
  "duration_ms": 15000,
  "play_status": "completed",
  "media_sha256": "64 hex chars",
  "schedule_item_id": "uuid (optional, cross-check)",
  "player_version": "string (optional, max 64)",
  "details_json": {}
}
```

### Validation & Rejection

**Порядок проверок (fail-fast, все rejected → HTTP 200):**

| # | Проверка | rejection_reason |
|---|---|---|
| 1 | `device.status ∈ {active, pending, lost}` | `device_disabled` |
| 2 | `manifest_item` существует | `manifest_item_not_found` |
| 3 | `manifest_version.status = published` | `manifest_not_published` |
| 4 | `publication_target.status = published` | `publication_target_not_published` |
| 5 | `publication_batch.status = published` | `publication_batch_not_published` |
| 6 | Device ↔ target match (Шаг 11 logic) | `manifest_item_not_allowed` |
| 7 | `media_sha256` совпадает с `manifest_items.sha256` | `media_sha256_mismatch` |
| 8 | `schedule_item_id` совпадает (если передан) | `schedule_item_mismatch` |
| 9 | `played_at ≤ now + 5 min` | `played_at_too_future` |
| 10 | `played_at ≥ now - 7 days` | `played_at_too_old` |
| 11 | `0 ≤ duration_ms ≤ 86_400_000` | `duration_ms_negative` / `duration_ms_too_large` |
| 12 | `play_status ∈ valid set` | `invalid_play_status` |
| 13 | `details_json` без forbidden keys | `forbidden_keys_in_details` |
| 14 | `details_json ≤ 65536 bytes` | `details_too_large` |

**Valid play_status values:** `started`, `completed`, `interrupted`, `skipped`, `failed`

### Deduplication

- `UNIQUE(gateway_device_id, device_event_id)` на уровне БД
- Дубликат → HTTP 200 `{"status": "duplicate", "proof_event_id": "..."}`
- Создаётся `device_event` с типом `pop_event_duplicate`

### Response

**Accepted:**
```json
HTTP 200
{"status": "accepted", "proof_event_id": "uuid"}
```

**Duplicate:**
```json
HTTP 200
{"status": "duplicate", "proof_event_id": "uuid"}
```

**Rejected:**
```json
HTTP 200
{"status": "rejected", "reason": "manifest_item_not_allowed"}
```

### Match Logic

Та же, что в Шаге 11: `display_surface_id → logical_carrier_id → physical_device_id`, с обязательной проверкой `channel_id` и `store_id`.

### Серверные поля

Сервер заполняет из `manifest_items`:
- `manifest_version_id`, `publication_target_id`, `schedule_item_id`
- `campaign_id`, `campaign_rendition_id`, `rendition_id`, `creative_version_id`
- `expected_sha256` (из `manifest_items.sha256`)
- `ip_address` (из `request.client.host`)
- `user_agent` (limit 500 chars)

Устройство НЕ передаёт эти поля (кроме optional `schedule_item_id` для cross-check).

### Rejected Records

Для rejected событий:
- Все FK nullable
- `duration_ms`, `play_status`, `media_sha256` сохраняются только при валидных значениях (DB-safe — без нарушения CHECK constraints)
- `rejection_reason` заполняется
- DB запись создаётся даже если `manifest_item_id` не найден

### Audit (`device_events`)

Новые event_type: `pop_event_accepted`, `pop_event_duplicate`, `pop_event_rejected`.

### New Table

- `proof_of_play_events` — все PoP события (accepted, duplicate, rejected)
  - FK: все `ON DELETE RESTRICT`, nullable для rejected сценариев
  - CHECK: `duration_ms IS NULL OR >= 0`, `media_sha256 IS NULL OR 64 hex`, `play_status IS NULL OR IN (...)`

### Config

```ini
POP_MAX_CLOCK_SKEW_SECONDS = 300       # 5 min future
POP_MAX_EVENT_AGE_DAYS = 7
POP_MAX_DURATION_MS = 86_400_000       # 24 hours
POP_DETAILS_MAX_BYTES = 65536
```

### Что НЕ в Шаге 13

- ❌ Batch PoP endpoint
- ❌ Отчёты, BI, план/факт, SLA, компенсации
- ❌ ClickHouse витрины
- ❌ Excel/PDF выгрузки
- ❌ Billing
- ❌ KSO player, transcoding
- ❌ Media retry / offline protocol
