# Hierarchy & KSO Device Registry — Foundation (Step 37.1)

## Overview

Foundation for one-KSO pilot: backend models, API, and seed for the
Branch → Cluster → Store → KsoDevice hierarchy.

## Hierarchy

```
Branch (demo_branch_north)
  └── Cluster (demo_cluster_001)
        └── Store (demo_store_001)
              └── KsoDevice (demo_kso_001)
```

## Models

### Branch (`branches`)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | gen_random_uuid() |
| code | String(50) | UNIQUE |
| name | String(255) | |
| timezone | String(50) | default Europe/Moscow |
| is_active | Boolean | |

### Cluster (`clusters`) — updated in 37.1
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| code | String(50) | NEW — UniqueConstraint(branch_id, code) |
| name | String(255) | |
| branch_id | UUID FK | → branches.id |
| is_active | Boolean | |

### Store (`stores`) — updated in 37.1
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| code | String(50) | UNIQUE |
| cluster_id | UUID FK | → clusters.id |
| format | String(50) | NEW |
| status | String(20) | NEW, default "active" |
| is_active | Boolean | preserved for backward compat |

### KsoDevice (`kso_devices`) — NEW in 37.1
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| store_id | UUID FK | → stores.id |
| device_code | String(64) | UNIQUE |
| display_name | String(255) | |
| status | String(20) | active/inactive/blocked/maintenance/lost |
| channel | String(20) | default "kso" |
| runtime_version | String(32) | |
| player_version | String(32) | |
| sidecar_version | String(32) | |
| state_adapter_version | String(32) | |
| manifest_version | String(64) | |
| screen_width | Integer | default 1920 |
| screen_height | Integer | default 1080 |
| ad_zone_width | Integer | default 1440 |
| ad_zone_height | Integer | default 1080 |
| last_seen_at | DateTime | |
| comment | Text | |

## Forbidden Fields

The KSO device registry NEVER stores:
- IP address, MAC address, hostname, serial number
- device_secret / client_secret (raw)
- filesystem paths
- real store IDs / external IDs
- backend URL

## API Endpoints

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | /api/devices/kso | devices.read | List KSO devices |
| GET | /api/devices/kso/{code} | devices.read | Get by device_code |
| POST | /api/devices/kso | devices.manage | Create KSO device |
| PUT | /api/devices/kso/{code} | devices.manage | Update KSO device |

Existing organization endpoints unchanged:
- GET/POST /api/branches → organization.read / organization.manage
- GET/POST /api/clusters → organization.read / organization.manage
- GET/POST /api/stores → organization.read / organization.manage

## Future RLS

Endpoints are ready for RLS filtering:
- `list_kso_devices()` will filter by `store_scope` / `device_scope`
- `list_stores()` will filter by `branch_scope` / `store_scope`

TODO comments placed in router.py.

## Seed

Idempotent synthetic seed for one-KSO pilot:
```bash
cd backend
INITIAL_ADMIN_PASSWORD=*** python -m app.domains.hierarchy.seed
```

Creates:
- Branch: `demo_branch_north`
- Cluster: `demo_cluster_001`
- Store: `demo_store_001` (format: supermarket)
- KSO: `demo_kso_001` (1920×1080, ad zone 1440×1080)

ALL VALUES ARE SYNTHETIC. No real stores, addresses, or device codes.

## Migration

Alembic revision `024` — adds:
- `clusters.code` + unique constraint (branch_id, code)
- `stores.format`, `stores.status`
- `kso_devices` table with indexes

Downgrade supported.
