# Current Project State — After Phase F

**Date:** 2026-07-10  
**Commit:** 998f5d4

## Analytics Capabilities (Phase F)

### Что есть

| Capability | Status |
|---|---|
| PoP normalization (KSO + Enterprise Gateway) | ✅ |
| Delivery aggregation (14 метрик) | ✅ |
| Delivery breakdowns (campaign/placement/store/device/channel/day) | ✅ |
| Analytics API (4 read-only endpoints) | ✅ |
| RLS/Scope enforcement | ✅ |
| Audit events | ✅ |
| Portal analytics page | ✅ |
| Dry-run exclusion | ✅ |
| No-secrets validation | ✅ |

### Что analytics пока НЕ делает

| Capability | Причина |
|---|---|
| ClickHouse pipeline | Deferred — не в scope F |
| Placement/store real data в breakdowns | Normalizers не делают JOIN (F.4+) |
| expected_impressions расчёт | Нет planning integration (F.4+) |
| Silent device detection | Нет expected device set |
| Export (PDF/XLSX/CSV) | Deferred |
| Portal advanced filters | Deferred |
| Performance indexes | Deferred |
| Materialized daily aggregates | Deferred |
| Production KSO switch | Deferred — отдельный design gate |

---

## Backend Baseline

| Метрика | Значение |
|---|---|
| Collection | **2145** |
| Errors | **0** |
| Analytics suite (F.1–F.4.1) | **268/268** |
| F.1 targeted | 42/42 |
| F.2 targeted | 54/54 |
| F.3 targeted | 69/69 |
| F.4 targeted | 60/60 |
| F.4.1 targeted | 43/43 |

### Analytics API endpoints

| Метод | Path | Permission |
|---|---|---|
| `GET` | `/api/analytics/delivery/summary` | `reports.read` |
| `POST` | `/api/analytics/delivery/query` | `reports.read` |
| `GET` | `/api/analytics/planned-vs-delivered` | `reports.read` |
| `GET` | `/api/analytics/device-health` | `reports.read` |

---

## Portal Baseline

| Метрика | Значение |
|---|---|
| Collection | **974** |
| Passed | **934** |
| Skipped | **32** |
| Pre-existing errors | **8** (live integration — требуется запущенный backend) |
| F.5 targeted | 44/44 |

### Portal pages

| Page | Permission |
|---|---|
| `/reports` | `reports.read` |
| `/reports/analytics` | `reports.read` 🆕 |
| `/proof-of-play` | `reports.read` |

---

## Deferred Items

- ClickHouse pipeline
- Placement/store JOIN в normalizers
- expected_impressions из planning
- Silent device detection
- Export reports
- Portal advanced filters
- Performance indexes / materialized aggregates
- Production KSO switch (отдельный design gate)

---

## Next Recommended Phase

**G — Emergency & Operations (design gate / pre-audit)**

Рекомендуется design-only gate для:
- Emergency management design review
- Operational health center design review
- Staged rollout strategy

**NO-GO** для прямого включения ClickHouse без performance gate.
**NO-GO** для production KSO switch без отдельного design gate.
