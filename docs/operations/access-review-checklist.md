# Access Review Checklist

**Date:** 2026-07-02 | **Phase:** H.1 | **Owner:** Security Admin (TBD)

> Review all roles, permissions, and access before pilot.

---

## 1. Role Inventory

| Role | Users (count) | Review | Notes |
|---|---|---|---|
| system_admin | TBD | ⬜ | Full access — limit to 1-2 people |
| security_admin | TBD | ⬜ | User management + audit |
| ad_manager | TBD | ⬜ | Campaign + media management |
| approver | TBD | ⬜ | Campaign/creative approval |
| analyst | TBD | ⬜ | Reports + analytics |
| advertiser | TBD | ⬜ | Own campaigns + reports |
| operations | TBD | ⬜ | Device management + monitoring |
| device_service | Machine only | ✅ | Gateway-only, no portal |

---

## 2. Sensitive Permission Review

| Permission | Who Has It | Review |
|---|---|---|
| `emergency.read` | system_admin, security_admin, operations | ⬜ Verify no advertiser/analyst/device_service |
| `emergency.manage` | system_admin only | ⬜ Not used by API — review need |
| `reports.read` | Multiple roles | ⬜ Broad — review |
| `planning.read` | Multiple roles | ⬜ Acceptable |
| `publications.publish` | system_admin, operations | ⬜ operations should not publish without approval |
| `devices.gateway.credentials` | system_admin, security_admin, operations | ⬜ Highest sensitivity — review |
| `users.manage` | system_admin, security_admin | ⬜ OK |
| `users.create` | system_admin only | ⬜ OK |
| `audit.read` | system_admin, security_admin | ⬜ OK |

---

## 3. Service Account Review

| Service Account | Permissions | Review |
|---|---|---|
| device_service (Gateway) | devices.gateway.* | ⬜ OK — machine-only |
| (others? TBD) | | ⬜ List all service accounts |

---

## 4. Admin Access Review

| Check | Status |
|---|---|
| Admin users documented | ⬜ |
| MFA enabled (if supported) | ⬜ |
| Admin password rotation | ⬜ |
| Break-glass account exists | ⬜ |
| Admin access audit log enabled | ✅ |

---

## 5. Least Privilege Checklist

| Principle | Status |
|---|---|
| No role has more permissions than needed | ⬜ Review |
| device_service restricted to Gateway only | ✅ |
| advertiser restricted to own campaigns | ✅ (RLS) |
| operations cannot approve/publish without review | ⬜ Review `publications.publish` |
| analyst cannot modify | ✅ (read-only permissions) |
| emergency.read restricted | ✅ (3 roles only) |

---

## 6. Audit Trail Review

| Event Type | Status |
|---|---|
| Login attempts | ⬜ Verify logged |
| Permission changes | ⬜ Verify logged |
| Role assignments | ⬜ Verify logged |
| Emergency API calls | ✅ (4 audit events) |
| Analytics API calls | ✅ (audit events) |
| Publication events | ⬜ Verify logged |
| User block/archive | ⬜ Verify logged |

---

## 7. Pre-Pilot Sign-Off

| Check | Owner | Date | Signature |
|---|---|---|---|
| All roles reviewed | Security Admin | | |
| Sensitive permissions verified | Security Admin | | |
| Service accounts listed | Ops | | |
| Admin access audited | Security Admin | | |
| Least privilege confirmed | Security Admin | | |
| Audit trail verified | Security Admin | | |
