# RC0 Demo Launch Note — 45.0.2 / 45.1.2 / 45.2 / 45.2.1

**Дата:** 2026-06-28
**Версия:** 45.2.1 (secure demo baseline — RLS fix + demo boundaries)

---

## Какой тег использовать для демонстрации

| Тег | HEAD | Назначение |
|-----|------|------------|
| `v0.9.0-rc0-business-demo` | `a9631af` | Исходная заморозка RC0 (НЕ использовать) |
| `v0.9.0-rc0-business-demo.1` | `6fac6a3` | Runtime smoke patch (НЕ использовать) |
| `v0.9.0-rc0-business-demo.2` | `76a9cd4` | Визуальный polish baseline **до RLS fix** (НЕ использовать) |
| **`v0.9.0-rc0-business-demo.3`** | **`d78e23f`** | **Secure demo baseline — использовать для показа** |

> **Для бизнес-демонстрации используйте ТОЛЬКО `v0.9.0-rc0-business-demo.3` (HEAD `d78e23f`).**
> Тег `.2` (`76a9cd4`) визуально готов, но содержит CRITICAL RLS bypass: любой пользователь с `campaigns.read`
> может читать чужие кампании по UUID. Тег `.3` закрывает эту уязвимость + включает admin account unlock.
>
> Предыдущие теги (.0, .1, .2) НЕ ИСПОЛЬЗОВАТЬ для демо.

---

## Границы демонстрации (Demo Boundaries)

### Что можно показывать

| # | Страница | Маршрут | Статус |
|---|----------|---------|--------|
| 1 | Вход | `/login` | ✅ Готово |
| 2 | Главный экран | `/dashboard` | ✅ Готово |
| 3 | Креативы | `/creatives` | ✅ Готово |
| 4 | Модерация: очередь | `/creatives/moderation/queue` | ✅ Готово |
| 5 | Кампании | `/campaigns` | ✅ Готово |
| 6 | Создание кампании | `/campaigns/create` | ✅ Готово |
| 7 | Расписание | `/schedule` | ✅ Готово |
| 8 | Согласования | `/approvals` | ✅ Готово |
| 9 | Публикации | `/publications` | ✅ Готово |
| 10 | Отчёты | `/reports` | ✅ Готово |
| 11 | Рекламное время | `/inventory` | ✅ Готово |
| 12 | Готовность к пилоту | `/readiness` | ✅ Готово |
| 13 | Бизнес-приёмка | `/readiness/business-acceptance` | ✅ Готово |
| 14 | Магазины | `/stores` | ✅ Готово |
| 15 | Администрирование (system_admin) | `/admin` | ✅ Готово |
| 16 | Развёртывание | `/deployment` | ✅ Готово |

**Все 16 страниц → HTTP 200 под `system_admin`. Без аутентификации → редирект на `/login`.**

### Что НЕ показывать как готовую функцию

| Функция | Причина | Статус |
|---------|---------|--------|
| Создание пользователей через portal UI | Не реализовано | ❌ RC0 limitation |
| Изменение ролей через `PUT /api/users/{id}/roles` | HTTP 500 (backend bug) | ❌ RC0 limitation |
| Изменение RLS-scope через `PATCH /api/users/{username}/rls-scopes` | HTTP 422 (backend bug) | ❌ RC0 limitation |

Эти три функции — **P1 limitations, задокументированы, не блокируют демо**.
Управление пользователями/ролями/scopes в RC0 возможно только через БД (не через UI/API).

---

## Что проверено (45.2 + 45.2.1)

- ✅ **P0 admin lockout** — исправлен: `is_locked=false`, admin входит, `/admin` = 200
- ✅ **P0 RLS bypass** — исправлен: 11 campaign UUID endpoints → 404 для кросс-доступа
- ✅ **RLS 21/21 PASS** — advertiser isolation подтверждён
- ✅ **RBAC матрица** — 8 ролей × 47 permissions проверены
- ✅ **Persistence** — create → DB → refresh работает
- ✅ **Audit trail** — login, user.create, campaign.create фиксируются
- ✅ **Error pages** — 403/404 стилизованы, бизнес-язык, без traceback
- ✅ **Видимых технических терминов** — 0
- ✅ **JS, CDN, localStorage** — 0
- ✅ **Secrets/tokens/URLs в выводах** — 0

### Regression

| Слой | Пройдено | Отказов |
|------|----------|---------|
| Portal | **759** (+32 skipped) | **0** |
| Backend | **807** | **0** |

---

## Что НЕ настроено и НЕ запущено

- ❌ **Физический запуск в магазин запрещён** — 5 P0 блокировок актуальны
- ❌ **Production AV не включён** — система в режиме `pilot_dev`
- ❌ **Фактические показы не имитируются** — раздел «Фактические показы» сообщает об отсутствии данных
- ❌ **Доставка на КСО заблокирована** — пакеты публикации не покидают контур платформы
- ❌ **Физический сканер не подключён**
- ❌ **Длительный прогон (long-run) не проводился**
- ❌ **Синхронизация агента (sidecar sync) не запускалась**
- ❌ **Физическая КСО не трогалась**
- ❌ **SSH/X11/Chromium/runner/sidecar/PoP не запускались**

---

## Что делать, если портал запущен старым процессом

```bash
# Проверить текущий HEAD
git log --oneline -1
# Должен быть: d78e23f (или новее)

# Если нет — переключиться на secure demo tag
git checkout v0.9.0-rc0-business-demo.3

# Остановить старый процесс портала и backend
pkill -f "uvicorn.*8422"
pkill -f "uvicorn.*8421"

# Перезапустить
cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8421 &
cd apps/portal-web && python3 main.py &
```

---

## Связанные документы

- `docs/audit/pre-demo-functional-audit-45-2.md` — полный аудит
- `docs/audit/rbac-rls-audit-45-2.md` — RBAC/RLS матрица
- `docs/audit/frontend-backend-contract-matrix-45-2.md` — контракт frontend-backend
- `docs/product/rc0-release-notes-44-6.md` — примечания к выпуску RC0
- `docs/product/business-demo-route-44-6.md` — маршрут бизнес-демонстрации
- `CHANGELOG.md` — история изменений
