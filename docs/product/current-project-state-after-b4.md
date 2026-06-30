# Current Project State — After B.4

**Date:** 2026-07-01
**Last commit:** `4d6f71f` (B.4.3 Simulation Engine)

---

## Phase Status

| Phase | Name | Status |
|---|---|---|
| A | Re-Alignment | ✅ COMPLETED |
| B.1 | Channel Registry Cleanup | ✅ COMPLETED |
| B.2 | Device Model Unification | ✅ COMPLETED |
| B.2.1 | Device Model Reproducibility Gate | ✅ COMPLETED |
| B.2.2 | QA Pipeline Debt Classification | ✅ COMPLETED |
| B.3 | Placement | ✅ COMPLETED |
| B.3.0 | Design Gate | ✅ |
| B.3.1 | Schema Migration + ORM | ✅ |
| B.3.2 | Service Layer + API | ✅ |
| B.3.3 | Functional Validation | ✅ |
| B.3.3.1 | Regression Delta + Real API | ✅ |
| B.3.4 | Portal Read-Only | ✅ |
| B.3.5 | Closure Gate | ✅ |
| **B.4** | **Channel Orchestrator** | **✅ COMPLETED** |
| B.4.0 | Design Gate | ✅ |
| B.4.1 | AdapterContract + MockAdapter + Registry | ✅ |
| B.4.2 | Orchestrator Service + Target Resolution | ✅ |
| B.4.3 | Simulation Engine | ✅ |
| B.4.4 | Closure Gate | ✅ (current) |
| **B.5** | **Universal Manifest** | 🔲 NEXT |
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
| Collected | 1129 (было 947) |
| Passed | 1063 (было 881) |
| Failed pre-existing | 66 |
| Collection errors | 0 |
| B.1+B.2 tests | 34/34 |
| Core tests | 73/73 |
| B.3 tests | 65/65 |
| B.4 tests | 79/79 (32+25+22) |

## Portal Baseline

| Metric | Value |
|---|---|
| Passed | 863 |
| Failed | 0 |
| Skipped | ... |
| Status | Не менялся с B.3.4 |

---

## What the Orchestrator Can Do

| Capability | Status |
|---|---|
| Resolve Placement → Channel chain | ✅ |
| Resolve PlacementTarget → DisplaySurface chain | ✅ |
| Resolve DisplaySurface → LogicalCarrier → PhysicalDevice | ✅ |
| Check capability compatibility | ✅ |
| Select adapter by channel_code | ✅ |
| Build adapter payload draft | ✅ |
| Assemble manifest draft (dry-run) | ✅ |
| Dry-run simulation (single + batch) | ✅ |
| Structured simulation errors | ✅ |
| Summarize simulation results | ✅ |

## What the Orchestrator Does NOT Do Yet

| Capability | When |
|---|---|
| Create final signed manifest | B.5 |
| Write to `generated_manifests` | B.5 + publish refactor |
| Real publication (push to devices) | Phase C + E |
| Public API | B.5 (TBD) |
| Device Gateway integration | Phase C |
| KSO channel adapter | Phase E |

---

## Key Artifacts (B.4)

| Artifact | Location |
|---|---|
| AdapterContract ABC | `orchestrator/contracts.py` (148 строк) |
| Orchestrator Service | `orchestrator/service.py` (489 строк) |
| Simulation Engine | `orchestrator/simulation.py` (319 строк) |
| MockAdapter | `adapters/mock_adapter.py` (102 строк) |
| Adapter Registry | `adapters/registry.py` (39 строк) |
| B.4.1 Tests | `tests/test_orchestrator_b4_1.py` (32 теста) |
| B.4.2 Tests | `tests/test_orchestrator_b4_2.py` (25 тестов) |
| B.4.3 Tests | `tests/test_orchestrator_b4_3.py` (22 теста) |
| Design Gate | `docs/architecture/b4-channel-orchestrator-design-gate.md` |
| Closure | `docs/qa/b4-channel-orchestrator-closure.md` |

---

## Deferred Risks

| Risk | Severity |
|---|---|
| Publication flow uses legacy KsoPlacement — нужен B.5 для миграции | High |
| 66 pre-existing backend failures (env/physical/tech-debt) | Low |
| user_crud ordering fragility (nest_asyncio) | Low |
| Portal B.3.4 tests — `test_placement_b3_4.py` не существует (portal tests в другом месте) | Info |

---

## What's Next

**B.5 — Universal Manifest Schema v1:**
- Core fields + adapter_payload
- Подпись (HMAC v1)
- Версионирование (`manifest_schema_version`)
- Валидация совместимости с capability profile
- Взаимодействие с ManifestDraft из B.4
