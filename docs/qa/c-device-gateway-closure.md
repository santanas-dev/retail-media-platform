# C.5 — Device Gateway Audit / Security Tests & Closure Gate

> **Дата:** 2026-07-01
> **Этап:** C.5 — Closure Gate для Phase C (Device Gateway)
> **Предыдущий:** C.4 (commit `3ee274b`)
> **Результат:** ✅ — GO для Phase D (D.0 Design Gate)

---

## 1. Executive Summary

Phase C (Device Gateway) завершён. Gateway существует на ~80% с production-готовым кодом. Все этапы C.0–C.5 выполнены: аудит, universal manifest delivery, security gate, registration validation, heartbeat/status validation, manifest delivery validation, closure gate.

**Добавлено:** 1 новый device endpoint (`/manifest/universal/current`), 195 targeted тестов, 5 QA-документов.

**Сохранено:** KSO legacy flow, GeneratedManifest, publication flow, PoP, admin API, auth model — всё без изменений.

---

## 2. C Scope

Phase C фокусировалась на Device Gateway — устройство-ориентированном слое между физическими устройствами и backend-ом.

### C Commits

| Commit | Этап | Описание |
|---|---|---|
| `0d6ba19` | C.0 | Pre-C Design Gate — аудит, 80% готовности |
| `01932b1` | C.1 | Universal Manifest Delivery endpoint |
| `8e01d89` | C.1.1 | Security & Regression Gate (+27 тестов) |
| `2281bb7` | C.2 | Registration Validation (+39 тестов) |
| `68d0db2` | C.3 | Heartbeat/Status Validation (+44 теста) |
| `3ee274b` | C.4 | Manifest Pull/Delivery Validation (+60 тестов) |

---

## 3. Gateway Endpoint Inventory

### Device Endpoints (JWT device auth)

| Endpoint | Method | Auth | Device States | DB Write | Secrets |
|---|---|---|---|---|---|
| `/auth/token` | POST | None | Active/lost/pending | Yes (session) | No |
| `/me` | GET | Device JWT | Active/lost/pending | No | No |
| `/heartbeat` | POST | Device JWT | Active/lost/pending → active | Yes (heartbeat) | No |
| `/config/current` | GET | Device JWT | Active/lost/pending | Audit log | No |
| `/manifest/current` | GET | Device JWT | Active/lost/pending | Audit log | No |
| `/manifest/{id}` | GET | Device JWT | Active/lost/pending | Audit log | No |
| `/manifest/universal/current` | GET | Device JWT | Active/lost/pending | No (touch_device) | No |
| `/kso/{code}/manifest` | GET | Device JWT+code | Active/lost/pending | Audit log | No |
| `/pop/events` | POST | Device JWT | Active/lost/pending | Yes (PoP) | No |
| `/pop/events/batch` | POST | Device JWT | Active/lost/pending | Yes (PoP) | No |
| `/media/{id}` | GET | Device JWT | Active/lost/pending | Audit log | No |
| `/media/{id}/metadata` | GET | Device JWT | Active/lost/pending | Audit log | No |
| `/media/kso/{ref}` | GET | Device JWT | Active/lost/pending | Audit log | No |
| `/manifest/{id}/apply` | POST | Device JWT | Active/lost/pending | Yes | No |
| `/media/cache/report` | POST | Device JWT | Active/lost/pending | Yes | No |

### Admin Endpoints (user permissions)

| Endpoint | Method | Permission |
|---|---|---|
| `/gateway-devices` | POST | `devices.gateway.manage` |
| `/gateway-devices` | GET | `devices.gateway.read` |
| `/gateway-devices/{id}` | GET/PUT | `read`/`manage` |
| `/gateway-devices/{id}/credentials` | POST | `credentials` |
| `/gateway-devices/{id}/credentials/{id}/revoke` | POST | `credentials` |
| `/gateway-devices/{id}/heartbeats` | GET | `read` |
| `/gateway-devices/{id}/events` | GET | `read` |
| `/gateway-devices/{id}/manifest-requests` | GET | `read` |
| `/gateway-devices/{id}/media-requests` | GET | `read` |
| `/gateway-devices/{id}/pop-events` | GET | `read` |
| `/gateway-devices/{id}/pop-batches` | GET | `read` |

---

## 4. Device Auth Summary

| Компонент | Детали |
|---|---|
| Схема | JWT shared-secret (bcrypt) |
| Алгоритм | HS256 (`JWT_ALGORITHM`) |
| Claims | `sub`, `type`, `aud`, `device_id`, `device_code`, `session_id`, `iat`, `exp` |
| Валидация | `authenticate_device()`: decode JWT, load session, check revocation/expiry/device status |
| Timing-safe | `bcrypt.checkpw()` для проверки секрета |
| No oracle | 401 "Invalid device credentials" для unknown + wrong secret |
| Сессии | `DeviceSession`: `access_token_hash` (SHA-256), `expires_at`, `revoked_at` |

---

## 5. Device Lifecycle

| State | Auth | Heartbeat | Manifest | Описание |
|---|---|---|---|---|
| `pending` | ✅ | ✅ (→ active) | ✅ | Зарегистрирован, ждёт heartbeat |
| `active` | ✅ | ✅ | ✅ | Работает |
| `lost` | ✅ | ✅ (→ active) | ✅ | Heartbeat пропал |
| `disabled` | ❌ (401) | ❌ | ❌ | Админ отключил |
| `retired` | ❌ (401) | ❌ | ❌ | Списан |

---

## 6. Registration / Credential Summary

| Операция | Admin Only | Механизм |
|---|---|---|
| Create device | ✅ | `device_code` unique, `channel_id`/`store_id` required, linkage validation |
| Update device | ✅ | Статусные переходы: `disabled_at` управляется |
| Create credential | ✅ | `secrets.token_hex(32)`, bcrypt hash, secret shown once |
| Revoke credential | ✅ | Все сессии credential немедленно отозваны |
| Rotate credential | ✅ | Revoke old → create new |

---

## 7. Heartbeat / Status Summary

| Аспект | Детали |
|---|---|
| Endpoint | `POST /heartbeat` |
| Side-effects | `last_seen_at=now`, `pending/lost→active`, `KsoDevice` cross-propagation |
| Не меняет | device_code, channel_id, credentials, placement, generated_manifests |
| Validation | status (ok/warning/error), non-negative, manifest hash 64 hex, forbidden keys |
| Admin views | `GET /gateway-devices/{id}/heartbeats` — `devices.gateway.read` |

---

## 8. Manifest Delivery Summary

### Legacy (production)

| Endpoint | Источник | Аудит |
|---|---|---|
| `/manifest/current` | PublicationTarget → ManifestVersion | `_record_manifest_request()` |
| `/kso/{code}/manifest` | GeneratedManifest WHERE `published` | Device code match enforced |

### Universal (dry-run/preview)

| Endpoint | Источник | Статус |
|---|---|---|
| `/manifest/universal/current` | Placement → Orchestrator → UniversalManifestV1 | Dry-run, no DB writes |

---

## 9. PoP / Config Boundary

| Система | Влияние Gateway |
|---|---|
| PoP ingestion | Read-only: device JWT, validate, store. Не меняет manifest |
| Runtime config | Read-only: ETag/304, audit. Не меняет credentials |
| Media delivery | Read-only: streaming, SHA-256 validation. Не меняет manifest |

---

## 10. Security Review

| Проверка | Результат |
|---|---|
| Device endpoints: `authenticate_device()` only | ✅ |
| Admin endpoints: `require_permission()` only | ✅ |
| User session token не подходит для device | ✅ |
| Device token не подходит для admin | ✅ |
| Disabled/retired denied | ✅ |
| No device_code oracle (same 401) | ✅ |
| Timing-safe bcrypt.checkpw | ✅ |
| JWT minimal claims (8 полей) | ✅ |
| Token expiry | ✅ |
| Secrets shown once (credential) | ✅ |
| No secrets in manifest/heartbeat/config/PoP | ✅ |
| No secrets in logs/test snapshots/docs | ✅ |
| ETag built on safe canonical JSON | ✅ |
| Media refs — no signed URL/token | ✅ |

---

## 11. Import Boundary Verification

| Проверка | Результат |
|---|---|
| Universal endpoint: нет `publications.service` | ✅ |
| Universal endpoint: нет `generate_manifests` | ✅ |
| Universal endpoint: нет `publish_batch` | ✅ |
| Universal endpoint: нет `KsoPlacement` | ✅ |
| Universal endpoint: нет `GeneratedManifest` | ✅ |
| Legacy KSO: нет `UniversalManifestV1` | ✅ |
| PoP: нет зависимости от Universal Manifest | ✅ |
| Admin: нет зависимости от Orchestrator/Builder | ✅ |

---

## 12. Data Safety Verification

| Проверка | Результат |
|---|---|
| Manifest pull: нет generated_manifests writes | ✅ |
| Universal endpoint: нет generated_manifests writes | ✅ |
| Heartbeat: нет placement/publication writes | ✅ |
| PoP: нет manifest/publication writes | ✅ |
| Config: нет credential writes | ✅ |
| Admin: credential secret not after creation | ✅ |
| generated_manifests FK unchanged | ✅ |
| Publication flow unchanged | ✅ |
| KSO projection unchanged | ✅ |
| Universal path: preview/dry-run only | ✅ |

---

## 13. Test Results

| Слой | Результат |
|---|---|
| C.4 targeted | 60/60 ✅ |
| C.3 targeted | 44/44 ✅ |
| C.2 targeted | 39/39 ✅ |
| C.1 + C.1.1 targeted | 39/39 ✅ |
| Legacy device gateway auth | 13/13 ✅ |
| **Gateway Suite** | **195/195** ✅ |
| **Full Backend Regression** | **1426 collected / 1360 passed / 66 failed (pre-existing) / 0 collection errors** |

---

## 14. Backend Baseline

| Параметр | Значение |
|---|---|
| Collected | 1426 |
| Passed | 1360 |
| Failed (pre-existing) | 66 |
| Collection errors | 0 |
| Gateway suite | 195/195 |

### Pre-existing failures (66)

class: `test_airtime_occupancy` (ModuleNotFoundError), `test_z_test_kso_readiness_384` (env/physical KSO), `test_user_crud_api` (nest_asyncio ordering), `conftest` (3 env tests), legal/compliance (1)

---

## 15. Portal Baseline

| Параметр | Значение |
|---|---|
| Portal tests | 863 passed / 0 failed / 32 skipped |
| Не менялся | С B.3.4 |

---

## 16. Deferred Items

| Item | Причина | Приоритет |
|---|---|---|
| mTLS | Не требуется для current scope | Future |
| Final signed manifest | B.6 (Manifest Signing) | Phase B продолжение |
| Universal manifest storage | B.6 (storage migration) | Phase B продолжение |
| Real publish (universal) | Requires full pipeline | Phase D/E |
| KSO Adapter | Specific channel adapter | Phase D+ |
| Compatibility projection | Legacy→universal mapping | Phase E |
| PoP analytics (ClickHouse) | Отдельная фаза | Phase F |
| Rate limiting / replay protection | Security hardening | Future |
| Certificate lifecycle | mTLS deferred | Future |
| Device heartbeat staleness detection | Требует cron/background task | Future |
| Device auto-retirement | Требует политики | Future |

---

## 17. What Next Phase Must Not Break

1. Device JWT auth, credential management
2. Device lifecycle: pending→active↔lost, disabled/retired
3. Heartbeat: last_seen, KsoDevice cross-propagation
4. KSO legacy manifest delivery (GeneratedManifest)
5. Universal manifest preview delivery (dry-run)
6. PoP ingestion (single + batch)
7. Runtime config delivery (ETag/304)
8. Admin API (device CRUD, credentials, audit views)
9. Import boundaries: no publication flow in device endpoints
10. Security: no secrets in responses, device isolation

---

## 18. GO/NO-GO for Next Phase

**GO ✅ для Phase D (D.0 — Inventory / Planning Design Gate).**
