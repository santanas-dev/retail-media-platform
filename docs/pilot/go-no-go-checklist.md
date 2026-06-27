# Pilot GO/NO-GO Checklist

> **Date:** 2026-06-16  
> **Baseline:** v0.12.0-product-workflow-backend-manifest (`296e13e`)  
> **Current Verdict:** **NO-GO** 🔴  

---

## Product Readiness

| # | Criterion | Status | Evidence |
|---|---|---|---|
| P1 | Creative upload UX works (server-side multipart) | ✅ GO | Portal tests, live integration |
| P2 | Business campaign creation UX works (orchestrated) | ✅ GO | Portal tests, live integration |
| P3 | Campaign submit → approval request creates ApprovalRequest | ✅ GO | Backend tests, maker-checker enforced |
| P4 | Approval decision UX (approve/reject per-row) | ✅ GO | Portal tests, campaign summary |
| P5 | Approved campaign → publication batch | ✅ GO | Backend endpoint, portal button |
| P6 | Batch approval workflow (draft → approved) | ✅ GO | State machine, backend tests |
| P7 | Manifest generation version N+1 | ✅ GO | Backend generate_manifests() |
| P8 | Manifest contains campaign creative/material | ✅ GO | Backend tests |
| P9 | Previous manifest not mutated on regenerate | ✅ GO | Old draft → cancelled |
| P10 | No JS/CDN/localStorage on all portal pages | ✅ GO | Source audits |

**Product verdict:** ✅ **GO** — full backend workflow functional.

---

## Backend Readiness

| # | Criterion | Status | Evidence |
|---|---|---|---|
| B1 | Backend health check (GET /health) | ✅ GO | Live check |
| B2 | All 551 backend tests green | ✅ GO | Regression |
| B3 | Device gateway auth (JWT + bcrypt) | ✅ GO | 39.1.1 hardening |
| B4 | PoP ingest requires valid device JWT | ✅ GO | Backend tests |
| B5 | Seed data idempotent (POST /api/test-kso/seed) | ✅ GO | 38.5 |
| B6 | Backend URL/secrets not in responses | ✅ GO | Safe projection audit |

**Backend verdict:** ✅ **GO**

---

## Portal Readiness

| # | Criterion | Status | Evidence |
|---|---|---|---|
| W1 | All 498 portal tests green (20 skipped) | ✅ GO | Regression |
| W2 | Admin access works (all pages) | ✅ GO | Portal-backend live integration |
| W3 | PAGE_PERMISSION_MAP aligned with backend | ✅ GO | 40.2.1 fix |
| W4 | No backend URLs/secrets in HTML | ✅ GO | Security audit |
| W5 | All forms server-side POST, no JS | ✅ GO | Template audits |

**Portal verdict:** ✅ **GO**

---

## Security / RBAC / RLS / Audit Readiness

| # | Criterion | Status | Evidence |
|---|---|---|---|
| S1 | RBAC: 49 permissions, 8 roles enforced | ✅ GO | Seed integrity tests |
| S2 | RLS: advertiser scope on all endpoints | ✅ GO | 42 RLS endpoint tests |
| S3 | Maker-checker: cannot approve own request | ✅ GO | Backend enforcement |
| S4 | Audit trail: all business actions logged | ✅ GO | 18 audit hardening tests |
| S5 | Forbidden field stripping in audit payloads | ✅ GO | Payload redaction tests |
| S6 | Constant-time device secret comparison | ✅ GO | 40.1 auth hardening |

**Security verdict:** ✅ **GO**

---

## Device Readiness

| # | Criterion | Status | Evidence |
|---|---|---|---|
| D1 | Test KSO device registered (test-dev-seed) | ✅ GO | Seed data |
| D2 | Display surface: 768×1024 portrait | ✅ GO | 38.13.1 fix |
| D3 | Device dashboard shows device status | ✅ GO | Portal page |
| D4 | Readiness endpoint returns device status | ✅ GO | Backend endpoint |
| D5 | Sidecar config template exists (agent_config.json.example) | ✅ GO | 38.9 |
| D6 | Kill-switch mechanism working | ✅ GO | 38.0.8 local kill-switch |

**Device verdict (backend):** ✅ **GO**  
**Device verdict (physical):** ⛔ **BLOCKED** — see below

---

## Scanner E2E

| # | Criterion | Status | Evidence |
|---|---|---|---|
| SC1 | Physical barcode scanner available | 🔴 NO-GO | No hardware |
| SC2 | Scanner E2E test plan documented | ✅ GO | `docs/audit/hw-scanner-e2e-validation-plan.md` |
| SC3 | Scanner test executed | 🔴 NO-GO | Not executed |
| SC4 | Barcode → campaign match verified | 🔴 NO-GO | Not executed |
| SC5 | No focus steal by overlay during scan | 🔴 NO-GO | Not verified |

**Scanner verdict:** 🔴 **NO-GO** — blocking

---

## Controlled Long-Run

| # | Criterion | Status | Evidence |
|---|---|---|---|
| LR1 | Long-run plan documented (1h/8h/48h) | ✅ GO | `docs/audit/pilot-readiness-gates-plan.md` |
| LR2 | 1h controlled run executed | 🔴 NO-GO | Not executed |
| LR3 | CPU/memory stable within thresholds | 🔴 NO-GO | Not measured |
| LR4 | UKM5 focus preserved throughout | 🔴 NO-GO | Not verified |
| LR5 | No resource leaks after run | 🔴 NO-GO | Not verified |

**Long-run verdict:** 🔴 **NO-GO** — blocking

---

## Physical Delivery Approval

| # | Criterion | Status | Evidence |
|---|---|---|---|
| PD1 | Physical delivery gate documented | ✅ GO | Approval tokens defined |
| PD2 | Manifest JSON verified safe (no secrets) | ✅ GO | Forbidden key validation |
| PD3 | Sidecar config ready (no placeholders) | 🔴 NO-GO | Not validated on live KSO |
| PD4 | Physical delivery approved | 🔴 NO-GO | Not approved |

**Physical delivery verdict:** 🔴 **NO-GO** — blocking

---

## Rollback Readiness

| # | Criterion | Status | Evidence |
|---|---|---|---|
| R1 | Rollback procedure documented | ✅ GO | Runbook section 10 |
| R2 | Kill-switch tested (local file flag) | ✅ GO | 38.0.8 |
| R3 | UKM5 restoration procedure known | ✅ GO | Runbook |
| R4 | No permanent changes to KSO config | ✅ GO | Runbook constraints |

**Rollback verdict:** ✅ **GO**

---

## Final GO/NO-GO Decision

### Current: **NO-GO** 🔴

### Blockers (must be resolved)

| # | Blocker | Required For |
|---|---|---|
| 1 | HW scanner E2E not executed | Physical pilot Phase 1 |
| 2 | Controlled long-run not executed | Physical pilot Phase 2 |
| 3 | Physical KSO delivery not approved | Physical pilot Phase 3 |

### What CAN proceed without blockers

- ✅ All backend/product development
- ✅ Portal UX improvements
- ✅ Additional tests and hardening
- ✅ Documentation updates
- ✅ Regression maintenance

### What CANNOT proceed

- 🔴 Physical KSO access for operations
- 🔴 Manifest delivery to KSO
- 🔴 Sidecar sync on KSO
- 🔴 PoP upload from KSO
- 🔴 Systemd autostart configuration

---

## Sign-Off

| Role | Name | Date | Decision |
|---|---|---|---|
| Product Owner | ________ | ________ | GO / NO-GO |
| Security Lead | ________ | ________ | GO / NO-GO |
| KSO Operator | ________ | ________ | GO / NO-GO |
