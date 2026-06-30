# B.3 — Placement Closure Gate

**Date:** 2026-06-29  
**Closure commit:** (to be filled)

---

## Executive Summary

B.3 реализовал Placement как отдельную доменную сущность с полным lifecycle: schema migration + ORM models + service layer + 7 API endpoints + RBAC/RLS via parent Campaign advertiser scope + audit trail + seed + 65 backend tests + portal read-only visibility. 7 подэтапов, 7 коммитов, 0 новых regression failures.

---

## Commits in B.3

| # | Commit | Sub-step |
|---|---|---|
| 1 | `aada294` | B.3.0 — Placement Design Gate |
| 2 | `460f23b` | B.3.1 — Schema Migration + ORM Models |
| 3 | `ce8c439` | B.3.1.1 — Regression Discrepancy Gate |
| 4 | `3ff11ca` | B.3.2 — Placement Service + API |
| 5 | `8676c59` | B.3.3 — Placement Functional Validation Gate |
| 6 | `de763c7` | B.3.3.1 — Regression Delta + Real API Validation |
| 7 | `f233760` | B.3.4 — Portal Placement Read-Only |

---

## What B.3 Delivered

### Database
- `placements.channel_id` (UUID, NOT NULL, FK → channels)
- `placements` table: campaign_id, channel_id, placement_code, name, status, priority, start_date, end_date, created_by, timestamps
- `placement_targets` table: placement_id, target_type, store_id, display_surface_id, logical_carrier_id

### ORM
- `Placement` model (`channels/models.py`)
- `PlacementTarget` model (`channels/models.py`)
- `Campaign.placements` relationship (`campaigns/models.py`)

### Service Layer (12 functions)
- `list_campaign_placements`, `create_campaign_placement`
- `get_placement`, `update_placement`, `cancel_placement`
- `get_placement_targets`, `set_placement_targets`
- `_get_placement_or_404`, `_get_campaign_for_placement` (helpers)

### API (7 endpoints)
| Method | Path | Permission |
|---|---|---|
| GET | `/api/campaigns/{cid}/placements` | campaigns.read |
| POST | `/api/campaigns/{cid}/placements` | campaigns.create |
| GET | `/api/placements/{id}` | campaigns.read |
| PUT | `/api/placements/{id}` | campaigns.manage |
| DELETE | `/api/placements/{id}` | campaigns.manage (→ cancel) |
| GET | `/api/placements/{id}/targets` | campaigns.read |
| PUT | `/api/placements/{id}/targets` | campaigns.manage |

### RBAC/RLS
- Advertiser scope inherited from parent Campaign
- `resolve_user_scope_context` + `assert_object_in_advertiser_scope`
- Cross-advertiser access → 403 (confirmed in B.3.3.1)

### Audit (4 actions)
- `placement.create` — target_ref = placement_code
- `placement.update` — target_ref = placement_code
- `placement.cancel` — target_ref = placement_code
- `placement.targets.update` — target_ref = placement_code (B.3.3 fix)

### Portal
- Campaign detail: read-only placements table (placement_code, name, status, priority, period)
- Placement detail: `/placements/{id}` — read-only card + targets table
- Empty states: "Размещения пока не созданы", "Цели не заданы"
- No CRUD, no forms, no JS/CDN/localStorage

### Seed
- `_seed_placement()` — idempotent, KSO channel_id, surface-linked target

---

## What B.3 Did NOT Change

| Item | Status |
|---|---|
| `campaign_targets` | ✅ Preserved |
| `kso_placements` | ✅ Preserved |
| `generated_manifests` FK | ✅ Unchanged |
| Publication flow | ✅ Unchanged |
| Campaign submit validation | ✅ Unchanged |
| Portal CRUD for placements | ✅ Not added |
| JS/CDN/localStorage | ✅ None added |
| DROP/TRUNCATE | ✅ None executed |

---

## Test Baseline

### Backend
| Metric | Value |
|---|---|
| Collected | 947 |
| Passed | 881 |
| Failed | 66 (all pre-existing) |
| Collection errors | 0 |
| B.1+B.2 | 38/38 |
| Core | 73/73 |
| B.3 total | 65/65 |

### Portal
| Metric | Value |
|---|---|
| Passed | 863 |
| Failed | 0 |
| Skipped | 32 |

---

## DB Integrity

| Check | Result |
|---|---|
| `placements.channel_id` NOT NULL | 0 nulls ✅ |
| Valid channel_id FK | 0 orphans ✅ |
| Orphan placement_targets | 0 ✅ |
| Invalid display_surface_id | 0 ✅ |
| campaign_targets exists | ✅ |
| kso_placements exists | ✅ |
| generated_manifests exists | ✅ |
| Physical DELETE on cancel | None ✅ |

---

## Known Risks / Deferred

| Item | Risk | Reason |
|---|---|---|
| 66 pre-existing failures | Low | All in pre-B.3 modules (airtime, creative_preview, inventory, kso_readiness, user_crud). 0 related to Placement. |
| Portal CRUD | Medium | Intentionally deferred to avoid scope creep. Backend API fully functional. |
| Channel name in portal placements | Low | Currently shows "—" for channel; needs channel list API integration. |
| user_crud ordering fragility | Low | 9 tests fail when run after seed tests due to event-loop conflict. Pre-existing. |

---

## GO/NO-GO for B.4

**✅ GO — B.4 Channel Orchestrator Skeleton**

B.3 delivers a complete, tested Placement domain with:
- Schema migration (Alembic, NOT NULL, FK)
- ORM models (Placement, PlacementTarget, Campaign.placements)
- Service layer (12 functions with validation)
- API (7 endpoints with permissions)
- RBAC/RLS (advertiser scope via parent Campaign)
- Audit (4 actions, placement_code as target_ref)
- Seed (idempotent)
- Portal (read-only, Russian, no JS)
- Tests (65 backend + 21 portal, 0 new failures)
- All legacy preserved, no destructive changes
