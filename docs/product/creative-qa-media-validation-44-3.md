# Production Media Validation Foundation (44.3)

**Status:** ✅ Complete
**Date:** 2026-06-16
**Commit:** TBD

## Scope

Production-grade validation for video (MP4/WebM), GIF, and AV scanner integration foundation for v1 KSO.

## What Was Done

### Video Validation (MP4/WebM)

Module: `backend/app/domains/media/media_validator.py`

**Checks (ffprobe-based):**
- Container: mp4, webm, mov — other containers rejected
- Codec allowlist: h264, vp8, vp9, av1
- Dimensions: must be 768×1024 portrait (active KSO profile)
- Duration: ≤30 seconds
- FPS: ≤30
- Audio: PROHIBITED for KSO
- Corruption: magic bytes check, ffprobe parse failure
- Size: ≤100 MB
- Extension↔MIME consistency

**Business-language errors (Russian):**
- "Неверный формат файла"
- "Размер ролика не подходит для экрана КСО"
- "Видео слишком длинное"
- "В ролике есть звук — для КСО звук запрещён"
- "Файл повреждён или не читается"

### GIF Validation

**Checks (Pillow-based):**
- GIF89a/GIF87a signature verification
- Dimensions: 768×1024 portrait
- Frame count: ≤300 frames
- Duration: ≤15 seconds (sum of frame delays)
- Size: ≤20 MB
- Corruption detection

### AV Scanner Integration Foundation

Module: `backend/app/domains/media/av_scanner.py`

**Components:**
- `AVScanner` abstract interface
- `ClamAVScanner` — ClamAV integration:
  - Priority 1: clamd UNIX socket (`/var/run/clamav/clamd.ctl` or `$CLAMD_SOCKET`)
  - Priority 2: clamscan subprocess (fallback)
  - 60-second timeout
  - Threat name extraction
  - Scanner unavailable → `not_configured` (never sets `clean`)
- `NoScanner` — explicit placeholder:
  - Returns `not_configured` ALWAYS
  - **NEVER returns `clean`** — fake AV pass prohibited
- `create_av_scanner()` — factory, auto-detects ClamAV availability

**Requirements (optional):**
```bash
sudo apt-get install clamav clamav-daemon
sudo freshclam
sudo systemctl start clamav-daemon
```

### Policy Enforcement (added to approve flow)

| Mode | `av_policy_mode` | `require_av_clean` | AV gate in approve |
|------|-------------------|---------------------|--------------------|
| Pilot (current) | `pilot_dev` | `false` | Warning + audit — manual approval allowed |
| Production | `production` | `true` | Block unless `scan_status=clean` |

**Current default:** `pilot_dev` (no AV required, manual moderation accepted with audit trail).

### Upload Changes

- MIME types accepted: PNG, JPEG, GIF, MP4, WebM
- Type-specific size limits: 50MB (image), 100MB (video), 20MB (GIF)
- AV scan runs on EVERY upload (best-effort, not blocking in pilot mode)
- `scan_status` persisted in creative record
- Infected files rejected immediately (400)

### Portal UI

- Upload form: accepts all 5 formats, shows type-specific limits
- AV banner: "Проверка безопасности — пилотный режим"
- Video preview icon: 🎬
- Business-language statuses only, no technical terms (ffprobe, clamav, etc.)
- Production requirement noted: "Для запуска в промышленную эксплуатацию потребуется обязательная проверка файлов"

## Profile

**Active:** `KSO_PORTRAIT_768x1024_v1` (768×1024 portrait)
**Deferred:** 1440×1080 — not broken, stays as future profile

## Tests

### Backend (test_media_validation_443.py — 27 tests)
- 12 video tests (integrity, MIME mismatch, size, valid MP4, wrong dimensions, landscape, too long, audio)
- 9 GIF tests (valid, empty, not-gif, wrong MIME, wrong dims, too many frames, too large, corrupted)
- 6 AV scanner tests (NoScanner never clean, ClamAV availability, factory, infected blocks)
- 4 policy tests (pilot_dev vs production, fake AV ban in notes, pilot warning)
- 3 upload validation tests (allowed types, size limits)

### Portal (8 new tests)
- AV pilot warning visible
- Manual moderation mentioned
- Production AV requirement mentioned
- No technical AV terms (clamav, ffprobe, daemon, socket)
- Video preview icon 🎬
- GIF in allowed types
- MP4/WebM in allowed types

## Regression

| Step | Backend | Portal |
|------|---------|--------|
| 44.3 | 748/0 | 683/0 |

## Deferred / Remaining

- Real ClamAV installation on production server
- Production AV policy activation (`av_policy_mode=production`)
- Video codec validation for vp8/vp9/av1 (requires test files)
- Audio track removal/re-encode pipeline
- HDR/color space validation
- Multi-profile dimension support (1440×1080, 1920×1080)

## AV Policy FAQ

**Q:** Why is AV scanner optional?
**A:** ClamAV requires system-level installation (daemon + signature updates). In pilot/dev, manual moderation suffices. Production will require `scan_status=clean`.

**Q:** Can we auto-approve without AV?
**A:** In pilot mode — yes, with explicit audit trail (`av_warning=true` in audit event). In production — no, `require_av_clean_for_publication=true` blocks approval.

**Q:** How to enable production AV?
**A:** Set `require_av_clean_for_publication=true` in `CreativePolicyResponse` (or change `av_policy_mode=production`), install ClamAV, restart. The scanner auto-detects ClamAV at startup.
