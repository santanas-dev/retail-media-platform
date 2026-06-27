# UI Business Glossary — 43.7

**Date:** 2026-06-16  
**Baseline:** HEAD (43.7)  
**Purpose:** Define business-facing language for production UI, replacing all technical terms.

---

## Forbidden Technical Terms in Production UI

| Технический термин | Бизнес-замена | Где применяется |
|---|---|---|
| `backend` (видимый пользователю) | «система», «подготовлено в системе» | Все страницы |
| `backend publication` | «Публикация подготовлена в системе» | `/publications`, `/reports` |
| `manifest` | «Пакет показа» | `/publications`, `/reports` |
| `publication batch` | «Пакет публикации» | `/publications`, `/campaigns` |
| `batch` | «Пакет публикации» | Все страницы |
| `PoP` / `Proof of Play` | «Фактические показы» | `/reports`, `/dashboard` |
| `device` (в контексте КСО) | «КСО», «экран КСО» | Все страницы |
| `device_code` | «Код КСО» | Формы, таблицы |
| `approval gate` | «Отдельное разрешение» | `/readiness`, `/publications` |
| `physical delivery` | «Доставка на КСО» | `/publications`, `/readiness` |
| `scanner E2E` | «Проверка физического сканера» | `/readiness`, `/dashboard` |
| `long-run` | «Длительная проверка стабильности» | `/readiness`, `/dashboard` |
| `sidecar sync` | «Синхронизация агента КСО» | `/readiness` |
| `NO-GO` (как статус) | «Запуск заблокирован», «Запуск пока запрещён» | `/dashboard`, `/readiness`, `/publications` |
| `backend-only` | «Только подготовка в системе» | `/publications` |
| `CSV export` | «Выгрузка отчёта» | `/reports` |
| `endpoint` | НЕ показывать | — |
| `API` | НЕ показывать | — |
| `token` (в бизнес-контексте) | «разрешение» | `/readiness` approval tokens |
| `pipeline` | «Процесс», «Этапы» | `/dashboard` |
| `legacy` | «Ранее созданные» | `/publications` |
| `deprecated` | «Созданы до обновления» | `/publications` |
| `internal` | НЕ показывать | — |
| `helper` | НЕ показывать | — |
| `test-kso` / `dev-*` | НЕ показывать | — |
| `sidecar` | «Агент КСО» | `/readiness` |
| `runner` | «Модуль показа» | `/readiness` |
| `gate` (physical gate) | «Этап проверки» | `/readiness` |
| `sync` (sidecar sync) | «Синхронизация» | `/readiness` |
| `state machine` | НЕ показывать | — |
| `service` | НЕ показывать | — |
| `UUID` / raw UUID | НЕ показывать | — |
| `HTML5` (в контексте плеера) | НЕ показывать | — |
| `mTLS` | НЕ показывать | — |
| `Chromium` | «Модуль отображения» | `/readiness` |

---

## Terms Allowed ONLY in docs/audit (NOT in production UI)

- `backend`, `backend URL`, `backend API`
- `test-kso`, `legacy`, `deprecated`
- `sidecar`, `runner`, `X11`, `Chromium`
- `E2E`, `long-run`, `state machine`, `service`
- `UUID`, `token`, `endpoint`, `API`
- `PoP`, `manifest`, `batch`
- `RBAC`, `RLS`, `audit trail`
- `fiscal`, `receipt`, `payment`, `barcode`
- `systemd`, `ssh`, `HTTPS`
- `NO-GO`, `GO`
- `approval gate`, `physical delivery`, `scanner E2E`
- `HTML5`, `mTLS`, `CDN`, `JS`, `localStorage`
- `PostgreSQL`, `MinIO`, `Redis`, `ClickHouse`
- `FastAPI`, `Jinja2`, `SQLAlchemy`
- `docker`, `docker-compose`

---

## Page-Specific Replacements

### Dashboard (`/dashboard`)
| Было | Стало |
|---|---|
| «Dashboard» | «Главный экран» |
| «Platform Summary» | «Сводка платформы» |
| «Advertising Pipeline» | «Процесс рекламной кампании» |
| «Pilot Readiness» | «Готовность к запуску» |
| «Business Next Actions» | «Что делать дальше» |
| «KSO v1» (подзаголовок) | убрать |
| «Pipeline: Креатив → ...» | «Этапы: Креатив → ...» |
| «Пилот: NO-GO» | «Запуск заблокирован» |
| «5 physical blockers» | «5 этапов проверки не пройдены» |
| «Сканер отсутствует — physical gates не запускаются» | «Сканер не подключён — физическая проверка не начата» |
| «Данные: production backend» | «Данные обновляются при каждом запросе» |

### Reports (`/reports`)
| Было | Стало |
|---|---|
| «Плановая отчётность» | ок |
| «Фактические показы (Proof of Play) недоступны» | «Фактические показы появятся после запуска на КСО» |
| «Пилот: NO-GO» | «Запуск заблокирован» |
| «HW scanner E2E не выполнен» | «Проверка физического сканера не пройдена» |
| «Controlled long-run не выполнен» | «Длительная проверка стабильности не пройдена» |
| «Physical KSO delivery gate не approved» | «Доставка на КСО не разрешена» |
| «Плановая занятость эфира» | ок |
| «Конфликты расписания» | ок |
| «Publication Batches» | «Пакеты публикации» |
| «Manifest status» | «Статус пакетов показа» |
| «Proof of Play — события» | «Фактические показы — события» |
| «RLS enforced. Advertiser видит только свои данные» | «Каждый рекламодатель видит только свои данные» |
| «CSV: без secrets, tokens, backend URL» | убрать из production UI (это safety note) |
| «CSV: campaign_code, name, status» | убрать из production UI |

### Publications (`/publications`)
| Было | Стало |
|---|---|
| «Publication batches» | «Пакеты публикации» |
| «Manifest delivery to physical KSO is blocked until approval gate» | «Доставка на КСО заблокирована до получения отдельного разрешения» |
| «Режим backend-only» | «Режим подготовки в системе» |
| «публикация формирует backend manifest без доставки на устройство» | «Пакет показа подготовлен в системе без доставки на КСО» |
| «доставка и sidecar sync отключены до отдельного approval» | «Доставка и синхронизация отключены до отдельного разрешения» |
| «batch в статусе «Черновик»» | «Пакет публикации в статусе «Черновик»» |
| «Generate manifest» | «Сформировать пакет показа» |
| «Publish (backend)» | «Опубликовать в системе» |
| «Backend-only. Физическая доставка заблокирована.» | «Только в системе. Доставка на КСО заблокирована.» |
| «Manifest (legacy)» → «Ранее созданные манифесты» | уже сделано в 43.5 ✅ |
| «Publication Batches» (заголовок) | «Пакеты публикации» |
| «Сводка публикаций» | ок |
| «Manifest» (в сводке) | «Пакеты показа» |
| «draft → pending → approved → manifest → published» | «черновик → на согласовании → одобрен → пакет показа → опубликован» |

### Readiness (`/readiness`)
| Было | Стало |
|---|---|
| «Readiness — Pilot Gate» | «Готовность к запуску» |
| «Готовность устройств» | ок |
| «Что уже готово (backend + портал)» | «Что уже готово» |
| «Сценарий демонстрации (backend-only)» | «Сценарий демонстрации» |
| «Весь сценарий выполняется в backend без физической КСО» | «Сценарий выполняется в системе без КСО» |
| «Manifest формируется, но не доставляется на устройство» | «Пакет показа формируется, но не доставляется на КСО» |
| «Scanner E2E» | «Проверка физического сканера» |
| «48h+ Long-run» | «Длительная проверка стабильности» |
| «Manifest delivery» | «Доставка на КСО» |
| «Sidecar sync» | «Синхронизация агента» |
| «PHASE_SCANNER_E2E_APPROVED» | «Разрешение на проверку сканера» |
| «PHASE_PHYSICAL_DELIVERY_APPROVED» | «Разрешение на доставку» |
| «PHASE_SIDECAR_SYNC_APPROVED» | «Разрешение на синхронизацию» |
| «PHASE_LONG_RUN_APPROVED» | «Разрешение на проверку стабильности» |
| «PHASE_FLEET_ROLLOUT_APPROVED» | «Разрешение на запуск» |
| «Publication batch создан» | «Пакет публикации создан» |
| «Manifest сгенерирован в backend» | «Пакет показа сформирован в системе» |
| «Backend публикация выполнена» | «Публикация в системе выполнена» |

### Creatives (`/creatives`)
| Было | Стало |
|---|---|
| «Креативы» | ок |
| «Рекомендованный формат для КСО: портрет 768×1024» | «Рекомендованный формат: портрет 768×1024» |
| «Загрузить креатив» | ок |
| Все технические safety notes | оставить как есть (внизу страницы, мелким шрифтом) |

### Campaigns (`/campaigns`)
| Было | Стало |
|---|---|
| «Кампании» | ок |
| «Создать кампанию» | ок |
| «Привязать креатив» | ок |
| «Запросить согласование» | ок |
| «Подготовить публикацию» | ок |
| Все safety notes | оставить |

### Approvals (`/approvals`)
| Было | Стало |
|---|---|
| «Согласования» | ок |
| «Maker-Checker» | «Принцип двух подписей» |
| «Пользователь не может согласовать собственный запрос» | ок |
| «approval request» | «Заявка на согласование» |
| «object_type / object_code» | «Тип / Код объекта» |
| «requested_by / decided_by» | «Запросил / Решил» |

### Schedule (`/schedule`)
| Было | Стало |
|---|---|
| «Расписание» | ок |
| «Создать расписание» | ок |
| «Слоты» | ок |
| «Плановая занятость эфира» | ок |
| «Не факт показа PoP» | «Не фактические показы» |
| «Конфликты — warning-only» | «Предупреждения — не блокируют публикацию» |

---

## Login Page

| Было | Стало |
|---|---|
| «KSO v1» (подзаголовок) | убрать |
| «Режим 1 — Локальный» | убрать |
| «Режим 2 — Корпоративный» | убрать |
| «SSO / Active Directory» | убрать |
| «Пользователи заводятся в меню Администрирование» | убрать |
| Технические детали про httpOnly cookie | убрать |
| Кнопка «Войти через SSO (скоро)» | убрать |
| «Способы входа» | убрать |
| «Пароль никогда не сохраняется в браузере» | убрать (или оставить как сноску внизу) |

---

## Общие замены по всем страницам

| Было | Стало |
|---|---|
| «KSO v1» | убрать из header |
| «Retail Media Platform» (заголовок) | оставить |
| «Безопасная проекция: ...» | убрать из видимого UI или свернуть в одну строку внизу |
| «RLS enforced» | убрать |
| «production backend» | «система» |
| «Данные из production API» | «Данные из системы» |
| «No JS/CDN/localStorage» | убрать из UI (это техническое требование) |
| «raw UUID» | убрать из UI |
| «backend URL» | убрать из UI |
| «storage paths» | убрать из UI |
