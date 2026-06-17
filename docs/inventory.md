# Inventory & Booking Core

## Overview

Inventory and booking subsystem for the Retail Media Platform. Manages sellable advertising units, capacity rules, and campaign bookings.

## Tables

### inventory_units
Sellable advertising unit linked to physical infrastructure.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| code | VARCHAR(64) | UNIQUE, `^[a-z0-9_-]+$` |
| name | VARCHAR(255) | |
| channel_id | UUID → channels | |
| store_id | UUID → stores | |
| logical_carrier_id | UUID → logical_carriers | nullable |
| display_surface_id | UUID → display_surfaces | nullable |
| capability_profile_id | UUID → capability_profiles | nullable, ON DELETE RESTRICT |
| status | VARCHAR(32) | active/inactive/maintenance |
| is_sellable | BOOLEAN | sellable requires logical_carrier or display_surface |
| comment | TEXT | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### inventory_capacity_rules
Capacity rules defining ad slots per inventory unit.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| inventory_unit_id | UUID → inventory_units | |
| valid_from | DATE | |
| valid_to | DATE | valid_from ≤ valid_to |
| days_of_week_json | JSONB | Array 1..7 (Mon=1, Sun=7) |
| time_from | TIME | Must be < time_to |
| time_to | TIME | |
| loop_duration_seconds | INTEGER | > 0 — ad cycle length |
| spot_duration_seconds | INTEGER | > 0 — single spot length |
| max_spots_per_loop | INTEGER | > 0 — spots per cycle |
| max_share_of_voice | NUMERIC(5,4) | 0..1, default 1.0 |
| status | VARCHAR(32) | active/inactive |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**No overlapping active rules** for the same inventory unit.

### campaign_bookings
Booking — reservation of inventory for a campaign.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| campaign_id | UUID → campaigns | |
| status | VARCHAR(32) | draft/reserved/confirmed/cancelled/expired |
| date_from | DATE | |
| date_to | DATE | date_from ≤ date_to |
| created_by | UUID → users | |
| approved_by | UUID → users | nullable |
| approved_at | TIMESTAMPTZ | nullable |
| comment | TEXT | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### booking_items
Items within a booking linking to inventory units.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| booking_id | UUID → campaign_bookings | |
| inventory_unit_id | UUID → inventory_units | |
| booked_spots_per_loop | INTEGER | > 0 |
| booked_share_of_voice | NUMERIC(5,4) | nullable, > 0 and ≤ 1 |
| date_from | DATE | |
| date_to | DATE | |
| created_at | TIMESTAMPTZ | |

UNIQUE(booking_id, inventory_unit_id).

## Permissions

| Code | Description |
|------|-------------|
| inventory.read | View inventory units and capacity |
| inventory.manage | Create/edit inventory units and capacity |
| bookings.read | View campaign bookings |
| bookings.manage | Create/edit campaign bookings |
| bookings.approve | Confirm campaign bookings |

### Role Matrix

| Role | inventory.read | inventory.manage | bookings.read | bookings.manage | bookings.approve |
|------|:---:|:---:|:---:|:---:|:---:|
| system_admin | ✅ | ✅ | ✅ | ✅ | ✅ |
| ad_manager | ✅ | — | ✅ | ✅ | — |
| approver | ✅ | — | ✅ | — | ✅ |
| analyst | ✅ | — | ✅ | — | — |
| operations | ✅ | ✅ | ✅ | — | — |
| security_admin | ✅ | — | ✅ | — | — |
| advertiser | — | — | — | — | — |
| device_service | — | — | — | — | — |

## API Endpoints (17)

### Inventory Units
- `GET /api/inventory-units` — list (read)
- `POST /api/inventory-units` — create (manage)
- `GET /api/inventory-units/{id}` — get (read)
- `PUT /api/inventory-units/{id}` — update (manage)

### Capacity Rules
- `GET /api/inventory-units/{id}/capacity-rules` — list (read)
- `POST /api/inventory-units/{id}/capacity-rules` — create (manage)
- `PUT /api/capacity-rules/{id}` — update (manage)

### Availability
- `POST /api/inventory/availability` — calculate (read)

### Bookings
- `GET /api/bookings` — list (read)
- `POST /api/bookings` — create (manage)
- `GET /api/bookings/{id}` — get (read)
- `PUT /api/bookings/{id}` — update (manage, draft only)
- `POST /api/bookings/{id}/reserve` — draft→reserved (manage)
- `POST /api/bookings/{id}/confirm` — reserved→confirmed (approve)
- `POST /api/bookings/{id}/cancel` — →cancelled (manage)
- `GET /api/bookings/{id}/items` — list items (read)
- `PUT /api/bookings/{id}/items` — replace items (manage, draft only)

## Capacity Calculation

Daily capacity = `(active_seconds / loop_duration_seconds) × max_spots_per_loop`

Where `active_seconds` is derived from time_from/time_to, and only days in `days_of_week_json` are counted.

## Booking Lifecycle

```
draft ──→ reserved ──→ confirmed
  │          │
  └──→ cancelled      └──→ cancelled
                           │
                       expired
```

### Occupancy Rules

| Status | Occupies |
|--------|----------|
| draft | No |
| reserved | Soft (checked against confirm + other reserved) |
| confirmed | Hard (checked against all reserved + confirmed) |
| cancelled | No |
| expired | No |

## Validation

- **Store consistency**: logical_carrier → physical_device.store_id == inventory_unit.store_id; display_surface → logical_carrier → physical_device.store_id == inventory_unit.store_id
- **Sellable**: is_sellable=true requires logical_carrier_id OR display_surface_id
- **Capacity overlap**: No two active capacity rules for same unit may have overlapping date ranges
- **Channel matching**: inventory_unit.channel_id must be in campaign_channels
- **Target matching**: inventory unit must match at least one campaign target (all_stores/ store/cluster/branch/logical_carrier/display_surface)
- **Booking dates**: within campaign planned dates
- **Capacity check on reserve**: checks against confirmed + other reserved
- **Capacity check on confirm**: checks against confirmed + other reserved (excluding self)

## What's NOT in this step

- Scheduling
- Playlist generation
- Manifest / PoP
- Device Gateway / player
- Pricing / billing / invoices
- Reports
- Audience forecasting / ML
- Frequency capping
- Minute-by-minute schedule
- RLS / advertiser ownership
