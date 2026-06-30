# Current Project State — After B.5

**Date:** 2026-07-01
**Last commit:** (ожидание B.5.5 closure)

---

## Phase Status

| Phase | Name | Status |
|---|---|---|
| A | Re-Alignment | ✅ COMPLETED |
| B.1 | Channel Registry Cleanup | ✅ COMPLETED |
| B.2 | Device Model Unification | ✅ COMPLETED |
| B.3 | Placement | ✅ COMPLETED |
| **B.4** | **Channel Orchestrator** | **✅ COMPLETED** |
| **B.5** | **Universal Manifest Schema** | **✅ COMPLETED** |
| B.5.0 | Design Gate | ✅ |
| B.5.1 | Schema Contracts | ✅ |
| B.5.2 | Manifest Builder | ✅ |
| B.5.3 | Validation Layer | ✅ |
| B.5.4 | Legacy Compatibility Analysis | ✅ |
| B.5.5 | Closure Gate | ✅ (current) |
| **C** | **Device Gateway** | 🔲 NEXT |
| D | Inventory & Planning | 🔲 |
| E | KSO Channel | 🔲 |
| F | PoP & Analytics | 🔲 |
| G | Emergency & Ops | 🔲 |
| H | Production Readiness | 🔲 |

---

## Backend Baseline

| Metric | Value |
|---|---|
| Collected | 1244 (было 1129) |
| Passed | 1178 (было 1063) |
| Failed pre-existing | 66 |
| Collection errors | 0 |
| B.1+B.2 tests | 34/34 |
| B.3 tests | 65/65 |
| B.4 tests | 79/79 |
| B.5 tests | 115/115 |

## Portal Baseline

| Metric | Value |
|---|---|
| Passed | 863 |
| Failed | 0 |
| Skipped | unchanged |
| Status | Не менялся с B.3.4 |

---

## What the Universal Manifest Can Do

| Capability | Status |
|---|---|
| UniversalManifestV1 schema (10 Pydantic models) | ✅ |
| Build from OrchestratorContext | ✅ |
| Dry-run preview через Orchestrator | ✅ |
| Required fields validation | ✅ |
| No-secrets scan (11 patterns) | ✅ |
| Campaign proxy detection | ✅ |
| Target validation (multi-target, type, playable) | ✅ |
| Capability compatibility (formats, proof_type) | ✅ |
| Content validation (preview/final) | ✅ |
| Schedule validation (start ≤ end) | ✅ |
| Adapter payload validation | ✅ |
| Preview vs Final validation modes | ✅ |
| Legacy compatibility matrix (30+ полей) | ✅ |
| Import boundaries clean | ✅ |

## What the Universal Manifest Does NOT Do Yet

| Capability | When |
|---|---|
| Final signed manifest | B.6 (Signing) |
| DB writes / generated_manifests | Compatibility gate |
| Real publish | Phase C (Device Gateway) |
| Public API | После schema validation |
| Content/creative integration | Фаза F или enrichment gate |
| Campaign data enrichment | OrchestratorContext enrichment |

---

## Key Artifacts (B.5)

| Artifact | Строк |
|---|---|
| `universal_schema.py` | 666 |
| `universal_builder.py` | 382 |
| `test_universal_manifest_schema_b5_1.py` | 486 |
| `test_universal_manifest_builder_b5_2.py` | 433 |
| `test_universal_manifest_validation_b5_3.py` | 489 |
| `docs/architecture/b5-*-design-gate.md` | 688 |
| `docs/architecture/b5-4-legacy-compatibility-analysis.md` | 427 |
| `docs/qa/b5-*-*.md` (3 files) | 301 |

---

## Coexistence Strategy

```
Production path: KsoPlacement → legacy GeneratedManifest (UNCHANGED)
Preview path:    Placement → Orchestrator → UniversalManifestV1 (in-memory, no DB)
```

---

## Deferred Risks

| Risk | Severity |
|---|---|
| Publication flow uses legacy KsoPlacement | High |
| 66 pre-existing backend failures | Low |
| Content/creative integration pending | Medium |
| Campaign data incomplete в OrchestratorContext | Medium |
| Dual manifest format (legacy + universal) | Low (preview-only) |

---

## What's Next

**C.0 — Device Gateway Design Gate / Pre-C Audit:**
- Device registration flow
- Device auth & heartbeat
- Manifest pull (ETag/304)
- PoP ingestion (batch)
- ClickHouse setup
- Compatibility с UniversalManifestV1 + legacy GeneratedManifest
