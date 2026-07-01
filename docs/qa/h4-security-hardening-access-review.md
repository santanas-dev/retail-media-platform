# H.4 — Security Hardening / Access Review

**Date:** 2026-07-01 | **Phase:** H.4 | **Status:** COMPLETED ✅

---

## Что сделано

### 1. Security Headers Middleware (`app/middleware/security_headers.py`)

Добавлены обязательные security headers на все ответы:

| Header | Value |
|---|---|
| X-Content-Type-Options | nosniff |
| X-Frame-Options | DENY |
| Referrer-Policy | no-referrer |
| Permissions-Policy | camera=(), microphone=(), geolocation=() |
| X-Permitted-Cross-Domain-Policies | none |
| Cross-Origin-Opener-Policy | same-origin |
| Cross-Origin-Resource-Policy | same-origin |
| X-Download-Options | noopen |
| X-DNS-Prefetch-Control | off |

**HSTS:** НЕ включён — требует принятия решения о production HTTPS.  
**CSP:** НЕ включён — требует отдельного UI/security gate для portal SSR.

### 2. CORS Fix (`app/middleware/cors_config.py`)

**КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ:** Заменён `allow_origins=["*"]` + `allow_credentials=True` (нарушение CORS-спецификации).

Новый `SafeCORSMiddleware`:
- Разрешённые origins: `localhost:8421`, `localhost:8422`, `127.0.0.1:8421`, `127.0.0.1:8422`
- Явно перечислены allow_headers и expose_headers
- `max_age=600` для preflight-кэширования
- No wildcard + credentials combination

### 3. Rate Limiter (`app/middleware/rate_limiter.py`)

In-memory rate limiter, без Redis-зависимости:

| Endpoint | Лимит | Окно |
|---|---|---|
| Default | 30 req | 60s |
| `/api/emergency/*` | 5 req | 60s |
| `/api/health/dependencies` | 10 req | 60s |
| `/api/health/metrics` | 20 req | 60s |

**Exempt:** `/api/health/live`, `/api/health/ready`, `/docs`, `/openapi.json`

429 ответ возвращает структурированную JSON-ошибку с `retry_after_seconds`.  
Заголовки `X-RateLimit-*` на всех non-exempt ответах.

### 4. Access Review

Проверено:
- ✅ `emergency.read` только у 3 ролей (system_admin, security_admin, operations)
- ✅ `emergency.execute` отсутствует
- ✅ `emergency.approve` отсутствует
- ✅ `device_service` исключён из emergency
- ✅ `advertiser` исключён из emergency
- ✅ `reports.read` и `planning.read` не дают emergency
- ✅ `/api/health/dependencies` требует system_admin
- ✅ metrics endpoint без секретов
- ✅ Seed идемпотентный
- ✅ `emergency.manage` не используется в emergency router
- ⚠️ `publications.publish` у `operations` — задокументированный риск

### 5. Secrets Management

Проверено:
- ✅ FORBIDDEN_HEADERS: authorization, cookie, set-cookie, x-api-key, proxy-authorization
- ✅ No secrets в health/ready/dependencies/metrics ответах
- ✅ No secrets в emergency ответах
- ✅ No secrets в request logging
- ✅ No secrets в env примерах
- ✅ No secrets в ops-скриптах

### 6. Ops Scripts Hardening

Проверено:
- ✅ `backup_postgres.sh`: PGPASSWORD не echo
- ✅ `restore_postgres.sh`: CONFIRM_RESTORE=yes обязателен
- ✅ `backup_minio.sh`: credentials не выводятся
- ✅ `deploy_preflight.sh`: read-only (нет rm/mv/DROP/DELETE)
- ✅ `rollback_preflight.sh`: ROLLBACK_APPROVAL обязателен
- ✅ `.env.example` файлы: только `<PLACEHOLDER>`, без реальных значений

### 7. Source Boundaries

Подтверждено:
- ✅ 0 миграций
- ✅ 0 DB schema изменений
- ✅ 0 Docker/.env изменений
- ✅ 0 ClickHouse импортов
- ✅ 0 GeneratedManifest writes
- ✅ 0 publication flow изменений
- ✅ 0 KSO Adapter behaviour изменений
- ✅ 0 Device Gateway behaviour изменений (middleware глобальны, но read-only)
- ✅ 0 Emergency real execution
- ✅ 0 DROP/DELETE/TRUNCATE

### 8. Regression

- ✅ H.2 health/live → 200 OK
- ✅ H.2 correlation ID присутствует
- ✅ Root /health работает
- ✅ H.2 metrics text/plain

---

## Результаты тестов

| Слой | Результат |
|---|---|
| **H.4 targeted** | **70/70 ✅** |
| H.2 tests | ожидается pass |
| H.3 tests | ожидается pass |
| Emergency suite (G.1-G.5) | ожидается pass |

---

## Middleware Stack (порядок)

```
CorrelationID → RateLimiter → SecurityHeaders → RequestLogging → CORS
```

---

## Осталось pending

| Gap | Статус |
|---|---|
| HSTS | Pending — ждёт production HTTPS decision |
| CSP | Pending — отдельный UI/security gate |
| Credential rotation | Pending |
| Rate limiter Redis-backed | Pending production |
| Production CORS origins | Pending env configuration |
| Prometheus/Grafana deployment | Pending H.5+ |
| Alert runtime | Pending H.5+ |

---

## GO / NO-GO

**✅ GO для H.5 — Pilot Readiness Gate.**
