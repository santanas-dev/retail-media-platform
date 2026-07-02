# B4 — Rollback Evidence

**Date:** 2026-07-02 | **Status:** ⬜ NOT TESTED — requires physical device

## Rollback Path

KSO device → Legacy KSO manifest route: `/api/legacy/kso/manifest`

## Pre-Verified

- ✅ Legacy manifest route unchanged (confirmed G/Phase E)
- ✅ Rollback runbook: `docs/operations/rollback-runbook.md` (H.1)
- ✅ Rollback preflight: `scripts/ops/rollback_preflight.sh` (H.3)
- ✅ KSO production switch: NO-GO

## Rollback Test Protocol

| # | Step | Expected | Collected |
|---|---|---|---|
| 1 | Verify universal mode active | New player showing universal manifest | ⬜ |
| 2 | Switch device to legacy endpoint | URL changed | ⬜ |
| 3 | Device pulls legacy manifest | Legacy creative plays | ⬜ |
| 4 | Measure cutover time | < 5 minutes | ⬜ |
| 5 | Verify legacy playback | Creative plays correctly | ⬜ |
| 6 | Confirm no data loss | PoP events from legacy recorded | ⬜ |

## Rollback Time Measurement

```
Start: <TIMESTAMP> — decision to rollback
End:   <TIMESTAMP> — legacy playback confirmed
Delta: <SECONDS>
Target: < 300 seconds (5 min)
```

## Status

- Protocol ready: ✅
- Rollback tested: ⬜ Pending manual test
