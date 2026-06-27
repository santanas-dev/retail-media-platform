# Creative QA & Media Validation (44.2 + 44.2.1)

**Status:** ✅ Complete (patch 44.2.1 applied)
**Date:** 2026-06-16
**Commits:** 5e9fa6e (44.2), TBD (44.2.1)

## Scope

Production-ready creative/media QA for v1 KSO pilot, covering:
- Safe upload with SHA-256
- Format/size/dimension validation
- Dangerous type blocking
- Moderation workflow (submit-review → approve/reject)
- Campaign binding gating
- AV scanner contract (no fake pass)

## Profile

**Active profile:** `KSO_PORTRAIT_768x1024_v1` — matches physical test KSO (768×1024 portrait)

The legacy 1440×1080 (from TZ v2.5 §7.1) is deferred as a future profile. The storage layer uses explicit constants (`KSO_PORTRAIT_WIDTH=768`, `KSO_PORTRAIT_HEIGHT=1024`) — no hidden global replacement. Future profiles can be added as separate constants or a profile registry.

## Allowed / Blocked / Deferred Formats

| Format | Status | Reason |
|--------|--------|--------|
| PNG, JPEG | ✅ Allowed | 768×1024 portrait |
| MP4, WebM | 📅 Deferred | Needs codec/duration/audio validation (separate step) |
| GIF | 📅 Deferred | Needs duration/CPU validation |
| HTML, JS, SVG, ZIP, TAR, EXE, DLL, SH, PY, RB, PHP, JAR, CLASS | 🚫 Blocked | Security — SVG can contain JS |
| Unknown MIME (`application/octet-stream`) | 🚫 Blocked | Rejected at upload |

## AV Scanner Contract

### Policy modes

| Mode | `av_policy_mode` | `require_av_clean` | Behaviour |
|------|-------------------|---------------------|-----------|
| Pilot / Dev (current) | `pilot_dev` | `false` | Creative can be approved manually without AV scan. Warning shown in UI. Audit event recorded. |
| Production | `production` | `true` | `scan_status=clean` required before publication. `not_configured` = blocked. |

### Scan status values

| Status | Meaning | Can publish? (pilot) | Can publish? (production) |
|--------|---------|----------------------|---------------------------|
| `not_configured` | AV scanner not set up | ✅ (after manual approval) | ❌ |
| `pending` | Submitted to scanner, awaiting result | ❌ (wait for result) | ❌ |
| `clean` | Scan passed | ✅ | ✅ |
| `infected` | Malware detected | ❌ | ❌ |
| `failed` | Scanner error | ❌ (retry needed) | ❌ |

### What we do NOT do

- ❌ Fake AV pass (auto-setting `scan_status=clean` without real scanner)
- ❌ AV test integration that can be mistaken for production
- ❌ Mock scanner in production code path

## Moderation Workflow

```
upload → draft (with scan_status=not_configured)
  → submit-review → pending_review
    → approve → approved (audit: who, when, reason)
    → reject → rejected (audit: who, when, reason_code, comment)
  → archive → archived
```

- Only `approved` creatives can be bound to campaigns
- Only `approved` creatives can be published
- Rejected/pending_review/validation_failed creatives → HTTP 400 when binding

## Campaign Binding Gate

Campaign binding (`bind_campaign_creative`) checks:
- `creative.status == "approved"` → allowed
- `creative.status in (rejected, pending_review, validation_failed, draft, archived)` → 400 rejected

## Backend Changes (44.2)

### New
- `Creative.scan_status` column (SQLAlchemy + Alembic migration 032)
- `CreativeAVScanner` interface in schemas
- Creative policy endpoint: `GET /api/creatives/policy`
- Moderation endpoints: `POST /api/creatives/{code}/submit-review`, `/approve`, `/reject`, `/archive`
- Duplicate SHA-256 detection before upload
- MP4 disguise detection (magic bytes `ftyp` check)

### Modified
- `upload_creative_combined()` — KSO profile 768×1024, dangerous type blocking, MIME check
- `bind_campaign_creative()` — requires `status == "approved"`
- `creative_list()` — enriches with `scan_status`
- Portal `/creatives` — summary cards, moderation actions, scan_status display

## Backend Changes (44.2.1)

### Fixed
- DDL in 3 test files missing `scan_status` column (caused 19 cascading failures)
- Stale docstring `1440×1080` → `768×1024 portrait` in router.py
- Campaign binding mock test missing `creative.status = "approved"`
- Policy schema: added `av_policy_mode` and `require_av_clean_for_publication` fields

### Added
- 3 campaign binding gate tests: rejected/pending_review/validation_failed creatives rejected

## Tests

### Backend (added in 44.2)
- Allowed JPG/PNG accepted
- Dangerous extensions rejected (HTML, JS, ZIP, EXE, SVG, etc.)
- MIME mismatch rejected
- Oversized file rejected
- Invalid dimensions rejected
- SHA-256 calculated
- Duplicate hash detected
- AV not_configured does not become clean
- Validation_failed creative cannot be approved
- Version replacement creates new version
- Moderation approve/reject audited

### Backend (added in 44.2.1)
- `test_bind_rejected_creative_fails` — rejected creative → 400
- `test_bind_pending_review_creative_fails` — pending_review → 400
- `test_bind_validation_failed_creative_fails` — validation_failed → 400
- `test_bind_creative_idempotent` — fixed (added `status="approved"`)

### Portal
- `/creatives` renders QA summary
- Business labels visible, technical labels absent
- Scan status display ("Проверка безопасности не настроена")
- Warning visible when AV not configured
- Moderation action buttons

## Regression

| Step | Backend | Portal |
|------|---------|--------|
| 44.2 (initial) | 690/20 | 669/0 |
| 44.2.1 (patched) | 710/0 | 676/0 |

## Deferred to Production

- MP4/WebM video validation (codec, duration, audio check)
- GIF validation (duration, CPU cost)
- Real AV scanner integration
- Multi-profile support (1440×1080, other aspect ratios)
- HTML5 creative support (requires ИБ approval)

## AV Policy FAQ

**Q:** Why not fake AV pass?
**A:** Fake AV creates false confidence. If we mark everything "clean" without real scanning, we miss real malware. The honest approach: either integrate a real scanner, or show "not configured" and let human approval handle it with audit trail.

**Q:** What changes for production?
**A:** Set `require_av_clean_for_publication=true` (or change `av_policy_mode=production`). Then integrate a real AV scanner (ClamAV, commercial, or cloud API). The `CreativeAVScanner` interface is the integration point.

**Q:** Can we use ClamAV?
**A:** Yes. The `CreativeAVScanner` interface accepts any implementation. ClamAV (`clamd` socket or `clamscan` subprocess) is a natural fit for on-prem KSO deployment.
