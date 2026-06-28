# RBAC & RLS Audit — 45.2

**Date:** 2026-06-28
**Part of:** Pre-demo functional audit (45.2)
**HEAD:** `c000e67`
**Demo tag:** `v0.9.0-rc0-business-demo.3` → `d78e23f`

---

## RBAC: Permission Matrix

### Roles (8 total)

| # | Code | Name | Portal Access |
|---|------|------|---------------|
| 1 | system_admin | System Administrator | Full (all pages) |
| 2 | security_admin | Security Administrator | Admin pages |
| 3 | ad_manager | Ad Manager | Campaign/media ops |
| 4 | approver | Approver | Approval workflow |
| 5 | analyst | Analyst | Reports read-only |
| 6 | advertiser | Advertiser | Own campaigns only |
| 7 | operations | Operations | Device/inventory ops |
| 8 | device_service | Device Service | Machine-only (no portal) |

### Permissions (47 total)

Full permission list in `backend/app/domains/identity/seed.py:28-79`.

### system_admin Permissions (all 47)

```
users.read, users.create, users.manage,
roles.read, roles.manage,
permissions.read, permissions.manage,
channels.read, channels.manage, devices.read, devices.manage,
organization.read, organization.manage,
advertisers.read, advertisers.manage,
brands.read, brands.manage,
contracts.read, contracts.manage,
orders.read, orders.manage,
campaigns.read, campaigns.create, campaigns.manage, campaigns.approve,
media.read, media.manage, media.approve,
inventory.read, inventory.manage,
bookings.read, bookings.manage, bookings.approve,
scheduling.read, scheduling.manage, scheduling.approve,
publications.read, publications.manage, publications.approve, publications.publish,
devices.gateway.read, devices.gateway.manage, devices.gateway.credentials,
reports.read, reports.export,
campaign_reports.read, campaign_reports.manage,
audit.read,
emergency.manage
```

---

## RLS: Scope Enforcement

### Mechanism

`assert_object_in_advertiser_scope(advertiser_id, ctx)` in `backend/app/domains/identity/rls.py:210`:
- Admin users (is_admin=True): bypass — always allowed
- Scoped users (is_advertiser_scoped=True): must match advertiser_ids
- Non-scoped users with permission: **warning** — sees everything (scope-less access)
- Uses HTTP 404 (not 403) to avoid leaking object existence

### Verified Checks (21/21 PASS after fix)

| # | Test | Expected | Actual | Result |
|---|------|----------|--------|--------|
| C1 | Adv-A lists own campaigns | Only Adv-A | 1 campaign visible | ✅ |
| C2 | Adv-A cannot see Adv-B in list | Adv-B absent | PASS | ✅ |
| C3 | Adv-B lists own campaigns | Only Adv-B | 19 campaigns visible | ✅ |
| C4 | Adv-B cannot see Adv-A in list | Adv-A absent | PASS | ✅ |
| C5 | Adv-A → Adv-B by UUID | 404 | 404 | ✅ |
| C6 | Adv-B → Adv-A by UUID | 404 | 404 | ✅ |
| C7 | Adv-A → Adv-B channels | 404 | 404 | ✅ |
| C8 | Adv-A → Adv-B targets | 404 | 404 | ✅ |
| C9 | Adv-A → Adv-B renditions | 404 | 404 | ✅ |
| C10 | Adv-A PUT Adv-B campaign | 404 | 404 | ✅ |
| C11 | Adv-A submit Adv-B campaign | 404 | 404 | ✅ |
| C12 | Adv-A approve Adv-B campaign | 404 | 404 | ✅ |
| C13 | Adv-A reject Adv-B campaign | 404 | 404 | ✅ |
| M1 | Adv-A media: no cross-advertiser | Clean | PASS | ✅ |
| A1 | Analyst can read campaigns | 200 | 200 | ✅ |
| A2 | Analyst cannot create | 403 | 403 | ✅ |
| A3 | Analyst cannot update | 403 | 403 | ✅ |
| D1 | Advertiser cannot access /api/users | 403 | 403 | ✅ |
| D2 | Advertiser cannot access /api/admin/audit | 403 | 403 | ✅ |
| E1 | Admin sees all campaigns | All visible | PASS | ✅ |
| E2 | Admin accesses audit | 200 | 200 | ✅ |

### Fixed Vulnerabilities

**Before fix (HEAD `0aa4bda`):** 5 CRITICAL RLS bypasses
- `GET /api/campaigns/{id}` — returned cross-advertiser data (HTTP 200)
- `GET /api/campaigns/{id}/channels` — returned cross-advertiser data
- `GET /api/campaigns/{id}/targets` — returned cross-advertiser data
- `GET /api/campaigns/{id}/renditions` — returned cross-advertiser data
- `PUT /api/campaigns/{id}` — allowed cross-advertiser modification (HTTP 403 leaked existence)

**After fix (HEAD `c000e67`):** All return 404 for cross-advertiser access.

### Info Leak Warnings (resolved by 404)

PUT/POST endpoints previously returned 403 (permission denied) for cross-advertiser access, leaking object existence. Now return 404 (consistent with GET behavior).

---

## RBAC: Page-Level Access

All 15 portal pages tested under system_admin:

```
/dashboard                     → 200
/creatives                     → 200
/creatives/moderation/queue    → 200
/campaigns                     → 200
/campaigns/create              → 200
/schedule                      → 200
/approvals                     → 200
/publications                  → 200
/reports                       → 200
/inventory                     → 200
/readiness                     → 200
/readiness/business-acceptance → 200
/stores                        → 200
/admin                         → 200
/deployment                    → 200
```

Sidebar menu shows all 15 items including "⚙️ Администрирование".

---

## Account Security

| Check | Status |
|-------|--------|
| Password bcrypt-hashed | ✅ `password_hash` column |
| Brute-force lockout (5 attempts → 30 min) | ✅ verified (admin was locked) |
| Locked account → HTTP 423 | ✅ |
| JWT access token (15 min) | ✅ |
| JWT refresh token | ✅ |
| httpOnly session cookie (portal) | ✅ |
| Service accounts blocked from portal login | ✅ `is_service_account` check |
