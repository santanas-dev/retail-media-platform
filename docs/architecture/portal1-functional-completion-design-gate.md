# PORTAL.1 — Portal Functional Completion Design Gate

**Date:** 2026-07-03
**Status:** Design Gate
**Previous:** BACKEND.1 — Backend Debt Closure ✅

---

## 1. Executive Summary

BACKEND.1 закрыл три критических backend-долга. Backend готов:
- 2695 тестов, 0 ошибок
- 3 feature flags защищают все write-операции
- E2E backend chain verified
- Security gate passed

**Portal отстаёт.** Функциональный скелет существует (27 страниц, 50+ routes, 110+ BackendClient методов), но 4 ключевых workflow полностью отсутствуют в портале при том что backend их поддерживает.

**Цель PORTAL.1:** добавить недостающие страницы без редизайна, чистым SSR на Jinja2.

---

## 2. Backend Readiness After BACKEND.1

| Capability | Backend | Feature Flag |
|---|---|---|
| Campaign CRUD | ✅ | — |
| Planning (availability/conflict/occupancy) | ✅ read-only | — |
| Booking (create/reserve/confirm/cancel) | ✅ | `ENABLE_BOOKING_WRITES` |
| Publication (batch lifecycle) | ✅ | `ENABLE_REAL_PUBLICATION` |
| GeneratedManifest | ✅ | `ENABLE_GENERATED_MANIFEST_WRITE` |
| Manifest preview | ✅ | — |
| Device dashboard | ✅ | — |
| Analytics | ✅ | — |
| Emergency (dry-run) | ✅ | — |
| Admin/users | ✅ | — |

---

## 3. Current Portal Inventory

### Routes (~50)
| Area | GET | POST | Status |
|---|---|---|---|
| Auth | /login, /logout | /login, /logout | ✅ |
| Dashboard | /, /dashboard | — | ✅ |
| Campaigns | /campaigns, /campaigns/{code}, /campaigns/create | create, edit, archive, submit, bind-creative, create-schedule, create-batch | ✅ 90% |
| Creatives | /creatives, /creatives/{code} | upload, archive, submit, approve, reject | ✅ |
| Schedule | /schedule | create, create-slot, archive | 🟡 60% |
| Placements | /placements/{id} | — | 🟡 50% |
| Publications | /publications | batch actions (approval, generate, publish, cancel) | 🟡 40% |
| Devices | /devices, /device-dashboard | — | ✅ 90% |
| Reports | /reports, /reports/analytics | export | 🟡 60% |
| Inventory | /inventory | — | 🟡 read-only |
| Approvals | /approvals | — | 🟡 read-only |
| Emergency | /emergency | POST dry-run | ✅ 95% |
| Admin | /admin | create-user, assign-roles, block, archive | ✅ 80% |
| **Planning** | ❌ | ❌ | **MISSING** |
| **Bookings** | ❌ | ❌ | **MISSING** |
| **Manifest** | ❌ | ❌ | **MISSING** |

### BackendClient Methods: ~110
~60% уже используются portal-страницами. ~40% не используются — в основном booking, planning, manifest.

---

## 4. Missing Portal Workflows (Priority Order)

| # | Workflow | Backend | Portal | Priority |
|---|---|---|---|---|
| 1 | **Planning** — availability, conflicts, occupancy | ✅ 5 read-only endpoints | ❌ ZERO | CRITICAL |
| 2 | **Booking** — create, reserve, confirm, cancel | ✅ full API behind flag | ❌ ZERO | CRITICAL |
| 3 | **Publication workflow** — status, flag errors, GM details | ✅ PublishBatchResult | 🟡 basic list only | HIGH |
| 4 | **Manifest/KSO preview** — GeneratedManifest list, body preview | ✅ endpoints exist | ❌ ZERO | HIGH |
| 5 | Campaign status/error visibility | ✅ API | 🟡 basic | MEDIUM |
| 6 | Analytics error/no-data states | ✅ API | 🟡 graceful | LOW |

---

## 5. PORTAL.1 Split

```
PORTAL.1.0 ✅ Design Gate (this document)
PORTAL.1.1 — Planning Page (availability + conflicts + occupancy)
PORTAL.1.2 — Booking Workflow Page (create/reserve/confirm/cancel)
PORTAL.1.3 — Publication Workflow Page (batch detail + flag states + GM details)
PORTAL.1.4 — Manifest/KSO Preview Page (GeneratedManifest list + body preview)
PORTAL.1.5 — Campaign Status/Error Improvements
PORTAL.1.6 — Analytics Error/No-Data States
PORTAL.1.7 — Portal Security/Regression Gate
PORTAL.1.8 — Portal Functional Closure Gate → UI.1
```

**Обоснование порядка:**
1. Planning — читает данные, самый безопасный (read-only), даёт немедленную ценность
2. Booking — зависит от planning (validation через те же endpoints), но write-операции под feature flag
3. Publication — зависит от booking (батчи создаются после бронирования)
4. Manifest — зависит от publication (манифесты после publish)

---

## 6. Out of Scope for PORTAL.1

| Item | Why |
|---|---|
| UI redesign | Отдельная фаза UI.1 |
| Frontend framework (React/Vue) | SSR only (Jinja2) |
| CDN/JS/localStorage | Server-side rendering |
| Production switch | NO-GO до всей дорожной карты |
| KSO physical test | Отдельная фаза KSO.1 |
| Store pilot | После PORTAL+UI+E2E+KSO+PROD |
| Backend API changes | Backend заморожен после BACKEND.1 |
| DB schema changes | 0 миграций |
| Docker/.env changes | 0 |

---

## 7. Feature Flag Handling in Portal

| Flag | OFF (default) | Portal behavior |
|---|---|---|
| `ENABLE_BOOKING_WRITES` | `False` | Формы видны, кнопки disabled с пояснением «Функция отключена» |
| `ENABLE_REAL_PUBLICATION` | `False` | Кнопка Publish показывает pending/disabled, 422 → «Публикация отключена feature flag» |
| `ENABLE_GENERATED_MANIFEST_WRITE` | `False` | После публикации показывать `generated_manifest_created=false`, `next_step` |

**Важно:** Портал НЕ проверяет feature flags на своей стороне. Он просто показывает backend-ответы:
- 422 → человекочитаемое сообщение
- PublishBatchResult → generated_manifest_created, next_step

---

## 8. RBAC / Security

| Страница | Требуемая permission | Роли |
|---|---|---|
| /planning | `planning.read` | ad_manager, analyst, operations, system_admin |
| /bookings | `bookings.read` (view), `bookings.manage` (actions) | ad_manager, operations |
| /publications | `publications.read` | ad_manager, operations, system_admin |
| /manifests | `publications.read` | ad_manager, operations |

**Запрещено:** device_service, advertiser (ограничен RLS)

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Planning page требует сложной визуализации | Таблицы + простые индикаторы, без графиков (до UI.1) |
| Booking validation errors сложны для отображения | Показывать backend error как есть, улучшить в UI.1 |
| Feature flag ответы могут быть неожиданными для пользователя | Понятные русские сообщения, не технические детали |
| 110+ BackendClient методов — не все задокументированы | Использовать только проверенные в аудите |

---

## 10. Tests Strategy

Каждый PORTAL.1 шаг добавляет portal-тесты:
- PORTAL.1.1: ~20 tests (page renders, data display, filters)
- PORTAL.1.2: ~25 tests (forms, error states, flag OFF)
- PORTAL.1.3: ~20 tests (batch detail, flag states)
- PORTAL.1.4: ~15 tests (manifest list, body preview)
- PORTAL.1.5: ~10 tests
- PORTAL.1.6: ~10 tests
- PORTAL.1.7: ~25 tests (security regression)
- **Total: ~125 portal tests**

---

## 11. GO/NO-GO

### ✅ GO for PORTAL.1.1 — Planning Page

Backend готов. Planning — read-only, самый безопасный первый шаг. Никаких write-операций. Даёт немедленную ценность: ad_manager видит доступность инвентаря.

### NO-GO for:
- UI redesign (до UI.1)
- Production switch
- Store pilot
- KSO physical test
- Backend API changes
