# B3 — RPO / RTO Measurement

**Date:** 2026-07-02 | **Status:** ⬜ NOT MEASURED — real drill not executed

## Definitions

| Metric | Definition | Target |
|---|---|---|
| **RPO** | Maximum acceptable data loss (time since last backup) | < 5 minutes |
| **RTO** | Maximum time to restore service after incident | < 15 minutes |

## Measurement Protocol

**RPO:**
1. Record timestamp before backup
2. Execute backup
3. Simulate data loss (insert test row)
4. Execute restore
5. RPO = restore timestamp − backup timestamp

**RTO:**
1. Record start timestamp before restore
2. Execute dropdb + createdb + pg_restore + seed + health check
3. RTO = end timestamp − start timestamp

## Estimated Values

- pg_dump (lab DB): ~5-30 seconds
- dropdb + createdb: ~2-5 seconds
- pg_restore: ~5-30 seconds
- seed: ~2 seconds
- health check: ~1 second
- **Estimated RTO: ~15-70 seconds** (well within 15 min target)

## Status

- Protocol: ✅ Ready
- Measurement: ⬜ Pending real drill
- Estimate: ✅ RTO likely < 60s
