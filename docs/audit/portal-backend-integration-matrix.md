# Portal ↔ Backend Integration Matrix

**Step:** 40.2.2 — Portal Backend Integration Gate  
**Generated:** 2026-06-16  
**HEAD:** 40.2.1 (5035203) → fixing in 40.2.2

## Summary

| Status | Count |
|--------|-------|
| Verified (production endpoint) | 13 pages |
| Fixed (legacy → production) | 1 page |
| Demo-only (by design) | 1 page |
| Broken (legacy endpoint) | 0 (all fixed) |

## Matrix

### Legend
- ✅ Verified: uses production endpoint, permission valid in seed, error handling safe
- 🔧 Fixed: was legacy/test-kso, now production
- 📄 Demo: static page, no backend data needed

| # | Portal Route | Template | BackendClient Method | Backend Endpoint | Portal Permission | Backend Permission | RLS Scope | Response Fields Used | Error State | Status |
|---|-------------|----------|---------------------|------------------|-------------------|-------------------|-----------|---------------------|-------------|--------|
| 1 | `/`, `/dashboard` | `pages/dashboard.html` | `list_campaigns_prod` | `GET /api/campaigns` | `campaigns.read` | `campaigns.read` | campaign_scope | status, name, campaign_code | Fallback: "Backend недоступен" | ✅ |
| | | | `list_creatives` | `GET /api/creatives` | | `media.read` | — | creative_code, name, status | Partial: "Часть данных недоступна" | ✅ |
| | | | `list_kso_devices` | `GET /api/devices/kso` | | `devices.read` | — | device_code, display_name | | ✅ |
| | | | `list_schedules` | `GET /api/schedules` | | `scheduling.read` | schedule_scope | schedule_code, status | | ✅ |
| | | | `list_manifests` | `GET /api/manifests` | | `publications.read` | — | manifest_code, status | | ✅ |
| | | | `list_approvals_prod` | `GET /api/approvals` | | `campaigns.approve` | — | status (pending/in_review count) | | ✅ |
| 2 | `/campaigns` | `pages/campaigns.html` | `list_campaigns_prod` | `GET /api/campaigns` | `campaigns.read` | `campaigns.read` | campaign_scope | campaign_code, name, status, creative_codes | Fallback: empty + "Данные временно недоступны" | ✅ |
| | GET `/campaigns/create` | `pages/campaigns_create.html` | `list_advertisers`, `list_creatives`, `list_kso_devices` | Advertiser/Creative/Device APIs | `campaigns.read` | `campaigns.read` | campaign_scope | Dropdown data (advertiser, creative, device codes) | Fallback: empty dropdowns | ✅ (new 41.2) |
| | POST `/campaigns/create` | — | `create_campaign` + `bind_campaign_creative` + `create_placement` + `create_schedule` + `create_schedule_slot` | 4-step orchestration via `POST /api/campaigns/by-code`, `POST /api/placements`, `POST /api/schedules`, `POST /api/schedules/{code}/items` | `campaigns.create`, `scheduling.manage` | `campaigns.create`, `scheduling.manage` | campaign_scope | campaign_code, name, placement_code, schedule_code, slot_count | Summary page with all created objects | ✅ (new 41.2) |
| | POST `/{code}/edit` | | `update_campaign_by_code` | `PATCH /api/campaigns/by-code/{code}` | | `campaigns.manage` | | | Flash → redirect | ✅ |
| | POST `/{code}/archive` | | `archive_campaign_by_code` | `POST /api/campaigns/by-code/{code}/archive` | | `campaigns.manage` | | | Flash → redirect | ✅ |
| | POST `/{code}/bind-creative` | | `bind_campaign_creative` | `POST /api/campaigns/by-code/{code}/creatives` | | `campaigns.manage` | | | Flash → redirect | ✅ |
| | POST `/{code}/unbind-creative/{cc}` | | `unbind_campaign_creative` | `DELETE /api/campaigns/by-code/{code}/creatives/{cc}` | | `campaigns.manage` | | | Flash → redirect | ✅ |
| | POST `/{code}/submit` | — | `submit_campaign` | `POST /api/campaigns/by-code/{code}/submit` | | `campaigns.manage` | campaign_scope | draft → in_review | Flash → redirect | ✅ (new 41.2) |
| 3 | `/creatives` | `pages/creatives.html` | `list_creatives` | `GET /api/creatives` | `media.read` | `media.read` | creative_scope | creative_code, name, status, content_type, width, height | Fallback: empty + "Данные временно недоступны" | ✅ |
| | POST `/creatives/upload` | | `upload_creative` | `POST /api/creatives/upload` | | `media.manage` | | | Flash → redirect | ✅ |
| 4 | `/schedule` | `pages/schedule.html` | `list_schedules` | `GET /api/schedules` | `scheduling.read` | `scheduling.read` | schedule_scope | schedule_code, name, status, campaign_code, slot_count | Fallback: empty + "Данные временно недоступны" | ✅ |
| | | | `list_schedule_slots` | `GET /api/schedules/{code}/items` | | | | slot_code, placement_code, day_of_week, start/end_time | | ✅ |
| | POST `/schedule/create` | | `create_schedule` | `POST /api/schedules` | | `scheduling.manage` | | | Flash → redirect | ✅ |
| | POST `/{code}/create-slot` | | `create_schedule_slot` | `POST /api/schedules/{code}/items` | | `scheduling.manage` | | | Flash → redirect | ✅ |
| | POST `/{code}/archive` | | `archive_schedule` | `POST /api/schedules/{code}/archive` | | `scheduling.manage` | | | Flash → redirect | ✅ |
| | POST `/{code}/items/{slot}/disable` | | `disable_schedule_slot` | `DELETE /api/schedules/{code}/items/{slot}` | | `scheduling.manage` | | | Flash → redirect | ✅ |
| 5 | `/approvals` | `pages/approvals.html` | `list_approvals_prod` | `GET /api/approvals` | `campaigns.approve` | `campaigns.approve` | approval_scope | approval_code, object_type, object_code, status, decision | Fallback: empty + "Данные временно недоступны" | ✅ |
| | POST `/approvals/request` | | `create_approval` | `POST /api/approvals` | | `campaigns.approve` | | | Flash → redirect | ✅ |
| | POST `/approvals/decide` | | `approve_approval` / `reject_approval` | `POST /api/approvals/{code}/approve` or `/reject` | | `campaigns.approve` | | | Flash → redirect | ✅ |
| 6 | `/publications` | `pages/publications.html` | `list_manifests` | `GET /api/manifests` | `publications.read` | `publications.read` | publication_scope | manifest_code, status | Fallback: empty + error message | ✅ |
| | POST `/publications/generate` | | `generate_manifest` | `POST /api/manifests` | | `publications.manage` | | | Flash → redirect | ✅ |
| | POST `/publications/publish` | | `publish_manifest` | `POST /api/manifests/{code}/publish` | | `publications.publish` | | | Flash → redirect | ✅ |
| 7 | `/reports` | `pages/reports.html` | `get_pop_summary` | `GET /api/reports/pop/summary` | `reports.read` | `reports.read` | report_scope | total_events, unique_devices, accepted, rejected, etc. | Fallback: empty + "Данные временно недоступны" | ✅ |
| | | | `get_pop_report` | `GET /api/reports/pop` | | | | event_code, device_code, campaign_code, creative_code | | ✅ |
| | | | `list_campaigns_prod` | `GET /api/campaigns` | | | | supplemental KPI counts | | ✅ |
| | | | `list_creatives` | `GET /api/creatives` | | | | supplemental KPI counts | | ✅ |
| | | | `list_kso_devices` | `GET /api/devices/kso` | | | | supplemental KPI counts | | ✅ |
| | | | `list_manifests` | `GET /api/manifests` | | | | supplemental KPI counts | | ✅ |
| 8 | `/stores` | `pages/stores.html` | `list_branches` | `GET /api/branches` | `organization.read` | `organization.read` | branch_scope | name, code, timezone | Fallback: "Backend unavailable" | ✅ |
| | | | `list_clusters` | `GET /api/clusters` | | | | name, code, branch_id | | ✅ |
| | | | `list_stores` | `GET /api/stores` | | | store_scope | name, code, format, status | | ✅ |
| | | | `list_kso_devices` | `GET /api/devices/kso` | | | | kso_count per store | | ✅ |
| 9 | `/devices` | `pages/devices.html` | `list_stores` | `GET /api/stores` | `devices.read` | `devices.read` | device_scope | store name for device rows | Fallback: "Backend unavailable" | ✅ |
| | | | `list_kso_devices` | `GET /api/devices/kso` | | | | device_code, display_name, status, versions, screen geometry | | ✅ |
| 10 | `/proof-of-play` | `pages/proof-of-play.html` | ~~`list_pop_events`~~ → `get_pop_report` | ~~`GET /api/proof-of-play/test-kso`~~ → `GET /api/reports/pop` | `reports.read` | `reports.read` | report_scope | event_code, device_code, campaign_code, creative_code | Fallback: "Backend unavailable" | 🔧 Fixed |
| 11 | `/device-dashboard` | `pages/device-dashboard.html` | `get_device_dashboard` | `GET /api/device-dashboard` | `devices.gateway.read` | `devices.gateway.read` | device_scope | device_code, display_name, store_name, readiness_badge, heartbeat, credential, manifest | Fallback: "Данные временно недоступны" | ✅ |
| 12 | `/readiness` | `pages/readiness.html` | `get_device_dashboard` | `GET /api/device-dashboard` | `devices.gateway.read` | `devices.gateway.read` | device_scope | readiness_badge, heartbeat.age_seconds, credential.status, manifest.status | Fallback: "Данные временно недоступны" | ✅ |
| 13 | `/admin` | `pages/admin.html` | `list_users` | `GET /api/users` | `users.read` + `roles.read` | `users.read` | — | username, display_name, roles, is_active, is_locked | Fallback: backend_ok=False | ✅ |
| | | | `list_roles` | `GET /api/roles` | | `roles.read` | | | code, name, description | | ✅ |
| | | | `list_permissions` | `GET /api/permissions` | | `permissions.read` | | | code, name, resource, action | | ✅ |
| | | | `list_admin_audit` | `GET /api/admin/audit` | | `audit.read` | | | action, target_type, created_at (safe stripped) | | ✅ |
| | POST `/admin/users/create` | | `create_user` | `POST /api/users` | `users.create` | `users.create` | | | Flash → redirect | ✅ |
| | POST `/admin/users/assign-roles` | | `assign_user_roles` | `GET/PUT /api/users/{id}/roles` | `roles.manage` | `roles.manage` | | | Flash → redirect | ✅ |
| | POST `/admin/users/assign-rls-scopes` | | `assign_user_rls_scopes` | `PATCH /api/users/{username}/rls-scopes` | `roles.manage` | `roles.manage` | | | Flash → redirect | ✅ |
| 14 | `/deployment` | `pages/deployment.html` | _(none)_ | _(none)_ | `campaigns.read` | — | — | Static documentation page | — | 📄 Demo |

## Permission Consistency

### PAGE_PERMISSION_MAP vs Seed

| Portal Permission | In Seed? | system_admin Has? | security_admin Has? | advertiser Has? |
|---|---|---|---|---|
| `campaigns.read` | ✅ | ✅ | ✅ | ✅ |
| `media.read` | ✅ | ✅ | ✅ | ❌ |
| `scheduling.read` | ✅ | ✅ | ✅ | ❌ |
| `publications.read` | ✅ | ✅ | ✅ | ❌ |
| `organization.read` | ✅ | ✅ | ✅ | ❌ |
| `devices.read` | ✅ | ✅ | ❌ | ❌ |
| `reports.read` | ✅ | ✅ | ❌ | ✅ |
| `campaigns.approve` | ✅ | ✅ | ❌ | ❌ |
| `users.read` | ✅ | ✅ | ✅ | ❌ |
| `devices.gateway.read` | ✅ | ✅ | ✅ | ❌ |

**Result: all PAGE_PERMISSION_MAP entries exist in seed.** No mismatch found (this time, unlike 40.2.1).

### RBAC Role Coverage

| Role | Can open /admin? | Can open /campaigns? | Can open /approvals? | Can open /device-dashboard? |
|------|-----------------|---------------------|---------------------|---------------------------|
| system_admin | ✅ (users.read + roles.read) | ✅ (campaigns.read) | ✅ (campaigns.approve) | ✅ (devices.gateway.read) |
| security_admin | ✅ | ✅ | ❌ (no campaigns.approve) | ✅ |
| ad_manager | ❌ (no users.read) | ✅ | ❌ | ✅ |
| approver | ❌ | ✅ | ✅ | ✅ |
| analyst | ❌ | ✅ | ❌ | ✅ |
| advertiser | ❌ | ✅ | ❌ | ❌ |
| operations | ❌ | ✅ | ❌ | ✅ |

### BackendClient Legacy Methods (unused by portal)

| Method | Endpoint | Used by Portal? | Status |
|--------|----------|----------------|--------|
| `list_campaigns()` | `GET /api/campaigns/test-kso` | ❌ | Legacy, unused |
| `list_placements()` | `GET /api/schedule/test-kso` | ❌ | Legacy, unused |
| `create_placement()` | `POST /api/schedule/test-kso` | ❌ | Legacy, unused |
| `list_approvals()` | `GET /api/approvals/test-kso` | ❌ | Legacy, unused |
| `request_approval()` | `POST /api/approvals/test-kso/request` | ❌ | Legacy, unused |
| `decide_approval()` | `POST /api/approvals/test-kso/{code}/decide` | ❌ | Legacy, unused |
| `get_test_kso_readiness()` | `GET /api/test-kso/readiness` | ❌ | Legacy, unused |
| `list_pop_events()` | `GET /api/proof-of-play/test-kso` | **WAS used → fixed** | 🔧 Now unused |

## Authorization & Error Handling

| Check | Status |
|-------|--------|
| All BackendClient methods pass `Authorization: Bearer {access_token}` | ✅ |
| 401/403/404/500 handled safely (no internal details leaked) | ✅ |
| Timeout handling (connect=5s, read=15s) | ✅ |
| Sensitive key stripping in admin data (`_safe_users`, `_safe_audit`) | ✅ |
| No secrets/tokens/backend_urls in HTML templates | ✅ |
| No JS/CDN/localStorage in templates | ✅ |

## Remaining Gaps

1. **`/deployment`** is demo-only (static documentation page) — no backend data. Acceptable.
2. **Legacy methods in BackendClient** are dead code but not breaking anything — can be cleaned up in future step.
3. **Live integration test** (portal → backend HTTP) is created but runs against mock in default regression; full HTTP mode requires running backend.
4. **RLS verification through portal** is implicit — portal trusts backend RLS, no separate portal-side RLS. Backend tests cover RLS enforcement.

## 41.4 Update — Publications Batch Integration

### New Portal Page Integration

| Portal Page | Handler | Backend Endpoint | BackendClient Method | Permission |
|---|---|---|---|---|
| `/campaigns` (approved) | `POST /campaigns/{code}/create-publication-batch` | `POST /api/campaigns/by-code/{code}/create-publication-batch` | `create_publication_batch()` | publications.manage |
| `/publications` | `GET /publications` | `GET /api/publication-batches` + `GET /api/manifests` | `list_publication_batches()`, `list_manifests()` | publications.read |

### Status
- ✅ Campaign → batch bridge endpoint: code-based, no UUIDs in portal
- ✅ Publications page updated: batches table with campaign context + legacy manifests
- ✅ Physical delivery deferred: backend-only mode warning on /publications
- ✅ No JS/CDN/localStorage on new/changed pages
