# Technical Debt — Next Actions

> **Статус:** 📋 Action Plan (37.14)
>
> Дата: 2026-06-16
>
> **Принцип:** Не закрывать весь долг сейчас. Закрывать только то, что блокирует следующий этап.

---

## Сейчас (пока нет physical test KSO)

| # | Действие | Почему |
|---|---|---|
| 1 | **Ничего не менять в коде** | Не ломать regression baseline |
| 2 | **Поддерживать regression green** | ~3700 тестов — якорь качества |
| 3 | **Подготовить конфиги для test KSO** | `sidecar.env`, `player.env`, `state-adapter.env` — заполнить схемы, не реальные значения |
| 4 | **Получить параметры от администратора** | Backend URL, device_code, device_secret, hostname test KSO, sudo-доступ |
| 5 | **Проверить сетевую доступность** | `curl` до backend `/health`, manifest endpoint, PoP endpoint с test KSO |
| 6 | **Провести deployment dry run по checklist** | `docs/audit/test-kso-deployment-dry-run.md` |

---

## Сразу после появления test KSO

| # | Действие | Debt ID | Оценка |
|---|---|---|---|
| 1 | **Добавить device auth на manifest endpoint** | P0-1 | ~2 часа |
| 2 | **Добавить device auth на PoP endpoint** | P0-2 | ~2 часа |
| 3 | **Persistent session store для portal** | P0-3 | ~4 часа |
| 4 | Установить KSO runtime через bootstrap | — | ~1 час |
| 5 | Заполнить реальные конфиги | — | ~30 мин |
| 6 | Запустить сервисы, проверить health | — | ~30 мин |
| 7 | Пройти 11 шагов E2E readiness gate | — | ~2 часа |

**Итого на P0:** ~1 день работы.

---

## После успешной test KSO проверки (перед pilot rollout)

| # | Действие | Debt ID | Оценка |
|---|---|---|---|
| 1 | RLS на всех query-level путях | P1-2 | ~3 дня |
| 2 | Реальный advertiser/brand/order контекст | P1-3 | ~2 дня |
| 3 | Creative approval lifecycle | P1-4 | ~2 дня |
| 4 | Media delivery через MinIO | P1-5 | ~3 дня |
| 5 | Production device credentials / mTLS | P1-6 | ~3 дня |
| 6 | Замена test-kso врапперов на enterprise | P1-7 | ~5 дней |
| 7 | Portal dashboard + reports backend-driven | P1-8 | ~3 дня |
| 8 | Observability basics (logging, metrics) | P1-9 | ~2 дня |
| 9 | Запуск на 3–5 КСО, 72ч стабильности | — | ~1 неделя |

**Итого на P1:** ~3–4 недели.

---

## После pilot rollout

| # | Действие | Когда |
|---|---|---|
| 1 | Консолидация enterprise + KSO PoP доменов | После pilot |
| 2 | Консолидация manifest/publication доменов | После pilot |
| 3 | Production hardening (TLS, scaling, rate limiting) | После pilot |
| 4 | CI/CD, backup, audit trail | После pilot |
| 5 | Power BI reports, Excel export | По запросу бизнеса |
| 6 | Performance benchmarks, E2E тесты | По мере необходимости |

---

## Что нельзя делать сейчас

| Запрещено | Почему |
|---|---|
| Менять KSO runtime код | Нарушит baseline, заблокирует physical test |
| Добавлять новый функционал | Затянет проект |
| Закрывать P1/P2/P3 долг | Не блокирует physical test |
| Начинать pilot rollout без test KSO | Нет подтверждения на реальном железе |
| Рефакторить архитектуру | Риск дестабилизации |

---

## Файлы

- `docs/audit/technical-debt-next-actions.md` — этот документ
- `docs/audit/technical-debt-register.md` — полный реестр (36 пунктов)
