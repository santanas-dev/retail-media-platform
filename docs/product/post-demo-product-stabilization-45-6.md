# Post-Demo Product Stabilization — 45.6

## Context

Tag `v0.9.0-rc0-business-demo.6` (commit `e17900e`) — стабильный business demo baseline.
Физическая КСО/scanner/long-run/sidecar sync заблокированы до появления оборудования.
Этап 45.6 — развитие продукта без затрагивания физической КСО.

## Changes

### 1. Help Page (`/help`)
- Новая страница «Как пользоваться» с 8 шагами
- Бизнес-язык, без технических терминов
- Меню: 📖 Как пользоваться

### 2. Creative Detail — Large Preview
- Большой блок предпросмотра с правильным fallback
- Секция «Где используется» — список кампаний
- Секция «Следующий шаг» — контекстный совет

### 3. Campaign Creative Previews
- Thumbnail 40×40 в таблице креативов кампании
- Разрешение и формат в карточке
- Fallback для видео (🎬)

### 4. Publication Batches — Business Names
- Имена кампаний вместо «📢 ?»
- Даты в формате ДД.ММ.ГГГГ ЧЧ:ММ
- Русские статусы

### 5. Date Formatting
- Единый фильтр `fmt_date` для всех шаблонов
- Кампании, креативы, расписание, согласования, публикации

### 6. Approval Dropdowns
- Единый dropdown «Объект согласования» вместо type+code
- Предзагрузка доступных кампаний и пакетов
- Disabled состояние при отсутствии объектов

### 7. Schedule UX
- Dropdown выбора кампании
- Имена кампаний в списке расписаний
- Даты в бизнес-формате

### 8. Action Availability Service
- Модуль `action_availability.py`
- Флаги для: edit, submit, approve, reject, archive, prepare_publication, add_creative
- Maker-checker enforcement
- Интеграция в campaigns_detail

### 9. User/Role Admin Plan
- План в `docs/product/user-role-admin-plan-45-6.md`
- 4 фазы: user CRUD, role management, RLS scope, audit viewer

### 10. Security Hardening Plan
- План в `docs/product/security-hardening-plan-45-6.md`
- Rate limiting, CSRF, cookie flags, session expiry, audit viewer

### 11. QA Gates
- Скрипт `qa_gates.py` — авто-проверка шаблонов и кода
- Double-slash, JS/CDN, broken images, seed/test patterns

## Status

| Check | Result |
|-------|--------|
| `.6` tag | Untouched ✅ |
| Physical KSO | Not touched ✅ |
| Scanner E2E | Not executed ✅ |
| Long-run | Not executed ✅ |
| Sidecar sync | Not executed ✅ |
| UKM5 DB | Not read ✅ |
| Production AV | Not enabled ✅ |
| Maker-checker | Preserved ✅ |
| RBAC/RLS | Preserved ✅ |
| Audit trail | Preserved ✅ |
| JS/CDN/localStorage | 0 ✅ |
| Secrets/leaks | 0 ✅ |
| QA gates | PASS ✅ |

### 45.6.1 — Regression Classification & Demo Cleanup

Portal 3 failures: stale server (restart fixed). Backend 1 error: import path fixed.
Both layers now 0 failures. Demo data cleanup plan ready.
