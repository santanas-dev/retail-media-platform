# Technical Debt Register — 42.4

**Date:** 2026-06-16
**Baseline:** HEAD `c3b8daa` (42.3)
**Total items:** 34 (6 P0, 4 P1, 20 P2, 4 P3)

---

## P0 — Pilot Blockers

*Без закрытия этих пунктов нельзя идти в physical pilot.*

| ID | Title | Area | Evidence | Risk | Required Fix | Suggested Step | Pilot Impact | Owner | Dependencies |
|---|---|---|---|---|---|---|---|---|---|
| D-DV-01 | Physical KSO device auth never tested | backend | No physical KSO auth session recorded | Auth flow may fail on real hardware | Execute device auth against physical UKM5 | Post-pilot-gate | Blocker | Ops | Physical KSO access |
| D-KS-01 | Device auth never tested with physical KSO | kso-player | Only test-dev-seed used | JWT flow may fail | End-to-end auth test on physical KSO | Post-pilot-gate | Blocker | Ops | D-DV-01 |
| D-KS-02 | Manifest fetch never tested end-to-end | sidecar | No physical manifest delivery recorded | Manifest may not parse on real KSO | E2E manifest delivery test | Post-pilot-gate | Blocker | Ops | Physical KSO |
| D-KS-03 | Media file download never tested from KSO | sidecar | MinIO access from KSO network unverified | Network/firewall may block media fetch | E2E media download test | Post-pilot-gate | Blocker | Ops | Physical KSO, MinIO access |
| D-KS-04 | Sidecar sync never physically started | sidecar | No sidecar daemon session on physical KSO | Sync may not start | Start sidecar on physical KSO, verify PoP send | Post-pilot-gate | Blocker | Ops | Physical KSO |
| D-IN-01 | systemd units never deployed to physical KSO | infra | No systemd deployment recorded | Daemons won't auto-start | Deploy and enable systemd units | Post-pilot-gate | Blocker | Ops | Physical KSO, D-KS-04 |
| D-IN-04 | Controlled 48h+ long-run never executed | infra | No long-run evidence | Memory leaks, crashes, disk full | Execute 48h+ monitoring | Post-pilot-gate | Blocker | Ops | All P0 items |

---

## P1 — Pre-Pilot Hardening

*Нужно закрыть до controlled pilot или до расширения fleet.*

| ID | Title | Area | Evidence | Risk | Required Fix | Suggested Step | Pilot Impact | Owner | Dependencies |
|---|---|---|---|---|---|---|---|---|---|
| D-MF-02 | Manifest delivery to physical KSO not validated | backend | No delivery gate approval | Manifest may not reach KSO | Delivery gate approval + test | Post-pilot-gate | Pre-pilot hardening | Ops | Physical KSO |
| D-KS-05 | No graceful offline degradation | sidecar | Daemon retries indefinitely without backpressure | Resource exhaustion on prolonged backend outage | Add exponential backoff, circuit breaker | 43.x | Pre-pilot hardening | Dev | — |
| D-IN-02 | No formal rollback runbook | infra | Docs missing | Cannot roll back failed pilot | Create rollback runbook | 43.x | Pre-pilot hardening | Docs | — |
| D-DC-01 | No security hardening document | docs | No dedicated security doc | Security review incomplete | Create `docs/security/hardening-plan.md` | 43.x | Pre-pilot hardening | Security | — |

---

## P2 — v1.x Hardening

*Можно после первого controlled pilot. Не блокирует pilot gate.*

| ID | Title | Area | Evidence | Risk | Required Fix | Suggested Step |
|---|---|---|---|---|---|---|
| D-A-01 | Remove test-kso approval endpoints | backend | 5 refs in approvals/router.py | Dual paths cause confusion | Delete test-kso routes, keep production | 43.x |
| D-A-02 | _IncludedRouter path introspection | backend | FastAPI 0.137.1 limitation | Tests fragile | Workaround exists (TestClient) | Deferred |
| D-PB-01 | Raw SQL ScheduleRun references | backend | fromisoformat issues on 3.6.9 | Python 3.6.9 incompatibility | Replace fromisoformat with strptime | 43.x |
| D-PB-02 | PublicationBatch non-admin CSV | backend | By design — admin-only fields hidden | No risk | Documented, no fix needed | — |
| D-MF-01 | Remove test-kso manifest endpoints | backend | 6 refs in manifests/router.py | Dual paths confuse | Delete test-kso routes | 43.x |
| D-RP-01 | No Excel/XLSX export | backend | CSV only in 42.3 | Business users prefer XLSX | Add XLSX if safe dependency available | Deferred |
| D-RP-02 | No date-range filter on exports | backend | Exports all data, no filter params | Large exports for big datasets | Add date_from/date_to to export endpoints | 43.x |
| D-CA-01 | Remove test-kso campaign endpoints | backend | 6 refs in campaigns/router.py | Dual paths confuse | Delete test-kso routes | 43.x |
| D-CA-02 | 7 legacy BackendClient test-kso methods | portal | 23 refs in backend_client.py | Dead code, maintenance burden | Remove legacy methods | 43.x |
| D-SC-01 | Remove test-kso schedule/placement endpoints | backend | 3 refs in scheduling/router.py | Dual paths confuse | Delete test-kso routes | 43.x |
| D-DV-02 | device_secret rotation not implemented | backend | No rotation endpoint | Long-lived secrets risk | Add rotation endpoint with audit | 43.x |
| D-DV-03 | KsoDevice screen defaults 1920×1080 | backend | Seeded for non-test-kso devices | Incorrect for portrait fleet | Update seed to 768×1024 default | 43.x |
| D-PP-02 | Remove test-kso PoP endpoints | backend | 3 refs in PoP router | Dual paths confuse | Delete test-kso routes | 43.x |
| D-SR-01 | Verify test-kso safe projection parity | backend | Before removal of test-kso paths | Could lose safety on migration | Audit each test-kso endpoint before deletion | 43.x |
| D-TK-01 | Remove all test-kso production paths | backend | 171 refs across 27 files | Legacy debt accumulation | Consolidation sprint | 43.x |
| D-TK-02 | Remove 7 legacy BackendClient methods | portal | See D-CA-02 | Dead code | Remove + update tests | 43.x |
| D-TK-03 | Remove test_kso_readiness from production | backend | Entire domain is test-only | Non-production code in prod router | Move to test-only or remove from main.py | 43.x |
| D-PT-01 | Remove demo_data imports | portal | 9 functions imported, unused in prod | Dead code, misleading | Remove imports and demo_data.py | 43.x |
| D-IN-03 | No incident response runbook | infra | Docs missing | No procedure for incidents | Create IR runbook | 43.x |
| D-DC-02 | Create campaign-workflow.md | docs | Missing doc | Incomplete product docs | Create doc | 43.x |
| D-DC-03 | Create ADR directory | docs | No architecture decisions recorded | Lost rationale | Create `docs/architecture/adr/` | 43.x |
| D-DC-04 | Update portal-backend-integration-matrix for 42.3 | docs | Outdated matrix | Missing export route coverage | Add 42.3 export routes to matrix | 43.x |

---

## P3 — Nice-to-Have

*Улучшения без влияния на pilot gate.*

| ID | Title | Area | Evidence | Risk | Required Fix |
|---|---|---|---|---|---|
| — | Campaign export link hidden when no data | portal | Empty state has no CSV button | Minor UX confusion | Always show export link |
| — | No date-range on CSV exports | portal | See D-RP-02 | — | — |
| — | Portal branding "KSO v1" | portal | Sidebar subtitle | Minor | Update to "Retail Media Platform v0.12" |
| — | Chart placeholders removed (42.3) | portal | BI charts placeholder block removed | No visualizations yet | Deferred to BI integration step |

---

## Known Pilot Blockers (unchanged from 42.1)

| ID | Blocker | Status | Resolution Gate |
|---|---|---|---|
| B-01 | HW scanner E2E validation | ❌ | Scanner hardware available |
| B-02 | Controlled 48h+ long-run | ❌ | All P0 items closed, monitoring ready |
| B-03 | Manifest delivery to physical KSO | ❌ | Physical KSO access, network configured |
| B-04 | Sidecar sync physical start | ❌ | D-KS-04 resolved |
| B-05 | Pilot runbook/fallback/rollback finalization | ❌ | D-IN-02 resolved |
| B-06 | Live pilot/fleet rollout approval | ❌ | All P0 + P1 closed |

**No new blockers introduced by 42.3.**

---

## Execution Notes

- All P0 items require physical KSO access — blocked until pilot gate opens
- P1 items should be addressed before controlled pilot expansion
- P2 items (20 total) can be batched into a test-kso cleanup sprint (43.x)
- P3 items are cosmetic/UX — no timeline pressure
- No runtime/physical actions taken during this audit
