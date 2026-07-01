# Pilot Readiness Checklist

**Date:** 2026-07-02 | **Phase:** H.1 | **Owner:** Ops Team (TBD)

> **Current Status: ❌ NOT READY**  
> Reason: blocking gaps from H.0 — monitoring/backup/rate-limiting/KSO-test/load-test отсутствуют.

---

## Pilot Entry Criteria (14 checks)

### ✅ Met (5/14)

| # | Criterion | Evidence | Notes |
|---|---|---|---|
| P1 | No production switch without approval gate | H.0/H.1 docs | KSO switch deferred |
| P2 | Device heartbeat visible | Gateway API | Functional |
| P3 | PoP visible | Analytics API + portal | Functional |
| P4 | Emergency dry-run available | Emergency API + portal | Functional |
| P5 | No-secrets checks pass | Per-domain validators | All suites pass |

### ❌ Not Met (9/14) — Blocking Pilot

| # | Criterion | Status | Owner | H target |
|---|---|---|---|---|
| P6 | Pilot store list defined | ❌ **Missing** | Ops | H.1 |
| P7 | Pilot device list defined | ❌ **Missing** | Ops | H.1 |
| P8 | Rollback plan approved | ❌ **Missing** | Ops/Dev | H.3 |
| P9 | Monitoring enabled + alerts configured | ❌ **Missing** | Ops/Dev | H.2 |
| P10 | Backup/restore drill completed | ❌ **Missing** | Ops/Dev | H.3 |
| P11 | KSO physical device test completed | ❌ **Not tested** | Ops | H.5 |
| P12 | Operator runbook exists + reviewed | ⬜ Created (H.1) | Ops | Review |
| P13 | Support escalation path exists | ❌ **Missing** | Ops/Mgmt | H.1 |
| P14 | Security approval + business approval received | ❌ **Missing** | Security/Mgmt | H.5 |

---

## Pilot Store / Device Selection (Template)

```
Pilot Store:   ____________________ (code: ________)
Store Address: ____________________
Device Code:   ____________________
Device Type:   KSO
Channel:       kso
Ad Zone:       ____×____ px (verify!)
Resolution:    ____×____ px
Network:       wired / wifi (SSID: ____)
Contact:       ____________________ (phone: ________)
```

---

## Go/No-Go Decision Matrix

| Gate | Required | Status |
|---|---|---|
| All 14 criteria met | Yes | ❌ 5/14 |
| Blocking risks mitigated (R1,R2,R4,R12,R13,R14) | Yes | ❌ 0/6 |
| Rollback plan tested | Yes | ❌ |
| KSO device tested | Yes | ❌ |
| Monitoring active | Yes | ❌ |
| Backup/restore drill passed | Yes | ❌ |
| Business approval | Yes | ❌ |
| Security approval | Yes | ❌ |

**Decision: NO-GO until all criteria met (estimated after H.5).**
