# H.5 — Pilot Readiness Gate

**Date:** 2026-07-01 | **Phase:** H.5 | **Decision:** 🟡 CONDITIONAL NO-GO

---

## Executive Summary

После завершения H.2 (Observability), H.3 (Deployment/Rollback/Backup), H.4 (Security Hardening) система прошла значительный путь к production readiness. Однако пилот в реальных магазинах **невозможен** — остаются 6 блокирующих gap'ов и отсутствуют бизнес-approval'ы.

**Решение:** CONDITIONAL GO FOR LAB / PRE-PILOT PREPARATION — разрешена работа по закрытию оставшихся gap'ов, включая внутреннее тестирование, развёртывание Prometheus/Grafana, нагрузочное тестирование, KSO physical test.  
**NO-GO:** production switch, реальный пилот в магазинах, real emergency execution.

---

## Current State After H.4

| Компонент | Статус | Фаза |
|---|---|---|
| Health endpoints (live/ready/dependencies/metrics) | ✅ Ready | H.2 |
| Correlation ID middleware | ✅ Ready | H.2 |
| Structured JSON logging | ✅ Ready | H.2 |
| Security headers (9 headers) | ✅ Ready | H.4 |
| CORS — fixed (no wildcard+credentials) | ✅ Ready | H.4 |
| Rate limiter — in-memory, per-endpoint | ✅ Ready | H.4 |
| Backup scripts (PostgreSQL, MinIO) | ✅ Tooling ready | H.3 |
| Restore scripts (CONFIRM_RESTORE required) | ✅ Tooling ready | H.3 |
| Deploy/rollback preflight | ✅ Tooling ready | H.3 |
| Post-deploy smoke tests | ✅ Tooling ready | H.3 |
| Emergency API + portal (dry-run) | ✅ Ready | G |
| Analytics/PoP (read-only) | ✅ Ready | F |
| Planning API (read-only) | ✅ Ready | D |
| Access review (permissions verified) | ✅ Ready | H.4 |
| Secrets management (no-secrets verified) | ✅ Ready | H.4 |
| Operations runbooks (6 docs) | ✅ Created | H.1 |
| Test baseline | ✅ 2458 collected / 0 errors | H.4 |
| Prometheus/Grafana deployed | ❌ Missing | — |
| Alert runtime configured | ❌ Missing | — |
| Backup/restore drill completed | ❌ Missing | — |
| KSO physical device tested | ❌ Not tested | — |
| Pilot store/device list defined | ❌ Missing | — |
| Credential rotation mechanism | ❌ Missing | — |
| Production HTTPS/HSTS | ❌ Pending | — |
| Load test (40k profile) | ❌ Not executed | — |
| Business approval | ❌ Missing | — |
| Security approval | ❌ Missing | — |

---

## Pilot Readiness Criteria — Matrix (16 criteria)

| # | Criterion | Status | Blocker | Evidence | Next Action |
|---|---|---|---|---|---|
| P1 | No production switch without approval | ✅ READY | No | H.0/H.1/G.6 docs | Maintain |
| P2 | Device heartbeat visible | ✅ READY | No | Gateway API functional | Monitor |
| P3 | PoP visible | ✅ READY | No | Analytics API + portal | Monitor |
| P4 | Emergency dry-run available | ✅ READY | No | Emergency API + portal | Maintain |
| P5 | No-secrets checks pass | ✅ READY | No | Per-domain validators, H.4 verified | Maintain |
| P6 | Pilot store list defined | ❌ MISSING | **Yes** | — | **Define with business** |
| P7 | Pilot device list defined | ❌ MISSING | **Yes** | — | **Define with business** |
| P8 | Rollback plan approved | 🟡 PARTIAL | **Yes** | Scripts exist (H.3), preflight ready; no real drill; plan not reviewed | Review + approve |
| P9 | Monitoring enabled + alerts configured | ❌ MISSING | **Yes** | `/api/health/metrics` exists (H.2); no Prometheus/Grafana; no alerts | **Deploy Prometheus + alerts** |
| P10 | Backup/restore drill completed | ❌ MISSING | **Yes** | Scripts exist (H.3); real drill not done | **Execute drill** |
| P11 | KSO physical device test completed | ❌ MISSING | **Yes** | Hardware present (192.168.110.223); no playback test | **Test physical playback** |
| P12 | Operator runbook exists + reviewed | 🟡 PARTIAL | No | Created (H.1); not yet reviewed by ops | Review with ops team |
| P13 | Support escalation path exists | ❌ MISSING | No | — | Define with management |
| P14 | Security approval received | ❌ MISSING | **Yes** | Security hardening done (H.4); no formal sign-off | **Security review** |
| P15 | Business approval received | ❌ MISSING | **Yes** | No stakeholder sign-off | **Business review** |
| P16 | Rate limiting active on sensitive endpoints | ✅ READY | No | H.4 in-memory rate limiter | Monitor |

### Summary by Status

| Status | Count | Criteria |
|---|---|---|
| ✅ READY | **7/16** | P1, P2, P3, P4, P5, P8a, P16 |
| 🟡 PARTIAL | **2/16** | P8 (rollback), P12 (runbook review) |
| ❌ MISSING | **7/16** | P6, P7, P9, P10, P11, P14, P15 + P13 |

---

## Blocking Items (MUST be resolved before real pilot)

| # | Blocker | Category | Impact |
|---|---|---|---|
| B1 | Pilot store/device list not defined | Operations | Cannot select pilot scope |
| B2 | Monitoring + alerts not deployed | Observability | No runtime visibility |
| B3 | Backup/restore drill not completed | Operations | No recovery confidence |
| B4 | KSO physical device test not done | KSO | No playback verification |
| B5 | Security approval not received | Security | No formal security sign-off |
| B6 | Business approval not received | Business | No stakeholder buy-in |

---

## Non-Blocking Items (can be deferred past pilot start)

| # | Item | Reasoning |
|---|---|---|
| N1 | Credential rotation mechanism | Can be manual initially |
| N2 | Production HTTPS/HSTS | Internal network only |
| N3 | CSP / UI security gate | Portal SSR — separate gate |
| N4 | Load test (40k profile) | Pilot is 1-5 devices, not 40k |
| N5 | Operator runbook review | Can be reviewed during pilot prep |
| N6 | Support escalation path | Internal pilot — direct contact |
| N7 | Redis-backed rate limiter | In-memory sufficient for pilot scale |

---

## KSO Physical Pilot Readiness

| Check | Status | Evidence |
|---|---|---|
| Hardware available (192.168.110.223) | 🟡 PARTIAL | UKM5 present |
| OS/Linux/Chromium kiosk ready | ❌ NOT TESTED | No X11/Chromium launch tested |
| Screen resolution/orientation (768×1024 portrait) | ❌ NOT VERIFIED | Assumed but not measured |
| Network path to Gateway | ❌ NOT TESTED | No connectivity test |
| Device registration process documented | ✅ DOCUMENTED | `device-onboarding-runbook.md` (H.1) |
| Legacy manifest unchanged | ✅ VERIFIED | Route untouched |
| Physical playback test (mp4/h264) | ❌ NOT DONE | Blocked — no Chromium kiosk test |
| PoP from physical KSO | ❌ NOT DONE | Blocked — no playback → no PoP |
| Emergency dry-run against KSO scope | 🟡 PARTIAL | API functional; physical scope untested |
| Rollback to legacy mode documented | ✅ DOCUMENTED | `rollback-runbook.md` (H.1) |

**KSO Decision:** Physical pilot **cannot start** until playback test completed. KSO production switch — separate design gate, **NO-GO**.

---

## Observability Readiness

| Component | Status |
|---|---|
| `/api/health/live` | ✅ Ready |
| `/api/health/ready` (PostgreSQL) | ✅ Ready |
| `/api/health/dependencies` (admin-only) | ✅ Ready |
| `/api/health/metrics` (Prometheus text) | ✅ Ready |
| Correlation ID (X-Correlation-ID) | ✅ Ready |
| Structured JSON logging | ✅ Ready |
| Prometheus server deployed | ❌ Missing |
| Grafana dashboard | ❌ Missing |
| Alert rules (Gateway down, PoP drop, etc.) | ❌ Missing |

**Decision:** Foundation ready (H.2). Runtime monitoring **missing** — Prometheus + Grafana deployment required before pilot.

---

## Backup / Restore / Rollback Readiness

| Component | Status |
|---|---|
| PostgreSQL backup script | ✅ Ready (H.3) |
| PostgreSQL restore script (guarded) | ✅ Ready (H.3) |
| MinIO backup script | ✅ Ready (H.3) |
| Deploy preflight script | ✅ Ready (H.3) |
| Post-deploy smoke script | ✅ Ready (H.3) |
| Rollback preflight script | ✅ Ready (H.3) |
| Real backup drill completed | ❌ NOT DONE |
| Real restore drill completed | ❌ NOT DONE |
| Automated rollback | ❌ NOT DONE |

**Decision:** Tooling ready (H.3). Real drills **missing** — must be executed before pilot. Rollback preflight checks readiness but does not perform actual rollback.

---

## Security Readiness

| Component | Status |
|---|---|
| Security headers (9) | ✅ Ready (H.4) |
| CORS — SafeCORSMiddleware | ✅ Ready (H.4) |
| Rate limiter (in-memory, per-endpoint) | ✅ Ready (H.4) |
| No-secrets (logs/API/metrics/scripts) | ✅ Verified (H.4) |
| Emergency permissions (3 roles only) | ✅ Verified (H.4) |
| Access review (seed idempotent) | ✅ Verified (H.4) |
| ⚠️ operations has publications.publish | 🟡 Documented risk |
| HSTS (HTTPS required first) | ❌ Pending prod HTTPS |
| CSP (portal UI security gate) | ❌ Pending separate gate |
| Credential rotation mechanism | ❌ Missing |
| Security approval | ❌ Missing |

**Decision:** Pilot security foundation solid (H.4). Remaining gaps (HSTS, CSP, credential rotation) are **non-blocking for lab/internal pilot** but must be addressed before production.

---

## Load / Performance Readiness

| Component | Status |
|---|---|
| Load test — 40k device profile | ❌ NOT EXECUTED |
| Mass publication test | ❌ NOT EXECUTED |
| Analytics aggregation load test | ❌ NOT EXECUTED |
| Gateway heartbeat stress test | ❌ NOT EXECUTED |

**Decision:** **Non-blocking for pilot** (1-5 devices only). Required before full production. H.2/H.4 middleware is lightweight and should not impact performance.

---

## Business / Legal Approval Readiness

| Component | Status |
|---|---|
| Business stakeholder sign-off | ❌ Missing |
| Security review sign-off | ❌ Missing |
| 152-ФЗ compliance | ❌ 5/8 checks fail |
| Data retention policy | 🟡 Partial |
| Privacy review | ❌ Missing |

**Decision:** All approvals **missing**. Cannot proceed to any form of pilot without at minimum business + security sign-off. Legal compliance deferred.

---

## Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | KSO physical playback fails | High | Pre-pilot test mandatory |
| R2 | No runtime monitoring → silent failures | High | Prometheus + alerts before pilot |
| R3 | No restore drill → recovery unknown | High | Execute drill before pilot |
| R4 | operations has publications.publish | Medium | Documented risk; review pre-pilot |
| R5 | Credential rotation missing | Medium | Manual rotation acceptable for pilot |
| R6 | No load test → scaling unknown | Low (pilot scale) | Execute before production |
| R7 | No HTTPS/HSTS | Low (internal network) | Required before public exposure |
| R8 | No CSP | Low (portal internal) | Required before public exposure |

---

## Test Baseline (H.4)

| Suite | Result |
|---|---|
| H.4 targeted (security) | **72/72** ✅ |
| H.2 targeted (observability) | pass ✅ |
| H.3 targeted (ops scripts) | pass ✅ |
| Emergency suite (G.1–G.5) | **414/414** ✅ |
| Backend collection | **2458 / 0 errors** ✅ |
| Portal regression | Not run (no portal changes) |
| H.5 gate docs-only | ✅ 0 code changes |

---

## Explicit NO-GO Items

| Item | Reason |
|---|---|
| 🚫 Production switch | No approvals, no monitoring, no KSO test |
| 🚫 Real pilot in stores | 6 blockers unresolved |
| 🚫 Real emergency execution | No execution permission, no design gate |
| 🚫 ClickHouse pipeline | Performance gate deferred |
| 🚫 KSO production switch | Separate design gate pending |
| 🚫 mTLS / signed manifests | Deferred design gate |

---

## Required Actions Before Pilot

### Mandatory (H.6+)

1. **Define pilot store + device list** (business + ops)
2. **Deploy Prometheus + Grafana** + alert rules
3. **Execute backup/restore drill** against dev/staging
4. **Test KSO physical playback** (Chromium kiosk, mp4/h264, portrait 768×1024)
5. **Obtain business + security approvals**

### Recommended (H.6+)

6. Review operator runbooks with ops team
7. Define support escalation path
8. Execute load test (1k devices minimum)
9. Configure credential rotation process
10. Review operations publications.publish permission

---

## Final Decision

| Gate | Decision |
|---|---|
| **Real pilot in stores** | 🚫 **NO-GO** — 6 blockers |
| **Lab / internal testing** | 🟢 **GO** — H.6 preparation work |
| **Production switch** | 🚫 **NO-GO** — deferred |
| **KSO physical test** | 🟢 **GO** — execute during H.6 prep |

### Next: H.6 — Closure Gate

H.6 should:
- Execute KSO physical playback test
- Deploy Prometheus + Grafana
- Execute backup/restore drill
- Create pilot store/device list template
- Close out remaining prep items
- Re-assess pilot readiness

---

## ✅ GO для H.6 — Pilot Preparation / Closure Gate
