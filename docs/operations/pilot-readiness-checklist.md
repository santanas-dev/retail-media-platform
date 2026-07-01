# Pilot Readiness Checklist

**Date:** 2026-07-02 | **Last review:** 2026-07-01 (H.6) | **Owner:** Ops Team (TBD)

> **Current Status: 🟡 PREPARATION PACKAGE READY — 6 blockers remain; templates/protocols created in H.6**  
> All blockers have templates/protocols ready — actions (not docs) needed for real pilot.

---

## Pilot Entry Criteria (16 checks)

### ✅ READY (7/16)

| # | Criterion | Evidence | Notes |
|---|---|---|---|
| P1 | No production switch without approval gate | H.0/H.1/G.6 docs | KSO switch deferred |
| P2 | Device heartbeat visible | Gateway API | Functional |
| P3 | PoP visible | Analytics API + portal | Functional |
| P4 | Emergency dry-run available | Emergency API + portal | Functional |
| P5 | No-secrets checks pass | Per-domain validators + H.4 verified | All suites pass |
| P16 | Rate limiting active on sensitive endpoints | H.4 in-memory rate limiter | Emergency 5/60s, Dependencies 10/60s |
| — | Security headers + CORS fixed + access review | H.4 | 9 headers, SafeCORSMiddleware |

### 🟡 PARTIAL — Templates/Protocols Ready (6/16)

| # | Criterion | Status | Evidence | Next |
|---|---|---|---|---|
| P6 | Pilot store list defined | 🟡 Template ready (H.6) | `pilot-store-device-list-template.md` | Fill + approve |
| P7 | Pilot device list defined | 🟡 Template ready (H.6) | `pilot-store-device-list-template.md` | Fill + approve |
| P9 | Monitoring enabled + alerts | 🟡 Configs ready (H.6) | `prometheus.example.yml`, `alert-rules.example.yml`, `monitoring-deployment-checklist.md` | Deploy |
| P10 | Backup/restore drill completed | 🟡 Protocol ready (H.6) | `backup-restore-drill-protocol.md` | Execute drill |
| P11 | KSO physical device test | 🟡 Protocol ready (H.6) | `kso-physical-playback-test-protocol.md` (9 phases) | Execute test |
| P14 | Security approval received | 🟡 Template ready (H.6) | `security-approval-template.md` | Sign |
| P15 | Business approval received | 🟡 Template ready (H.6) | `business-approval-template.md` | Sign |

### 🟡 PARTIAL — Other (2/16)

| # | Criterion | Status | Evidence | Next |
|---|---|---|---|---|
| P8 | Rollback plan approved | 🟡 Scripts ready (H.3); no real drill | `rollback_preflight.sh`, `rollback-runbook.md` | Execute drill + review |
| P12 | Operator runbook exists + reviewed | 🟡 Created (H.1); not reviewed | 6 runbooks in `docs/operations/` | Review with ops |

### ❌ NOT YET CLOSED (1/16)

| # | Criterion | Status | Next |
|---|---|---|---|
| P13 | Support escalation path exists | ❌ Missing | Define with management |

**Decision:** Preparation package complete (H.6). All 6 blockers have templates/protocols — executors can proceed to actual actions. Real pilot still NO-GO until evidence collected.

---

## Pilot Store / Device Selection (Template)

```
Pilot Store:   ____________________ (code: ________)
Store Address: ____________________
Device Code:   ____________________
Device Type:   KSO
Channel:       kso
Ad Zone:       768 × 1024 px (portrait — verify!)
Resolution:    768 × 1024 px
Network:       wired / wifi (SSID: ____)
Contact:       ____________________ (phone: ________)
```

---

## H.2–H.4 Improvements (since H.1 baseline)

| H.1 criterion | Was | Now (H.5) |
|---|---|---|
| Monitoring enabled (P9) | ❌ | 🟡 `/api/health/metrics` exists; no Prometheus/Grafana deployed |
| Backup/restore drill (P10) | ❌ | 🟡 Scripts exist; drill not done |
| Rollback plan (P8) | ❌ | 🟡 Scripts + preflight ready; drill pending |
| Rate limiting (new P16) | ❌ | ✅ In-memory, 4 tiers |
| No-secrets (P5) | ✅ | ✅ Re-verified (H.4) |
| Security headers / CORS | ❌ | ✅ 9 headers, fixed CORS |
| Access review | ⬜ | ✅ All roles verified |

---

## Blocking Items (must resolve before pilot)

| # | Blocker | Category |
|---|---|---|
| B1 | Pilot store/device list not defined | Operations |
| B2 | Monitoring + alerts not deployed | Observability |
| B3 | Backup/restore drill not completed | Operations |
| B4 | KSO physical device test not done | KSO |
| B5 | Security approval not received | Security |
| B6 | Business approval not received | Business |

---

## Non-Blocking Items (can defer past pilot start)

- Credential rotation mechanism (manual acceptable for pilot)
- Production HTTPS/HSTS (internal network only)
- CSP / UI security gate (portal SSR — separate gate)
- Load test 40k profile (pilot is 1-5 devices)
- Operator runbook review (during pilot prep)
- Support escalation path (internal pilot — direct contact)
- Redis-backed rate limiter (in-memory sufficient for pilot scale)

---

## Go/No-Go Decision Matrix

| Gate | Required | Status |
|---|---|---|
| All 16 criteria met | Yes | ❌ 7/16 |
| 6 blockers resolved | Yes | ❌ 0/6 |
| Rollback plan tested | Yes | ❌ |
| KSO device tested | Yes | ❌ |
| Monitoring active | Yes | ❌ |
| Backup/restore drill passed | Yes | ❌ |
| Business approval | Yes | ❌ |
| Security approval | Yes | ❌ |

**Decision: 🟡 CONDITIONAL NO-GO — lab/pre-pilot preparation OK; real pilot NO-GO until 6 blockers resolved.**
