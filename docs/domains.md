# Домены системы

## Реализованные (Шаг 1)

### Organization
`backend/app/domains/organization/`
- **branches** — филиалы (Сеть → Филиал → Кластер → Магазин)
- **clusters** — кластеры
- **stores** — магазины
- **Ответственность:** иерархия торговой сети. Не знает о рекламе.

### Channels & Devices
`backend/app/domains/channels/`
- **channels** — типы каналов (kso, android_tv, esl, led, price_checker)
- **device_types** — типы устройств внутри канала
- **capability_profiles** — профили возможностей (разрешение, форматы, proof_type, cache_policy)
- **physical_devices** — физические устройства в магазинах
- **logical_carriers** — логические носители (экран, ценник, LED-полоса)
- **display_surfaces** — поверхности показа (привязаны к capability_profile)
- **Ответственность:** регистрация устройств, профили, иерархия носителей. Не знает о кампаниях.

## Заглушки (будут реализованы позже)

### Identity & Access (Шаг 2)
- Пользователи, роли, RBAC/RLS, LDAP, MFA, сессии

### Advertisers (Шаг 3)
- Рекламодатели, бренды, договоры, заказы

### Media Library (Шаг 4)
- Креативы, renditions, Creative QA, SHA-256, версионирование

### Campaigns & Placements (Шаг 5)
- Кампании, размещения, статусы, A/B, бюджеты

### Inventory (Шаг 6)
- Временные слоты, загрузка, конфликты, приоритеты, sold out

### Scheduling (Шаг 7)
- Плейлисты, расписания, проверка пересечений

### Orchestrator (Шаг 8)
- Перевод размещений в manifest-задания, симуляция, staged rollout

### Channel Adapters (Шаг 9)
- KSO Adapter, Android Adapter, ESL Adapter, LED Adapter
- Изолированы, не видят PostgreSQL/ClickHouse
- Работают через контракт: задание → доставка → ack → proof

### Device Gateway (Шаг 9)
- `backend/app/gateway/` — отдельный device-facing слой
- HTTPS/mTLS, регистрация устройств, manifest, PoP, heartbeat, команды

### Proof & Analytics (Шаг 10)
- PoP-события, ClickHouse, дедупликация

### Emergency (Шаг 11)
- Стоп-реклама, экстренные сообщения, возврат

### Audit (Шаг 11)
- Все действия пользователей и системы

### Operations (Шаг 12)
- Здоровье устройств, мониторинг, алерты
