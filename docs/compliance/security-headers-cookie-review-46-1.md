# Security Headers / Cookie / Session Review — 46.1

> Retail Media Platform — обзор безопасности сессий, cookie и заголовков
> Версия: 1.0 | Дата: 2026-06-29 | Этап: 46.1

## 1. Cookie Security

### 1.1. Portal session cookie

| Параметр | Значение | Статус |
|---|---|---|
| Имя | `portal_session_id` | ✅ |
| Тип значения | opaque hex string (64 chars) | ✅ |
| httpOnly | ✅ Да | ✅ JS не может читать |
| SameSite | Lax | ✅ Защита от CSRF |
| Signed | ✅ Да (Starlette sessions) | ✅ |
| Secure | ❌ Нет (dev без HTTPS) | ⚠️ Документировано для production |
| max_age | 3600 сек (1 час) | ✅ |
| Хранение | Серверный in-memory dict | ⚠️ DEV only; заменить на Redis/PG в production |

### 1.2. Что НЕ в cookie

- ❌ JWT токены (только на сервере)
- ❌ Пароли/хеши
- ❌ Роли/права (только на сервере)
- ❌ UUID пользователя

## 2. Session Security

### 2.1. Серверное хранение

- Токены (access + refresh) хранятся **только на сервере**
- Браузер получает opaque session_id
- `PortalUser` — safe view без токенов, email, UUID
- `get_portal_tokens()` — internal only, never exposed to templates

### 2.2. Session expiration

- TTL: 1 час (3600 сек)
- При истечении: серверная сессия удаляется
- Refresh token: 7 дней (JWT), хранится как SHA-256 хеш

### 2.3. Logout

- Портал: очистка серверной сессии + cookie
- Backend: отзыв refresh-токена (`revoked=true`)
- JWT access token: не отзывается (короткий TTL 15 мин)

## 3. CSRF Protection

| Механизм | Статус |
|---|---|
| SameSite=Lax cookie | ✅ |
| Server-side forms (POST) | ✅ Нет JS, нет fetch |
| Нет CORS для cookie | ✅ (SameSite) |
| Отсутствие localStorage для токенов | ✅ |

## 4. HTTP Security Headers

**Текущее состояние:** заголовки безопасности не настроены на уровне backend/portal (dev-режим).

### 4.1. Рекомендованные заголовки (production)

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
```

### 4.2. План

- Добавить middleware для security headers
- Активировать только в production (env-флаг)
- Не менять dev-режим без HTTPS

## 5. Password Policy

| Параметр | Значение |
|---|---|
| Мин. длина | 8 символов |
| Макс. длина | 128 символов |
| Хеширование | bcrypt |
| Блокировка | После N неудачных попыток (is_locked) |
| Сброс | Только администратором |

## 6. Итоговая оценка

| Категория | Оценка |
|---|---|
| Cookie security | ✅ Хорошо (httpOnly, SameSite, signed) |
| Token storage | ✅ Отлично (server-side only, no browser exposure) |
| Session management | ⚠️ Хорошо для dev (in-memory); нужен Redis/PG в production |
| CSRF | ✅ Защищено (SameSite + server-side forms) |
| Security headers | ⚠️ Не настроены (dev mode); задокументированы для production |
| Password storage | ✅ bcrypt, необратимый |
| Logout | ✅ Отзыв refresh-токена + очистка сессии |
