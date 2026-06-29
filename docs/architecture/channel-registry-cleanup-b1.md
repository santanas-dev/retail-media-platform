# Channel Registry Cleanup — B.1

> **Дата:** 2026-06-29 | **Этап:** B.1 | **Статус:** ✅ COMPLETED
> **Commit:** (pending)

## Цель

Закрепить channel-agnostic модель v2.5 в коде и справочниках. KSO — первый канал в универсальной модели, не отдельная вертикаль.

## Changes Summary

### Seed (channel registry)

| Entity | Before | After |
|---|---|---|
| channels | 5 ✅ | 5 (unchanged) |
| device_types | 1 (kso_gen5) | **5** (+4: android_tv_gen1, price_checker_gen1, esl_gen1, led_shelf_gen1) |
| capability_profiles | 1 (wrong: landscape, screenshot) | **6** (1 per device_type + KSO dual landscape/portrait) |
| display_surfaces | 2 (orientation bug) | 2 (orientation FIXED) |

### Bugfixes

1. **KSO portrait orientation**: 768×1024 display surface now points to correct portrait capability profile (was landscape)
2. **KSO proof_type**: Changed from `screenshot` to `real_playback`
3. **KSO formats**: Added `["mp4","jpg","png"]` (was NULL)
4. **ORM model**: Added `external_code` and `device_properties` columns to `PhysicalDevice` (DB columns existed since A.3, ORM was missing them)

### Universal read helpers

| Helper | Location | Status |
|---|---|---|
| `list_physical_devices(channel_code=...)` | `channels/service.py` | ✅ Added |
| `get_physical_device_by_external_code()` | `channels/service.py` | ✅ Added |
| `GET /api/physical-devices?channel_code=kso` | `channels/router.py` | ✅ Added |
| `GET /api/physical-devices/by-code/{code}` | `channels/router.py` | ✅ Added |
| `PhysicalDeviceResponse.external_code` | `channels/schemas.py` | ✅ Exposed |

### Files changed

| File | Change |
|---|---|
| `backend/app/domains/channels/seed.py` | Extended: device_types + capability_profiles seed |
| `backend/app/domains/channels/models.py` | +external_code, +device_properties on PhysicalDevice |
| `backend/app/domains/channels/service.py` | +channel_code filter, +get_by_external_code |
| `backend/app/domains/channels/router.py` | +channel_code param, +by-code endpoint |
| `backend/app/domains/channels/schemas.py` | +external_code in PhysicalDeviceResponse |

### NOT changed (compatibility preserved)

- `backend/app/domains/hierarchy/` — legacy KSO device registry (seed.py, router.py, service.py, schemas.py)
- `backend/app/domains/hierarchy/models.py` — `kso_devices` ORM model
- `backend/app/domains/campaigns/` — KSO references in docs/comments
- `backend/app/domains/manifests/service.py` — `channel_code="kso"` hardcode
- Legacy routes: `GET/POST/PUT /api/devices/kso/*`
- Legacy tables: `kso_devices`, `kso_placements`, `kso_proof_of_play_events`

### Data

- **No DROP/DELETE/TRUNCATE**
- **Legacy kso_* tables preserved**
- **No data migration** (only seed additions)

## Verification

- Backend regression: TBD
- Portal regression: TBD
- Channel registry: 5 channels, 5 device types, 6 capability profiles
- KSO portrait surface: 768×1024 → correct profile
- External code: exposed in API, filterable by channel
