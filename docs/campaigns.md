# Campaign Workflow

## Business Principle

**Campaign adds ad material to schedule. Publication builds full manifest/playlist for KSO. Local KSO playlist is never mutated piecemeal.**

## Workflow

```
1. Create Campaign (draft)     →  /campaigns/create (business form)
2. Bind Creatives              →  POST /campaigns/by-code/{code}/creatives
3. Configure Schedule          →  /campaigns/create creates Schedule + Slots
4. Submit for Review           →  POST /campaigns/by-code/{code}/submit (draft → in_review)
5. Approve                     →  POST /api/campaigns/{id}/approve (in_review → approved)
6. Generate Manifest           →  POST /api/manifests
7. Publish                     →  POST /api/manifests/{code}/publish

After publication:
- KSO polls gateway for current manifest
- Sidecar agent updates local cache
- Player renders scheduled creatives
- Proof of Play events flow from KSO → gateway → PoP pipeline
```

## Business Campaign Creation (41.2)

The portal `/campaigns/create` page provides a business-friendly form:

### Fields

| Field | Required | Description |
|---|---|---|
| campaign_code | Yes | Unique code (a-z0-9_-), 3-64 chars |
| name | Yes | Campaign name, 1-255 chars |
| description | No | Free text, up to 500 chars |
| advertiser_code | No | Informational dropdown |
| creative_code | No | Creative to bind |
| device_code | No | KSO device for placement |
| date_from | Yes | Campaign start date |
| date_to | Yes | Campaign end date |
| timezone | Yes | Default: Europe/Moscow |
| days_of_week | Yes | Checkboxes: Пн–Вс |
| time_window_preset | Yes | all_day / morning / day / evening / custom |

### Creation Pipeline

On submit, the portal orchestrates 4 backend calls:

1. **`POST /api/campaigns/by-code`** — Create campaign (draft) using internal technical context
2. **`POST /api/placements`** — Create placement (campaign→creative→device) if device selected
3. **`POST /api/schedules`** — Create schedule linked to campaign
4. **`POST /api/schedules/{code}/items`** — Create schedule slots (one per selected day_of_week)

### Submit for Approval

- `POST /campaigns/by-code/{code}/submit` → campaign status: draft → in_review
- Requires `campaigns.manage` permission
- RLS: advertiser scope enforced
- Audit: campaign.submit event written

### Approval

See [Approvals domain documentation](../backend/app/domains/approvals/) for approval workflow.

### Manifest Generation & Publication

After a campaign is approved, it is included in the next manifest generation cycle.
Publication creates a full manifest/playlist — KSO playlist is never mutated piecemeal.

## Permissions

| Role | create | read | manage | approve |
|---|---|---|---|---|
| system_admin | ✓ | ✓ | ✓ | ✓ |
| ad_manager | ✓ | ✓ | ✓ | — |
| approver | — | ✓ | — | ✓ |
| analyst | — | ✓ | — | — |
| security_admin | — | ✓ | — | — |
| operations | — | ✓ | — | — |
