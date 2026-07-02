# Pilot GO — Evidence Tracker

**Version:** 1.0 | **Date:** 2026-07-01 | **Owner:** Ops Team

> Track evidence for all 6 blockers. Update status as actions are completed.  
> **PILOT GO only when ALL blockers have evidence → approved.**

---

## Legend

| Symbol | Meaning |
|---|---|
| ⬜ | Not started |
| 🔄 | In progress |
| 🟡 | Evidence collected, pending review |
| ✅ | Approved |
| ❌ | Blocked / failed |

---

## Blocker Status Summary

| # | Blocker | Status | Evidence | Reviewer | Decision | Date |
|---|---|---|---|---|---|---|
| B1 | Pilot store/device list | ⬜ | — | Business + Ops | ⬜ | |
| B2 | Monitoring deployed + alerts | 🟡 | `docs/evidence/pilot/b2-monitoring/` | Ops | ⬜ | 2026-07-02 |
| B3 | Backup/restore drill | 🟡 | `docs/evidence/pilot/b3-backup-restore/` | Ops | ⬜ | 2026-07-02 |
| B4 | KSO physical playback test | 🔴 | `docs/evidence/pilot/b4-kso-physical/` | Ops | ⬜ | BLOCKED_BY_HARDWARE |
| B5 | Security approval | ⬜ | — | Security | ⬜ | |
| B6 | Business approval | ⬜ | — | Business | ⬜ | |

---

## B1 — Pilot Store/Device List

| Field | Value |
|---|---|
| **Owner** | Business + Ops |
| **Template** | `docs/operations/templates/pilot-store-device-list-template.md` |

| # | Action | Status | Evidence Required | Evidence Link | Notes |
|---|---|---|---|---|---|
| B1.1 | Select pilot store | ⬜ | Store code + address + contact | — | |
| B1.2 | Confirm on-site contact | ⬜ | Contact name + phone | — | |
| B1.3 | Register devices in Gateway | ⬜ | Gateway device IDs | — | |
| B1.4 | Fill pilot list template | ⬜ | Filled `pilot-YYYY-MM-DD.md` | — | |
| B1.5 | Verify rollback path per device | ⬜ | Rollback verified checkbox | — | |
| B1.6 | Business owner approval | ⬜ | Signature | — | |
| B1.7 | Ops owner approval | ⬜ | Signature | — | |

**Reviewer:** ______________  
**Decision:** ⬜ Approved / ⬜ Rejected  
**Date:** ____-__-__

---

## B2 — Monitoring Deployment

| Field | Value |
|---|---|
| **Owner** | Ops |
| **Configs** | `prometheus.example.yml`, `alert-rules.example.yml`, `grafana-dashboard-requirements.md` |

| # | Action | Status | Evidence Required | Evidence Link | Notes |
|---|---|---|---|---|---|
| B2.1 | Deploy Prometheus | ⬜ | `curl :9090/api/v1/targets` — all UP | — | |
| B2.2 | Verify scrape targets (4) | ⬜ | Screenshot of targets page | — | |
| B2.3 | Deploy alert rules | ⬜ | `curl :9090/api/v1/rules` — rules loaded | — | |
| B2.4 | Configure Alertmanager | ⬜ | Alertmanager UI screenshot | — | |
| B2.5 | Deploy Grafana | ⬜ | Grafana login page screenshot | — | |
| B2.6 | Create Backend Health dashboard | ⬜ | Dashboard screenshot | — | |
| B2.7 | Create Request Metrics dashboard | ⬜ | Dashboard screenshot | — | |
| B2.8 | Create Gateway Heartbeat dashboard | ⬜ | Dashboard screenshot | — | |
| B2.9 | Create PoP dashboard | ⬜ | Dashboard screenshot | — | |
| B2.10 | Create Emergency + RL dashboard | ⬜ | Dashboard screenshot | — | |
| B2.11 | Fire test alert → verify delivery | ⬜ | Alert notification screenshot | — | |
| B2.12 | Document deployment | 🟡 | Evidence files created | `docs/evidence/pilot/b2-monitoring/` |

**Reviewer:** ______________  
**Decision:** ⬜ Approved / ⬜ Rejected  
**Date:** ____-__-__

---

## B3 — Backup/Restore Drill

| Field | Value |
|---|---|
| **Owner** | Ops |
| **Protocol** | `docs/operations/backup-restore-drill-protocol.md` |
| **⚠️ SAFETY** | Lab/stage DB only. NEVER production. |

| # | Action | Status | Evidence Required | Evidence Link | Notes |
|---|---|---|---|---|---|
| B3.1 | Pre-drill verification (6 checks) | 🟡 | Scripts verified --help/--dry-run | `docs/evidence/pilot/b3-backup-restore/` | 2026-07-02 |
| B3.2 | Execute backup | ⬜ | Terminal + checksum | — | |
| B3.3 | Backup file checksum | ⬜ | SHA256 hash | — | |
| B3.4 | Intentional data change | ⬜ | INSERT confirmation | — | |
| B3.5 | Execute restore (guarded) | ⬜ | Terminal output | — | |
| B3.6 | Post-restore validation (7 checks) | ⬜ | Row counts match | — | |
| B3.7 | Seed re-run | ⬜ | "Seed complete" | — | |
| B3.8 | Health check post-restore | ⬜ | `curl /api/health/ready` → 200 | — | |
| B3.9 | RPO measurement | ⬜ | Timestamp diff | — | |
| B3.10 | RTO measurement | ⬜ | Timestamp diff | — | |
| B3.11 | Evidence documented | 🟡 | 5 evidence files created | `docs/evidence/pilot/b3-backup-restore/` | 2026-07-02 |

**RPO achieved:** ______ seconds  
**RTO achieved:** ______ seconds  
**Reviewer:** ______________  
**Decision:** ⬜ Approved / ⬜ Rejected  
**Date:** ____-__-__

---

## B4 — KSO Physical Playback Test

| Field | Value |
|---|---|
| **Owner** | Ops |
| **Protocol** | `docs/operations/kso-physical-playback-test-protocol.md` |
| **⚠️ SAFETY** | Lab/stage only. NO production switch. |

| # | Action | Status | Evidence Required | Evidence Link | Notes |
|---|---|---|---|---|---|
| B4.1 | Phase 1: Hardware & OS (5) | ⬜ | Screenshot + terminal | — | |
| B4.2 | Phase 2: Display & Graphics (4) | ⬜ | Screenshot (xrandr + visual) | — | |
| B4.3 | Phase 3: Chromium Kiosk (4) | ⬜ | Screenshot | — | |
| B4.4 | Phase 4: Network & Gateway (4) | ⬜ | Terminal output | — | |
| B4.5 | Phase 5: Media Playback (7) | ⬜ | Video (.mp4) | — | |
| B4.6 | Phase 6: Playlist / Campaign (3) | ⬜ | Log output | — | |
| B4.7 | Phase 7: Proof of Play (4) | ⬜ | API query + portal screenshot | — | |
| B4.8 | Phase 8: Fallback & Rollback (4) | ⬜ | Log + screenshot | — | |
| B4.9 | Phase 9: Emergency Dry-Run (3) | ⬜ | API response | — | |
| B4.10 | Acceptance criteria review | ⬜ | Checklist | — | |

**Playback success rate:** ______ / ______  
**Rollback time:** ______ seconds  
**Reviewer:** ______________  
**Decision:** ⬜ Approved / ⬜ Rejected  
**Date:** ____-__-__

---

## B5 — Security Approval

| Field | Value |
|---|---|
| **Owner** | Security |
| **Template** | `docs/operations/templates/security-approval-template.md` |

| # | Action | Status | Evidence Required | Evidence Link | Notes |
|---|---|---|---|---|---|
| B5.1 | Fill approval template | ⬜ | Filled template | — | |
| B5.2 | Attach B2 evidence (monitoring) | ⬜ | Link to B2 evidence | — | |
| B5.3 | Attach B3 evidence (backup drill) | ⬜ | Link to B3 evidence | — | |
| B5.4 | Attach B4 evidence (KSO test) | ⬜ | Link to B4 evidence | — | |
| B5.5 | Present to security reviewer | ⬜ | Meeting notes | — | |
| B5.6 | Address conditions (if any) | ⬜ | — | — | |
| B5.7 | Obtain signed approval | ⬜ | Signed document | — | |

**Approval ID:** `SEC-APPROVAL-____`  
**Approver:** ______________  
**Decision:** ⬜ Approved / ⬜ Conditional / ⬜ Rejected  
**Conditions:** ______________  
**Date:** ____-__-__

---

## B6 — Business Approval

| Field | Value |
|---|---|
| **Owner** | Business |
| **Template** | `docs/operations/templates/business-approval-template.md` |

| # | Action | Status | Evidence Required | Evidence Link | Notes |
|---|---|---|---|---|---|
| B6.1 | Fill approval template | ⬜ | Filled template | — | |
| B6.2 | Attach B1 evidence (pilot list) | ⬜ | Link to B1 evidence | — | |
| B6.3 | Attach B5 evidence (security) | ⬜ | Link to B5 evidence | — | |
| B6.4 | Define success criteria | ⬜ | 6 criteria filled | — | |
| B6.5 | Define rollback criteria | ⬜ | 4 criteria filled | — | |
| B6.6 | Present to business stakeholder | ⬜ | Meeting notes | — | |
| B6.7 | Address conditions (if any) | ⬜ | — | — | |
| B6.8 | Obtain signed approval | ⬜ | Signed document | — | |

**Approval ID:** `BIZ-APPROVAL-____`  
**Approver:** ______________  
**Decision:** ⬜ Approved / ⬜ Conditional / ⬜ Rejected  
**Conditions:** ______________  
**Date:** ____-__-__

---

## Pilot GO Decision

| # | Blocker | Status |
|---|---|---|
| B1 | Pilot store/device list | ⬜ |
| B2 | Monitoring deployed + alerts | ⬜ |
| B3 | Backup/restore drill | ⬜ |
| B4 | KSO physical playback test | ⬜ |
| B5 | Security approval | ⬜ |
| B6 | Business approval | ⬜ |

**PILOT GO:** ⬜ YES / ⬜ NO  
**Decision date:** ______________  
**Decision maker:** ______________
