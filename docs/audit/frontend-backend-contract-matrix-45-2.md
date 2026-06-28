# Frontend-Backend Contract Matrix — 45.2

**Date:** 2026-06-28
**Part of:** Pre-demo functional audit (45.2)

---

## Page → Backend Route Mapping

| Portal Page | User Action | Backend Route | Method | Table(s) | Test Coverage |
|-------------|------------|---------------|--------|----------|---------------|
| /login | Login | /api/auth/login | POST | users, refresh_tokens | test_main.py |
| /login | — | /api/auth/me | GET | users, user_roles, roles, role_permissions | test_main.py |
| /dashboard | View KPI | /api/campaigns | GET | campaigns | test_main.py |
| /dashboard | View KPI | /api/media | GET | creatives | test_main.py |
| /dashboard | View KPI | /api/scheduling/* | GET | schedule_runs | test_main.py |
| /dashboard | View KPI | /api/publications | GET | publication_batches | test_main.py |
| /creatives | List | /api/media | GET | creatives | test_main.py |
| /creatives/moderation/queue | List pending | /api/media/moderation/queue | GET | creatives, moderation_actions | test_main.py |
| /creatives/{code} | View detail | /api/media/by-code/{code} | GET | creatives, moderation_actions | test_main.py |
| /campaigns | List | /api/campaigns | GET | campaigns | test_main.py |
| /campaigns/create | Create | /api/campaigns | POST | campaigns | test_main.py |
| /schedule | List runs | /api/scheduling/* | GET | schedule_runs, schedule_items | test_main.py |
| /approvals | List pending | /api/campaigns (filter=submitted) | GET | campaigns | test_main.py |
| /approvals | Approve | /api/campaigns/{id}/approve | POST | campaigns | test_main.py |
| /approvals | Reject | /api/campaigns/{id}/reject | POST | campaigns | test_main.py |
| /publications | List batches | /api/publications | GET | publication_batches | test_main.py |
| /reports | View reports | /api/reports/* | GET | campaign_reports, proof_of_play | test_main.py |
| /inventory | View inventory | /api/inventory/* | GET | inventory_units, stores | test_main.py |
| /readiness | View status | /api/readiness/* | GET | readiness_checks | test_main.py |
| /readiness/business-acceptance | View BA | /api/readiness/business-acceptance | GET | readiness_checks | test_main.py |
| /stores | List | /api/organization/stores | GET | stores, branches | test_main.py |
| /admin | User list | /api/users | GET | users | test_main.py |
| /admin | Role list | /api/roles | GET | roles | test_main.py |
| /admin | Audit log | /api/admin/audit | GET | audit_events | test_main.py |
| /deployment | Deployment status | /api/deployment/* | GET | deployment_records | test_main.py |

---

## Data Flow Verification

### GET Pages: All return HTTP 200 with backend data
- 15/15 portal pages return 200 under system_admin
- No pages use fake/demo data as primary source
- All KPI cards, lists, and statuses sourced from backend API

### POST Actions: Forms submit to real backend handlers
- `/campaigns/create` → `POST /api/campaigns` → row in `campaigns` table
- Portal uses `backend_client.py` methods (not direct DB access)
- Session cookie carries JWT from `/api/auth/login`

### Error Propagation
- Backend 401 → Portal re-renders login page
- Backend 403 → Portal shows "Вход запрещён" / redirects
- Backend 423 → Portal shows "Учётная запись заблокирована"
- Backend 502/504 → Portal shows "Сервер временно недоступен"
- All error messages in business language (Russian), no tracebacks

---

## Test Coverage Summary

| Test File | Focus | Tests |
|-----------|-------|-------|
| backend/tests/test_auth_models.py | Auth models, password hashing, roles | ~15 |
| backend/tests/test_admin_portal_access_bootstrap.py | system_admin permissions | ~15 |
| backend/tests/test_rls.py | RLS scope enforcement | ~20 |
| backend/tests/test_rls_endpoint_enforcement.py | Per-endpoint RLS checks | ~25 |
| backend/tests/test_user_crud_api.py | User CRUD + role assignment | ~20 |
| apps/portal-web/tests/test_main.py | Portal pages + UI guarding | ~100+ |
| apps/portal-web/tests/test_portal_backend_live_integration.py | Live HTTP integration | ~10 |

**Total: ~200+ tests covering auth, RBAC, RLS, and contract.**

---

## Portal Backend Client

`apps/portal-web/backend_client.py` wraps all backend API calls:
- `backend_login(username, password)` → `POST /api/auth/login`
- `backend_me(token)` → `GET /api/auth/me`
- `backend_list_campaigns(token, ...)` → `GET /api/campaigns`
- `backend_create_campaign(token, ...)` → `POST /api/campaigns`
- (etc. for all domains)

All client methods return `{"ok": bool, "data": ..., "status": int}` pattern.
Portal never accesses DB directly — always through backend API.
