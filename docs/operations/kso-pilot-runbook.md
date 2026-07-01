# KSO Pilot Runbook

**Date:** 2026-07-02 | **Phase:** H.5 target | **Owner:** Ops (TBD)

> **Status:** ❌ NOT TESTED — physical KSO device (192.168.110.223) не тестирован.  
> **IMPORTANT:** KSO production switch is NO-GO. Only legacy endpoint + universal preview testing.

---

## 1. Prerequisites

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | KSO device powered on + connected | Ops | ❌ |
| 2 | Network access to Gateway (<GATEWAY_IP>:<PORT>) | Ops | ❌ |
| 3 | Chromium kiosk available on device | Ops | ❌ |
| 4 | Operator account with `operations` role | Admin | ❌ |
| 5 | Test campaign created (draft/approved) | Ad Manager | ❌ |
| 6 | Test creative uploaded (mp4/h264, 768×1024) | Media | ❌ |
| 7 | Test placement created for KSO channel | Ad Manager | ❌ |
| 8 | Rollback plan reviewed | Ops | ❌ |

---

## 2. Physical KSO Compatibility Check

```
Device model:   UKM5 (TBD)
OS:             <check via uname or system info>
Screen:         768×1024 portrait (verify!)
Ad zone:        <verify actual dimensions>
Chromium:       /usr/bin/chromium-browser (verify path)
Network:        ping <GATEWAY_IP>
DNS:            nslookup <GATEWAY_HOST>
```

---

## 3. Gateway Auth Check

```bash
# 1. Check legacy endpoint (should be unchanged)
curl http://<GATEWAY>/kso/<DEVICE_CODE>/manifest

# 2. Register device (if not already)
curl -X POST http://<GATEWAY>/api/gateway/register \
  -H "Content-Type: application/json" \
  -d '{"device_code": "<DEVICE_CODE>", "channel_code": "kso"}'

# 3. Get auth token
curl -X POST http://<GATEWAY>/api/gateway/auth \
  -H "Content-Type: application/json" \
  -d '{"device_code": "<DEVICE_CODE>", "secret": "<TOKEN>"}'

# 4. Test heartbeat
curl -X POST http://<GATEWAY>/api/gateway/heartbeat \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"device_code": "<DEVICE_CODE>", "status": "active"}'
```

---

## 4. Manifest Preview Check

```bash
# Universal manifest preview (dry-run)
curl http://<GATEWAY>/api/manifest/universal-preview?device_code=<DEVICE_CODE> \
  -H "Authorization: Bearer <TOKEN>"

# Verify:
# - HTTP 200
# - Contains adapter_payload
# - Contains campaigns list
# - No secrets (password/token/api_key absent)
# - No raw UUIDs exposed
```

---

## 5. Media Playback Check

```bash
# 1. Download creative from MinIO
curl http://<GATEWAY>/api/media/creative/<CREATIVE_CODE> \
  -H "Authorization: Bearer <TOKEN>" \
  -o /tmp/test_creative.mp4

# 2. Verify format
ffprobe /tmp/test_creative.mp4
# Expected: mp4 container, h264 video, aac audio (if any)

# 3. Test playback (on KSO device)
chromium-browser --kiosk --autoplay-policy=no-user-gesture-required \
  file:///tmp/test_creative.mp4
```

---

## 6. PoP Check

```bash
# 1. Send test PoP event
curl -X POST http://<GATEWAY>/api/gateway/proof-of-play \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "device_code": "<DEVICE_CODE>",
    "campaign_code": "<CAMPAIGN_CODE>",
    "creative_code": "<CREATIVE_CODE>",
    "event_type": "impression",
    "playback_status": "success",
    "timestamp": "<ISO_TIMESTAMP>"
  }'

# 2. Verify in portal
# Go to /reports/analytics — PoP event should appear

# 3. Verify in analytics API
curl http://<BACKEND>/api/analytics/delivery/summary \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 7. Rollback to Legacy Mode

```
If any test fails and device needs to return to production:

1. Stop Chromium kiosk
2. Switch back to legacy KSO endpoint (unchanged)
3. Restart legacy player
4. Verify legacy manifest: curl /kso/<DEVICE_CODE>/manifest
5. Verify legacy PoP

No production switch was activated — rollback is restart.
```

---

## 8. Acceptance Criteria

| # | Criterion | Expected | Actual |
|---|---|---|---|
| AC1 | Device heartbeat visible in dashboard | Seen < 2 min | |
| AC2 | Universal manifest preview returns valid JSON | 200, adapter_payload present | |
| AC3 | No secrets in manifest response | Validator pass | |
| AC4 | Creative file downloads | 200, valid mp4 | |
| AC5 | Creative plays on device | Video shown | |
| AC6 | PoP event appears in analytics | Event in /reports/analytics | |
| AC7 | Emergency preview works for device | Capabilities + preview OK | |
| AC8 | Legacy endpoint unchanged | 200, same format as before | |

---

## 9. Acceptance Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Operator (test executor) | TBD | | |
| Ops Manager | TBD | | |
| Developer (witness) | TBD | | |
