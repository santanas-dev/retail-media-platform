# Production Readiness Checklist

**Date:** 2026-07-02 | **Last review:** 2026-07-01 (H.5) | **Owner:** Ops Team (TBD)

> Status: 🟡 PARTIAL — H.2–H.4 closed 11 gaps; 8 blocking items remain; pilot NOT READY.

---

## 1. Environment / Config

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 1.1 | Production `.env` template exists | ⬜ Missing | Yes | — | Create from dev template |
| 1.2 | PostgreSQL production config (pool, timeouts) | ⬜ Missing | Yes | — | Review defaults vs 40k profile |
| 1.3 | MinIO production config (retention, quotas) | ⬜ Missing | No | — | Set quotas |
| 1.4 | Redis production config | ⬜ Missing | No | — | Set memory limits |
| 1.5 | Backend port/host production config | ⬜ Missing | Yes | — | `DOMAIN`/`PORT` env vars |
| 1.6 | Portal session secret (not dev default) | ⬜ Missing | Yes | — | Generate from vault/secret manager |
| 1.7 | CORS config for production domains | ✅ **H.4** | No | `SafeCORSMiddleware` | Update origins for production |

---

## 2. Secrets Management

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 2.1 | No secrets in git repo (scan pass) | ✅ Ready | Yes | No-secrets validators | Periodic scan |
| 2.2 | `.env` not committed | ✅ Ready | Yes | `.gitignore` | Verify |
| 2.3 | DB password in vault/secret manager | ⬜ Missing | Yes | — | Move from `.env` to vault |
| 2.4 | Gateway device tokens stored securely | 🟡 Partial | Yes | DB hashed | Add rotation |
| 2.5 | Admin password rotation process | ⬜ Missing | No | — | Document rotation |
| 2.6 | Emergency access procedure | ⬜ Missing | No | — | Break-glass account |
| 2.7 | No secrets in logs/audit/portal HTML | ✅ **H.4** | Yes | FORBIDDEN_HEADERS + validators | Maintain |
| 2.8 | No secrets in ops scripts | ✅ **H.4** | Yes | `backup_postgres.sh` PGPASSWORD not echoed | Maintain |
| 2.9 | No secrets in `.env.example` files | ✅ **H.4** | Yes | `<PLACEHOLDER>` for sensitive keys | Maintain |

---

## 3. Access / RBAC / RLS

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 3.1 | Role-permission map documented | ✅ Ready | No | `seed.py` | Review annually |
| 3.2 | Least privilege review (all roles) | ✅ **H.4** | Yes | Access review verified | Periodic audit |
| 3.3 | `device_service` restrictions verified | ✅ Ready | Yes | G.5 tests | Maintain |
| 3.4 | `advertiser` restrictions verified | ✅ Ready | Yes | G.5 tests | Maintain |
| 3.5 | Admin access audit log enabled | ✅ Ready | Yes | Audit events | Review |
| 3.6 | Service account review | ⬜ Missing | No | — | List all service accounts |
| 3.7 | RLS scope enforcement (advertiser, store, channel) | ✅ Ready | Yes | F.4.1 tests | Add scope docs |
| 3.8 | `emergency.read` exact 3 roles | ✅ **H.4** | Yes | H.4 tests | Maintain |
| 3.9 | No `emergency.execute`/`emergency.approve` | ✅ **H.4** | Yes | Not defined in seed | Maintain |

---

## 4. Device Gateway

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 4.1 | Auth/token endpoint functional | ✅ Ready | Yes | Gateway tests | Monitor |
| 4.2 | Heartbeat endpoint functional | ✅ Ready | Yes | Gateway tests | Set thresholds |
| 4.3 | Manifest universal preview functional | ✅ Ready | Yes | E tests | Monitor |
| 4.4 | PoP ingestion (legacy + enterprise) | ✅ Ready | Yes | F tests | Monitor |
| 4.5 | Media delivery endpoint functional | ✅ Ready | No | Gateway tests | Cache config |
| 4.6 | Rate limiting on all gateway endpoints | ✅ **H.4** | No | In-memory, 30/60s default | Production: Redis-backed |
| 4.7 | Credential rotation mechanism | ❌ Missing | **Yes** | — | Implement before production |
| 4.8 | Device lifecycle (register/block/unregister) | ✅ Ready | No | Gateway API | Monitor |
| 4.9 | Gateway health endpoint | ✅ Ready | No | `/health` | Monitor |

---

## 5. KSO Devices

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 5.1 | Physical KSO device available (192.168.110.223) | 🟡 Partial | **Yes** | UKM5 present | **Test** |
| 5.2 | Ad zone dimensions verified (768×1024) | ❌ Not tested | **Yes** | — | **Measure** |
| 5.3 | Chromium kiosk ready | ❌ Not tested | **Yes** | — | **Test** |
| 5.4 | Network connectivity to Gateway | ❌ Not tested | **Yes** | — | **Ping/curl** |
| 5.5 | Legacy manifest unchanged | ✅ Ready | Yes | Route unchanged | Verify |
| 5.6 | KSO production switch | ❌ NO-GO | — | Design gate required | Deferred |
| 5.7 | Media format compatibility | ❌ Not tested | **Yes** | — | **Test mp4/h264** |

---

## 6. Manifest Delivery

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 6.1 | UniversalManifestV1 format stable | ✅ Ready | Yes | Schema tests | Maintain |
| 6.2 | KSO adapter dry-run functional | ✅ Ready | Yes | E tests | Monitor |
| 6.3 | No-secrets in manifest responses | ✅ Ready | Yes | Validator | Maintain |
| 6.4 | Manifest size limits | ⬜ Missing | No | — | Define max size |
| 6.5 | Manifest caching strategy | ⬜ Missing | No | — | Design |
| 6.6 | Signed manifests | ❌ NO-GO | — | Deferred | Design gate |
| 6.7 | Production publish switch | ❌ NO-GO | — | Deferred | Design gate |

---

## 7. Media Delivery

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 7.1 | Creative upload functional | ✅ Ready | No | Creative tests | Monitor |
| 7.2 | AV scan (NoScanner in dev, real in prod) | 🟡 Partial | No | Scanner config | Prod AV enabled |
| 7.3 | Media format validation (ffprobe) | ✅ Ready | No | Upload validation | Monitor |
| 7.4 | Media caching (MinIO) | ⬜ Missing | No | — | CDN/cache config |
| 7.5 | Media delivery to KSO device | ❌ Not tested | **Yes** | — | **Test** |

---

## 8. Planning

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 8.1 | Read-only Planning API (5 endpoints) | ✅ Ready | Yes | D tests | Monitor |
| 8.2 | Portal planning block | ✅ Ready | No | Portal tests | Monitor |
| 8.3 | CampaignBooking writes | ❌ Deferred | No | — | Separate design |

---

## 9. Analytics / PoP

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 9.1 | PoP normalization (KSO + Gateway) | ✅ Ready | Yes | F tests | Monitor |
| 9.2 | Delivery aggregation (14 метрик) | ✅ Ready | Yes | F tests | Monitor |
| 9.3 | Analytics API (4 endpoints) | ✅ Ready | Yes | F tests | Monitor |
| 9.4 | Portal analytics page | ✅ Ready | Yes | F.5 tests | Monitor |
| 9.5 | Placement/store JOIN (currently «unknown») | ⬜ Deferred | No | — | F.4+ |
| 9.6 | ClickHouse pipeline | ❌ NO-GO | — | Deferred | Performance gate |

---

## 10. Emergency

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 10.1 | Emergency API (4 dry-run endpoints) | ✅ Ready | Yes | G tests | Monitor |
| 10.2 | Emergency portal page | ✅ Ready | Yes | G.4 tests | Monitor |
| 10.3 | No-secrets/source boundaries | ✅ Ready | Yes | G.5 tests | Maintain |
| 10.4 | Real emergency execution | ❌ NO-GO | — | Deferred | Design gate |

---

## 11. Monitoring / Observability

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 11.1 | `/api/health/live` | ✅ **H.2** | Yes | Liveness endpoint | Maintain |
| 11.2 | `/api/health/ready` (DB check) | ✅ **H.2** | Yes | Readiness endpoint | Maintain |
| 11.3 | `/api/health/dependencies` (admin) | ✅ **H.2** | Yes | Admin-only check | Maintain |
| 11.4 | `/api/health/metrics` (Prometheus text) | ✅ **H.2** | Yes | Metrics endpoint | Maintain |
| 11.5 | Prometheus server deployed | ❌ Missing | **Yes** | — | **H.6** |
| 11.6 | Grafana dashboard | ❌ Missing | No | — | **H.6** |
| 11.7 | Alert rules configured | ❌ Missing | **Yes** | — | **H.6** |
| 11.8 | Correlation ID / request ID | ✅ **H.2** | No | `X-Correlation-ID` | Maintain |
| 11.9 | Structured JSON logging | ✅ **H.2** | No | `RequestLoggingMiddleware` | Maintain |
| 11.10 | No secrets in logs | ✅ Ready | Yes | FORBIDDEN_HEADERS | Maintain |

---

## 12. Backup / Restore

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 12.1 | PostgreSQL backup script | ✅ **H.3** | Yes | `backup_postgres.sh` | Execute drill |
| 12.2 | PostgreSQL restore script (guarded) | ✅ **H.3** | Yes | `restore_postgres.sh` (CONFIRM_RESTORE) | Execute drill |
| 12.3 | MinIO backup script | ✅ **H.3** | No | `backup_minio.sh` | Execute drill |
| 12.4 | Backup drill completed | ❌ Not done | **Yes** | — | **H.6** |
| 12.5 | Restore drill completed | ❌ Not done | **Yes** | — | **H.6** |
| 12.6 | Redis persistence enabled | ⬜ Missing | No | — | Config |
| 12.7 | Config/seed backup | ⬜ Missing | No | — | Git-based |
| 12.8 | RPO/RTO defined | ⬜ Missing | No | — | Define with business |

---

## 13. Deployment

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 13.1 | Deploy preflight script | ✅ **H.3** | Yes | `deploy_preflight.sh` | Maintain |
| 13.2 | Post-deploy smoke script | ✅ **H.3** | Yes | `post_deploy_smoke.sh` | Maintain |
| 13.3 | Docker compose for prod | 🟡 Partial | Yes | `infra/docker-compose.yml` | Review + harden |
| 13.4 | Blue-green/canary strategy | ❌ Missing | No | — | Design |
| 13.5 | Migration apply procedure | 🟡 Partial | Yes | Alembic | Document |

---

## 14. Rollback

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 14.1 | Rollback preflight script | ✅ **H.3** | Yes | `rollback_preflight.sh` | Maintain |
| 14.2 | Rollback runbook | ✅ H.1 | Yes | `rollback-runbook.md` | Review |
| 14.3 | Migration rollback tested | ❌ Missing | Yes | — | **H.6** |
| 14.4 | Manifest rollback procedure | ❌ Missing | No | — | Document |
| 14.5 | Campaign/publication rollback | ❌ NO-GO | — | Production switch deferred | Deferred |

---

## 15. Load / Performance

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 15.1 | Load tests (40k devices profile) | ❌ Not executed | **Yes** | — | Pilot scale (1-5 devices) is fine; prod scale needs testing |
| 15.2 | Performance baseline established | ❌ Missing | No | — | Establish |
| 15.3 | DB query performance review | ❌ Missing | No | — | DB analysis |
| 15.4 | Index review | ❌ Missing | No | — | DB analysis |

---

## 16. Security Hardening

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 16.1 | Security headers (9) | ✅ **H.4** | No | `SecurityHeadersMiddleware` | Maintain |
| 16.2 | CORS — no wildcard+credentials | ✅ **H.4** | No | `SafeCORSMiddleware` | Maintain |
| 16.3 | Rate limiting (in-memory) | ✅ **H.4** | No | 4-tier limits | Production: Redis-backed |
| 16.4 | Access review (all roles verified) | ✅ **H.4** | Yes | H.4 tests | Periodic audit |
| 16.5 | No-secrets (logs/API/metrics/scripts) | ✅ **H.4** | Yes | Verified | Maintain |
| 16.6 | HTTPS/TLS on all endpoints | ⬜ Missing | Yes | — | Cert config |
| 16.7 | Input validation (all APIs) | ✅ Ready | Yes | Per-domain | Maintain |
| 16.8 | HSTS | ❌ Pending | No | Requires HTTPS first | Post-HTTPS |
| 16.9 | CSP | ❌ Pending | No | Portal SSR — separate gate | Post-HTTPS |
| 16.10 | Dependency vulnerability scan | ❌ Missing | No | — | CI pipeline |

---

## 17. Operations Runbooks

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 17.1 | Device onboarding runbook | ✅ H.1 | No | `device-onboarding-runbook.md` | Review with ops |
| 17.2 | Incident response runbook | ✅ H.1 | No | `incident-response-runbook.md` | Review with ops |
| 17.3 | Rollback runbook | ✅ H.1 | No | `rollback-runbook.md` | Review with ops |
| 17.4 | Backup/restore runbook | ✅ H.1 | No | `backup-restore-runbook.md` | Review with ops |
| 17.5 | KSO pilot runbook | ✅ H.1 | No | `kso-pilot-runbook.md` | Review with ops |
| 17.6 | Monitoring requirements doc | ✅ H.1 | No | `monitoring-alerting-requirements.md` | Review with ops |

---

## 18. Legal / Business Approvals

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 18.1 | 152-ФЗ compliance (5/8 checks fail) | ❌ Incomplete | **Yes** | — | Legal review |
| 18.2 | Data retention policy | 🟡 Partial | No | `/compliance/retention` | Review |
| 18.3 | Business approval for pilot | ❌ Missing | **Yes** | — | Stakeholder sign-off |
| 18.4 | Security approval | ❌ Missing | **Yes** | — | Security review |
| 18.5 | Privacy review (personal data) | ❌ Missing | No | — | Review |

---

## Summary (H.5 update)

| Category | Ready | Partial | Missing | NO-GO/Deferred | Δ from H.1 |
|---|---|---|---|---|---|
| Environment/Config | 1 | 0 | 6 | 0 | CORS → ✅ |
| Secrets Management | 3 | 1 | 3 | 0 | +2 verifications (H.4) |
| Access/RBAC/RLS | 5 | 0 | 1 | 0 | +2 verifications (H.4) |
| Device Gateway | 7 | 0 | 1 | 0 | Rate limiting → ✅ |
| KSO Devices | 1 | 1 | 4 | 1 | No change |
| Manifest Delivery | 3 | 0 | 2 | 2 | No change |
| Media Delivery | 2 | 1 | 1 | 0 | No change |
| Planning | 2 | 0 | 0 | 1 | No change |
| Analytics/PoP | 4 | 0 | 0 | 1 | No change |
| Emergency | 3 | 0 | 0 | 1 | No change |
| Monitoring/Observability | 6 | 0 | 3 | 0 | +4 endpoints (H.2) |
| Backup/Restore | 3 | 0 | 3 | 0 | +3 scripts (H.3) |
| Deployment | 2 | 2 | 1 | 0 | +2 scripts (H.3) |
| Rollback | 2 | 0 | 2 | 1 | +1 script (H.3) |
| Load/Performance | 0 | 0 | 4 | 0 | No change |
| Security Hardening | 5 | 0 | 3 | 0 | +5 items (H.4) |
| Operations Runbooks | 6 | 0 | 0 | 0 | No change |
| Legal/Business | 0 | 1 | 4 | 0 | No change |

**Overall: H.2–H.4 closed 11 gaps. 8 blocking items remain. Pilot NOT READY. GO for H.6 preparation.**
