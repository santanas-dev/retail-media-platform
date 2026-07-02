# Roadmap Reconciliation

**Date:** 2026-07-02 | **Audit:** AUDIT.0

---

## Original Roadmap (46.1)

| Phase | Name | Status |
|---|---|---|
| A | Re-Alignment | ✅ |
| B | Multichannel Core | ✅ |
| C | Device Gateway | ✅ |
| D | Inventory & Planning | ✅ |
| E | KSO Channel | ✅ |
| F | PoP & Analytics | ✅ |
| G | Emergency & Ops | ✅ |
| H | Production Readiness | ✅ (preparation) |

**Assessment:** Фазы A→G были полезны и закрыли архитектурный долг. Phase H была **преждевременной** — начата до завершения базового функционала backend+portal.

---

## Analysis

### Phases that were useful

| Phase | Why useful |
|---|---|
| A — Re-Alignment | Исправил архитектурные отклонения от ТЗ v2.5 |
| B — Multichannel Core | Внедрил универсальную модель каналов |
| C — Device Gateway | Базовый gateway для устройств |
| D — Inventory & Planning | Read-only planning API |
| E — KSO Channel | KSO adapter (dry-run) |
| F — PoP & Analytics | Нормализация PoP, аналитика |
| G — Emergency | Dry-run emergency |

### Phases that went off-track

| Phase | Problem |
|---|---|
| H.0-H.1 | Design gate + runbooks — полезны, но рано |
| H.2 | Health endpoints — полезны |
| H.3 | Ops scripts — полезны |
| H.4 | Security hardening — полезно, но могло подождать |
| H.5 | Pilot readiness gate — преждевременно |
| H.6 | Pilot closure — преждевременно |
| PILOT.0 | Action plan — рано |
| PILOT.B2/B3/B4 | Evidence collection — рано |

### What should have been before Phase H

1. BACKEND.1 — Publication real publish
2. BACKEND.2 — Manifest real generation
3. BACKEND.3 — Booking/reservation
4. PORTAL.1 — Portal planning workflow
5. PORTAL.2 — Portal publication/manifest workflow
6. UI.1-2 — Portal UI redesign
7. E2E.1 — Full scenario test without KSO
8. KSO.1 — 1 test KSO execution

**Вывод:** Phase H (production readiness) должна идти **после** завершения backend+portal+e2e+KSO, а не параллельно с ними.

---

## Corrected Roadmap

```
Фаза BACKEND.1 — Backend Debt Closure
├── BACKEND.1.1  Publication: real publish (feature flag)
├── BACKEND.1.2  Manifest: real generation (feature flag)
└── BACKEND.1.3  Booking/reservation system

Фаза PORTAL.1 — Portal Completion
├── PORTAL.1.1   Portal completeness audit (gap analysis)
├── PORTAL.1.2   Planning workflow (availability/occupancy/conflicts)
├── PORTAL.1.3   Booking workflow (reservation)
├── PORTAL.1.4   Publication/manifest workflow
├── PORTAL.1.5   Campaign assembly UX improvement
└── PORTAL.1.6   Error handling + status visibility

Фаза UI.1 — Portal UI Redesign
├── UI.1.0       Design gate — design system, component library
├── UI.1.1       Design system implementation (styles.css)
├── UI.1.2       Page-by-page redesign
└── UI.1.3       Business demo readiness review

Фаза E2E.1 — End-to-End Validation
├── E2E.1.1      Full scenario test (API + portal, no KSO)
├── E2E.1.2      Scenario fixes
└── E2E.1.3      Regression: backend + portal suites

Фаза KSO.1 — 1 Test KSO
├── KSO.1.1      Device profile verification
├── KSO.1.2      Chromium kiosk setup + test
├── KSO.1.3      Physical playback test (9-phase protocol)
├── KSO.1.4      PoP + heartbeat verification
├── KSO.1.5      Rollback + emergency dry-run test
└── KSO.1.6      Acceptance: 1-KSO test report

Фаза PROD.1 — Production Readiness (after all above)
├── PROD.1.1     Prometheus + Grafana deployment
├── PROD.1.2     Alert rules loading + test
├── PROD.1.3     Backup/restore drill
├── PROD.1.4     Load testing
├── PROD.1.5     HTTPS deployment
└── PROD.1.6     Credential rotation

Фаза PILOT.1 — Store Pilot (only after ALL above)
├── PILOT.1.0    Pilot GO decision gate
├── PILOT.1.1    Pilot list filled + approved
├── PILOT.1.2    Security approval
├── PILOT.1.3    Business approval
└── PILOT.1.4    Store pilot execution (1 store, 1-5 devices)
```

---

## What to Freeze Immediately

- 🚫 All pilot actions (B1-B6 evidence track)
- 🚫 Approval processes (B5/B6)
- 🚫 Prometheus/Grafana deployment (configs exist)
- 🚫 Production readiness docs (h5, h6, pilot0, pilot-b2-b3-b4)
- 🚫 Pilot readiness checklist updates
- 🚫 Evidence tracker updates

## What to Archive

- PILOT track documents in `docs/archive/pilot-track/`
- H.5/H.6 pilot docs in `docs/archive/phase-h-pilot/`

## What to Keep Active

- Backend code (all 28 domains)
- Portal code (27 pages)
- Operations scripts (6 scripts)
- Health endpoints + security headers
- Test suites (2458 tests)

---

## Decision

- **Current 46.1 roadmap:** ✅ Completed (all A→H done)
- **PILOT track:** 🚫 FROZEN
- **New roadmap:** 🟢 BACKEND.1 → PORTAL.1 → UI.1 → E2E.1 → KSO.1 → PROD.1 → PILOT.1
