# Audit Trail Matrix — 45.8.1 (Closure)

**Coverage: 20/20 (100%) — исправлено с 14/20**

> Исходная матрица 45.8 занижала coverage: identity domain audits (create_user, assign_role,
> status_user, assign_rls_scopes) писались через `record_admin_action` в ту же таблицу
> `admin_audit_events`, но не были учтены. campaign_creative.unbind также уже был покрыт.

## Core 20 Business Audit Actions

| # | Action | Status | Domain | Router/Service | Severity |
|---|---|---|---|---|---|
| 1 | campaign.create | ✅ | campaigns | router.py:75 | HIGH |
| 2 | campaign.update | ✅ | campaigns | router.py:107,380 | MEDIUM |
| 3 | campaign.archive | ✅ | campaigns | router.py:406 | MEDIUM |
| 4 | campaign.submit | ✅ | campaigns | router.py:521 | HIGH |
| 5 | campaign.approve | ✅ | approvals | router.py:103 (approval.approve) | HIGH |
| 6 | campaign.reject | ✅ | approvals | router.py:134 (approval.approve+decision) | HIGH |
| 7 | campaign.bind_creative | ✅ | campaigns | router.py:587 | MEDIUM |
| 8 | campaign.unbind_creative | ✅ | campaigns | router.py:614 | MEDIUM |
| 9 | creative.create | ✅ | media | router.py:68 | MEDIUM |
| 10 | creative.upload_version | ✅ | media | router.py:122 | MEDIUM |
| 11 | creative.submit_review | ✅ | media | router.py:145,354 | MEDIUM |
| 12 | creative.approve | ✅ | media | router.py:489 | MEDIUM |
| 13 | creative.reject | ✅ | media | router.py:550 | MEDIUM |
| 14 | publication_batch.create | ✅ | publications | router.py:52 | HIGH |
| 15 | publication_batch.publish | ✅ | publications | router.py:201 | HIGH |
| 16 | schedule.create | ✅ | scheduling | router.py:242 | HIGH |
| 17 | user.create | ✅ | identity | service.py:393 | HIGH |
| 18 | user.deactivate | ✅ | identity | service.py:669 (status_user) | HIGH |
| 19 | role.assign | ✅ | identity | service.py:528 | HIGH |
| 20 | rls_scope.assign | ✅ | identity | service.py:734 | MEDIUM |

## Negative/Security Audit Events

| # | Action | Status | Domain | Details |
|---|---|---|---|---|
| N1 | approval.denied_self_approve | ✅ (45.8.1) | approvals | Maker-checker violation audit |

## Additional Covered Actions (beyond core 20)

| Action | Domain | Notes |
|---|---|---|
| creative.reject | media | `creative.reject` |
| creative.return_for_rework | media | Additional moderation action |
| creative.archive | media | Lifecycle |
| publication_batch.request_approval | publications | Workflow |
| publication_batch.generate_manifests | publications | Workflow |
| publication_batch.approve | publications | Workflow |
| publication_batch.cancel | publications | Workflow |
| publication_batch.create_from_campaign | campaigns | Cross-domain |
| schedule.update | scheduling | Lifecycle |
| schedule.archive | scheduling | Lifecycle |
| schedule_slot.create | scheduling | Lifecycle |
| schedule_slot.update | scheduling | Lifecycle |
| schedule_slot.disable | scheduling | Lifecycle |
| approval.request | approvals | Workflow |

## Separate Audit Tables

| Table | Actions |
|---|---|
| login_audit_events | login_success, login_failure |

## Audit Event Schema

```
admin_audit_events:
  id: UUID
  actor_user_id: UUID → users
  action: str (dot.notation)
  target_type: str
  target_ref: str (code or ID)
  details_json: JSONB (secrets-stripped)
  occurred_at: TIMESTAMPTZ
```

## Secrets Safety

`FORBIDDEN_DETAILS` frozenset strips: password, password_hash, secret, device_secret,
access_token, refresh_token, token, token_hash, backend_url, minio_endpoint, private_key.

All audit paths use `_strip_forbidden()` before write. Verified by `test_audit_hardening.py`.
