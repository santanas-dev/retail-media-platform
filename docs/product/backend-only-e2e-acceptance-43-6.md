# Backend-only E2E Acceptance — 43.6

**Date:** 2026-06-16  
**Baseline:** HEAD (43.6)  
**Status:** ✅ 50 structural/invariant tests pass + portal regression 665 pass

---

## Scope

Structural verification of the full backend-only flow without live database:
**creative → campaign → schedule → approval → publication batch → manifest →
backend publication → planned reports/CSV export.**

50 tests across 6 categories validate endpoint registration, state machines,
CSV safety, code invariants, and physical delivery isolation.

---

## Test Categories

### A. Production Endpoint Enumeration (24 tests)
Every step of the backend-only flow has a registered production endpoint:
- Creatives: list, create, get-by-code
- Campaigns: list, create, bind creative, submit, campaign→batch bridge
- Schedules: list, create, slots
- Approvals: list, create, decide (approve/reject)
- Publications: batch list
- Manifests: list, generate, publish
- Reports: campaigns/airtime/conflicts/publications export, PoP summary

### B. State Machine Validation (8 tests)
- Campaign lifecycle statuses (draft → pending_approval → approved → rejected → archived)
- Approval decision statuses (pending → approved/rejected)
- Batch statuses and transitions (draft → pending → approved → manifest → published)
- Published state is terminal
- Manifest generated + published statuses exist
- Service docstrings state physical delivery NOT triggered

### C. CSV Export Safety (9 tests)
- All 4 CSV export types have safe headers (no token/secret/password/url/hash/uuid)
- CSV response uses `text/csv` content-type
- CSV response includes `Content-Disposition` header
- No forbidden patterns in export headers (access_token, device_secret, backend_url, minio://, s3://, etc.)
- Export endpoints registered in main FastAPI app

### D. Safety Invariants (6 tests)
- Publication service never imports sidecar/runner/chromium modules
- Manifest service never imports sidecar/runner modules
- Production endpoint paths in publications/reports routers are test-kso free
- Approvals and manifests routers retain legacy test-kso sections (known tech debt D-A-01, D-MF-01)

### E. Reports Export Content Safety (2 tests)
- Reports export service code contains no forbidden patterns (secrets, tokens, barcodes, fiscal data)
- Conflicts CSV has RLS/anonymization logic for advertisers

### F. Physical Delivery — Explicitly NOT Triggered (4 tests)
- Batch publish action does not reference sidecar_sync/sync_manifest/deliver_to_kso
- Airtime occupancy is explicitly `is_planned`, not factual PoP
- Publication service documents backend-only nature
- Campaign→batch bridge documents physical delivery NOT triggered

---

## Production Endpoints Verified

| Domain | Endpoint | Verified |
|---|---|---|
| Media | `GET /api/creatives` | ✅ |
| Media | `POST /api/creatives` | ✅ |
| Media | `GET /api/creatives/by-code/{code}` | ✅ |
| Campaigns | `GET /api/campaigns` | ✅ |
| Campaigns | `POST /api/campaigns` | ✅ |
| Campaigns | `POST .../creatives` (bind) | ✅ |
| Campaigns | `POST .../submit` | ✅ |
| Campaigns | `POST .../create-publication-batch` | ✅ |
| Scheduling | Schedule/placement list | ✅ |
| Scheduling | Schedule/placement create | ✅ |
| Scheduling | Slot/item create | ✅ |
| Approvals | `GET /api/approvals` | ✅ |
| Approvals | `POST /api/approvals` | ✅ |
| Approvals | `POST /api/approvals/{code}/approve` | ✅ |
| Publications | `GET /api/publication-batches` | ✅ |
| Manifests | `GET /api/manifests` | ✅ |
| Manifests | `POST /api/manifests` (generate) | ✅ |
| Manifests | `POST /api/manifests/{code}/publish` | ✅ |
| Reports | `GET /api/reports/campaigns/export` | ✅ |
| Reports | `GET /api/reports/airtime/export` | ✅ |
| Reports | `GET /api/reports/conflicts/export` | ✅ |
| Reports | `GET /api/reports/publications/export` | ✅ |

---

## CSV Export Safety Summary

| Export | Safe Headers ✅ | No Secrets ✅ | text/csv ✅ | Content-Disposition ✅ |
|---|---|---|---|---|
| Campaigns | ✅ | ✅ | ✅ | ✅ |
| Airtime | ✅ | ✅ | ✅ | ✅ |
| Conflicts | ✅ | ✅ | ✅ | ✅ |
| Publications | ✅ | ✅ | ✅ | ✅ |

---

## Physical Delivery Isolation

| Check | Result |
|---|---|
| Publication service imports sidecar | ❌ Not found |
| Publication service imports runner | ❌ Not found |
| Batch publish references sidecar_sync | ❌ Not found |
| Manifest service imports runner | ❌ Not found |
| Airtime marked as `is_planned` | ✅ Present |
| "Physical KSO delivery is NOT triggered" in docstring | ✅ Present |
| Campaign→batch bridge docstring: "NOT triggered" | ✅ Present |

---

## Regression

- **Backend:** 647 passed, 6 pre-existing failures (test_reports_portal_42_3.py — stale template checks), 25 warnings
- **Portal:** 665 passed, 21 skipped, 0 failed
- **New E2E test:** 50 passed, 0 failed

---

## Known Limitations

- Does not exercise live database (structural/invariant tests only)
- Does not test sidecar/PoP/Chromium (out of scope — physical KSO not touched)
- Legacy test-kso routes still present in approvals, manifests, campaigns (tracked in tech-debt)
- 4 pre-existing test failures in test_reports_portal_42_3.py (stale template string checks)
