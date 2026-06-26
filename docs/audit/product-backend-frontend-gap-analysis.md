# Product Backend / Frontend Gap Analysis

**Date:** 2026-06-25
**Phase:** 39.0 — Product Backend / Frontend Gap Analysis
**Status:** 📋 Gap Analysis
**Previous:** 38.17 (backend regression baseline stabilization)

---

## Executive Summary

После завершения Phase D one-KSO E2E dry run (D0–D6) и стабилизации regression baseline
(38.17: 4939 tests all green) проведена полная ревизия backend и frontend состояния проекта.

**Ключевой вывод:** техническая вертикаль KSO (manifest → player → PoP → report) доказана
на физической КСО. Backend domain model покрывает все необходимые сущности. Frontend имеет
backend-driven страницы для большинства операций, но существуют DEMO-заглушки и TEST_ONLY
security gaps, которые необходимо закрыть перед pilot/production.

**Что блокирует pilot:**
1. 🔴 Device gateway / PoP ingest — TEST_ONLY без аутентификации (security gap)
2. 🟡 Campaign/placement creation — test-kso wrapper'ы (не production API)
3. 🟢 Schedule UI — production backend-driven (✅ 39.2.1)
4. 🟡 Reports UI — DEMO page (slicers disabled, charts placeholder)
5. 🟡 Dashboard — DEMO page (использует demo_data.py)

### Уже исправлено в 39.2:
- ✅ SG7 — Schedule backend (39.1.3)
- ✅ B2 — Schedule UI (39.2.1)
- ✅ Campaign/placement production API (39.1.2)
- ✅ Campaign UI — production backend-driven (39.2.2)

**Что НЕ блокирует pilot:**
- RBAC/RLS enforcement (базовый уровень достаточен для pilot)
- Admin audit log (базовый audit есть)
- Deployment page (статическая справка)
- Excel export (можно отложить)

---

## 1. Current Proven Chain

```
Portal UI ──→ Backend API ──→ Manifest/Media ──→ KSO Player (768×1024 X11)
                  │                                      │
             Test-KSO Seed                          PoP Event ◄── X11 render
                  │                                      │
             Campaign/Placement                     Backend Ingest (TEST_ONLY)
             /Approval/Publication                      │
                  │                                 Portal PoP Report ✅
             Device Gateway (TEST_ONLY)
```

**Доказано на физической КСО (192.168.110.223):**
- D0–D6 все зелёные
- Manifest delivery → player render → PoP → backend → portal report
- Regression: 4939 tests, все suites green
- Git: clean, коммит `2d7c025`

---

## 2. Backend Status Table

### 2.1 Domain Coverage

| # | Домен | Router | Models | Service | Tests | Статус |
|---|---|---|---|---|---|---|
| 1 | Identity (users/roles/perms) | ✅ `/api/users`, `/api/roles`, `/api/permissions`, `/api/auth` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 2 | RBAC middleware | ✅ `require_permission()` | — | ✅ | ✅ | **PRODUCTION-READY** |
| 3 | Hierarchy (branches/clusters/stores) | ✅ `/api/branches`, `/api/clusters`, `/api/stores` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 4 | Device operations (KSO registry) | ✅ `/api/devices/kso` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 5 | Creatives (upload/validation) | ✅ `/api/creatives` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 6 | Campaigns | ✅ `/api/campaigns` (test-kso wrapper) | ✅ | ✅ | ✅ | 🟡 **TEST-KSO WRAPPER** |
| 7 | Placements | ✅ `/api/placements` (test-kso wrapper) | ✅ | ✅ | ✅ | 🟡 **TEST-KSO WRAPPER** |
| 8 | Scheduling | ✅ `/api/schedules` (partial) | ✅ | 🟡 | ✅ | 🟡 **PARTIAL** |
| 9 | Approvals | ✅ `/api/approvals` (simplified) | ✅ | ✅ | ✅ | 🟡 **SIMPLIFIED** |
| 10 | Manifests | ✅ `/api/manifests` | ✅ | ✅ | 13 | **PRODUCTION-READY** |
| 11 | Publications | ✅ `/api/publications` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 12 | Device gateway | ✅ `/api/device-gateway/kso/...` | ✅ | ✅ | ✅ | 🔴 **TEST_ONLY** |
| 13 | PoP ingest | ✅ `/api/device-gateway/kso/{code}/pop` | ✅ | ✅ | 28 | 🔴 **TEST_ONLY** |
| 14 | PoP reporting | ✅ `/api/proof-of-play/test-kso` | ✅ | ✅ | ✅ | 🟡 **TEST-KSO PATH** |
| 15 | Campaign reports | ✅ `/api/campaign-reports` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 16 | Test KSO readiness | ✅ `/api/test-kso/readiness`, `/api/test-kso/seed` | ✅ | ✅ | ✅ | 🟡 **TEST-KSO ONLY** |
| 17 | RLS scopes | 🟡 model exists | ✅ | 🟡 partial | 🟡 | 🟡 **PARTIAL** |
| 18 | Admin audit | ✅ `/api/admin/audit` | 🟡 basic | ✅ | 🟡 | 🟡 **BASIC** |
| 19 | Advertisers | ✅ `/api/advertisers` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 20 | Inventory | ✅ `/api/inventory` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 21 | Channels | ✅ `/api/channels` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 22 | Organization | ✅ `/api/organization` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |
| 23 | Media | ✅ `/api/media` | ✅ | ✅ | ✅ | **PRODUCTION-READY** |

### 2.2 Security Gaps (Backend)

| # | Gap | Severity | Локация | Fix |
|---|---|---|---|---|
| SG1 | PoP ingest без аутентификации | 🔴 HIGH → ✅ FIXED (39.1.1) | `proof_of_play/router.py` | Device JWT auth added |
| SG2 | Manifest delivery (KSO path) без аутентификации | 🔴 HIGH → ✅ FIXED (39.1.1) | `device_gateway/router.py` | Device JWT auth added |
| SG3 | Media delivery без аутентификации | 🔴 HIGH | `device_gateway/router.py` | Already protected ✅ |
| SG4 | Test KSO readiness без аутентификации | 🟡 MEDIUM | `test_kso_readiness/router.py` | TEST-KSO only (explicit) |
| SG5 | Campaign/placement через test-kso wrapper | 🟡 MEDIUM → ✅ FIXED (39.1.2) | `campaigns/router.py`, `scheduling/router.py` | Production API added |
| SG6 | RLS enforcement частичный | 🟡 MEDIUM | `identity/rls.py` | Полный query-level RLS (future) |
| SG7 | Schedule backend API | 🟡 MEDIUM → ✅ FIXED (39.1.3) | `scheduling/` | Schedule + ScheduleSlot API |
| SG8 | In-memory portal session store | 🟡 LOW | `portal-web/portal_session.py` | Redis/persistent session (future) |
| SG9 | Portal session secret hardcoded default | 🟡 LOW | `portal-web/main.py:49` | Env-only, no default (future) |

---

## 3. Frontend Status Table

### 3.1 Portal Pages

| # | Route | Название | Данные | Формы | Статус |
|---|---|---|---|---|---|
| 1 | `/` | Dashboard | **DEMO** (demo_data.py) | — | 🔴 **DEMO STUB** |
| 2 | `/dashboard` | Dashboard | **DEMO** (то же что /) | — | 🔴 **DEMO STUB** |
| 3 | `/login` | Login | Backend-driven | ✅ Login form active | ✅ **DONE** |
| 4 | `/logout` | Logout | Backend-driven | ✅ | ✅ **DONE** |
| 5 | `/stores` | Stores | Backend-driven (branches+clusters+stores+kso) | — | ✅ **DONE** |
| 6 | `/devices` | Devices | Backend-driven (stores+kso) | — | ✅ **DONE** |
| 7 | `/creatives` | Creatives | Backend-driven (list) | ✅ Upload form active | ✅ **DONE** |
| 8 | `/campaigns` | Campaigns | Backend-driven (list) | ✅ Create form (test-kso) | 🟡 **TEST-KSO** |
| 9 | `/schedule` | Schedule | **DEMO** (placeholders) | 🔴 DEMO form, stub POST | 🔴 **DEMO STUB** |
| 10 | `/publications` | Publications | Backend-driven (list) | ✅ Generate + Publish | ✅ **DONE** |
| 11 | `/approvals` | Approvals | Backend-driven (list) | ✅ Request + Decide | ✅ **DONE** |
| 12 | `/proof-of-play` | PoP Reports | Backend-driven (list_pop_events) | ✅ Filters active | ✅ **DONE** |
| 13 | `/reports` | Reports | **DEMO** (demo_data.py) | 🔴 Slicers disabled, charts placeholder | 🔴 **DEMO STUB** |
| 14 | `/readiness` | Readiness | Backend-driven (get_test_kso_readiness) | — | ✅ **DONE** |
| 15 | `/admin` | Admin | Backend-driven (users+roles+perms+audit) | ✅ CRUD + RLS forms | ✅ **DONE** |
| 16 | `/deployment` | Deployment | Static page | — | 🟡 **STATIC** |

### 3.2 Frontend Gaps

| # | Gap | Severity | Локация | Fix |
|---|---|---|---|---|
| FG1 | Dashboard — DEMO данные | 🟡 MEDIUM | `main.py:/` | Backend-driven KPI + real data |
| FG2 | Schedule — DEMO form | 🔴 HIGH | `main.py:/schedule` | Backend API + real form |
| FG3 | Reports — DEMO page | 🟡 MEDIUM | `main.py:/reports` | Backend-driven reports + active slicers |
| FG4 | Campaign create — test-kso wrapper | 🟡 MEDIUM | `main.py:/campaigns/create` | Production campaign CRUD |
| FG5 | Excel export — disabled | 🟢 LOW | `main.py:/reports` | RLS-aware export (deferred) |
| FG6 | SSO button — disabled | 🟢 LOW | `main.py:/login` | Future SSO/AD integration |
| FG7 | Creative upload — no progress/preview | 🟢 LOW | `templates/pages/creatives.html` | UX improvement |
| FG8 | No KSO sidecar status in portal | 🟡 MEDIUM | `main.py:/devices` | Sidecar heartbeat status |
| FG9 | Deployment — статическая справка | 🟢 LOW | `main.py:/deployment` | Можно оставить как справку |

---

## 4. Security / RBAC / RLS Gaps

### 4.1 Authentication & Authorization

| Компонент | Статус | Gap |
|---|---|---|
| Portal login (local) | ✅ Backend-driven JWT | — |
| Portal session (httpOnly cookie) | ✅ 1h max_age, same_site=lax | Secret from env for prod |
| Portal page guards | ✅ `require_auth_for_page()` | — |
| Backend RBAC middleware | ✅ `require_permission()` | 47 permissions, 8 roles |
| Device gateway auth | 🔴 TEST_ONLY (no auth) | Нужен device credential token |
| PoP ingest auth | 🔴 TEST_ONLY (no auth) | Нужен device credential token |
| SSO / AD integration | 🔴 Не реализован | Deferred (post-pilot) |
| MFA | 🔴 Не реализован | Deferred (post-pilot) |

### 4.2 RLS (Row-Level Security)

| Компонент | Статус | Gap |
|---|---|---|
| RLS scope model | ✅ `user_rls_scopes` таблица | — |
| RLS scope assignment UI | ✅ Portal admin page | — |
| RLS enforcement (query-level) | 🟡 Частичный | Не все query paths фильтруют по RLS |
| PoP reporting RLS | 🟡 TEST-KSO path | Нет RLS на `/api/proof-of-play/test-kso` |
| Campaign reporting RLS | ✅ `campaign_reports` | RLS applied |

### 4.3 Audit

| Компонент | Статус | Gap |
|---|---|---|
| Admin audit events | 🟡 Basic | `admin_audit_events` table, basic logging |
| Login audit events | 🟡 Basic | `login_audit_events` table |
| PoP ingest audit | ❌ None | Нет аудита PoP ingestion |
| Manifest access audit | ❌ None | Нет аудита device gateway access |

---

## 5. Reporting Gaps

| # | Gap | Severity | Fix |
|---|---|---|---|
| RG1 | Reports page (/reports) — DEMO | 🟡 MEDIUM | Backend-driven с активными slicers |
| RG2 | Chart placeholders (3 шт) | 🟢 LOW | Реальные графики (deferred) |
| RG3 | Excel export disabled | 🟢 LOW | RLS-aware export (deferred) |
| RG4 | No drill-down в PoP reports | 🟢 LOW | Детализация по времени/КСО |
| RG5 | Campaign reports KPI только базовые | 🟢 LOW | Расширенные метрики |

---

## 6. Device / Sidecar Readiness Gaps

| # | Gap | Severity | Fix |
|---|---|---|---|
| DR1 | Sidecar status не виден в portal | 🟡 MEDIUM | Heartbeat status на devices page |
| DR2 | Media cache status не виден | 🟡 MEDIUM | Cache ready/dirty status |
| DR3 | KSO config status только в /readiness | 🟢 LOW | Показ на devices page |
| DR4 | Device gateway health check отсутствует | 🟡 MEDIUM | `/api/device-gateway/health` или ping |

---

## 7. Pilot Blockers

### 🔴 HIGH — блокирует pilot

| # | Blocker | Компонент | Fix complexity |
|---|---|---|---|
| B1 | Device gateway auth (manifest/media/PoP) | Backend | 3-5 шагов |
| B2 | Schedule UI — DEMO form | Frontend | ✅ FIXED (39.2.1) |
| B3 | HW scanner E2E validation | KSO physical | POSTPONED (scanner unavailable) |
| B4 | Controlled long-run (≥1 час) | KSO physical | PLAN NEEDED (38.16) |

### 🟡 MEDIUM — желательно перед pilot

| # | Blocker | Компонент | Fix complexity |
|---|---|---|---|
| B5 | Campaign/placement production API | Backend | 🟡 MEDIUM → ✅ FIXED (39.1.2) |
| B6 | Dashboard — real data | Frontend | 2-3 шага |
| B7 | Reports — backend-driven | Frontend | 3-5 шагов |
| B8 | Sidecar status in portal | Frontend | 2-3 шага |
| B9 | RLS enforcement (full) | Backend | 3-5 шагов (future) |

### 🟢 LOW — можно отложить

| # | Item | Компонент |
|---|---|---|
| B10 | Excel export | Frontend |
| B11 | SSO / AD integration | Backend |
| B12 | MFA | Backend |
| B13 | Device gateway health endpoint | Backend |
| B14 | Audit hardening | Backend |
| B15 | In-memory session → persistent | Frontend |
| B16 | Deployment page | Frontend |

---

## 8. Release Plan Proposal

### Phase 39.1 — Backend API Hardening
**Goal:** Закрыть TEST_ONLY security gaps для device gateway и PoP.

- Device credential auth (token-based) на manifest/media/PoP endpoints
- Production campaign/placement CRUD (замена test-kso wrapper)
- Campaign→placement→schedule→approval→publication workflow hardening
- Schedule backend API completion
- Campaign reports RLS hardening

**Estimate:** 5-7 шагов

### Phase 39.2 — Portal Campaign/Creative/Placement UI Completion
**Goal:** Убрать DEMO-заглушки, подключить все формы к backend.

- Schedule page: backend-driven (✅ 39.2.1 — list + create + slots + archive)
- Campaign UI: production form (не test-kso)
- Dashboard: реальные KPI из backend campaign_reports
- Creative list: backend-driven (уже ✅)
- Creative upload: улучшить UX (preview, progress)

**Estimate:** 5-7 шагов

### Phase 39.3 — Approval/Publication Workflow Hardening
**Goal:** Production-grade approval workflow.

- Multi-step approval (maker→checker→publisher)
- Publication scheduling (отложенная публикация)
- Manifest version history в portal
- Publication rollback

**Estimate:** 3-5 шагов

### Phase 39.4 — Device/Readiness/Sidecar Dashboard
**Goal:** Операторский dashboard для мониторинга КСО.

- Sidecar heartbeat status на devices page
- Media cache status
- KSO config status (из /readiness)
- Device gateway health endpoint
- Fleet overview (все КСО одним взглядом)

**Estimate:** 3-5 шагов

### Phase 39.5 — PoP Reporting Improvements
**Goal:** Полноценная отчётность.

- Reports page: backend-driven (замена DEMO)
- Активные slicers (время, КСО, кампания, креатив)
- Time-series графики (deferred: сначала текстовые отчёты)
- Drill-down: КСО → кампания → креатив → события

**Estimate:** 3-5 шагов

### Phase 39.6 — RBAC/RLS/Admin Hardening
**Goal:** Production-grade access control.

- Full query-level RLS enforcement
- PoP reporting RLS
- Admin audit hardening (device gateway access, PoP ingest)
- Session persistence (in-memory → Redis)

**Estimate:** 3-5 шагов

### Phase 39.7 — Pilot Runbook and Operator Workflow
**Goal:** Готовность к pilot rollout.

- Pilot runbook update (включить D3/D4/D5/D6 процедуры)
- Operator training workflow
- Incident response playbook
- Deployment automation hardening

**Estimate:** 2-3 шага

---

## 9. Test Commands (Regression)

```
python3 -m unittest discover -s backend/tests -v          # 292/292 OK
python3 -m unittest discover -s apps/portal-web/tests -v   # 424/424 OK
PYTHONPATH=apps/kso_state_adapter python3 -m unittest discover -s apps/kso_state_adapter/tests -v  # 86/86 OK
PYTHONPATH=apps/kso_player python3 -m unittest discover -s apps/kso_player/tests -v  # 2072/2072 OK (12 skipped)
PYTHONPATH=apps/kso_sidecar_agent:apps/kso_player python3 -m unittest discover -s apps/kso_sidecar_agent/tests -v  # 1838/1838 OK
python3 -m unittest discover -s infra/kso-linux/tests -v   # 227/227 OK
```

---

## 10. Summary Statistics

| Категория | ✅ Done | 🟡 Partial | 🔴 Gap |
|---|---|---|---|
| Backend domains | 16 | 4 | 3 (security) |
| Frontend pages | 10 | 3 | 3 (DEMO stubs) |
| Security gates | 3 | 2 | 3 (device auth) |
| Reporting | 1 | 1 | 1 (DEMO page) |
| Pilot blockers | — | 5 | 4 |

**Total gaps identified:** 29
**Pilot blockers (HIGH):** 4
**Pre-pilot recommended (MEDIUM):** 5
**Deferred (LOW):** 7
**Production-ready (already):** 13

---

*Document created 2026-06-25 as part of 39.0 Product Backend / Frontend Gap Analysis.
No KSO modifications. No physical tests. No secrets disclosed. Regression green baseline preserved.*
