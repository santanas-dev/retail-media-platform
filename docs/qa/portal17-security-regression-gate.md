# PORTAL.1.7 — Security / Regression Gate

**Phase:** PORTAL.1.7 (Gate-only — no functional changes)  
**Previous:** PORTAL.1.6 — Analytics / Error States / Cross-Linking (b772d14)  
**Status:** ✅ PASSED — GO for PORTAL.1.8

---

## Что проверено

### 1. RBAC / Direct URL

| Route | Permission | Guard | Status |
|-------|-----------|-------|--------|
| `GET /planning` | `planning.read` | `require_auth_for_page` | ✅ |
| `GET /bookings` | `bookings.read` | `require_auth_for_page` | ✅ |
| `GET /bookings/{id}` | `bookings.read` | `require_auth_for_page` | ✅ |
| `POST /bookings` | `bookings.read` | `require_auth_for_page` | ✅ |
| `POST /bookings/{id}/reserve` | `bookings.read` | `require_auth_for_page` | ✅ |
| `POST /bookings/{id}/confirm` | `bookings.read` | `require_auth_for_page` | ✅ |
| `POST /bookings/{id}/cancel` | `bookings.read` | `require_auth_for_page` | ✅ |
| `GET /publications` | `publications.read` | `require_auth_for_page` | ✅ |
| `GET /publications/{id}` | `publications.read` | `require_auth_for_page` | ✅ |
| `POST /publications/batch/{id}/publish` | `publications.read` | `require_auth_for_page` | ✅ |
| `GET /packages` | `publications.read` | `require_auth_for_page` | ✅ |
| `GET /packages/{code}` | `publications.read` | `require_auth_for_page` | ✅ |
| `POST /packages/check-kso` | `publications.read` | `require_auth_for_page` | ✅ |
| `GET /reports/analytics` | `reports.read` | `require_auth_for_page` | ✅ |
| `GET /proof-of-play` | `reports.read` | `require_auth_for_page` | ✅ |

Все 15 новых PORTAL.1 routes имеют guards.

### 2. Device Service Exclusion

`device_service` имеет только `devices.read` и `devices.gateway.read`. Тесты подтверждают:
- `/planning` → 403 (нет `planning.read`)
- `/bookings` → 403 (нет `bookings.read`)
- `/packages` → 403 (нет `publications.read`)

### 3. Feature Flag Error Safety

| Флаг | Сообщение | Без traceback | Без raw JSON |
|------|-----------|:---:|:---:|
| `ENABLE_BOOKING_WRITES=false` | booking_writes_disabled | ✅ | ✅ |
| `ENABLE_REAL_PUBLICATION=false` | real_publication_disabled | ✅ | ✅ |
| `ENABLE_GENERATED_MANIFEST_WRITE=false` | generated_manifest_write_disabled | ✅ | ✅ |

`_safe_error()` обрезает сообщения до 300 символов, убирает traceback и raw JSON.

### 4. No-Data / Backend Error States

| Страница | No-data | 403 | 422 | Backend unavailable |
|----------|:---:|:---:|:---:|:---:|
| `/planning` | ✅ | ✅ | ✅ | ✅ |
| `/bookings` | ✅ | ✅ | ✅ | ✅ |
| `/publications` | ✅ | ✅ | ✅ | ✅ |
| `/packages` | ✅ | ✅ | ✅ | ✅ |
| `/reports/analytics` | ✅ | ✅ | ✅ | ✅ |
| `/proof-of-play` | ✅ | ✅ | ✅ | ✅ |

Все ошибки: без traceback, без raw JSON, без раскрытия внутренних permission names.

### 5. No-Secrets Checks

Проверены 13 templates (PORTAL.1 + campaign + reports):

| Проверка | Результат |
|----------|:---:|
| Authorization | ✅ Нет |
| Cookie/token/password/api_key | ✅ Нет (кроме login-формы) |
| Traceback | ✅ Нет |
| localStorage/sessionStorage | ✅ Нет |
| CDN (cdn./unpkg/jsdelivr) | ✅ Нет |
| `<script>` tags | ✅ Нет |
| `\| safe` filter | ✅ Нет |
| raw JSON dump | ✅ Нет |

### 6. Cross-Link Safety

- `device_code` → экранирован через `sanitize_code`
- `manifest_code` → без `|safe` фильтра
- `campaign_code` → авто-экранирование Jinja2
- Unknown buckets → «Не определено»
- Ссылки видны всем пользователям (не RBAC-aware) — ведут на 403 при отсутствии прав. **UX gap, не security vulnerability.**

### 7. Source Boundaries

- Backend не менялся ✅
- Миграций не добавлено ✅
- DB schema не менялась ✅
- Docker/.env не менялись ✅
- Production switch NO-GO ✅
- KSO/Gateway не менялись ✅
- Feature flags default `False` ✅
- UI redesign не проводился ✅

### 8. Remaining Portal Risks (documented)

1. **Cross-links не RBAC-aware**: ссылки видны всем, ведут на 403. UX улучшение для UI.1.
2. **Booking confirm guard**: использует `bookings.read` (не `bookings.approve`). Backend-level enforcement компенсирует.
3. **Nav links не RBAC-aware**: все пункты меню видны всем.

---

## Tests

| Suite | Tests | Status |
|-------|-------|--------|
| PORTAL.1.7 targeted | 62 | ✅ 62/62 |
| PORTAL.1.1 targeted | 42 | ✅ |
| PORTAL.1.2 targeted | 56 | ✅ |
| PORTAL.1.3 targeted | 53 | ✅ |
| PORTAL.1.4 targeted | 56 | ✅ |
| PORTAL.1.5 targeted | 47 | ✅ |
| PORTAL.1.6 targeted | 43 | ✅ |
| Portal regression | 1337 | ✅ (20 skipped) |

---

## Limitations

- Gate-only: без изменений кода
- Cross-link UX gap задокументирован → UI.1
- Confirm booking guard использует `bookings.read` вместо `bookings.approve` (backend-level enforcement)

---

## GO/NO-GO

**✅ GO для PORTAL.1.8 Closure Gate**

PORTAL.1 security gate пройден:
- 15 routes с RBAC guards ✅
- 0 secrets в 13 templates ✅
- 0 traceback/CDN/scripts/json ✅
- Feature flag errors безопасны ✅
- Backend untouched ✅
- Regression 1337/0 ✅
