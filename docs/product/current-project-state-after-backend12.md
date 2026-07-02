# Current Project State — After BACKEND.1.2

**Date:** 2026-07-02
**Last Phase:** BACKEND.1.2 — GeneratedManifest Writes Feature Flag Gate ✅
**Previous:** BACKEND.1.1 — Publication Feature Flag Gate ✅
**Pilot Decision:** 🚫 FROZEN
**Production Switch:** 🚫 NO-GO

---

## 1. BACKEND.1.2 — What changed

**Разрыв публикации закрыт.** `publish_batch()` → `GeneratedManifest` → KSO endpoint видит манифест.

### Два feature flags теперь защищают публикацию:

| Flag | Default | Gate |
|---|---|---|
| `ENABLE_REAL_PUBLICATION` | `False` | BACKEND.1.1 |
| `ENABLE_GENERATED_MANIFEST_WRITE` | `False` | BACKEND.1.2 |

Оба должны быть `True` для полной цепочки: publish → GeneratedManifest → KSO delivery.

### Bridge-функция
`create_generated_manifests_for_published_batch()` — резолвит device_code через KsoDevice, строит KSO-safe projection через `build_kso_safe_manifest_projection()`, создаёт `GeneratedManifest(status="published")`.

### Идемпотентность
`manifest_code = "pub-{batch_id}-{device_code}"` — детерминированный ключ. Повторный publish не дублирует.

### Файлы изменены
| File | Change |
|---|---|
| `backend/app/core/config.py` | +1: `ENABLE_GENERATED_MANIFEST_WRITE` |
| `backend/app/domains/publications/service.py` | +191: bridge function |
| `backend/app/domains/publications/router.py` | +14/-2: bridge call + response |
| `backend/app/domains/publications/schemas.py` | +2: count + details fields |
| `backend/tests/test_generated_manifest_write_backend12.py` | 🆕 43 tests |

---

## 2. Key Metrics

| Metric | Value |
|---|---|
| Backend domains | 28 |
| Backend test collection | **2539** (+43 since BACKEND.1.1) |
| Backend test errors | 0 |
| Feature flags | 2 (`ENABLE_REAL_PUBLICATION`, `ENABLE_GENERATED_MANIFEST_WRITE`) |
| Publication → KSO gap | ✅ CLOSED |
| Booking gap | Still open → BACKEND.1.3 |
| Portal pages | 27 (unchanged) |
| KSO physical tests | 0 |

---

## 3. Roadmap progress

```
AUDIT.0       ✅ Full project audit
BACKEND.1.0   ✅ Design gate
BACKEND.1.1   ✅ Publication feature flag
BACKEND.1.2   ✅ GeneratedManifest writes  ← HERE
BACKEND.1.3   ⏳ Booking write API (GO)
BACKEND.1.4   ⏳ E2E scenarios
BACKEND.1.5   ⏳ Security / regression gate
BACKEND.1.6   ⏳ Closure gate → GO/NO-GO PORTAL.1
PORTAL.1      ⏳ Portal functional completion
...
```

---

## 4. Next step

**BACKEND.1.3 — Booking Write API**
- `ENABLE_BOOKING_WRITES` feature flag
- CRUD для `CampaignBooking` + `BookingItem`
- RLS, permission `bookings.manage`, conflict validation
- 35+ тестов
