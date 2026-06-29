# RLS Scope Matrix — 45.8

**Verified domains with advertiser scope enforcement:**

| Domain | Route | Method | Scope Check | Location |
|---|---|---|---|---|
| campaigns | /api/campaigns | GET | apply_advertiser_rls | router + service |
| campaigns | /api/campaigns/{id} | GET | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id} | PUT | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/submit | POST | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/approve | POST | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/reject | POST | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/archive | POST | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/channels | GET/POST | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/targets | GET/POST | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/renditions | GET/POST | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/creatives | GET | assert_object_in_advertiser_scope | router |
| campaigns | /api/campaigns/{id}/creatives | POST | assert + creative adv check | router |
| campaigns | /api/campaigns/{id}/publication-batches | POST | assert_object_in_advertiser_scope | router |
| media | /api/creatives | GET | apply_advertiser_rls | router + service |
| media | /api/creatives | POST | assert_object_in_advertiser_scope | router |
| media | /api/creatives/{id} | GET | assert_object_in_advertiser_scope | router |
| media | /api/creatives/{id}/archive | POST | assert_object_in_advertiser_scope | router |
| media | /api/creatives/{id}/preview | GET | assert_object_in_advertiser_scope | router |
| media | /api/creatives/{id}/submit-review | POST | scope_ctx resolved | router |
| media | /api/creatives/{id}/approve | POST | scope_ctx resolved | router |
| media | /api/creatives/{id}/reject | POST | scope_ctx resolved | router |
| publications | /api/publication-batches | GET | scope_ctx resolved | router |
| publications | /api/publication-batches/{id} | GET | assert_object_in_advertiser_scope | router |
| publications | /api/publication-batches/{id}/request-approval | POST | assert_object_in_advertiser_scope | router |
| publications | /api/publication-batches/{id}/generate | POST | assert_object_in_advertiser_scope | router |
| publications | /api/publication-batches/{id}/approve | POST | assert_object_in_advertiser_scope | router |
| publications | /api/publication-batches/{id}/publish | POST | assert_object_in_advertiser_scope | router |
| publications | /api/publication-batches/{id}/cancel | POST | scope_ctx resolved | router |
| publications | /api/publication-batches/{id}/targets | GET | assert_object_in_advertiser_scope | router |
| publications | /api/publication-batches/{id}/manifests | GET | assert_object_in_advertiser_scope | router |
| scheduling | /api/schedules | GET/POST | assert_object_in_advertiser_scope | router |
| scheduling | /api/schedules/{code} | GET/PATCH | assert_object_in_advertiser_scope | router |
| scheduling | /api/schedules/{code}/archive | POST | assert_object_in_advertiser_scope | router |
| scheduling | /api/schedules/{code}/items | GET/POST | assert_object_in_advertiser_scope | router |
| scheduling | /api/schedules/{code}/items/{slot} | PATCH/DELETE | assert_object_in_advertiser_scope | router |
| approvals | /api/approvals | GET | scope_ctx resolved | router |
| approvals | /api/approvals/submit | POST | scope_ctx + assert | router + service |
| approvals | /api/approvals/{id}/approve | POST | assert_object_in_advertiser_scope | service |
| approvals | /api/approvals/{id}/reject | POST | assert_object_in_advertiser_scope | service |
| manifests | /api/manifests | POST | assert_object_in_advertiser_scope | router |
| manifests | /api/manifests/{id} | GET | assert_object_in_advertiser_scope | router |
| manifests | /api/manifests/{id}/publish | POST | assert_object_in_advertiser_scope | router |
| reports | /api/reports/* | GET | scope_ctx filtered | router + service |
| device-dashboard | /api/device-dashboard | GET | scope_ctx filtered | router |
| proof-of-play | /api/proof-of-play/* | GET | scope_ctx filtered | router |

**Total scope-enforced routes: 47**

**Admin bypass:** `resolve_user_scope_context` returns empty context for system_admin/security_admin — full access.

**Portal 403 handling:** Added to `/campaigns/{campaign_code}`. Backend scope violations produce styled Russian "Доступ запрещён" page.
