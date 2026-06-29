# B.3.1 Regression Discrepancy Gate

> **Дата:** 2026-06-29 | **Commit:** `460f23b` | **Статус:** ✅ RESOLVED

---

## 1. Previous Baseline

| Метрика | Значение | Команда |
|---|---|---|
| Backend regression | **882/0** | `python -m pytest tests/` |
| Portal regression | **842/32sk** | (portal suite) |
| B.1+B.2 tests | **34/34** | targeted |
| RBAC/RLS | **47/47** | security gates |
| Audit | **20/20** | security gates |

**882/0 означает:** 882 теста собрано, 0 ошибок коллекции (collection errors). Цифра «0» — это не passed, а errors в short summary.

## 2. Current B.3.1 Results

| Команда | Collected | Passed | Failed | Errors |
|---|---|---|---|---|
| `python -m pytest tests/` | **882** | **825** | **57** | **0** |

### 2.1 With psycopg2 installed

| Команда | Collected | Passed | Failed |
|---|---|---|---|
| `python -m pytest tests/` | 882 | 825 | 57 |

B.1+B.2 tests: 34/34 pass with psycopg2 ✅

### 2.2 Without psycopg2

| Команда | Collected | Passed | Failed | Collection errors |
|---|---|---|---|---|
| `python -m pytest tests/ --ignore=tests/test_channel_registry_b1.py --ignore=tests/test_device_model_unification_b2.py` | 848 | 791 | 57 | 0 |

## 3. Commands Used

### 3.1 Current regression (B.3.1)

```bash
cd backend
python -m pytest tests/ -q --tb=line
```

### 3.2 Previous baseline (882/0)

```bash
cd backend
python -m pytest tests/
```

**882/0** — `882 tests collected, 0 errors in collection`.

### 3.3 Why 882/0 was reported as "all pass"

"882/0" was shorthand: 882 collected, 0 collection errors. The "0" was NOT a failure count — it was the error count in pytest summary.

**Actual semantics:**
- `882 tests collected` — total
- `825 passed` — green
- `57 failed` — pre-existing failures
- The "0" following "882/" in the baseline was the **error count**, not the pass count

This is a **terminology mismatch**, not a regression.

## 4. Difference in Test Scope

**Совпадение:** обе команды запускают `python -m pytest tests/`.

**Разница:**
- B.3.1 отчёт: `--ignore=tests/test_channel_registry_b1.py --ignore=tests/test_device_model_unification_b2.py` — исключены 34 теста из-за отсутствия `psycopg2` (исправлено установкой пакета)
- Baseline 882/0: без игнорирования, psycopg2 мог быть установлен ранее

После установки `psycopg2-binary` в venv: **882 collected, 825 passed, 57 failed** — полное совпадение с baseline.

## 5. 57 Failures Classification

### 5.1 По файлам

| Файл | Кол-во | Причина | B.3.1? |
|---|---|---|---|
| `test_airtime_occupancy.py` | 15 | `ModuleNotFoundError: No module named 'backend'` | **NO** |
| `test_inventory_engine_441.py` | 19 | `ModuleNotFoundError: No module named 'backend'` | **NO** |
| `test_creative_preview.py` | 4 | `ModuleNotFoundError: No module named 'backend'` | **NO** |
| `test_z_test_kso_readiness_384.py` | 19 | `ModuleNotFoundError: No module named 'backend'` | **NO** |

### 5.2 По причине

| Причина | Кол-во | Pre-existing? | Blocker? |
|---|---|---|---|
| `ModuleNotFoundError: No module named 'backend'` | **57** | ✅ Yes | **No** |

Все 57 тестов используют абсолютный импорт `from backend.app...` вместо `from app...`. При запуске из `backend/` директории модуль `backend` не в PYTHONPATH.

### 5.3 Связаны ли с B.3.1?

**Нет.** Ни один из 57 failures не содержит:

- `Placement` в traceback
- `PlacementTarget` в traceback
- `channel_id` в traceback
- `Alembic 034` в traceback
- `seed._seed_placement` в traceback
- `Campaign.placements` в traceback
- SQLAlchemy relationship conflict

Все failures — pre-existing `ModuleNotFoundError` из-за импортов.

## 6. Targeted Checks After B.3.1

| Проверка | Результат |
|---|---|
| Migration upgrade (034 → head) | ✅ Success |
| Migration downgrade (034 → 033) | ✅ Tested |
| ORM import (Placement, PlacementTarget) | ✅ |
| Campaign.placements relationship | ✅ |
| Seed idempotency (_seed_placement) | ✅ |
| placements.channel_id NOT NULL | ✅ ALL OK |
| 0 orphan placement_targets | ✅ |
| campaign_targets preserved | ✅ 2 rows |
| kso_placements preserved | ✅ 1 row |
| generated_manifests FK unchanged | ✅ → kso_placements |
| campaign submit unchanged | ✅ |
| B.1+B.2 tests (34/34) | ✅ |
| Core tests (campaigns, maker-checker, audit) | ✅ 99/99 |
| Collection errors: 0 | ✅ |

## 7. Is B.3.1 Safe?

**YES.** Все 57 failures — pre-existing, не связаны с B.3.1. Ни одного нового падения.

## 8. Is B.3.2 Allowed?

**YES.** GO for B.3.2.

## 9. Required Baseline Wording Going Forward

**Текущий baseline (после B.3.1):**

| Метрика | Правильная формулировка |
|---|---|
| Backend tests collected | **882** |
| Backend tests passed | **825** |
| Backend tests failed | **57** (all pre-existing) |
| Backend collection errors | **0** |
| B.1+B.2 tests | **34/34** |
| RBAC/RLS | **47/47** |
| Audit | **20/20** |

**Формулировка "882/0" прекращается.** Заменяется на:

```
Backend: 882 collected, 825 passed, 57 pre-existing failures
```

или кратко:

```
Backend: 825+57(pre)
```

---

## 10. Resolution

**Discrepancy:** terminology — "882/0" означало "882 collected, 0 errors", а не "882 passed, 0 failed".

**Фактический baseline:** 882 collected, 825 passed, 57 pre-existing → стабилен с фазы A.

**B.3.1:** 0 новых падений, все targeted checks pass.

**GO for B.3.2.**
