# Access Review Checklist

**Date:** 2026-07-02 | **Last review:** 2026-07-01 (H.4) | **Owner:** Security Admin (TBD)

> Review all roles, permissions, and access before pilot.

---

## 1. Role Inventory

| Role | Users (count) | Review | Notes |
|---|---|---|---|
| system_admin | TBD | ✅ (H.4) | Full access — limit to 1-2 people |
| security_admin | TBD | ✅ (H.4) | User management + audit |
| ad_manager | TBD | ⬜ | Campaign + media management |
| approver | TBD | ⬜ | Campaign/creative approval |
| analyst | TBD | ⬜ | Reports + analytics |
| advertiser | TBD | ⬜ | Own campaigns + reports |
| operations | TBD | ✅ (H.4) | Device management + monitoring. **Note:** has `publications.publish` — acceptable risk for pilot |
| device_service | Machine only | ✅ | Gateway-only, no portal |

**H.4 Verification:**
- ✅ `device_service` has ONLY gateway permissions (3 total: read, manage, credentials)
- ✅ `advertiser` has minimal permissions (campaigns.read, planning.read, reports.read)
- ✅ `operations` has `emergency.read` (3 roles total)
- ✅ No role has `emergency.execute` or `emergency.approve` (not even defined)

---

## 2. Sensitive Permission Review

| Permission | Who Has It | Review |
|---|---|---|
| `emergency.read` | system_admin, security_admin, operations | ✅ Verified H.4 — exact 3 roles |
| `emergency.manage` | system_admin only | ✅ Exists but NOT used in API — documented |
| `reports.read` | Multiple roles | ⬜ Broad — review before pilot |
| `planning.read` | Multiple roles | ✅ Acceptable |
| `publications.publish` | system_admin, operations | ⚠️ operations should not publish without approval — risk accepted for pilot |
| `devices.gateway.credentials` | system_admin, security_admin, operations | ⚠️ High sensitivity — review before pilot |
| `users.manage` | system_admin, security_admin | ✅ OK |
| `users.create` | system_admin only | ✅ OK |
| `audit.read` | system_admin, security_admin | ✅ OK |

---

## 3. Service Account Review

| Service Account | Permissions | Review |
|---|---|---|
| device_service (Gateway) | devices.gateway.read, devices.gateway.manage, devices.gateway.credentials | ✅ OK — machine-only, no portal access |
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
| No role has more permissions than needed | ⚠️ operations has publications.publish — risk accepted for pilot |
| device_service restricted to Gateway only | ✅ |
| advertiser restricted to own campaigns | ✅ (RLS) |
| operations cannot approve/publish without review | ⚠️ operations CAN publish — documented risk |
| analyst cannot modify | ✅ (read-only permissions) |
| emergency.read restricted | ✅ (3 roles only) |
| emergency.execute/approve absent | ✅ (not defined) |

---

## 6. H.4 Middleware Security Review

| Check | Status |
|---|---|
| Security headers on all responses | ✅ 9 headers |
| CORS: no wildcard + credentials | ✅ Fixed — explicit origins |
| Rate limiting: sensitive endpoints | ✅ 5/10/20/30 req per 60s |
| Rate limiter: no Redis dependency | ✅ In-memory |
| HSTS: not forced | ✅ (pending HTTPS decision) |
| CSP: not added | ✅ (pending UI security gate) |

---

## 7. Audit Trail Review

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

## 8. Pre-Pilot Sign-Off

| Check | Owner | Date | Signature |
|---|---|---|---|
| All roles reviewed | Security Admin | | |
| Sensitive permissions verified | Security Admin | | |
| Service accounts listed | Ops | | |
| Admin access audited | Security Admin | | |
| Least privilege confirmed | Security Admin | | |
| Audit trail verified | Security Admin | | |
| Security headers deployed | Dev (H.4) | 2026-07-01 | ✅ |
| CORS fixed (no wildcard+credentials) | Dev (H.4) | 2026-07-01 | ✅ |
| Rate limiting active | Dev (H.4) | 2026-07-01 | ✅ |
