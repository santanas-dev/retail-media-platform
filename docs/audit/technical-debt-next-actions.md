# Technical Debt — Next Actions

> **Статус:** 📋 Action Plan (37.14)
>
> Дата: 2026-06-16
> Ревизия: 9 (38.1 — physical KSO Phase 0–1 dry smoke executed)
>
> **Принцип:** Не закрывать весь долг сейчас. Закрывать только то, что блокирует следующий этап.
>
> **Обновление 38.1:** Phase 0 readiness + Phase 1 dry smoke выполнены на физической КСО (192.168.110.223).
> 6/6 smoke-кейсов пройдено на Python 3.6.9. Phase 2 (overlay render) НЕ одобрен.

---

## Сейчас (portrait player design завершён — 38.0.6+ implementation)

| # | Действие | Почему |
|---|---|---|
| 1 | **Ничего не менять в коде (пока)** | Не ломать regression baseline |
| 2 | **Поддерживать regression green** | ~3700 тестов — якорь качества |
| 3 | **38.0.6 — Contract & tests ✅** | 71 тест: geometry, forbidden zones, state rules, SLA |
| 4 | **38.0.7 — Shell plan support ✅** | 59 тестов: geometry, visibility, transitions, chromium flags |
| 5 | **38.0.8 — Local kill-switch ✅** | File flag `/run/verny/kso/kill_switch` + shell plan integration, 41 тест |
| 6 | **38.0.9 — State observer stub ✅** | Safe state contract, forbidden fields, 114 тестов |
| 7 | **38.0.10 — Local smoke on dev ✅** | Safe smoke harness, 42 теста |
| 8 | **38.0.11 — Manual test plan ✅** | Physical KSO test plan, 3 phases + stop criteria + rollback |
| 9 | **НЕ менять УКМ5, openbox, Chromium, systemd** | production кассовая система |
| 10 | **38.1 — Physical KSO Phase 0–1 ✅** | Dry smoke 6/6 на Python 3.6.9, Phase 2 ⛔ не одобрен |
| 11 | **38.1.2 — Phase 2 Overlay Attempted ⚠️** | Процесс запущен, xdotool окно НЕ нашёл, visual NOT confirmed |
| 12 | **38.1.4 — Fullscreen Idle Screensaver Design ✅** | Profile contract + interaction hide rules + 141 тест |

---

## Сразу после portrait player design (38.0.5)

| # | Действие | Debt ID | Оценка |
|---|---|---|---|
| 1 | Реализовать portrait player (новый модуль/профиль) | P0-4, P0-5 | ~5 дней |
| 2 | Интегрировать с sidecar/state-adapter | — | ~2 дня |
| 3 | Протестировать на test KSO (read-only, без перекрытия УКМ5) | — | ~1 день |
| 4 | Закрыть P0-1, P0-2 (device auth) параллельно | P0-1, P0-2 | ~1 день |

**Примечание:** Landscape player сохранён для будущих ландшафтных КСО, не удаляется.
DS API integration — secondary, не блокирует portrait player development.

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
