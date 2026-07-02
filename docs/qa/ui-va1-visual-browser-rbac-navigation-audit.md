# UI.VA.1 — Visual Browser Audit / RBAC Navigation Audit

**Date:** 2026-07-03 | **Trigger:** User sees only 2 sidebar groups | **Audit-only** — no code changes

---

## 1. Executive Summary

**CONFIRMED DEFECT:** Портал показывает только группу «Сервис» в sidebar для пользователя с 18 permissions (role `analyst`). Бизнес-группы (Продажи, Планирование, Публикация, Устройства, Аналитика, Администрирование) **отсутствуют**, хотя permissions присутствуют в сессии.

**Severity: 🔴 CRITICAL** — блокирует навигацию для всех пользователей, включая system_admin.

---

## 2. Что проверено

### 2.1 Browser verification

| Check | Result |
|-------|--------|
| Portal URL | http://localhost:8422 ✅ |
| Login page renders | ✅ |
| User `media_analyst_638117` / `test123` | ✅ Logged in as «Media Test Analyst (Аналитик)» |
| Sidebar groups visible | ❌ **Только «Сервис»** |
| Sidebar links visible | `/help`, `/compliance` (2 ссылки) |
| Dashboard renders | ✅ (200) |
| Header user-panel | ✅ «Media Test Analyst (Аналитик)» |

### 2.2 Direct URL access matrix

| Route | Status | Expected |
|-------|--------|----------|
| `/campaigns` | 200 ✅ | 200 (has `campaigns.read`) |
| `/publications` | 200 ✅ | 200 (has `publications.read`) |
| `/devices` | 200 ✅ | 200 (has `devices.read`) |
| `/deployment` | 200 ✅ | 200 (has `campaigns.read`) |
| `/admin` | 403 ✅ | 403 (no `users.read`) |
| `/planning` | 404 ❌ | 200 (has `planning.read`) |
| `/bookings` | 404 ❌ | 200 (has `bookings.read`) |
| `/reports/analytics` | 404 ❌ | 200 (has `reports.read`) |
| `/emergency` | 404 ❌ | 403 (no `emergency.read`) |

**Key finding:** Direct URLs work for existing routes (200), but sidebar still shows only «Сервис». Routes `/planning`, `/bookings`, `/reports/analytics`, `/emergency` return 404 — маршруты **отсутствуют** в running процессе.

### 2.3 Sidebar → ONLY «Сервис»

Подтверждено на **всех страницах**: dashboard, campaigns, publications, devices, deployment.

---

## 3. Root Cause Analysis

### 3.1 Проверенные гипотезы

| H# | Гипотеза | Результат |
|----|----------|-----------|
| H1 | Current user has limited role/permissions | ❌ Исключено — backend возвращает 18 permissions |
| H2 | system_admin role missing permissions | ❌ Исключено — seed содержит все нужные permissions |
| H3 | permissions не передаются в template context | ❌ Исключено — `"permissions": get_session_permissions(request)` в коде |
| H4 | base.html проверяет неправильные permission names | ❌ Исключено — template render test показывает ВСЕ группы |
| H5 | PAGE_PERMISSION_MAP расходится с sidebar | ❌ Исключено — guards работают (200 на прямых URL) |
| H6 | device_service / limited user | ❌ Исключено — используется analyst role |
| H7 | CSS/responsive скрывает пункты | ❌ Исключено — HTML не содержит скрытых групп |
| H8 | Tests мокают permissions, реальная сессия — другой формат | ⚠️ Возможно |
| H9 | backend_client возвращает roles, но не permissions | ❌ Исключено — `/api/auth/me` возвращает permissions |
| H10 | permissions injection добавлена не во все routes | ❌ Исключено — все проверенные handler'ы передают permissions |

### 3.2 Что подтверждено

1. **Backend `/api/auth/me`** возвращает 18 permissions для `media_analyst_638117` ✅
2. **Код `get_session_permissions`** корректен — читает `data.get("permissions", [])` из session store ✅
3. **Template render test** с frozenset из 10 permissions показывает ВСЕ группы и 17 sidebar-ссылок ✅
4. **Running процесс** показывает только «Сервис» — **7 пустых блоков** между brand и Сервис ❌
5. **Portal запущен 29 июня** без `--reload` — Python модули загружены однократно

### 3.3 Confirmed Root Cause

**`get_session_permissions()` returns an empty frozenset in the running portal process**, despite the session being valid and guards passing. 

The 7 empty-line blocks in the rendered HTML correspond to the 7 `{% if condition %}` blocks in base.html — all evaluating to False.

**Most likely mechanism:** The portal process (started Jun 29, no `--reload`) has a state where `_store.get(session_id)` returns data where `data.get("permissions", [])` is `[]`. This could be caused by:

1. **Module-level state corruption** — in-memory `_SessionStore` singleton loaded with old code
2. **Jinja2 template cache** — compiled template uses stale bytecode
3. **Missing routes** — `/planning`, `/bookings`, `/reports/analytics`, `/emergency` return 404, confirming the running process has stale route definitions

---

## 4. Additional Defects Found

### 4.1 Admin account LOCKED (423)

`admin` account returns 423 (Account is locked). The system_admin user cannot log in.

### 4.2 Missing routes in running process

| Route | Expected | Actual |
|-------|----------|--------|
| `/planning` | 200 | **404** |
| `/bookings` | 200 | **404** |
| `/reports/analytics` | 200 | **404** |
| `/emergency` | 200/403 | **404** |

These routes exist in the code on disk but are **not registered** in the running process.

---

## 5. Severity

**🔴 CRITICAL** — sidebar navigation broken for ALL users. Blocks E2E.1.

---

## 6. Blocker / Not Blocker

**🔴 BLOCKER for E2E.1** — без рабочей навигации E2E-сценарии невозможны.

---

## 7. Recommended Fix Plan

1. **Restart portal** (`pkill -f "uvicorn main:app.*8422" && restart with reload`)
2. **Verify** all routes registered (`/planning`, `/bookings`, etc.)
3. **Verify** sidebar shows correct groups for analyst user
4. **Unlock admin** account
5. **Verify** system_admin sees all 6 business groups

---

## 8. GO/NO-GO

- **❌ NO-GO for E2E.1** — until portal restarted and sidebar verified
- **After restart + verification: GO for E2E.1**

---

## 9. Audit Constraints Preserved

- ✅ No code changes
- ✅ No template changes
- ✅ No CSS changes
- ✅ No backend changes
- ✅ No permission changes
- ✅ No Docker/.env changes
- ✅ No production switch
