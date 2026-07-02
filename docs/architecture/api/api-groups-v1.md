# API Groups v1 — Retail Media Platform

**Version:** 1.0
**Phase:** 0 (Architecture Lock)
**Source:** ТЗ v2.5 Table 20; §16.1, §24.11

---

## API Architecture

Four logically separated API groups, each with its own authentication, rate limiting, and versioning.

```
┌──────────────┐  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐
│ User API     │  │ Device API    │  │ Internal API │  │ Analytics API│
│ /api/v1/*    │  │ /device/v1/*  │  │ /internal/*  │  │ /analytics/* │
│ Control Plane│  │ Device Gateway│  │ Inter-service│  │ Read-only BI │
│ AD/SSO + MFA │  │ JWT (device)  │  │ Service auth │  │ AD/SSO       │
└──────────────┘  └───────────────┘  └──────────────┘  └──────────────┘
```

---

## 1. Auth API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| POST | `/api/v1/auth/login` | None | — | AD/SSO or local login |
| POST | `/api/v1/auth/refresh` | Refresh token | — | Refresh access token |
| POST | `/api/v1/auth/logout` | JWT | — | Invalidate refresh token |
| GET | `/api/v1/auth/me` | JWT | — | Current user profile + permissions |
| POST | `/api/v1/auth/mfa/verify` | JWT (partial) | — | MFA second factor |

---

## 2. Users & RBAC API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/users` | JWT | `users.read` | List users (paginated, filterable) |
| POST | `/api/v1/users` | JWT | `users.create` | Create user |
| GET | `/api/v1/users/{id}` | JWT | `users.read` | Get user details |
| PATCH | `/api/v1/users/{id}` | JWT | `users.manage` | Update user |
| POST | `/api/v1/users/{id}/roles` | JWT | `roles.manage` | Assign role to user |
| DELETE | `/api/v1/users/{id}/roles/{role_id}` | JWT | `roles.manage` | Remove role |
| POST | `/api/v1/users/{id}/block` | JWT | `users.manage` | Block/unlock user |
| GET | `/api/v1/roles` | JWT | `roles.read` | List roles |
| GET | `/api/v1/permissions` | JWT | `permissions.read` | List permissions |
| GET | `/api/v1/users/{id}/scopes` | JWT | `users.read` | Get RLS scopes |

---

## 3. Organization API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/branches` | JWT | `hierarchy.read` | List branches |
| POST | `/api/v1/branches` | JWT | `hierarchy.manage` | Create branch |
| GET | `/api/v1/clusters` | JWT | `hierarchy.read` | List clusters (filter by branch) |
| GET | `/api/v1/stores` | JWT | `hierarchy.read` | List stores (filter by cluster) |
| GET | `/api/v1/store-zones` | JWT | `hierarchy.read` | List store zones |

---

## 4. Channels & Devices API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/channels` | JWT | `channels.read` | List channels |
| GET | `/api/v1/device-types` | JWT | `devices.read` | List device types |
| GET | `/api/v1/device-types/{id}/capabilities` | JWT | `devices.read` | Capability profile |
| GET | `/api/v1/devices` | JWT | `devices.read` | List physical devices (paginated) |
| POST | `/api/v1/devices` | JWT | `devices.manage` | Register device (manual) |
| GET | `/api/v1/devices/{id}` | JWT | `devices.read` | Device details |
| PATCH | `/api/v1/devices/{id}` | JWT | `devices.manage` | Update device |
| POST | `/api/v1/devices/{id}/commands` | JWT | `devices.command` | Send command to device |
| GET | `/api/v1/logical-carriers` | JWT | `devices.read` | List logical carriers |
| GET | `/api/v1/display-surfaces` | JWT | `devices.read` | List display surfaces |
| GET | `/api/v1/player-builds` | JWT | `devices.read` | List player versions |

---

## 5. Advertisers API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/advertisers` | JWT | `advertisers.read` | List advertisers |
| POST | `/api/v1/advertisers` | JWT | `advertisers.manage` | Create advertiser |
| GET | `/api/v1/advertisers/{id}` | JWT | `advertisers.read` | Advertiser details |
| GET | `/api/v1/contracts` | JWT | `contracts.read` | List contracts |
| POST | `/api/v1/contracts` | JWT | `contracts.manage` | Create contract |
| GET | `/api/v1/orders` | JWT | `orders.read` | List orders |
| POST | `/api/v1/orders` | JWT | `orders.manage` | Create order |

---

## 6. Campaigns & Placements API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/campaigns` | JWT | `campaigns.read` | List campaigns (paginated, filterable) |
| POST | `/api/v1/campaigns` | JWT | `campaigns.create` | Create campaign (draft) |
| GET | `/api/v1/campaigns/{code}` | JWT | `campaigns.read` | Campaign detail |
| PATCH | `/api/v1/campaigns/{code}` | JWT | `campaigns.manage` | Update campaign |
| POST | `/api/v1/campaigns/{code}/submit` | JWT | `campaigns.submit` | Submit for approval |
| POST | `/api/v1/campaigns/{code}/pause` | JWT | `campaigns.manage` | Pause campaign |
| POST | `/api/v1/campaigns/{code}/archive` | JWT | `campaigns.manage` | Archive campaign |
| GET | `/api/v1/placements` | JWT | `placements.read` | List placements |
| POST | `/api/v1/placements` | JWT | `placements.manage` | Create placement |
| PATCH | `/api/v1/placements/{id}` | JWT | `placements.manage` | Update placement |
| POST | `/api/v1/placements/{id}/check` | JWT | `inventory.read` | Check conflicts |

---

## 7. Inventory API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/inventory/availability` | JWT | `inventory.read` | Query free/busy/reserved |
| GET | `/api/v1/inventory/forecast` | JWT | `inventory.read` | Forecast impressions |
| POST | `/api/v1/inventory/reserve` | JWT | `inventory.reserve` | Reserve inventory |
| DELETE | `/api/v1/inventory/reservations/{id}` | JWT | `inventory.reserve` | Release reservation |
| GET | `/api/v1/inventory/rules` | JWT | `inventory.read` | List rules |
| POST | `/api/v1/inventory/rules` | JWT | `inventory.manage` | Create/update rule |

---

## 8. Content & Creatives API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| POST | `/api/v1/media/upload` | JWT | `media.upload` | Upload media asset |
| GET | `/api/v1/media` | JWT | `media.read` | List media (paginated) |
| GET | `/api/v1/media/{id}` | JWT | `media.read` | Media detail |
| GET | `/api/v1/media/{id}/preview` | JWT | `media.read` | Preview/thumbnail |
| POST | `/api/v1/media/{id}/versions` | JWT | `media.upload` | Upload new version |
| GET | `/api/v1/creatives/{id}/renditions` | JWT | `media.read` | List renditions for creative |
| POST | `/api/v1/creatives/{id}/renditions` | JWT | `media.upload` | Upload rendition |
| POST | `/api/v1/moderation/{id}/review` | JWT | `media.moderate` | Review creative/rendition |

---

## 9. Playlist & Manifest API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/playlists` | JWT | `playlists.read` | List playlists |
| POST | `/api/v1/playlists` | JWT | `playlists.manage` | Create playlist |
| GET | `/api/v1/playlists/{id}/versions` | JWT | `playlists.read` | List versions |
| POST | `/api/v1/playlists/{id}/publish` | JWT | `publications.publish` | Publish → generate manifests |
| GET | `/api/v1/manifests` | JWT | `manifests.read` | List manifests (paginated) |
| GET | `/api/v1/manifests/{id}` | JWT | `manifests.read` | Manifest detail |
| POST | `/api/v1/manifests/preview` | JWT | `manifests.read` | Dry-run manifest generation |

---

## 10. Approval API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/approvals` | JWT | `approvals.read` | List approval tasks (assigned) |
| POST | `/api/v1/approvals/{id}/decide` | JWT | `approvals.approve` | Approve/reject |
| GET | `/api/v1/approvals/{id}/history` | JWT | `approvals.read` | Approval history |

---

## 11. Emergency API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| POST | `/api/v1/emergency/stop` | JWT + MFA | `emergency.execute` | Stop all advertising |
| POST | `/api/v1/emergency/message` | JWT + MFA | `emergency.execute` | Replace with emergency message |
| POST | `/api/v1/emergency/resume` | JWT + MFA | `emergency.execute` | Resume normal play |
| GET | `/api/v1/emergency/status` | JWT | `emergency.read` | Emergency status |
| GET | `/api/v1/emergency/history` | JWT | `emergency.read` | Emergency command history |

---

## 12. Analytics API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/analytics/dashboard` | JWT | `analytics.read` | Network KPI dashboard |
| GET | `/api/v1/analytics/campaign/{code}` | JWT | `analytics.read` | Campaign analytics |
| GET | `/api/v1/analytics/store/{id}` | JWT | `analytics.read` | Store/device analytics |
| GET | `/api/v1/analytics/inventory` | JWT | `analytics.read` | Inventory occupancy report |
| GET | `/api/v1/analytics/sla` | JWT | `analytics.read` | SLA compliance report |
| POST | `/api/v1/analytics/export` | JWT | `analytics.export` | Export PDF/XLSX/CSV |
| GET | `/api/v1/analytics/advertiser/{code}/report` | JWT | `analytics.read` | Advertiser report (scoped) |

---

## 13. Audit API

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| GET | `/api/v1/audit/events` | JWT | `audit.read` | Query audit events (paginated) |

---

## 14. Device Gateway API (separate auth)

| Method | Endpoint | Auth | Permission | Description |
|--------|----------|------|------------|-------------|
| POST | `/device/v1/register` | device_code | — | Register device, get credentials |
| POST | `/device/v1/session` | device HMAC | — | Establish session, get JWT |
| POST | `/device/v1/session/refresh` | device JWT | — | Refresh JWT |
| GET | `/device/v1/manifest` | device JWT | — | Pull latest manifest for this device (ETag/304). Manifest may contain `display_surfaces[]` for multi-surface devices. |
| POST | `/device/v1/manifest/ack` | device JWT | — | Acknowledge manifest applied |
| POST | `/device/v1/heartbeat` | device JWT | — | Device heartbeat |
| POST | `/device/v1/pop/batch` | device JWT | — | Submit PoP batch |
| GET | `/device/v1/commands` | device JWT | — | Poll pending commands |
| POST | `/device/v1/commands/{id}/result` | device JWT | — | Report command execution |
| GET | `/device/v1/capabilities` | device JWT | — | Report device capabilities |

---

## Common Patterns

- **Pagination:** `?page=1&page_size=20` (allowed: 20, 50, 100)
- **Filtering:** `?status=active&channel_type=KSO&search=term`
- **Sorting:** `?sort_by=created_at&sort_order=desc`
- **Idempotency:** `Idempotency-Key: <uuid>` header for POST/PATCH
- **Versioning:** `/api/v1/`, `/device/v1/`
- **Error format:** `{"error": {"code": "CONFLICT", "message": "...", "details": {...}}}`
- **Correlation:** `X-Correlation-ID: <uuid>` propagated across services

## References

- TZ v2.5 Table 20 (API Groups)
- TZ v2.5 §16.1 (API Groups), §24.11 (API versioning)
- TZ v2.5 §21.5 (API-first contract development)
