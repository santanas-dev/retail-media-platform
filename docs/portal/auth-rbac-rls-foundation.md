# Portal Auth, RBAC and RLS Foundation

> **Статус:** 🔐 Foundation. Архитектурный контракт.
>
> Последнее обновление: 2026-06-21

## Принципы безопасности

1. **UI hiding is NOT security.** Backend/DB/API must enforce all rules.
2. **RLS must be enforced on backend/DB/API level.**
3. **Excel export must apply the same RLS as reports.**
4. **Manual URL opening must not bypass permissions.**
5. **BI reports must apply RLS filters before aggregation.**
6. **Approval workflow must enforce role-based routing.**
7. **All access decisions are made server-side, never client-side.**

## Роли

| Роль | ID | Описание |
|---|---|---|
| Системный администратор | `system_admin` | Полный доступ, без RLS-ограничений |
| Администратор безопасности | `security_admin` | Управление пользователями, ролями, аудит |
| Менеджер рекламы | `ad_manager` | Создание кампаний, публикация, согласование |
| Согласующий | `approver` | Проверка креативов/кампаний/расписания |
| Аналитик | `analyst` | BI-отчёты, Excel export, план/факт |
| Рекламодатель | `advertiser` | Только свои кампании и креативы |
| Оператор | `operations` | Мониторинг магазинов/КСО, развёртывание |
| Сервис КСО | `device_service` | Только КСО-устройства, развёртывание |

Роли назначаются через группы Active Directory / IdP. Маппинг: AD-группа → роль платформы.

## Permissions

| Permission | Описание |
|---|---|
| `view_dashboard` | Просмотр dashboard |
| `view_stores` | Просмотр магазинов |
| `view_devices` | Просмотр КСО-устройств |
| `view_creatives` | Просмотр библиотеки креативов |
| `view_campaigns` | Просмотр кампаний |
| `view_schedule` | Просмотр расписания |
| `view_publications` | Просмотр публикаций |
| `view_proof_of_play` | Просмотр Proof of Play |
| `view_approvals` | Просмотр согласований |
| `view_reports` | Просмотр BI-отчётов |
| `view_deployment` | Просмотр развёртывания |
| `view_admin` | Доступ к администрированию |
| `export_reports` | Выгрузка отчётов в Excel |
| `approve_objects` | Согласование объектов |
| `publish_manifest` | Публикация manifest на КСО |
| `manage_users` | Управление пользователями |
| `manage_roles` | Управление ролями |
| `manage_devices` | Управление КСО |
| `view_audit` | Просмотр аудита |

### Role → Permission Matrix

| Permission | sys_admin | sec_admin | ad_mgr | approver | analyst | advertiser | ops | device |
|---|---|---|---|---|---|---|---|---|
| view_dashboard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| view_stores | ✅ | — | ✅ | — | ✅ | — | ✅ | — |
| view_devices | ✅ | — | ✅ | — | ✅ | — | ✅ | ✅ |
| view_creatives | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| view_campaigns | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| view_schedule | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| view_publications | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| view_proof_of_play | ✅ | — | ✅ | — | ✅ | ✅ | — | — |
| view_approvals | ✅ | — | ✅ | ✅ | — | — | — | — |
| view_reports | ✅ | — | ✅ | ✅ | ✅ | ✅ | — | — |
| view_deployment | ✅ | — | ✅ | — | — | — | ✅ | ✅ |
| view_admin | ✅ | ✅ | — | — | — | — | — | — |
| export_reports | ✅ | — | ✅ | — | ✅ | — | — | — |
| approve_objects | — | — | ✅ | ✅ | — | — | — | — |
| publish_manifest | — | — | ✅ | — | — | — | — | — |
| manage_users | ✅ | ✅ | — | — | — | — | — | — |
| manage_roles | ✅ | ✅ | — | — | — | — | — | — |
| manage_devices | ✅ | — | — | — | — | — | ✅ | ✅ |
| view_audit | ✅ | ✅ | — | — | — | — | — | — |

## RLS Scopes

RLS-фильтры ограничивают видимость данных на уровне строк БД.

| Scope | Описание | Применяется к |
|---|---|---|
| `advertiser_scope` | По рекламодателю | campaigns, creatives, reports |
| `branch_scope` | По филиалу | stores, devices, reports |
| `store_scope` | По магазину | devices, PoP, reports |
| `campaign_scope` | По кампании | schedule, publications, reports |
| `device_scope` | По устройству | PoP, deployment |
| `approval_scope` | По согласованию | approvals |
| `report_scope` | По отчётам | BI dashboards, Excel export |

### Role → RLS Scope Matrix

| Role | RLS Scopes |
|---|---|
| system_admin | Без RLS (полный доступ) |
| security_admin | Без RLS (полный доступ) |
| ad_manager | branch, store, campaign, device, approval, report |
| approver | campaign, approval, report |
| analyst | branch, store, campaign, device, report |
| advertiser | advertiser, campaign, report |
| operations | branch, store, device |
| device_service | store, device |

RLS scopes additive — пользователь видит union своих scopes.

## Page Access Matrix

| Маршрут | Требуемое permission |
|---|---|
| `/dashboard` | `view_dashboard` |
| `/campaigns` | `view_campaigns` |
| `/creatives` | `view_creatives` |
| `/schedule` | `view_schedule` |
| `/publications` | `view_publications` |
| `/stores` | `view_stores` |
| `/devices` | `view_devices` |
| `/proof-of-play` | `view_proof_of_play` |
| `/approvals` | `view_approvals` |
| `/reports` | `view_reports` |
| `/deployment` | `view_deployment` |
| `/admin` | `view_admin` |

## Роль рекламодателя

- Видит только **свои** кампании и креативы (advertiser_scope + campaign_scope)
- Видит план/факт только по своим кампаниям
- Не видит устройства, магазины, развёртывание, согласования других рекламодателей
- Не может публиковать — только просмотр

## Роль аналитика

- Видит агрегированные данные по филиалам/кампаниям/устройствам в своём RLS-scope
- Может выгружать отчёты в Excel с теми же RLS-фильтрами
- Не видит конкретных пользователей и персональных данных
- Не может согласовывать или публиковать

## Роль согласующего

- Видит только объекты, направленные на согласование в его скоупе
- Не видит «чужие» креативы/кампании/расписания
- История согласований доступна только по своим объектам

## Роль оператора

- Видит магазины и КСО в своём филиале
- Мониторит статус устройств
- Доступ к развёртыванию без возможности менять сервисы

## Роль администратора

- Полный доступ без RLS-ограничений
- Управление пользователями и ролями
- Просмотр аудита

## Auth Flow (будущее)

1. Пользователь нажимает «Войти через SSO»
2. Редирект на IdP (Azure AD / corporate SSO)
3. Аутентификация, получение claims (группы AD)
4. Маппинг AD-групп → роли платформы
5. Создание серверной сессии с ролями и RLS-scopes
6. Все последующие запросы проверяют permission + RLS на backend/API/DB

## Файлы

- `apps/portal-web/security_contract.py` — контракт: роли, permissions, RLS scopes, page access matrix
- `apps/portal-web/templates/pages/login.html` — placeholder страницы входа
- `apps/portal-web/templates/pages/logout.html` — placeholder страницы выхода
- `apps/portal-web/templates/base.html` — статус пользователя в header
- `apps/portal-web/templates/pages/admin.html` — управление пользователями, ролями, RLS, аудит
- `apps/portal-web/templates/pages/reports.html` — note про RLS для BI/Excel
- `apps/portal-web/demo_data.py` — demo users для Admin

## Local Portal Authorization and Admin User Management (Шаг 35.2.1)

### Два режима авторизации

| Режим | Статус |
|---|---|
| Локальная учётная запись портала | Будет реализована |
| Корпоративный SSO / Active Directory | Будет подключён |

### Создание пользователей

- Пользователи заводятся **локально в меню Администрирование** администратором портала.
- Роли назначаются администратором.
- SSO/AD может быть подключён дополнительно.

### User Statuses

| Статус | Описание |
|---|---|
| `active` | Активен |
| `blocked` | Заблокирован |
| `archived` | Архив (логическое удаление) |
| `pending_activation` | Ожидает активации |

### Admin Capabilities

| Capability | Описание |
|---|---|
| `create_user` | Создание пользователя |
| `block_user` | Блокировка пользователя |
| `archive_user` | Архивирование пользователя |
| `assign_roles` | Назначение ролей |
| `assign_rls_scopes` | Назначение областей доступа / RLS |
| `require_mfa` | Требовать MFA |
| `view_admin_audit` | Просмотр аудита администрирования |

### Принципы локальной авторизации

1. Пользователь создаётся в Admin.
2. Роли назначаются администратором портала.
3. Для критичных ролей (system_admin, security_admin) требуется MFA.
4. Все изменения доступа аудируются.
5. Удаление пользователя должно быть логическим (archive, не физическое удаление).
6. RLS применяется на backend/DB/API уровне.
7. Excel export и BI reports учитывают RLS пользователя.
8. **Plaintext passwords запрещены** — только безопасный hash (bcrypt/argon2).
9. Пароли никогда не отображаются в UI и не передаются в открытом виде.
