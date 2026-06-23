# Technical Debt — Next Actions

> **Статус:** 📋 Action Plan (37.14)
>
> Дата: 2026-06-16
> Ревизия: 3 (38.0.3 — UKM5 integration decision)
>
> **Принцип:** Не закрывать весь долг сейчас. Закрывать только то, что блокирует следующий этап.
>
> **Обновление 38.0.3:** Physical test KSO — 768×1024 портрет, УКМ5 монопольно владеет экраном.
> KSO Player на этот КСО не устанавливается. Принят UKM5/DS integration path.
> Приоритет: получить ответ поставщика УКМ5/DS (P0-4) перед любыми установками.

---

## Сейчас (пока нет ответа поставщика УКМ5/DS)

| # | Действие | Почему |
|---|---|---|
| 1 | **Ничего не менять в коде** | Не ломать regression baseline |
| 2 | **Поддерживать regression green** | ~3700 тестов — якорь качества |
| 3 | **НЕ устанавливать KSO Player на test KSO** | P0-4: геометрия 768×1024 портрет, принят UKM5/DS path |
| 4 | **НЕ разворачивать backend на КСО** | Недостаточно RAM, риск конфликта с УКМ5 |
| 5 | **НЕ менять УКМ5, openbox, Chromium, systemd** | production кассовая система |
| 6 | **Отправить вопросы поставщику УКМ5/DS** | `docs/audit/ukm5-test-kso-integration-decision.md` §4 |
| 7 | **Изучить DS API документацию** | Если DS on-premise доступен |

---

## Сразу после ответа поставщика УКМ5/DS

| # | Действие | Debt ID | Оценка |
|---|---|---|---|
| 1 | Спроектировать DS API integration adapter | P0-4 | ~2 дня |
| 2 | Реализовать DS API client (content upload, schedule, PoP) | P0-4 | ~3 дня |
| 3 | Протестировать на test KSO (read-only, без изменения УКМ5) | P0-4 | ~1 день |
| 4 | Если DS API недоступен — спроектировать embedded widget/iframe | P0-4 | ~2 дня |

**Примечание:** Установка KSO runtime на test KSO не производится до решения P0-4.
Device auth (P0-1, P0-2) и persistent session (P0-3) закрываются параллельно.

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
