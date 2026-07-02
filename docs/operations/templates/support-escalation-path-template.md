# Support Escalation Path Template

**Version:** 1.0 | **Date:** ____-__-__ | **Owner:** Ops Team

> **IMPORTANT:** Fill in before pilot. Defines who to contact during pilot incidents.  
> This template closes pilot criterion P13 — support escalation path.

---

## Escalation Levels

### L1 — Ops / First Responder

| Field | Value |
|---|---|
| **Team / Person** | ______________ |
| **Primary Contact** | ______________ (phone: ________) |
| **Backup Contact** | ______________ (phone: ________) |
| **Escalation Trigger** | Any incident detected by monitoring (alert fired) or reported by store |
| **Response Time** | < 5 minutes |
| **Actions** | 1. Acknowledge alert 2. Check Grafana dashboards 3. Attempt restart/recovery 4. Escalate to L2 if unresolved > 15 min |
| **Fallback** | Rollback to legacy mode if issue persists > 15 min |

---

### L2 — Dev / Engineering

| Field | Value |
|---|---|
| **Team / Person** | ______________ |
| **Primary Contact** | ______________ (phone: ________) |
| **Backup Contact** | ______________ (phone: ________) |
| **Escalation Trigger** | L1 unable to resolve within 15 min; or L1 requests escalation |
| **Response Time** | < 15 minutes |
| **Actions** | 1. Investigate backend/Gateway logs 2. Check DB connectivity 3. Run health/debug checks 4. Hotfix if possible 5. Escalate to L3 if unresolved > 1 hour |
| **Fallback** | Full rollback to legacy KSO mode; stop pilot; notify business |

---

### L3 — Architecture / Emergency

| Field | Value |
|---|---|
| **Team / Person** | ______________ |
| **Primary Contact** | ______________ (phone: ________) |
| **Backup Contact** | ______________ (phone: ________) |
| **Escalation Trigger** | L2 unable to resolve within 1 hour; or critical failure (DB down, Gateway down, data loss) |
| **Response Time** | < 30 minutes |
| **Actions** | 1. Full incident response per `incident-response-runbook.md` 2. Emergency dry-run preview 3. Decision: continue pilot or full stop 4. Engage external support if needed |
| **Fallback** | Emergency stop all pilot campaigns; full rollback; incident report |

---

## Key Contacts

| Role | Name | Phone | Email |
|---|---|---|---|
| **Business Owner** | ______________ | ________ | ________ |
| **Security Owner** | ______________ | ________ | ________ |
| **IT / Network** | ______________ | ________ | ________ |
| **Store Manager** | ______________ | ________ | ________ |
| **On-Site Contact** | ______________ | ________ | ________ |

---

## Incident Communication Template

```
[PILOT INCIDENT] <Severity: L1/L2/L3>
Time: <HH:MM UTC>
Device: <DEVICE_CODE>
Store: <STORE_CODE>
Issue: <description>
Status: <investigating / mitigating / resolved>
Next update: <HH:MM UTC>
Contact: <NAME> at <PHONE>
```

---

## After-Hours Coverage

| Period | Coverage | Contact |
|---|---|---|
| Business hours (09:00–18:00) | Full L1+L2 | Standard contacts |
| After hours (18:00–09:00) | ⬜ None / ⬜ L1 on-call / ⬜ Full | ________ |
| Weekends | ⬜ None / ⬜ L1 on-call / ⬜ Full | ________ |
| Holidays | ⬜ None / ⬜ ________ | ________ |

---

## Approval

| Role | Name | Date | Signature |
|---|---|---|---|
| Ops Owner | ______________ | __-__-__ | ________ |
| Business Owner | ______________ | __-__-__ | ________ |
