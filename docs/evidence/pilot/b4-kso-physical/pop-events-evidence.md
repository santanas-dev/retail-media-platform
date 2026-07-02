# B4 — PoP Events Evidence

**Date:** 2026-07-02 | **Status:** ⬜ NOT COLLECTED — requires playback on physical device

## Pre-Verified (API level)

PoP analytics API confirmed functional (Phase F.5):
- ✅ KSO PoP ingestion (legacy `KsoProofOfPlayEvent`)
- ✅ Enterprise PoP ingestion (`ProofOfPlayEvent`)
- ✅ Analytics API (4 endpoints)
- ✅ Portal analytics page
- ✅ Delivery aggregation (14 metrics)

## Physical Test Verification

| # | Check | Method | Collected |
|---|---|---|---|
| 1 | PoP event generated after playback | DB query | ⬜ |
| 2 | PoP visible in analytics API | API call | ⬜ |
| 3 | PoP visible in portal | Portal screenshot | ⬜ |
| 4 | Heartbeat sent within 60s | Gateway log | ⬜ |
| 5 | Heartbeat visible in portal | Dashboard screenshot | ⬜ |

## Status

- API verified: ✅ (Phase F.5)
- Physical PoP evidence: ⬜ Pending manual test
