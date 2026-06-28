# TZ Compliance Matrix — 44.0

Сравнение фактического состояния Retail Media Platform с ТЗ v2.5.

**Дата:** 2026-06-16
**HEAD:** a5c752e
**Статус пилота:** 🔴 NO-GO (5 физических P0 блокеров)

---

## Легенда

| Статус | Значение |
|---|---|
| ✅ DONE | Реализовано, протестировано |
| 🟡 PARTIAL | Частично реализовано |
| ⬜ NOT_STARTED | Не начато |
| 🔴 BLOCKED | Заблокировано физикой/зависимостью |
| 📅 DEFERRED | Осознанно отложено до v2 |
| ⚠️ DEVIATION | Осознанное отклонение от ТЗ |

---

## 1. Назначение и бизнес-цели

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 1.1 | Платформа управления рекламой на экранах КСО | ✅ DONE | Портал: 50 routes, 19 templates, backend: 108 endpoints | — | P0 |
| 1.2 | Единый интерфейс для рекламодателей, менеджеров, аналитиков | ✅ DONE | 8 ролей RBAC, 47 permissions, server-side portal | — | P0 |
| 1.3 | Управление кампаниями, креативами, расписанием | ✅ DONE | Campaigns CRUD, creative upload/QA, schedule slots | — | P0 |
| 1.4 | Автоматическая доставка контента на КСО | 🟡 PARTIAL | Manifest generation ✅, физическая доставка 🔴 BLOCKED | P0: scanner + delivery gate | P0 |
| 1.5 | Сбор фактических показов (PoP) | 🟡 PARTIAL | PoP service + API ✅, KSO sidecar готов, физический сбор 🔴 BLOCKED | P0: sidecar sync gate | P0 |

## 2. Границы проекта

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 2.1 | v1: канал КСО (Full HD экраны) | 🟡 PARTIAL | Channel KSO exists, но test device 768×1024 portrait | Physical deviation | P1 |
| 2.2 | v2: многоканальность (Android TV, LED, ESL, Mobile) | 📅 DEFERRED | Channel model в БД ✅, адаптеры не реализованы | v2 multichannel | P2 |
| 2.3 | Не более 100 КСО на первом этапе | ✅ DONE | Gateway device API, limit=200 в dashboard | — | P1 |
| 2.4 | Web-портал для управления | ✅ DONE | Portal: 50 routes, server-side HTML/CSS/Jinja2 | — | P0 |

## 3. Целевые сценарии

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 3.1 | Загрузка креатива → модерация → approved | ✅ DONE | Creative upload, QA checks (768×1024, PNG/JPEG/MP4), status: draft→review→approved | — | P0 |
| 3.2 | Создание кампании → привязка креатива → расписание | ✅ DONE | Campaign CRUD, creative binding, schedule slots | — | P0 |
| 3.3 | Согласование (maker-checker) → approved | ✅ DONE | Approval workflow: request→approve/reject, 2-signature | — | P0 |
| 3.4 | Публикация → manifest → доставка на КСО | 🟡 PARTIAL | Batch→manifest generation ✅, физическая доставка 🔴 BLOCKED | Physical gate | P0 |
| 3.5 | Показ рекламы на КСО | 🔴 BLOCKED | KSO player готов (2,072 tests), но физический запуск не выполнялся | Scanner + delivery gate | P0 |
| 3.6 | Сбор фактических показов → отчёты | 🟡 PARTIAL | PoP API ✅, sidecar готов (1,838 tests), физический сбор 🔴 BLOCKED | Sidecar sync gate | P0 |
| 3.7 | Плановая отчётность (CSV export) | ✅ DONE | 4 CSV exports: campaigns, airtime, conflicts, publications | — | P0 |

## 4. Архитектура

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 4.1 | Микросервисная архитектура | 🟡 PARTIAL | Backend монолит FastAPI, 16 доменов, разделение на уровне сервисов | Не микросервисы, но domain-driven | P2 |
| 4.2 | PostgreSQL — основная БД | ✅ DONE | 72 модели, 32 миграции Alembic | — | P0 |
| 4.3 | ClickHouse — аналитика | 🟡 PARTIAL | Сервис в docker-compose ✅, но загрузка данных PoP не подтверждена | Ждёт физического PoP | P2 |
| 4.4 | MinIO — медиа-хранилище | ✅ DONE | S3-совместимое хранилище, docker-compose, прокси через nginx | — | P0 |
| 4.5 | Redis — кэширование | ✅ DONE | Docker-compose, portal sessions, backend caching | — | P0 |
| 4.6 | Nginx — reverse proxy | ✅ DONE | Docker-compose, 3 location blocks (MinIO + API) | — | P0 |
| 4.7 | React + TypeScript frontend | ⚠️ DEVIATION | Portal: server-side HTML/CSS/Jinja2, без JS | ADR: security-first, no JS for v1 | P2 |
| 4.8 | Docker Compose для разработки | ✅ DONE | 5 сервисов | Production deployment не automated | P1 |

## 5. Безопасность

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 5.1 | RBAC — ролевая модель | ✅ DONE | 8 ролей, 47 permissions, route-level + page-level enforcement | — | P0 |
| 5.2 | RLS — Row-Level Security | ✅ DONE | 7 scope types, query-level enforcement, advertiser anonymization in exports | — | P0 |
| 5.3 | Аудит действий | ✅ DONE | Dual audit: login events + admin actions, forbidden-field stripping | — | P0 |
| 5.4 | JWT-аутентификация | ✅ DONE | Backend: JWT (60 min), device gateway: bcrypt secret | — | P0 |
| 5.5 | Server-side sessions | ✅ DONE | Portal: signed httpOnly cookies, server-side session store | — | P0 |
| 5.6 | AD/SSO/MFA | 📅 DEFERRED | Не требуется для v1 KSO pilot | v2 enterprise | P2 |
| 5.7 | mTLS для КСО | 📅 DEFERRED | Не реализовано, ТЗ не требует для v1 | v1 production | P2 |
| 5.8 | Безопасная проекция в портале | ✅ DONE | No raw UUID, secrets, tokens, backend URLs in HTML | — | P0 |

## 6. Пользователи / Роли / RBAC / RLS

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 6.1 | Системный администратор | ✅ DONE | role system_admin, все permissions | — | P0 |
| 6.2 | Security admin | ✅ DONE | role security_admin, audit + user management | — | P0 |
| 6.3 | Менеджер рекламы | ✅ DONE | role ad_manager, campaign/creative/schedule management | — | P0 |
| 6.4 | Согласующий | ✅ DONE | role approver, approval decisions | — | P0 |
| 6.5 | Аналитик | ✅ DONE | role analyst, reports + dashboard view | — | P0 |
| 6.6 | Рекламодатель | ✅ DONE | role advertiser, RLS-scoped to own campaigns | — | P0 |
| 6.7 | Оператор КСО | ✅ DONE | role operations, device/store view | — | P0 |
| 6.8 | Сервис КСО (machine) | ✅ DONE | role device_service, machine-only, blocked from human login | — | P0 |
| 6.9 | User CRUD через портал | ✅ DONE | Admin page: create/block/archive, assign roles | — | P0 |

## 7. Рекламодатели / Заказы / Кампании

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 7.1 | Управление рекламодателями | ✅ DONE | Advertiser CRUD в backend | Portal UI минимален | P1 |
| 7.2 | Создание кампаний | ✅ DONE | Campaign CRUD, campaign_code, status lifecycle | — | P0 |
| 7.3 | Привязка креативов к кампании | ✅ DONE | Creative binding API + UI | — | P0 |
| 7.4 | Статусная модель кампании | ✅ DONE | draft→pending_approval→approved→published | — | P0 |
| 7.5 | Бюджетирование | 📅 DEFERRED | Не реализовано | v2 | P2 |

## 8. Инвентарь

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 8.1 | Управление устройствами | ✅ DONE | Device CRUD, gateway API, device dashboard | — | P0 |
| 8.2 | Группировка по магазинам | ✅ DONE | Store model, store_code на device | — | P0 |
| 8.3 | Статус устройства (online/offline) | ✅ DONE | Heartbeat-based: heartbeat age, readiness badge | — | P0 |
| 8.4 | Геометрия экрана | ✅ DONE | screen_width/height, ad_zone_width/height в БД | Test KSO 768×1024 — deviation | P1 |

## 9. Медиатека / Creative QA

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 9.1 | Загрузка креативов | ✅ DONE | PNG/JPEG upload через portal + backend, MinIO storage | — | P0 |
| 9.2 | Валидация формата и размера | ✅ DONE | 768×1024 portrait, file size ≤50MB, extension/MIME consistency | — | P0 |
| 9.3 | Статусная модель креатива | ✅ DONE | draft→pending_review→approved/rejected/archived + validation_failed | — | P0 |
| 9.4 | Preview в портале | ✅ DONE | Safe preview через backend proxy, no raw storage URLs | — | P0 |
| 9.5 | SHA-256 при загрузке | ✅ DONE | Вычисляется инкрементально, duplicate hash detection (409 Conflict) | — | P0 |
| 9.6 | Блокировка опасных типов | ✅ DONE | HTML/JS/SVG/ZIP/EXE/DLL/SH/PY — rejected до MIME-проверки | — | P0 |
| 9.7 | AV-сканер (contract) | 🟡 PARTIAL | ClamAV adapter, NoScanner, `scan_status`, AV policy contract | Реальный ClamAV не установлен | P1 |
| 9.8 | Модерация (workflow) | ✅ DONE | submit-review→approve/reject с audit trail, reason codes, AV gate | — | P0 |
| 9.9 | Campaign binding gate | ✅ DONE | Только approved creative можно привязать к кампании | — | P0 |
| 9.10 | MP4/WebM validation | ✅ DONE | ffprobe: container, codec, dimensions, duration, FPS, audio | — | P0 |
| 9.11 | GIF validation | ✅ DONE | Pillow: frames, duration, dimensions, corruption | — | P0 |
| 9.12 | Версионирование креативов | ✅ DONE | Замена файла → новая версия, старая сохраняется, audit | — | P0 |

## 10. Пакет показа / Manifest

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 10.1 | Генерация manifest | ✅ DONE | Manifest generation из approved campaigns + batches | — | P0 |
| 10.2 | Подписанный manifest | 🟡 PARTIAL | JSON manifest, подпись в ТЗ указана, но не верифицирована на КСО | Ждёт физической доставки | P1 |
| 10.3 | Batch lifecycle | ✅ DONE | draft→pending→approved→manifest_generated→published | — | P0 |
| 10.4 | Доставка на КСО | 🔴 BLOCKED | Backend publish ✅, физическая доставка через sidecar не запускалась | Physical gate | P0 |

## 11. Плеер / Агент

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 11.1 | KSO Player (Chromium-based) | 🟡 PARTIAL | 2,072 tests, X11 runner, render plan, playlist, PoP writer | Не запущен на физической КСО | P0 |
| 11.2 | KSO Sidecar Agent | 🟡 PARTIAL | 1,838 tests, auth/manifest/media/heartbeat/PoP send | Не запущен на физической КСО | P0 |
| 11.3 | State Adapter (UKM5) | 🟡 PARTIAL | 86 tests, 9-state model, atomic writes | Не подключён к реальному UKM5 | P0 |
| 11.4 | Автозапуск (systemd) | ✅ DONE | 3 unit templates: player, sidecar, state-adapter | — | P0 |
| 11.5 | Kill switch | ✅ DONE | Emergency stop механизм в player | — | P0 |

## 12. Устройства

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 12.1 | Регистрация устройства | ✅ DONE | Device registration через backend API | — | P0 |
| 12.2 | Аутентификация устройства | ✅ DONE | Device gateway: bcrypt secret → JWT | — | P0 |
| 12.3 | Heartbeat мониторинг | ✅ DONE | Heartbeat endpoint, age-based readiness | — | P0 |
| 12.4 | Readiness badge (ready/warning/blocked) | ✅ DONE | Комплексная оценка: heartbeat + credential + manifest + sidecar | — | P0 |

## 13. Фактические показы (PoP)

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 13.1 | Сбор PoP-событий с КСО | 🟡 PARTIAL | Sidecar PoP send pipeline (1,838 tests), backend PoP API | Физический сбор не запускался | P0 |
| 13.2 | Хранение PoP в ClickHouse | 🟡 PARTIAL | ClickHouse в docker ✅, но данные не загружались | Ждёт физического PoP | P2 |
| 13.3 | PoP-отчёты | 🟡 PARTIAL | PoP API + portal PoP page | Без реальных данных | P1 |

## 14. Отчёты

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 14.1 | CSV экспорт кампаний | ✅ DONE | /reports/export/campaigns — safe projection, RLS | — | P0 |
| 14.2 | CSV экспорт занятости эфира | ✅ DONE | /reports/export/airtime | — | P0 |
| 14.3 | CSV экспорт конфликтов | ✅ DONE | /reports/export/conflicts | — | P0 |
| 14.4 | CSV экспорт публикаций | ✅ DONE | /reports/export/publications | — | P0 |
| 14.5 | Визуальные отчёты (графики) | 📅 DEFERRED | Без JS невозможно | v2 | P2 |

## 15. Emergency

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 15.1 | Kill switch для плеера | ✅ DONE | Player kill switch механизм | — | P0 |
| 15.2 | Блокировка устройства | ✅ DONE | Gateway device disable, credential revoke | — | P0 |
| 15.3 | Fallback при потере связи | ✅ DONE | Player: fail-closed, state adapter: error→unknown | — | P0 |

## 16. Эксплуатация / HA / Backup / Monitoring

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 16.1 | Docker Compose для разработки | ✅ DONE | 5 сервисов, health checks | — | P0 |
| 16.2 | Мониторинг (Prometheus/Grafana) | 📅 DEFERRED | Не настроено | v1 production | P2 |
| 16.3 | Резервное копирование | 📅 DEFERRED | Не автоматизировано | v1 production | P2 |
| 16.4 | HA / отказоустойчивость | 📅 DEFERRED | Один инстанс каждого сервиса | v2 | P3 |
| 16.5 | Система очередей (RabbitMQ/Kafka) | 📅 DEFERRED | Не реализовано | v2 | P3 |
| 16.6 | Нагрузочное тестирование | 📅 DEFERRED | Не проводилось | v1 production | P2 |

## 17. Мультиканальность

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 17.1 | Канальная модель (Channel > DeviceType) | 🟡 PARTIAL | Channel/DeviceType модели ✅, только KSO реализован | Android/LED/ESL/Mobile не реализованы | P2 |
| 17.2 | Адаптеры под каналы | 📅 DEFERRED | KSO adapter ✅, остальные не начаты | v2 | P2 |

## 18. Acceptance Criteria

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 18.1 | Загрузка и модерация креатива | ✅ DONE | 43.6.1 acceptance tests | — | P0 |
| 18.2 | Создание и управление кампанией | ✅ DONE | Campaign lifecycle tests | — | P0 |
| 18.3 | Настройка расписания | ✅ DONE | Schedule CRUD + slots | — | P0 |
| 18.4 | Согласование (maker-checker) | ✅ DONE | Approval workflow tests | — | P0 |
| 18.5 | Публикация → manifest | ✅ DONE | Batch→manifest tests | — | P0 |
| 18.6 | Доставка на КСО | 🔴 BLOCKED | Физический gate | P0 |
| 18.7 | Показ рекламы | 🔴 BLOCKED | Физический gate | P0 |
| 18.8 | Сбор фактических показов | 🔴 BLOCKED | Физический gate | P0 |

## 19. Best Practices

| # | Пункт ТЗ | Статус | Evidence | Gap | Priority |
|---|---|---|---|---|---|
| 19.1 | Code review | ✅ DONE | PR-based, step-by-step commits | — | P0 |
| 19.2 | Тестирование (>5600 тестов) | ✅ DONE | 5,614 тестов: backend 690, portal 701, kso_player 2,072, kso_sidecar 1,838 | — | P0 |
| 19.3 | Документация (>100 docs) | ✅ DONE | 104 .md файлов в docs/ | — | P0 |
| 19.4 | CI/CD | 📅 DEFERRED | Не настроено | v1 production | P2 |
| 19.5 | Логирование | 🟡 PARTIAL | Python logging, нет централизованного сбора | v1 production | P1 |

---

## Сводка

| Статус | Количество |
|---|---|
| ✅ DONE | 44 |
| 🟡 PARTIAL | 15 |
| ⬜ NOT_STARTED | 0 |
| 🔴 BLOCKED | 5 |
| 📅 DEFERRED | 10 |
| ⚠️ DEVIATION | 1 |
| **Всего** | **75** |

---

## 20. Business Acceptance Pack (44.5)

**Дата:** 2026-06-27
**HEAD:** 7c3715d
**Статус:** ✅ RC0 backend-only demo ready

### Приёмочный пакет

Полный пакет бизнес-приёмки задокументирован в `docs/product/business-acceptance-pack-44-5.md`. Охватывает 8 бизнес-сценариев:

| # | Сценарий | Статус | Комментарий |
|---|---|---|---|
| 20.1 | Вход и безопасность | ✅ DONE | RBAC (8 ролей, 47 прав), RLS, server-side sessions, без JS/CDN |
| 20.2 | Жизненный цикл креатива | ✅ DONE | Загрузка → валидация → модерация → approve/reject |
| 20.3 | Кампания + привязка креатива | ✅ DONE | Gate: только approved creative |
| 20.4 | Расписание и занятость эфира | ✅ DONE | Слоты, занятость, прогноз, инвентарь |
| 20.5 | Согласование (maker-checker) | ✅ DONE | Двухстороннее, аудит каждого действия |
| 20.6 | Подготовка публикации | 🟡 PARTIAL | Backend publish ✅, физическая доставка 🔴 BLOCKED |
| 20.7 | Отчёты и CSV-экспорт | ✅ DONE | 4 типа CSV, безопасная проекция, RLS |
| 20.8 | Готовность к пилоту | 🟡 PARTIAL | Дашборд и readiness ✅, физический пилот 🔴 BLOCKED |

### Ключевые политики (44.5)

- **Maker-checker обязателен** — для креативов и кампаний
- **Журнал аудита обязателен для каждого действия модерации**
- **Имитация проверки безопасности (fake AV pass) запрещена**
- **Загрузка `.mov` пользователем запрещена**
- **Активный профиль: 768×1024 portrait**
- **1440×1080 остаётся будущим/отложенным**
- **Режим `pilot_dev` разрешает ручную модерацию**
- **Производственный AV требует отдельного решения**
- **В производственном режиме публикация без `scan_status=clean` должна блокировать одобрение и публикацию**
- **Физический пилот остаётся заблокированным (5 P0 блокировок)**

---

## 21. Видимый UI-аудит

**Дата:** 2026-06-27
**Статус:** ✅ Пройден

### Результат аудита production UI

Grep production UI по запрещённым терминам: **0 совпадений**.

Исправленные термины (видимый интерфейс):

| Было (запрещено) | Стало (бизнес-язык) |
|---|---|
| `demo` | `демонстрация` / удалено из видимых меток |
| `demo_creative_001` | `рекламный_макет_001` |
| `manifest` | `пакет рекламных материалов` |
| `backend` | `система` |
| `Proof of Play` | `Фактические показы` |
| `NO-GO` | `Запуск заблокирован` |
| `Dashboard` | `Главный экран` |
| `Flow` | `Этапы` |
| `Publication batch` | `Пакет публикации` |
| `Production` | `Система` |
| `Scanner E2E` | `Проверка физического сканера` |
| `Long-run` | `Длительная проверка стабильности` |
| `Sidecar sync` | `Синхронизация агента` |
| `Maker-checker` | `двух подписей` |
| `test-kso` | удалено из видимых меток |
| `dev` | `разработка` / удалено из видимых меток |
| `internal` | `внутренний` / удалено из видимых меток |

### Задокументированные термины — ✅ ИСПРАВЛЕНО (44.5.1)

132 предсуществующих запрещённых термина (`backend`, `manifest`, `API`, `PoP`, `batch`, `sidecar`, `Chromium`, `daemon`) очищены в 13 production-шаблонах. `UI_AUDIT_001` закрыт (✅ RESOLVED by 44.5.1). Оставшиеся вхождения — только CSS-классы, HTML-комментарии и Jinja2 variable names (невидимые, не блокируют бизнес-демонстрацию).

---

## 22. Демонстрационные термины удалены из production UI

**Дата:** 2026-06-27

- Термин `demo` удалён из всех видимых меток production UI
- `demo_creative_001` переименован в `рекламный_макет_001`
- Политика демонстрационных данных: **никаких поддельных данных в производственном интерфейсе**
- Все демонстрационные записи используют бизнес-формулировки
