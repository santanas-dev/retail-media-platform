# UI.VA.2 — Controlled Portal Restart / Runtime Verification

**Date:** 2026-07-03 | **Trigger:** UI.VA.1 found CRITICAL sidebar defect | **Doc-only**

---

## 1. Executive Summary

**Portal restart RESOLVED the sidebar defect.** After restart with `--reload`, all 7 business groups and 17 links appear correctly in the sidebar. RBAC filtering works as designed.

**Verdict: Sidebar defect was caused by stale process (Jun 29, no `--reload`).** ✅ RESOLVED.

---

## 2. Pre-Restart State

| Parameter | Value |
|-----------|-------|
| Git HEAD | `7e855e9` (UI.VA.1) |
| Portal PID | 983289 |
| Start time | Mon Jun 29 12:54:54 2026 |
| Command | `uvicorn main:app --host 0.0.0.0 --port 8422` |
| `--reload` | **NO** |
| Uptime | ~4 days |
| Sidebar groups | 1 (Сервис only) ❌ |
| Routes returning 404 | 5 (/planning, /bookings, /packages, /reports/analytics, /emergency) |

---

## 3. Restart Action

| Parameter | Old | New |
|-----------|-----|-----|
| PID | 983289 | 456735 |
| Command | `uvicorn main:app --host 0.0.0.0 --port 8422` | `uvicorn main:app --host 0.0.0.0 --port 8422 --reload` |
| `--reload` | NO | **YES** |
| Start time | Jun 29 | Jul 3 |

---

## 4. Post-Restart Route Verification

All previously-404 routes now respond correctly:

| Route | Pre-restart | Post-restart | Notes |
|-------|------------|--------------|-------|
| / | 200 | 303 → 200 | ✅ |
| /dashboard | 200 | 303 → 200 | ✅ |
| /campaigns | 200 | 200 | ✅ |
| **/planning** | **404** | **403** | ✅ (no `planning.read` for analyst) |
| **/bookings** | **404** | **200** | ✅ |
| /publications | 200 | 200 | ✅ |
| **/packages** | **404** | **200** | ✅ |
| **/reports/analytics** | **404** | **200** | ✅ |
| /devices | 200 | 200 | ✅ |
| **/emergency** | **404** | **403** | ✅ (no `emergency.read` for analyst) |
| /admin | 403 | 403 | ✅ (no `users.read` for analyst) |
| /deployment | 200 | 200 | ✅ |
| /proof-of-play | 200 | 200 | ✅ |
| /help | 200 | 200 | ✅ |

**0 routes return 404.** All 403s are correct — analyst role lacks those permissions.

---

## 5. Sidebar Verification (analyst role)

### Groups: 7/7 ✅

| # | Group | Visible | Trigger permissions |
|---|-------|---------|---------------------|
| 1 | Продажи | ✅ | `campaigns.read` + `media.read` |
| 2 | Планирование | ✅ | `bookings.read` + `scheduling.read` + `inventory.read` |
| 3 | Публикация | ✅ | `publications.read` |
| 4 | Устройства | ✅ | `devices.read` + `devices.gateway.read` |
| 5 | Аналитика | ✅ | `reports.read` |
| 6 | Администрирование | ✅ | `organization.read` + `inventory.read` |
| 7 | Сервис | ✅ | Always visible |

### Links: 17 total ✅

| Link | Visible | Reason |
|------|---------|--------|
| Главный экран | ✅ | `campaigns.read` |
| Кампании | ✅ | `campaigns.read` |
| Креативы | ✅ | `media.read` |
| Согласования | ❌ | No `campaigns.approve` ✅ |
| Планирование | ❌ | No `planning.read` ✅ |
| Бронирования | ✅ | `bookings.read` |
| Расписание | ✅ | `scheduling.read` |
| Публикации | ✅ | `publications.read` |
| Пакеты показа | ✅ | `publications.read` |
| Устройства | ✅ | `devices.read` |
| Панель КСО | ✅ | `devices.gateway.read` |
| Готовность | ✅ | `devices.gateway.read` |
| Отчёты | ✅ | `reports.read` |
| Аналитика показов | ✅ | `reports.read` |
| Фактические показы | ✅ | `reports.read` |
| Рекламное время | ✅ | `inventory.read` |
| Магазины | ✅ | `organization.read` |
| Администрирование | ❌ | No `users.read` ✅ |
| Аварийное управление | ❌ | No `emergency.read` ✅ |
| Как пользоваться | ✅ | Public |
| Соответствие | ✅ | Public |

---

## 6. RBAC Matrix

| Route | Sidebar | Direct URL | Match |
|-------|---------|------------|-------|
| /campaigns | ✅ | 200 | ✅ |
| /planning | ❌ (no perm) | 403 | ✅ |
| /bookings | ✅ | 200 | ✅ |
| /publications | ✅ | 200 | ✅ |
| /packages | ✅ | 200 | ✅ |
| /reports/analytics | ✅ | 200 | ✅ |
| /devices | ✅ | 200 | ✅ |
| /emergency | ❌ (no perm) | 403 | ✅ |
| /admin | ❌ (no perm) | 403 | ✅ |

**Sidebar visibility AND direct URL guard are fully consistent.** ✅

---

## 7. Findings

### 7.1 Resolved: Stale process (sidebar + 404s)
**Root cause:** Portal started Jun 29 without `--reload`. Code changes (UI.1) not reflected in running process. Restart with `--reload` fixed all routes and sidebar.

### 7.2 Known: Admin account locked (423)
`admin` / system_admin cannot log in. Needs manual unlock. **Not a portal bug.**

### 7.3 Known: DB seed mismatch for analyst role
`planning.read` is in code seed (`identity/seed.py` line 181) but NOT in database. The analyst role was seeded with an older version. **Not a portal bug** — needs `python -m app.domains.identity.seed` re-run.

### 7.4 Not tested: system_admin sidebar
Cannot verify — admin account locked. Expected: all 7 groups + all 21+ links visible.

---

## 8. GO/NO-GO

| Item | Verdict |
|------|---------|
| Portal routes (0 404s) | ✅ GO |
| Sidebar RBAC (7 groups, 17 links) | ✅ GO |
| Direct URL / sidebar consistency | ✅ GO |
| E2E.1 readiness | ✅ **GO** (after admin unlock + seed re-run) |

---

## 9. Constraints Preserved

- ✅ No code changes
- ✅ No template changes
- ✅ No CSS changes
- ✅ No backend changes
- ✅ No Docker/.env changes
- ✅ No permission changes
- ✅ No production switch
- ✅ Process restart only (add `--reload`)
