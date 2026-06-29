# B.3 Placement Design Gate

> **Дата:** 2026-06-29 | **Commit:** `aada294` | **Статус:** DESIGN ONLY
> **Фаза:** B.3.0 — проектирование (не реализация)

---

## 1. Executive Summary

Placement в ТЗ v2.5 — центральная сущность, связывающая Campaign с каналами, поверхностями показа, временными слотами и статусами. Текущая БД содержит **2 параллельные модели целеуказания** (campaign_targets + placement_targets) и **таблицу placements без ORM/API**. B.3 должен:

1. Сделать Placement полноценной ORM-сущностью с API
2. Установить связь Campaign 1→N Placements
3. Добавить channel_id в placements
4. Сохранить placement_targets как связку Placement→DisplaySurface
5. Campaign_targets — legacy, не удалять
6. Не сломать существующие workflows

---

## 2. Current State

### 2.1 Таблицы и данные

| Таблица | Строк | Назначение | Проблема |
|---|---|---|---|
| `placements` | 1 | Универсальное размещение | Нет channel_id, нет ORM, нет API |
| `placement_targets` | 1 | Цели размещения (store/surface) | Работает, FK→display_surfaces ✅ |
| `campaign_targets` | 2 | Цели кампании (legacy) | Дублирует placement_targets |
| `campaign_channels` | 3 | Каналы кампании | Дублирует будущий placement.channel_id |
| `kso_placements` | 1 | KSO-специфичное размещение | FK→kso_devices, не универсальное |
| `campaigns` | 6 | Кампании | Нет relationship→placements |
| `generated_manifests` | ? | Манифесты | FK→kso_placements (legacy!) |
| `proof_events` | 2 | PoP события | FK→placements ✅ |

### 2.2 Схема placements (текущая)

```
placements
├── id                  UUID PK
├── campaign_id         UUID FK→campaigns      ← есть
├── placement_code      VARCHAR(64) UNIQUE     ← есть
├── name                VARCHAR(255)           ← есть
├── status              VARCHAR(20)            ← есть
├── priority            INTEGER               ← есть
├── start_date          DATE                  ← есть
├── end_date            DATE                  ← есть
├── created_by          UUID FK→users
├── created_at          TIMESTAMPTZ
├── updated_at          TIMESTAMPTZ
❌ channel_id           — ОТСУТСТВУЕТ ← КЛЮЧЕВАЯ ПРОБЛЕМА
❌ channel_type         — ОТСУТСТВУЕТ ← для универсальности
```

### 2.3 ORM/API статус

| Слой | placements | placement_targets |
|---|---|---|
| ORM model | ❌ Нет | ❌ Нет |
| Service | ❌ Нет | ❌ Нет |
| API router | ❌ Нет | ❌ Нет |
| Seed | ❌ Нет (SQL в A.3) | ✅ _link_placement_target_to_surface() |
| Tests | ❌ Нет | ❌ Нет |

### 2.4 Campaign → Placement связь

**Текущее:** Campaign НЕ знает о placements.
- Campaign.relationships: channels, targets, renditions — но **нет placements**
- Campaign submit/approve проверяет channels + targets + renditions — **не проверяет placements**

### 2.5 Publication → Placement связь

**Текущее:** Publication batch НЕ использует placements.
- PublicationBatch: FK→campaign_id, schedule_run_id, booking_id — **нет placement_id**
- generate_manifests: группирует по inventory_units — **не по placements**
- PublicationTarget: FK→inventory_unit_id — **нет placement_id**

---

## 3. Current Problems

### P0 — Двойное целеуказание

`campaign_targets` и `placement_targets` — две параллельные модели с почти идентичной структурой:

```
campaign_targets:  campaign_id→(branch|cluster|store|carrier|surface)
placement_targets: placement_id→(store|carrier|surface)
```

**Решение B.3:** placement_targets становится primary, campaign_targets — legacy.

### P0 — Нет channel_id в placements

Сейчас канал задаётся на уровне Campaign (campaign_channels), а не Placement. Это ломает модель «одна кампания → много размещений в разных каналах».

**Решение B.3:** добавить channel_id в placements (неразрушающий ALTER).

### P1 — Placements без ORM

Таблица есть, но нет модели SQLAlchemy → нельзя использовать в коде.

**Решение B.3.1:** создать ORM model + schemas.

### P1 — Campaign не знает о placements

Campaign.relationships: channels, targets, renditions — placements отсутствуют.

**Решение B.3.2:** добавить relationship + API endpoints.

### P2 — generated_manifests FK на kso_placements

`generated_manifests.placement_code → kso_placements.placement_code` (legacy FK).

**Решение:** на B.3 не менять (отложено до B.5 — Universal Manifest Schema).

---

## 4. Proposed Placement Model v1

### 4.1 Минимальная модель

```python
# backend/app/domains/channels/models.py (или новый domains/placements/)

class Placement(Base):
    __tablename__ = "placements"

    id = Column(UUID, PK, server_default=gen_random_uuid())
    campaign_id = Column(UUID, FK→campaigns, NOT NULL, INDEX)
    channel_id = Column(UUID, FK→channels, NOT NULL, INDEX)    # ← НОВОЕ
    placement_code = Column(String(64), UNIQUE, NOT NULL)
    name = Column(String(255), NOT NULL)
    status = Column(String(20), NOT NULL, default='draft')
    priority = Column(Integer, NOT NULL, default=0)
    start_date = Column(Date)
    end_date = Column(Date)
    created_by = Column(UUID, FK→users, ON DELETE RESTRICT)
    created_at = Column(DateTime(timezone=True), server_default=now())
    updated_at = Column(DateTime(timezone=True), server_default=now())

    # Relationships
    campaign = relationship("Campaign", back_populates="placements")
    channel = relationship("Channel")
    targets = relationship("PlacementTarget", back_populates="placement")
    proof_events = relationship("ProofEvent", back_populates="placement")
```

### 4.2 PlacementTarget (существующая + relationship)

```python
class PlacementTarget(Base):
    __tablename__ = "placement_targets"

    id = Column(UUID, PK, server_default=gen_random_uuid())
    placement_id = Column(UUID, FK→placements, NOT NULL, INDEX)
    target_type = Column(String(20), NOT NULL)  # store/surface/zone
    store_id = Column(UUID, FK→stores)           # nullable
    display_surface_id = Column(UUID, FK→display_surfaces)  # nullable
    logical_carrier_id = Column(UUID, FK→logical_carriers)  # nullable
    created_at = Column(DateTime(timezone=True), server_default=now())

    # Relationships
    placement = relationship("Placement", back_populates="targets")
    store = relationship("Store")
    display_surface = relationship("DisplaySurface")
    logical_carrier = relationship("LogicalCarrier")
```

### 4.3 Статусы Placement

| Статус | Описание | Переходы |
|---|---|---|
| `draft` | Черновик размещения | → active, → cancelled |
| `active` | Активное размещение | → paused, → completed, → cancelled |
| `paused` | Приостановлено | → active, → cancelled |
| `completed` | Завершено (end_date прошла) | терминальный |
| `cancelled` | Отменено | терминальный |
| `error` | Ошибка размещения | → draft (retry) |

**Проверки переходов:** валидация в service layer, не в БД (CHECK constraint только на валидные значения).

---

## 5. Database Changes Needed

### B.3.1 Migration (неразрушающая)

```sql
-- 1. Добавить channel_id (nullable на время миграции)
ALTER TABLE placements ADD COLUMN channel_id UUID;
ALTER TABLE placements ADD CONSTRAINT fk_placements_channel
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE RESTRICT;
CREATE INDEX idx_placements_channel ON placements(channel_id);

-- 2. Заполнить для существующей строки
UPDATE placements SET channel_id = (
    SELECT ch.id FROM channels ch WHERE ch.code = 'kso'
) WHERE placement_code = 'test-place-seed';

-- 3. Сделать NOT NULL после заполнения
ALTER TABLE placements ALTER COLUMN channel_id SET NOT NULL;
```

**Проверка перед миграцией:** убедиться, что 0 строк имеют NULL channel_id.

**Откат:**
```sql
ALTER TABLE placements DROP COLUMN channel_id;
```

### B.3.2 Без destructive изменений

- ❌ НЕ трогать campaign_targets
- ❌ НЕ трогать kso_placements
- ❌ НЕ трогать generated_manifests FK
- ❌ НЕ удалять колонки/таблицы

---

## 6. Campaign → Placement Relationship

### 6.1 Модель

```python
# Campaign model — добавить:
placements = relationship("Placement", back_populates="campaign", lazy="selectin")
```

### 6.2 Сервис

Campaign service добавляет:
```python
async def get_campaign_placements(db, campaign_id) -> list[Placement]:
    """Get all placements for a campaign."""

async def create_placement(db, campaign_id, data) -> Placement:
    """Create placement within campaign. Validates: campaign editable, channel valid."""

async def update_placement(db, placement_id, data) -> Placement:
    """Update placement fields. Validates: campaign editable."""

async def set_placement_targets(db, placement_id, data) -> list[PlacementTarget]:
    """Replace targets for a placement."""
```

### 6.3 API

```
GET    /api/campaigns/{id}/placements        — list placements
POST   /api/campaigns/{id}/placements        — create placement
GET    /api/placements/{id}                  — get placement
PUT    /api/placements/{id}                  — update placement
DELETE /api/placements/{id}                  — cancel placement
GET    /api/placements/{id}/targets          — list targets
PUT    /api/placements/{id}/targets          — set targets
```

---

## 7. Placement → Channel Relationship

Placement.channel_id → channels.id.

**Валидации:**
- channel_id должен существовать
- channel_id должен быть в campaign_channels (если campaign_channels не пуст)
- При создании placement: если campaign_channels не пуст, channel_id должен быть в этом списке

**Миграция campaign_channels → placement.channel_id:**
- На B.3 НЕ удалять campaign_channels
- Placement.channel_id добавляется как ДОПОЛНЕНИЕ
- На будущем этапе (B.5+) campaign_channels дедуплицируется/убирается

---

## 8. Placement → Display Surface Relationship

Уже существует через placement_targets:
```
Placement → PlacementTarget.display_surface_id → DisplaySurface
```

**B.2.1 уже исправил:** FK→display_surfaces работает, seed линкует.

**На B.3:**
- Добавить ORM model для PlacementTarget
- API: GET/PUT /api/placements/{id}/targets
- Валидация: surface должен принадлежать тому же каналу, что и placement.channel_id

---

## 9. placement_target Strategy

**Оставить как есть. Расширить:**

- Добавить ORM model ✅
- Добавить relationship к Placement ✅
- Использовать как основную связку Placement → Surface/Store ✅
- Не ломать существующие данные ✅

**Целевая модель (B.3):**
```
Campaign 1→N Placement (через campaign_id)
Placement 1→N PlacementTarget (через placement_id)
PlacementTarget → Store | DisplaySurface | LogicalCarrier
```

---

## 10. campaign_targets Legacy Strategy

**На B.3:**
- ❌ НЕ удалять
- ❌ НЕ менять структуру
- ✅ Сохранить как legacy
- ✅ Не использовать в новом коде placements
- ✅ Campaign submit продолжает проверять campaign_targets (не ломать)

**Будущее (B.5+):**
- Мигрировать campaign_targets → placement_targets
- Удалить campaign_targets после миграции и approval

---

## 11. kso_placements Legacy Strategy

**На B.3:**
- ❌ НЕ удалять
- ❌ НЕ менять структуру
- ✅ Сохранить для legacy compatibility
- ✅ Не развивать

**Проблема:** generated_manifests.placement_code → kso_placements.placement_code (legacy FK).

**Решение:** На B.3 эту связь НЕ менять. Когда B.5 (Universal Manifest) будет готов — переключить на placements.placement_code.

---

## 12. API Design

### 12.1 Placement Endpoints

| Метод | Путь | RLS | Audit |
|---|---|---|---|
| GET | /api/campaigns/{cid}/placements | campaigns.read → advertiser scope | — |
| POST | /api/campaigns/{cid}/placements | campaigns.create → advertiser scope | placement.create |
| GET | /api/placements/{id} | campaigns.read → advertiser scope (через campaign) | — |
| PUT | /api/placements/{id} | campaigns.manage → advertiser scope | placement.update |
| DELETE | /api/placements/{id} | campaigns.manage → advertiser scope | placement.cancel |
| GET | /api/placements/{id}/targets | campaigns.read → advertiser scope | — |
| PUT | /api/placements/{id}/targets | campaigns.manage → advertiser scope | placement.targets.update |

### 12.2 Schemas

```python
class PlacementCreate(BaseModel):
    channel_id: UUID
    name: str (max 255)
    priority: int = 0
    start_date: date | None
    end_date: date | None

class PlacementUpdate(BaseModel):
    name: str | None
    status: str | None
    priority: int | None
    start_date: date | None
    end_date: date | None

class PlacementResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    channel_id: UUID
    placement_code: str
    name: str
    status: str
    priority: int
    start_date: date | None
    end_date: date | None
    created_at: datetime
    updated_at: datetime

class PlacementTargetPut(BaseModel):
    targets: list[PlacementTargetItem]

class PlacementTargetItem(BaseModel):
    target_type: str  # store/surface/zone
    store_id: UUID | None
    display_surface_id: UUID | None
    logical_carrier_id: UUID | None
```

---

## 13. Portal Impact

**На B.3 — минимально. B.3.4 (portal read-only):**

- Campaign detail: показать placements (список)
- Placement detail: базовая страница (название, канал, статус, цели)

**Не сейчас:**
- Placement CRUD через portal
- Drag-and-drop placement management
- Календарь/таймлайн размещений

---

## 14. RBAC/RLS Design

### 14.1 Permissions (используем существующие)

Placement использует permissions домена campaigns:
- `campaigns.read` — просмотр placements
- `campaigns.create` — создание placements
- `campaigns.manage` — редактирование/удаление placements

**Обоснование:** Placement — подсущность Campaign. Отдельные permissions преждевременны.

### 14.2 RLS Scope

Placement наследует advertiser_scope от родительского Campaign:

```python
# Во всех placement endpoints:
campaign = await get_campaign(db, placement.campaign_id)
scope_ctx = await resolve_user_scope_context(db, current_user)
assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "access placement")
```

### 14.3 Что нельзя ослаблять

- Не давать доступ к placement без проверки advertiser_scope
- Не позволять видеть placements чужих кампаний
- Не возвращать placement_code с секретами/токенами

---

## 15. Audit Design

### 15.1 Новые audit actions

| Action | Target Type | Target Ref | Details |
|---|---|---|---|
| `placement.create` | placement | placement_code | {name, channel_id, campaign_id} |
| `placement.update` | placement | placement_code | {changed_fields} |
| `placement.cancel` | placement | placement_code | {reason} |
| `placement.targets.update` | placement | placement_code | {target_count, target_types} |

### 15.2 Интеграция

```python
# При создании placement:
await audit_business_action(
    db, actor_user_id=str(current_user.id),
    action="placement.create", target_type="placement",
    target_ref=placement.placement_code,
    details={"name": data.name, "channel_id": str(data.channel_id)},
)
```

---

## 16. Migration Plan

### B.3.1 — Schema + ORM

1. Создать Alembic миграцию: ALTER placements ADD channel_id (nullable)
2. Data migration: заполнить channel_id для существующей строки
3. ALTER placements ALTER channel_id SET NOT NULL
4. Создать ORM model: Placement, PlacementTarget
5. Зарегистрировать модели в `__init__.py` domains

**Проверка:** Backend regression (882) не должен упасть.

### B.3.2 — Service + API

1. Campaign model: добавить relationship→placements
2. Placement service: create/update/get/list/targets
3. Placement router: POST/GET/PUT/DELETE endpoints
4. Campaign router: добавить GET /campaigns/{id}/placements

**Проверка:** B.3 tests 15-20 штук, Backend regression.

### B.3.3 — Tests + Seed

1. Seed для placement (idempotent, проверка существующего)
2. Unit tests: placement CRUD, targets, валидации
3. Integration tests: campaign→placement→targets flow
4. RLS test: cross-advertiser изоляция

### B.3.4 — Portal Read-Only

1. Campaign detail: список placements
2. Placement detail: простая страница
3. Без CRUD, без форм

### B.3.5 — Documentation + Regression

1. Regression: Backend 882+, Portal 842+
2. B.3 tests: 15-20 (все pass)
3. Обновить roadmap, CHANGELOG
4. Commit

---

## 17. Seed/Test Data Plan

### 17.1 Placement Seed

```python
# backend/app/domains/channels/seed.py — добавить:

async def _seed_placement(db):
    """Idempotent: seed test placement for KSO campaign."""
    # Проверить существующий placement
    existing = await db.execute(
        select(Placement).where(Placement.placement_code == 'test-place-seed')
    )
    if existing.scalar_one_or_none():
        return  # уже существует

    # Найти KSO campaign + channel
    kso_campaign = ...  # по campaign_code
    kso_channel = ...   # по channel.code == 'kso'

    placement = Placement(
        campaign_id=kso_campaign.id,
        channel_id=kso_channel.id,
        placement_code='test-place-seed',
        name='test-place-seed',
        status='active',
        priority=0,
        start_date=...,
        end_date=...,
    )
    db.add(placement)
    await db.flush()

    # Placement_target уже линкуется через _link_placement_target_to_surface()
```

### 17.2 Test фикстуры

```python
# conftest.py — добавить:
@pytest.fixture
async def test_placement(db_session, test_campaign, test_channel_kso):
    placement = Placement(
        campaign_id=test_campaign.id,
        channel_id=test_channel_kso.id,
        placement_code='test-placement-001',
        name='Test Placement',
        status='draft',
    )
    db_session.add(placement)
    await db_session.commit()
    return placement
```

---

## 18. Test Strategy

### B.3.1 (schema only)
- Тесты не нужны — проверяется regression (882/0)

### B.3.2 (service + API)
- `test_placement_crud.py` — 8-10 тестов:
  - create placement (валидный)
  - create placement (invalid channel)
  - create placement (campaign not editable)
  - get placement
  - update placement
  - cancel placement
  - list placements for campaign
  - cross-advertiser isolation (403)

- `test_placement_targets.py` — 5-7 тестов:
  - set targets
  - get targets
  - invalid target (wrong surface for channel)
  - remove targets
  - cross-advertiser isolation

### B.3.3 (integration)
- `test_campaign_placement_flow.py` — 5 тестов:
  - campaign → placement → targets → submit
  - placement targets vs campaign_channels consistency

**Итого: ~20 тестов для B.3**

---

## 19. Rollback Plan

### Schema rollback
```sql
-- Удалить колонку (если миграция не закоммичена)
ALTER TABLE placements DROP COLUMN IF EXISTS channel_id;

-- Откатить миграцию Alembic
alembic downgrade -1
```

### Code rollback
```bash
git revert <B.3.1 commit>
git revert <B.3.2 commit>
```

### Data safety
- Migration НЕ удаляет данные
- ALTER ADD COLUMN — обратим (DROP COLUMN)
- Существующая строка placement сохраняется
- Campaign_targets не трогаются

---

## 20. Risks

| # | Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|---|
| 1 | campaign_targets и placement_targets — confusion | Средняя | P1 | Документировать как legacy. Убрать в B.5 |
| 2 | generated_manifests всё ещё FK→kso_placements | Высокая | P1 | Не трогать на B.3. Исправить в B.5 |
| 3 | channel_id nullable → NOT NULL на живых данных | Низкая | P0 | Data migration перед SET NOT NULL |
| 4 | Ломаем campaign submit (проверяет channels/targets) | Низкая | P0 | Не менять submit логику. Placement — дополнение |
| 5 | Двойное целеуказание (campaign_targets + placement_targets) при submit | Средняя | P1 | На B.3 submit проверяет ТОЛЬКО campaign_targets |
| 6 | Нет миграции для заполнения channel_id в существующих placements | Низкая | P2 | Data migration включена в B.3.1 |

---

## 21. Recommended B.3 Implementation Split

| Этап | Содержание | Оценка | Тесты |
|---|---|---|---|
| **B.3.1** | Schema migration + ORM models | 1 сессия | Regression only |
| **B.3.2** | Service layer + API endpoints | 1-2 сессии | ~15 тестов |
| **B.3.3** | Tests + seed + validation | 1 сессия | ~5 интеграционных |
| **B.3.4** | Portal read-only visibility | 0.5 сессии | Portal regression |
| **B.3.5** | Documentation + regression closure | 0.5 сессии | Full regression |

**Итого: ~4-5 сессий на B.3.**

---

## 22. Go/No-Go

### GO for B.3.1 ✅

Все pre-conditions выполнены:
- Device model unified (B.2) ✅
- Channel registry полный (B.1) ✅
- 0 orphan rows ✅
- Backend 882/0, Portal 842/32sk ✅
- Аудит после B.2.2: GO ✅
- Git clean ✅

### Что точно НЕ делаем

- ❌ B.3 Implementation (только design gate)
- ❌ code changes, migrations, DB changes
- ❌ placement CRUD API
- ❌ portal changes
- ❌ campaign_targets removal
- ❌ kso_placements removal
- ❌ generated_manifests FK changes
- ❌ campaign submit logic changes

---

*Design gate complete. Ready for B.3.1 implementation upon approval.*
