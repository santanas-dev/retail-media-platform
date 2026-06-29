# Domain Boundaries v2.5 — A.2

> **Дата:** 2026-06-29 | **Этап:** A.2  
> **Основание:** ТЗ v2.5 Sections 24.2-24.3, Table 28  
> **Статус:** ПРОЕКТ

---

## 1. Campaign Domain

**Ответственность:** Кампании, рекламодатели, заказы, согласования, workflow.

| ✅ Можно | ❌ Нельзя |
|---|---|
| CRUD campaigns, placements, advertisers, brands, contracts, orders | Знать технические детали Chromium, Android, ESL API, LED-контроллеров |
| Статусный workflow: draft→review→approved→live→completed | Публиковать напрямую на устройство |
| Связь campaign→placement→creative | Рассчитывать инвентарь (это Inventory Domain) |
| Отправка на согласование | Генерировать manifest (это Orchestrator) |

**Таблицы:** campaigns, placements, placement_targets, campaign_status_history, campaign_creatives, advertisers, brands, contracts, orders, approval_requests.  
**API:** `/api/campaigns/*`, `/api/placements/*`, `/api/advertisers/*`, `/api/approvals/*`  
**Публикует:** `publish.requested`, `campaign.status.changed`  
**Читает:** `proof.received` (для статуса выполнения)

---

## 2. Inventory Domain

**Ответственность:** Расчёт доступной ёмкости, sold out, приоритеты, прогноз, компенсации.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Расчёт свободного/занятого/зарезервированного времени | Зависеть от конкретной таблицы КСО |
| Правила ёмкости по каналам | Менять статусы кампаний |
| Прогноз показов | Принимать решения о публикации |
| Проверка конфликтов | |

**Таблицы:** inventory_rules, inventory_reservations, inventory_snapshots, capacity_units, conflict_checks.  
**API:** `/api/inventory/*`  
**Читает:** `campaign.created`, `placement.updated`  
**Публикует:** `inventory.snapshot.generated`

---

## 3. Content Domain

**Ответственность:** Креативы, версии, renditions, модерация, MinIO, SHA-256.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Загрузка, валидация, хранение креативов | Публиковать на устройство напрямую |
| Создание renditions под каналы | Принимать решение о публикации кампании |
| Модерация: approve/reject/change | |
| SHA-256, AV проверка | |

**Таблицы:** creatives, creative_versions, creative_renditions, rendition_validations, channel_previews, creative_moderation_tasks.  
**API:** `/api/creatives/*`, `/api/renditions/*`  
**Зависимость:** MinIO (через абстракцию storage).  
**НЕ зависит от:** конкретных устройств, campaign workflow.

---

## 4. Channel Domain

**Ответственность:** Каналы, типы устройств, capability profiles, адаптеры.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Справочники каналов, device_types, profiles | Менять бизнес-статусы кампаний |
| Регистрация адаптеров | Рассчитывать инвентарь |
| Capability matrix: форматы, разрешения, PoP-режимы | Генерировать manifest (это Orchestrator) |
| | Принимать proof (это Proof Domain) |

**Таблицы:** channels, channel_adapters, channel_capabilities, device_types, capability_profiles, media_constraints, proof_capabilities, runtime_versions.  
**API:** `/api/channels/*`, `/api/device-types/*`

---

## 5. Orchestrator Domain

**Ответственность:** Перевод утверждённого placement в задания для каналов и устройств.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Расчёт target surfaces по правилам placement | Принимать решения о статусе кампании |
| Сборка channel-neutral manifest | Обращаться напрямую к vendor API |
| Симуляция перед публикацией | Менять бизнес-правила приоритетов |
| Staged rollout и rollback | |
| Управление версиями manifest | |

**Таблицы:** playlist_versions, manifest_versions, manifest_targets, adapter_payloads, orchestrator_tasks, adapter_delivery_attempts.  
**API:** internal worker API  
**Публикует:** `manifest.generated`, `channel.task.created`  
**Читает:** `publish.requested`, `device.apply.ack`, `adapter.delivery.attempted`

---

## 6. Device Gateway Domain

**Ответственность:** API для устройств, плееров, шлюзов. Регистрация, auth, heartbeat, manifest pull, приём PoP.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Device registration + auth | Менять бизнес-логику кампаний |
| Heartbeat приём и статус устройств | Рассчитывать инвентарь |
| Manifest pull с ETag/304 | Валидировать креативы |
| Приём PoP batch с дедупликацией | |
| Отправка команд устройству | |

**Таблицы:** physical_devices, device_certificates, device_status, device_commands, device_events, device_heartbeats (ClickHouse).  
**API:** `/device/*` (отдельный контур)  
**Публикует:** `device.apply.ack`, `proof.received`, `device.heartbeat.received`  
**Читает:** `manifest.generated`

---

## 7. Proof Domain

**Ответственность:** Валидация, дедупликация и хранение proof-событий.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Приём PoP batch с проверкой подписи | Принимать неподписанные события как коммерческое доказательство |
| Идемпотентная дедупликация | Строить отчёты (это Analytics Domain) |
| Запись в ClickHouse | Менять статусы кампаний |
| Различение proof_type (real_playback vs delivery_ack) | |

**Таблицы (ClickHouse):** proof_events, apply_ack_events, delivery_events.  
**API:** `/device/pop/batch` (через Device Gateway)  
**Читает:** `device.apply.ack`  
**Публикует:** `proof.received` (валидированные события для Analytics)

---

## 8. Analytics Domain

**Ответственность:** Отчёты, дашборды, экспорт, SLA, план/факт.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Агрегация данных из ClickHouse | Менять статусы кампаний |
| Построение дашбордов: сеть, кампания, магазин, устройство | Рассчитывать инвентарь в реальном времени |
| Экспорт PDF/XLSX/CSV | |
| Расчёт недопоказов и причин | |
| Advertiser read-only portal | |

**Таблицы (ClickHouse):** campaign_daily_stats, inventory_daily_snapshots (предагрегаты).  
**API:** `/api/analytics/*`  
**Читает:** `proof.received`, `device.heartbeat.received`

---

## 9. Emergency Domain

**Ответственность:** Высокоприоритетные команды: стоп, сообщение, возврат.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Stop ads, emergency message, resume | Обходить approval/RBAC |
| Применение по уровням: device→network | Выполняться без MFA + audit |
| Аудит всех emergency-действий | |

**Таблицы:** emergency_events, emergency_targets.  
**API:** `/api/emergency/*` (MFA required)  
**Публикует:** `emergency.requested`  
**Зависимость:** Orchestrator (для доставки), Device Gateway (для статуса)

---

## 10. Operations Domain

**Ответственность:** Мониторинг, rollout, rollback, health, incident response.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Мониторинг устройств/адаптеров | Обходить согласования кампаний |
| Staged rollout новых версий | Менять права пользователей |
| Health dashboard, алерты | |
| Rollback при превышении порога ошибок | |

**Таблицы:** rollout_plans, rollout_steps, adapter_health, feature_flags.  
**API:** `/api/operations/*`  
**Читает:** `device.heartbeat.received`, `device.error.received`, `adapter.delivery.attempted`

---

## 11. Audit / Security Domain

**Ответственность:** Аудит действий, журналирование, ИБ.

| ✅ Можно | ❌ Нельзя |
|---|---|
| Запись всех критичных действий | Блокировать бизнес-операции (только audit) |
| Хранение audit trail | Содержать secrets/tokens в audit |
| ClickHouse для долгосрочного аудита | |

**Таблицы:** admin_audit_events, login_audit_events, audit_events_operational.  
**API:** `/api/audit/*`, `/api/admin/audit`  
**Читает:** все доменные события (через trace_id)

---

## 12. Cross-Domain Rules

| Запрет | Почему |
|---|---|
| Adapter → PostgreSQL/ClickHouse/MinIO напрямую | Только через утверждённые API |
| Campaign → device/vendor API | Только через Orchestrator |
| Content → publish to device | Только через Orchestrator |
| Proof → принимать как коммерческое без подписи | Риск недостоверных данных |
| Operations → bypass approval | Нарушение maker-checker |
| Emergency → без audit | Нарушение compliance |
| Любой домен → менять чужие статусы | Нарушение domain boundaries |
