# Technical Debt Register

**Date:** 2026-07-02 | **Audit:** AUDIT.0

---

## Legend

| Severity | Meaning |
|---|---|
| 🔴 CRITICAL | Blocks store pilot |
| 🟠 HIGH | Blocks portal / 1-KSO test |
| 🟡 MEDIUM | Degrades quality |
| 🟢 LOW | Nice to have |

---

## Backend Functional Debt

| ID | Item | Severity | Blocks |
|---|---|---|---|
| BFD-01 | Publication: real publish not implemented — only dry-run | 🔴 CRITICAL | Store pilot |
| BFD-02 | Manifest generation: only preview mode — no GeneratedManifest writes | 🔴 CRITICAL | Store pilot |
| BFD-03 | Booking/reservation system missing | 🟠 HIGH | Portal planning |
| BFD-04 | KSO production switch not implemented | 🟠 HIGH | KSO real |
| BFD-05 | Planning API: read-only (5 endpoints) — no write capability | 🟡 MEDIUM | Portal |
| BFD-06 | Emergency: dry-run only — no real execution | 🟡 MEDIUM | Production |
| BFD-07 | Analytics API: read-only (4 endpoints) | 🟢 LOW | — |
| BFD-08 | Campaign reports: read-only | 🟢 LOW | — |
| BFD-09 | Media AV scanner: NoScanner in dev | 🟢 LOW | — |

---

## Portal Functional Debt

| ID | Item | Severity | Blocks |
|---|---|---|---|
| PFD-01 | Planning workflow: no page for availability/occupancy/conflict | 🟠 HIGH | 1-KSO test |
| PFD-02 | Booking workflow: no page for reservation | 🟠 HIGH | 1-KSO test |
| PFD-03 | Publication workflow: view-only, no approval chain | 🔴 CRITICAL | Store pilot |
| PFD-04 | Manifest preview page: missing | 🟠 HIGH | 1-KSO test |
| PFD-05 | Campaign assembly: basic forms, no guided workflow | 🟡 MEDIUM | — |
| PFD-06 | Error handling: technical messages, not user-friendly | 🟡 MEDIUM | — |
| PFD-07 | Cross-linking: entities not linked in UI | 🟡 MEDIUM | — |
| PFD-08 | Status transitions: not visible in portal | 🟡 MEDIUM | — |
| PFD-09 | BackendClient methods: 104 methods, portal uses ~40% | 🟡 MEDIUM | — |

---

## Portal UX/UI Debt

| ID | Item | Severity | Blocks |
|---|---|---|---|
| UID-01 | No design system or component library | 🟠 HIGH | Business demo |
| UID-02 | Basic CSS only — no visual hierarchy | 🟠 HIGH | Business demo |
| UID-03 | Technical UUIDs visible to users | 🟡 MEDIUM | Business demo |
| UID-04 | Mixed RU/EN labels and terminology | 🟡 MEDIUM | Business demo |
| UID-05 | No responsive design | 🟡 MEDIUM | — |
| UID-06 | Tables lack filtering/sorting/pagination | 🟡 MEDIUM | — |
| UID-07 | No loading states or progress indicators | 🟢 LOW | — |
| UID-08 | Forms lack validation feedback | 🟡 MEDIUM | — |

---

## KSO / Hardware Debt

| ID | Item | Severity | Blocks |
|---|---|---|---|
| KSO-01 | KSO physical playback test: NEVER executed | 🔴 CRITICAL | Store pilot |
| KSO-02 | Chromium kiosk test: NEVER executed | 🔴 CRITICAL | Store pilot |
| KSO-03 | Screen resolution not verified | 🔴 CRITICAL | Store pilot |
| KSO-04 | Rollback to legacy: NEVER tested on device | 🟠 HIGH | Store pilot |
| KSO-05 | PoP from physical KSO: NEVER tested | 🟠 HIGH | Store pilot |
| KSO-06 | Network connectivity not tested from KSO | 🟠 HIGH | 1-KSO test |

---

## Production Readiness Debt

| ID | Item | Severity | Blocks |
|---|---|---|---|
| PRD-01 | Prometheus not deployed | 🟡 MEDIUM | — |
| PRD-02 | Grafana not deployed | 🟢 LOW | — |
| PRD-03 | Alert rules not loaded | 🟡 MEDIUM | — |
| PRD-04 | Backup/restore drill not executed | 🟠 HIGH | Store pilot |
| PRD-05 | Load testing not executed | 🟡 MEDIUM | — |
| PRD-06 | HTTPS not deployed | 🟡 MEDIUM | — |
| PRD-07 | Credential rotation not automated | 🟡 MEDIUM | — |

---

## Documentation / Roadmap Debt

| ID | Item | Severity | Blocks |
|---|---|---|---|
| DRD-01 | Roadmap mismatch with actual state | 🟠 HIGH | Planning |
| DRD-02 | Pilot track (B1-B6) prematurely started | 🟠 HIGH | Planning |
| DRD-03 | Evidence tracker: 50+ checkpoints, 0 completed | 🟡 MEDIUM | — |
| DRD-04 | Production readiness docs: configs exist, nothing deployed | 🟡 MEDIUM | — |

---

## Summary

| Category | CRITICAL | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| Backend functional | 2 | 2 | 3 | 2 |
| Portal functional | 1 | 3 | 5 | 0 |
| Portal UX/UI | 0 | 2 | 5 | 1 |
| KSO/Hardware | 3 | 3 | 0 | 0 |
| Production readiness | 0 | 1 | 5 | 1 |
| Documentation/roadmap | 0 | 2 | 2 | 0 |
| **TOTAL** | **6** | **13** | **20** | **4** |

---

## Updated after BACKEND.1 (2026-07-03)

Three critical backend debts CLOSED:

| # | Item | Severity | Resolution |
|---|---|---|---|
| TDB-001 | Publication real publish blocked | CRITICAL → RESOLVED | `ENABLE_REAL_PUBLICATION` (BACKEND.1.1) |
| TDB-002 | GeneratedManifest not created | CRITICAL → RESOLVED | Bridge function, `ENABLE_GENERATED_MANIFEST_WRITE` (BACKEND.1.2) |
| TDB-003 | Booking write API unguarded | HIGH → RESOLVED | `ENABLE_BOOKING_WRITES`, 6 endpoints (BACKEND.1.3) |

Remaining: 3 CRITICAL, 10 HIGH, 20 MEDIUM, 4 LOW after BACKEND.1.

---

## Updated after PORTAL.1 (2026-07-03)

Portal functional debt RESOLVED:

| # | Item | Severity | Resolution |
|---|---|---|---|
| PFD-01 | Planning workflow missing | HIGH → RESOLVED | `/planning` — availability/conflicts/occupancy (PORTAL.1.1) |
| PFD-02 | Booking workflow missing | HIGH → RESOLVED | `/bookings` — create/reserve/confirm/cancel (PORTAL.1.2) |
| PFD-03 | Publication workflow partial | CRITICAL → RESOLVED | `/publications/{id}` + publish result (PORTAL.1.3) |
| PFD-04 | Manifest preview missing | HIGH → RESOLVED | `/packages` — list/detail/KSO check (PORTAL.1.4) |
| PFD-05 | Campaign assembly basic | MEDIUM → RESOLVED | 9-step workflow + cross-links (PORTAL.1.5) |
| PFD-06 | Error handling technical | MEDIUM → RESOLVED | `_safe_error()`, no-data states (PORTAL.1.6) |
| PFD-07 | Cross-linking missing | MEDIUM → RESOLVED | analytics/PoP/devices/packages cross-links (PORTAL.1.6) |
| PFD-08 | Status transitions invisible | MEDIUM → RESOLVED | campaign workflow checklist (PORTAL.1.5) |

**Portal functional debt: 0 remaining** (all 8 items resolved).  
Portal UX/UI debt: unchanged — deferred to UI.1.

Updated totals: **3 CRITICAL, 5 HIGH, 12 MEDIUM, 4 LOW** after PORTAL.1.

---

## Updated after UI.1 (2026-07-03)

Portal UX/UI debt RESOLVED or downgraded:

| # | Item | Severity | Resolution |
|---|------|----------|------------|
| UID-01 | No design system or component library | 🟠 HIGH → **RESOLVED** | 60+ CSS custom properties, 11 компонентов (UI.1.1) |
| UID-02 | Basic CSS only — no visual hierarchy | 🟠 HIGH → **RESOLVED** | page-header, section-card, metric-grid, status-badge, crosslinks (UI.1.1–UI.1.6) |
| UID-03 | Technical UUIDs visible to users | 🟡 MEDIUM → **PARTIAL** | Code/short forms где возможно; raw UUIDs остаются где нет бизнес-кода |
| UID-04 | Mixed RU/EN labels and terminology | 🟡 MEDIUM → **RESOLVED** | «Пакеты показа», «Подтверждения показов», «Технический переключатель» (UI.1.3–UI.1.6) |
| UID-05 | No responsive design | 🟡 MEDIUM → **PARTIAL** | Media queries, table overflow safe, sidebar responsive — baseline complete |
| UID-06 | Tables lack filtering/sorting/pagination | 🟡 MEDIUM → **RESOLVED** | Filter-bar, action-bar, data-table component (UI.1.1–UI.1.6) |
| UID-07 | No loading states or progress indicators | 🟢 LOW → **DEFERRED** | Требует JS/async — отложено до post-E2E |
| UID-08 | Forms lack validation feedback | 🟡 MEDIUM → **PARTIAL** | Базовые ошибки отображены; rich validation требует JS |

**Portal UX/UI debt: 0 CRITICAL, 0 HIGH, 3 MEDIUM (PARTIAL), 2 LOW (1 DEFERRED).**

Updated totals: **3 CRITICAL, 5 HIGH, 9 MEDIUM, 3 LOW** after UI.1.
