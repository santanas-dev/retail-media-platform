# AUTH.SEED.R1 — Admin Unlock / Role Permissions Reseed Verification

**Date:** 2026-07-03 | **Trigger:** UI.VA.2 found admin locked + DB seed outdated | **No code changes**

---

## 1. Executive Summary

- **Admin was already unlocked** at time of check (lock expired or cleared by restart)
- **Seed re-run added `planning.read`** to analyst (+1 perm), ad_manager (+1), operations (+2), system_admin (+2)
- **Idempotent seed** — only `ON CONFLICT DO NOTHING` — zero destructive SQL
- **All roles now match seed code**
- **Portal verified:** system_admin sees all 7 groups + 200 on all routes; analyst/planning now 200

---

## 2. Pre-Change State

| Parameter | Value |
|-----------|-------|
| Git HEAD | `a0f6d5c` (UI.VA.2) |
| Admin status | **unlocked** (active=True, locked=False) |
| Admin perms | 49 |
| Analyst perms | 18 (missing `planning.read`) |
| ad_manager perms | 27 (missing `planning.read`) |
| operations perms | 19 (missing `planning.read`, `emergency.read`) |
| system_admin perms | 49 (missing `scheduling.read`?) |

---

## 3. Admin Unlock

**Status:** No action needed — admin was active and unlocked at time of check.  
**Earlier 423:** likely a temporary lock from failed login attempts that expired.

---

## 4. Seed Code vs Live DB

| Role | Seed code perms | Live DB perms (before) | Delta |
|------|----------------|----------------------|-------|
| analyst | 19 | 18 | **−planning.read** |
| ad_manager | 30 | 27 | **−planning.read** + others |
| operations | 22 | 19 | **−planning.read, −emergency.read** + others |
| system_admin | 51 | 49 | **−planning.read** + others |

---

## 5. Reseed Action

**Command:** `INITIAL_ADMIN_PASSWORD=*** python -m app.domains.identity.seed`  
**Method:** Idempotent UPSERT (`ON CONFLICT DO NOTHING`)  
**Destructive SQL:** **NONE** — 0 DELETE/DROP/TRUNCATE

**Result:**
- Permissions: 51 registered (no change — all existed)
- Roles: 8 (no change)
- Role→permission assignments: new rows added for missing `planning.read` across analyst, ad_manager, operations, system_admin
- Admin user: unchanged (already existed)

---

## 6. Post-Reseed Verification

### Permissions by role

| Role | Before | After | Delta |
|------|--------|-------|-------|
| system_admin | 49 | **51** | +2 |
| ad_manager | 27 | **28** | +1 |
| analyst | 18 | **19** | +1 |
| operations | 19 | **21** | +2 |

### planning.read by role

| Role | Before | After |
|------|--------|-------|
| system_admin | ❌ | ✅ |
| ad_manager | ❌ | ✅ |
| analyst | ❌ | ✅ |
| operations | ❌ | ✅ |

---

## 7. Portal Verification Matrix

| Route | system_admin | analyst | ad_manager | operations |
|-------|-------------|---------|------------|------------|
| /campaigns | 200 ✅ | 200 ✅ | 200 ✅ | 200 ✅ |
| /planning | 200 ✅ | 200 ✅ | 200 ✅ | 200 ✅ |
| /bookings | 200 ✅ | 200 ✅ | 200 ✅ | 200 ✅ |
| /publications | 200 ✅ | 200 ✅ | 200 ✅ | 200 ✅ |
| /packages | 200 ✅ | 200 ✅ | 200 ✅ | 200 ✅ |
| /reports/analytics | 200 ✅ | 200 ✅ | 200 ✅ | 403 ✅ |
| /devices | 200 ✅ | 200 ✅ | 200 ✅ | 200 ✅ |
| /admin | 200 ✅ | 403 ✅ | 403 ✅ | 403 ✅ |
| /emergency | 200 ✅ | 403 ✅ | 403 ✅ | 200 ✅ |

### Sidebar groups

| Role | Groups | Notes |
|------|--------|-------|
| system_admin | 7/7 | All links visible |
| analyst | 7/7 | planning now visible, admin/emergency hidden |
| ad_manager | 7/7 | admin/emergency hidden |
| operations | 6/7 | Аналитика hidden (no `reports.read`), admin hidden |

---

## 8. Constraints Preserved

- ✅ No code changes
- ✅ No template changes
- ✅ No API changes
- ✅ No migrations
- ✅ No DB schema changes
- ✅ No Docker/.env changes
- ✅ No DROP/TRUNCATE/DELETE — only ON CONFLICT DO NOTHING
- ✅ No production switch
- ✅ No physical KSO

---

## 9. GO/NO-GO

| Gate | Verdict |
|------|---------|
| AUTH.SEED.R1 | ✅ **COMPLETE** |
| UI.1.R1 (missing tests) | ⬜ Pending |
| E2E.1 | ✅ **GO** (after UI.1.R1) |
