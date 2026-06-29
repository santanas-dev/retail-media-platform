# Roadmap After Full Audit — 45.7 (DEPRECATED)

> **⚠️ ЗАМЕНЁН документом `tz-v2-5-realignment-roadmap-46-1.md`**
> **Причина:** Gap analysis 46.1 показал значительные отклонения от ТЗ v2.5.
> **Дата замены:** 2026-06-29
>
> Старая roadmap (45.7→46.2) закрыта. Новая roadmap начинается с фазы A (Re-Alignment)
> и следует архитектуре ТЗ v2.5: channel-agnostic core → Channel Orchestrator →
> Adapter Layer → Device Gateway → KSO как первый канал.

## Итоги выполненных фаз (сохранены как control-plane slice)

| Phase | Status |
|---|---|
| 45.8 Security Hardening | ✅ DONE — 47/47 RLS, 20/20 audit |
| 45.9 Portal UX Hardening | ✅ DONE — русские labels, accessibility |
| 46.0 Status Lifecycle Cleanup | ✅ DONE — единая карта статусов |
| 46.1 Compliance 152-ФЗ | ✅ DONE — PII inventory, privacy notice |
| 46.1 TZ v2.5 Gap Analysis | ✅ DONE — **см. новый roadmap** |

## Остановленные фазы

| Phase | Причина |
|---|---|
| 46.2 Pilot Readiness | Преждевременно — нет Device Gateway, Channel Orchestrator |
| Дальнейший UX hardening | Достаточно для v1; приоритет — архитектура |
| Дальнейший compliance | Достаточно для v1 |

## Новый roadmap

**См.** `docs/product/tz-v2-5-realignment-roadmap-46-1.md`

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

## Phase 46.1 — Compliance 152-ФЗ Readiness ✅ DONE

### Goal
Подготовить портал, backend и БД к базовым требованиям по персональным данным и внутреннему ИБ-контролю.

### Completed
- [x] PII inventory — все поля в БД идентифицированы и классифицированы
- [x] Login privacy notice — уведомление на странице входа (auth_base.html)
- [x] Public compliance pages: `/compliance`, `/compliance/retention`
- [x] Deactivation procedure — задокументирована; backend уже поддерживает (is_archived, is_active)
- [x] Data retention policy — сроки хранения по всем категориям данных
- [x] Login/logout audit mapping — документирован
- [x] Security headers/cookie review — httpOnly, SameSite, signed подтверждены
- [x] UI PII visibility — email не показывается в UI; IP/UA хешированы
- [x] Compliance tests: 19 pytest-тестов

### Key Decisions
- Consent checkbox rejected: нет утверждённой юристами формы. Использовано «уведомление» вместо «согласие».
- Data deletion endpoint отложен: backend уже поддерживает archive (soft delete) с audit trail. Физическое удаление требует approval.
- Security headers middleware отложен до production (HTTPS).

### Acceptance Criteria
- [x] Login page shows privacy notice
- [x] `/compliance` page exists (public)
- [x] `/compliance/retention` page exists (public)
- [x] Deactivation procedure documented
- [x] PII inventory complete
- [x] No raw IP/UA stored (hashed)
- [x] Cookie security documented (httpOnly, SameSite, signed)

### What's NOT Included
- Full 152-ФЗ certification (requires lawyers)
- Roskomnadzor notification
- Consent checkbox (requires legal-approved text)
- Physical data deletion (soft delete only in v1)
- Security headers middleware (dev mode, no HTTPS)

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
