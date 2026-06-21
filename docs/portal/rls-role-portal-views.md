# Detailed RLS Role-Based Portal Views

> **Статус:** 🔐 Contract. Архитектурный документ.
>
> Последнее обновление: 2026-06-21

## 1. Принцип Auth/RBAC/RLS

Авторизация в портале строится на трёх уровнях:

1. **Auth** — кто пользователь (локальная учётная запись или SSO/AD)
2. **RBAC** — что пользователь может делать (роль → permissions)
3. **RLS** — какие данные пользователь видит (роль → RLS scopes → фильтрация строк)

Критическое правило: **UI hiding is NOT security**. Каждый запрос к backend/API/DB должен проверять permissions и применять RLS-фильтры независимо от того, что показано в UI. Ручной вызов URL или API не должен обходить ограничения.

## 2. Роли портала

| Роль | ID | Зона ответственности |
|---|---|---|
| Системный администратор | `system_admin` | Полный доступ, без RLS |
| Администратор безопасности | `security_admin` | Пользователи, роли, аудит |
| Менеджер рекламы | `ad_manager` | Кампании, креативы, публикация |
| Согласующий | `approver` | Проверка и согласование |
| Аналитик | `analyst` | BI-отчётность, Excel export |
| Рекламодатель | `advertiser` | Только свои кампании |
| Оператор | `operations` | Мониторинг КСО, развёртывание |
| Сервис КСО | `device_service` | Machine-only: Device Gateway, Sidecar, Player, Service API. Нет human UI. |

## 3. RLS Scopes

| Scope | Ограничение |
|---|---|
| `advertiser_scope` | По рекламодателю — только свои кампании и креативы |
| `branch_scope` | По филиалу — только магазины своего филиала |
| `store_scope` | По магазину — только свои КСО и показы |
| `campaign_scope` | По кампании — только свои кампании |
| `device_scope` | По устройству — только свои КСО |
| `approval_scope` | По согласованию — только свои объекты |
| `report_scope` | По отчётам — агрегаты по своим scope |

**Правила пересечения:**
- Внутри одного scope type — **OR** (union)
- Между разными scope types — **AND** (intersection)

**Порядок применения RLS:**
1. RLS → pagination (out-of-scope rows never counted)
2. RLS → aggregation (out-of-scope data not in totals)
3. RLS → drill-down (cannot navigate outside scope)
4. RLS → Excel export (exported data respects scope)
5. RLS → approval queue (only in-scope objects visible)

## 4. Иерархия данных

### Сетевая иерархия (Network → Device)
```
Сеть
  → Филиал
    → Кластер
      → Магазин
        → КСО
```

### Коммерческая иерархия (Advertiser → Report)
```
Рекламодатель
  → Бренд
    → Кампания
      → Размещение
        → Manifest
          → PoP-событие
            → Отчёт
```

## 5. Представление портала для каждой роли

### Системный администратор (system_admin)
- **Основной экран:** Dashboard
- **Доступ:** Все 12 страниц портала
- **RLS:** Без ограничений (полный доступ)
- **Действия:** Управление пользователями, ролями, аудит, публикация, согласование, отчёты, Excel export
- **MFA:** ✅ Обязательно
- **Аудит:** ✅ Все действия аудируются
- **Видит:** Полную сеть, все кампании, всех рекламодателей, все технические данные

### Администратор безопасности (security_admin)
- **Основной экран:** Admin
- **Доступ:** Dashboard, Admin
- **RLS:** Без ограничений
- **Действия:** Управление пользователями, ролями, RLS-scopes, аудит
- **Запрещено:** Просмотр кампаний, креативов, отчётов, публикация, согласование, Excel export
- **MFA:** ✅ Обязательно
- **Аудит:** ✅ Все действия аудируются
- **Видит:** Только Admin-интерфейс, не видит коммерческие данные

### Менеджер рекламы (ad_manager)
- **Основной экран:** Кампании
- **Доступ:** Все, кроме Admin
- **RLS:** branch_scope, store_scope, campaign_scope, device_scope, approval_scope, report_scope
- **Действия:** Создание кампаний, публикация manifest, согласование, Excel export
- **Запрещено:** Управление пользователями, ролями, доступ к Admin
- **MFA:** Не требуется
- **Аудит:** ✅
- **Видит:** Коммерческие и технические данные в рамках своего RLS

### Согласующий (approver)
- **Основной экран:** Согласования
- **Доступ:** Dashboard, креативы, кампании, расписание, публикации, согласования, отчёты
- **RLS:** campaign_scope, approval_scope, report_scope
- **Действия:** Согласование объектов, просмотр отчётов
- **Запрещено:** Публикация manifest, управление пользователями, Excel export, доступ к КСО и магазинам
- **MFA:** Не требуется
- **Аудит:** ✅
- **Maker-checker:** Не может согласовать собственный объект
- **Видит:** Только объекты своего approval scope и campaign scope

### Аналитик (analyst)
- **Основной экран:** Отчёты
- **Доступ:** Всё, кроме Admin и Deployment
- **RLS:** branch_scope, store_scope, campaign_scope, device_scope, report_scope
- **Действия:** Просмотр отчётов, Excel export в RLS, просмотр кампаний и PoP
- **Запрещено:** Согласование, публикация, управление пользователями, Admin
- **MFA:** Не требуется
- **Аудит:** ✅
- **Видит:** Агрегированные данные по своим филиалам/кампаниям/КСО

### Рекламодатель (advertiser)
- **Основной экран:** Кампании
- **Доступ:** Dashboard, свои креативы и кампании, расписание, публикации, PoP, отчёты
- **RLS:** advertiser_scope, campaign_scope, report_scope
- **Действия:** Просмотр своих кампаний, креативов и отчётов
- **Запрещено:** Согласование, публикация, Excel export, управление пользователями, доступ к КСО/магазинам/Admin
- **MFA:** Не требуется
- **Аудит:** ✅
- **Видит:** Только свои кампании и креативы (advertiser_scope). Не видит сеть, устройства, согласования.

### Оператор (operations)
- **Основной экран:** КСО Устройства
- **Доступ:** Dashboard, магазины, КСО, развёртывание
- **RLS:** branch_scope, store_scope, device_scope
- **Действия:** Мониторинг КСО, управление устройствами, развёртывание
- **Запрещено:** Просмотр кампаний, креативов, коммерческих данных, отчётов, согласование, Admin
- **MFA:** Не требуется
- **Аудит:** ✅
- **Видит:** Техническое состояние КСО, но не коммерческие данные (кампании, цены, условия)

### Сервис КСО (device_service) — machine-only

**device_service не является пользователем портала.** Это техническая роль для сервисного взаимодействия.

- **Доступ в портал:** Нет human UI-доступа. Не аутентифицируется через страницу входа портала.
- **Обычная сессия web UI:** Отсутствует.
- **Используется для:** Device Gateway, Sidecar, Player, Service API — только сервисное взаимодействие.
- **RLS:** store_scope, device_scope
- **Действия:** Управление КСО, deployment (через API, не через UI)
- **Запрещено:** Весь human portal UI. Не видит Admin, Campaigns, Reports, Deployment как человек.
- **MFA:** Не требуется
- **Аудит:** Не требуется (machine-only)
- **Проверка доступа:** Должна выполняться отдельно в Device/API контуре, не через portal auth flow.
- **Отображение:** В Admin и RLS-документации — только для governance и аудита.

## 6. Матрица страниц по ролям

| Страница | sys_admin | sec_admin | ad_mgr | approver | analyst | advertiser | ops | device |
|---|---|---|---|---|---|---|---|---|
| /dashboard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| /stores | ✅ | — | ✅ | — | ✅ | — | ✅ | — |
| /devices | ✅ | — | ✅ | — | ✅ | — | ✅ | — |
| /creatives | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| /campaigns | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| /schedule | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| /publications | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| /proof-of-play | ✅ | — | ✅ | — | ✅ | ✅ | — | — |
| /approvals | ✅ | — | ✅ | ✅ | — | — | — | — |
| /reports | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| /deployment | ✅ | — | ✅ | — | — | — | ✅ | — |
| /admin | ✅ | ✅ | — | — | — | — | — | — |

## 7–16. RLS по страницам

### RLS на Dashboard
Dashboard показывает агрегированные KPI. RLS применяется до расчёта метрик — пользователь видит только статистику по своим scope. Оператор видит технические метрики (КСО онлайн, hold, ошибки), но не коммерческие (кампании, показы).

### RLS на Stores
Магазины фильтруются по branch_scope и store_scope. Рекламодатель и согласующий не видят страницу Stores.

### RLS на Devices
КСО фильтруются по store_scope и device_scope. Оператор видит КСО своего филиала. Рекламодатель не видит устройства. Коммерческие данные не отображаются операционным ролям.

### RLS на Creatives
Креативы фильтруются по advertiser_scope и campaign_scope. Рекламодатель видит только свои креативы. Оператор не видит креативы.

### RLS на Campaigns
Кампании фильтруются по campaign_scope и advertiser_scope. План/факт только по своим кампаниям.

### RLS на Schedule
Расписание фильтруется по campaign_scope и store_scope. Слоты только по доступным магазинам/КСО.

### RLS на Publications
Публикации фильтруются по campaign_scope, store_scope, device_scope. Публикация manifest доступна только с permission publish_manifest и совпадением RLS scope.

### RLS на Proof of Play
PoP-события фильтруются по campaign_scope, store_scope, device_scope.

### RLS на Approvals
Очередь согласования фильтруется по approval_scope и campaign_scope. Пользователь не видит объекты вне своего approval scope. Maker-checker: нельзя согласовать собственный объект.

### RLS на Reports / BI
BI-отчёты строятся после применения RLS-фильтров. KPI, графики, drill-down — все работают в рамках scope. Out-of-scope данные не попадают в агрегаты и totals.

### RLS на Excel export
Excel export применяет те же RLS-фильтры, что и UI отчётов. Выгружаются только данные в scope пользователя. Формат .xlsx включает дату формирования, применённые фильтры и scope.

## 18. Admin / Users / Roles / RLS

Управление пользователями доступно только system_admin и security_admin. Все изменения пользователей/ролей/RLS аудируются. Admin-доступ не обходит бизнес-процессы согласования.

## 19. Audit Requirements

Аудируются:
- Создание/блокировка/архивирование пользователей
- Назначение/изменение ролей
- Назначение/изменение RLS-scopes
- Все действия system_admin и security_admin
- Публикация manifest
- Согласование объектов
- Экстренная остановка
- Изменение critical конфигурации

## 20. Запрещённые поля

Ни при каких условиях в UI, API-ответах, Excel-файлах и логах не отображаются:

- `device_secret`, `access_token`, `token`, `authorization`, `api_key`
- `password`, `password_hash`
- `manifest_hash`, `sha256`, `fingerprint`
- `storage_key`, `minio`, `file_path`, `filename`
- `campaign_id`, `creative_id`, `rendition_id`, `store_id`, `device_id`
- `schedule_item_id`, `manifest_item_id`, `booking_id`
- `device_event_id`, `batch_id`
- `receipt_number`, `card_number`, `customer_id`, `phone`, `email`, `fiscal_data`
- `sku_id`, `price`

## 21. Правила пересечения scopes

- Внутри одного типа scope — **OR** (пользователь с двумя филиалами видит оба)
- Между разными типами — **AND** (кампания должна быть И в campaign_scope, И в advertiser_scope)
- system_admin и security_admin — без RLS (пустой frozenset = полный доступ)

## 22. Maker-Checker Rule

Пользователь не может финально согласовать (final-approve) собственный объект. Создатель кампании/креатива/расписания не может быть единственным согласующим. Требуется минимум два разных пользователя в цепочке согласования.

## 23. Critical Rules (явно)

| Правило | Описание |
|---|---|
| UI hiding ≠ security | Backend/API/DB проверяет всё независимо |
| RLS before pagination | Out-of-scope rows never counted |
| RLS before aggregation | Out-of-scope data not in totals |
| RLS before drill-down | Cannot navigate outside scope |
| RLS before Excel export | Exported data respects scope |
| Excel = report UI RLS | Excel export использует те же фильтры |
| Maker-checker | Нельзя согласовать свой объект |
| Final approval required | Manifest без approval не публикуется |
| Emergency → MFA + reason | Экстренная остановка требует MFA, причины и аудита |
| Device service = machine | Нет human UI, нет коммерческих данных |
| Advertiser = own scope | Только свои кампании и отчёты |
| Operations = technical | Нет коммерческих данных, нет BI/Excel |
| Admin ≠ business bypass | Admin не обходит бизнес-согласования |
| Role/RLS changes audited | С timestamp и admin identity |

## Файлы контракта

- `apps/portal-web/security_contract.py` — `RolePortalView`, `PAGE_ROLE_MATRIX`, `RLS_RULES`, `FORBIDDEN_FIELDS_ALL`, `NETWORK_HIERARCHY`, `COMMERCIAL_HIERARCHY`, `DEVICE_SERVICE_IS_MACHINE_ONLY`
- `apps/portal-web/templates/pages/admin.html` — Role-Based Portal Views + RLS Matrix UI + device_service machine-only note
- `apps/portal-web/templates/pages/reports.html` — RLS note: до KPI/drill-down/Excel
- `apps/portal-web/templates/pages/approvals.html` — RLS note: scope + maker-checker
- `apps/portal-web/templates/pages/publications.html` — RLS note: permission + scope
- `apps/portal-web/templates/pages/devices.html` — RLS note: device scope visibility

## 24. Device Service Machine-Only Contract

Роль `device_service` является **исключительно machine-only**. Это означает:

1. **Не является пользователем портала.** Не имеет учётной записи для входа через `/login`.
2. **Не имеет human UI-сессии.** Не может открыть браузер и «залогиниться как device_service».
3. **Не видит страницы портала.** `allowed_pages` = пустой set. Ни одна portal page не доступна.
4. **Используется только через API.** Device Gateway, Sidecar, Player, Service API — сервисное взаимодействие.
5. **Аутентификация — отдельный контур.** Проверка device_service происходит в Device Gateway/API, не через portal auth flow.
6. **Отображается в Admin/RLS для governance.** Видимость в документации и Admin UI — для администраторов, чтобы понимать полную картину ролей, но не для предоставления доступа.
7. **Разрешения сохраняются для API.** `view_devices`, `view_deployment`, `manage_devices` действуют в API-контексте, но не дают доступа к portal UI.

### Признаки machine-only в контракте

| Признак | Значение |
|---|---|
| `DEVICE_SERVICE_IS_MACHINE_ONLY` | `True` |
| `allowed_pages` | `frozenset()` — пустой |
| `primary_page` | `"— (machine-only, no human UI)"` |
| `PAGE_ROLE_MATRIX` | Нет записей |
| Human portal login | Запрещён |
| Admin UI | Только governance note |
