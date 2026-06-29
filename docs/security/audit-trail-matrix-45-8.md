# Audit Trail Matrix — 45.8

**Coverage: 14/20 (70%) — up from 8/20 (40%)**

| # | Action | Audit Call | Target | Details | Severity |
|---|---|---|---|---|---|
| 1 | campaign.create | ✅ campaign.create | campaign | name | HIGH |
| 2 | campaign.update | ✅ campaign.update | campaign | updated_fields | MEDIUM |
| 3 | campaign.archive | ✅ campaign.archive | campaign | — | MEDIUM |
| 4 | campaign.submit | ✅ campaign.submit | campaign | — | HIGH |
| 5 | campaign.approve | ✅ (via approvals.approve) | approval | — | HIGH |
| 6 | campaign.reject | ✅ (via approvals.reject) | approval | — | HIGH |
| 7 | creative.upload | ✅ creative.upload | creative | name, mime_type | MEDIUM |
| 8 | creative.update | ✅ creative.update | creative | updated_fields | LOW |
| 9 | creative.archive | ✅ creative.archive | creative | — | LOW |
| 10 | creative.submit_review | ✅ creative.submit_review | creative | — | MEDIUM |
| 11 | creative.approve | ✅ creative.approve | creative | — | MEDIUM |
| 12 | creative.reject | ✅ creative.reject | creative | — | MEDIUM |
| 13 | campaign_creative.bind | ✅ campaign_creative.bind | campaign | campaign_code, creative_code | MEDIUM |
| 14 | campaign_creative.unbind | ❌ | — | — | MEDIUM |
| 15 | schedule.create | ✅ (added 45.8) | schedule | name, campaign_code | HIGH |
| 16 | schedule.update | ✅ (added 45.8) | schedule | updated_fields | MEDIUM |
| 17 | schedule.archive | ✅ (added 45.8) | schedule | — | MEDIUM |
| 18 | schedule_slot.create | ✅ (added 45.8) | schedule_slot | schedule_code, slot_code | MEDIUM |
| 19 | schedule_slot.update | ✅ (added 45.8) | schedule_slot | schedule_code | LOW |
| 20 | schedule_slot.disable | ✅ (added 45.8) | schedule_slot | schedule_code | LOW |
| 21 | publication.create | ✅ publication.create | publication_batch | name, campaign_code | HIGH |
| 22 | publication.request_approval | ✅ publication.request_approval | publication_batch | — | HIGH |
| 23 | publication.generate | ✅ publication.generate | publication_batch | — | HIGH |
| 24 | publication.approve | ✅ publication.approve | publication_batch | — | HIGH |
| 25 | publication.publish | ✅ publication.publish | publication_batch | — | HIGH |
| 26 | publication.cancel | ✅ publication.cancel | publication_batch | — | MEDIUM |
| 27 | user.create | ❌ | — | — | HIGH |
| 28 | user.deactivate | ❌ | — | — | HIGH |
| 29 | role.assign | ❌ | — | — | HIGH |
| 30 | login | ❌ | — | — | MEDIUM |
| 31 | logout | ❌ | — | — | LOW |

### Audit Event Schema
```
admin_audit_events:
  id: UUID
  actor_user_id: UUID → users
  action: str (e.g., "campaign.create", "schedule.archive")
  target_type: str (e.g., "campaign", "schedule", "creative")
  target_ref: str (code or ID)
  details_json: JSONB (action-specific metadata)
  occurred_at: TIMESTAMPTZ
```

### Remaining Gaps
- **campaign_creative.unbind**: No backend endpoint currently — deferred
- **user.create/deactivate**: Requires admin module expansion — deferred to 45.8+
- **role.assign**: Linked to user management — deferred
- **login/logout**: Requires auth middleware changes — deferred to 46.1 (compliance)
