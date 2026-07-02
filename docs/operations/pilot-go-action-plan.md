# Pilot GO — Action Plan

**Version:** 1.0 | **Date:** 2026-07-01 | **Owner:** Ops Team (TBD)

> **Goal:** Execute 6 blocking actions to reach REAL PILOT GO.  
> **Current state:** Preparation package complete (Phase H). 6 blockers require **actions**, not docs.  
> **Target:** Pilot GO decision gate → start limited pilot (1 store, 1–5 devices).

---

## Current Status

| Metric | Value |
|---|---|
| Phase H | ✅ COMPLETED (preparation) |
| Templates / protocols | ✅ 8 created (H.6) |
| Config templates | ✅ 3 created (H.6) |
| Backend test baseline | 2458 / 0 errors |
| Real pilot | 🚫 NO-GO — 6 blockers |

---

## 6 Blockers — Execution Order

### Recommended sequence (dependencies matter)

```
B3 (backup drill) → B4 (KSO test) → B1 (pilot list) ─┐
B2 (monitoring) ────────────────────────────────────────┤
                                                        ├─→ B5 (security)
                                                        └─→ B6 (business) → PILOT GO
```

**Rationale:**
- B3 (backup drill) and B4 (KSO test) are independent and can run in parallel
- B1 (pilot list) depends on B4 (need confirmed working device)
- B2 (monitoring) is independent
- B5/B6 (approvals) depend on evidence from B2, B3, B4

---

## Detailed Action Plans

---

### B1 — Pilot Store/Device List

| Field | Value |
|---|---|
| **Owner** | Business + Ops |
| **Template** | `docs/operations/templates/pilot-store-device-list-template.md` |
| **Dependencies** | B4 (confirmed working KSO device) |
| **Estimated effort** | 1 hour |

**Actions:**
1. [ ] Confirm KSO device working (B4 complete)
2. [ ] Select pilot store (1 store, on-site contact available)
3. [ ] Fill store section in template
4. [ ] Fill device section (1–5 devices, device codes, resolution, orientation)
5. [ ] Verify rollback path for each device
6. [ ] Obtain pre-pilot verification signatures (business + ops)
7. [ ] Save filled template as `docs/operations/pilot-lists/pilot-YYYY-MM-DD.md`

**Acceptance criteria:**
- [ ] 1 store selected with on-site contact
- [ ] 1–5 devices registered in Gateway
- [ ] Rollback path documented per device
- [ ] Business owner approved
- [ ] Ops owner approved

**Evidence:** Filled pilot list document in `docs/operations/pilot-lists/`

---

### B2 — Monitoring Deployment

| Field | Value |
|---|---|
| **Owner** | Ops |
| **Configs** | `docs/observability/prometheus.example.yml`, `alert-rules.example.yml`, `grafana-dashboard-requirements.md` |
| **Dependencies** | None (independent) |
| **Estimated effort** | 1 day |

**Actions:**
1. [ ] Copy `prometheus.example.yml` → deploy as `prometheus.yml`
2. [ ] Update `<BACKEND_HOST:PORT>` with actual backend address
3. [ ] Update `<PORTAL_HOST:PORT>` with actual portal address
4. [ ] Start Prometheus (Docker or bare metal)
5. [ ] Verify all 4 scrape targets: `curl http://<prometheus>:9090/api/v1/targets`
6. [ ] Copy `alert-rules.example.yml` → deploy as `alert-rules.yml`
7. [ ] Configure Alertmanager
8. [ ] Start Grafana
9. [ ] Configure Prometheus data source
10. [ ] Create 5 dashboards per `grafana-dashboard-requirements.md`
11. [ ] Fire test alert → verify notification channel
12. [ ] Document deployment in evidence tracker

**Acceptance criteria:**
- [ ] Prometheus scraping all 4 targets with status "UP"
- [ ] Grafana showing at least 3 dashboards
- [ ] Alert rules loaded: `curl http://<prometheus>:9090/api/v1/rules`
- [ ] Test alert fired and received on notification channel

**Evidence:** Screenshots of Prometheus targets, Grafana dashboards, alert test

---

### B3 — Backup/Restore Drill

| Field | Value |
|---|---|
| **Owner** | Ops |
| **Protocol** | `docs/operations/backup-restore-drill-protocol.md` |
| **Dependencies** | None (lab/stage only) |
| **Estimated effort** | 2 hours |
| **⚠️ SAFETY** | Lab/stage DB only. NEVER production. CONFIRM_RESTORE=yes. |

**Actions:**
1. [ ] Set up lab/stage environment variables (NO PRODUCTION)
2. [ ] Execute Phase 1: pre-drill verification (6 checks)
3. [ ] Execute Phase 2: backup execution (4 steps)
4. [ ] Record checksum of backup file
5. [ ] Execute Phase 3: intentional data change (insert test row)
6. [ ] Execute Phase 4: restore execution (3 steps)
7. [ ] Execute Phase 5: post-restore validation (7 checks)
8. [ ] Record RPO and RTO measurements
9. [ ] Execute MinIO backup drill (optional)
10. [ ] Document all evidence in tracker

**Acceptance criteria:**
- [ ] Backup created successfully (> 1 KB)
- [ ] Restore completed without errors
- [ ] Post-restore validation: all table row counts match pre-backup
- [ ] Seed re-run: "Seed complete"
- [ ] Health check: `/api/health/ready` → 200
- [ ] RPO < 5 minutes
- [ ] RTO < 15 minutes

**Evidence:** Terminal output of all 5 phases, checksum, RPO/RTO timestamps

---

### B4 — KSO Physical Playback Test

| Field | Value |
|---|---|
| **Owner** | Ops |
| **Protocol** | `docs/operations/kso-physical-playback-test-protocol.md` |
| **Dependencies** | Physical KSO device (192.168.110.223) |
| **Estimated effort** | 4 hours |
| **⚠️ SAFETY** | Lab/stage only. NO production switch. NO KSO production flow change. |

**Actions:**
1. [ ] Phase 1: Hardware & OS (5 checks)
2. [ ] Phase 2: Display & Graphics (4 checks)
3. [ ] Phase 3: Chromium Kiosk (4 checks)
4. [ ] Phase 4: Network & Gateway (4 checks)
5. [ ] Phase 5: Media Playback (7 checks)
6. [ ] Phase 6: Playlist / Campaign (3 checks)
7. [ ] Phase 7: Proof of Play (4 checks)
8. [ ] Phase 8: Fallback & Rollback (4 checks)
9. [ ] Phase 9: Emergency Dry-Run (3 checks)
10. [ ] Collect evidence: screenshots + terminal output + video
11. [ ] Document all evidence in tracker

**Acceptance criteria:**
- [ ] All Phase 1–8 checks pass
- [ ] At least 3 full playbacks observed
- [ ] PoP events confirmed for all playbacks
- [ ] Heartbeat every 60s
- [ ] Rollback tested < 5 min
- [ ] Emergency dry-run shows device in scope
- [ ] No production switch triggered
- [ ] Evidence: screenshots + terminal + video

**Evidence:** Screenshots (9 phases), terminal output, video of playback

---

### B5 — Security Approval

| Field | Value |
|---|---|
| **Owner** | Security |
| **Template** | `docs/operations/templates/security-approval-template.md` |
| **Dependencies** | B2 (monitoring deployed), B3 (backup drill), B4 (KSO tested) |
| **Estimated effort** | 1 day (review cycle) |

**Actions:**
1. [ ] Fill security approval template with actual data
2. [ ] Attach evidence from B2 (monitoring deployed)
3. [ ] Attach evidence from B3 (backup/restore drill)
4. [ ] Attach evidence from B4 (KSO physical test)
5. [ ] Present to security reviewer
6. [ ] Address any conditions
7. [ ] Obtain signed approval

**Acceptance criteria:**
- [ ] Template filled with actual scope
- [ ] Evidence attached for B2, B3, B4
- [ ] Risks acknowledged and accepted
- [ ] Signed by Security Administrator

**Evidence:** Signed `SEC-APPROVAL-XXXX` document

---

### B6 — Business Approval

| Field | Value |
|---|---|
| **Owner** | Business |
| **Template** | `docs/operations/templates/business-approval-template.md` |
| **Dependencies** | B1 (pilot list filled), B5 (security approval) |
| **Estimated effort** | 1 day (review cycle) |

**Actions:**
1. [ ] Fill business approval template with actual data
2. [ ] Attach filled pilot list (B1)
3. [ ] Attach security approval (B5)
4. [ ] Present to business stakeholder
5. [ ] Address any conditions
6. [ ] Obtain signed approval

**Acceptance criteria:**
- [ ] Template filled with pilot scope and success criteria
- [ ] Risks acknowledged and accepted
- [ ] Filled pilot list attached
- [ ] Security approval attached
- [ ] Signed by Business Owner

**Evidence:** Signed `BIZ-APPROVAL-XXXX` document

---

## Dependencies Map

```
B3 (backup drill) ─────┐
                        ├──→ B5 (security) ──→ B6 (business) ──→ PILOT GO
B4 (KSO test) ─────────┤                         │
                        │                         │
B2 (monitoring) ────────┘                         │
                                                  │
B1 (pilot list) ──────────────────────────────────┘
```

**Parallelizable:** B2 ‖ B3 ‖ B4  
**Sequential:** B5 after B2+B3+B4, B6 after B1+B5

---

## Estimated Timeline

| Day | Actions | Dependencies |
|---|---|---|
| Day 1 | B2 (deploy monitoring) + B3 (backup drill) + B4 start (KSO test) | None |
| Day 2 | B4 complete (KSO test) + B1 (fill pilot list) | B4 done |
| Day 3 | B5 (security approval) + B6 (business approval) | B1+B2+B3+B4 done |
| Day 4 | PILOT GO DECISION | All 6 done |

**Total: ~4 days** при наличии KSO hardware.

---

## Pilot GO Decision Gate

After all 6 blockers closed:

| Gate | Required | Status |
|---|---|---|
| All 16 pilot criteria met | Yes | ⬜ Pending |
| All 6 blockers resolved with evidence | Yes | ⬜ Pending |
| Pilot list filled + approved | Yes | ⬜ Pending |
| Monitoring deployed + alerts tested | Yes | ⬜ Pending |
| Backup/restore drill passed | Yes | ⬜ Pending |
| KSO physical playback test passed | Yes | ⬜ Pending |
| Security approval signed | Yes | ⬜ Pending |
| Business approval signed | Yes | ⬜ Pending |

**Decision: ⬜ GO / ⬜ NO-GO**  
**Date of decision:** ______________  
**Approver:** ______________

---

## Explicit NO-GO (unchanged)

- 🚫 Production switch
- 🚫 Real emergency execution
- 🚫 ClickHouse pipeline
- 🚫 KSO production switch
- 🚫 mTLS / signed manifests
