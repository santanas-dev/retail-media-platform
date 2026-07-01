# Production Readiness Checklist

**Date:** 2026-07-02 | **Phase:** H.1 | **Owner:** Ops Team (TBD)

> Status: ⬜ NOT READY — documentation exists, implementation pending.

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
| 1.7 | CORS config for production domains | ⬜ Missing | Yes | — | Restrict to known origins |

---

## 2. Secrets Management

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 2.1 | No secrets in git repo (scan pass) | ✅ Ready | Yes | No-secrets validators | Periodic scan |
| 2.2 | `.env` not committed | ✅ Ready | Yes | `.gitignore` | Verify |
| 2.3 | DB password in vault/secret manager | ⬜ Missing | Yes | — | Move from `.env` to vault |
| 2.4 | Gateway device tokens stored securely | ⬜ Partial | Yes | DB hashed | Add rotation |
| 2.5 | Admin password rotation process | ⬜ Missing | No | — | Document rotation |
| 2.6 | Emergency access procedure | ⬜ Missing | No | — | Break-glass account |
| 2.7 | No secrets in logs/audit/portal HTML | ✅ Ready | Yes | Per-domain validators | Maintain |

---

## 3. Access / RBAC / RLS

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 3.1 | Role-permission map documented | ✅ Ready | No | `seed.py` | Review annually |
| 3.2 | Least privilege review (all roles) | ⬜ Missing | Yes | — | Audit each role |
| 3.3 | `device_service` restrictions verified | ✅ Ready | Yes | G.5 tests | Maintain |
| 3.4 | `advertiser` restrictions verified | ✅ Ready | Yes | G.5 tests | Maintain |
| 3.5 | Admin access audit log enabled | ✅ Ready | Yes | Audit events | Review |
| 3.6 | Service account review | ⬜ Missing | No | — | List all service accounts |
| 3.7 | RLS scope enforcement (advertiser, store, channel) | ✅ Ready | Yes | F.4.1 tests | Add scope docs |

---

## 4. Device Gateway

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 4.1 | Auth/token endpoint functional | ✅ Ready | Yes | Gateway tests | Monitor |
| 4.2 | Heartbeat endpoint functional | ✅ Ready | Yes | Gateway tests | Set thresholds |
| 4.3 | Manifest universal preview functional | ✅ Ready | Yes | E tests | Monitor |
| 4.4 | PoP ingestion (legacy + enterprise) | ✅ Ready | Yes | F tests | Monitor |
| 4.5 | Media delivery endpoint functional | ✅ Ready | No | Gateway tests | Cache config |
| 4.6 | Rate limiting on all gateway endpoints | ❌ Missing | **Yes** | — | **Implement before pilot** |
| 4.7 | Credential rotation mechanism | ❌ Missing | **Yes** | — | **Implement before pilot** |
| 4.8 | Device lifecycle (register/block/unregister) | ✅ Ready | No | Gateway API | Monitor |
| 4.9 | Gateway health endpoint | ✅ Ready | No | `/health` | Monitor |

---

## 5. KSO Devices

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 5.1 | Physical KSO device available (192.168.110.223) | ⬜ Partial | **Yes** | UKM5 present | **Test** |
| 5.2 | Ad zone dimensions verified | ❌ Not tested | **Yes** | — | **Measure** |
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
| 7.2 | AV scan (NoScanner in dev, real in prod) | ⬜ Partial | No | Scanner config | Prod AV enabled |
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
| 11.1 | Prometheus metrics endpoint | ❌ Missing | **Yes** | — | **H.2** |
| 11.2 | Grafana dashboard | ❌ Missing | No | — | **H.2** |
| 11.3 | Alert rules (Gateway down, PoP drop, etc.) | ❌ Missing | **Yes** | — | **H.2** |
| 11.4 | Correlation ID / request ID | ❌ Missing | No | — | **H.2** |
| 11.5 | Structured logging (JSON) | ⬜ Partial | No | Audit only | **H.2** |
| 11.6 | `/health` endpoint | ✅ Ready | Yes | Backend + portal | Maintain |
| 11.7 | No secrets in logs | ✅ Ready | Yes | Validators | Maintain |

---

## 12. Backup / Restore

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 12.1 | PostgreSQL backup configured | ❌ Missing | **Yes** | — | **H.3** |
| 12.2 | PostgreSQL restore drill completed | ❌ Missing | **Yes** | — | **H.3** |
| 12.3 | MinIO backup configured | ❌ Missing | No | — | **H.3** |
| 12.4 | Redis persistence enabled | ⬜ Missing | No | — | Config |
| 12.5 | Config/seed backup | ⬜ Missing | No | — | Git-based |
| 12.6 | RPO/RTO defined | ⬜ Missing | No | — | Define with business |

---

## 13. Deployment

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 13.1 | Automated deployment script | ❌ Missing | **Yes** | — | **H.3** |
| 13.2 | Docker compose for prod | ⬜ Partial | Yes | `infra/docker-compose.yml` | Review + harden |
| 13.3 | Blue-green/canary strategy | ❌ Missing | No | — | Design |
| 13.4 | Migration apply procedure | ⬜ Partial | Yes | Alembic | Document |

---

## 14. Rollback

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 14.1 | Rollback plan documented | ⬜ Missing | **Yes** | — | **H.3** |
| 14.2 | Migration rollback tested | ❌ Missing | Yes | — | **H.3** |
| 14.3 | Manifest rollback procedure | ❌ Missing | No | — | Document |
| 14.4 | Campaign/publication rollback | ❌ NO-GO | — | Production switch deferred | Deferred |

---

## 15. Load / Performance

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 15.1 | Load tests (40k devices profile) | ❌ Not executed | **Yes** | — | **H.2** |
| 15.2 | Performance baseline established | ❌ Missing | No | — | **H.2** |
| 15.3 | DB query performance review | ❌ Missing | No | — | **H.2** |
| 15.4 | Index review | ❌ Missing | No | — | DB analysis |

---

## 16. Security Hardening

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 16.1 | HTTPS/TLS on all endpoints | ⬜ Missing | Yes | — | Cert config |
| 16.2 | Rate limiting | ❌ Missing | **Yes** | — | **H.4** |
| 16.3 | Input validation (all APIs) | ✅ Ready | Yes | Per-domain | Maintain |
| 16.4 | CORS restricted | ⬜ Missing | Yes | — | Config |
| 16.5 | Security headers (HSTS, CSP, etc.) | ⬜ Missing | No | — | Config |
| 16.6 | Dependency vulnerability scan | ❌ Missing | No | — | CI pipeline |

---

## 17. Operations Runbooks

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 17.1 | Device onboarding runbook | ⬜ Created | **Yes** | H.1 | Review |
| 17.2 | Incident response runbook | ⬜ Created | **Yes** | H.1 | Review |
| 17.3 | Rollback runbook | ⬜ Created | **Yes** | H.1 | Review |
| 17.4 | Backup/restore runbook | ⬜ Created | **Yes** | H.1 | Review |
| 17.5 | KSO pilot runbook | ⬜ Created | **Yes** | H.1 | Review |
| 17.6 | Monitoring requirements doc | ⬜ Created | **Yes** | H.1 | Review |

---

## 18. Legal / Business Approvals

| # | Item | Status | Blocks? | Evidence | Next |
|---|---|---|---|---|---|
| 18.1 | 152-ФЗ compliance (5/8 checks fail) | ❌ Incomplete | **Yes** | — | Legal review |
| 18.2 | Data retention policy | ⬜ Partial | No | `/compliance/retention` | Review |
| 18.3 | Business approval for pilot | ❌ Missing | **Yes** | — | Stakeholder sign-off |
| 18.4 | Security approval | ❌ Missing | **Yes** | — | Security review |
| 18.5 | Privacy review (personal data) | ❌ Missing | No | — | Review |

---

## Summary

| Category | Ready | Partial | Missing | NO-GO/Deferred |
|---|---|---|---|---|
| Environment/Config | 1 | 0 | 6 | 0 |
| Secrets Management | 2 | 1 | 3 | 0 |
| Access/RBAC/RLS | 4 | 0 | 2 | 0 |
| Device Gateway | 6 | 0 | 2 | 0 |
| KSO Devices | 1 | 1 | 4 | 1 |
| Manifest Delivery | 3 | 0 | 2 | 2 |
| Media Delivery | 2 | 1 | 1 | 0 |
| Planning | 2 | 0 | 0 | 1 |
| Analytics/PoP | 4 | 0 | 0 | 1 |
| Emergency | 3 | 0 | 0 | 1 |
| Monitoring/Observability | 2 | 1 | 5 | 0 |
| Backup/Restore | 0 | 0 | 4 | 0 |
| Deployment | 0 | 2 | 1 | 0 |
| Rollback | 0 | 1 | 1 | 1 |
| Load/Performance | 0 | 0 | 4 | 0 |
| Security Hardening | 1 | 0 | 5 | 0 |
| Operations Runbooks | 6 | 0 | 0 | 0 |
| Legal/Business | 0 | 1 | 4 | 0 |

**Overall: documentation created. Implementation pending in H.2–H.5.**
