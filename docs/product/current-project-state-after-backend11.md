# Current Project State — After BACKEND.1.1

**Date:** 2026-07-02
**Last Phase:** BACKEND.1.1 — Publication Feature Flag Gate ✅
**Previous:** AUDIT.0 — Full Project Audit
**Pilot Decision:** 🚫 FROZEN
**Production Switch:** 🚫 NO-GO

---

## 1. BACKEND.1.1 — What changed

**Feature flag `ENABLE_REAL_PUBLICATION=false`** добавлен для защиты `publish_batch()`.

### AUDIT.0 ошибка исправлена
AUDIT.0 утверждал, что publication — DRY_RUN. В реальности `publish_batch()` полностью реализован и коммитит в БД. BACKEND.1.1 добавил защитный feature flag, который:
- **OFF** (default): возвращает 422, не вызывает сервис
- **ON**: существующий `publish_batch()` работает как прежде, но `GeneratedManifest` всё ещё не создаётся

### Файлы изменены
| File | Change |
|---|---|
| `backend/app/core/config.py` | +1 line: `ENABLE_REAL_PUBLICATION: bool = False` |
| `backend/app/domains/publications/router.py` | Feature flag check + `PublishBatchResult` wrapper |
| `backend/app/domains/publications/schemas.py` | +7 lines: `PublishBatchResult` schema |
| `backend/tests/test_publication_feature_flag_backend11.py` | 🆕 38 targeted tests |

### Что НЕ менялось
- 0 миграций, 0 schema changes
- Docker/.env не тронуты
- GeneratedManifest не создаётся
- Legacy KSO endpoint не тронут
- KSO adapter, Device Gateway, portal — не тронуты
- Production switch не затронут

---

## 2. Key Metrics

| Metric | Value |
|---|---|
| Backend domains | 28 |
| Backend test collection | **2496** (+38 since AUDIT.0) |
| Backend test errors | 0 |
| Publication feature flags | 1 (`ENABLE_REAL_PUBLICATION`) |
| GeneratedManifest gap | Still open → BACKEND.1.2 |
| Booking gap | Still open → BACKEND.1.3 |
| Portal pages | 27 (unchanged) |
| KSO physical tests | 0 |

---

## 3. Roadmap progress

```
AUDIT.0  ✅ Full project audit
BACKEND.1.0 ✅ Design gate
BACKEND.1.1 ✅ Publication feature flag gate ← HERE
BACKEND.1.2 ⏳ GeneratedManifest writes (GO)
BACKEND.1.3 ⏳ Booking write API
BACKEND.1.4 ⏳ E2E scenarios
BACKEND.1.5 ⏳ Security / regression gate
BACKEND.1.6 ⏳ Closure gate → GO/NO-GO PORTAL.1
PORTAL.1 ⏳ Portal functional completion
UI.1 ⏳ UI/UX redesign
E2E.1 ⏳ End-to-end validation
KSO.1 ⏳ 1 test KSO
PROD.1 ⏳ Production readiness
PILOT.1 ⏳ Store pilot
```

---

## 4. Next step

**BACKEND.1.2 — GeneratedManifest writes**
- Add `ENABLE_GENERATED_MANIFEST_WRITE` feature flag
- Create `GeneratedManifest` entries in `publish_batch()` caller
- Verify Device Gateway `/kso/{device_code}/manifest` delivery
- 30+ tests, no migrations, no legacy KSO changes
