# Technical Debt — Next Actions

> **Статус:** 📋 Action Plan (37.14)
>
> Дата: 2026-06-16
> Ревизия: 2 (37.15 — isolated test KSO risk acceptance)
>
> **Принцип:** Не закрывать весь долг сейчас. Закрывать только то, что блокирует следующий этап.
>
> **Обновление 37.15:** Physical test KSO в изолированном контуре — P0 временно принят как controlled risk. Pilot rollout всё ещё требует закрытия P0.

---

## Сейчас (пока нет physical test KSO)

| # | Действие | Почему |
|---|---|---|
| 1 | **Ничего не менять в коде** | Не ломать regression baseline |
| 2 | **Поддерживать regression green** | ~3700 тестов — якорь качества |
| 3 | **Подготовить конфиги для test KSO** | `sidecar.env`, `player.env`, `state-adapter.env` — заполнить схемы, не реальные значения |
| 4 | **Получить параметры от администратора** | Backend URL, device_code, device_secret, hostname test KSO, sudo-доступ |
| 5 | **Проверить сетевую доступность** | `curl` до backend `/health`, manifest endpoint, PoP endpoint с test KSO |
| 6 | **Подтвердить изолированный контур** | Нет internet exposure, firewall allowlist, только synthetic данные |
| 7 | **Провести deployment dry run по checklist** | `docs/audit/test-kso-deployment-dry-run.md` |

---

## Сразу после появления test KSO

| # | Действие | Debt ID | Оценка |
|---|---|---|---|
| 1 | Установить KSO runtime через bootstrap | — | ~1 час |
| 2 | Заполнить реальные конфиги | — | ~30 мин |
| 3 | Запустить сервисы, проверить health | — | ~30 мин |
| 4 | Пройти 11 шагов E2E readiness gate | — | ~2 часа |

**Примечание:** P0-1, P0-2, P0-3 временно приняты как controlled risk для isolated test KSO.
Device auth НЕ добавляется до pilot rollout — это осознанное решение для ускорения physical test.

---

## После успешной test KSO проверки (перед pilot rollout)

| # | Действие | Debt ID | Оценка |
|---|---|---|---|
| 1 | **Закрыть P0:** device auth на manifest + PoP + persistent session | P0-1, P0-2, P0-3 | ~1 день |
| 2 | RLS на всех query-level путях | P1-2 | ~3 дня |
| 3 | Реальный advertiser/brand/order контекст | P1-3 | ~2 дня |
| 4 | Creative approval lifecycle | P1-4 | ~2 дня |
| 5 | Media delivery через MinIO | P1-5 | ~3 дня |
| 6 | Production device credentials / mTLS | P1-6 | ~3 дня |
| 7 | Замена test-kso врапперов на enterprise | P1-7 | ~5 дней |
| 8 | Portal dashboard + reports backend-driven | P1-8 | ~3 дня |
| 9 | Observability basics (logging, metrics) | P1-9 | ~2 дня |
| 10 | Запуск на 3–5 КСО, 72ч стабильности | — | ~1 неделя |

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
