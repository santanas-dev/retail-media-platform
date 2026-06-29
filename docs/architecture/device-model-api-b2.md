# Device Model API — B.2

> **Дата:** 2026-06-29

## Universal Device API (B.1 + B.2)

### Channels & Device Types

| Method | Endpoint | Permission | B. |
|---|---|---|---|
| GET | `/api/channels` | `channels.read` | B.1 |
| POST | `/api/channels` | `channels.manage` | B.1 |
| GET | `/api/device-types?channel_id=` | `devices.read` | B.1 |
| POST | `/api/device-types` | `devices.manage` | B.1 |

### Physical Devices (Universal Model)

| Method | Endpoint | Permission | B. |
|---|---|---|---|
| GET | `/api/physical-devices?channel_code=&device_type_id=&store_id=&status=` | `devices.read` | B.1 |
| GET | `/api/physical-devices/by-code/{external_code}` | `devices.read` | B.1 |
| GET | `/api/physical-devices/{id}/surfaces` | `devices.read` | **B.2** |
| POST | `/api/physical-devices` | `devices.manage` | B.1 |

### Capability Profiles

| Method | Endpoint | Permission | B. |
|---|---|---|---|
| GET | `/api/capability-profiles?device_type_id=` | `devices.read` | B.1 |
| POST | `/api/capability-profiles` | `devices.manage` | B.1 |

### Logical Carriers

| Method | Endpoint | Permission | B. |
|---|---|---|---|
| GET | `/api/logical-carriers?physical_device_id=` | `devices.read` | B.1 |
| POST | `/api/logical-carriers` | `devices.manage` | B.1 |

### Display Surfaces

| Method | Endpoint | Permission | B. |
|---|---|---|---|
| GET | `/api/display-surfaces?logical_carrier_id=` | `devices.read` | B.1 |
| GET | `/api/display-surfaces/{id}/readiness` | `devices.read` | **B.2** |
| POST | `/api/display-surfaces` | `devices.manage` | B.1 |

### Legacy KSO Routes (preserved, deprecated in future)

| Method | Endpoint | Permission | Status |
|---|---|---|---|
| GET | `/api/devices/kso` | `devices.read` | ⚠️ Legacy |
| GET | `/api/devices/kso/{device_code}` | `devices.read` | ⚠️ Legacy |
| POST | `/api/devices/kso` | `devices.manage` | ⚠️ Legacy |
| PUT | `/api/devices/kso/{device_code}` | `devices.manage` | ⚠️ Legacy |

## RBAC

- All endpoints require authentication
- Read operations: `devices.read` or `channels.read`
- Write operations: `devices.manage` or `channels.manage`
- RLS/scope: 47/47 unchanged
- Audit: 20/20 unchanged
