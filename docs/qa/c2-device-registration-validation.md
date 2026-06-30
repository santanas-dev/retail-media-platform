# C.2 — Device Registration Validation

> **Дата:** 2026-07-01
> **Этап:** C.2 — Device Registration Validation (аудит + тесты)
> **Предыдущий:** C.1.1 (commit `8e01d89`, 39 tests)
> **Результат:** ✅ — GO для C.3

---

## Аудит registration flow

Device Gateway уже имеет полноценный registration flow. C.2 **не создавал** новый — провёл аудит и добавил тесты.

### Admin API (user permissions)

| Endpoint | Method | Permission |
|---|---|---|
| `/api/gateway-devices` | POST | `devices.gateway.manage` |
| `/api/gateway-devices` | GET | `devices.gateway.read` |
| `/api/gateway-devices/{id}` | GET/PUT | `devices.gateway.read` / `manage` |
| `/api/gateway-devices/{id}/credentials` | POST | `devices.gateway.credentials` |
| `/api/gateway-devices/{id}/credentials/{id}/revoke` | POST | `devices.gateway.credentials` |
| `/api/gateway-devices/{id}/heartbeats` | GET | `devices.gateway.read` |
| `/api/gateway-devices/{id}/events` | GET | `devices.gateway.read` |

### Device API (JWT device auth, no user permission)

| Endpoint | Auth |
|---|---|
| `POST /auth/token` | Нет (anonymous) |
| Все остальные device endpoints | `authenticate_device()` (JWT) |

---

## Device Identity Lifecycle

```
 ┌─────────┐    register    ┌──────────┐   first heartbeat   ┌────────┐
 │ (create) │──────────────→│ pending   │───────────────────→│ active  │
 └─────────┘               └──────────┘                     └────────┘
                                  │                              │
                                  │ disable/retire          lost │ (no heartbeat)
                                  ▼                              ▼
                            ┌──────────┐                  ┌────────┐
                            │ disabled  │                  │  lost   │
                            │ retired   │                  └────────┘
                            └──────────┘
```

**Состояния:**
- `pending` — зарегистрирован, ждёт первого heartbeat
- `active` — работает, отправляет heartbeat
- `lost` — heartbeat пропал (может аутентифицироваться)
- `disabled` — админ отключил (auth denied, heartbeat denied)
- `retired` — списан (auth denied, heartbeat denied)

**Валидация при регистрации:**
- `device_code`: unique, `[a-z0-9_-]+`, 1–64 chars
- `channel_id`: required, FK
- `store_id`: required, FK
- `physical_device_id`: optional, валидируется цепочка physical→logical→surface→store
- `logical_carrier_id`: optional
- `display_surface_id`: optional
- `status`: default "pending"

**Статусные переходы (update_device):**
- `disabled`/`retired` → устанавливается `disabled_at`
- Возврат к `active`/`pending`/`lost` → `disabled_at = None`
- Реактивация логируется как `device_reactivated`

---

## Credential Lifecycle

```
 ┌──────────────────┐   create_credential   ┌──────────────┐
 │ GatewayDevice    │──────────────────────→│ shared_secret │
 │ (active)         │   (1 active max)       │ (active)      │
 └──────────────────┘                       └──────────────┘
                                                    │
                                          revoke    │ rotate (revoke old → create new)
                                                    ▼
                                            ┌──────────────┐
                                            │ shared_secret │
                                            │ (revoked)     │
                                            └──────────────┘
                                            Все sessions revoked
```

**Создание credential:**
- Генерация: `secrets.token_hex(32)` — 64 hex chars
- Хранение: bcrypt hash в `secret_hash`, НИКОГДА raw
- Fingerprint: SHA-256 secret (односторонний)
- Секрет возвращается **ОДИН раз** в `DeviceCredentialCreatedResponse`
- `DeviceCredentialResponse` (GET/PUT) НЕ содержит секрет
- Нельзя иметь два активных shared_secret одновременно

**Отзыв credential:**
- `credential.status = "revoked"`, `revoked_at = now`
- Все сессии credential немедленно отозваны
- Логируется как `credential_revoked`

**Аутентификация:**
- `bcrypt.checkpw()` — timing-safe сравнение
- Неизвестный device → 401 "Invalid device credentials" (без раскрытия существования)
- Неверный секрет → 401 "Invalid device credentials" (то же сообщение)
- Disabled/retired → 401 (до проверки секрета)

**JWT Claims:**
- `sub`: `device:{id}`
- `type`: `device`
- `aud`: `device-gateway`
- `device_id`, `device_code`
- `session_id`
- `iat`, `exp`
- JWT-секрет: `effective_device_jwt_secret` из settings

**Session:**
- `access_token_hash`: SHA-256 токена (не хранится raw)
- `expires_at`: `DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES`
- `revoked_at`: устанавливается при отзыве credential или сессии

---

## Validation Rules (подтверждены или усилены C.2)

| Rule | Status | Test |
|---|---|---|
| device_code pattern `[a-z0-9_-]+` | ✅ | `test_schema_device_code_pattern` |
| device_code 1-64 chars | ✅ | `test_schema_device_code_pattern` |
| channel_id required | ✅ | `test_channel_id_required` |
| store_id required | ✅ | `test_store_id_required` |
| Secret shown only once | ✅ | `test_create_credential_returns_secret_only_once` |
| secret_hash not in any response | ✅ | `test_credential_secret_hash_never_in_response` |
| bcrypt for storage | ✅ | `test_create_credential_service_uses_bcrypt` |
| bcrypt.checkpw for auth | ✅ | `test_device_auth_uses_bcrypt_checkpw` |
| Duplicate active credential rejected | ✅ | `test_create_credential_rejects_duplicate_active` |
| Revoke also revokes sessions | ✅ | `test_revoke_credential_revokes_all_sessions` |
| Disabled device auth denied | ✅ | `test_disabled_device_auth_rejected` |
| Retired device auth denied | ✅ | `test_retired_device_auth_rejected` |
| Lost device can auth | ✅ | `test_lost_device_can_attempt_auth` |
| JWT minimal claims | ✅ | `test_jwt_claims_are_minimal` |
| JWT has expiry | ✅ | `test_jwt_has_expiry` |
| JWT type=device claim | ✅ | `test_jwt_device_type_claim` |
| Auth response no secret | ✅ | `test_auth_response_has_no_secret` |
| Admin endpoints require permission | ✅ | `test_admin_create_device_requires_permission` |
| Device endpoints no user permission | ✅ | `test_device_auth_no_user_permission` |
| All device endpoints use authenticate_device | ✅ | `test_all_device_endpoints_use_authenticate_device` |
| authenticate_device checks status | ✅ | `test_authenticate_device_checks_status` |
| Timing-safe compare exists | ✅ | `test_timing_safe_compare_exists` |
| Unknown device same error as wrong secret | ✅ | `test_unknown_device_returns_same_error_as_wrong_secret` |
| _log_event never logs secret | ✅ | `test_auth_log_event_does_not_log_secret` |
| Revoked credential sessions revoked | ✅ | `test_revoked_credential_sessions_revoked` |
| Reactivation clears disabled_at | ✅ | `test_update_device_handles_reactivation` |
| Device stores linkage chain | ✅ | `test_device_stores_linkage_chain_fields` |

---

## Safety Boundary

Все функции регистрации/аутентификации проверены на отсутствие импортов:

- `publications` (сервис/модели) — не импортируется ✅
- `GeneratedManifest` — не используется ✅
- `generate_manifests` — не вызывается ✅
- `publish_batch` — не вызывается ✅
- `KsoPlacement` — не используется ✅
- KSO endpoint — присутствует и не изменён ✅
- Universal manifest endpoint — присутствует и не изменён ✅
- PoP ingestion — не изменён ✅

---

## Test Results

| Слой | Результат |
|---|---|
| **C.2 targeted (NEW)** | **39/39** ✅ |
| C.1 + C.1.1 targeted | 39/39 ✅ |
| Legacy device gateway auth | 13/13 ✅ |
| Backend collection | **1322** (0 errors) |

### Delta

| Метрика | C.1.1 | C.2 | Δ |
|---|---|---|---|
| Gateway tests | 39 + 13 = 52 | **39 + 39 + 13 = 91** | +39 |
| Backend collection | 1283 | **1322** | +39 |

---

## Сохранность подтверждена

- KSO endpoint — не менялся ✅
- GeneratedManifest — не менялся ✅
- Publication flow — не менялся ✅
- Universal manifest endpoint — не менялся ✅
- PoP ingestion — не менялся ✅
- Admin API — не менялся ✅
- Auth model global — не менялся ✅
- Миграции — не созданы ✅
- БД — не менялась ✅
- Portal — не менялся ✅

---

## Файлы изменены

| Файл | Действие |
|---|---|
| `backend/tests/test_device_registration_c2.py` | 🆕 39 тестов |
| `backend/tests/test_device_gateway_universal_c1.py` | 🔄 `_code_lines` fix (regex docstring removal) |

---

## GO/NO-GO для C.3

**GO ✅ для C.3 — Heartbeat/Status Validation.**
