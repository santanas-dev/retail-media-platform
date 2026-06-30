# C.1 — Universal Manifest Device Gateway Delivery

> **Дата:** 2026-07-01
> **Этап:** C.1 — Device Gateway Universal Manifest Delivery
> **Результат:** ✅ — GO для C.2

---

## Что добавлено

### 1 новый endpoint

`GET /api/device-gateway/manifest/universal/current` — device-facing, существующий JWT auth.

### Service функция

`get_universal_manifest_for_device(device, db, current_manifest_hash, client_ip, user_agent)`

### Placement resolver

`_resolve_placement_for_gateway_device(device, db)` — приоритетный поиск:
1. GatewayDevice.display_surface_id → PlacementTarget
2. GatewayDevice.logical_carrier_id → PlacementTarget
3. GatewayDevice.physical_device_id → LogicalCarrier → PlacementTarget

### Response schema

`UniversalManifestCurrentResponse` — status (ok/no_manifest/not_modified), manifest, hash, reason.

---

## Device Auth

Existing JWT (`authenticate_device()`):
- Disabled/retired device → 403
- Invalid/expired session → 401
- Valid → GatewayDevice + DeviceSession

## Manifest Resolution

GatewayDevice → Placement → OrchestratorContext → UniversalManifestV1 (все существующие B.4/B.5)

## No-Manifest Behavior

| Причина | Response |
|---|---|
| Нет matching surface/device | `{status: "no_manifest", reason: "no_matching_surface"}` |
| Placement not found | `{status: "no_manifest", reason: "placement_not_found"}` |
| Unsupported channel | `{status: "no_manifest", reason: "unsupported_channel"}` |

## ETag/304

- Hash: SHA-256 canonical JSON UniversalManifestV1
- `current_manifest_hash` match → `{status: "not_modified"}`
- Будущий ETag header: можно добавить после C.1

---

## Safety Checks

| Check | Status |
|---|---|
| Не использует KsoPlacement | ✅ |
| Не использует GeneratedManifest | ✅ |
| Не вызывает generate_manifests() | ✅ |
| Не вызывает publish_batch() | ✅ |
| Не пишет в generated_manifests | ✅ |
| KSO endpoint unchanged | ✅ |
| Publication flow unchanged | ✅ |
| PoP ingestion unchanged | ✅ |
| Admin API unchanged | ✅ |
| Auth model unchanged | ✅ |
| No secrets in response | ✅ |

---

## Test Results

| Слой | Результат |
|---|---|
| C.1 targeted | **12/12** ✅ |
| B.5.3 targeted | 40/40 ✅ |
| Backend collection | **1256** (0 errors) |

---

## Что не менялось

KSO endpoint (`/kso/{device_code}/manifest`), GeneratedManifest, publication flow, generate_manifests(), publish_batch(), KSO projection, PoP, admin API, auth model, portal — всё сохранено.

---

## GO/NO-GO для C.2

**GO ✅ для C.2 — Device Registration Validation.**
