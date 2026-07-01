# F.1 — Analytics Schemas / Contracts

**Date:** 2026-07-01
**Status:** ✅ COMPLETED
**Commit:** (pending)

---

## Что создано

### Analytics domain: `backend/app/domains/analytics/`

| Файл | Содержание |
|---|---|
| `__init__.py` | Public API — все схемы и сервисные контракты |
| `schemas.py` | 14 Pydantic v2 моделей |
| `service.py` | 6 сервисных контрактов + 5 validation helpers |

### Schemas

| Модель | Назначение |
|---|---|
| `AnalyticsTimeRange` | date_from, date_to, timezone, granularity (total/day/hour) |
| `AnalyticsScope` | 9 фильтров: advertiser, campaign, placement, store, device, channel |
| `DeliveryMetricQuery` | Запрос метрик: источники, scope, exclude_dry_run |
| `DeliveryMetricResult` | Ответ: ok, метрики, breakdowns, warnings/errors |
| `DeliveryMetricsSummary` | 14 агрегированных метрик |
| `DeliveryBreakdown` | Разбивка по измерению (campaign/placement/store/device/channel/day/hour) |
| `DeviceHealthQuery` | Запрос здоровья устройств с порогом silent_threshold |
| `DeviceHealthResult` | Ответ: список DeviceHealthItem |
| `DeviceHealthItem` | Статус устройства: ok/warning/error/silent/unknown |
| `PopEventNormalized` | Нормализованное PoP-событие из KSO или Enterprise Gateway |
| `PlannedVsDeliveredQuery` | Запрос сравнения плана и факта |
| `PlannedVsDeliveredResult` | Ответ: expected, delivered, gap, status |
| `AnalyticsIssue` | Структурированная ошибка/предупреждение |

### Service contracts (skeleton — логика в F.2+)

| Функция | Статус |
|---|---|
| `normalize_pop_events(query)` | Возвращает `[]` в F.1 |
| `calculate_delivery_metrics(query)` | Возвращает structured empty result, валидирует query |
| `calculate_device_health(query)` | Возвращает structured empty result |
| `calculate_planned_vs_delivered(query)` | Возвращает structured empty result |
| `exclude_dry_run_events(events)` | **Полная реализация** — фильтрует `is_dry_run=True` |
| `build_analytics_issue(...)` | Строит `AnalyticsIssue` |

### Validation helpers

| Helper | Что делает |
|---|---|
| `validate_time_range(date_from, date_to)` | date_from ≤ date_to |
| `validate_granularity(g)` | g ∈ {total, day, hour} |
| `validate_analytics_scope(scope)` | Пустой scope = global (allowed) |
| `validate_no_secrets_in_analytics_payload(payload)` | 20 forbidden keys рекурсивно |

## Source types

PopEventNormalized.source_type различает:
- `legacy_kso` → KsoProofOfPlayEvent (code-based)
- `enterprise_gateway` → ProofOfPlayEvent (FK-based)

## Dry-run exclusion

- `PopEventNormalized.is_dry_run = True` — маркер dry-run события
- `exclude_dry_run_events()` — фильтрует dry-run события
- `DeliveryMetricQuery.exclude_dry_run = True` (default)
- Dry-run UniversalManifest preview НЕ попадает в production analytics

## Чего F.1 НЕ делает

- ❌ Не создаёт API (нет router.py)
- ❌ Не создаёт миграции
- ❌ Не меняет БД
- ❌ Не меняет PoP ingestion
- ❌ Не меняет Device Gateway
- ❌ Не меняет KSO Adapter
- ❌ Не включает ClickHouse
- ❌ Не меняет portal
- ❌ Не читает тяжёлые данные (skeleton only)

## Тесты

**F.1 targeted:** 42 tests (все pass)

| Категория | Тестов |
|---|---|
| TimeRange validation | 4 |
| Scope validation | 3 |
| Delivery metric schemas | 5 |
| Device health schemas | 3 |
| PopEventNormalized | 4 |
| Planned vs delivered | 2 |
| AnalyticsIssue | 1 |
| Service contracts | 7 |
| No-secrets | 6 |
| Boundaries | 6 |
| Compatibility | 1 |

## Baseline

| Метрика | До F.1 | После F.1 |
|---|---|---|
| Backend collection | 1877 | 1919 |
| E-series | 217/217 | 217/217 |

## GO/NO-GO для F.2

**GO** ✅ — F.2 может начинать PoP Mapping & Normalization Service.
F.1 создал полную контрактную базу: схемы, сервисные интерфейсы, валидацию.
Все skeleton-функции возвращают structured результаты, готовые к наполнению в F.2.
