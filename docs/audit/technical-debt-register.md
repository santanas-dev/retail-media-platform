# Technical Debt Register — Retail Media Platform / KSO Portal

> **Статус:** 📋 Audit (37.14)
>
> Дата: 2026-06-16
> Ревизия: 1
>
> **Назначение:** Управляемый backlog технического долга. Не план немедленного закрытия — реестр для приоритизации.
>
> **Принцип:** Закрываем только то, что блокирует следующий этап. Остальное — в очередь.

---

## 1. Executive Summary

Проект прошёл 37 шагов foundation и technical validation. Цепочка `creative → campaign → placement → approval → manifest → publish → sidecar/player smoke → PoP ingest → portal view` замкнута на уровне ~3700 тестов. Проект готов к **physical test KSO** при условии, что P0-блокеры (device auth на TEST_ONLY эндпоинтах) будут закрыты до или сразу после получения доступа к железу.

**Выявлено debt items: 36.**

| Приоритет | Количество | Блокирует |
|---|---|---|
| P0 | 3 | Physical test KSO |
| P1 | 9 | Pilot rollout (3–5 КСО) |
| P2 | 11 | Production rollout |
| P3 | 13 | Улучшения / polish |

**Ключевой вывод:** P0-блокеров всего 3, и все они — временные TEST_ONLY endpoint'ы, которые созданы осознанно для technical validation. Их закрытие требует ~1–2 дня работы после появления test KSO.

---

## 2. Что уже готово и не является долгом

| # | Компонент | Основание |
|---|---|---|
| ✅ | Backend health + DB connectivity | `/health` → 200 |
| ✅ | Identity domain (users, roles, permissions) | 47 permissions, 8 ролей, seed |
| ✅ | JWT auth + refresh rotation | Access 15min, refresh 7d |
| ✅ | RBAC middleware на backend | `require_permission()` dependency |
| ✅ | Portal login/logout + session | httpOnly cookie, server-side store |
| ✅ | Portal page guards (RBAC) | `require_auth_for_page()` |
| ✅ | Hierarchy + device registry | 1 branch, 1 cluster, 1 store, 1 KSO |
| ✅ | Creative upload + validation | 1440×1080, PNG/JPEG, 50MB max |
| ✅ | Campaign create (test KSO wrapper) | `POST /api/campaigns/test-kso` |
| ✅ | Placement/schedule (test KSO) | Conflict guard, FK на коды |
| ✅ | Approval (test KSO) | Maker-checker, 1 шаг |
| ✅ | Manifest generation + publish | Safe projection, idempotent |
| ✅ | Device manifest endpoint | `GET /api/device-gateway/kso/{device_code}/manifest` |
| ✅ | Sidecar fetch contract | 1838 тестов PASS |
| ✅ | Player local smoke | 968 тестов PASS |
| ✅ | PoP ingest | `POST /api/device-gateway/kso/{device_code}/pop`, correlation |
| ✅ | Portal PoP view | `/proof-of-play` backend-driven, KPI, фильтры |
| ✅ | KSO Linux deployment artifacts | Bootstrap, preflight, systemd × 3, release builder |
| ✅ | Readiness gate + dry run docs | 37.12, 37.13 |
| ✅ | Forbidden fields enforcement | Все схемы, все тесты |
| ✅ | Regression baseline | ~3700 тестов, все green |

---

## 3. Технический долг P0 — блокирует physical test KSO

### P0-1: TEST_ONLY unauthenticated device manifest endpoint

| Поле | Значение |
|---|---|
| **ID** | P0-1 |
| **Название** | Device manifest endpoint без аутентификации |
| **Описание** | `GET /api/device-gateway/kso/{device_code}/manifest` — открытый, без auth |
| **Где проявляется** | `backend/app/domains/device_gateway/router.py:134-181` |
| **Риск** | Любой знающий device_code может получить manifest. На physical test KSO — низкий (изолированная сеть). На production — критический. |
| **Влияние на test KSO** | Блокирует безопасную установку |
| **Приоритет** | **P0** |
| **Рекомендуемое решение** | Добавить `authenticate_device` перед отдачей manifest (как enterprise-эндпоинты) |
| **Когда закрывать** | До или сразу после получения test KSO |
| **Файлы** | `device_gateway/router.py` |
| **Как проверить** | `curl` без заголовка → 401; с device_secret → 200 |

### P0-2: TEST_ONLY unauthenticated PoP ingest endpoint

| Поле | Значение |
|---|---|
| **ID** | P0-2 |
| **Название** | PoP ingest без аутентификации |
| **Описание** | `POST /api/device-gateway/kso/{device_code}/pop` — открытый, без auth |
| **Где проявляется** | `backend/app/domains/proof_of_play/router.py:26-52` |
| **Риск** | Любой может отправить фальшивые PoP события. |
| **Влияние на test KSO** | Блокирует безопасную установку |
| **Приоритет** | **P0** |
| **Рекомендуемое решение** | Добавить `authenticate_device` перед приёмом PoP (как enterprise `/pop/events`) |
| **Когда закрывать** | До или сразу после получения test KSO |
| **Файлы** | `proof_of_play/router.py` |
| **Как проверить** | `curl -X POST` без заголовка → 401 |

### P0-3: In-memory portal session store

| Поле | Значение |
|---|---|
| **ID** | P0-3 |
| **Название** | DEV-only in-memory `_SessionStore` |
| **Описание** | Сессии хранятся в dict — теряются при перезапуске portal, не масштабируются |
| **Где проявляется** | `apps/portal-web/portal_session.py:63-121` |
| **Риск** | После перезапуска portal все пользователи разлогинены. Для test KSO допустимо, для pilot — нет. |
| **Влияние на test KSO** | Приемлемо (один сервер) |
| **Приоритет** | **P0** (закрыть до pilot rollout) |
| **Рекомендуемое решение** | Redis или SQLite-backed session store |
| **Когда закрывать** | До pilot rollout |
| **Файлы** | `portal_session.py` |
| **Как проверить** | Перезапустить portal → сессия сохранена |

---

## 4. Технический долг P1 — блокирует pilot rollout

### P1-1: Отсутствие production MFA/SSO/AD

| Поле | Значение |
|---|---|
| **ID** | P1-1 |
| **Приоритет** | P1 |
| **Когда закрывать** | Перед pilot rollout (если требуется безопасностью) |

### P1-2: RLS не на всех query-level путях

| Поле | Значение |
|---|---|
| **ID** | P1-2 |
| **Приоритет** | P1 |
| **Когда закрывать** | До pilot rollout |
| **Файлы** | `identity/`, все domain service'ы с list-запросами |

### P1-3: Synthetic technical advertiser/order/brand контекст

| Поле | Значение |
|---|---|
| **ID** | P1-3 |
| **Описание** | `demo_advertiser_technical`, `demo_brand_technical`, `demo_order_technical` — заглушки для test KSO |
| **Где проявляется** | `backend/app/domains/campaigns/service.py:557-559` |
| **Приоритет** | P1 |
| **Когда закрывать** | До pilot rollout (нужны реальные рекламодатели/бренды/заказы) |

### P1-4: Creative upload/approval lifecycle неполный

| Поле | Значение |
|---|---|
| **ID** | P1-4 |
| **Описание** | Креатив загружается, но нет approval workflow (media.approve), нет lifecycle (draft → review → approved → active → archived) |
| **Приоритет** | P1 |
| **Когда закрывать** | До pilot rollout |

### P1-5: Media file delivery/download отсутствует

| Поле | Значение |
|---|---|
| **ID** | P1-5 |
| **Описание** | Есть только metadata/smoke. Реальная доставка media на КСО через MinIO не протестирована |
| **Приоритет** | P1 |
| **Когда закрывать** | До pilot rollout |

### P1-6: Real device credentials / mTLS не настроены

| Поле | Значение |
|---|---|
| **ID** | P1-6 |
| **Описание** | Device secret хранится в `.env` / dev secret store. Нет production credential management, нет mTLS |
| **Приоритет** | P1 |
| **Когда закрывать** | До pilot rollout |

### P1-7: Test KSO campaign/schedule/approval/manifest — временные врапперы

| Поле | Значение |
|---|---|
| **ID** | P1-7 |
| **Описание** | `/campaigns/test-kso`, `/schedule/test-kso`, `/approvals/test-kso`, `/manifests/test-kso` — временные эндпоинты |
| **Приоритет** | P1 |
| **Когда закрывать** | До pilot rollout (объединить с enterprise-эндпоинтами или заменить) |

### P1-8: Portal integration неполный — часть страниц DEMO

| Поле | Значение |
|---|---|
| **ID** | P1-8 |
| **Описание** | `/dashboard`, `/reports` — DEMO данные. Нужны backend-driven |
| **Приоритет** | P1 |
| **Когда закрывать** | До pilot rollout |

### P1-9: Observability / мониторинг отсутствует

| Поле | Значение |
|---|---|
| **ID** | P1-9 |
| **Описание** | Нет structured logging, нет метрик, нет алертов. Только `/health` |
| **Приоритет** | P1 |
| **Когда закрывать** | До pilot rollout |

---

## 5. Технический долг P2 — блокирует production rollout

| ID | Название | Когда закрывать |
|---|---|---|
| P2-1 | Enterprise PoP ↔ test KSO PoP — две параллельные модели | До production |
| P2-2 | GeneratedManifest ↔ enterprise PublicationBatch — два параллельных домена | До production |
| P2-3 | MinIO production hardening (TLS, access policies, lifecycle) | До production |
| P2-4 | Database migrations audit и consolidation (30 миграций) | До production |
| P2-5 | Config management / secrets rotation | До production |
| P2-6 | Horizontal scaling (backend workers > 1) | До production |
| P2-7 | Rate limiting на все публичные эндпоинты | До production |
| P2-8 | Audit trail на все критические операции | До production |
| P2-9 | Backup / disaster recovery процедуры | До production |
| P2-10 | CI/CD pipeline для backend + portal + KSO runtime | До production |
| P2-11 | Cross-test stability в backend (37.10.1 патч) | До production |

---

## 6. Технический долг P3 — улучшения / polish

| ID | Название |
|---|---|
| P3-1 | Power BI-like reports / drill-down |
| P3-2 | Excel export (RLS-aware) |
| P3-3 | Portal UI polish (responsive, accessibility) |
| P3-4 | API documentation (OpenAPI/Swagger) |
| P3-5 | Performance benchmarks |
| P3-6 | Internationalisation / i18n |
| P3-7 | Code coverage метрики |
| P3-8 | Dependency audit / vulnerability scan |
| P3-9 | Docker Compose production profile |
| P3-10 | KSO runtime health dashboard |
| P3-11 | Device fleet management UI |
| P3-12 | Advertiser self-service portal |
| P3-13 | Automated E2E тесты (playwright/selenium) |

---

## 7. Security Debt

| ID | Название | Приоритет |
|---|---|---|
| S-1 | TEST_ONLY unauthenticated manifest endpoint | P0 |
| S-2 | TEST_ONLY unauthenticated PoP endpoint | P0 |
| S-3 | In-memory session store | P0 |
| S-4 | Нет MFA/SSO/AD | P1 |
| S-5 | Нет mTLS на device gateway | P1 |
| S-6 | Device secret management dev-only | P1 |
| S-7 | Нет rate limiting на auth endpoints | P2 |
| S-8 | Нет audit trail на write-операциях | P2 |
| S-9 | Нет secrets rotation механизма | P2 |
| S-10 | CORS allow_origins=["*"] | P2 |

---

## 8. Architecture Debt

| ID | Название | Приоритет |
|---|---|---|
| A-1 | Два параллельных PoP домена (enterprise + KSO bridge) | P2 |
| A-2 | Два параллельных manifest/publication домена | P2 |
| A-3 | test-kso временные врапперы во всех доменах | P1 |
| A-4 | Synthetic технический контекст (advertiser/brand/order) | P1 |
| A-5 | Отсутствие event-driven архитектуры (всё синхронное) | P3 |

---

## 9. Test Debt

| ID | Название | Приоритет |
|---|---|---|
| T-1 | Cross-test ordering dependency (37.10.1) | P2 |
| T-2 | Нет E2E интеграционных тестов (backend + portal + KSO) | P3 |
| T-3 | Нет performance/load тестов | P3 |
| T-4 | Нет chaos/resilience тестов | P3 |

---

## 10. Operational Debt

| ID | Название | Приоритет |
|---|---|---|
| O-1 | Нет structured logging (JSON) | P2 |
| O-2 | Нет метрик (Prometheus) | P2 |
| O-3 | Нет алертов | P2 |
| O-4 | Нет CI/CD пайплайна | P2 |
| O-5 | Нет backup процедур | P2 |
| O-6 | KSO runtime развёртывание только manual | P2 |

---

## 11. Reporting Debt

| ID | Название | Приоритет |
|---|---|---|
| R-1 | Нет Power BI-like reports | P3 |
| R-2 | Нет Excel export | P3 |
| R-3 | Portal `/dashboard` — DEMO | P1 |
| R-4 | Portal `/reports` — DEMO | P1 |

---

## 12. Что нельзя исправлять до physical test KSO

| Запрещено | Причина |
|---|---|
| Менять KSO runtime (player/sidecar/state-adapter) | Нарушит test baseline |
| Добавлять новый функционал | Затянет physical test |
| Закрывать P1/P2/P3 долг | Не блокирует physical test |
| Добавлять миграции | Риск поломать существующую схему |
| Переписывать тесты | Нарушит regression baseline |

---

## 13. Что нужно закрыть до pilot rollout

| # | Что | Приоритет |
|---|---|---|
| 1 | Device auth на TEST_ONLY endpoints (P0-1, P0-2) | P0 |
| 2 | In-memory session → persistent store (P0-3) | P0 |
| 3 | RLS на всех query-level путях (P1-2) | P1 |
| 4 | Реальный advertiser/brand/order контекст (P1-3) | P1 |
| 5 | Creative approval lifecycle (P1-4) | P1 |
| 6 | Media delivery через MinIO (P1-5) | P1 |
| 7 | Production device credentials / mTLS (P1-6) | P1 |
| 8 | Замена test-kso врапперов на enterprise (P1-7) | P1 |
| 9 | Portal dashboard/reports backend-driven (P1-8) | P1 |
| 10 | Observability basics (P1-9) | P1 |

---

## 14. Что можно закрывать после pilot rollout

| # | Что | Приоритет |
|---|---|---|
| 1 | Консолидация enterprise PoP + KSO PoP (A-1) | P2 |
| 2 | Консолидация manifest/publication доменов (A-2) | P2 |
| 3 | Production hardening (TLS, scaling, rate limiting) | P2 |
| 4 | CI/CD, backup, audit trail | P2 |
| 5 | Power BI reports, Excel export | P3 |
| 6 | Performance benchmarks, E2E тесты | P3 |

---

## 15. Рекомендуемый порядок закрытия долга

```
Сейчас (пока нет test KSO):
├── Ничего не менять в коде
├── Поддерживать regression green
└── Готовить конфиги для physical test KSO

Сразу после получения test KSO:
├── P0-1, P0-2: добавить device auth на manifest + PoP endpoints
└── P0-3: persistent session store

После успешной test KSO проверки (перед pilot rollout):
├── P1-1...P1-9: закрыть все P1
├── R-3, R-4: portal dashboard + reports backend-driven
└── O-1...O-3: observability basics

После pilot rollout:
├── P2-*: production hardening
└── P3-*: улучшения по мере необходимости
```

---

## Файлы

- `docs/audit/technical-debt-register.md` — этот документ
- `docs/audit/technical-debt-next-actions.md` — краткий план действий
- `docs/audit/test-kso-end-to-end-readiness-gate.md` — readiness gate
- `docs/audit/test-kso-deployment-dry-run.md` — deployment dry run
- `docs/audit/one-kso-pilot-readiness-plan.md` — общий план
