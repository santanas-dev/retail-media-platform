# H.2 — Observability & Health Checks

**Date:** 2026-07-02 | **Phase:** H (Production Readiness) | **Step:** H.2  
**Status:** ✅ COMPLETED  
**Prerequisite:** H.1 Production Readiness Checklists / Runbooks  

---

## Summary

Добавлена базовая observability: health endpoints (live/ready/dependencies),  
correlation ID middleware, structured request logging, metrics endpoint.

Никаких изменений в DB schema, миграций, Docker/.env, ClickHouse,  
production switch, Gateway/KSO/Emergency behavior.

---

## Health Endpoints

| Метод | Endpoint | Auth | Описание |
|---|---|---|---|
| GET | `/api/health/live` | Public | Liveness — без DB |
| GET | `/api/health/ready` | Public | Readiness — PostgreSQL |
| GET | `/api/health/dependencies` | system_admin | Детальный статус всех зависимостей |
| GET | `/api/health/metrics` | Public | Prometheus-text метрики |

### Dependency Checks

| Зависимость | Live | Ready | Dependencies | Безопасно |
|---|---|---|---|---|
| PostgreSQL | ❌ | ✅ | ✅ | Да — `check_db_connection()` |
| Redis | ❌ | ⚠️ unknown | ⚠️ unknown | Да — timeout 2s, no secrets |
| MinIO | ❌ | ⚠️ unknown | ⚠️ unknown | Да — `ensure_bucket()` |

**Redis/MinIO возвращают `unknown` если не настроены или недоступны.**  
Никакие DSN/credentials/connection_strings не раскрываются.

---

## Correlation ID

- Middleware: `app/middleware/correlation_id.py`
- Header: `X-Correlation-ID`
- Читает: `X-Correlation-ID` → `X-Request-ID` → UUID generation
- Максимальная длина: 128 символов
- Санитизация: удаление `\n`, `\r`, `\0`
- Добавляется в response header
- Сохраняется в `request.state.correlation_id`

---

## Structured Logging

- Middleware: `app/middleware/request_logging.py`
- Формат: JSON → stdout
- Поля: `method`, `path`, `status_code`, `duration_ms`, `correlation_id`
- Опционально: `user_id`, `device_code`
- **НЕ логируется:** body, Authorization, Cookie, Set-Cookie, X-API-Key, tokens
- FORBIDDEN_HEADERS: authorization, cookie, set-cookie, x-api-key, x-auth-token, proxy-authorization

---

## Metrics

- Endpoint: `GET /api/health/metrics`
- Формат: `text/plain; charset=utf-8` (Prometheus exposition)
- Счётчики (in-memory, лёгковесные):
  - `app_requests_total`
  - `app_errors_total`
  - `health_check_total`
- Без зависимостей (нет prometheus_client)
- Без дорогих DB-запросов
- Без secrets

---

## Created Files

| Файл | Описание |
|---|---|
| `app/middleware/__init__.py` | Package init |
| `app/middleware/correlation_id.py` | Correlation ID middleware |
| `app/middleware/request_logging.py` | Structured logging middleware |
| `app/domains/health/__init__.py` | Package init |
| `app/domains/health/schemas.py` | HealthResponse, DependencyStatus |
| `app/domains/health/service.py` | check_postgresql, check_redis, check_minio |
| `app/domains/health/router.py` | live, ready, dependencies, metrics |
| `backend/tests/test_observability_health_h2.py` | 58 tests |

### Modified

| Файл | Изменение |
|---|---|
| `backend/app/main.py` | +2 middleware registrations, +health router |

---

## Security / No-Secrets

- Live/ready endpoints без авторизации
- Dependencies endpoint требует `system_admin`
- Никакие DSN/credentials/host не раскрываются
- No traceback в ответах об ошибках
- No secrets в метриках
- No body/Authorization/Cookie в логах

---

## Boundaries Confirmed

- No migrations ✅
- No DB schema changes ✅
- No Docker/.env changes ✅
- No ClickHouse ✅
- No GeneratedManifest writes ✅
- No publication flow changes ✅
- No KSO Adapter changes ✅
- No Device Gateway mutation ✅
- No Emergency execution added ✅
- No DROP/DELETE/TRUNCATE ✅

---

## Test Results

| Слой | Результат |
|---|---|
| **H.2 targeted** | **58/58** ✅ |
| Emergency suite | 232/232 ✅ |
| Backend collection | **2435 / 0 errors** (2377 + 58) |

---

## Pending (H.3+)

- Prometheus/Grafana deployment
- Alert rules runtime configuration
- Rate limiting
- Credential rotation

---

## GO / NO-GO

### ✅ GO для H.3 — Deployment / Rollback / Backup

### ❌ NO-GO для:
- Production switch
- ClickHouse
- Real emergency execution
- mTLS/signed manifests
