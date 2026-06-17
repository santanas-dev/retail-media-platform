# Scheduling Core (Step 8)

Generates internal placement plans from confirmed bookings for retail media.

## Overview

The Scheduling Core takes confirmed bookings (with their items, inventory units, and capacity rules) and produces a **schedule plan** — a day-by-day, slot-by-slot assignment of campaign renditions to inventory units.

This is **not** a final playlist for devices, a manifest, or a PoP. It is an internal plan that will later feed into playlist generation and device delivery.

## Tables

### schedule_runs

A generation run for a confirmed booking.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `booking_id` | FK → campaign_bookings | RESTRICT |
| `campaign_id` | FK → campaigns | Denormalized for fast querying |
| `status` | VARCHAR(32) | `draft`, `generated`, `has_conflicts`, `approved`, `cancelled` |
| `created_by` | FK → users | Who created the run |
| `generated_by` | FK → users | Who ran generation (nullable) |
| `generated_at` | TIMESTAMPTZ | When generation finished (nullable) |
| `approved_by` | FK → users | Who approved (nullable) |
| `approved_at` | TIMESTAMPTZ | When approved (nullable) |
| `comment` | TEXT | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### schedule_items

A single placement slot — one rendition on one inventory unit at a specific time.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `schedule_run_id` | FK → schedule_runs | |
| `booking_item_id` | FK → booking_items | |
| `inventory_unit_id` | FK → inventory_units | Denormalized |
| `campaign_id` | FK → campaigns | Denormalized |
| `campaign_rendition_id` | FK → campaign_renditions | The actual content placement |
| `rendition_id` | FK → renditions | Denormalized |
| `date` | DATE | |
| `time_from` | TIME | |
| `time_to` | TIME | |
| `loop_position` | INTEGER | Which loop within the day |
| `spot_position` | INTEGER | Which spot within the loop |
| `spot_duration_seconds` | INTEGER | Duration of this spot |
| `priority` | INTEGER | From campaign priority |
| `weight` | INTEGER | From campaign_rendition weight |
| `status` | VARCHAR(20) | `active`, `cancelled` |
| `created_at` | TIMESTAMPTZ | |

### schedule_conflicts

Problems detected during generation.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `schedule_run_id` | FK → schedule_runs | |
| `inventory_unit_id` | FK → inventory_units | Nullable |
| `booking_item_id` | FK → booking_items | Nullable |
| `conflict_type` | VARCHAR(50) | See types below |
| `severity` | VARCHAR(20) | `warning`, `error`, `blocker` |
| `message` | TEXT | Human-readable description |
| `details_json` | JSONB | Structured context |
| `created_at` | TIMESTAMPTZ | |

**Conflict types:** `capacity_exceeded`, `missing_capacity_rule`, `invalid_rendition`, `channel_mismatch`, `target_mismatch`, `date_out_of_range`, `no_available_slot`, `invalid_capacity_rule`, `too_many_schedule_items`, `slot_conflict`

## Status Machine

```
POST /schedule-runs → draft
draft → generate → generated (no conflicts)
draft → generate → has_conflicts (conflicts exist)
generated → approve → approved
generated → cancel → cancelled
has_conflicts → cancel → cancelled
approved → cancel → cancelled (frees booking for new run)
```

- Cannot generate an approved or cancelled run
- Cannot approve a run with `error` or `blocker` conflicts
- Cannot create a new run while an approved run exists for the booking
- Cancelling an approved run requires `scheduling.approve`

## Generation Algorithm

For each booking item in the confirmed booking:

1. **Load and validate inventory unit** — must be active and sellable
2. **Per-day capacity rule lookup** — different days may have different rules (non-overlapping)
3. **Skip days** not in `days_of_week_json` (not an error)
4. **Validate capacity rule** — check times, durations, max_spots consistency
5. **Check campaign channels** — inventory unit's channel must be in campaign channels
6. **Re-verify target matching** — store→cluster→branch chain
7. **Collect valid renditions** — active campaign_rendition, rendition valid, creative approved, channel match, duration fit
8. **Check slot availability** — find free spot_positions from approved schedule_runs
9. **Place spots** — weighted round-robin through renditions

### Limits

`MAX_SCHEDULE_ITEMS_PER_RUN = 100_000` (configurable in `.env`). If estimated items exceed the limit, generation stops with `too_many_schedule_items` conflict.

## Permissions

| Permission | Resource | Action |
|-----------|----------|--------|
| `scheduling.read` | scheduling | read |
| `scheduling.manage` | scheduling | manage |
| `scheduling.approve` | scheduling | approve |

**Matrix:**

| Role | Read | Manage | Approve |
|------|:---:|:-----:|:------:|
| system_admin | ✅ | ✅ | ✅ |
| ad_manager | ✅ | ✅ | |
| approver | ✅ | | ✅ |
| analyst | ✅ | | |
| operations | ✅ | | |
| security_admin | ✅ | | |
| advertiser | | | |
| device_service | | | |

## API Endpoints

| Method | Path | Permission |
|--------|------|-----------|
| `POST` | `/api/schedule-runs` | `scheduling.manage` |
| `GET` | `/api/schedule-runs` | `scheduling.read` |
| `GET` | `/api/schedule-runs/{id}` | `scheduling.read` |
| `POST` | `/api/schedule-runs/{id}/generate` | `scheduling.manage` |
| `POST` | `/api/schedule-runs/{id}/approve` | `scheduling.approve` |
| `POST` | `/api/schedule-runs/{id}/cancel` | `scheduling.manage` (approved: `scheduling.approve`) |
| `GET` | `/api/schedule-runs/{id}/items` | `scheduling.read` |
| `GET` | `/api/schedule-runs/{id}/conflicts` | `scheduling.read` |
| `GET` | `/api/schedule-items` | `scheduling.read` |

### Filters

- `GET /schedule-runs`: `booking_id`, `campaign_id`, `status`
- `GET /schedule-items`: `date_from`, `date_to`, `inventory_unit_id`, `campaign_id`

## Idempotency

- Each booking may have at most one `approved` schedule_run
- `draft` runs can be regenerated (overwrites items/conflicts)
- `generated`/`has_conflicts` runs must be cancelled before creating a new one
- `approved` runs must be cancelled before creating a new one

## What is NOT included (deferred)

- Manifest / Device Gateway / PoP / player
- Publish to devices
- Per-device playlist
- Reports / billing / pricing
- ML / forecast / frequency capping / audience prediction
- Auto-retry on delivery failure
- Emergency stop
