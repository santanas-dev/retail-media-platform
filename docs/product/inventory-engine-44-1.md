# Inventory Engine — 44.1

Базовая production-ready модель инвентаря для v1 KSO:
свободное/занятое/зарезервированное рекламное время,
конфликты, sold out и прогноз доступных показов.

**Дата:** 2026-06-16
**HEAD:** TBD (commit)

---

## Что сделано

### 1. Модель данных

Расширена существующая модель `BookingItem`:

| Поле | Назначение |
|---|---|
| `reservation_type` | Тип резерва: `campaign` (по умолчанию), `internal` (внутренние нужды), `emergency` (экстренные), `filler` |

Миграция: `031_add_reservation_type_to_booking_items.py` (down_revision: `030`).

### 2. Сервис доступности (availability)

Функция `calculate_availability` расширена:

- **sold_out** — явный флаг, когда `available <= 0`
- **occupancy_pct** — процент занятости: `(confirmed + reserved) / capacity`
- **internal_booked** — слоты для внутренних нужд
- **emergency_booked** — слоты для экстренных показов
- **store_code / store_name** — название магазина в ответе
- **alternatives** — предложения при sold out/limited
- **reasons** — причины на русском бизнес-языке
- **summary** — агрегация: total_units, total_capacity, sold_out_units, limited_units

### 3. Прогноз показов (forecast v1)

Новый сервис `calculate_forecast`:

- **Формула:** capacity_spots × spots_per_loop × days
- **Учитывает:** количество КСО, активные правила нагрузки
- **НЕ учитывает:** фактический трафик, чеки
- **confidece:** `low`
- **disclaimer:** «Оценка по расписанию и количеству КСО. Не учитывает фактический трафик и чеки.»

### 4. Снапшот инвентаря

`get_inventory_snapshot(scope)` — агрегация по филиалу/кластеру/магазину:

- total_units, sellable_units
- with_rules (с активными правилами нагрузки)
- with_bookings (с активными бронированиями)
- total_kso_devices, active_kso_devices

### 5. API endpoints

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/inventory/availability` | Расширен: sold_out, business labels, summary, alternatives |
| POST | `/api/inventory/forecast` | **Новый:** прогноз показов v1 |
| GET | `/api/inventory/snapshot` | **Новый:** scope-снапшот инвентаря |
| GET/POST/PUT | `/api/inventory-units` | Без изменений |
| GET/POST/PUT | `/api/inventory-units/{id}/capacity-rules` | Без изменений |
| GET/POST/PUT | `/api/bookings` | Расширен: reservation_type в items |

Все endpoints: RBAC (`inventory.read`, `bookings.read`, `bookings.manage`, `bookings.approve`).

### 6. Портал

- **Страница `/inventory`** — рекламное время: summary cards, forecast, availability table, snapshot
- **Sidebar:** пункт «⏱ Рекламное время» в разделе «Аналитика»
- **BackendClient:** методы `get_inventory_availability`, `get_inventory_forecast`, `get_inventory_snapshot`
- **Без JS/CDN/localStorage** — server-side HTML/CSS/Jinja2
- **Русский бизнес-язык** — все статусы и причины на русском

### 7. Тесты

| Слой | Файл | Количество |
|---|---|---|
| Backend | `backend/tests/test_inventory_engine_441.py` | 20 тестов |
| Portal | `apps/portal-web/tests/test_main.py::TestInventoryPage44_1` | 8 тестов |

Темы:
- day_capacity, days_in_range
- sold_out detection (no capacity → unavailable)
- availability with business labels
- forecast v1 (estimate + disclaimer)
- reservation_type (campaign/internal/emergency)
- safety: no secrets/tokens/UUID leakage
- router endpoint presence
- business language (Russian only, no technical)

---

## Что НЕ делаем в 44.1

- ❌ Сложная коммерческая оптимизация
- ❌ Интеграция с чеками / фактическим трафиком
- ❌ ML/статистический forecast
- ❌ Визуальные отчёты (графики) — без JS невозможно
- ❌ Полная мультиканальность (КСО first channel)

---

## Что закрыто в TZ Matrix

Из TZ Compliance Matrix (44.0) переводятся из 🟡 PARTIAL в ✅ DONE:

| # | Пункт | Было | Стало |
|---|---|---|---|
| 7.4 | Управление инвентарём (свободное/занятое/зарезервированное время) | 🟡 PARTIAL | ✅ DONE |
| 7.4a | Sold out detection | ⬜ NOT_STARTED | ✅ DONE |
| 7.4b | Прогноз показов | ⬜ NOT_STARTED | ✅ DONE |
| 7.4c | Альтернативы при sold out | ⬜ NOT_STARTED | ✅ DONE |

---

## Что осталось для v1 production

- ClickHouse-нагрузка для фактического PoP (ждёт физического PoP)
- Load testing инвентаря
- Сложный оптимизатор размещения
- Интеграция прогноза с реальным трафиком
