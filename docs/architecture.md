# Retail Media Platform — Архитектура

## Принципы

### 1. Channel-agnostic core
Ядро системы **не зависит** от типа цифрового носителя. Кампании, инвентарь, расписания, модерация, согласование и отчётность работают с универсальными сущностями (каналы, устройства, поверхности, capability profiles).

**КСО — первый реализуемый канал, но не основа архитектуры.**

### 2. Строгое разделение слоёв

```
┌──────────────────────────────────┐
│           CORE (ядро)            │
│  Campaigns / Inventory /         │
│  Scheduling / Media / RBAC       │
├──────────────────────────────────┤
│     CHANNEL ORCHESTRATOR         │
│  Placement → поверхности →       │
│  universal signed JSON manifest  │
├──────────────────────────────────┤
│     CHANNEL ADAPTER LAYER        │
│  KSO Adapter / Android Adapter / │
│  ESL Adapter / LED Adapter       │
├──────────────────────────────────┤
│       DEVICE GATEWAY             │
│  HTTPS/mTLS / registration /     │
│  manifest delivery / PoP / cmd   │
└──────────────────────────────────┘
```

### 3. Границы
- **Core** не вызывает Adapter напрямую
- **Adapter** не читает PostgreSQL/ClickHouse напрямую
- **Device Gateway** — отдельный device-facing слой (backend/app/gateway/), не бизнес-домен
- Adapters — backend/worker слой (backend/app/domains/adapters/), не клиентский runtime
- Players — клиентские runtime-компоненты на устройствах (players/)

### 4. Manifest
- Универсальный подписанный JSON manifest
- Общая часть + channel-specific adapter_payload
- **JWT/access token запрещён в URL**
- Медиа: относительный endpoint `/api/device/media/{id}` через Device Gateway
- Signed URL допустим только если: не раскрывает access token, срок жизни — минуты, генерируется Gateway при запросе

### 5. Безопасность
- Production: HTTPS + mTLS/сертификаты устройств
- mTLS — отдельный production-hardening шаг (не на старте)
- HTML5/JS-контент: **запрещён на первом релизе**. Только изображения и видео
- HTML5 sandbox — архитектурно предусмотрен, реализация только после согласования ИБ

### 6. Технологический стек

| Компонент | Технология |
|-----------|-----------|
| Бэкенд | Python / FastAPI |
| БД операционная | PostgreSQL 16 |
| БД аналитики | ClickHouse |
| Кэш / очереди | Redis |
| Хранение медиа | MinIO (S3) |
| Плеер КСО | Chromium kiosk-mode |
| Фронтенд | React + TypeScript |

### 7. Модель носителей
```
Channel → Device Type → Physical Device → Logical Carrier → Display Surface
                                                              ↑
                                                     Capability Profile
```
