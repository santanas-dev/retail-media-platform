# Campaigns Core

## Overview

Core campaign management — lifecycle, channel assignment, infrastructure targeting,
and validated rendition assignment.

## Models

### Campaign

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `order_id` | UUID → orders | FK, NOT NULL |
| `advertiser_id` | UUID → advertisers | Auto-populated from order |
| `brand_id` | UUID → brands | Nullable, must match order.brand_id if set |
| `name` | String(255) | |
| `objective` | String(100) | e.g. brand_awareness, sales, promo |
| `status` | String(20) | draft, in_review, approved, rejected, paused, cancelled, completed |
| `planned_start_date` | Date | |
| `planned_end_date` | Date | Must be >= start, within order bounds |
| `priority` | Integer | >= 0, default 0 |
| `budget` | Numeric(15,2) | >= 0 |
| `currency` | String(3) | Default RUB |
| `comment` | Text | |
| `created_by` | UUID → users | |
| `approved_by` | UUID → users | Set on approve |
| `approved_at` | DateTime | Set on approve |
| `rejection_reason` | Text | Set on reject |
| `created_at`, `updated_at` | DateTime | |

### CampaignChannel
Links campaign to media channels. UNIQUE(campaign_id, channel_id).

### CampaignTarget
Infrastructure targeting: all_stores, branch, cluster, store, logical_carrier, display_surface.
Only one id field filled per target, matching the target_type.

### CampaignRendition
Links campaign to validated renditions. UNIQUE(campaign_id, rendition_id).

## Lifecycle

```
draft → submit → in_review → approve → approved
  ↑                   ↓
  └── (resubmit) ── rejected ← reject
```

| Action | From | To | Permission |
|--------|------|----|-----------|
| Create | — | draft | campaigns.create |
| Edit | draft, rejected | — | campaigns.manage |
| Submit | draft, rejected | in_review | campaigns.manage |
| Approve | in_review | approved | campaigns.approve |
| Reject | in_review | rejected | campaigns.approve |

Submit and approve both require: ≥1 channel, ≥1 target, ≥1 active valid rendition
(with approved creative, matching campaign channel).

## API

| Method | Path | Permission |
|--------|------|-----------|
| GET | /api/campaigns | campaigns.read |
| POST | /api/campaigns | campaigns.create |
| GET | /api/campaigns/{id} | campaigns.read |
| PUT | /api/campaigns/{id} | campaigns.manage |
| POST | /api/campaigns/{id}/submit | campaigns.manage |
| POST | /api/campaigns/{id}/approve | campaigns.approve |
| POST | /api/campaigns/{id}/reject | campaigns.approve |
| GET | /api/campaigns/{id}/channels | campaigns.read |
| PUT | /api/campaigns/{id}/channels | campaigns.manage |
| GET | /api/campaigns/{id}/targets | campaigns.read |
| PUT | /api/campaigns/{id}/targets | campaigns.manage |
| GET | /api/campaigns/{id}/renditions | campaigns.read |
| PUT | /api/campaigns/{id}/renditions | campaigns.manage |

## Permissions

| Role | read | create | manage | approve |
|------|:----:|:------:|:------:|:-------:|
| system_admin | ✓ | ✓ | ✓ | ✓ |
| ad_manager | ✓ | ✓ | ✓ | — |
| approver | ✓ | — | — | ✓ |
| analyst | ✓ | — | — | — |
| security_admin | ✓ | — | — | — |
| operations | ✓ | — | — | — |

Using existing permissions only — no new permissions created.
