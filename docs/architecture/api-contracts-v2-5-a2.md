# API Contracts v2.5 — A.2

> **Дата:** 2026-06-29 | **Этап:** A.2  
> **Основание:** ТЗ v2.5 Tables 3, 14, 19  
> **Статус:** ПРОЕКТ (код не меняется)

---

## 1. User API (Control Plane)

### 1.1. Auth

| Endpoint | Method | Auth | RBAC | Idempotency | Audit |
|---|---|---|---|---|---|
| `/api/auth/login` | POST | None (Basic/JSON) | — | — | login_audit_events |
| `/api/auth/refresh` | POST | Refresh token | — | — | — |
| `/api/auth/logout` | POST | Access token | — | — | refresh_tokens.revoked |
| `/api/auth/me` | GET | Access token | — | — | — |

**login request:** `{username, password}`  
**login response:** `{access_token, refresh_token, expires_at, user: {username, display_name, roles, permissions}}`  
**Безопасность:** access_token 15min, refresh_token 7d SHA-256 hashed. JWT не в URL. Cookie: httpOnly, SameSite, signed.

### 1.2. Users / RBAC

| Endpoint | Method | Permission | RLS | Audit |
|---|---|---|---|---|
| `/api/users` | GET | `users.read` | По scope администратора | — |
| `/api/users` | POST | `users.create` | — | admin_audit (create_user) |
| `/api/users/{username}` | GET | `users.read` | По scope | — |
| `/api/users/{username}/status` | PUT | `users.manage` | — | admin_audit (archive/block/activate_user) |
| `/api/roles` | GET | `roles.read` | — | — |
| `/api/roles` | POST | `roles.create` | — | admin_audit |
| `/api/users/{username}/roles` | PUT | `roles.assign` | — | admin_audit (assign_role) |
| `/api/users/{username}/rls-scopes` | PUT | `rls.manage` | — | admin_audit (assign_rls_scope) |

**Статус:** ✅ User API в основном реализован. Нужна доработка: user status history.

### 1.3. Hierarchy

| Endpoint | Method | Permission | RLS |
|---|---|---|---|
| `/api/branches` | GET/POST | `hierarchy.read`/`.manage` | branch_scope |
| `/api/clusters` | GET/POST | `hierarchy.read`/`.manage` | через branch |
| `/api/stores` | GET/POST | `hierarchy.read`/`.manage` | store_scope |
| `/api/store-groups` | GET/POST | `hierarchy.read`/`.manage` | — |

**Статус:** ✅ Branches/clusters/stores реализованы. store_groups: ❌

### 1.4. Advertisers

| Endpoint | Method | Permission | RLS |
|---|---|---|---|
| `/api/advertisers` | GET/POST | `advertisers.read`/`.create` | advertiser_scope |
| `/api/advertisers/{id}` | GET/PUT | `advertisers.read`/`.update` | advertiser_scope |
| `/api/brands` | GET/POST | `advertisers.read`/`.create` | через advertiser |
| `/api/contracts` | GET/POST | `advertisers.read`/`.create` | через advertiser |
| `/api/orders` | GET/POST | `advertisers.read`/`.create` | через advertiser |

**Статус:** ✅ Частично. Нужно: brand/contract/order CRUD если отсутствует.

### 1.5. Campaigns

| Endpoint | Method | Permission | RLS | Audit |
|---|---|---|---|---|
| `/api/campaigns` | GET | `campaigns.read` | advertiser_scope | — |
| `/api/campaigns` | POST | `campaigns.create` | advertiser_scope | campaign.created |
| `/api/campaigns/{code}` | GET | `campaigns.read` | advertiser_scope | — |
| `/api/campaigns/{code}` | PUT | `campaigns.update` | advertiser_scope | campaign.updated |
| `/api/campaigns/{code}/submit` | POST | `campaigns.submit` | advertiser_scope | campaign.submitted |
| `/api/campaigns/{code}/approve` | POST | `campaigns.approve` | advertiser_scope | campaign.approved |
| `/api/campaigns/{code}/reject` | POST | `campaigns.approve` | advertiser_scope | campaign.rejected |
| `/api/campaigns/{code}/status-history` | GET | `campaigns.read` | advertiser_scope | — |

**Статус:** ✅ Campaigns CRUD + workflow. Нужно: campaign_type, status_history.

### 1.6. Placements ❌ НОВЫЙ

| Endpoint | Method | Permission | RLS | Notes |
|---|---|---|---|---|
| `/api/campaigns/{code}/placements` | GET | `campaigns.read` | advertiser_scope | List placements |
| `/api/campaigns/{code}/placements` | POST | `campaigns.create` | advertiser_scope | Create placement |
| `/api/placements/{code}` | GET | `campaigns.read` | advertiser_scope | |
| `/api/placements/{code}` | PUT | `campaigns.update` | advertiser_scope | |
| `/api/placements/{code}/targets` | GET/PUT | `campaigns.update` | advertiser_scope | placement_targets |
| `/api/placements/{code}/simulate` | POST | `campaigns.read` | advertiser_scope | Симуляция перед публикацией |
| `/api/placements/{code}/publish` | POST | `campaigns.publish` | advertiser_scope | → Channel Orchestrator |
| `/api/placements/{code}/conflicts` | GET | `campaigns.read` | advertiser_scope | Проверка конфликтов |

### 1.7. Inventory ❌ НОВЫЙ

| Endpoint | Method | Permission |
|---|---|---|
| `/api/inventory/availability` | GET | `inventory.read` |
| `/api/inventory/forecast` | GET | `inventory.read` |
| `/api/inventory/reservations` | GET/POST | `inventory.manage` |
| `/api/inventory/rules` | GET/PUT | `inventory.manage` |
| `/api/inventory/snapshots` | GET | `inventory.read` |
| `/api/inventory/channels` | GET | `inventory.read` |

**Параметры:** `?channel_id=&scope_type=&scope_id=&date_from=&date_to=`

### 1.8. Content / Media

| Endpoint | Method | Permission |
|---|---|---|
| `/api/creatives` | GET/POST | `creatives.read`/`.upload` |
| `/api/creatives/{code}` | GET/PUT | `creatives.read`/`.update` |
| `/api/creatives/{code}/versions` | GET/POST | `creatives.read`/`.upload` |
| `/api/creatives/{code}/renditions` | GET | `creatives.read` |
| `/api/renditions/{code}` | GET | `creatives.read` |
| `/api/creatives/{code}/preview` | GET | `creatives.read` |
| `/api/creatives/{code}/moderation` | POST | `creatives.moderate` |

**Статус:** ✅ Частично. Нужно: renditions per channel, moderation tasks.

### 1.9. Approvals

| Endpoint | Method | Permission |
|---|---|---|
| `/api/approvals` | GET | `approvals.read` |
| `/api/approvals/{code}` | GET | `approvals.read` |
| `/api/approvals/{code}/approve` | POST | `approvals.approve` |
| `/api/approvals/{code}/reject` | POST | `approvals.approve` |

**Статус:** ✅ Реализован. Maker-checker enforced.

### 1.10. Channels / Devices ❌ НОВЫЙ

| Endpoint | Method | Permission |
|---|---|---|
| `/api/channels` | GET/POST | `channels.read`/`.manage` |
| `/api/channels/{code}/device-types` | GET | `channels.read` |
| `/api/device-types/{code}/capability-profiles` | GET | `channels.read` |
| `/api/physical-devices` | GET | `devices.read` |
| `/api/physical-devices/{code}` | GET/PUT | `devices.read`/`.manage` |
| `/api/physical-devices/{code}/status` | GET | `devices.read` |
| `/api/physical-devices/{code}/commands` | POST | `devices.manage` |
| `/api/logical-carriers` | GET/POST | `devices.read`/`.manage` |
| `/api/display-surfaces` | GET/POST | `devices.read`/`.manage` |
| `/api/surface-groups` | GET/POST | `devices.read`/`.manage` |
| `/api/store-zones` | GET/POST | `hierarchy.manage` |
| `/api/runtime-versions` | GET/POST | `devices.manage` |

**Фильтры:** `?channel_id=&store_id=&status=&device_type_id=&search=`

### 1.11. Analytics ❌ НОВЫЙ

| Endpoint | Method | Permission |
|---|---|---|
| `/api/analytics/dashboard/network` | GET | `analytics.read` |
| `/api/analytics/campaign/{code}` | GET | `analytics.read` |
| `/api/analytics/placement/{code}` | GET | `analytics.read` |
| `/api/analytics/store/{code}` | GET | `analytics.read` |
| `/api/analytics/device/{code}` | GET | `analytics.read` |
| `/api/analytics/inventory` | GET | `analytics.read` |
| `/api/analytics/sla` | GET | `analytics.read` |
| `/api/analytics/export/{type}` | POST | `analytics.export` |

### 1.12. Emergency ❌ НОВЫЙ

| Endpoint | Method | Permission | MFA |
|---|---|---|---|
| `/api/emergency/stop` | POST | `emergency.manage` | ✅ required |
| `/api/emergency/message` | POST | `emergency.manage` | ✅ required |
| `/api/emergency/resume` | POST | `emergency.manage` | ✅ required |
| `/api/emergency/status` | GET | `emergency.read` | — |

### 1.13. Audit

| Endpoint | Method | Permission |
|---|---|---|
| `/api/audit/events` | GET | `audit.read` |
| `/api/audit/operational` | GET | `audit.read` |
| `/api/admin/audit` | GET | `audit.read` |

**Статус:** ✅ Admin + login audit. Нужно: operational audit.

---

## 2. Device API (Device Gateway)

**Отдельный контур.** Путь: `/device/*`. Auth: mTLS или JWT device token.

| Endpoint | Method | Auth | Idempotency | Rate Limit |
|---|---|---|---|---|
| `/device/register` | POST | device_code + fingerprint | — | 1/сек/IP |
| `/device/heartbeat` | POST | device JWT/mTLS | — | 1/30сек |
| `/device/manifest` | GET | device JWT/mTLS | — | 1/30сек |
| `/device/pop/batch` | POST | device JWT/mTLS | batch_key | burst OK |
| `/device/events` | POST | device JWT/mTLS | event_code | — |
| `/device/errors` | POST | device JWT/mTLS | — | — |
| `/device/commands/ack` | POST | device JWT/mTLS | command_id | — |

### 2.1. /device/register
**Request:** `{device_code, hardware_fingerprint, device_type?, store_code?}`  
**Response:** `{device_id, external_code, certificate (или JWT), expires_at}`  
**Errors:** 409 duplicate, 400 invalid device_code

### 2.2. /device/heartbeat
**Request:** `{status, player_version, manifest_applied, cpu_percent, memory_mb, disk_free_mb, cache_size_mb, chromium_version?}`  
**Response:** `{ack, server_time, pending_commands?}`  
**Headers:** ETag для неизменного статуса → 304

### 2.3. /device/manifest
**Request:** Query — `?supported_schema_versions=1.0&player_version=1.2.3`  
**Response:** `{manifest: {manifest_id, version, valid_from, valid_to, media_files[], rules[], signature, adapter_payload?}}`  
**Headers:** ETag → 304 если manifest не изменился  
**Security:** JWT не в URL. Manifest подписан. SHA-256 каждого media_file проверяется плеером.

### 2.4. /device/pop/batch
**Request:** `{batch_key, events: [{event_code, proof_type, started_at, ended_at, duration_ms, media_sha256, playback_result, failure_reason?, device_signature}]}`  
**Response:** `{accepted: N, duplicates: M, rejected: K, errors: [...]}`  
**Idempotency:** batch_key + event_code. Дубли отбрасываются.

### 2.5. /device/errors
**Request:** `{error_code, message, manifest_id?, stack_trace?}`  
**Response:** `{ack}`

---

## 3. Channel Adapter API (Internal)

**Consumer API** — адаптеры каналов потребляют задания от Orchestrator.

| Endpoint | Направление | Consumer → Gateway |
|---|---|---|
| `GET /adapter/tasks/pending` | Adapter → Gateway | Получить pending задания |
| `POST /adapter/tasks/{id}/delivery` | Adapter → Gateway | Подтвердить доставку |
| `POST /adapter/tasks/{id}/apply` | Adapter → Gateway | Подтвердить применение |
| `POST /adapter/tasks/{id}/proof` | Adapter → Gateway | Отправить proof |
| `POST /adapter/health` | Adapter → Gateway | Health check адаптера |

**Контракт адаптера:**
```json
{
  "task_id": "uuid",
  "task_type": "publish|update|rollback|emergency",
  "manifest": { ... },
  "adapter_payload": { ... },
  "target_devices": [...]
}
```

---

## 4. Internal Worker API (Event-Driven)

| Событие | Producer | Consumer |
|---|---|---|
| `publish.requested` | Campaign Service | Channel Orchestrator |
| `manifest.generated` | Orchestrator | Adapter Router |
| `channel.task.created` | Orchestrator | Channel Adapters |
| `adapter.delivery.attempted` | Adapters | Orchestrator |
| `device.apply.ack` | Device Gateway | Orchestrator → Analytics |
| `proof.received` | PoP Ingestion | Analytics |
| `rollout.paused` | Operations | Orchestrator |
| `rollback.started` | Operations | Orchestrator |

---

## 5. Статус реализации

| Группа API | Кол-во endpoints | EXISTS | НОВЫЙ |
|---|---|---|---|
| Auth | 4 | ✅ 4 | 0 |
| Users/RBAC | 7 | ✅ 7 | 0 |
| Hierarchy | 4 | ✅ 3 | 1 (store-groups) |
| Advertisers | 5 | ✅ 4 | 1 |
| Campaigns | 8 | ✅ 7 | 1 (status-history) |
| Placements | 8 | ❌ 0 | 8 |
| Inventory | 6 | ❌ 0 | 6 |
| Content | 7 | ✅ 5 | 2 (renditions channel, mod) |
| Approvals | 4 | ✅ 4 | 0 |
| Channels/Devices | 12 | ❌ 0 | 12 |
| Analytics | 8 | ❌ 0 | 8 |
| Emergency | 4 | ❌ 0 | 4 |
| Audit | 3 | ✅ 3 | 0 |
| **Device API** | 7 | ❌ 0 | 7 |
| **Adapter API** | 5 | ❌ 0 | 5 |
| **Итого** | **92** | **37** | **55** |
