# Security Hardening Register — 42.4

**Date:** 2026-06-16  
**Baseline:** HEAD `c3b8daa` (42.3)  
**Security Posture:** Good — no critical findings from audit

---

## 1. Authentication & Authorization

### 1.1 User Auth (Portal)

| Check | Status |
|---|---|
| Password hashing | ✅ bcrypt (verified) |
| Session management | ✅ httpOnly cookie, 1h max age |
| Login audit | ✅ Every attempt logged (success/failure) |
| MFA | ⚠️ Architectural preparation only — `mfa_enabled`, `mfa_secret` fields exist, no implementation |
| Rate limiting | ⚠️ Login rate limiting not verified in production config |
| SSO | ⚠️ SSO button disabled — architectural placeholder |

**Debt:**
- **S-AU-01 (P1):** Implement MFA for `system_admin` and `security_admin` roles
- **S-AU-02 (P2):** Verify login rate limiting in production config
- **S-AU-03 (P2):** SSO integration (AD/LDAP) deferred

### 1.2 Device Auth (KSO)

| Check | Status |
|---|---|
| Device secret | ✅ bcrypt hash, never in response |
| JWT expiry | ✅ 60 minutes |
| Device identity | ✅ `device_code` verified against registry |
| Secret rotation | ❌ Not implemented |
| Device revocation | ⚠️ `is_active=False` exists, no forced re-auth on revocation |

**Debt:**
- **S-DA-01 (P2):** Implement device_secret rotation
- **S-DA-02 (P2):** Add forced re-auth on device disable/revocation

---

## 2. RBAC / RLS

### 2.1 Permission Coverage

| Check | Status |
|---|---|
| All production endpoints have `require_permission()` | ✅ Verified (50+ endpoints) |
| Admin bypass scope | ✅ `system_admin`, `security_admin` — full access |
| 404 for out-of-scope | ✅ Prevents information leakage |
| CSV exports RLS | ✅ advertiser anonymization, admin-only fields |

**No new debt.**

### 2.2 RLS Scope Resolution

| Check | Status |
|---|---|
| Advertiser scope | ✅ Resolved via `advertiser_scope` → UUID |
| Branch scope | ✅ Resolved via `branch_scope` → branch ID |
| Store scope | ✅ Resolved via `store_scope` → store ID |
| Device scope | ✅ Direct `device_code` match |
| Campaign scope | ✅ Direct `campaign_code` match |
| Report scope | ✅ Maps to `reports.read` permission |

**No new debt.**

---

## 3. Data Protection

### 3.1 Secrets / Tokens

| Check | Status |
|---|---|
| `device_secret` in responses | ✅ Never returned |
| `access_token` in HTML | ✅ Never in portal HTML |
| Backend URL in HTML/CSV | ✅ Never exposed |
| MinIO paths in responses | ✅ Never returned (42.2) |
| Signed URLs in responses | ✅ Never generated |

**No new debt.**

### 3.2 Safe Projections

| Check | Status |
|---|---|
| Pydantic schemas limit response fields | ✅ |
| CSV export filters admin-only columns | ✅ (42.3) |
| Conflict anonymization | ✅ Advertiser sees no foreign campaign names |
| 404 for forbidden (not 403) | ✅ Consistent |

**No new debt.**

### 3.3 Audit Trail

| Check | Status |
|---|---|
| Admin actions audited | ✅ `AdminAuditEvent` |
| Login attempts audited | ✅ `LoginAuditEvent` |
| Device auth failures audited | ✅ `device_gateway/service.py:82` |
| Audit immutability | ✅ No UPDATE on audit tables |
| Audit coverage gaps | ⚠️ No audit for export/download actions |

**Debt:**
- **S-AT-01 (P2):** Add audit events for CSV export/download actions

---

## 4. Input Validation

| Check | Status |
|---|---|
| SQL injection | ✅ SQLAlchemy ORM, parameterized queries |
| XSS | ✅ Jinja2 auto-escaping, no user HTML in responses |
| CSRF | ⚠️ No CSRF tokens on forms (all GET-only exports mitigate this for 42.3) |
| Path traversal | ✅ No file path from user input in production |
| File upload validation | ✅ Content-Type check, size limits on creative upload |

**Debt:**
- **S-IV-01 (P2):** Add CSRF tokens to POST forms (schedule, campaign create, etc.)
- **S-IV-02 (P2):** Add rate limiting on creative upload endpoint

---

## 5. Transport Security

| Check | Status |
|---|---|
| HTTPS in production | ⚠️ Not verified — localhost dev environment |
| HSTS | ❌ Not configured |
| Certificate management | ❌ Not addressed |
| mTLS for device gateway | ⚠️ Architectural placeholder — "позже" in docs |

**Debt:**
- **S-TS-01 (P1):** Configure HTTPS for production deployment
- **S-TS-02 (P2):** Add HSTS headers
- **S-TS-03 (P2):** mTLS for device-to-backend communication (deferred)

---

## 6. Dependency & Environment

| Check | Status |
|---|---|
| Python version | 3.11.15 (dev), 3.6.9 (KSO) |
| `fromisoformat` compatibility | ⚠️ Replaced with strptime for KSO 3.6.9 |
| `| None` syntax | ⚠️ Replaced with `Optional`/`Union` for KSO 3.6.9 |
| `.env` in git | ✅ gitignored |
| Secrets in test files | ⚠️ `test-dev-seed` used as test device_code — acceptable for tests |

**No new debt.**

---

## 7. KSO-Specific

| Check | Status |
|---|---|
| UKM5 DB isolation | ✅ No access to UKM5 DB/receipt/payment/customer data |
| X11 isolation | ✅ Player uses dedicated X display |
| Chromium sandbox | ⚠️ Not explicitly configured |
| Player process isolation | ✅ Separate systemd units |
| File permissions | ⚠️ Not audited on physical KSO |

**Debt:**
- **S-KS-01 (P1):** Audit file permissions on physical KSO
- **S-KS-02 (P2):** Configure Chromium sandbox flags

---

## Summary

| Category | P1 | P2 | Total |
|---|---|---|---|
| Auth | 1 | 3 | 4 |
| RBAC/RLS | 0 | 0 | 0 |
| Data Protection | 0 | 1 | 1 |
| Input Validation | 0 | 2 | 2 |
| Transport | 1 | 2 | 3 |
| Dependencies | 0 | 0 | 0 |
| KSO | 1 | 1 | 2 |
| **Total** | **3** | **9** | **12** |

**No P0 security findings. Platform is secure enough for controlled pilot with hardening items addressed beforehand.**
