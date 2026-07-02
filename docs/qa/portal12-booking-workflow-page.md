# PORTAL.1.2 — Booking Workflow Page: QA Gate

**Date:** 2026-07-02
**Phase:** PORTAL.1.2
**Status:** ✅ COMPLETE

---

## Что добавлено

Страница портала для полного Booking Workflow:

### Routes
| Метод | Маршрут | Назначение | RBAC |
|-------|---------|-----------|------|
| GET | `/bookings` | Список бронирований + фильтры + форма создания | `bookings.read` |
| POST | `/bookings` | Создание бронирования | `bookings.read` (portal-level) |
| GET | `/bookings/{id}` | Детали бронирования + элементы + действия | `bookings.read` |
| POST | `/bookings/{id}/reserve` | Зарезервировать | `bookings.read` |
| POST | `/bookings/{id}/confirm` | Подтвердить (backend: `bookings.approve`) | `bookings.read` |
| POST | `/bookings/{id}/cancel` | Отменить с причиной | `bookings.read` |

### Templates
- `apps/portal-web/templates/pages/bookings.html` — список + фильтры + форма создания
- `apps/portal-web/templates/pages/booking_detail.html` — детали + элементы + действия

### BackendClient
Добавлено 9 методов (PORTAL.1.2):
- `list_bookings(access_token, campaign_id, status, date_from, date_to)`
- `get_booking(access_token, booking_id)`
- `create_booking(access_token, payload)`
- `update_booking(access_token, booking_id, payload)`
- `reserve_booking(access_token, booking_id)`
- `confirm_booking(access_token, booking_id)`
- `cancel_booking(access_token, booking_id, reason)`
- `list_booking_items(access_token, booking_id)`
- `update_booking_items(access_token, booking_id, items)`

### CSS
- `.inline-form`, `.action-buttons`, `.btn-sm`, `.btn-primary`, `.btn-success`, `.btn-danger`, `.section-collapse`, `.hint-text`

---

## Используемые backend endpoints

Все через существующий `inventory/router.py`:
- `GET /api/bookings` — список с фильтрами
- `POST /api/bookings` — создание (guarded: `ENABLE_BOOKING_WRITES`)
- `GET /api/bookings/{id}` — детали
- `POST /api/bookings/{id}/reserve` — резерв (guarded)
- `POST /api/bookings/{id}/confirm` — подтверждение (guarded, `bookings.approve`)
- `POST /api/bookings/{id}/cancel` — отмена (guarded)
- `GET /api/bookings/{id}/items` — элементы

**Backend не менялся.**

---

## Блоки страницы

### /bookings (список)
- **A.** Форма создания (campaign_id, date_from, date_to, comment)
- **B.** Фильтры (campaign_id, status, date_from, date_to)
- **C.** Таблица бронирований: ID, кампания, статус, период, дата создания, действия
- **D.** Статус-лейблы с иконками (🟡 draft, 🔵 reserved, 🟢 confirmed, ⚫ cancelled)
- **E.** Flash-сообщения через query params (создано/зарезервировано/подтверждено/отменено)

### /bookings/{id} (детали)
- **A.** Информация: ID, кампания, статус, период, комментарий, created/updated/approved
- **B.** Элементы бронирования: блок, слотов/цикл, тип, период
- **C.** Действия: зарезервировать (draft), подтвердить (draft/reserved), отменить (кроме cancelled)
- **D.** Отмена с причиной
- **E.** Ссылка «← К списку»

---

## Обработка ошибок

- **Feature flag OFF** — backend возвращает 422 `booking_writes_disabled` → `_safe_error()` показывает сообщение
- **Capacity exceeded** — backend validation error → `_safe_error()` обрезает до 300 символов
- **Validation errors** — redirect с flash-сообщением (заполните поля)
- **Backend unavailable** — «Данные бронирований временно недоступны»
- **No data** — «Нет бронирований. Создайте первое бронирование или измените фильтры.»

---

## RBAC

- `/bookings` → `bookings.read` (PAGE_PERMISSION_MAP)
- `require_auth_for_page()` проверяет через session permissions
- device_service denied (нет в rbac map)

---

## Security

- ✅ No secrets в шаблонах
- ✅ No traceback
- ✅ No Authorization/Cookie/token/password/api_key
- ✅ No localStorage
- ✅ No CDN
- ✅ No inline JS
- ✅ _safe_error() truncates backend errors
- ✅ No raw JSON dump

---

## Boundaries

- ✅ No backend API changes
- ✅ No migrations
- ✅ No DB schema changes
- ✅ No Docker/.env changes
- ✅ No publication/publish actions
- ✅ No manifest write actions
- ✅ No production switch
- ✅ No KSO/Gateway changes

---

## Tests

**PORTAL.1.2 targeted:** 56/56 ✅
- Route/RBAC: 11
- BackendClient: 8
- Rendering: 8
- Workflow: 11
- Security: 7
- Boundaries: 8
- Regression: 3

**PORTAL.1.1:** 42/42 ✅
**Portal regression:** 1089 passed / 32 skipped / 8 pre-existing errors ✅

---

## GO/NO-GO

**✅ GO для PORTAL.1.3 — Publication Workflow Page**
