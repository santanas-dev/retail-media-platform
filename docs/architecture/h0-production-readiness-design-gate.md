# H.0 — Production Readiness Design Gate / Pre-Audit

**Date:** 2026-07-02  
**Phase:** H (Production Readiness) — Design Gate  
**Status:** ✅ COMPLETED  
**Prerequisite:** Phase G Emergency & Operations (closed)

---

## Executive Summary

Phase H.0 — design-only gate. Проведён pre-audit текущего состояния платформы  
после закрытия фаз B–G. Определены production readiness gaps, pilot readiness  
criteria, risk register, и рекомендованный split Phase H.

Реализация НЕ начинается. Миграции/API/portal/Gateway/KSO/Emergency НЕ меняются.  
ClickHouse НЕ включается. Production switch НЕ активируется.

---

## 1. Roadmap Phase H Reading

Из `tz-v2-5-realignment-roadmap-46-1.md`:

| Подэтап | Roadmap Scope |
|---|---|
| H.1 | HA & Backups: PostgreSQL standby, backup/restore drill, ClickHouse репликация, MinIO отказоустойчивость |
| H.2 | Load Testing: 40 000 устройств (heartbeat 30s, manifest pull 30s, PoP batch 60s), массовая публикация, аналитика |
| H.3 | Мониторинг: Prometheus/Grafana метрики, алерты, correlation ID |

**Blockers:** работающая платформа (фазы B–G) — ✅ выполнено  
**KSO hardware:** желательно для реалистичных тестов

---

## 2. Current Capability Matrix

### A. Core Model (Phase B)
| Capability | Status |
|---|---|
| Channels (channel registry) | ✅ |
| Device Types | ✅ |
| Physical Devices | ✅ |
| Logical Carriers | ✅ |
| Display Surfaces | ✅ |
| Placements | ✅ |
| Placement Targets | ✅ |
| Capability Profiles | ✅ |
| AdapterContract + MockAdapter | ✅ |

### B. Manifest / Orchestrator (Phase B+E)
| Capability | Status |
|---|---|
| UniversalManifestV1 | ✅ |
| build_universal_manifest_for_device() | ✅ |
| build_universal_manifest_preview() | ✅ |
| KSO Adapter dry-run | ✅ |
| adapter_payload generation | ✅ |
| Universal preview endpoint | ✅ |
| **KSO production switch** | ❌ Deferred |
| **Compatibility projection** | ❌ Deferred |
| **Signed manifests** | ❌ Deferred |

### C. Device Gateway (Phase C)
| Capability | Status |
|---|---|
| Auth / token issuance | ✅ |
| Heartbeat (device health) | ✅ |
| Config endpoint | ✅ |
| Manifest universal preview | ✅ |
| PoP ingestion (legacy + enterprise) | ✅ |
| Media delivery endpoint | ✅ |
| Device lifecycle (register, status) | ✅ |
| Legacy KSO endpoint (unchanged) | ✅ |
| **Gateway credential rotation** | ❌ No mechanism |
| **mTLS** | ❌ Decision deferred |

### D. Planning (Phase D)
| Capability | Status |
|---|---|
| InventoryUnit + CapacityRule | ✅ |
| Availability / Conflicts / Occupancy | ✅ |
| Planning API (5 read-only endpoints) | ✅ |
| Portal planning block | ✅ |
| **CampaignBooking writes** | ❌ Deferred |
| **Auto-planning** | ❌ Deferred |

### E. Analytics (Phase F)
| Capability | Status |
|---|---|
| PoP normalization (KSO + Gateway) | ✅ |
| Delivery aggregation (14 метрик) | ✅ |
| Delivery breakdowns (6 измерений) | ✅ |
| Analytics API (4 read-only endpoints) | ✅ |
| Portal analytics page | ✅ |
| RLS/Scope enforcement | ✅ |
| Audit events | ✅ |
| Dry-run exclusion | ✅ |
| **Placement/store real data in breakdowns** | ❌ «unknown» bucket |
| **expected_impressions** | ❌ None/no_plan |
| **ClickHouse pipeline** | ❌ Deferred |
| **Export reports** | ❌ Deferred |

### F. Emergency (Phase G)
| Capability | Status |
|---|---|
| Emergency API (4 dry-run endpoints) | ✅ |
| Emergency portal | ✅ |
| Security/RLS/Audit/No-secrets | ✅ |
| **Real execution** | ❌ Deferred |
| **Approval workflow** | ❌ Deferred |
| **Gateway/KSO emergency delivery** | ❌ Deferred |
| **emergency_actions persistence** | ❌ Deferred |

### G. Legacy KSO
| Component | Status |
|---|---|
| `/kso/{device_code}/manifest` | ✅ Unchanged |
| GeneratedManifest | ✅ Not written by universal |
| Publication flow | ✅ Unchanged |

---

## 3. Production Readiness Gaps

### 3.1 Environment / Config Readiness
- [ ] Production `.env` / config шаблон
- [ ] Secrets management (не hardcoded)
- [ ] PostgreSQL production config (pool size, timeouts)
- [ ] MinIO production config (retention, quotas)
- [ ] Backend port/host production config
- [ ] Portal session secret production config

### 3.2 Monitoring / Observability
- [ ] **Prometheus/Grafana метрики:** отсутствуют
- [ ] **Алерты:** mass offline, PoP errors spike, Gateway unavailable — нет
- [ ] **Correlation ID / trace ID:** отсутствует
- [ ] `/health` endpoint: есть — базовый
- [ ] **Structured logging:** частично (seed/audit)
- [ ] **Error budgets / SLO:** не определены

### 3.3 Backup / Restore
- [ ] PostgreSQL backup strategy — нет
- [ ] PostgreSQL restore drill — нет
- [ ] MinIO backup — нет
- [ ] ClickHouse (deferred)

### 3.4 Deployment / Rollback
- [ ] Automated deployment script — нет
- [ ] Rollback plan — нет
- [ ] Migration rollback procedure — нет
- [ ] Docker compose (infra/docker-compose.yml) — есть, требует production review

### 3.5 Security Hardening
- [ ] RLS review (все фазы) — поэтапно проверено
- [ ] Admin access review — `/admin` page, RBAC mapping
- [ ] Gateway device credential rotation — нет механизма
- [ ] Certificate / mTLS — decision deferred
- [ ] Rate limiting — отсутствует
- [ ] No-secrets validation — ✅ во всех критических доменах
- [ ] Seed idempotency — ✅

### 3.6 KSO Pilot Readiness
- [ ] KSO physical device compatibility — не тестировано
- [ ] KSO player runtime (Chromium/UKM5) — заблокирован hardware
- [ ] Media delivery/caching для KSO — не готово
- [ ] Real publish switch — отдельный design gate

### 3.7 Operations Runbooks
- [ ] Device onboarding runbook — нет
- [ ] Incident response runbook — нет
- [ ] Support escalation process — нет
- [ ] Operator training — нет

### 3.8 Load / Performance
- [ ] Load testing (40k devices) — не проведено
- [ ] Performance baseline — отсутствует
- [ ] DB indexes review — не проведён

### 3.9 Testing
- [ ] Backend full regression: 2270 passed / 47 pre-existing failures ✅
- [ ] Portal regression: 991 passed / 32 skipped / 8 pre-existing ✅
- [ ] Seed idempotency tests: ✅
- [ ] No-secrets tests: ✅
- [ ] Security/source-boundary tests: ✅
- [ ] **Integration tests with real KSO hardware:** заблокированы
- [ ] **E2E tests:** отсутствуют
- [ ] **Performance/load tests:** отсутствуют

---

## 4. Pilot Readiness Criteria

Pilot может быть разрешён только при выполнении ВСЕХ условий:

1. ✅ No production switch without approval gate
2. ⬜ Selected pilot store/device list defined
3. ⬜ Rollback plan exists
4. ⬜ Monitoring exists (basic health checks visible)
5. ✅ Device heartbeat visible (Gateway)
6. ✅ PoP visible (Analytics)
7. ✅ Emergency dry-run available
8. ✅ No-secrets checks pass
9. ✅ Audit works
10. ⬜ Operator runbook exists
11. ⬜ Support escalation process exists
12. ⬜ KSO physical device tested (at least 1 device)
13. ⬜ Deployment script tested
14. ⬜ Backup tested

**Current pilot readiness:** 5/14 ✅ — НЕ ГОТОВ.

---

## 5. Risk Register

| # | Risk | Severity | Status | Mitigation | Blocks Pilot? |
|---|---|---|---|---|---|
| R1 | KSO production switch premature | Critical | Deferred | Отдельный design gate | ✅ Yes |
| R2 | Physical KSO compatibility untested | High | Blocked (HW) | Throttled pilot: 1 device only | ✅ Yes |
| R3 | No signed manifests | Medium | Deferred | Manifest signature gate | No |
| R4 | Gateway credential lifecycle incomplete | High | Gap | Rotation mechanism + expiry | ✅ Yes |
| R5 | Emergency real execution absent | High | Deferred | Dry-run only acceptable for pilot | No |
| R6 | Placement/store analytics «unknown» bucket | Low | Known limitation | JOIN normalizers later | No |
| R7 | expected_impressions = None | Low | Known limitation | Planning integration later | No |
| R8 | ClickHouse not enabled | Medium | Deferred | PostgreSQL-only pilot acceptable | No |
| R9 | 8 portal pre-existing live integration errors | Low | Stable | Не растут | No |
| R10 | operations broad preview без scope | Medium | Documented | Scope enforcement before real execution | No |
| R11 | 47 pre-existing backend failures | Medium | Stable | 2270 pass, failures изолированы (KSO readiness) | No |
| R12 | No rate limiting | Medium | Gap | Gateway rate limits needed | ✅ Yes |
| R13 | No backup/restore | Critical | Gap | pg_dump + restore drill | ✅ Yes |
| R14 | No monitoring (Prometheus/Grafana) | High | Gap | /health + structured logs minimum | ✅ Yes |

---

## 6. Production Readiness Checklist

### Security
- [ ] RLS review — done ✅
- [ ] Admin access review
- [ ] Rate limiting
- [ ] Gateway credential rotation
- [ ] Production secrets scan

### Access / RBAC / RLS
- [ ] Permission map review
- [ ] Role assignment audit
- [ ] Scope enforcement review

### Device Gateway
- [ ] Auth token rotation
- [ ] Heartbeat thresholds
- [ ] Rate limiting
- [ ] Credential lifecycle

### KSO Devices
- [ ] Physical device tested
- [ ] Media delivery tested
- [ ] Player compatibility

### Manifest Delivery
- [ ] Manifest size limits
- [ ] Caching strategy
- [ ] Signed manifests (deferred)

### Planning
- [ ] Booking writes (deferred)
- [ ] Auto-planning (deferred)

### Analytics
- [ ] Placement/store JOIN (deferred)
- [ ] Expected impressions (deferred)
- [ ] ClickHouse (deferred)

### Emergency
- [ ] Real execution (deferred)
- [ ] Approval workflow (deferred)

### Observability
- [ ] Prometheus/Grafana
- [ ] Alert rules
- [ ] Correlation ID
- [ ] Structured logging

### Backup/Restore
- [ ] PostgreSQL backup
- [ ] Restore drill
- [ ] MinIO backup

### Deployment
- [ ] Deployment script
- [ ] Rollback plan
- [ ] Migration rollback

### Operations Runbooks
- [ ] Device onboarding
- [ ] Incident response
- [ ] Support escalation

### Testing
- [ ] Backend full regression: ✅
- [ ] Portal regression: ✅
- [ ] Security tests: ✅
- [ ] Load/performance tests: ❌
- [ ] E2E tests: ❌
- [ ] KSO hardware tests: ❌

### Performance
- [ ] Load baseline (40k devices)
- [ ] DB query performance
- [ ] Index review

### Legal/Business
- [ ] 152-ФЗ compliance (5/8 checks fail)
- [ ] Data retention policy
- [ ] Business approval for pilot

---

## 7. Recommended Phase H Split

| Step | Name | Scope | Needs Migrations? | Needs API? |
|---|---|---|---|---|
| **H.0** | Design Gate | ✅ This document | No | No |
| **H.1** | Readiness Checklist / Runbooks | Documents, checklists, runbooks only | No | No |
| **H.2** | Observability & Health Checks | Prometheus/Grafana, structured logging, alert rules, correlation ID | No | Minimal (metrics endpoint) |
| **H.3** | Deployment / Rollback / Backup | Backup scripts, deployment scripts, rollback procedures, restore drill | No | No |
| **H.4** | Security Hardening | Rate limiting, credential rotation, access review, secrets audit | No | Minimal (rate limiter) |
| **H.5** | Pilot Readiness Gate | Pilot checklist verification, KSO device test (1 device), operator training | No | No |
| **H.6** | Closure Gate | Final audit, GO/NO-GO for pilot | No | No |

### Decisions for H.1:

| Decision | Answer | Reason |
|---|---|---|
| Нужны ли миграции в H.1? | **NO** | Documents/runbooks only |
| Нужен ли API в H.1? | **NO** | No backend changes |
| Нужен ли portal в H.1? | **NO** | No portal changes |
| Нужен ли ClickHouse в H.1? | **NO** | Deferred until performance gate |
| Разрешён ли production switch? | **NO** | Отдельный design gate |

---

## 8. Explicit NO-GO Items

❌ KSO production switch без design gate  
❌ ClickHouse без performance gate  
❌ Real emergency execution без design gate  
❌ UniversalManifest → GeneratedManifest write без compatibility gate  
❌ mTLS/certificates без design gate  
❌ Signed manifests без design gate  
❌ Staged rollout без Pilot Readiness Gate (H.5)  

---

## 9. Test Baseline Strategy (before pilot)

Обязательные тесты перед pilot:

| Suite | Status | Count |
|---|---|---|
| Backend full regression | ✅ | 2270 passed / 47 pre-existing |
| Portal full regression | ✅ | 991 passed / 32 skipped / 8 pre-existing |
| Gateway suite | ✅ | (included in backend) |
| KSO adapter E suite | ✅ | 217/217 |
| Planning suite | ✅ | 254/254 |
| Analytics suite | ✅ | 268/268 |
| Emergency suite | ✅ | 232/232 |
| Security/source-boundary | ✅ | G.5: 60/60 |
| No-secrets tests | ✅ | Per-domain |
| Seed idempotency | ✅ | Tests exist |
| Migration check | ✅ | 0 new since G.3 |
| **Load/performance** | ❌ | **Not performed** |
| **KSO hardware E2E** | ❌ | **Not performed** |
| **Backup/restore drill** | ❌ | **Not performed** |

---

## 10. Documents Reviewed

| Document | Phase |
|---|---|
| `tz-v2-5-realignment-roadmap-46-1.md` | Roadmap |
| `current-project-state-after-e.md` | After E |
| `current-project-state-after-f.md` | After F |
| `current-project-state-after-g.md` | After G |
| `g-emergency-operations-closure.md` | G Closure |

---

## 11. Final Decision

### ✅ GO для H.1 — Production Readiness Checklist / Runbooks

H.1 — documents/runbooks/checklists only:
- No migrations
- No API changes
- No portal changes
- No Gateway/KSO/Emergency/Publication changes
- No ClickHouse
- No production switch

### ❌ NO-GO для:
- Implementation (H.2+) до закрытия H.1
- Real emergency execution
- KSO production switch
- ClickHouse pipeline
- Signed manifests
- mTLS/certificates

### Recommended next: H.1 — Production Readiness Checklist / Runbooks

---

## 12. H.1 Result (Post-Completion) — ✅ COMPLETED

**Commit:** `TBD` | **Date:** 2026-07-02

10 operational documents created:

| # | Document | Type |
|---|---|---|
| 1 | `docs/operations/production-readiness-checklist.md` | 18 категорий, 100+ items |
| 2 | `docs/operations/pilot-readiness-checklist.md` | 14 критериев |
| 3 | `docs/operations/device-onboarding-runbook.md` | 9 шагов |
| 4 | `docs/operations/incident-response-runbook.md` | 10 сценариев |
| 5 | `docs/operations/rollback-runbook.md` | 6 типов |
| 6 | `docs/operations/backup-restore-runbook.md` | pg/MinIO/Redis |
| 7 | `docs/operations/monitoring-alerting-requirements.md` | Prometheus/Grafana |
| 8 | `docs/operations/kso-pilot-runbook.md` | 8 acceptance criteria |
| 9 | `docs/operations/access-review-checklist.md` | 6 разделов |
| 10 | `docs/operations/secrets-management-checklist.md` | 9 разделов |

Pilot readiness: **still NOT READY** (5/14) — documentation created, implementation pending H.2–H.5.

**Next — H.2: Observability & Health Checks.**
