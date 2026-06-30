# C.0 — Device Gateway Pre-C Audit / Design Gate

> **Дата:** 2026-07-01
> **Этап:** C.0 — Pre-C Audit
> **Статус:** Design Gate — GO для C.1 (gap closure)

---

## Executive Summary

Device Gateway уже реализован на **80%** как production-ready модуль:
- GatewayDevice модель с 8 связанными таблицами
- JWT-based device auth (не mTLS)
- Admin API (CRUD устройств, credentials, heartbeats, manifest requests)
- Device API (auth, /me, heartbeat, manifest, media, PoP, runtime config)
- KSO manifest delivery (из GeneratedManifest)
- PoP ingestion (single + batch)
- Runtime config с ETag/304

**Gap:** manifest delivery использует legacy `GeneratedManifest` (KSO-specific).
Универсальный manifest (UniversalManifestV1) пока не доставляется через Gateway.

**Рекомендация:** C.1 = закрыть gap: добавить universal manifest delivery
через Device Gateway без ломки KSO legacy path.

---

## 1. Existing Device Gateway Architecture

### 1.1 Data Model (8 таблиц)

| Таблица | Назначение | FK |
|---|---|---|
| `gateway_devices` | Device identity | physical_devices, logical_carriers, display_surfaces, channels, stores |
| `device_credentials` | Shared secret или certificate | gateway_devices |
| `device_sessions` | JWT sessions | gateway_devices, device_credentials |
| `device_heartbeats` | Device health/status | gateway_devices |
| `device_events` | Security/audit events | gateway_devices |
| `device_manifest_requests` | Manifest pull audit | gateway_devices |
| `device_media_requests` | Media download audit | gateway_devices |
| `proof_of_play_events` | PoP ingestion | gateway_devices, gateway_devices (device_id) |
| `proof_of_play_batches` | Batch PoP ingestion | gateway_devices |

### 1.2 GatewayDevice Model

| Поле | Тип | Связь |
|---|---|---|
| `device_code` | String(64) UNIQUE | Идентификатор устройства |
| `physical_device_id` | FK → physical_devices | Universal chain |
| `logical_carrier_id` | FK → logical_carriers | Universal chain |
| `display_surface_id` | FK → display_surfaces | Universal chain |
| `channel_id` | FK → channels | Universal chain |
| `store_id` | FK → stores | Организация |
| `status` | pending/active/disabled/retired | Lifecycle |

**GatewayDevice уже привязан к universal chain** (physical_devices, logical_carriers, display_surfaces, channels).

### 1.3 Auth Mechanism

- **JWT-based** (jose library)
- `POST /api/device-gateway/auth/token` → DeviceAuthRequest (device_code + credential_secret) → DeviceAuthResponse (access_token + refresh_token)
- `authenticate_device(request, db)` → (GatewayDevice, DeviceSession)
- Timing-safe hash comparison
- Session expiry, revocation support
- **Не mTLS** — shared secret модель

### 1.4 Device API Endpoints

| Endpoint | Метод | Аутентификация |
|---|---|---|
| `/auth/token` | POST | Shared secret |
| `/me` | GET | JWT |
| `/heartbeat` | POST | JWT |
| `/manifest/current` | GET + ETag | JWT |
| `/manifest/{id}` | GET | JWT |
| `/kso/{device_code}/manifest` | GET | JWT |
| `/media/{manifest_item_id}/metadata` | GET + 304 | JWT |
| `/media/{manifest_item_id}` | GET + 304 | JWT |
| `/media/kso/{media_ref}` | GET + 304 | JWT |
| `/pop/events` | POST | JWT |
| `/pop/events/batch` | POST | JWT |
| `/config/current` | GET + ETag/304 | JWT |
| `/manifest/{id}/apply` | POST | JWT |

### 1.5 Manifest Delivery (Current)

```
Device → /manifest/current → authenticate_device()
  → get_current_manifest() → ManifestVersion (PublicationBatch pipeline)
                               ИЛИ
  → /kso/{device_code}/manifest → GeneratedManifest (KSO pipeline)
```

**KSO manifest delivery:** `GET /kso/{device_code}/manifest` читает `GeneratedManifest` с `status=published` для заданного `device_code`. Возвращает `{status:"served", manifest, manifest_hash, ...}`.

**ManifestVersion delivery:** `GET /manifest/current` использует PublicationBatch → ManifestVersion pipeline.

**Gap:** Нет доставки UniversalManifestV1 через Gateway.

---

## 2. Existing Security / RLS / Audit

### 2.1 RBAC Permissions

| Permission | Область |
|---|---|
| `devices.gateway.manage` | Create/update devices |
| `devices.gateway.read` | List/get devices |
| `devices.gateway.credentials` | Create/revoke credentials |

### 2.2 Device Auth vs User Auth

- **Device endpoints** — `authenticate_device()` (JWT, не user session)
- **Admin endpoints** — `require_permission()` (user RBAC)
- Разделение чистое — устройства не используют user auth

### 2.3 Audit Trail

- `device_events` — security events
- `device_manifest_requests` — manifest pull audit
- `device_media_requests` — media download audit
- `device_heartbeats` — device status history
- PoP events имеют validation_status, play_status

### 2.4 Secrets Safety

- `FORBIDDEN_KEYS` в `publications/kso_manifest_projection.py` — защита KSO manifest
- `validate_no_secrets()` в универсальном manifest — 11 patterns
- JWT secret из `settings.effective_device_jwt_secret`

---

## 3. Gap Analysis: Universal Manifest Delivery

### 3.1 Что УЖЕ есть для Universal Manifest

| Компонент | Статус | Примечание |
|---|---|---|
| UniversalManifestV1 schema | ✅ B.5.1 | 10 Pydantic моделей |
| Universal manifest builder | ✅ B.5.2 | Из OrchestratorContext |
| Validation layer | ✅ B.5.3 | Preview/Final режимы |
| Legacy compatibility | ✅ B.5.4 | Option A: parallel preview |
| GatewayDevice → universal chain | ✅ | FK к physical_devices/channels |

### 3.2 Что НУЖНО для Universal Manifest Delivery

| Gap | Severity | Что нужно |
|---|---|---|
| **Manifest delivery использует только legacy** | 🔴 HIGH | Новый endpoint или расширение `/manifest/current` |
| **KSO manifest endpoint жёстко привязан к GeneratedManifest** | 🟡 MEDIUM | Universal endpoint должен использовать Placement → Orchestrator |
| **Device ↔ Placement mapping** | 🟡 MEDIUM | GatewayDevice.physical_device_id → PlacementTarget |
| **Manifest ETag/304 для universal** | 🟡 MEDIUM | Content hash из UniversalManifestV1 |
| **Preview vs Production manifest** | 🟢 LOW | Preview через simulation, production через publication |
| **No-secrets scan на delivery** | 🟢 LOW | Уже есть в обоих путях |

### 3.3 Что НЕ НУЖНО менять

- ❌ KSO manifest endpoint (`/kso/{device_code}/manifest`) — остаётся как есть
- ❌ GeneratedManifest — production path не меняется
- ❌ Publication flow — не меняется
- ❌ Device auth (JWT) — остаётся
- ❌ GatewayDevice модель — FKs уже верные

---

## 4. Recommended C Implementation Split

### C.1 — Universal Manifest Delivery (gap closure)

**Добавить в Device Gateway:**
- `GET /api/device-gateway/manifest/universal/current` — universal manifest для аутентифицированного устройства
- Service function: `get_universal_manifest(device, db)` — резолвит GatewayDevice → Placement → OrchestratorContext → UniversalManifestV1
- ETag/304 поддержка
- Preview режим (dry_run=true)
- **Не писать в generated_manifests**
- **Не менять KSO endpoint**
- **Не менять publication flow**

### C.2 — Device Registration Validation

**Существующий admin API уже есть** (`POST /gateway-devices`, `POST /credentials`).
Что добавить:
- Validation: device_code уникален, channel_id валиден
- Auto-link к physical_device по device_code
- Проверка статуса (pending → active after registration)

### C.3 — Heartbeat Enhancement

**Существующий endpoint уже есть** (`POST /heartbeat`).
Что добавить:
- Capability profile check (изменился ли профиль устройства)
- Player version tracking (уже может быть в user_agent)
- Status transition: offline → online, degraded detection

### C.4 — PoP Ingestion (уже есть)

`POST /pop/events` и `POST /pop/events/batch` уже работают.
Что добавить:
- Correlation с UniversalManifestV1 (manifest_id вместо KSO manifest_version_id)
- Validation для universal proof_type

### C.5 — Gateway Security/Audit Tests

- Unknown device denied
- Disabled/retired device denied
- Expired session denied
- Device can only access own manifest
- No cross-device data leakage
- Secrets not in manifest response
- Rate limiting tests

### C.6 — Closure Gate

---

## 5. Security Model

### Current: JWT shared-secret

```
Device → POST /auth/token (device_code + secret)
  → verify secret_hash
  → issue JWT (sub=device:UUID, aud=device-gateway, session_id)
  → Device uses JWT for all subsequent requests
```

### Future: mTLS (optional, не сейчас)

- Client certificate per device
- Certificate lifecycle (issue, renew, revoke)
- **Не требуется для C.1** — JWT достаточно

### Security Rules

| Правило | Статус |
|---|---|
| Device auth отделён от user auth | ✅ |
| Disabled device denied | ✅ (authenticate_device проверяет status) |
| Expired session denied | ✅ |
| Revoked credential denied | ✅ |
| Device видит только свой manifest | ⚠️ KSO endpoint проверяет; universal endpoint нужно добавить |
| No secrets in manifest response | ✅ (FORBIDDEN_KEYS + validate_no_secrets) |
| Rate limiting | ⚠️ Не реализовано (можно deferred) |

---

## 6. Data Model / Migration Decision

### В C.1: миграции НЕ нужны

- `gateway_devices` уже имеет FK к universal chain
- `device_manifest_requests` уже существует для аудита
- UniversalManifestV1 — in-memory, не требует таблицы

### Future (C.3+): возможные миграции

| Таблица | Назначение | Когда |
|---|---|---|
| `device_manifest_cache` | Кэш universal manifest per device | C.3+ |
| `device_capability_snapshots` | История capability profile | C.3 |
| `device_rate_limits` | Rate limiting counters | C.5 |

**НО:** на C.1 ничего не создавать.

---

## 7. API Decision

### C.1: добавить 1 новый device endpoint

```
GET /api/device-gateway/manifest/universal/current
  → authenticate_device()
  → resolve GatewayDevice → Placement → OrchestratorContext
  → build_universal_manifest_from_draft()
  → ETag/304
  → Response: UniversalManifestV1 JSON
```

### НЕ добавлять

- ❌ Public API (без device auth)
- ❌ Admin API для universal manifest (пока)
- ❌ KSO manifest changes
- ❌ Real publish
- ❌ PoP changes

---

## 8. Test Strategy (C.1)

| Тест | Тип |
|---|---|
| Device without placement receives no_manifest | Functional |
| Device with placement receives universal manifest | Functional |
| ETag/304 for unchanged manifest | Functional |
| manifest_version = "1.0" in response | Schema |
| signature_status = "unsigned" | Schema |
| No secrets in response JSON | No-secrets |
| Disabled device denied | Security |
| Cross-device manifest denied | Security |
| KSO endpoint unchanged (regression) | Regression |
| No generated_manifests writes | Isolation |
| Publication flow unchanged | Regression |

---

## 9. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Universal manifest endpoint interference с KSO | 🟡 MEDIUM | Отдельный endpoint, не трогать KSO |
| Device без placement | 🟡 MEDIUM | Возвращать статус "no_manifest" |
| GatewayDevice не привязан к placement | 🟡 MEDIUM | Резолвить через physical_device_id |
| Performance (Orchestrator chain per request) | 🟢 LOW | ETag/304 кэширование |
| Dual manifest format confusion | 🟢 LOW | Разные endpoints, device выбирает |

---

## 10. What Phase C Must Not Break

### B.5 Artifacts
- `universal_schema.py` — UniversalManifestV1 contracts
- `universal_builder.py` — build_universal_manifest_from_draft
- Validation helpers
- No-secrets patterns

### B.4 Artifacts
- `orchestrator/service.py` — build_manifest_context
- `orchestrator/contracts.py` — AdapterContract
- `orchestrator/simulation.py` — simulate_placement

### Legacy
- `generated_manifests` FK
- `generate_manifests()` / `publish_batch()`
- KSO projection
- Publication flow
- Placement API / Portal

---

## 11. GO/NO-GO

### GO ✅ для C.1 — Universal Manifest Delivery через Device Gateway

**Основание:**
- Device Gateway на 80% готов (auth, модели, API, PoP)
- Universal chain резолвится через GatewayDevice → physical_devices
- UniversalManifestV1 builder готов (B.5.2)
- Единственный gap: нет endpoint для universal manifest delivery
- KSO path не затрагивается (отдельный endpoint)
- Блокирующих рисков нет

**НЕ GO для C.2+ без отдельного approval после C.1.**
