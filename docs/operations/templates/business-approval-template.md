# Business Approval — Retail Media Platform Pilot

**Version:** 1.0 | **Date:** ____-__-__ | **Status:** ⬜ Pending

> **IMPORTANT:** This is a template. Fill in and obtain sign-off before pilot.  
> No pilot can proceed without business approval.

---

## 1. Request

| Field | Value |
|---|---|
| **Request ID** | `BIZ-APPROVAL-____` |
| **Request Date** | ____-__-__ |
| **Requester** | ______________ |
| **Pilot Phase** | Phase H — Production Readiness Pilot |
| **Pilot Window** | ____-__-__ to ____-__-__ |

---

## 2. Pilot Goal

*What is the business objective of this pilot?*

_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

---

## 3. Pilot Scope

| Field | Value |
|---|---|
| **Stores** | __ store(s): ______________ |
| **Devices** | __ device(s): ______________ |
| **Device Type** | KSO (UKM5) |
| **Expected Ad Zones** | 1–5 portrait displays (768×1024 px) |
| **Expected Duration** | __ days |
| **Campaign Volume** | __ campaigns |
| **Expected Impressions** | ________ |

---

## 4. Operational Impact

| Area | Impact | Mitigation |
|---|---|---|
| **Store operations** | KSO device runs new player | On-site contact available |
| **Network** | Internal LAN — no external dependency | LAN only |
| **IT support** | Ops team monitors during pilot | Escalation path TBD |
| **Legacy KSO** | Legacy manifest unchanged | Rollback available |
| **Customer experience** | No change — same ad zones | — |

---

## 5. Success Criteria

| # | Criterion | Threshold |
|---|---|---|
| SC1 | Playback rate | > 95% of scheduled playbacks |
| SC2 | PoP visibility | PoP events visible in analytics |
| SC3 | Heartbeat consistency | Heartbeat every 60s ± 10s |
| SC4 | Zero production incidents | 0 emergency stops |
| SC5 | Device uptime | > 99% during pilot window |
| SC6 | Rollback tested | Rollback < 5 min confirmed |

---

## 6. Rollback Criteria

Pilot will be **rolled back** if:
- [ ] Playback rate drops below 80%
- [ ] Device goes offline > 1 hour
- [ ] PoP events stop for > 30 min
- [ ] Any production incident triggered
- [ ] Business owner or ops lead requests rollback

**Rollback owner:** ______________ (phone: ________)

---

## 7. Costs & Resources

| Resource | Estimate |
|---|---|
| **Ops team time** | __ hours during pilot |
| **Dev team time** | __ hours standby |
| **Store staff impact** | Minimal — no interaction needed |
| **Infrastructure cost** | Internal — no additional cost |
| **Risk of failure** | Low — legacy always available |

---

## 8. Risk Acknowledgement

The following risks are known and accepted:

| # | Risk | Likelihood | Impact | Accepted? |
|---|---|---|---|---|
| R1 | KSO physical playback fails | Medium | High | ⬜ |
| R2 | No runtime monitoring deployed | Medium | Medium | ⬜ |
| R3 | Backup/restore drill not completed | Low | Medium | ⬜ |
| R4 | Credential rotation not automated | Low | Low | ⬜ |

---

## 9. Decision

| Field | Value |
|---|---|
| **Decision** | ⬜ APPROVED / ⬜ CONDITIONAL / ⬜ REJECTED |
| **Conditions** | ______________ |
| **Approver Name** | ______________ |
| **Approver Role** | Business Owner |
| **Approval Date** | ____-__-__ |
| **Signature** | ______________ |
