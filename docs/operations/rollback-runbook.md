# Rollback Runbook

**Date:** 2026-07-02 | **Phase:** H.1 | **Owner:** Ops Team (TBD)

> **IMPORTANT:** KSO production switch is NO-GO. Campaign/publication rollback is limited to existing approved-batch flow. No real emergency stop execution.

---

## 1. Rollback Decision

**Decision maker:** Ops Manager / On-call lead (TBD).  
**Rollback threshold:** >10% pilot devices affected, security incident, business-critical campaign impacted, incident >1h unresolved.

**Rollback is NOT:**
- Emergency real stop (deferred — G.0)
- KSO production switch deactivation (not active)
- GeneratedManifest deletion (not written by universal)
- Campaign status change (read-only from emergency)

---

## 2. Backend Release Rollback

```
1. Stop backend: docker stop <backend_container>
2. Switch to previous version: git checkout <PREV_TAG>
3. Rebuild: docker build -t backend:<PREV_TAG> .
4. Run migrations DOWN if needed: alembic downgrade -1
5. Start: docker run -d backend:<PREV_TAG>
6. Verify: curl <BACKEND_URL>/health
7. Verify: run backend test suite
8. Notify ops: "Backend rolled back to <PREV_TAG>"
```

---

## 3. Portal Release Rollback

```
1. Stop portal: docker stop <portal_container>
2. Switch to previous version: git checkout <PREV_TAG>
3. Rebuild portal image
4. Start portal
5. Verify: curl <PORTAL_URL>/health
6. Verify: run portal test suite
7. Notify ops
```

---

## 4. Gateway Config Rollback

```
1. Restore previous Gateway config (env vars / compose)
2. Restart Gateway container
3. Verify health endpoint
4. Verify device heartbeat resumes
5. Verify PoP ingestion resumes
```

---

## 5. Device Config Rollback

```
1. SSH to KSO device (if accessible)
2. Restore previous config / runner version
3. Restart Chromium kiosk
4. Verify heartbeat resumes within 2 min
5. Verify manifest pull: check device dashboard
6. Verify PoP events appearing
```

---

## 6. Post-Rollback Validation

| Check | Method | Expected |
|---|---|---|
| Backend health | `curl /health` | 200 |
| Portal health | `curl /health` | 200 |
| Gateway health | `curl /health` | 200 |
| Device heartbeat | Device dashboard | Seen < 2 min ago |
| PoP flow | Analytics page | Events appearing |
| Manifest pull | Device dashboard | Version updated |
| Emergency API | `curl /api/emergency/capabilities` | 200 |
| Analytics API | Portal `/reports/analytics` | Data shown |
| No error spike | Logs | Normal error rate |

---

## 7. Communication

| Audience | What | When |
|---|---|---|
| Ops team | Rollback started/completed | Immediate |
| Developers | Root cause + logs | Within 15 min |
| Stakeholders | Impact summary | Within 30 min |
| Device operators | Device restart needed? | Immediate |

---

## 8. Rollback Log

Date / Time | Reason | Rollback From | Rollback To | Decision Maker | Success? | Post-Rollback Issues
