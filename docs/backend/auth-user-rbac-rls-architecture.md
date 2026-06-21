# Backend Auth / User / RBAC / RLS — Architecture Contract

> **Статус:** 📄 Contract / Design. Без реализации.
>
> Дата: 2026-06-21
> Шаг: 36.2
> Ревизия: 1
>
> **ВАЖНО:** Этот документ — архитектурный контракт. Он описывает ЦЕЛЕВУЮ модель.
> Ни одна миграция БД, ни одна строка production-кода, ни один endpoint
> не реализованы в рамках этого шага. Только проектирование.

---

## 1. Auth Model

### 1.1 Локальная авторизация

Портал поддерживает **локальную авторизацию** как основной способ входа для
пилота на 1 КСО. Пользователи создаются администратором через Admin UI
(после реализации 36.3–36.6).

**Принципы:**
- Учётная запись создаётся администратором
- Пароль задаётся при создании, never stored plaintext
- Пользователь входит через `/login` с username + password
- После успешного входа выдаётся access_token (JWT, short-lived) + refresh_token

### 1.2 Будущий SSO/AD

Архитектура预留ает возможность подключения корпоративного SSO/AD:

- Поле `auth_provider` в таблице `users` (`local` | `ldap` | `saml` | `oidc`)
- Поле `ldap_dn` для маппинга AD-пользователя
- Маппинг AD-групп → роли платформы (через отдельную таблицу `sso_group_mappings` — будущая)
- SSO-пользователи не имеют локального пароля (`password_hash = NULL` разрешён для `auth_provider != 'local'`)

**Для пилота:** только `auth_provider = 'local'`.

### 1.3 Сервисные учётные записи

- `is_service_account = true`
- Не могут входить через `/login`
- Не имеют refresh_token
- Используются для Device Gateway / Sidecar / Player / Service API
- `device_service` роль — исключительно machine-only (см. шаг 35.2.2.1)

---

## 2. Password Policy

### 2.1 Hashing

| Параметр | Значение |
|---|---|
| Алгоритм | **bcrypt** (через `passlib`) |
| Cost factor | 12 |
| Plaintext storage | ❌ Запрещён |
| Hash в API-ответах | ❌ Никогда не возвращается |
| Hash в логах | ❌ Никогда не пишется |

**Почему bcrypt, не argon2:**
- bcrypt — зрелый, проверенный, есть во всех стандартных библиотеках
- Argon2 требует дополнительных зависимостей и не даёт критического преимущества для портала с < 100 пользователями
- При росте до enterprise — миграция на argon2 через поле `password_hash_version`

### 2.2 Password Requirements

| Требование | Значение |
|---|---|
| Минимальная длина | 8 символов |
| Максимальная длина | 128 символов |
| Проверка сложности | Не enforced в v1 (администратор задаёт пароль) |
| Смена пароля | Через отдельный flow (не в v1) |

### 2.3 Login Attempts

| Параметр | Значение |
|---|---|
| Максимальное число попыток | 5 |
| Период сброса счётчика | 15 минут |
| Блокировка после превышения | `is_locked = true`, `locked_until = now + 30 min` |
| Разблокировка | Автоматически после `locked_until`, или администратором |
| Информация в ответе | «Неверное имя пользователя или пароль» (без уточнения) |

### 2.4 Администратор и пароли

- Администратор **не видит** пароль пользователя
- Администратор **не видит** password_hash
- Администратор может **сбросить** пароль (задать новый)
- При сбросе пароля администратором — аудит-событие

---

## 3. User Model

### 3.1 User Statuses (portal contract)

Из `apps/portal-web/security_contract.py`:

| Статус | Поле БД | Описание |
|---|---|---|
| `active` | `is_active = true`, `is_locked = false` | Активен |
| `blocked` | `is_locked = true` | Заблокирован |
| `archived` | `is_archived = true` (новое поле) | Логическое удаление |
| `pending_activation` | `is_active = false`, `is_locked = false` | Ожидает активации |

### 3.2 Необходимые доработки модели User

Текущая модель: `is_active`, `is_locked`, `locked_until`, `failed_attempts`, `last_login_at`, `created_at`, `updated_at`.

**Нужно добавить:**
- `is_archived` (Boolean, default false) — логическое удаление
- `archived_at` (DateTime) — когда архивирован
- `archived_by` (UUID → users.id) — кто архивировал
- `status` — computed property: active / blocked / archived / pending_activation

### 3.3 Запрещённые поля

Ни при каких условиях в UI, API-ответах и логах не отображаются:

| Поле | Где запрещено |
|---|---|
| `password_hash` | Всегда |
| `mfa_secret` | Всегда |
| `token` / `access_token` / `refresh_token` | Кроме момента выдачи (response body) |
| `authorization` header | В логах |
| `email` | Без отдельного решения по ПДн |
| `phone` | Отсутствует в модели |
| `ldap_dn` | В UI |

---

## 4. Session Model

### 4.1 Рекомендация: JWT + Refresh Token

**Выбранная модель:** JWT access token (short-lived) + refresh token (long-lived, stored as SHA-256 hash).

**Почему:**
- **Stateless** — не требует server-side session store для каждого запроса
- **Refresh token уже есть** в текущей модели (`refresh_tokens` таблица)
- **Revocation** — через `revoked` флаг в refresh_tokens
- **Масштабируемость** — нет sticky session
- **CSRF** — JWT передаётся в `Authorization: Bearer` header (не cookie) для API; для portal pages — httpOnly secure cookie

### 4.2 Token Lifecycle

| Токен | TTL | Хранение |
|---|---|---|
| Access token (JWT) | 15 минут | Только в памяти клиента |
| Refresh token | 7 дней | SHA-256 hash в `refresh_tokens` |
| Refresh token rotation | При каждом refresh выдаётся новый refresh_token, старый revoke |

### 4.3 Session Expiration

| Событие | Действие |
|---|---|
| Access token expired | Клиент использует refresh_token для получения нового |
| Refresh token expired | Пользователь перенаправляется на `/login` |
| Idle timeout (опционально) | 30 минут — может быть добавлено позже |
| Logout | Revoke всех refresh_tokens пользователя (или конкретного) |

### 4.4 Session Revocation

- **Logout:** revoke refresh_token (флаг `revoked = true`)
- **Logout all sessions:** revoke все refresh_tokens пользователя
- **Блокировка пользователя:** revoke все refresh_tokens + `is_locked = true`
- **Смена пароля:** revoke все refresh_tokens

### 4.5 MFA Step-Up

Для критичных действий (emergency stop, публикация manifest) требуется
MFA step-up:
- Пользователь уже аутентифицирован
- При критичном действии — проверка `mfa_enabled`
- Если MFA включён — challenge (TOTP)
- После успешного MFA — short-lived elevated token (5 минут) для конкретного действия

### 4.6 CSRF Protection

- Portal forms используют CSRF token (Double Submit Cookie pattern или Synchronizer Token)
- API endpoints (JSON) — CORS + `Authorization: Bearer` header (CSRF не применим)

---

## 5. RBAC Enforcement

### 5.1 Permission Check Flow

```
Request → get_current_user → check_permission(required_permission) →
  → user.permissions содержит required_permission?
    YES → continue to business logic
    NO  → 403 Forbidden
```

### 5.2 Permission Naming Convention

Backend использует формат `resource.action` (из seed.py):
- `users.read`, `users.create`, `users.manage`
- `campaigns.read`, `campaigns.create`, `campaigns.manage`, `campaigns.approve`
- `publications.read`, `publications.manage`, `publications.approve`, `publications.publish`
- etc.

**Маппинг portal → backend permissions:**

| Portal permission (`security_contract.py`) | Backend permission (`seed.py`) |
|---|---|
| `view_dashboard` | `channels.read` |
| `view_stores` | `organization.read` |
| `view_devices` | `devices.read` |
| `view_creatives` | `media.read` |
| `view_campaigns` | `campaigns.read` |
| `view_schedule` | `scheduling.read` |
| `view_publications` | `publications.read` |
| `view_proof_of_play` | `campaign_reports.read` |
| `view_approvals` | `campaigns.approve` + `publications.approve` |
| `view_reports` | `reports.read` |
| `view_deployment` | `devices.gateway.read` |
| `view_admin` | `users.read` + `roles.read` |
| `export_reports` | `reports.export` |
| `approve_objects` | `campaigns.approve` + `media.approve` + `publications.approve` |
| `publish_manifest` | `publications.publish` |
| `manage_users` | `users.create` + `users.manage` |
| `manage_roles` | `roles.manage` |
| `manage_devices` | `devices.manage` + `devices.gateway.manage` |
| `view_audit` | `audit.read` |

### 5.3 Critical RBAC Rules

| Правило | Enforcement |
|---|---|
| Публикация manifest требует `publications.publish` | Backend middleware |
| Согласование требует `campaigns.approve` | Backend middleware |
| Admin-доступ требует `users.read` + `roles.read` | Backend middleware |
| Emergency stop требует `emergency.manage` + MFA | Backend middleware + MFA check |
| device_service не имеет portal UI доступа | `is_service_account = true` → login rejected |

---

## 6. RLS Enforcement

### 6.1 RLS Scope Model

Из portal `security_contract.py`, 7 scopes:

| Scope | Описание | Поле фильтрации |
|---|---|---|
| `advertiser_scope` | По рекламодателю | `advertiser_id` |
| `branch_scope` | По филиалу | `branch_id` |
| `store_scope` | По магазину | `store_id` |
| `campaign_scope` | По кампании | `campaign_id` |
| `device_scope` | По устройству | `device_id` |
| `approval_scope` | По согласованию | `approval_route_id` |
| `report_scope` | По отчётам | агрегация по scope |

### 6.2 RLS Flow

```
Request → get_current_user → get_user_rls_scopes →
  → apply_rls_filter(query, user_rls_scopes) →
    → query.where(scope_conditions)
  → execute query
  → return filtered result
```

### 6.3 RLS Application Order (Critical)

RLS должен применяться **до** всех downstream операций:

1. **RLS → pagination** — out-of-scope rows never counted (page count корректен)
2. **RLS → aggregation** — out-of-scope data not in totals
3. **RLS → BI drill-down** — cannot navigate outside scope
4. **RLS → Excel export** — exported data respects scope
5. **RLS → approval queue** — only in-scope objects visible
6. **RLS → publication selection** — только доступные КСО/магазины

### 6.4 Scope Intersection Rules

- **Внутри одного типа scope:** OR (union) — пользователь с двумя филиалами видит оба
- **Между разными типами:** AND (intersection) — кампания должна быть И в campaign_scope, И в advertiser_scope
- **system_admin, security_admin:** пустой set = без RLS (полный доступ)
- **device_service:** machine-only, RLS применяется на API уровне

### 6.5 Manual URL/API Bypass Protection

- RLS enforced на backend/API/DB уровне — **не полагается на UI**
- Каждый API endpoint применяет RLS фильтр независимо
- Прямой вызов API с другим `?store_id=` не обходит RLS (фильтр по user scopes)
- SQLAlchemy query filtering: `query.where(model.store_id.in_(user_accessible_store_ids))`

---

## 7. Future PostgreSQL Tables

### 7.1 Существующие таблицы (уже в models.py)

| Таблица | Назначение | Статус |
|---|---|---|
| `users` | Portal users | ✅ Существует |
| `roles` | RBAC roles | ✅ Существует |
| `permissions` | Granular permissions | ✅ Существует |
| `user_roles` | User ↔ Role mapping | ✅ Существует |
| `role_permissions` | Role ↔ Permission mapping | ✅ Существует |
| `refresh_tokens` | JWT refresh token storage | ✅ Существует |

### 7.2 Новые таблицы (требуют создания)

#### `user_rls_scopes`

**Назначение:** связь пользователя с областями данных (RLS scopes).

```sql
-- Концептуальная схема, не миграция
CREATE TABLE user_rls_scopes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    scope_type  VARCHAR(64) NOT NULL,  -- 'branch_scope', 'store_scope', etc.
    scope_value VARCHAR(255) NOT NULL, -- конкретный филиал/магазин/КСО/кампания
    assigned_by UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(user_id, scope_type, scope_value)
);

CREATE INDEX idx_user_rls_scopes_user ON user_rls_scopes(user_id);
CREATE INDEX idx_user_rls_scopes_type_value ON user_rls_scopes(scope_type, scope_value);
```

**Безопасные ограничения:**
- `scope_value` — opaque reference, не raw ID
- Не хранить иерархические пути
- Не хранить полные адреса/названия

#### `login_audit_events`

**Назначение:** журнал попыток входа (успешных и неуспешных).

```sql
CREATE TABLE login_audit_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username    VARCHAR(100) NOT NULL,      -- attempted username
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,  -- NULL if user not found
    success     BOOLEAN NOT NULL,
    ip_address  VARCHAR(45),               -- optional, требует решения по ПДн
    user_agent  VARCHAR(512),              -- optional
    failure_reason VARCHAR(100),           -- 'invalid_credentials', 'locked', 'inactive'
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_login_audit_user ON login_audit_events(user_id, created_at DESC);
CREATE INDEX idx_login_audit_created ON login_audit_events(created_at DESC);
```

**Безопасные ограничения:**
- Не хранить пароль (даже неверный)
- Не хранить token
- `ip_address` — optional, требует compliance review
- `user_agent` — optional, не парсится для fingerprinting без согласования

#### `admin_audit_events`

**Назначение:** журнал административных действий.

```sql
CREATE TABLE admin_audit_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id   UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    action          VARCHAR(100) NOT NULL,  -- 'create_user', 'block_user', 'assign_role', etc.
    target_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    target_type     VARCHAR(64),            -- 'user', 'role', 'rls_scope'
    target_value    VARCHAR(255),           -- opaque reference
    details         JSONB,                  -- structured, без forbidden fields
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_admin_audit_admin ON admin_audit_events(admin_user_id, created_at DESC);
CREATE INDEX idx_admin_audit_target ON admin_audit_events(target_user_id, created_at DESC);
CREATE INDEX idx_admin_audit_action ON admin_audit_events(action, created_at DESC);
```

**Безопасные ограничения:**
- `details` JSONB — только разрешённые поля (role_code, scope_type, scope_value, status_change)
- Не хранить password, hash, token, email, phone
- Не хранить raw SQL
- Не хранить полные request bodies

#### `mfa_settings`

**Назначение:** выделенные настройки MFA (выносится из `users.mfa_secret`).

```sql
CREATE TABLE mfa_settings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
    enabled     BOOLEAN DEFAULT false,
    secret      VARCHAR(255),              -- TOTP secret (encrypted at rest)
    backup_codes TEXT,                     -- hashed backup codes
    enrolled_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,

    CONSTRAINT mfa_settings_user_unique UNIQUE(user_id)
);

CREATE INDEX idx_mfa_settings_user ON mfa_settings(user_id);
```

**Безопасные ограничения:**
- `secret` — encrypted at rest (не plaintext)
- `backup_codes` — только bcrypt-хеши, не plaintext
- Не возвращается в API-ответах
- Не пишется в логи

### 7.3 Индексы (сводка)

| Таблица | Индекс | Назначение |
|---|---|---|
| `users` | `username` (unique) | Login lookup |
| `users` | `is_active`, `is_locked` | User queries |
| `roles` | `code` (unique) | Role lookup |
| `permissions` | `code` (unique) | Permission lookup |
| `user_roles` | `user_id`, `role_id` (PK) | User-role queries |
| `role_permissions` | `role_id`, `permission_id` (PK) | Role-permission queries |
| `refresh_tokens` | `user_id` | Session queries |
| `refresh_tokens` | `token_hash` (unique) | Token lookup |
| `user_rls_scopes` | `user_id` | User RLS |
| `login_audit_events` | `user_id`, `created_at` | Audit trail |
| `admin_audit_events` | `admin_user_id`, `created_at` | Admin audit |
| `mfa_settings` | `user_id` (unique) | MFA check |

### 7.4 Аудит изменений (все таблицы)

Все таблицы identity-домена должны иметь:
- `created_at` — timestamp создания
- `updated_at` — timestamp изменения (для mutable таблиц)

Изменения ролей, разрешений, RLS-scopes аудируются через `admin_audit_events`.

---

## 8. Future API Contracts

### 8.1 Endpoints

| Метод | Путь | Назначение | Permission | RLS | Аудит |
|---|---|---|---|---|---|
| `POST` | `/api/auth/login` | Вход | — (public) | — | ✅ login_audit |
| `POST` | `/api/auth/logout` | Выход | — (authenticated) | — | — |
| `POST` | `/api/auth/refresh` | Обновление токена | — (public, с refresh_token) | — | — |
| `GET` | `/api/auth/me` | Текущий пользователь | — (authenticated) | — | — |
| `GET` | `/api/users` | Список пользователей | `users.read` | — | — |
| `POST` | `/api/users` | Создать пользователя | `users.create` | — | ✅ admin_audit |
| `PATCH` | `/api/users/{safe_user_ref}/status` | Изменить статус | `users.manage` | — | ✅ admin_audit |
| `GET` | `/api/roles` | Список ролей | `roles.read` | — | — |
| `POST` | `/api/users/{safe_user_ref}/roles` | Назначить роли | `roles.manage` | — | ✅ admin_audit |
| `POST` | `/api/users/{safe_user_ref}/rls-scopes` | Назначить RLS scopes | `roles.manage` | — | ✅ admin_audit |
| `GET` | `/api/admin/audit` | Журнал аудита | `audit.read` | — | — |

### 8.2 Безопасные формы запросов/ответов

**`POST /api/auth/login`**

```json
// Request
{
  "username": "string (1-100)",
  "password": "string (1-128)"
}

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}

// Response 401
{
  "detail": "Неверное имя пользователя или пароль"
}

// Response 423 (locked)
{
  "detail": "Учётная запись заблокирована"
}
```

**`GET /api/auth/me`**

```json
// Response 200
{
  "id": "uuid",
  "username": "string",
  "display_name": "string | null",
  "is_active": true,
  "is_locked": false,
  "auth_provider": "local",
  "roles": ["ad_manager"],
  "permissions": ["campaigns.read", "campaigns.create", ...],
  "rls_scopes": [
    {"type": "branch_scope", "value": "central"},
    {"type": "store_scope", "value": "store-001"}
  ]
}

// Forbidden fields: password_hash, mfa_secret, email, ldap_dn
```

**`POST /api/users`**

```json
// Request
{
  "username": "string (1-100, ^[a-z0-9_]+$)",
  "password": "string (8-128)",
  "display_name": "string | null"
}

// Response 201
{
  "id": "uuid",
  "username": "string",
  "display_name": "string | null",
  "is_active": true,
  "is_locked": false,
  "status": "pending_activation",
  "auth_provider": "local",
  "created_at": "ISO8601"
}

// Forbidden fields: password (не возвращается), password_hash
```

**`GET /api/users`**

```json
// Response 200
{
  "users": [
    {
      "id": "uuid",
      "username": "string",
      "display_name": "string | null",
      "is_active": true,
      "is_locked": false,
      "status": "active",
      "auth_provider": "local",
      "is_service_account": false,
      "roles": ["ad_manager"],
      "last_login_at": "ISO8601 | null",
      "created_at": "ISO8601"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}

// Forbidden fields: password_hash, mfa_secret, email, ldap_dn
```

**`PATCH /api/users/{safe_user_ref}/status`**

```json
// Request
{
  "status": "blocked",          // active | blocked | archived
  "reason": "string | null"     // причина изменения
}

// Response 200
{
  "id": "uuid",
  "username": "string",
  "status": "blocked",
  "updated_at": "ISO8601"
}

// Forbidden: нельзя архивировать самого себя, system_admin
```

**`POST /api/users/{safe_user_ref}/roles`**

```json
// Request
{
  "role_codes": ["ad_manager", "approver"]
}

// Response 200
{
  "id": "uuid",
  "username": "string",
  "roles": ["ad_manager", "approver"]
}
```

**`POST /api/users/{safe_user_ref}/rls-scopes`**

```json
// Request
{
  "scopes": [
    {"type": "branch_scope", "value": "central"},
    {"type": "store_scope", "value": "store-001"}
  ]
}

// Response 200
{
  "id": "uuid",
  "username": "string",
  "rls_scopes": [
    {"type": "branch_scope", "value": "central"},
    {"type": "store_scope", "value": "store-001"}
  ]
}

// Forbidden fields: scope_value не содержит raw internal ID
```

**`GET /api/admin/audit`**

```json
// Response 200
{
  "events": [
    {
      "id": "uuid",
      "admin_user": "admin",
      "action": "assign_role",
      "target_user": "operator1",
      "target_type": "role",
      "target_value": "operations",
      "created_at": "ISO8601"
    }
  ],
  "total": 156,
  "limit": 50,
  "offset": 0
}

// Forbidden fields: details JSONB (если содержит sensitive), ip_address
```

### 8.3 `safe_user_ref`

Вместо raw UUID в URL использовать безопасную ссылку:
- `safe_user_ref = username` для API (admin-facing)
- `safe_user_ref = external_id` (opaque, не sequential) для внешних consumer'ов

**Причина:** username уникален, читаем администратором, не раскрывает internal structure.

### 8.4 Error Codes

| Код | Описание |
|---|---|
| 400 | Неверный формат запроса |
| 401 | Не аутентифицирован |
| 403 | Недостаточно прав (permission check) |
| 404 | Пользователь/роль/scope не найден |
| 409 | Конфликт (username занят, роль уже назначена) |
| 422 | Ошибка валидации (password too short, etc.) |
| 423 | Учётная запись заблокирована |
| 429 | Слишком много попыток входа |

---

## 9. Security Rules

### 9.1 Forbidden Fields (глобально)

Ни при каких условиях не отображаются в UI, API-ответах, логах:

```
password
password_hash
token
access_token
refresh_token
authorization
bearer
client_secret
device_secret
backend_url
raw internal id (в UI-контексте)
sha256
storage_key
minio
file_path
filename
phone
email (без отдельного compliance review)
payment data
receipt data
fiscal data
mfa_secret
```

### 9.2 Log Safety

- Никакие токены не пишутся в логи приложения
- `Authorization` header маскируется: `Bearer ***`
- `password` field маскируется в request logging
- Ошибки аутентификации логируются без пароля

### 9.3 Admin Safety

- Администратор не видит пароли пользователей
- Администратор не видит password_hash
- Администратор не может войти как другой пользователь (impersonation запрещён)
- Администратор не обходит бизнес-процессы согласования
- Изменения ролей/RLS администратором аудируются

---

## 10. Alignment with Portal Security Contract

### 10.1 Соответствие

| Portal (`security_contract.py`) | Backend (этот контракт) |
|---|---|
| 8 ролей (`Role` enum) | 8 ролей в `seed.py` ✅ |
| 19 permissions (`Permission` enum) | 47 permissions (resource.action) ✅ superset |
| 7 RLS scopes (`RLSScope` enum) | `user_rls_scopes` table ✅ |
| `DEVICE_SERVICE_IS_MACHINE_ONLY` | `is_service_account`, login rejection ✅ |
| `SECURITY_PRINCIPLES` | RBAC/RLS enforcement ✅ |
| `RLS_RULES` | RLS application order ✅ |
| `ROLE_PORTAL_VIEWS` | Маппинг portal→backend permissions ✅ |
| `PAGE_ROLE_MATRIX` | Backend-enforced через permissions ✅ |

### 10.2 Несоответствия (требуют решения)

| Portal | Backend | Действие |
|---|---|---|
| `view_dashboard` | `channels.read` | Принять backend naming как canonical |
| `view_admin` | `users.read` + `roles.read` | Комбинация permissions |
| `view_proof_of_play` | `campaign_reports.read` | Уточнить naming |
| `view_approvals` | `campaigns.approve` + `publications.approve` | Комбинация |

---

## 11. Implementation Sequence

### Phase 2 Decomposition (для `one-kso-pilot-readiness-plan.md`)

| Шаг | Описание | Статус |
|---|---|---|
| 36.2 | Auth/User/RBAC/RLS architecture contract | ✅ Этот документ |
| 36.3 | Auth DB model and migrations | Будущий |
| 36.4 | Password hashing / session foundation | Будущий |
| 36.5 | User CRUD backend | Будущий |
| 36.6 | Admin users API + portal integration | Будущий |
| 36.7 | RBAC/RLS enforcement tests | Будущий |

---

## Файлы

- `docs/backend/auth-user-rbac-rls-architecture.md` — этот документ
- `backend/app/domains/identity/models.py` — существующая модель (User, Role, Permission, etc.)
- `backend/app/domains/identity/seed.py` — существующий seed (47 permissions, 8 ролей)
- `backend/app/core/security.py` — существующий модуль безопасности (hash_password)
- `apps/portal-web/security_contract.py` — portal security contract (reference)
- `docs/audit/full-system-audit-tz-v2-5.md` — full system audit
- `docs/audit/one-kso-pilot-readiness-plan.md` — pilot readiness plan
