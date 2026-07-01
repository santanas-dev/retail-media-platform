# Secrets Management Checklist

**Date:** 2026-07-02 | **Last review:** 2026-07-01 (H.4) | **Owner:** Ops / Security (TBD)

> Verify no secrets in repo/logs/responses/portal HTML before pilot.

---

## 1. No Secrets in Git Repo

| Check | Status | Scan Method |
|---|---|---|
| `.env` files in `.gitignore` | ✅ | Git check |
| No hardcoded passwords in source | ✅ | Code review |
| No API keys in source | ✅ | Code review |
| No tokens in test files (except placeholders) | ✅ | Code review |
| Git history scan (no leaked secrets in past) | ⬜ | `git secrets --scan-history` or truffleHog |

**H.4 Verification:**
- ✅ All 3 new middleware files: no secrets, no credentials, no tokens
- ✅ `cors_config.py`: only localhost origins
- ✅ `rate_limiter.py`: IP+path key only, no user_id/token
- ✅ `security_headers.py`: static headers only, no secrets

---

## 2. Environment Config

| Check | Status | Notes |
|---|---|---|
| `.env.example` has placeholders only | ✅ | `<PLACEHOLDER>` for sensitive keys |
| Production `.env` outside repo | ⬜ | `/etc/retail-media/.env` or vault |
| Database password not in shared config | ⬜ | Vault or secrets manager |
| Portal session secret not dev default | ⬜ | Generate from vault |
| MinIO credentials in vault | ⬜ | Not in compose/env |

**H.4 Verification:**
- ✅ `backup.env.example` — all sensitive keys use `<PLACEHOLDER>` format
- ✅ `deploy.env.example` — all sensitive keys use `<PLACEHOLDER>` format
- ✅ Port numbers (5432) and paths (/backups/pg) are acceptable defaults

---

## 3. Token Storage

| Check | Status | Notes |
|---|---|---|
| JWT secret in vault | ⬜ | Not in `.env` |
| Refresh tokens hashed in DB | ✅ | Hashed via backend |
| Gateway device tokens hashed | ✅ | DB hashed |
| Admin password hashed | ✅ | bcrypt |
| No plaintext tokens in logs | ✅ | No-secrets validators |
| No tokens in audit events | ✅ | Audit sanitized |

**H.4 Verification:**
- ✅ FORBIDDEN_HEADERS: authorization, cookie, set-cookie, x-api-key, proxy-authorization
- ✅ Health responses: no DSN, no password, no token, no secret
- ✅ Metrics: no passwords, DSN, tokens, secrets, pg credentials
- ✅ Emergency responses: no secrets
- ✅ Rate limiter keys: IP+path only, no user_id/token

---

## 4. Device Credentials

| Check | Status | Notes |
|---|---|---|
| Gateway device secrets stored hashed | ✅ | |
| Device token issuance logged | ✅ | |
| Device token rotation mechanism | ❌ | **Needed before pilot** |
| Device token expiry | ⬜ | Define TTL |
| Compromised device revocation | ⬜ | Block device + rotate |

---

## 5. Rotation Process

| What | Rotation Frequency | Status |
|---|---|---|
| DB password | 90 days | ❌ No process |
| JWT signing key | 180 days | ❌ No process |
| MinIO access keys | 90 days | ❌ No process |
| Admin password | 90 days | ❌ No process |
| Gateway device tokens | On compromise | ❌ No process |
| Portal session secret | 180 days | ❌ No process |

---

## 6. Emergency Access

| Check | Status |
|---|---|
| Break-glass admin account exists | ❌ |
| Emergency access logged + alerted | ❌ |
| Emergency access auto-expires (24h) | ❌ |
| Emergency procedure documented | ❌ |

---

## 7. Audit (H.4 update)

| Check | Status |
|---|---|
| All API responses pass no-secrets validation | ✅ |
| Portal HTML passes no-secrets check | ✅ (G.4/G.5) |
| Logs pass no-secrets check | ✅ (FORBIDDEN_HEADERS) |
| Audit events pass no-secrets check | ✅ |
| Emergency payload pass no-secrets check | ✅ (20 keys) |
| Analytics payload pass no-secrets check | ✅ |
| **NEW: Security headers responses safe** | ✅ |
| **NEW: CORS configuration no secrets** | ✅ |
| **NEW: Rate limiter keys no secrets** | ✅ |
| **NEW: Ops scripts no secrets echo** | ✅ |

---

## 8. H.4 Ops Scripts Hardening Verification

| Script | No-secrets check |
|---|---|
| backup_postgres.sh | ✅ PGPASSWORD not echoed |
| restore_postgres.sh | ✅ CONFIRM_RESTORE required |
| backup_minio.sh | ✅ No credentials echoed |
| deploy_preflight.sh | ✅ Read-only, no destructive ops |
| rollback_preflight.sh | ✅ ROLLBACK_APPROVAL required |
| backup.env.example | ✅ Sensitive keys are `<PLACEHOLDER>` |
| deploy.env.example | ✅ Sensitive keys are `<PLACEHOLDER>` |

---

## 9. Incident Handling

| Scenario | Response |
|---|---|
| Secret found in logs | Rotate immediately, clean logs |
| Token leaked in git | Rotate, squash history, force push |
| Credential compromise suspected | Block account, rotate all tokens, audit |
| Production `.env` exposed | Rotate ALL secrets immediately |

---

## 10. Pre-Pilot Sign-Off

| Check | Owner | Date | Signature |
|---|---|---|---|
| Git scan: no secrets | Security | | |
| `.env` not in repo | Ops | | |
| Production secrets in vault | Ops | | |
| Token rotation documented | Ops | | |
| Emergency access configured | Security | | |
| No-secrets validators active | Dev | | |
| **H.4: Security headers + CORS + rate limit** | Dev | 2026-07-01 | ✅ |
| **H.4: Access review verified** | Security | 2026-07-01 | ✅ |
| **H.4: Ops scripts hardened** | Ops | 2026-07-01 | ✅ |
