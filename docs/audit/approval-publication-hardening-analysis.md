# Approval & Publication Hardening Analysis

> **Phase:** 39.3.0 — Analysis First
>
> Date: 2026-06-25
> Baseline: v0.9.0-product-portal-hardening (commit `7d0e7cd`)
> Regression: 4976 tests green

---

## Executive Summary

После v0.9.0 (Product Portal Hardening) проведён полный аудит цепочки согласования и публикации.
**Ключевой вывод:** approval workflow существует, но фрагментирован между test-kso endpoints и production
Publications Batch системой. Не хватает интеграции между approvals и batch-публикациями.
Campaign → placement → schedule → approval → manifest → batch → publish — связный production workflow
отсутствует.

---

## 1. Текущий Workflow

### 1.1 Backend Endpoints

| Domain | Endpoint | Path | Status |
|---|---|---|---|
| Approvals | list | `GET /api/approvals/test-kso` | 🔴 TEST-KSO only |
| Approvals | request | `POST /api/approvals/test-kso/request` | 🔴 TEST-KSO only |
| Approvals | decide | `POST /api/approvals/test-kso/{code}/decide` | 🔴 TEST-KSO only |
| Manifests | list (production) | `GET /api/manifests` | ✅ Production |
| Manifests | list (test-kso) | `GET /api/manifests/test-kso` | 🔴 TEST-KSO only |
| Manifests | generate | `POST /api/manifests/test-kso/generate` | 🔴 TEST-KSO only |
| Manifests | get | `GET /api/manifests/test-kso/{code}` | 🔴 TEST-KSO only |
| Manifests | publish | `POST /api/manifests/test-kso/{code}/publish` | 🔴 TEST-KSO only |
| Publications | create batch | `POST /api/publication-batches` | ✅ Production |
| Publications | list batches | `GET /api/publication-batches` | ✅ Production |
| Publications | get batch | `GET /api/publication-batches/{id}` | ✅ Production |
| Publications | generate | `POST /api/publication-batches/{id}/generate` | ✅ Production |
| Publications | approve | `POST /api/publication-batches/{id}/approve` | ✅ Production |
| Publications | publish | `POST /api/publication-batches/{id}/publish` | ✅ Production |
| Publications | cancel | `POST /api/publication-batches/{id}/cancel` | ✅ Production |
| Publications | targets | `GET /api/publication-batches/{id}/targets` | ✅ Production |
| Publications | manifests | `GET /api/publication-batches/{id}/manifests` | ✅ Production |
| Publications | events | `GET /api/publication-batches/{id}/events` | ✅ Production |

### 1.2 Статусы

| Домен | Статусы | Переходы |
|---|---|---|
| **Campaign** | draft, pending_approval, approved, rejected, active, archived | draft→pending_approval (request_approval), pending_approval→approved/rejected (decide_approval) |
| **Placement** | draft, pending_approval, approved, rejected | draft→pending_approval→approved/rejected — только через test-kso approval |
| **ApprovalRequest** | pending, approved, rejected | pending→approved/rejected (decide), maker-checker enforced |
| **PublicationBatch** | draft → generation_in_progress → generated → approved → published → cancelled | State machine enforced |
| **ManifestVersion** | generated, published | generated→published (idempotent) |
| **GeneratedManifest** | generated, published | generated→published (idempotent, publish_manifest) |
| **Creative** | draft, approved, active, archived | Through campaign creative binding |

### 1.3 Portal Actions

| Page | Actions |
|---|---|
| `/approvals` | List approvals, Request approval (campaign/placement), Decide approve/reject |
| `/publications` | List manifests, Generate manifest (POST), Publish manifest (POST) |

---

## 2. Gaps — Blocking Pilot

### 🔴 Blocker 1: No Production Approval Endpoint → ✅ FIXED (39.3.1)

**Fix:** Production endpoints added. Legacy test-kso retained.

**Impact:** Campaign/placement approval недоступен через production API. Portal использует test-kso.

**Fix:** Создать production approval endpoints: `GET /api/approvals`, `POST /api/approvals/request`, `POST /api/approvals/{code}/decide`.

### 🔴 Blocker 2: Approvals Not Integrated with Publication Batch → 🟡 PARTIALLY FIXED (39.3.1)

**Fix:** `publication_batch` object_type added to approval system. `publish_batch` now checks for approved ApprovalRequest. Schema updated to allow `publication_batch`.

**Impact:** Непонятно, какой approval нужен для публикации — через `/api/approvals` или через batch `approve`. Двойной approval — confusion.

**Fix:** Либо объединить: batch `approve` должен проверять ApprovalRequest статус, либо убрать встроенный approve из batch и требовать отдельный approval через `/api/approvals`.

### 🔴 Blocker 3: Fragmented Manifest Generation

**Проблема:** `POST /api/manifests/test-kso/generate` (standalone) и `POST /api/publication-batches/{id}/generate` (batch) — две разные системы генерации manifest. Standalone test-kso не использует batch workflow.

**Impact:** Portal генерирует manifest через test-kso endpoint, минуя batch-трекинг. Нет audit trail для standalone генерации.

**Fix:** Перевести portal на batch-based генерацию: create batch → add targets → generate manifests → approve → publish.

### 🔴 Blocker 4: No Status Validation on Approval Request

**Проблема:** `request_approval` в `/api/approvals/test-kso/request` не проверяет, что объект в валидном pre-approval состоянии. Можно запросить approval на rejected/archived campaign.

**Impact:** Одобрение rejected кампании — data integrity risk.

**Fix:** Добавить проверку: campaign должен быть `draft` или `pending_approval`, placement должен быть `draft`.

### 🟡 Gap 5: Fragile Status String Manipulation

**Проблема:** `decide_approval` line 167: `approval.status = data.decision + "d" if data.decision == "approve" else data.decision`. Работает (`"approve"+"d"="approved"`, `"reject"` остаётся `"rejected"`) но хрупко.

**Impact:** Если добавить новый decision type — сломается.

**Fix:** Использовать явный mapping: `DECISION_TO_STATUS = {"approve": "approved", "reject": "rejected"}`.

---

## 3. Gaps — Deferred (не блокирует pilot)

| # | Gap | Severity | Deferred reason |
|---|---|---|---|
| D1 | No creative/schedule/manifest approval types | 🟢 LOW | v0.9 ограничен campaign+placement |
| D2 | Batch uses UUID-based identity | 🟢 LOW | Portal dashboard/manifests уже используют safe projection |
| D3 | No auto-reject on campaign archive | 🟢 LOW | Ручной workflow OK для one-KSO |
| D4 | Duplicate approval_code collision not handled gracefully | 🟢 LOW | Уникальный формат `appr_{type}_{code}` — low collision risk |
| D5 | `generate_manifest` (standalone) не проверяет schedule exists | 🟡 MEDIUM | Placement уже ссылается на campaign + device + creative; schedule — часть placement |

---

## 4. Безопасные Quick Fixes (39.3.0)

### 4.1 Fix `decide_approval` status mapping — explicit dict

**Current (fragile):**
```python
approval.status = data.decision + "d" if data.decision == "approve" else data.decision
```

**Fix:**
```python
_DECISION_TO_APPROVAL_STATUS = {"approve": "approved", "reject": "rejected"}
approval.status = _DECISION_TO_APPROVAL_STATUS[data.decision]
```

Это безопасный рефакторинг без изменения контракта. Тесты уже есть (test_approval_kso).

### 4.2 Add pre-approval state validation in `request_approval`

Добавить проверку: campaign/placement должен быть `draft` или `pending_approval`.

---

## 5. Предлагаемый план 39.3.1

1. **Создать production approval endpoints** (не test-kso):
   - `GET /api/approvals` (safe projection, `approvals.read`)
   - `POST /api/approvals/request` (`approvals.manage`)
   - `POST /api/approvals/{approval_code}/decide` (`approvals.approve`)

2. **Интегрировать approvals с Publications Batch:**
   - Batch `approve` проверяет approval status объекта
   - Либо batch `generate` проверяет, что campaign/placement approved

3. **Перевести portal на production endpoints:**
   - `/approvals` → production `GET /api/approvals`
   - `/publications` → использовать batch workflow вместо test-kso manifest generation

4. **Добавить portal BackendClient методы для Publications Batch**

5. **Tests + regression**

---

## 6. Regression

Код не менялся — docs only. Regression всё равно запустить для подтверждения стабильности baseline.

---

## 7. Подтверждения

- ❌ КСО/SSH/X11/Chromium/runner/sidecar daemon/PoP не запускались
- ❌ Secrets/full URLs/tokens/barcodes не выводились
- ✅ v0.9.0 tag не переписывается
