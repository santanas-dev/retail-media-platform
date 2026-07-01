# D.5.1.1 — Planning API Security / RLS / Regression Gate

> **Дата:** 2026-07-01
> **Этап:** D.5.1.1 — Security Gate
> **Предыдущий:** D.5.1 (commit `da90835`, 52 теста)
> **Результат:** ✅ GO для D.5.2 Portal Read-Only Planning Visibility

---

## Что проверено

### 1. Permission / Seed Validation

| Проверка | Результат |
|---|---|
| `planning.read` в PERMISSIONS списке | ✅ |
| Permission появляется ровно 1 раз | ✅ |
| Seed идемпотентен (`on_conflict_do_nothing`) | ✅ |
| Ровно 7 ролей имеют `planning.read` | ✅ |
| `device_service` не имеет `planning.read` | ✅ |
| `planning.manage` не существует (deferred) | ✅ |

### 2. Advertiser Scope

| Проверка | Результат |
|---|---|
| own placement → доступ разрешён | ✅ |
| cross-advertiser placement → 404 (conflict) | ✅ |
| cross-advertiser placement → 404 (availability) | ✅ |
| cross-advertiser campaign → 404 (availability) | ✅ (D.5.1) |
| cross-advertiser campaign → 404 (scenario) | ✅ (D.5.1) |

### 3. Store Scope

| Проверка | Результат |
|---|---|
| matching store → доступ | ✅ |
| wrong store → 404 | ✅ |
| без store_id → scope check skipped | ✅ |
| assert_object_in_store_scope вызывается | ✅ |

### 4. Denied Requests Don't Write Success Audit

| Проверка | Результат |
|---|---|
| cross-advertiser denied → NO availability audit | ✅ |
| cross-advertiser denied → NO scenario audit | ✅ |
| store-scope denied → NO occupancy audit | ✅ |
| audit вызывается ТОЛЬКО после прохождения scope | ✅ |

### 5. No Secrets

| Проверка | Результат |
|---|---|
| availability response без secrets/tokens | ✅ |
| occupancy response без secrets/tokens | ✅ |
| audit source без forbidden слов | ✅ |

### 6. Invalid Input

| Проверка | Результат |
|---|---|
| negative SOV → 422 | ✅ |
| SOV > 100 → 422 | ✅ |
| negative spots → 422 | ✅ |

### 7. Import Boundaries (planning/service.py)

| Проверка | Результат |
|---|---|
| нет device_gateway импортов | ✅ |
| нет publication импортов | ✅ |
| нет generated_manifest импортов | ✅ |

### 8. Main.py Registration

| Проверка | Результат |
|---|---|
| planning router импортирован | ✅ |
| planning router включён в app | ✅ |

### 9. Additional Read-Only

| Проверка | Результат |
|---|---|
| нет InventoryUnit конструкторов | ✅ |
| нет CapacityRule конструкторов | ✅ |
| нет ScheduleRun/ScheduleItem | ✅ |

---

## Test Results

| Слой | До D.5.1.1 | После | Δ |
|---|---|---|---|
| D.5.1 targeted | 52/52 | 52/52 | — |
| D.5.1.1 targeted | — | **30/30** | +30 |
| D.5.1 + D.5.1.1 | 52/52 | **82/82** | +30 |
| Planning suite | 224/224 | **254/254** | +30 |
| Backend collection | 1630 | **1660** (0 errors) | +30 |

---

## Что не менялось

- API endpoints — без изменений
- API contracts — без изменений
- Миграции — не создавались
- БД — не менялась
- CampaignBooking/BookingItem — не создавались
- Placement/Campaign/publication/Gateway/portal — не менялись
- Docker/.env — не менялись

---

## Файлы

| Файл | Действие | Строк |
|---|---|---|
| `backend/tests/test_planning_api_d5_1_1.py` | 🆕 | 30 tests |
| `docs/qa/d5-1-1-planning-api-security-rls-regression.md` | 🆕 | этот документ |

---

## GO ✅ для D.5.2 — Portal Read-Only Planning Visibility
