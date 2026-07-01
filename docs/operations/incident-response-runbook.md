# Incident Response Runbook

**Date:** 2026-07-02 | **Phase:** H.1 | **Owner:** Ops Team (TBD)

> **Escalation path:** TBD — define contact numbers/emails before pilot.

---

## Scenario 1: Gateway Unavailable

**Symptoms:** Backend `/health` fails, portal errors, devices report connection timeouts.

**First checks:**
1. `curl <GATEWAY_URL>/health` — 200?
2. Check Docker container: `docker ps | grep gateway`
3. Check PostgreSQL: `pg_isready -h <HOST> -U <USER>`
4. Check disk: `df -h`
5. Check logs: `docker logs <gateway_container> --tail 100`

**Escalation:** If no response in 5 min → escalate to on-call developer.

**Decision points:**
- If PostgreSQL down → restart DB, verify data integrity
- If disk full → clean logs, expand volume
- If app crash → restart container, check crash logs

---

## Scenario 2: Device Heartbeat Missing

**Symptoms:** Device status shows «offline» in dashboard, last_seen_at > threshold.

**First checks:**
1. Is the device powered on? (physical check)
2. Can the device reach Gateway? `ping <GATEWAY_IP>`
3. Check device logs (if accessible)
4. Check Gateway rate limiting logs

**Escalation:** > 10% devices offline → escalate to ops manager.

**Decision points:**
- Single device: restart device, re-register if needed
- Multiple devices: check network / Gateway health
- > 30 min offline: rollback consideration

---

## Scenario 3: Manifest Not Updating

**Symptoms:** Device shows stale campaign, manifest version unchanged.

**First checks:**
1. Check publication status in portal
2. Check if campaign is active/approved
3. Force manifest pull from device: `curl <GATEWAY>/api/manifest/universal-preview?device_code=<CODE>`
4. Check manifest size (too large?)

**Escalation:** Affects >1 device → escalate.

**Decision points:**
- Publish stuck: cancel + re-publish
- Manifest too large: check media size limits

---

## Scenario 4: PoP Not Arriving

**Symptoms:** Analytics shows 0 events for a device, PoP report empty.

**First checks:**
1. Is device playing ads? (visual check)
2. Gateway PoP ingestion logs: search for `device_code=<CODE>`
3. Check device PoP batch interval
4. Check PoP endpoint: curl test

**Escalation:** > 30 min no PoP from pilot devices → escalate.

---

## Scenario 5: Media Not Downloading

**Symptoms:** Device shows black screen or error for specific creative.

**First checks:**
1. Check creative status in portal (approved?)
2. Check creative file exists in MinIO
3. Check device connectivity to MinIO
4. Verify media format (mp4/h264)

**Escalation:** Affects >1 creative → escalate to media team.

---

## Scenario 6: Portal Unavailable

**Symptoms:** Portal UI shows 502/504, login fails.

**First checks:**
1. `curl <PORTAL_URL>/health`
2. Check portal process: `ps aux | grep portal`
3. Check backend: portal depends on backend API
4. Check session store (in-memory — restart loses sessions)

---

## Scenario 7: Analytics Not Showing Data

**Symptoms:** `/reports/analytics` shows «no data» when data expected.

**First checks:**
1. Check date range filter
2. Check PoP events in DB for that period
3. Check Analytics API directly: `curl -H "Authorization: Bearer <TOKEN>" <API>/api/analytics/delivery/summary`
4. Verify normalizers are processing events

---

## Scenario 8: Emergency Preview Not Working

**Symptoms:** `/emergency` page shows error or no results.

**First checks:**
1. Check user has `emergency.read` permission
2. Check backend `/api/emergency/capabilities`
3. Try preview with known target (e.g., `channel_code=kso`)
4. Check audit logs for denied requests

**Note:** Emergency is dry-run only — no real impact on campaigns.

---

## Scenario 9: Suspected Credential Leak

**Symptoms:** Unauthorized access, unusual API calls, audit anomalies.

**First checks:**
1. Block suspected account immediately: `PATCH /api/users/<username>/status {status: "blocked"}`
2. Rotate all affected tokens/keys
3. Review audit logs for access pattern
4. Check if secrets appear in logs/responses

**Escalation:** Immediate — security on-call.

---

## Scenario 10: Publication Error

**Symptoms:** Publication batch stuck, manifest not generated.

**First checks:**
1. Check batch status in portal
2. Check campaign: approved? has creatives? has placements?
3. Check creative: approved? AV scan passed?
4. Check orchestrator logs

**Note:** Production switch is NO-GO — only approved batches via existing flow.

---

## Rollback Criteria

Consider rollback when:
- > 10% pilot devices affected
- Data integrity concern
- Security incident
- Business-critical campaign impacted
- Incident unresolved after 1 hour

**Rollback decision maker:** TBD (Ops Manager / on-call).
**Rollback procedure:** See `rollback-runbook.md`.
