# Login / Logout Audit Mapping — 46.1

> Retail Media Platform — сопоставление аудита входа/выхода
> Версия: 1.0 | Дата: 2026-06-29 | Этап: 46.1

## 1. Текущее состояние

### 1.1. Login audit (login_audit_events)

**Покрытие:** каждый вход (успешный и неуспешный) пишется в `login_audit_events`.

| Событие | result_code | Примечание |
|---|---|---|
| Успешный вход | `success` | username, user_id, occurred_at |
| Неверные учётные данные | `invalid_credentials` | username, occurred_at |
| Заблокирован | `locked` | username, occurred_at |
| Неактивен | `inactive` | username, occurred_at |
| Архивирован | `archived` | username, occurred_at |
| Сервисная учётка | `service_account` | username, occurred_at |

### 1.2. Logout audit

**Текущее состояние:** logout **НЕ** пишется в `login_audit_events`.

Причина: `login_audit_events` спроектирована только для попыток входа (аутентификации). Logout — это завершение сессии, не аутентификация.

### 1.3. Что происходит при logout

1. Портал вызывает `backend_logout(refresh_token)` — backend отзывает refresh-токен (`revoked=true`)
2. Портал очищает серверную сессию (`_store.delete(session_id)`)
3. Браузер получает очищенный cookie

**Аудит logout:** запись об отзыве refresh-токена сохраняется в БД (`refresh_tokens.revoked=true, revoked_at=now()`), но не в отдельной audit-таблице.

## 2. Mapping: где искать события

| Событие | Таблица | Поле | Как найти |
|---|---|---|---|
| Попытка входа | `login_audit_events` | `success`, `result_code` | `SELECT * WHERE username=X ORDER BY occurred_at` |
| Успешный вход | `login_audit_events` | `success=true` | `WHERE success=true AND username=X` |
| Неудачный вход | `login_audit_events` | `success=false` | `WHERE success=false AND username=X` |
| Блокировка учётной записи | `login_audit_events` | `result_code='locked'` | `WHERE result_code='locked'` |
| Отзыв refresh-токена (logout) | `refresh_tokens` | `revoked=true, revoked_at` | `WHERE user_id=X AND revoked=true ORDER BY revoked_at` |
| Деактивация пользователя | `admin_audit_events` | `action='archived_user'` | `WHERE action IN ('archived_user','blocked_user')` |

## 3. Пробелы

| Пробел | Влияние | План |
|---|---|---|
| Logout не пишется в `login_audit_events` | Невозможно построить «сессию от входа до выхода» в одной таблице | Задокументировано; объединение через `refresh_tokens.revoked_at` |
| Нет отдельной таблицы сессий | Нельзя отследить длительность сессии | В roadmap: `session_events` таблица |
| Refresh-токены не отзываются при деактивации | Активная сессия продолжается до истечения (1 час) | Низкий риск; в roadmap |

## 4. Рекомендации

1. **Краткосрочно**: задокументировать текущий mapping (✅ сделано)
2. **Среднесрочно**: добавить `session_events` таблицу с `session_start` / `session_end`
3. **Долгосрочно**: авто-отзыв refresh-токенов при деактивации
