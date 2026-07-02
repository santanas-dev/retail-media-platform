# ERD v2.5 — Retail Media Platform

**Version:** 2.5
**Phase:** 0 (Architecture Lock)
**Source:** ТЗ v2.5 Tables 18, 19; §24.4 (Channel → Device → Surface model)

---

## 1. PostgreSQL: Operational Model

### 1.0 Universal Channel Model (Foundation)

```
channels                    device_types
┌──────────────────┐       ┌──────────────────────┐
│ id               │       │ id                   │
│ code (KSO/ANDROID│       │ code (KSO_V1/ANDROID_│
│   _TV/ESL/LED)   │       │   TV/WEBOS/ESL_GW)   │
│ name             │       │ channel_id FK ──────►│
│ description      │       │ name                 │
│ is_active        │       │ player_runtime       │
│ sort_order       │       │ (chromium/android/   │
│ created_at       │       │  webview/esl_adapter)│
└──────────────────┘       │ is_active            │
                           │ created_at           │
        ┌──────────────────┘
        │
        ▼
capability_profiles            physical_devices
┌──────────────────────┐       ┌──────────────────────┐
│ id                   │       │ id                   │
│ code                 │       │ code (human-readable)│
│ device_type_id FK ──►│       │ store_id FK ────────►│
│ resolution_w         │       │ device_type_id FK ──►│
│ resolution_h         │       │ serial_number        │
│ orientation          │       │ hardware_fingerprint │
│ supported_formats[]  │       │ os_version           │
│ max_file_size_bytes  │       │ ip_address           │
│ max_duration_sec     │       │ status (online/      │
│ supports_video       │       │   offline/degraded/   │
│ supports_animation   │       │   error/maintenance/  │
│ supports_interactive │       │   revoked)            │
│ pop_mode             │       │ last_seen_at         │
│ (real_playback/      │       │ current_manifest_id  │
│  screen_render/      │       │ cache_size_bytes     │
│  gateway_ack/etc)    │       │ created_at           │
│ created_at           │       │ updated_at           │
└──────────────────────┘       └──────┬───────────────┘
                                      │
        ┌─────────────────────────────┘
        │
        ▼
logical_carriers                   display_surfaces
┌──────────────────────┐           ┌──────────────────────────┐
│ id                   │           │ id                       │
│ code                 │           │ code                     │
│ physical_device_id ──►           │ logical_carrier_id FK ──►│
│ carrier_type          │           │ store_id FK ────────────►│
│ (direct/esl_gw/       │           │ zone_id FK (optional)   │
│  led_controller/      │           │ shelf_id (optional)     │
│  vendor_api)          │           │ category_id (optional)  │
│ vendor_name           │           │ sku_group_id (optional) │
│ vendor_config_json    │           │ resolution_w            │
│ labels_count (ESL)    │           │ resolution_h            │
│ led_panels_count      │           │ is_active               │
│ created_at            │           │ current_manifest_id     │
└──────────────────────┘           │ created_at               │
                                   └──────────────────────────┘
```

### 1.1 Organization & Users

```
branches                    clusters                   stores
┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│ id           │           │ id           │           │ id           │
│ code         │◄─────FK───│ branch_id    │◄─────FK───│ cluster_id   │
│ name         │           │ code         │           │ code         │
│ timezone     │           │ name         │           │ name         │
│ is_active    │           │ is_active    │           │ address      │
│ created_at   │           │ created_at   │           │ timezone     │
└──────────────┘           └──────────────┘           │ is_active    │
                                                      │ created_at   │
users                         roles                   └──────┬───────┘
┌──────────────┐           ┌──────────────┐                  │
│ id           │           │ id           │      store_zones  │
│ username     │           │ code         │      ┌───────────┐│
│ display_name │           │ name         │      │ id        ││
│ email        │           │ description  │      │ store_id  │◄┘
│ password_hash│           │ is_system    │      │ code      │
│ (local only) │           │ created_at   │      │ name      │
│ ad_guid      │           └──────┬───────┘      │ zone_type │
│ is_active    │                  │              └───────────┘
│ is_locked    │     user_roles   │
│ locked_until │     ┌───────────┐│     permissions
│ mfa_enabled  │     │ user_id   ││     ┌──────────────┐
│ created_at   │     │ role_id   ││     │ id           │
└──────┬───────┘     │ granted_by││     │ code         │
       │             │ granted_at││     │ name         │
       │             └───────────┘│     │ description  │
       │                          │     │ created_at   │
       │            role_permissions    └──────┬───────┘
       │            ┌───────────────┐           │
       │            │ role_id       │  access_scopes
       │            │ permission_id │  ┌────────────────┐
       │            └───────────────┘  │ id             │
       │                               │ user_id        │
       │                               │ scope_type     │
       │                               │ (branch/cluster/│
       │                               │  store/         │
       │                               │  advertiser)    │
       │                               │ scope_id       │
       │                               └────────────────┘
```

### 1.2 Advertisers & Contracts

```
advertisers             brands                contracts
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ id           │       │ id           │       │ id           │
│ code         │       │ advertiser_id│◄──────│ advertiser_id│
│ name         │       │ name         │       │ code         │
│ legal_name   │       │ is_active    │       │ name         │
│ inn          │       │ created_at   │       │ start_date   │
│ contacts_json│       └──────────────┘       │ end_date     │
│ is_active    │                              │ status       │
│ created_at   │       orders                │ created_at   │
└──────┬───────┘       ┌──────────────┐       └──────┬───────┘
       │               │ id           │              │
       │               │ contract_id  │◄─────────────┘
       │               │ campaign_id  │──┐ (optional)
       │               │ code         │  │
       │               │ type         │  │
       │               │ (commercial/ │  │
       │               │  internal/   │  │
       │               │  compensation│  │
       │               │  /test)      │  │
       │               │ budget       │  │
       │               │ status       │  │
       │               │ created_at   │  │
       │               └──────────────┘  │
       │                                 │
```

### 1.3 Campaigns & Placements

```
campaigns                          placements
┌──────────────────┐              ┌──────────────────┐
│ id               │              │ id               │
│ code             │─────FK──────►│ campaign_id      │
│ advertiser_id ───┼──┐           │ code             │
│ brand_id      ───┼──┤ (opt)     │ channel_type FK  │
│ name             │  │           │ priority         │
│ start_date       │  │           │ start_time       │
│ end_date         │  │           │ end_time         │
│ status           │  │           │ days_of_week[]   │
│ (draft/moderation│  │           │ frequency        │
│  /review/approved│  │           │ max_impressions  │
│  /scheduled/live │  │           │ weight           │
│  /paused/complet.│  │           │ overbooking_pct  │
│  /archived/canc.)│  │           │ status           │
│ created_by FK    │  │           │ (draft/active/   │
│ updated_by FK    │  │           │  paused/complet.)│
│ created_at       │  │           │ created_at       │
└──────────────────┘  │           └──────┬───────────┘
                      │                  │
campaign_targets      │   placement_targets
┌─────────────────┐   │   ┌───────────────────────┐
│ campaign_id     │◄──┤   │ placement_id FK       │
│ target_type     │   │   │ target_type           │
│ (branch/cluster │   │   │ (branch/cluster/store/ │
│  /store/device_ │   │   │  zone/category/device_ │
│  type/surface)  │   │   │  type/display_surface)│
│ target_id       │   │   │ target_id             │
└─────────────────┘   │   └───────────────────────┘
                      │
campaign_status_history│   campaign_creative_links
┌──────────────────┐   │   ┌──────────────────────┐
│ campaign_id FK   │   │   │ campaign_id FK       │
│ from_status      │   │   │ creative_version_id FK
│ to_status        │   │   │ is_active            │
│ changed_by FK    │   │   │ assigned_at          │
│ comment          │   │   └──────────────────────┘
│ changed_at       │   │
└──────────────────┘   │
```

### 1.4 Content & Creatives

```
media_assets                    creative_versions
┌──────────────────┐           ┌──────────────────────┐
│ id               │           │ id                   │
│ code             │──FK──────►│ media_asset_id        │
│ original_filename│           │ version_number        │
│ mime_type        │           │ file_path (MinIO key) │
│ file_size_bytes  │           │ sha256                │
│ sha256           │           │ resolution_w          │
│ duration_sec     │           │ resolution_h          │
│ resolution_w     │           │ duration_sec          │
│ resolution_h     │           │ file_size_bytes       │
│ uploaded_by FK   │           │ status (draft/in_rev. │
│ storage_ref      │           │   /approved/rejected) │
│ created_at       │           │ moderation_notes      │
└──────────────────┘           │ created_by FK         │
                               │ created_at            │
renditions                     └──────┬───────────────┘
┌──────────────────────┐              │
│ id                   │  rendition_requirements
│ creative_version_id ─┼──┐           ┌────────────────────┐
│ device_type_id FK ───┼──┤ (target)  │ id                 │
│ rendition_type       │  │           │ device_type_id FK  │
│ (fullscreen/card/    │  │           │ min_width          │
│  banner/shelf_label) │  │           │ min_height         │
│ file_path (MinIO)    │  │           │ max_width          │
│ sha256               │  │           │ max_height         │
│ width                │  │           │ allowed_formats    │
│ height               │  │           │ max_size_bytes     │
│ format               │  │           │ max_duration_sec   │
│ created_at           │  │           │ color_space         │
└──────────────────────┘  │           │ requires_no_audio  │
                          │           └────────────────────┘
creative_moderation_tasks  │
┌──────────────────────┐   │
│ id                   │   │
│ creative_version_id ─┼───┘
│ rendition_id (opt)   │
│ reviewer_id FK       │
│ decision (approved/  │
│   rejected/needs_work│
│   )                  │
│ comments             │
│ checks_json          │
│ decided_at           │
└──────────────────────┘
```

### 1.5 Inventory

```
inventory_rules                  inventory_reservations
┌──────────────────────┐         ┌──────────────────────┐
│ id                   │         │ id                   │
│ code                 │         │ placement_id FK      │
│ name                 │         │ scope_type (branch/  │
│ scope_type           │         │   cluster/store/     │
│ (network/branch/     │         │   device_type/surface│
│  cluster/store)      │         │ scope_id             │
│ scope_id (opt)       │         │ start_time           │
│ channel_type FK      │         │ end_time             │
│ max_revenue_share_pct│         │ status (reserved/    │
│ slot_duration_sec    │         │   confirmed/released)│
│ max_ads_per_slot     │         │ created_by FK        │
│ prime_time_start     │         │ created_at           │
│ prime_time_end       │         └──────────────────────┘
│ priority_rules_json  │
│ is_active            │         inventory_snapshots
│ created_at           │         ┌──────────────────────┐
└──────────────────────┘         │ id                   │
                                 │ snap_date            │
                                 │ scope_type           │
                                 │ scope_id             │
                                 │ capacity_sec         │
                                 │ reserved_sec         │
                                 │ sold_sec             │
                                 │ free_sec             │
                                 │ devices_online       │
                                 │ devices_total        │
                                 └──────────────────────┘
```

### 1.6 Manifest & Delivery

```
manifests                         manifest_items
┌──────────────────────┐          ┌──────────────────────┐
│ id                   │          │ id                   │
│ manifest_id (UUID)   │──FK─────►│ manifest_id          │
│ device_id/surface_id │          │ order                │
│ store_id FK          │          │ creative_version_id FK
│ playlist_version_id  │          │ rendition_id FK      │
│ manifest_version     │          │ sha256               │
│ valid_from           │          │ minio_key            │
│ valid_to             │          │ duration_sec         │
│ status (generated/   │          │ weight               │
│   delivered/applied/ │          │ priority             │
│   expired/error)     │          │ emergency_flag       │
│ channel_type         │          │ fallback_rule        │
│ adapter_payload JSON │          └──────────────────────┘
│ signature_alg        │
│ signature_value      │          adapter_configs
│ created_at           │          ┌──────────────────────┐
└──────────────────────┘          │ id                   │
                                  │ channel_type FK      │
playlists                         │ adapter_code         │
┌──────────────────────┐          │ config_json          │
│ id                   │          │ is_active            │
│ code                 │          │ created_at           │
│ name                 │          └──────────────────────┘
│ scope_type           │
│ scope_id             │          rollout_plans
│ priority             │          ┌──────────────────────┐
│ created_at           │          │ id                   │
└──────┬───────────────┘          │ manifest_version_id FK
       │                          │ scope_type           │
playlist_versions                 │ scope_id             │
┌──────────────────────┐          │ stage (lab/5stores/  │
│ id                   │          │   50stores/10pct/50p │
│ playlist_id FK       │          │   ct/100pct)        │
│ version_label        │          │ current_step         │
│ status (draft/appr.  │          │ total_steps          │
│   /published)        │          │ status (in_progress/ │
│ created_by FK        │          │   completed/paused/  │
│ created_at           │          │   rolled_back)       │
└──────────────────────┘          │ started_at           │
                                  │ completed_at         │
playlist_items                    └──────────────────────┘
┌──────────────────────┐
│ id                   │          player_builds
│ playlist_version_id FK         ┌──────────────────────┐
│ creative_version_id FK         │ id                   │
│ order                 │          │ device_type_id FK    │
│ duration_sec          │          │ version              │
│ weight                │          │ channel (alpha/beta/│
│ priority              │          │   stable)            │
│ start_time (opt)      │          │ file_path (MinIO)    │
│ end_time (opt)        │          │ sha256               │
│ days_of_week[]        │          │ min_os_version       │
│ conditions_json       │          │ release_notes        │
└──────────────────────┘          │ created_at           │
                                  └──────────────────────┘
```

### 1.7 Emergency & Approvals

```
emergency_events                       approval_tasks
┌──────────────────────┐              ┌──────────────────────┐
│ id                   │              │ id                   │
│ action_type          │              │ object_type (campaign│
│ (stop_all/replace/   │              │   /placement/content)│
│  fallback/resume)    │              │ object_code          │
│ scope_type (network/ │              │ object_id            │
│   branch/cluster/    │              │ requested_by FK      │
│   store/device)      │              │ request_comment      │
│ scope_id (opt)       │              │ status (pending/     │
│ reason               │              │   approved/rejected) │
│ message (opt)        │              │ decided_by FK        │
│ created_by FK        │              │ decision_comment     │
│ status (pending/appl.│              │ requested_at         │
│   /completed/partial)│              │ decided_at           │
│ applied_count        │              └──────────────────────┘
│ total_count          │
│ created_at           │
└──────────────────────┘

emergency_targets (join)
┌──────────────────────┐
│ emergency_event_id FK│
│ device_id/surface_id │
│ status (pending/appl.│
│   /failed)           │
│ applied_at           │
└──────────────────────┘
```

### 1.8 Audit

```
audit_events_operational            device_events
┌──────────────────────┐            ┌──────────────────────┐
│ id                   │            │ id                   │
│ user_id FK (opt)     │            │ device_id FK         │
│ actor_role            │            │ event_type (register │
│ action                │            │   /manifest_applied/  │
│ target_type           │            │   /manifest_error/    │
│ target_ref            │            │   /heartbeat/         │
│ details_json          │            │   /error/revoked)     │
│ ip_address            │            │ details_json          │
│ user_agent            │            │ severity              │
│ correlation_id        │            │ created_at            │
│ created_at            │            └──────────────────────┘
└──────────────────────┘
                                       device_commands
┌──────────────────────┐              ┌──────────────────────┐
│ id                   │              │ id                   │
│ old_value (text diff)│              │ device_id FK         │
│ new_value (text diff)│              │ command_type (restart│
│ changed_by FK        │              │   /clear_cache/      │
│ changed_at           │              │   /refresh_manifest/  │
└──────────────────────┘              │   /maintenance/       │
                                       │   /revoke/           │
                                       │   /diagnostics)      │
                                       │ status (pending/sent │
                                       │   /executed/failed)  │
                                       │ params_json          │
                                       │ created_by FK        │
                                       │ created_at           │
                                       │ executed_at          │
                                       └──────────────────────┘
```

---

## 2. ClickHouse: Analytical Model

```
pop_events                              device_heartbeats
┌──────────────────────────┐            ┌──────────────────────┐
│ event_date Date          │            │ event_date Date      │
│ event_id UUID            │            │ device_id UUID       │
│ device_id UUID           │            │ store_id UUID        │
│ store_id UUID            │            │ timestamp DateTime   │
│ campaign_id UUID         │            │ player_version String │
│ placement_id UUID        │            │ status String        │
│ creative_version_id UUID │            │ cache_size_bytes UInt│
│ media_asset_id UUID      │            │ ip_address String    │
│ manifest_id UUID         │            │ correlation_id String│
│ channel_type String      │            └──────────────────────┘
│ device_type String       │
│ surface_id UUID (opt)    │            device_errors
│ started_at DateTime      │            ┌──────────────────────┐
│ ended_at DateTime        │            │ event_date Date      │
│ duration_ms UInt32       │            │ device_id UUID       │
│ media_sha256 String      │            │ error_code String    │
│ playback_result Enum     │            │ error_message String │
│   ('success','skipped',  │            │ manifest_id UUID     │
│    'failed','interrupted')│            │ timestamp DateTime   │
│ failure_reason String    │            │ correlation_id String│
│ pop_mode Enum            │            └──────────────────────┘
│   ('real_playback',      │
│    'screen_render',      │            campaign_daily_stats
│    'idle_screen',        │            ┌──────────────────────┐
│    'template_applied',   │            │ date Date            │
│    'gateway_ack',        │            │ campaign_id UUID     │
│    'label_ack',          │            │ store_id UUID        │
│    'controller_ack')     │            │ channel_type String  │
│ device_signature String  │            │ impressions UInt64   │
│ correlation_id String    │            │ failures UInt64      │
│ batch_id UUID            │            │ unique_devices UInt32│
└──────────────────────────┘            │ play_duration_sec U64│
ENGINE = MergeTree()                    └──────────────────────┘
PARTITION BY toYYYYMM(event_date)       ENGINE = SummingMergeTree()
ORDER BY (event_date, campaign_id,      PARTITION BY toYYYYMM(date)
          device_id)                     ORDER BY (date, campaign_id,
                                                     store_id, channel_type)

audit_events (ClickHouse)
┌──────────────────────────┐            inventory_daily_snapshots
│ event_date Date          │            ┌──────────────────────┐
│ user_id UUID (opt)       │            │ date Date            │
│ action String            │            │ scope_type String    │
│ target_type String       │            │ scope_id UUID        │
│ target_ref String        │            │ channel_type String  │
│ actor_role String        │            │ capacity_sec UInt64  │
│ ip_address String        │            │ reserved_sec UInt64  │
│ details_json String      │            │ sold_sec UInt64      │
│ correlation_id String    │            │ free_sec UInt64      │
│ timestamp DateTime       │            │ devices_online UInt32│
└──────────────────────────┘            │ devices_total UInt32 │
ENGINE = MergeTree()                    └──────────────────────┘
PARTITION BY toYYYYMM(event_date)       ENGINE = MergeTree()
ORDER BY (event_date, user_id, action)  PARTITION BY toYYYYMM(date)
                                        ORDER BY (date, scope_type, scope_id)
```

## 3. Relational Summary

- `branches` 1→N `clusters` 1→N `stores` 1→N `store_zones`
- `channels` 1→N `device_types` 1→N `capability_profiles`
- `stores` 1→N `physical_devices` 1→N (opt) `logical_carriers` 1→N `display_surfaces`
- `device_types` → `physical_devices`
- `advertisers` 1→N `brands` 1→N `contracts` 1→N `orders`
- `campaigns` N→1 `advertisers`, `campaigns` 1→N `placements` 1→N `placement_targets`
- `campaigns` N→M `creative_versions` (via `campaign_creative_links`)
- `media_assets` 1→N `creative_versions` 1→N `renditions`
- `playlists` 1→N `playlist_versions` 1→N `playlist_items`
- `playlist_versions` 1→N `manifests` 1→N `manifest_items`
- `emergency_events` N→M `devices/surfaces` (via `emergency_targets`)
- `users` N→M `roles` (via `user_roles`), `roles` N→M `permissions` (via `role_permissions`)

## References

- TZ v2.5 Table 18 (PostgreSQL operational model), Table 19 (ClickHouse analytical model)
- TZ v2.5 §24.4 (New channel → device → surface model)
- `rmp_rewrite_starting_decisions.md` — First tables to build
