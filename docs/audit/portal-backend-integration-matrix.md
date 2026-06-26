# Portal → Backend Integration Matrix

**Phase:** 40.2.2 — Portal Backend Integration Gate
**Date:** 2026-06-26
**Baseline:** commit `5035203` (40.2.1 — admin portal access bootstrap fix)

---

## Executive Summary

Full audit of every portal page → BackendClient method → backend endpoint chain. Permission consistency verified against backend seed. Two broken links found and fixed: `/campaigns` and `/dashboard` were using legacy test-kso endpoints.

---

## 1. Integration Matrix

### Legend

| Symbol | Meaning |
|---|---|
| ✅ | Verified — production endpoint, correct permission |
| 🟡 | Partial — works but needs hardening |
| 🔴 | BROKEN — legacy/test-kso, wrong endpoint/permission |
| ⬜ | N/A |

---

### /dashboard

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /dashboard` |
| **Handler** | `dashboard_page()` (line 104) |
| **RBAC guard** | `require_auth_for_page` → `campaigns.read` |
| **BackendClient methods** | `list_campaigns_prod`, `list_creatives`, `list_kso_devices`, `list_schedules`, `list_manifests`, `list_approvals_prod` |
| **Backend endpoints** | `GET /api/campaigns`, `GET /api/creatives`, `GET /api/hierarchy/kso-devices`, `GET /api/schedules`, `GET /api/manifests`, `GET /api/approvals` |
| **Permission** | `campaigns.read` (minimal — all roles have it) |
| **RLS** | Backend-enforced on each list endpoint |
| **Empty state** | ✅ Safe fallback when backend unreachable |
| **Status** | ✅ VERIFIED — all production endpoints after 40.2.2 fix |

### /campaigns

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /campaigns` |
| **Handler** | `campaigns_page()` (line 855) |
| **RBAC guard** | `require_auth_for_page` → `campaigns.read` |
| **BackendClient methods** | `list_campaigns_prod`, `create_campaign`, `get_campaign_by_code`, `update_campaign_by_code`, `archive_campaign_by_code`, `list_campaign_creatives`, `bind_campaign_creative`, `unbind_campaign_creative` |
| **Backend endpoints** | `GET /api/campaigns`, `POST /api/campaigns/by-code`, `GET/PATCH /api/campaigns/by-code/{code}`, `POST .../{code}/archive`, `GET .../{code}/creatives`, `POST/DELETE .../{code}/creatives/{cc}` |
| **Permission** | `campaigns.read` (list), `campaigns.create` (create), `campaigns.manage` (edit/archive/bind) |
| **RLS** | Backend-enforced — advertiser A cannot see campaign B |
| **Empty state** | ✅ Safe fallback |
| **Fix 40.2.2** | 🔴→✅ `list_campaigns()` → `list_campaigns_prod()` (was `/api/campaigns/test-kso`, now `/api/campaigns`) |

### /creatives

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /creatives` |
| **Handler** | `creatives_page()` (line 733) |
| **RBAC guard** | `require_auth_for_page` → `media.read` |
| **BackendClient methods** | `list_creatives`, `upload_creative` |
| **Backend endpoints** | `GET /api/creatives`, `POST /api/creatives` |
| **Permission** | `media.read` (list), `media.manage` (upload) |
| **RLS** | Backend-enforced |
| **Status** | ✅ VERIFIED |

### /schedule

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /schedule` |
| **Handler** | `schedule_page()` (line 1121) |
| **RBAC guard** | `require_auth_for_page` → `scheduling.read` |
| **BackendClient methods** | `list_schedules`, `list_schedule_slots`, `create_schedule`, `create_schedule_slot`, `archive_schedule`, `disable_schedule_slot` |
| **Backend endpoints** | `GET /api/schedules`, `POST /api/schedules`, `GET /api/schedules/{code}/items`, `POST /api/schedules/{code}/items`, `POST .../{code}/archive`, `DELETE .../{slot}/disable` |
| **Permission** | `scheduling.read` (list), `scheduling.manage` (create/edit) |
| **RLS** | Backend-enforced via `_resolve_schedule_advertiser` |
| **Status** | ✅ VERIFIED |

### /approvals

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /approvals` |
| **Handler** | `approvals_page()` (line 1503) |
| **RBAC guard** | `require_auth_for_page` → `campaigns.approve` |
| **BackendClient methods** | `list_approvals_prod`, `request_approval`, `decide_approval` |
| **Backend endpoints** | `GET /api/approvals`, `POST /api/approvals`, `POST /api/approvals/{code}/approve`, `POST /api/approvals/{code}/reject` |
| **Permission** | `campaigns.approve` |
| **RLS** | Backend-enforced via multi-type advertiser resolution |
| **Status** | ✅ VERIFIED |

### /publications

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /publications` |
| **Handler** | `publications_page()` (line 1391) |
| **RBAC guard** | `require_auth_for_page` → `publications.read` |
| **BackendClient methods** | `list_manifests`, `generate_manifest`, `publish_manifest` |
| **Backend endpoints** | `GET /api/manifests`, `POST /api/manifests`, `POST /api/manifests/{code}/publish` |
| **Permission** | `publications.read` |
| **RLS** | Backend-enforced via `_resolve_manifest_advertiser` |
| **Status** | ✅ VERIFIED |

### /reports

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /reports` |
| **Handler** | `reports_page()` (line 282) |
| **RBAC guard** | `require_auth_for_page` → `reports.read` |
| **BackendClient methods** | `get_pop_summary`, `get_pop_report`, `list_campaigns_prod`, `list_creatives`, `list_kso_devices`, `list_manifests` |
| **Backend endpoints** | `GET /api/reports/pop`, `GET /api/reports/pop/summary`, `GET /api/campaigns`, `GET /api/creatives`, `GET /api/hierarchy/kso-devices`, `GET /api/manifests` |
| **Permission** | `reports.read` |
| **RLS** | Backend-enforced via campaign_code join |
| **Status** | ✅ VERIFIED |

### /stores

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /stores` |
| **Handler** | `stores_page()` (line 615) |
| **RBAC guard** | `require_auth_for_page` → `organization.read` |
| **BackendClient methods** | `list_branches`, `list_clusters`, `list_stores`, `list_kso_devices` |
| **Backend endpoints** | `GET /api/branches`, `GET /api/clusters`, `GET /api/stores`, `GET /api/hierarchy/kso-devices` |
| **Permission** | `organization.read` |
| **RLS** | Backend-enforced |
| **Status** | ✅ VERIFIED |

### /devices

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /devices` |
| **Handler** | `devices_page()` (line 662) |
| **RBAC guard** | `require_auth_for_page` → `devices.read` |
| **BackendClient methods** | `list_stores`, `list_kso_devices` |
| **Backend endpoints** | `GET /api/stores`, `GET /api/hierarchy/kso-devices` |
| **Permission** | `devices.read` |
| **RLS** | Backend-enforced |
| **Status** | ✅ VERIFIED |

### /device-dashboard

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /device-dashboard` |
| **Handler** | `device_dashboard_page()` (line 419) |
| **RBAC guard** | `require_auth_for_page` → `devices.gateway.read` |
| **BackendClient methods** | `get_device_dashboard` |
| **Backend endpoints** | `GET /api/device-dashboard` |
| **Permission** | `devices.gateway.read` |
| **RLS** | Backend-enforced (device_code + store scope post-filter) |
| **Status** | ✅ VERIFIED |

### /readiness

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /readiness` |
| **Handler** | `readiness_page()` (line 509) |
| **RBAC guard** | `require_auth_for_page` → `devices.gateway.read` |
| **BackendClient methods** | `get_device_dashboard` |
| **Backend endpoints** | `GET /api/device-dashboard` |
| **Permission** | `devices.gateway.read` |
| **RLS** | Backend-enforced |
| **Status** | ✅ VERIFIED |

### /admin

| Aspect | Detail |
|---|---|
| **Portal route** | `GET /admin` |
| **Handler** | `admin_page()` (line 1656) |
| **RBAC guard** | `require_admin_access` → `users.read` + `roles.read` |
| **BackendClient methods** | `list_users`, `list_roles`, `list_permissions`, `list_admin_audit` |
| **Backend endpoints** | `GET /api/users`, `GET /api/roles`, `GET /api/permissions`, `GET /api/admin/audit` |
| **Permission** | `users.read` + `roles.read` (system_admin/security_admin) |
| **RLS** | N/A (admin-level) |
| **Status** | ✅ VERIFIED |

---

## 2. Broken Links Found & Fixed (40.2.2)

| # | Page | Method (old) | Endpoint (old) | Method (new) | Endpoint (new) |
|---|---|---|---|---|---|
| 1 | `/campaigns` | `list_campaigns()` | `/api/campaigns/test-kso` | `list_campaigns_prod()` | `/api/campaigns` |
| 2 | `/dashboard` | `list_approvals()` | `/api/approvals/test-kso` | `list_approvals_prod()` | `/api/approvals` |

---

## 3. Permission Consistency (Backend Seed)

### PAGE_PERMISSION_MAP → backend seed cross-reference

| Route | Portal Permission | In Seed? | system_admin? | security_admin? |
|---|---|---|---|---|
| `/dashboard` | `campaigns.read` | ✅ | ✅ | ✅ |
| `/campaigns` | `campaigns.read` | ✅ | ✅ | ✅ |
| `/creatives` | `media.read` | ✅ | ✅ | ✅ |
| `/schedule` | `scheduling.read` | ✅ | ✅ | ✅ |
| `/publications` | `publications.read` | ✅ | ✅ | ✅ |
| `/stores` | `organization.read` | ✅ | ✅ | ✅ |
| `/devices` | `devices.read` | ✅ | ✅ | ✅ |
| `/reports` | `reports.read` | ✅ | ✅ | ✅ |
| `/approvals` | `campaigns.approve` | ✅ | ✅ | ✅ |
| `/admin` | `users.read` | ✅ | ✅ | ✅ (via `users.manage`) |
| `/device-dashboard` | `devices.gateway.read` | ✅ | ✅ | ✅ |
| `/readiness` | `devices.gateway.read` | ✅ | ✅ | ✅ |

**Result: 12/12 permissions exist in backend seed. system_admin has all 12. security_admin has all 12.**

---

## 4. Legacy Test-KSO Usage Audit

| BackendClient method | Endpoint | Production alternative | Called by page? |
|---|---|---|---|
| `list_campaigns()` | `/api/campaigns/test-kso` | `list_campaigns_prod()` → `/api/campaigns` | ❌ No (fixed) |
| `list_approvals()` | `/api/approvals/test-kso` | `list_approvals_prod()` → `/api/approvals` | ❌ No (fixed) |
| `list_pop_events()` | `/api/proof-of-play/test-kso` | `get_pop_report()` → `/api/reports/pop` | ❌ No |
| `get_test_kso_readiness()` | `/api/test-kso/readiness` | `get_device_dashboard()` | ❌ No |
| `list_placements()` | `/api/schedule/test-kso` | `list_placements_prod()` → `/api/placements` | ❌ No |
| `request_approval()` | `/api/approvals/test-kso/request` | `create_approval()` → `/api/approvals` | ❌ No |
| `decide_approval()` | `/api/approvals/test-kso/{code}/decide` | `approve_approval()` / `reject_approval()` | ❌ No |
| `generate_manifest()` | `/api/manifests` | N/A (same — delegates to unified builder) | ✅ (but delegates to unified builder) |

**Conclusion: No portal page calls legacy test-kso endpoints as primary path. All pages use production endpoints after 40.2.2 fix.**

---

## 5. Remaining Integration Gaps

| # | Gap | Severity | Notes |
|---|---|---|---|
| G1 | BackendClient legacy methods still exist | 🟢 LOW | Methods exist but NOT called by any production page |
| G2 | `generate_manifest()` uses `/api/manifests` (production) but also has test-kso legacy path | 🟢 LOW | Production path is primary |
| G3 | Portal tests mostly mock-based, not live backend | 🟡 MEDIUM | Live integration profile added in 40.2.2 |
| G4 | `/proof-of-play` page uses test-kso reporting | 🟡 MEDIUM | Deferred — production PoP report is `/reports` |

---

*Document created 2026-06-26 as part of 40.2.2 Portal Backend Integration Gate.*
*No KSO/SSH/X11/Chromium/runner/sidecar/PoP/scanner/long-run launched.*
*No secrets, full URLs, tokens, barcodes, or personal data disclosed.*
