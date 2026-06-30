# Current Project State — After B.3

**Date:** 2026-06-29  
**Last commit:** `f233760` (B.3.4 Portal Read-Only)

---

## Phase Status

| Phase | Name | Status |
|---|---|---|
| A | Re-Alignment | ✅ COMPLETED |
| B.1 | Channel Registry Cleanup | ✅ COMPLETED |
| B.2 | Device Model Unification | ✅ COMPLETED |
| B.2.1 | Device Model Reproducibility Gate | ✅ COMPLETED |
| B.2.2 | QA Pipeline Debt Classification | ✅ COMPLETED |
| **B.3** | **Placement** | **✅ COMPLETED** |
| B.3.0 | Design Gate | ✅ |
| B.3.1 | Schema Migration + ORM | ✅ |
| B.3.2 | Service Layer + API | ✅ |
| B.3.3 | Functional Validation | ✅ |
| B.3.3.1 | Regression Delta + Real API | ✅ |
| B.3.4 | Portal Read-Only | ✅ |
| B.3.5 | Closure Gate | ✅ (current) |
| **B.4** | **Channel Orchestrator** | 🔲 NEXT |
| B.5 | Universal Manifest | 🔲 |
| C | Device Gateway | 🔲 |
| D | Inventory & Planning | 🔲 |
| E | KSO Channel | 🔲 |
| F | PoP & Analytics | 🔲 |
| G | Emergency & Ops | 🔲 |
| H | Production Readiness | 🔲 |

---

## Backend Baseline

| Metric | Value |
|---|---|
| Collected | 947 |
| Passed | 881 |
| Failed | 66 (all pre-existing) |
| Collection errors | 0 |
| B.1+B.2 tests | 38/38 |
| Core tests | 73/73 |
| B.3 tests | 65/65 |

## Portal Baseline

| Metric | Value |
|---|---|
| Passed | 863 |
| Failed | 0 |
| Skipped | 32 |
| Errors | 8 (pre-existing, live integration) |

---

## Key Artifacts (B.3)

| Artifact | Location |
|---|---|
| Placement ORM | `channels/models.py` — Placement, PlacementTarget |
| Placement service | `channels/service.py` — 12 functions |
| Placement API | `channels/placements_router.py` + `campaigns/router.py` — 7 endpoints |
| Placement schemas | `channels/schemas.py` — 8 Pydantic models |
| Migration | `alembic/versions/034_add_channel_id_to_placements.py` |
| Seed | `channels/seed.py` — `_seed_placement()` |
| Portal placements block | `campaigns_detail.html` |
| Portal placement detail | `/placements/{id}` + `placement_detail.html` |
| BackendClient | `backend_client.py` — 3 placement methods |

---

## What's Next

**B.4 — Channel Orchestrator Skeleton:**
- `orchestrator/service.py` — manifest assembly
- `orchestrator/simulation.py` — pre-publication simulation
- `orchestrator/contracts.py` — AdapterContract interface
- Mock adapter for tests
