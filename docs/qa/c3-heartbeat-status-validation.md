# C.3 — Heartbeat / Device Status Validation

> **Дата:** 2026-07-01
> **Этап:** C.3 — Heartbeat & Status Validation (аудит + тесты)
> **Предыдущий:** C.2 (commit `2281bb7`, 39 tests)
> **Результат:** ✅ — GO для C.4

---

## Heartbeat Flow (существующий — подтверждён)

```
Device (JWT)                                    Gateway
    │                                              │
    │  POST /api/device-gateway/heartbeat           │
    │  Authorization: Bearer {token}                │
    │  Body: DeviceHeartbeatRequest                 │
    │─────────────────────────────────────────────→│
    │                                              │ authenticate_device()
    │                                              │  ├─ JWT decode
    │                                              │  ├─ DeviceSession valid?
    │                                              │  ├─ Device status ≠ disabled/retired?
    │                                              │  └─ → GatewayDevice
    │                                              │
    │                                              │ record_heartbeat():
    │                                              │  ├─ Validate status (ok/warning/error)
    │                                              │  ├─ Validate non-negative
    │                                              │  ├─ Validate manifest hash
    │                                              │  ├─ Check forbidden keys
    │                                              │  ├─ Size limit
    │                                              │  ├─ Create DeviceHeartbeat row
    │                                              │  ├─ device.last_seen_at = now
    │                                              │  ├─ pending/lost → active
    │                                              │  ├─ KsoDevice.last_seen_at = now
    │                                              │  └─ commit
    │                                              │
    │  ◄── DeviceHeartbeatResponse                 │
    │      (no secrets)                             │
```

---

## Status Lifecycle

```
 ┌─────────┐   admin/seed   ┌──────────┐   heartbeat   ┌────────┐
 │ (create) │──────────────→│ pending   │──────────────→│ active  │
 └─────────┘               └──────────┘               └────────┘
                                  │                        │
                     admin disable│                        │ heartbeat stops
                                  ▼                        ▼
                            ┌──────────┐             ┌────────┐
                            │ disabled  │             │  lost   │
                            │ retired   │             └────────┘
                            └──────────┘                  │
                                 ▲              heartbeat │ resumes
                                 │                        ▼
                                 │                  ┌────────┐
                          admin   │                  │ active  │
                        reactivate│                  └────────┘
```

**Правила переходов:**
| Transition | By whom | Rule |
|---|---|---|
| pending → active | Heartbeat | Automatic on first valid heartbeat |
| lost → active | Heartbeat | Automatic on heartbeat resume |
| active → lost | System | Manual admin or detection logic (no heartbeat for N minutes) |
| any → disabled | Admin | `update_device(status="disabled")` — sets `disabled_at` |
| any → retired | Admin | `update_device(status="retired")` — sets `disabled_at` |
| disabled/retired → active | Admin | Clears `disabled_at`, logs `device_reactivated` |

**Heartbeat НЕ может:**
- Перевести active в disabled/retired ❌
- Перевести disabled/retired в active ❌
- Перевести lost в disabled ❌
- Менять device_code, channel_id, credentials, placement ❌

---

## Heartbeat Validation Rules

| Rule | Status |
|---|---|
| `data.status` ∈ {ok, warning, error} (default: ok) | ✅ |
| `storage_free_mb >= 0` | ✅ |
| `cache_items_count >= 0` | ✅ |
| `current_manifest_hash`: 64 hex chars if present | ✅ |
| `details_json` forbidden keys blocked | ✅ |
| `details_json` size limit enforced | ✅ |
| Sidecar_status injected into details_json | ✅ |

---

## Heartbeat Side-Effects

| Update | Mechanism |
|---|---|
| `device.last_seen_at = now` | Direct |
| `pending → active` | Conditional |
| `lost → active` | Conditional |
| `KsoDevice.last_seen_at = now` | Cross-propagation (GAP 3 fix) |
| `device_heartbeats` row created | ORM insert |
| `device_events` log entry | `_log_event("heartbeat_received")` |

**NOT updated:**
- device_code ❌
- channel_id ❌
- physical_device_id ❌
- display_surface_id ❌
- credentials ❌
- generated_manifests ❌
- placement/manifest/publication ❌

---

## Security Checks

| Check | Status |
|---|---|
| Auth: `authenticate_device()` only (device JWT) | ✅ |
| No user session token accepted | ✅ |
| Disabled/retired blocked by `authenticate_device()` | ✅ |
| No secrets in response | ✅ |
| No secrets in heartbeat payload (forbidden keys) | ✅ |
| No `device_code`/`channel_id`/`credential` in request schema | ✅ |
| Log message does not contain `device_secret` | ✅ |
| Admin views require `devices.gateway.read` | ✅ |
| Admin response does not contain `secret_hash` | ✅ |

---

## Test Results

| Слой | Результат |
|---|---|
| **C.3 targeted (NEW)** | **44/44** ✅ |
| C.2 targeted | 39/39 ✅ |
| C.1 + C.1.1 targeted | 39/39 ✅ |
| Legacy device gateway auth | 13/13 ✅ |
| **Total gateway suite** | **135/135** ✅ |
| Backend collection | **1366** (0 errors) |

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
| `backend/tests/test_heartbeat_status_c3.py` | 🆕 44 теста |

---

## GO/NO-GO для C.4

**GO ✅ для C.4 — Manifest Pull Dry-Run / Delivery Validation.**
