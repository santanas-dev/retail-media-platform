# Known Risks and Deferred Items

> **Date:** 2026-06-16  
> **Baseline:** v0.12.0-product-workflow-backend-manifest  

---

## Pilot Blockers

These must be resolved before any physical KSO pilot phase.

| # | Blocker | Impact | Resolution | Status |
|---|---|---|---|---|
| B1 | **HW scanner E2E not executed** | Cannot validate barcode → campaign match on physical KSO | Acquire scanner hardware + run E2E per `docs/audit/hw-scanner-e2e-validation-plan.md` | 🔴 Blocked |
| B2 | **Controlled long-run not executed** | No stability data for 1h+ continuous operation | Run 1h controlled test with monitoring per `docs/audit/pilot-readiness-gates-plan.md` Gate B | 🔴 Blocked |
| B3 | **Physical KSO delivery not approved** | Cannot deliver manifest or sync sidecar on physical KSO | Explicit approval token `PHASE_MANIFEST_DELIVERY_APPROVED` required | 🔴 Blocked |

---

## Non-Blocking Technical Debt

These can be addressed after pilot or in parallel — they do not block the pilot.

| # | Item | Impact | Resolution | Priority |
|---|---|---|---|---|
| T1 | **ScheduleRun raw SQL in create_batch_from_campaign** | Uses `text()` instead of ORM. Works correctly but is less maintainable. | ORM model exists (`ScheduleRun`); migrate `create_batch_from_campaign` to use ORM | 🟢 Low |
| T2 | **CampaignCreative.is_active ORM/schema mismatch** | Column exists in DB but not in ORM model. Compat helper active (`_is_campaign_creative_active`). | Add column to ORM model + alembic migration (deferred to migration track) | 🟢 Low |
| T3 | **7 legacy BackendClient methods unused** | Dead code: `list_campaigns(test-kso)`, `list_placements`, `create_placement`, `list_approvals(test-kso)`, `request_approval(test-kso)`, `decide_approval`, `get_test_kso_readiness` (unauthenticated) | Remove or refactor to production endpoints | 🟢 Low |
| T4 | **/deployment page demo-only** | Static page with no backend data — documentation placeholder | Keep as-is until deployment system is built | 🟢 Low |
| T5 | **ScheduleConflict ORM model missing** | `schedule_conflicts` table exists in DB (migration 008) but no ORM model | Add model when conflict resolution is implemented | 🟢 Low |

---

## Known Risks (Accepted)

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Python 3.6.9 on KSO** | Certain | Some modern syntax unavailable | All code compatible; `fromisoformat` replaced; `Optional[Type]` used instead of `Type \| None` |
| R2 | **Single test device** | Certain | No redundancy if KSO fails | Pilot scope limited to 1 KSO; rollback documented |
| R3 | **No mTLS for device auth** | Low for pilot | Slightly weaker device identity | JWT + bcrypt secret sufficient for single-device pilot |
| R4 | **No rate limiting on device-auth** | Low for pilot | Single device, no abuse risk | Add before fleet rollout |
| R5 | **Sidecar daemon not configured** | Medium | Manual start per phase | Acceptable for controlled pilot; systemd autostart deferred |

---

## Deferred to Post-Pilot

| # | Item | Reason |
|---|---|---|
| D1 | Fleet rollout (3+ KSO devices) | Requires successful 1-KSO pilot |
| D2 | Performance benchmarks | Pilot is functional validation, not load test |
| D3 | CI/CD pipeline | Manual regression sufficient for pre-pilot |
| D4 | Production device credentials / mTLS | Single device with static secret OK for pilot |
| D5 | Observability (metrics, alerting) | Manual monitoring sufficient for 1h long-run |
| D6 | Excel/Power BI reports | Not needed for technical pilot validation |
| D7 | Consolidation of enterprise + KSO domains | Architecture refactor — post-pilot |

---

## Document Sign-Off

| Role | Name | Date | Acknowledged |
|---|---|---|---|
| Product Owner | ________ | ________ | ________ |
| Security Lead | ________ | ________ | ________ |
| KSO Operator | ________ | ________ | ________ |
