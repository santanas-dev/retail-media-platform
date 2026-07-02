# BACKEND.1.1 — Publication Feature Flag Gate: QA Report

**Date:** 2026-07-02
**Status:** ✅ COMPLETE
**Git HEAD:** `d4ffac3` (parent: AUDIT.0)
**Phase:** BACKEND.1 — Backend Debt Closure

---

## What was found in BACKEND.1.0

AUDIT.0 classified publications as DRY_RUN. Code inspection during BACKEND.1.0 revealed:

- **`publish_batch()` IS FULLY IMPLEMENTED** in `backend/app/domains/publications/service.py:802-880`
- It commits to DB, transitions `ManifestVersion.status → "published"`, and updates `PublicationBatch.status → "published"`
- Any user with `publications.publish` permission can call it — **no feature flag, no guard**
- The real gap is that `GeneratedManifest` is NOT created after publish, so `/kso/{device_code}/manifest` returns `"no_manifest"`

### Risk discovered

The publish endpoint was **live without protection**. While the project was in development, there was no feature flag to prevent accidental publishing. **BACKEND.1.1 fixes this gap.**

---

## What was done

### 1. Feature flag added

**Config:** `backend/app/core/config.py`

```python
ENABLE_REAL_PUBLICATION: bool = False  # BACKEND.1.1 — feature flag, OFF by default
```

- Default: **`False`** (OFF)
- Set via env: `ENABLE_REAL_PUBLICATION=true`
- Pydantic Settings, auto-loaded from `.env`
- No migration, no DB schema change

### 2. Router guard implemented

**Router:** `backend/app/domains/publications/router.py`

The `publish_batch` endpoint now checks `get_settings().ENABLE_REAL_PUBLICATION` BEFORE any service call, BEFORE any DB query.

**OFF behavior (default):**
- Returns HTTP **422** with structured JSON error:
  ```json
  {
    "detail": {
      "error": "real_publication_disabled",
      "message": "Real publication is disabled by feature flag (ENABLE_REAL_PUBLICATION=false). Set ENABLE_REAL_PUBLICATION=true to enable.",
      "batch_id": "<batch_id>"
    }
  }
  ```
- No `service.publish_batch()` call
- No `ManifestVersion` status change
- No `PublicationBatch` status change
- No `GeneratedManifest` creation
- No partial writes

**ON behavior:**
- Existing `publish_batch()` executes normally
- Response wrapped in `PublishBatchResult`:
  ```json
  {
    "batch": { ...PublicationBatchResponse... },
    "generated_manifest_created": false,
    "next_step": "generated_manifest_write_disabled"
  }
  ```

### 3. Response schema added

**Schema:** `backend/app/domains/publications/schemas.py`

```python
class PublishBatchResult(BaseModel):
    batch: PublicationBatchResponse
    generated_manifest_created: bool = False
    next_step: str = "generated_manifest_write_disabled"
```

- Non-breaking addition (new schema, existing `PublicationBatchResponse` unchanged)
- All other endpoints continue using `PublicationBatchResponse`

---

## Boundaries verified

| Constraint | Status |
|---|---|
| No migrations | ✅ 0 migrations |
| No DB schema changes | ✅ No DDL |
| No Docker/.env changes | ✅ Only code defaults |
| No GeneratedManifest writes | ✅ Router service source confirmed |
| No legacy KSO endpoint changes | ✅ /kso/{device_code}/manifest untouched |
| No KSO adapter changes | ✅ kso_adapter.py untouched |
| No Device Gateway changes | ✅ service.py/router.py untouched |
| No portal changes | ✅ portal-web untouched |
| No production switch | ✅ No production_switch strings |

---

## Tests

### Targeted: 38/38 ✅

**File:** `backend/tests/test_publication_feature_flag_backend11.py`

| Group | Count | Status |
|---|---|---|
| Feature Flag OFF | 9 | ✅ |
| Feature Flag ON | 8 | ✅ |
| Permissions / Security | 7 | ✅ |
| Boundaries | 10 | ✅ |
| Regression | 4 | ✅ |
| **Total** | **38** | **✅** |

### Regression: 87/87 ✅

Existing publication tests:
- `test_publication_batch_workflow.py` — 25 tests ✅
- `test_campaign_publication_batch_414.py` — 49 tests ✅
- `test_production_manifest_api.py` — 13 tests ✅

**Total: 125/125 (38 targeted + 87 regression) — 0 failures**

---

## Files changed

| File | Change |
|---|---|
| `backend/app/core/config.py` | +1 line: `ENABLE_REAL_PUBLICATION: bool = False` |
| `backend/app/domains/publications/router.py` | +22 / -4 lines: feature flag check + wrapped response |
| `backend/app/domains/publications/schemas.py` | +7 lines: `PublishBatchResult` schema |
| `backend/tests/test_publication_feature_flag_backend11.py` | 🆕 600+ lines: 38 targeted tests |

---

## Decisions

### GO/NO-GO for BACKEND.1.2 (GeneratedManifest writes)

**✅ GO**

Rationale:
- Publication path is now protected by feature flag
- `publish_batch()` works correctly when flag is ON
- Response explicitly signals `generated_manifest_created=false`
- All boundaries hold
- 125 tests pass, 0 failures
- The next logical step is to create a real `GeneratedManifest` entry when publication happens

### Key risk for BACKEND.1.2

`GeneratedManifest` writes will be the first **real data creation** in the publication pipeline. This needs its own feature flag (`ENABLE_GENERATED_MANIFEST_WRITE`), careful integration with the `publish_batch()` caller path, and verification that the Device Gateway `/kso/{device_code}/manifest` endpoint correctly serves the generated manifest. The legacy KSO endpoint must NOT be affected.

---

## Next step

**BACKEND.1.2 — GeneratedManifest writes**
- Add `ENABLE_GENERATED_MANIFEST_WRITE` feature flag
- In `publish_batch()` or a caller, create `GeneratedManifest` rows
- Verify Device Gateway manifest delivery
- Keep legacy KSO unchanged
- ~30+ targeted tests
