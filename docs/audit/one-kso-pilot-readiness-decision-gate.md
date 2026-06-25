# One-KSO Pilot Readiness — Decision Gate

**Date:** 2026-06-25
**Phase:** 38.14 — Post Phase D E2E Dry Run
**Status:** 📋 Decision Gate
**Commit:** TBD

---

## Executive Summary

One-KSO technical dry run (D0–D6) завершён. Полная техническая цепочка доказана
на физической КСО: portal/backend → manifest/media → KSO player render → PoP → backend → portal report.
Технических блокеров для controlled long-run и HW scanner E2E нет.
Production/fleet rollout требует отдельного approval.

---

## 1. Что доказано (D0–D6)

| Phase | Что | Результат | Commit |
|---|---|---|---|
| D0 | Backend readiness | ✅ Health OK, DB connected, seed data valid | — |
| D1 | Sidecar local status | ✅ Config present, secret valid, manifest 731 B, media 108 B | — |
| D2 | Dry-run / preflight | ✅ Profile, geometry, state matrix (130 tests green) | — |
| D2.1 | Python 3.6 compatibility | ✅ `fromisoformat`→`parse_iso_utc()`, fullscreen profile registered | `1534bc6` |
| D3 | Visual run (768×1024 fullscreen) | ✅ 100% green, click-through confirmed, 13/13 stop criteria | `b080025` |
| D3.1 | Pre-D4 regression triage | ✅ 4917 passed, pre-existing failures documented | `dd64ab7` |
| D4 | PoP upload | ✅ HTTP 200 accepted, FK resolution bug fixed | `8b367eb`, `7146029` |
| D5 | Report verification | ✅ Event visible, all filters pass, forbidden fields clean | `7ad2b7c` |
| D6 | Cleanup & closure | ✅ Temp files removed, PoP event preserved, config intact | `f1613ba` |

### Proven technical chain

```
Portal ──→ Backend ──→ Manifest/Media ──→ KSO Player (768×1024 X11)
                                              │
                                         PoP Event ◄── X11 render
                                              │
                                         Backend Ingest
                                              │
                                         Portal PoP Report
```

Все звенья цепи проверены на физической КСО (192.168.110.223) с реальным PostgreSQL.

---

## 2. Что сохранено

| Артефакт | Место | Статус |
|---|---|---|
| Backend PoP events (2) | PostgreSQL `kso_proof_of_play_events` | ✅ |
| Agent config | `/home/ukm5/kso-agent/config/agent_config.json` | ✅ |
| Device secret | `/home/ukm5/kso-agent/device_secret.dev` | ✅ |
| Current manifest | `/home/ukm5/kso-agent/manifest/current_manifest.json` | ✅ |
| Media cache | `/home/ukm5/kso-agent/media/current/slot-000.png` | ✅ |
| KSO agent root | `/home/ukm5/kso-agent/` | ✅ |
| UKM5 files | `/home/ukm5/` (vendor app) | ✅ не тронуты |
| D3 evidence | `/tmp/d3_evidence/` (КСО, harmless) | ✅ |
| Backend DB | PostgreSQL (Docker) | ✅ |
| Full regression | 4918 passed, 0 core failures | ✅ |

---

## 3. Что осталось (blockers / follow-up)

### Блокирует pilot (REQUIRED перед pilot rollout)

| # | Что | Почему | Severity |
|---|---|---|---|
| 1 | **HW scanner E2E validation** | ⚠️ PLAN CREATED (38.15), validation POSTPONED — scanner unavailable. | 🔴 HIGH |
| 2 | **Controlled long-run** | D3 был 10 секунд. Нужен прогон ≥1 часа с реальным циклом рендера. | 🔴 HIGH |
| 3 | **BackendIntegration test isolation fix** | 9 pre-existing failures блокируют чистый CI baseline для production. | 🟡 MEDIUM |

### Желательно перед production

| # | Что | Почему |
|---|---|---|
| 4 | Production-grade device auth (mTLS / device gateway credentials) | Сейчас PoP ingest TEST_ONLY без аутентификации |
| 5 | KSO `/tmp/d3_evidence/` cleanup | Эстетика — harmless, но мусор |
| 6 | Sidecar daemon systemd service hardening | Сейчас ручной запуск, не systemd |
| 7 | Portal BackendIntegration RBAC fix | 3-layer isolation defect (documented) |

---

## 4. Decision

### One-KSO Technical Dry Run

```
████████████████████████████████████████████████
██              PASSED ✅                    ██
████████████████████████████████████████████████
```

D0–D6 все зелёные. Полная техническая цепочка доказана.
Ни одного secrets/screenshots/tmp/logs в репозитории.
Все stop criteria соблюдены.

### One-KSO Pilot Readiness

```
████████████████████████████████████████████████
██         CONDITIONAL ⚠️                    ██
██   (requires HW scanner E2E + long-run)    ██
████████████████████████████████████████████████
```

Технических блокеров **нет**, но HW scanner E2E и controlled long-run
обязательны перед любым pilot в магазине. Без них — pilot НЕ approved.

### Production / Fleet Rollout

```
████████████████████████████████████████████████
██         NOT APPROVED 🚫                   ██
████████████████████████████████████████████████
```

Не approved. Требуется: production-grade auth, systemd hardening,
fleet management readiness, full CI/CD pipeline.

---

## 5. Разрешено дальше (без отдельного approval)

| Действие | Статус |
|---|---|
| HW scanner E2E validation plan | ✅ разрешено |
| Controlled long-run plan | ✅ разрешено |
| Portal BackendIntegration isolation fix | ✅ разрешено |
| Pilot runbook update | ✅ разрешено |
| Document updates | ✅ разрешено |
| Regression runs | ✅ разрешено |
| New feature development (non-KSO, non-prod) | ✅ разрешено |

---

## 6. Запрещено (без отдельного explicit approval)

| Действие | Почему |
|---|---|
| systemd/autostart sidecar daemon | Требует production hardening |
| Fleet rollout | Не tested at scale |
| Live store pilot | HW scanner не проверен |
| Repeated PoP upload to production backend | D4 был controlled single event |
| Deleting backend PoP evidence | Audit trail |
| УКМ5/Openbox/systemd modification | Vendor system, нельзя трогать |
| X11/Chromium/runner auto-start | Требует controlled long-run first |
| KSO agent root deletion | Конфигурация test KSO preserved |

---

## 7. Regression Baseline

| Suite | Passed | Failed | Notes |
|---|---|---|---|
| Backend | 292 | 0 | Integration scripts excluded |
| Portal-web | 415 | 9 pre-existing | BackendIntegration isolation |
| KSO state adapter | 86 | 0 | |
| KSO player | 2060 | 0 (12 skipped) | |
| KSO sidecar | 1838 | 0 | |
| Infra | 227 | 0 | |
| **Total** | **4918** | **9 pre-existing** | |

---

## 8. Next Steps (рекомендованные)

1. **HW scanner E2E validation** — ⚠️ PLAN CREATED (38.15), POSTPONED until hardware available
2. **Controlled long-run** — 1+ час с реальным циклом рендера на физической КСО (38.16)
3. **BackendIntegration RBAC fix** — 3-layer isolation defect (documented in regression-baseline-notes.md) (38.17)
4. **Pilot runbook update** — добавить D3/D4/D5/D6 процедуры, stop criteria, rollback (38.18)
5. **Production auth hardening** — заменить TEST_ONLY PoP ingest на device gateway auth / mTLS

### 38.15 — HW Scanner E2E Validation Plan (2026-06-25)

See: `docs/audit/hw-scanner-e2e-validation-plan.md`

- **Validation:** NOT EXECUTED ❌
- **Reason:** physical barcode scanner hardware unavailable
- **Pilot blocker:** 🔴 HIGH — remains active
- **Cannot be replaced:** keyboard simulation is NOT equivalent
- **Safe protocol documented:** 4-phase test (S1–S4), 8 stop criteria, safety rules
- **Safe alternatives while blocked:** long-run plan (38.16), BackendIntegration fix (38.17), runbook (38.18)
- **Resumption:** requires `PHASE_SCANNER_E2E_APPROVED` + scanner hardware + operator present

---

*Document created 2026-06-25 as part of 38.14 Pilot Readiness Decision Gate.
All constraints from Phase D E2E dry run respected. No secrets, full URLs,
tokens, barcodes, UKM5 data, or personal information disclosed.*
