# Web Portal UI Foundation — KSO v1

> **Статус:** 🖥️ Foundation. Первый шаг Web Portal UI.
>
> Последнее обновление: 2026-06-21

## Что создано

**Приложение:** `apps/portal-web/` — FastAPI + Jinja2 серверный портал.
**Стек:** FastAPI 0.133 + Jinja2 3.1 + Starlette TestClient.
**Тестов:** 108 (routes, navigation, devices, stores, creatives, campaigns, schedule, content, security).

## Страницы (12 routes v1)

| Route | Страница | Статус |
|---|---|---|
| `/` `/dashboard` | Dashboard — обзорные карточки | ✅ заглушка |
| `/campaigns` | Кампании | ✅ UI foundation (cards + lifecycle + filters + table) |
| `/creatives` | Креативы | ✅ UI foundation (cards + requirements + filters + table) |
| `/schedule` | Расписание | ✅ UI foundation (cards + planning + filters + table) |
| `/publications` | Публикации манифестов | ✅ заглушка |
| `/stores` | Магазины и КСО-инвентаризация | ✅ UI foundation (cards + filters + table) |
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

## Stores & KSO Inventory page

**Структура:**
- **6 summary cards:** Всего магазинов, Магазинов с КСО, КСО подключено, Готовы к показу, В hold, Требуют внимания
- **6 фильтров:** Филиал, Город/Регион, Формат магазина, Статус КСО, Готовность к рекламе, Версия runtime (все disabled)
- **Таблица (10 колонок):** Филиал, Магазин, Формат, КСО, State Adapter, Sidecar, Player, Готовность, Heartbeat, Действия
- **Empty state:** «Пока нет данных по магазинам»
- **Легенда готовности:** Готов, В hold, Ошибка, Нет связи, Нет данных
- **Связь с /devices:** инфо-блок «Детальный статус отдельных КСО отображается на странице КСО Устройства»

**Status badges:** `.badge-ready` (green), `.badge-no-connection` (gray)

**Planned future API fields (не отображаются пока):**
- branch_name, store_name, store_format, kso_count
- readiness_status, last_heartbeat_utc
- Без store_id, device_id, raw addresses, real store codes

**Security:**
- ❌ Нет store_id, device_id, address, city
- ❌ Нет device_secret, access_token, manifest_hash
- ❌ Нет backend URL, campaign_id, creative_id
- ❌ Нет Android TV, LED-шелф, ESL, Mobile App
- ✅ Все значения статичные (—)
- ✅ Реальные магазины/адреса не использовались

## KSO Creatives Library page

**Структура:**
- **6 summary cards:** Всего креативов, Готовы к публикации, На проверке, С ошибками, Используются в кампаниях, Требуют замены
- **Требования КСО v1:** Зона 1440×1080, PNG/JPEG, MP4, аудио запрещено, внешние ссылки/CDN запрещены, доставка через sidecar media cache
- **5 фильтров:** Тип материала, Статус проверки, Формат, Использование в кампаниях, Дата обновления (все disabled)
- **Таблица (9 колонок):** Название, Тип, Формат, Размер, Длительность, Статус, Используется, Обновлён, Действия
- **Empty state:** «Пока нет загруженных креативов»
- **Легенда статусов:** Готов, На проверке, Ошибка, Архив, Нет данных
- **Связь с campaigns:** инфо-блок «Креативы будут использоваться при создании кампаний и публикации манифестов»

**Status badges:** `.badge-ready` (green), `.badge-review` (blue), `.badge-error` (red), `.badge-archived` (gray), `.badge-unknown` (light gray)

**Planned future API fields (не отображаются пока):**
- creative_name, type (image/video), format (PNG/JPEG/MP4), file_size_bytes
- duration_seconds, review_status, campaign_count, updated_at_utc
- Без creative_id, rendition_id, storage key, sha256, file_path, filename

**Supported KSO v1 formats:**
- ✅ PNG, JPEG, MP4
- ❌ Аудио запрещено
- ❌ Внешние CDN/ссылки запрещены
- ✅ Материалы доставляются локально через sidecar media cache

**Future workflow (не на этом шаге):**
- Реальная загрузка файлов
- Модерация и проверка
- Хранение в MinIO
- Публикация в manifest
- Интеграция с backend API

**Security:**
- ❌ Нет creative_id, rendition_id, storage_key, minio
- ❌ Нет sha256, file_path, filename
- ❌ Нет device_secret, access_token, manifest_hash
- ❌ Нет backend URL, campaign_id
- ❌ Нет Android TV, LED-шелф, ESL, Mobile App
- ✅ Все значения статичные (—)

## KSO Campaigns page

**Структура:**
- **6 summary cards:** Всего кампаний, Активные, Черновики, На согласовании, Опубликованы, Требуют внимания
- **Жизненный цикл:** Черновик → На согласовании → Готова к публикации → Опубликована → В эфире → Завершена. Терминальные: Ошибка публикации, Остановлена, Архив
- **6 фильтров:** Статус кампании, Период, Креатив, Филиал/магазин, Готовность публикации, План/факт (все disabled)
- **Таблица (10 колонок):** Кампания, Статус, Период, Креативы, Магазины/КСО, Публикация, Показы план, Показы факт, PoP, Действия
- **Empty state:** «Пока нет рекламных кампаний»
- **Легенда статусов:** Черновик, На согласовании, Готова, В эфире, Завершена, Ошибка, Архив, Нет данных
- **Связи:** инфо-блоки — кампания связывает креативы, магазины/КСО, расписание публикации и план/факт; BI-отчётность и Excel в модуле Reports

**Status badges:** `.badge-draft` (light gray), `.badge-review` (blue), `.badge-ready` (green), `.badge-live` (green), `.badge-completed` (dark gray), `.badge-error` (red), `.badge-archived` (gray), `.badge-unknown` (light gray)

**Planned future API fields (не отображаются пока):**
- campaign_name, status, period_start/end, creative_count, store_count
- publication_status, planned_impressions, actual_impressions, pop_status
- Без campaign_id, creative_id, store_id, device_id, schedule_item_id, manifest_item_id, booking_id

**Future BI reporting (зафиксировано на этом шаге):**
- Power BI-like интерактивные дашборды, фильтры, срезы
- Drill-down от кампании → магазин → КСО → креатив
- Выгрузка в Excel с учётом выбранных фильтров
- Реализация в модуле Reports (не на этом шаге)

**Future workflow (не на этом шаге):**
- Создание/редактирование/удаление кампаний
- Согласование и публикация
- Backend campaign workflow
- Excel export и BI dashboards

**Security:**
- ❌ Нет campaign_id, creative_id, rendition_id, store_id, device_id
- ❌ Нет schedule_item_id, manifest_item_id, booking_id
- ❌ Нет manifest_hash, storage_key, minio, sha256, file_path, filename
- ❌ Нет device_secret, access_token, backend_url
- ❌ Нет Android TV, LED-шелф, ESL, Mobile App
- ✅ Все значения статичные (—)

## KSO Schedule page

**Структура:**
- **6 summary cards:** Запланировано кампаний, Активных периодов, Занято эфирного времени, Свободно эфирного времени, Конфликты расписания, Готово к публикации
- **Planning block:** Период кампании, Слот показа, Длительность креатива, Магазины/КСО, Проверка конфликтов, Публикация manifest
- **6 фильтров:** Период, Кампания, Филиал/магазин, КСО, Статус публикации, Занятость эфирного времени (все disabled)
- **Таблица (10 колонок):** Период, Кампания, Креативы, Магазины/КСО, Слот, Длительность, Занятость, Публикация, Конфликты, Действия
- **Empty state:** «Пока нет расписания»
- **Легенда статусов:** Запланировано, Готово, Опубликовано, Конфликт, Ошибка, Нет данных
- **Связи:** инфо-блоки — расписание связывает кампанию, креативы, магазины/КСО и публикацию manifest; занятость эфирного времени и BI/Excel в следующих шагах

**Status badges:** `.badge-scheduled` (blue), `.badge-ready` (green), `.badge-published` (indigo), `.badge-conflict` (red), `.badge-error` (red), `.badge-unknown` (light gray)

**Planned future API fields (не отображаются пока):**
- period_start/end, campaign_name, creative_count, store_count
- slot_interval, duration_seconds, occupancy_pct, publication_status, conflict_count
- Без campaign_id, creative_id, store_id, device_id, schedule_item_id, booking_id, manifest_item_id

**Future workflow (не на этом шаге):**
- Реальное бронирование слотов и проверка конфликтов
- Расчёт занятости эфирного времени
- Публикация manifest
- Excel export и BI dashboards

**Security:**
- ❌ Нет schedule_item_id, booking_id, manifest_item_id
- ❌ Нет campaign_id, creative_id, rendition_id, store_id, device_id
- ❌ Нет manifest_hash, storage_key, minio, sha256, file_path, filename
- ❌ Нет device_secret, access_token, backend_url
- ❌ Нет Android TV, LED-шелф, ESL, Mobile App
- ✅ Все значения статичные (—)

## Styling

- Минимальный CSS (311 строк) — без внешних CDN
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
# 108 tests: routes, navigation, content, security
```

## Следующие UI шаги

- Интеграция с backend API (безопасный API client)
- Auth/RBAC
- Реальные данные на dashboard
- CRUD кампаний/креативов
- Таблицы с реальными данными
- Формы создания/редактирования
- Графики и отчёты
