# Web Portal UI Foundation — KSO v1

> **Статус:** 🖥️ Foundation. Первый шаг Web Portal UI.
>
> Последнее обновление: 2026-06-21

## Что создано

**Приложение:** `apps/portal-web/` — FastAPI + Jinja2 серверный портал.
**Стек:** FastAPI 0.133 + Jinja2 3.1 + Starlette TestClient.
**Тестов:** 51 (routes, navigation, devices, content, security).

## Страницы (12 routes v1)

| Route | Страница | Статус |
|---|---|---|
| `/` `/dashboard` | Dashboard — обзорные карточки | ✅ заглушка |
| `/campaigns` | Кампании | ✅ заглушка |
| `/creatives` | Креативы | ✅ заглушка |
| `/schedule` | Расписание | ✅ заглушка |
| `/publications` | Публикации манифестов | ✅ заглушка |
| `/stores` | Магазины и филиалы | ✅ заглушка |
| `/devices` | КСО Устройства | ✅ UI foundation (cards + filters + table) |
| `/proof-of-play` | Proof of Play | ✅ заглушка |
| `/reports` | Отчёты | ✅ заглушка |
| `/deployment` | Развёртывание (KSO Runtime) | ✅ контент |
| `/admin` | Администрирование | ✅ заглушка |

## Меню v1 (11 пунктов)

Главное: Dashboard
Реклама: Кампании, Креативы, Расписание, Публикации
КСО: КСО Устройства, Proof of Play, Магазины
Управление: Отчёты, Развёртывание, Администрирование

## Что входит в v1

- KSO-реклама (Chromium kiosk)
- Proof of Play
- Отчётность по показам
- Управление КСО устройствами
- Развёртывание KSO Runtime

## Что out of scope (отсутствует в меню v1)

- ❌ Android TV
- ❌ LED-шелфбаннеры
- ❌ Электронные ценники (ESL)
- ❌ Price checker
- ❌ Мобильное приложение

## Dashboard

6 карточек без реальных данных:
- КСО устройств
- Активных кампаний
- Опубликованных манифестов
- Proof of Play сегодня
- Устройств в hold
- Устройств с ошибками

Значения: `—` (нет API).

## Deployment page

Описывает компоненты KSO Runtime:
- State Adapter, Sidecar Agent, KSO Player
- Bootstrap, Preflight, Release Package Builder
- Pilot Runbook, Release Package Contract, UKM 4 Discovery

Без raw system paths и секретов.

## KSO Devices page

**Структура:**
- **6 summary cards:** Всего КСО, Онлайн, В hold, С ошибками, Без heartbeat, Требуют обновления
- **4 фильтра:** Филиал, Магазин, Статус, Версия runtime (все disabled)
- **Таблица (10 колонок):** Магазин, КСО, State Adapter, Sidecar, Player, Runtime, Heartbeat, Manifest, PoP, Действия
- **Empty state:** «Пока нет подключённых КСО»
- **Легенда статусов:** Онлайн, Hold, Ошибка, Офлайн, Нет данных

**Status badges (CSS):** `.badge-online` (green), `.badge-hold` (yellow),
`.badge-error` (red), `.badge-offline` (gray), `.badge-unknown` (light gray)

**Planned future API fields (не отображаются пока):**
- device_code, store_name, state_adapter_status, sidecar_status, player_status
- runtime_version, last_heartbeat_utc, last_manifest_utc, pop_status
- Без raw IDs/secret/hash/backend URL

**Security:**
- ❌ Нет device_secret, access_token, manifest_hash
- ❌ Нет backend URL, campaign_id, creative_id
- ❌ Нет Android TV, LED-шелф, ESL, Mobile App
- ✅ Все значения статичные (—)

## Styling

- Минимальный CSS (250 строк) — без внешних CDN
- Светлая тема, corporate layout
- Fixed sidebar (240px), fixed header (56px)
- Адаптивная сетка карточек (`auto-fill, minmax(240px, 1fr)`)
- Без внешних шрифтов (system font stack)

## Security rules

- ❌ Нет внешних CDN/fonts/scripts
- ❌ Нет хардкоженных backend URL
- ❌ Нет секретов/token в шаблонах
- ❌ Нет Windows/MSI/ProgramData
- ❌ Нет Android TV/LED/ESL/mobile app в меню
- ✅ Все значения — статичные заглушки
- ✅ Нет реальных API-вызовов

## Запуск

```bash
cd apps/portal-web
python3 main.py  # или uvicorn main:app --port 8422
```

## Тесты

```bash
cd apps/portal-web
python3 -m unittest discover -s tests -v
# 39 tests: routes, navigation, content, security
```

## Следующие UI шаги

- Интеграция с backend API (безопасный API client)
- Auth/RBAC
- Реальные данные на dashboard
- CRUD кампаний/креативов
- Таблицы с реальными данными
- Формы создания/редактирования
- Графики и отчёты
