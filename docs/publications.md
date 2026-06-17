# Manifest & Publication Core

## Overview

Шаг 9 — внутреннее ядро публикации. Берёт **approved schedule_run**, группирует schedule_items по целям публикации (inventory_unit → logical_carrier → display_surface → store) и формирует версионированный manifest document в JSONB.

**Это ещё не Device Gateway, не плеер, не PoP и не реальная доставка на устройства.**

Статус `published` на Шаге 9 означает **«готово для будущего Device Gateway»**, а не «доставлено на устройство». Cancel published batch — логическая отмена (не трогает устройства, т.к. Device Gateway ещё нет).

---

## Tables

### `publication_batches`
Единый запуск публикации, привязанный к одному approved schedule_run.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| schedule_run_id | UUID FK → schedule_runs | NOT NULL |
| campaign_id | UUID FK → campaigns | NOT NULL, derived from schedule_run |
| booking_id | UUID FK → campaign_bookings | NOT NULL, derived from schedule_run |
| status | VARCHAR(20) | draft, generated, approved, published, failed, cancelled |
| comment | TEXT | |
| created_by | UUID FK → users | |
| created_at | TIMESTAMPTZ | |
| approved_by | UUID FK → users | nullable |
| approved_at | TIMESTAMPTZ | nullable |
| published_by | UUID FK → users | nullable |
| published_at | TIMESTAMPTZ | nullable |
| cancelled_by | UUID FK → users | nullable |
| cancelled_at | TIMESTAMPTZ | nullable |
| updated_at | TIMESTAMPTZ | |

### `publication_targets`
Конкретная цель публикации.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| publication_batch_id | UUID FK → publication_batches | |
| inventory_unit_id | UUID FK → inventory_units | |
| logical_carrier_id | UUID FK → logical_carriers | nullable |
| display_surface_id | UUID FK → display_surfaces | nullable |
| channel_id | UUID FK → channels | |
| store_id | UUID FK → stores | |
| status | VARCHAR(20) | pending, generated, published, failed, cancelled |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

UNIQUE(publication_batch_id, inventory_unit_id)

### `manifest_versions`
Версия manifest для конкретной цели.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| publication_batch_id | UUID FK → publication_batches | |
| publication_target_id | UUID FK → publication_targets | |
| manifest_version | INTEGER | 1, 2, … |
| manifest_json | JSONB | |
| manifest_hash | VARCHAR(64) | SHA-256 canonical JSON |
| signature | VARCHAR(512) | nullable — stub, настоящая подпись будет отдельным шагом (PKI/HSM) |
| status | VARCHAR(20) | draft, approved, published, cancelled |
| created_at, approved_at, published_at | TIMESTAMPTZ | |

UNIQUE(publication_target_id, manifest_version)

### `manifest_items`
Связь manifest_version → конкретный schedule_item и media.

| Column | Type |
|--------|------|
| id | UUID PK |
| manifest_version_id | UUID FK |
| schedule_item_id | UUID FK |
| campaign_id | UUID FK |
| campaign_rendition_id | UUID FK |
| rendition_id | UUID FK |
| creative_version_id | UUID FK |
| media_path | VARCHAR(1000) — MinIO object key, без токенов |
| sha256 | VARCHAR(64) |
| date, time_from, time_to | Date, Time |
| loop_position, spot_position | INTEGER |

### `publication_events`
Аудиторский журнал.

| Column | Type |
|--------|------|
| id | UUID PK |
| publication_batch_id | UUID FK |
| event_type | VARCHAR(30): batch_created, manifest_generated, manifest_generation_failed, batch_approved, batch_published, batch_cancelled, validation_failed |
| actor_user_id | UUID FK → users, nullable |
| message | TEXT |
| details_json | JSONB |
| created_at | TIMESTAMPTZ |

---

## Status Machine

```
draft → generated (POST generate)
draft → failed    (POST generate, если ошибка)
draft → cancelled (POST cancel)

generated → generated (POST generate — пересоздание, старые version → cancelled)
generated → approved  (POST approve)
generated → cancelled (POST cancel)

approved → published  (POST publish)
approved → cancelled  (POST cancel)

published → cancelled (POST cancel — логическая отмена)

failed → (только чтение)
cancelled → (терминальный)
```

---

## Manifest Structure

```json
{
  "manifest_version": 1,
  "batch_id": "<uuid>",
  "target_id": "<uuid>",
  "inventory_unit": {"id": "<uuid>", "code": "main-hall-screen-1"},
  "logical_carrier_id": "<uuid>",
  "display_surface_id": "<uuid>",
  "store": {"id": "<uuid>", "code": "store-473"},
  "channel": {"id": "<uuid>", "code": "in-store-display"},
  "schedule": {
    "items": [
      {
        "date": "2026-06-18",
        "time_from": "08:00:00",
        "time_to": "08:00:15",
        "loop_position": 2,
        "spot_position": 3,
        "media": {
          "path": "creatives/abc/v1/uuid.webp",
          "sha256": "deadbeef...",
          "mime_type": "image/png",
          "width": 1920,
          "height": 1080,
          "duration_seconds": null
        },
        "campaign": {"id": "<uuid>", "code": "summer-promo"},
        "rendition_id": "<uuid>",
        "campaign_rendition_id": "<uuid>"
      }
    ]
  }
}
```

**Правила:**
- Никаких `access_token`, `refresh_token`, `token`, `jwt`, `password`, `secret`, `credential`, `credentials`, `authorization`, `cookie`, `api_key`, `private_key`, `public_key`
- `media.path` — MinIO object key, без presigned URL и токенов
- `sha256` для верификации целостности
- `manifest_hash` = SHA-256 от canonical JSON (sort_keys, compact separators, ensure_ascii=False)
- `signature` — честный stub/nullable, настоящая подпись будет отдельным шагом с PKI/HSM

---

## Validation

| # | Check | Stage |
|---|-------|-------|
| 1 | schedule_run.status == "approved" | generate |
| 2 | schedule_items exist and status == "active" | generate |
| 3 | inventory_unit active + sellable | generate |
| 4 | channel_id matches | generate |
| 5 | creative.status == "approved" | generate |
| 6 | rendition.status == "valid" | generate |
| 7 | media_path not empty | generate |
| 8 | sha256 not empty | generate |
| 9 | MIME type in allowlist: image/jpeg, image/png, video/mp4, video/webm | generate |
| 10 | manifest_json has no forbidden keys (recursive) | generate |
| 11 | manifest canonical JSON ≤ MAX_MANIFEST_JSON_BYTES (10 MB) | generate |
| 12 | approve: batch.status == "generated" + has targets + versions + items | approve |
| 13 | approve: no validation_failed events | approve |
| 14 | publish: batch.status == "approved" + has approved versions | publish |

---

## Idempotency

| Situation | Behavior |
|-----------|----------|
| Published batch exists for schedule_run | New batch: 400 |
| Approved batch exists | New batch: 400 (cancel approved first) |
| Generated → generate again | New versions created, old draft versions → cancelled |
| Approved → generate | 400 |
| Published → any change | 400 |
| Published → cancel | Allowed (logical only) |
| Failed → create new batch | Allowed |
| Cancelled → any action | 400 |

---

## Permissions (4 new, total 44)

| Permission | System Admin | Ad Manager | Approver | Operations | Analyst | Security Admin | Advertiser | Device Service |
|------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| publications.read | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| publications.manage | ✅ | ✅ | — | — | — | — | — | — |
| publications.approve | ✅ | — | ✅ | — | — | ✅ | — | — |
| publications.publish | ✅ | — | — | ✅ | — | — | — | — |

Cancel permission:
- draft/generated/failed → publications.manage
- approved/published → publications.approve

---

## API Endpoints (11)

| Method | Path | Permission |
|--------|------|------------|
| POST | /api/publication-batches | publications.manage |
| GET | /api/publication-batches | publications.read |
| GET | /api/publication-batches/{id} | publications.read |
| POST | /api/publication-batches/{id}/generate | publications.manage |
| POST | /api/publication-batches/{id}/approve | publications.approve |
| POST | /api/publication-batches/{id}/publish | publications.publish |
| POST | /api/publication-batches/{id}/cancel | get_current_user (service picks right) |
| GET | /api/publication-batches/{id}/targets | publications.read |
| GET | /api/publication-batches/{id}/manifests | publications.read |
| GET | /api/manifest-versions/{id} | publications.read |
| GET | /api/publication-batches/{id}/events | publications.read |

DELETE не предусмотрено.
