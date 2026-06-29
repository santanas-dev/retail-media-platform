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
| 45.8 Security Hardening: RLS + Audit | ⬜ PENDING | Medium | 2-3 sessions |
| 45.9 Portal UX Hardening | ⬜ PENDING | Low | 2 sessions |
| 46.0 Publication/Status Lifecycle | ⬜ PENDING | Medium | 2 sessions |
| 46.1 Compliance 152-ФЗ Readiness | ⬜ PENDING | Low | 1-2 sessions |
| 46.2 Pilot Readiness (Physical KSO) | ⬜ BLOCKED | High | TBD |

---

## Phase 45.8 — Security Hardening: RLS + Audit Trail

### Goal
Close RLS/advertiser-scope gaps and expand audit trail from 40% → 80%.

### Backend/API Tasks
- [ ] Add advertiser-scope check to campaign/creative routes (ad_manager sees own advertiser only)
- [ ] Add advertiser-scope check to schedule/publication routes
- [ ] Add audit calls for: campaign.create, campaign.approve/reject, creative.upload, schedule.create, publication.prepare, user.create, role.assign, login
- [ ] Add `login_audit_events` for login/logout tracking
- [ ] Standardize audit event schema: action, target_type, target_ref, actor_id, details

### Portal Tasks
- [ ] Verify advertiser dropdown filtered by scope in campaign_create
- [ ] Verify creative list filtered by advertiser scope

### Security Tasks
- [ ] RLS scope check on all 20 UUID-based routes
- [ ] Audit trail test: verify events written for each action

### Tests/Gates
- [ ] Unit tests for RLS scope enforcement (ad_manager can't see other advertiser's campaigns)
- [ ] Unit tests for audit event creation (≥15 action types covered)
- [ ] Regression: backend 770, portal 835

### Acceptance Criteria
- [ ] Ad_manager sees only own advertiser's campaigns/creatives
- [ ] Cross-advertiser access returns 403
- [ ] Audit events for all P1 actions (campaign, creative, schedule, publication)
- [ ] Login events tracked
- [ ] No regression

### What's NOT Included
- Row-level security at DB level (PostgreSQL RLS policies)
- Full SIEM integration
- Real-time audit streaming

### Blockers
- None

---

## Phase 45.9 — Portal UX Hardening

### Goal
Fix P1 UX issues: form labels, density, empty states.

### Backend/API Tasks
- None (backend already returns correct data)

### Portal Tasks
- [ ] Add `<label>` elements to schedule.html (8 inputs)
- [ ] Add `required` visual markers (CSS `::after { content: " *"; color: red; }`)
- [ ] Add cancel/back links to admin.html forms
- [ ] Reduce schedule.html columns from 12 → 8 (hide advanced fields)
- [ ] Group admin.html into tabs/sections (Users, Roles, RLS, Audit)
- [ ] Add "Create first X" CTA to inventory.html and stores.html empty states
- [ ] Replace emoji icons with SVG (📢, 📋, ✅, etc.)

### Security Tasks
- None

### Tests/Gates
- [ ] Visual regression: all pages render without broken layouts
- [ ] WCAG A compliance: all inputs have labels
- [ ] QA gates: no JS/CDN/localStorage, no raw JSON

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
