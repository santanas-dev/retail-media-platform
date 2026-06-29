# Current Project State — After B.2.2

> **Дата:** 2026-06-29 | **Commit:** `1d767d7`

## Где мы сейчас

Проект в фазе **B (Multichannel Core)** дорожной карты Re-Alignment.
Закрыто: A (полностью), B.1, B.2, B.2.1, B.2.2.
Следующий этап: **B.3 — Placement как отдельная сущность.**

## Source of Truth

| Документ | Роль |
|---|---|
| `docs/audit/tz-v2-5-gap-analysis-46-1.md` | ТЗ v2.5 gap analysis |
| `docs/product/tz-v2-5-realignment-roadmap-46-1.md` | Актуальная дорожная карта (A→H) |
| `docs/architecture/erd-v2-5-a2.md` | Целевая ERD (30 existing + 39 new) |
| `docs/audit/full-project-audit-after-b2-2.md` | Полный аудит (этот документ — краткая версия) |
| `docs/qa/b2-2-qa-pipeline-baseline.md` | QA baseline |

## Deprecated Documents

| Документ | Причина |
|---|---|
| `docs/product/roadmap-after-full-audit-45-7.md` | Старая roadmap (до Re-Alignment) |

## Что запрещено без отдельного решения

- Удалять legacy kso_* таблицы
- Выполнять DROP/DELETE/TRUNCATE
- Запускать физическую КСО (SSH/X11/Chromium/runner/sidecar/PoP)
- Включать production AV
- Переписывать теги .0–.6
- Добавлять JS/CDN/localStorage
- Менять RBAC/RLS/audit без security review
