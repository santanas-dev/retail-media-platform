# Device Onboarding Runbook

**Date:** 2026-07-02 | **Phase:** H.1 | **Owner:** Ops Team (TBD)

> Placeholder credentials throughout. Replace `<PLACEHOLDER>` with real values.

---

## 1. Pre-Onboarding Checklist

- [ ] Device physically present and powered on
- [ ] Network connectivity confirmed (ping Gateway)
- [ ] Channel registered in backend
- [ ] Device Type registered in backend
- [ ] Capability Profile configured
- [ ] Store registered in backend (if applicable)
- [ ] Operator has `devices.gateway.read` + `devices.gateway.manage` permission

---

## 2. Registration

### 2.1 Register Physical Device

```bash
# In portal or API: register physical device
POST /api/devices/gateway/register
{
  "external_code": "<DEVICE_CODE>",
  "device_type_code": "<DEVICE_TYPE_CODE>",
  "channel_code": "<CHANNEL_CODE>",
  "store_code": "<STORE_CODE>",
  "display_name": "<DISPLAY_NAME>"
}
```

### 2.2 Verify Registration

```bash
GET /api/devices/kso
# Confirm device_code appears in list, status=active
```

### 2.3 Issue Gateway Credentials

```bash
POST /api/devices/gateway/<device_id>/credentials
# Returns: device_token (save securely on device)
```

---

## 3. Logical Carrier / Display Surface

### 3.1 Create Logical Carrier (if dynamic content)

```bash
POST /api/logical-carriers
{
  "code": "<CARRIER_CODE>",
  "name": "<CARRIER_NAME>",
  "device_type_code": "<DEVICE_TYPE_CODE>"
}
```

### 3.2 Create Display Surface

```bash
POST /api/display-surfaces
{
  "code": "<SURFACE_CODE>",
  "physical_device_code": "<DEVICE_CODE>",
  "logical_carrier_code": "<CARRIER_CODE>",
  "ad_zone_width": <WIDTH_PX>,
  "ad_zone_height": <HEIGHT_PX>
}
```

---

## 4. Gateway Verification

### 4.1 Auth Token Test

```bash
curl -X POST https://<GATEWAY_HOST>/api/device-gateway/auth \
  -H "Content-Type: application/json" \
  -d '{"device_token": "<DEVICE_TOKEN>"}'
# Expect: 200, access_token
```

### 4.2 Heartbeat Test

```bash
curl -X POST https://<GATEWAY_HOST>/api/device-gateway/heartbeat \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"device_code": "<DEVICE_CODE>", "status": "active"}'
# Expect: 200
```

### 4.3 Config Test

```bash
curl https://<GATEWAY_HOST>/api/device-gateway/config \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
# Expect: 200, config JSON
```

### 4.4 Manifest Preview Test

```bash
curl https://<GATEWAY_HOST>/api/device-gateway/manifest/universal-preview \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
# Expect: 200, UniversalManifestV1 (dry_run=true)
```

---

## 5. PoP Verification

### 5.1 Send Test PoP Event

```bash
curl -X POST https://<GATEWAY_HOST>/api/device-gateway/proof-of-play \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "device_code": "<DEVICE_CODE>",
    "event_type": "impression",
    "creative_code": "<CREATIVE_CODE>",
    "playback_status": "success",
    "timestamp": "<ISO_TIMESTAMP>"
  }'
# Expect: 200
```

### 5.2 Verify PoP in Portal

- Portal → Отчёты → Фактические показы
- Filter by device_code
- Confirm event appears

---

## 6. Media Delivery Verification

```bash
curl https://<GATEWAY_HOST>/api/device-gateway/media/<MEDIA_REF> \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -o /tmp/test_media.mp4
# Expect: 200, media file
# Verify: ffprobe /tmp/test_media.mp4
```

---

## 7. Troubleshooting

| Symptom | First Check |
|---|---|
| Auth fails | Device token expired? Re-issue credentials |
| Heartbeat 401 | Access token expired? Re-auth |
| Manifest empty | Campaigns published? Check portal → Публикации |
| PoP not showing | Event timestamp in range? Check filters |
| Media 404 | Media ref correct? Creative uploaded? |
| Device not listed | Registered? Check GET /api/devices/kso |

---

## 8. Removal / Rollback

### 8.1 Block Device

```bash
PATCH /api/devices/<device_id>/status
{"status": "blocked"}
```

### 8.2 Unregister (if needed)

```bash
DELETE /api/devices/<device_id>
# Removes device from registry (campaigns/placements auto-unlinked)
```

### 8.3 Rollback to Legacy KSO Mode

- Legacy endpoint `/kso/{device_code}/manifest` remains unchanged
- Switch device config to use legacy endpoint (no Gateway)
- Verify legacy manifest still delivers

---

## 9. Acceptance Criteria

- [ ] Device appears in portal → Устройства (status=active)
- [ ] Heartbeat received (portal → Панель КСО)
- [ ] Manifest preview returns valid UniversalManifestV1
- [ ] PoP event appears in reports
- [ ] Media download successful
- [ ] Emergency preview shows device in affected list
- [ ] Rollback to legacy mode verified
