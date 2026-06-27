# Pilot Evidence Checklist

> **Date:** 2026-06-16  
> **Baseline:** v0.12.0-product-workflow-backend-manifest  
> **All evidence must be captured WITHOUT secrets, tokens, backend URLs, or PII.**

---

## 1. Backend-Only Evidence (captured, no physical KSO needed)

| # | Evidence Item | Source | Status |
|---|---|---|---|
| E1 | Full regression: 5260 passed, 32 skipped, 0 failed | Test suites | ✅ Captured |
| E2 | Portal-backend live integration green | `RUN_PORTAL_BACKEND_LIVE_INTEGRATION=1` | ✅ Captured |
| E3 | Admin accesses all portal pages (200 OK) | Portal tests | ✅ Captured |
| E4 | Creative upload: multipart POST → 201, creative visible in list | Portal tests + live | ✅ Captured |
| E5 | Campaign creation: orchestrated 4-API-call chain | Backend tests | ✅ Captured |
| E6 | Campaign submit → ApprovalRequest created (pending_approval) | Backend tests | ✅ Captured |
| E7 | Campaign approval: pending_approval → approved (maker-checker) | Backend tests | ✅ Captured |
| E8 | Publication batch creation from approved campaign (draft) | Backend tests | ✅ Captured |
| E9 | Batch request-approval → pending_approval | Backend tests | ✅ Captured |
| E10 | Batch approve → approved | Backend tests | ✅ Captured |
| E11 | Manifest generation: approved → manifest_generated | Backend tests | ✅ Captured |
| E12 | Manifest version N+1: JSON valid, hash correct, no forbidden keys | Backend tests | ✅ Captured |
| E13 | Manifest contains campaign creative code | Backend tests | ✅ Captured |
| E14 | Previous manifest preserved (old draft → cancelled) | Backend tests | ✅ Captured |
| E15 | Backend publish: manifest_generated → published | Backend tests | ✅ Captured |
| E16 | No physical KSO delivery triggered | Code audit | ✅ Captured |
| E17 | No secrets/tokens/backend URLs in HTML | Security audit | ✅ Captured |
| E18 | No JS/CDN/localStorage on portal pages | Template audit | ✅ Captured |
| E19 | RBAC enforced: wrong role → 403 | RLS endpoint tests | ✅ Captured |
| E20 | Maker-checker: cannot approve own request | Backend tests | ✅ Captured |
| E21 | Audit trail: all business actions logged | Audit hardening tests | ✅ Captured |

---

## 2. Physical KSO Evidence (requires approval tokens)

| # | Evidence Item | Required Token | Status |
|---|---|---|---|
| P1 | Scanner E2E: UKM5 screenshot with scanner input → backend campaign match | `PHASE_SCANNER_E2E_APPROVED` | ⛔ Pending |
| P2 | Scanner E2E: confirm no focus steal, no input capture | `PHASE_SCANNER_E2E_APPROVED` | ⛔ Pending |
| P3 | Controlled long-run: CPU/memory graph (1h) | `PHASE_LONG_RUN_APPROVED` | ⛔ Pending |
| P4 | Controlled long-run: UKM5 focus preserved throughout | `PHASE_LONG_RUN_APPROVED` | ⛔ Pending |
| P5 | Controlled long-run: no resource leaks post-run | `PHASE_LONG_RUN_APPROVED` | ⛔ Pending |
| P6 | Manifest delivery: manifest JSON on KSO (masked paths) | `PHASE_MANIFEST_DELIVERY_APPROVED` | ⛔ Pending |
| P7 | Manifest delivery: no forbidden keys (recursive check) | `PHASE_MANIFEST_DELIVERY_APPROVED` | ⛔ Pending |
| P8 | Sidecar sync: manifest + media cache on KSO | `PHASE_SIDECAR_SYNC_APPROVED` | ⛔ Pending |
| P9 | PoP upload: event visible in backend /api/reports/pop | `PHASE_POP_UPLOAD_APPROVED` | ⛔ Pending |
| P10 | PoP upload: fields correct (campaign_code, creative_code, device_code) | `PHASE_POP_UPLOAD_APPROVED` | ⛔ Pending |
| P11 | PoP upload: no barcode/payment/customer data | `PHASE_POP_UPLOAD_APPROVED` | ⛔ Pending |
| P12 | Rollback: UKM5 functional after all phases | All | ⛔ Pending |

---

## 3. Evidence Format

All evidence MUST be:
- Screenshot (PNG) or log excerpt (TXT) — **NOT committed to git**
- Masked: `****` for backend URLs, device secrets, tokens
- No barcodes, payment data, customer PII, or fiscal data
- Stored in secure location, not in repository

---

## 4. Evidence Sign-Off

| Phase | Evidence Count | Reviewer | Date | Status |
|---|---|---|---|---|
| Backend-only | 21 items | ________ | ________ | ✅ / ⛔ |
| Scanner E2E | 2 items | ________ | ________ | Pending |
| Long-run | 3 items | ________ | ________ | Pending |
| Manifest delivery | 2 items | ________ | ________ | Pending |
| Sidecar sync | 1 item | ________ | ________ | Pending |
| PoP upload | 3 items | ________ | ________ | Pending |
| Rollback | 1 item | ________ | ________ | Pending |
