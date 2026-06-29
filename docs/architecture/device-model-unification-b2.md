# Device Model Unification — B.2

> **Дата:** 2026-06-29 | **Статус:** ✅ COMPLETED

## Цель

Полная цепочка: channel → device_type → physical_device → logical_carrier → display_surface → capability_profile

## Inventory (before B.2)

| Сущность | Before | After |
|---|---|---|
| channels | 5 | 5 |
| device_types | 5 | 5 |
| capability_profiles | 6 | 6 |
| physical_devices | 2 | 2 |
| logical_carriers | 2 (only seed device) | **3** (+1 KSO) |
| display_surfaces | 2 (only seed device) | **3** (+1 KSO) |
| placement_targets | 1 (no surface link) | 1 (linked to surface) |

## Changes

### Data fixes

1. **Migrated KSO device** (`test-dev-seed`): created logical_carrier `kso_player` + display_surface `768x1024` (portrait)
2. **Placement target**: linked to KSO portrait display_surface

### Service helpers

| Helper | Description |
|---|---|
| `get_device_surfaces(device_id)` | List display surfaces for a device through PD→LC→DS chain |
| `get_device_capabilities(device_id)` | List capability profiles for a device through full chain |
| `get_device_surface_readiness(surface_id)` | Check surface readiness (active, resolution, orientation, formats, proof_type) |

### API extensions

| Endpoint | Description |
|---|---|
| `GET /api/physical-devices/{id}/surfaces` | List display surfaces for a physical device |
| `GET /api/display-surfaces/{id}/readiness` | Check surface readiness for content delivery |

### Existing universal API (unchanged)

| Endpoint | Status |
|---|---|
| `GET /api/channels` | ✅ |
| `GET /api/device-types` | ✅ |
| `GET /api/physical-devices?channel_code=` | ✅ |
| `GET /api/physical-devices/by-code/{code}` | ✅ |
| `GET /api/capability-profiles` | ✅ |
| `GET /api/logical-carriers` | ✅ |
| `GET /api/display-surfaces` | ✅ |

## KSO Device Full Chain

```
channel: КСО (kso)
  └─ device_type: КСО 5-го поколения (kso_gen5)
       └─ physical_device: test-dev-seed (online)
            └─ logical_carrier: kso_player (ad_zone, portrait_768x1024)
                 └─ display_surface: 768x1024 (active)
                      └─ capability_profile: 768x1024 portrait, real_playback, [mp4,jpg,png]
```

## Compatibility

- Legacy routes `/api/devices/kso/*` — preserved
- Legacy tables `kso_*` — preserved
- No DROP/DELETE/TRUNCATE
- No data destroyed

## Tests

- B.2 tests: 18 tests (chain integrity, KSO device, placement target, channel registry, proof events, legacy preservation)
