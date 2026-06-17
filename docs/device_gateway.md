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
- ❌ Reports
