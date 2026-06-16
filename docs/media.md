# Media Library & Creative QA

## Overview

Domain for managing advertising creatives — business entities, uploaded file versions,
channel-specific renditions, and automated validation checks.

## Models

### Creative
Business entity for an advertising asset. Belongs to an advertiser, optionally a brand.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `advertiser_id` | UUID → advertisers | FK, NOT NULL, RESTRICT |
| `brand_id` | UUID → brands | FK, nullable, RESTRICT |
| `name` | String(255) | NOT NULL |
| `status` | String(20) | draft, in_review, approved, rejected, archived |
| `comment` | Text | |
| `created_by` | UUID → users | FK, RESTRICT |
| `created_at` | DateTime TZ | |
| `updated_at` | DateTime TZ | |

### CreativeVersion
A specific uploaded file version of a creative.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `creative_id` | UUID → creatives | FK, RESTRICT |
| `version` | Integer | Auto-incremented per creative |
| `original_filename` | String(500) | User's filename |
| `file_path` | String(1000) | MinIO object key |
| `mime_type` | String(100) | image/jpeg, image/png, video/mp4, video/webm |
| `file_size` | BigInteger | Bytes |
| `sha256` | String(64) | Hex digest |
| `width` | Integer | nullable (images only) |
| `height` | Integer | nullable (images only) |
| `duration_seconds` | Float | nullable (video only, not implemented) |
| `uploaded_by` | UUID → users | FK, RESTRICT |
| `status` | String(20) | uploaded, validated, rejected, archived |
| `created_at` | DateTime TZ | |

UNIQUE(creative_id, version)

### Rendition
Prepared variant linking a creative version to a channel and capability profile.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `creative_version_id` | UUID → creative_versions | FK, RESTRICT |
| `channel_id` | UUID → channels | FK, RESTRICT |
| `capability_profile_id` | UUID → capability_profiles | FK, nullable |
| `file_path` | String(1000) | Same as version (no transcoding yet) |
| `mime_type` | String(100) | |
| `file_size` | BigInteger | |
| `sha256` | String(64) | |
| `width` | Integer | nullable |
| `height` | Integer | nullable |
| `duration_seconds` | Float | nullable |
| `status` | String(20) | pending, valid, invalid, archived |
| `created_at` | DateTime TZ | |
| `updated_at` | DateTime TZ | |

### RenditionValidation
Result of a single validation check on a rendition.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `rendition_id` | UUID → renditions | FK, RESTRICT |
| `check_type` | String(50) | mime_type, file_size, sha256, resolution, capability_compliance |
| `result` | String(20) | passed, failed, warning |
| `details_json` | JSONB | Check-specific details |
| `checked_by` | UUID → users | FK, RESTRICT |
| `checked_at` | DateTime TZ | |

## API Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/api/creatives` | media.read | List creatives (?advertiser_id, ?status) |
| POST | `/api/creatives` | media.manage | Create creative |
| GET | `/api/creatives/{id}` | media.read | Get creative |
| PUT | `/api/creatives/{id}` | media.manage (+ media.approve for approved/rejected) | Update creative |
| POST | `/api/creatives/{id}/versions/upload` | media.manage | Upload file version (multipart) |
| GET | `/api/creatives/{id}/versions` | media.read | List versions |
| GET | `/api/creative-versions/{id}` | media.read | Get version metadata |
| GET | `/api/renditions` | media.read | List renditions (?creative_version_id, ?channel_id) |
| POST | `/api/renditions` | media.manage | Create rendition |
| GET | `/api/renditions/{id}` | media.read | Get rendition |
| POST | `/api/renditions/{id}/validate` | media.manage | Run validation checks |
| GET | `/api/renditions/{id}/validations` | media.read | List validation results |

## Permissions

| Role | media.read | media.manage | media.approve |
|------|:----------:|:------------:|:-------------:|
| system_admin | ✓ | ✓ | ✓ |
| ad_manager | ✓ | ✓ | — |
| approver | ✓ | — | ✓ |
| analyst | ✓ | — | — |
| security_admin | ✓ | — | — |
| operations | ✓ | — | — |
| advertiser | — | — | — |
| device_service | — | — | — |

## Storage (MinIO)

- Bucket: `retail-media` (from env)
- Object key pattern: `creatives/{creative_id}/{version}/{uuid}.{ext}`
- Only metadata stored in PostgreSQL — files in MinIO
- SHA-256 computed on upload (streaming)
- Allowed MIME types: image/jpeg, image/png, video/mp4, video/webm
- Max upload size: 500 MB

## Validation

Checks run on `POST /api/renditions/{id}/validate`:

| Check | How | Notes |
|-------|-----|-------|
| `mime_type` | Against allowlist | |
| `file_size` | Against global max + profile max_file_size | |
| `sha256` | Integrity (DB value) | Verified on upload |
| `resolution` | Pillow (images only) | Compared to profile.resolution |
| `capability_compliance` | formats_json, size, etc. | |
| `duration` | Skipped | Needs ffprobe |

Files rejected on upload:
- SVG, HTML, JS, ZIP, Canvas content
- Any MIME type not in allowlist
- Invalid/corrupt images (Pillow verification)
