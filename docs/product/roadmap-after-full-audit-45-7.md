# Roadmap After Full Audit — 45.7

**Date:** 2026-06-29  
**Based on:** Full System Audit v3.0 + Live Reconciliation 45.7  
**Current baseline:** v0.9.0-rc0-business-demo.6 (e17900e)  
**Current dev:** 07d5b02 (cleanup complete)

---

## Phase Status Overview

| Phase | Status | Risk | Est. Effort |
|---|---|---|---|
| 45.7 Audit Reconciliation | 🔵 IN PROGRESS | Low | 1 session |
| 45.8 Security Hardening: RLS + Audit | ✅ DONE | Medium | 2 sessions (45.8 + 45.8.1) |
| 45.8.1 Security Hardening Closure | ✅ DONE | Low | 1 session |
| 45.9 Portal UX Hardening | ✅ DONE | Low | 1 session |
| 46.0 Publication/Status Lifecycle | ⬜ PENDING | Medium | 2 sessions |
| 46.1 Compliance 152-ФЗ Readiness | ⬜ PENDING | Low | 1-2 sessions |
| 46.2 Pilot Readiness (Physical KSO) | ⬜ BLOCKED | High | TBD |

---

## Phase 45.8 — Security Hardening: RLS + Audit Trail ✅ DONE

### Outcome (45.8 + 45.8.1)
- **RLS/scope**: Confirmed 47/47 routes enforce `assert_object_in_advertiser_scope`. No gaps.
- **Audit trail**: Corrected from 14/20 (original miscount) → **20/20 (100%)**. 34 total audit actions + 1 negative audit.
- **Negative audit**: `approval.denied_self_approve` — maker-checker violation logged.
- **Portal**: Styled Russian 403 page replaces raw JSON on scope violations.
- **Tests**: 25 audit-specific tests + 804 backend / 803 portal regression.
- **Docs**: `audit-trail-matrix-45-8-1.md`, `security-hardening-closure-45-8-1.md`.

### Deferred to 46.1
- Login/logout in admin_audit_events (separate `login_audit_events` table already exists).
- Scope-violation audit middleware (404-based, needs 403/404 separation).
- Real-time audit streaming, SIEM integration.

### Acceptance Criteria
- [x] Ad_manager sees only own advertiser's campaigns/creatives
- [x] Cross-advertiser access returns 404 (privacy-preserving)
- [x] Audit events for all 20 P1 actions (campaign, creative, schedule, publication, identity)
- [ ] Login events tracked → separate `login_audit_events` table (46.1)
- [x] No regression

### What's NOT Included
- Row-level security at DB level (PostgreSQL RLS policies)
- Full SIEM integration
- Real-time audit streaming

### Blockers
- None

---

## Phase 45.9 — Portal UX Hardening ✅ DONE

### Outcome
- **Labels**: 8 added (schedule slot form: 6, approvals reject: 1, admin required markers: 5 fixed)
- **Cancel links**: 7 added (schedule create, approvals create, campaign_detail create-schedule, admin 4 forms)
- **Density**: Admin quick-nav + id anchors added
- **Empty states**: Inventory CTA buttons added
- **Tests**: 10 UX audit tests, all pass. Portal regression: 813/32.
- **Backend**: 0 files touched. RBAC/RLS/audit/maker-checker unchanged.
- **No**: JS/CDN/localStorage/raw JSON/technical language.

### Acceptance Criteria
- [ ] All form inputs have accessible labels
- [ ] Required fields visually marked
- [ ] Schedule page ≤8 columns
- [ ] Admin page uses tabbed layout
- [ ] Empty states have actionable CTAs
- [ ] No emoji in production UI

### What's NOT Included
- Full responsive redesign
- Dark mode toggle
- Custom component library

### Blockers
- None

---

## Phase 46.0 — Publication/Status Lifecycle Cleanup

### Goal
Fix status string mismatch, publication dead-end states, English error text.

### Backend/API Tasks
- [ ] Align status strings: backend `in_review` ↔ portal `pending_approval` → use single canonical name
- [ ] Add publication status transitions: approved → archived, cancelled → archived
- [ ] Translate 422 error messages to Russian
- [ ] Remove `pending_approval` from portal — use `in_review` everywhere

### Portal Tasks
- [ ] Update status display to use canonical backend names
- [ ] Add archive button to publication detail page
- [ ] Handle empty campaign_code display gracefully (C-63939f)

### Security Tasks
- None

### Tests/Gates
- [ ] Backend tests for publication status transitions
- [ ] Portal tests for status display consistency
- [ ] Regression: backend 770, portal 835

### Acceptance Criteria
- [ ] No `pending_approval` string in portal code (use `in_review`)
- [ ] Publication can transition: approved → archived, cancelled → archived
- [ ] 422 errors return Russian messages (when Accept-Language: ru)
- [ ] C-63939f displays correctly without raw campaign_code

### What's NOT Included
- Full state machine formalization
- Status history/audit per object

### Blockers
- Backend API change requires coordinated portal update

---

## Phase 46.1 — Compliance 152-ФЗ Readiness

### Goal
Address 152-ФЗ gaps: data localization, consent, deletion.

### Backend/API Tasks
- [ ] Document data storage location (confirm .ru hosting or document Russia-based storage)
- [ ] Add consent checkbox to login page ("Я согласен на обработку персональных данных")
- [ ] Add user data deletion endpoint (GDPR-style: anonymize PII, keep audit trail)
- [ ] Add data retention policy document

### Portal Tasks
- [ ] Consent checkbox on login page
- [ ] Privacy policy page (`/privacy`)
- [ ] Data deletion request form (admin-only)

### Security Tasks
- [ ] Verify TLS on all connections
- [ ] Document encryption at rest

### Tests/Gates
- [ ] Login requires consent acceptance
- [ ] Data deletion endpoint functional
- [ ] Audit trail preserved after deletion

### Acceptance Criteria
- [ ] Login page shows consent checkbox
- [ ] `/privacy` page exists
- [ ] Admin can initiate data deletion
- [ ] Documented data storage location

### What's NOT Included
- Full 152-ФЗ certification
- Roskomnadzor notification
- Data Protection Officer appointment

### Blockers
- Legal review required for consent text
- Hosting location decision (.ru vs current)

---

## Phase 46.2 — Pilot Readiness for Physical KSO

### Goal
Prepare for deployment to physical KSO devices when scanner hardware is available.

### Backend/API Tasks
- [ ] Verify device gateway endpoints (manifest, media, PoP)
- [ ] Test device authentication (JWT token flow)
- [ ] Verify heartbeat monitoring

### Portal Tasks
- [ ] Device dashboard: show real device status (not demo data)
- [ ] Device health alerts: configure thresholds

### Security Tasks
- [ ] mTLS between KSO and backend
- [ ] Device secret rotation

### Tests/Gates
- [ ] E2E: KSO → manifest fetch → media download → PoP upload
- [ ] Scanner integration test
- [ ] Long-run stability (24h+)

### Acceptance Criteria
- [ ] Physical KSO boots and fetches manifest
- [ ] Media plays on KSO display
- [ ] PoP events arrive in backend
- [ ] Device health dashboard shows real status

### What's NOT Included
- Fleet management at scale
- OTA updates
- Multi-site rollout

### Blockers
- 🔴 Physical KSO hardware not available
- 🔴 Scanner hardware not available
- 🔴 Network configuration for KSO subnet

---

## Timeline Estimate

| Phase | Sessions | Dependencies |
|---|---|---|
| 45.7 (current) | 1 | — |
| 45.8 Security | 2-3 | None |
| 45.9 UX | 2 | None |
| 46.0 Lifecycle | 2 | 45.8 (status strings) |
| 46.1 Compliance | 1-2 | None |
| 46.2 Pilot | TBD | 🔴 Hardware |

**Total estimated: 8-10 sessions for phases 45.8–46.1**
