# AUDIT.0 — Full Project Audit

**Date:** 2026-07-02 | **Phase:** AUDIT.0 | **Owner:** Architect

---

## Executive Summary

Проект Retail Media Platform / DOOH прошёл через 8 фаз (A→H) и подготовительные PILOT-этапы. Формально все фазы закрыты, backend collection — 2458 тестов / 0 ошибок. Однако **реальное состояние проекта не соответствует формальной готовности**:

- **Backend:** мощный (28 доменов, 24 роутера), но значительная часть функционала — **read-only, dry-run, или deferred**
- **Portal:** 27 страниц, но UI требует полной переработки, многие workflow отсутствуют
- **KSO:** физический тест ни разу не проводился
- **Production readiness:** инструменты созданы, но не развёрнуты
- **Pilot:** заблокирован на этапе evidence collection

**Ключевая проблема:** проект ушёл в production readiness track до завершения базового функционала backend + portal + e2e-теста на 1 КСО.

---

## 1. Backend Audit Summary

### 1.1 Domain Inventory

| # | Domain | Router | Service | Models | Status |
|---|---|---|---|---|---|
| 1 | identity | ✅ | ✅ | ✅ | READY |
| 2 | organization | ✅ | ✅ | ✅ | READY |
| 3 | channels | ✅ | ✅ | ✅ | READY |
| 4 | advertisers | ✅ | ✅ | ✅ | READY |
| 5 | media | ✅ | ✅ | ✅ | READY (AV: NoScanner in dev) |
| 6 | campaigns | ✅ | ✅ | ✅ | READY |
| 7 | scheduling | ✅ | ✅ | — | PARTIAL |
| 8 | inventory | ✅ | ✅ | ✅ | PARTIAL (read-only) |
| 9 | planning | ✅ | ✅ | ✅ | READ_ONLY (5 endpoints) |
| 10 | publications | ✅ | ✅ | ✅ | DRY_RUN (no real publish) |
| 11 | manifests | ✅ | ✅ | ✅ | DRY_RUN (no real Generation) |
| 12 | device_gateway | ✅ | ✅ | ✅ | READY |
| 13 | device_operations | ✅ | ✅ | — | READY |
| 14 | device_dashboard | ✅ | ✅ | — | READY |
| 15 | proof_of_play | ✅ | ✅ | ✅ | READY |
| 16 | analytics | ✅ | ✅ | ✅ | READ_ONLY (4 endpoints) |
| 17 | campaign_reports | ✅ | ✅ | ✅ | READ_ONLY |
| 18 | reports | ✅ | ✅ | — | READ_ONLY (CSV export) |
| 19 | emergency | ✅ | ✅ | ✅ | DRY_RUN only |
| 20 | health | ✅ | ✅ | ✅ | READY (H.2) |
| 21 | approvals | ✅ | ✅ | — | READY |
| 22 | hierarchy | ✅ | ✅ | — | READY |
| 23 | airtime | ✅ | ✅ | — | READY |
| 24 | test_kso_readiness | ✅ | ✅ | — | READY (dev only) |
| 25 | adapters | — | ✅ | — | DRY_RUN (KSO adapter) |
| 26 | orchestrator | — | ✅ | — | DRY_RUN |
| 27 | audit | — | ✅ | — | READY |
| 28 | identity/seed | — | ✅ | — | READY (8 roles, 51 permissions) |

### 1.2 Backend Gaps

| Gap | Domain | Severity | Blocks Portal? |
|---|---|---|---|
| Booking/reservation отсутствует | planning | HIGH | Да — нельзя бронировать |
| Publication: только dry-run | publications | CRITICAL | Да — нет реального publish |
| Manifest generation: только preview | manifests | CRITICAL | Да — нет реальных манифестов |
| KSO production switch: NO-GO | adapters | HIGH | Нет (KSO-specific) |
| ClickHouse pipeline: deferred | analytics | MEDIUM | Нет |
| mTLS: deferred | device_gateway | LOW | Нет |
| Emergency: dry-run only | emergency | MEDIUM | Нет (by design) |
| Real AV scanner: not in dev | media | LOW | Нет |

### 1.3 Test Baseline

- Backend collection: **2458 tests / 0 errors**
- Emergency suite: 414/414
- H.2-H.4 targeted: pass

---

## 2. Portal Audit Summary

### 2.1 Page Inventory

| # | Page | Route | RBAC | Method | Status |
|---|---|---|---|---|---|
| 1 | login | /login | public | GET | ✅ |
| 2 | dashboard | /dashboard | campaigns.read | GET | ✅ |
| 3 | campaigns | /campaigns | campaigns.read | GET | ✅ |
| 4 | campaigns/create | /campaigns/create | campaigns.read | GET+POST | ✅ |
| 5 | campaigns/detail | /campaigns/{code} | campaigns.read | GET | ✅ |
| 6 | creatives | /creatives | media.read | GET+POST | ✅ |
| 7 | creatives/detail | /creatives/{code} | media.read | GET | ✅ |
| 8 | creatives/upload | /creatives/upload | media.read | POST | ✅ |
| 9 | creatives/moderation | /creatives/moderation/queue | media.read | GET | ✅ |
| 10 | schedule | /schedule | scheduling.read | GET | PARTIAL |
| 11 | publications | /publications | publications.read | GET | PARTIAL |
| 12 | stores | /stores | organization.read | GET | ✅ |
| 13 | devices | /devices | devices.read | GET | ✅ |
| 14 | device-dashboard | /device-dashboard | devices.gateway.read | GET | ✅ |
| 15 | proof-of-play | /proof-of-play | reports.read | GET | ✅ |
| 16 | reports | /reports | reports.read | GET | PARTIAL |
| 17 | reports/analytics | /reports/analytics | reports.read | GET | ✅ |
| 18 | reports/export | /reports/export/* | reports.read | GET | ✅ |
| 19 | inventory | /inventory | inventory.read | GET | ✅ |
| 20 | approvals | /approvals | campaigns.approve | GET | PARTIAL |
| 21 | readiness | /readiness | devices.gateway.read | GET | ✅ |
| 22 | deployment | /deployment | campaigns.read | GET | ✅ |
| 23 | emergency | /emergency | emergency.read | GET | ✅ |
| 24 | admin | /admin | users.read | GET | ✅ |
| 25 | help | /help | public | GET | ✅ |
| 26 | compliance | /compliance | public | GET | ✅ |
| 27 | placement_detail | /placement/{code} | campaigns.read | GET | ✅ |

### 2.2 Portal Gaps

| Gap | Severity | Description |
|---|---|---|
| Planning page: MISSING | HIGH | Backend имеет 5 endpoints, portal — только /inventory |
| Booking workflow: MISSING | HIGH | Нет страницы создания бронирования |
| Publication workflow: PARTIAL | CRITICAL | Только просмотр батчей, нет approval chain |
| Manifest preview page: MISSING | HIGH | Нет страницы предпросмотра манифеста |
| Campaign assembly UX: BASIC | MEDIUM | Формы работают, но без подсказок/подтверждений |
| UI/UX design: POOR | HIGH | Базовый CSS, нет дизайн-системы, нет визуальной иерархии |
| Navigation completeness: PARTIAL | MEDIUM | 27 страниц, но нет cross-linking между сущностями |
| Error handling: BASIC | MEDIUM | Технические сообщения, не user-friendly |
| Russian labels: PARTIAL | LOW | Присутствуют, но смешаны с техническими терминами |

---

## 3. KSO Readiness

| Check | Status |
|---|---|
| KSO device available (192.168.110.223) | 🟡 Hardware exists |
| Physical playback test | 🔴 NEVER EXECUTED |
| Chromium kiosk test | 🔴 NEVER EXECUTED |
| Screen resolution verified (768×1024) | 🔴 NOT VERIFIED |
| Manifest delivery to KSO | 🔴 NEVER TESTED |
| PoP from physical KSO | 🔴 NEVER TESTED |
| Rollback to legacy tested | 🔴 NEVER TESTED |
| Emergency dry-run on KSO scope | 🔴 NEVER TESTED |

**KSO status: ZERO physical testing. Все проверки — только API level.**

---

## 4. Production Readiness

| Component | Status |
|---|---|
| Health endpoints | ✅ Deployed |
| Security headers | ✅ Deployed |
| CORS | ✅ Fixed |
| Rate limiter | ✅ In-memory |
| Backup scripts | ✅ Created (dry-run only) |
| Prometheus configs | ✅ Created (not deployed) |
| Grafana specs | ✅ Created (not deployed) |
| Alert rules | ✅ Created (not loaded) |
| Backup/restore drill | ⬜ Never executed |
| Load testing | ⬜ Never executed |

---

## 5. What Went Right

1. **Backend architecture solid** — 28 доменов, чёткое разделение, 2458 тестов / 0 ошибок
2. **Multichannel core правильный** — универсальная модель (Channel → Device → LogicalCarrier → DisplaySurface)
3. **RBAC/RLS внедрены** — 8 ролей, 51 permission, seed идемпотентный
4. **Security hardening выполнен** — headers, CORS, rate limiter, access review
5. **Observability foundation** — health endpoints, correlation ID, structured logging
6. **Ops tooling** — backup/restore/deploy/rollback scripts

---

## 6. Where Project Went Off-Track

1. **Pilot track before backend/portal completion** — Phase H (production readiness) начата до полного backend+portal+e2e
2. **KSO не протестирован физически** — 0 реальных тестов на устройстве
3. **Portal UI не готов для бизнеса** — базовый CSS, нет workflow, нет дизайн-системы
4. **Publication/manifest — только dry-run** — нельзя опубликовать и доставить реальную рекламу
5. **Booking отсутствует** — нет reservation system
6. **Production tools created but not deployed** — Prometheus/Grafana/alerts только в конфигах
7. **Roadmap deviation** — 46.1 roadmap правильно остановил KSO-специфичную разработку, но добавил production readiness phases до завершения core

---

## 7. Critical Blockers (must resolve before store pilot)

| # | Blocker | Domain |
|---|---|---|
| C1 | Publication: real publish невозможен | publications |
| C2 | Manifest generation: только preview | manifests |
| C3 | Booking/reservation отсутствует | planning |
| C4 | Portal planning workflow отсутствует | portal |
| C5 | Portal publication/manifest workflow отсутствует | portal |
| C6 | KSO physical playback ни разу не тестировался | kso |
| C7 | Portal UI/UX не готов для бизнеса | portal |

---

## 8. Recommended Corrected Roadmap

```
AUDIT.0 ✅ Full project audit (this document)

── Backend debt closure ──
BACKEND.1  Publication: enable real publish (feature flag)
BACKEND.2  Manifest: enable real generation (feature flag)  
BACKEND.3  Booking/reservation system

── Portal completion ──
PORTAL.0   Portal completeness audit (gap analysis vs backend API)
PORTAL.1   Portal functional completion (missing pages/workflows)
PORTAL.2   Portal workflow (approval chain, status transitions, error handling)

── UI redesign ──
UI.0       Design gate — design system, component library, style guide
UI.1       Design system implementation
UI.2       Page-by-page redesign (dashboard → campaigns → creatives → ...)

── End-to-end validation ──
E2E.0      Full scenario test WITHOUT physical KSO (API + portal only)
E2E.1      Scenario fixes

── KSO testing ──
KSO.0      1 test KSO readiness (device profile, network, Chromium kiosk)
KSO.1      1 test KSO execution (playback, PoP, heartbeat, rollback, emergency)

── Pilot gate ──
PILOT.GO   Store pilot decision gate (only after ALL above complete)
PILOT.1    Store pilot (1 store, 1-5 devices, limited window)
```

---

## 9. Immediate Freeze Recommendation

**Заморозить:**
- 🚫 Все pilot actions (B1-B6)
- 🚫 Production readiness deployment (Prometheus/Grafana — configs есть)
- 🚫 Approval processes (B5/B6)
- 🚫 Evidence collection track
- 🚫 KSO production switch design
- 🚫 ClickHouse pipeline

**Продолжить:**
- ✅ Текущий аудит (AUDIT.0)
- ✅ Backend debt closure (BACKEND.1)
- ✅ Никаких новых pilot/production phases

---

## 10. Decision

| Gate | Decision |
|---|---|
| **Store pilot** | 🚫 **NO-GO** — 7 critical blockers |
| **Production switch** | 🚫 **NO-GO** |
| **Pilot track continuation** | 🚫 **STOP** — freeze until backend+portal+e2e complete |
| **Next phase** | 🟢 **BACKEND.1** — Publication real publish |

---

## ✅ GO для BACKEND.1 — Publication real publish (backend debt closure)
