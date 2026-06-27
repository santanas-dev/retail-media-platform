# Release Scope — v1 KSO Pilot & Production (44.0)

**Дата:** 2026-06-16
**HEAD:** a5c752e

---

## v1 KSO Pilot — Что входит

### ✅ Backend (готово, 690 тестов)

- 108 API endpoints, 16 доменов
- Campaigns: CRUD + lifecycle (draft→pending→approved→published)
- Creatives: upload + QA (768×1024 portrait, PNG/JPEG/MP4)
- Schedules: CRUD + time slots
- Approvals: maker-checker workflow
- Publications: batch lifecycle → manifest generation
- Reports: 4 CSV exports (campaigns, airtime, conflicts, publications)
- Device gateway: device registration, auth (bcrypt→JWT), heartbeat
- PoP API: event ingestion
- RBAC: 8 ролей, 47 permissions
- RLS: 7 scope types, query-level enforcement
- Audit: dual audit trail (login + admin actions)
- Docker Compose: 5 сервисов (postgres, clickhouse, minio, redis, nginx)

### ✅ Portal (готово, 701 тест)

- 50 routes, 19 templates, 34 KB CSS
- Server-side HTML/CSS/Jinja2 (без JS/CDN/localStorage)
- Изолированный логин (auth_base.html)
- Русский бизнес-язык, тёмный enterprise UI
- Dashboard, Campaigns, Creatives, Schedule, Approvals, Publications
- Reports с CSV export, Device Dashboard (7 колонок)
- Readiness page с acceptance checklist
- Admin: user CRUD, роли, RLS scopes

### 🟡 KSO Components (код готов, не запущен физически)

| Компонент | Тесты | Статус |
|---|---|---|
| kso_player | 2,072 | Код готов, не запущен |
| kso_sidecar_agent | 1,838 | Код готов, не запущен |
| kso_state_adapter | 86 | Код готов, не подключён к UKM5 |
| infra/kso-linux | 227 | Bootstrap + systemd готовы |

### 🔴 P0 Blockers (физические)

| Блокер | Описание | Зависимость |
|---|---|---|
| 1. Проверка сканера | Физический сканер не протестирован | Доступ к КСО |
| 2. Доставка пакета | Manifest не доставлен на КСО | Блокер 1 |
| 3. Запуск агента | Sidecar не запущен на КСО | Блокер 2 |
| 4. Длительная проверка | 48h+ прогон не выполнялся | Блокеры 1-3 |
| 5. Fleet rollout | Не утверждён | Блокеры 1-4 |

---

## v1 KSO Production — Что добавить

| Компонент | Статус | Описание |
|---|---|---|
| Физические P0 blockers | 🔴 | Закрыть все 5 |
| Мониторинг | 📅 | Prometheus/Grafana |
| Резервное копирование | 📅 | Automated backup для PostgreSQL, MinIO |
| Логирование | 🟡 | Централизованный сбор логов |
| CI/CD | 📅 | GitHub Actions или аналог |
| Нагрузочное тестирование | 📅 | До 100 КСО |
| AD/SSO | 📅 | Для enterprise-клиентов |
| mTLS | 📅 | Для защищённых инсталляций |
| Production деплой | 📅 | Ansible/Kubernetes |

---

## v2 Multichannel — Что переносится

| Компонент | Описание |
|---|---|
| Android TV player | Адаптер под Android TV |
| LED/ESL адаптеры | Shelf-edge displays, ценники |
| Mobile app | Мобильное приложение для малого бизнеса |
| Многоканальный dashboard | Единый интерфейс для всех каналов |
| Бюджетирование | Финансовый модуль |
| Визуальные отчёты | Графики (потребуют JS или server-side рендеринг) |
| Очереди (Kafka/RabbitMQ) | Для высокой нагрузки |
| HA / горизонтальное масштабирование | Multi-instance |
| React/TypeScript frontend | Если принято решение отказаться от server-side |

---

## Осознанные отклонения (deviations)

См. `docs/audit/deviation-register-44-0.md`:

1. **Server-side HTML вместо React** — security-first решение для v1
2. **768×1024 portrait вместо Full HD** — физическое ограничение test KSO
3. **Монолит FastAPI вместо микросервисов** — domain-driven, разделение на уровне сервисов
4. **Мультиканальность отложена** — KSO first channel

---

## Статистика

| Метрика | Значение |
|---|---|
| Всего пунктов ТЗ | 75 |
| ✅ DONE | 44 (59%) |
| 🟡 PARTIAL | 15 (20%) |
| 🔴 BLOCKED | 5 (7%) |
| 📅 DEFERRED | 10 (13%) |
| ⚠️ DEVIATION | 1 (1%) |
| Всего тестов | 5,614 |
| Всего документов | 104 .md |
| Python файлов | 3,688 |
