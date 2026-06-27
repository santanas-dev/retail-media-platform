# One-KSO Pilot Runbook

> **Status:** 📋 Ready for approval  
> **Date:** 2026-06-16  
> **Baseline:** v0.12.0-product-workflow-backend-manifest (`296e13e`)  
> **Regression:** 5260 passed, 32 skipped, 0 failed  

---

## 1. Pilot Goal

Validate the full Retail Media Platform backend product workflow on a single physical
KSO device (test-dev-seed, 192.168.110.223) — from creative upload through manifest
generation — WITHOUT physical manifest delivery to the device.

**Success:** Backend-only workflow confirmed green; all approval gates passed;
manifest version N+1 generated correctly; no regressions introduced.

**Not a goal:** Live fleet rollout, production traffic, or KSO-side manifest delivery.

---

## 2. What Has Been Proven

| Capability | Evidence | Phase |
|---|---|---|
| Creative upload (server-side multipart) | Portal tests + live integration | 41.1 |
| Business campaign creation (orchestrated) | Portal tests + live integration | 41.2 |
| Campaign submit → approval request | Portal tests + live integration | 41.2.1 |
| Approval decision UX (maker-checker) | Portal tests + live integration | 41.3 |
| CampaignCreative is_active compat guard | Backend tests (no AttributeError) | 41.3.1 |
| Approved campaign → publication batch | Backend endpoint + portal button | 41.4 |
| Batch workflow (approve → generate → publish) | Backend tests + state machine | 41.4.1 |
| Manifest version N+1 generation | Backend generate_manifests() | 41.4.1 |
| RBAC/RLS/Audit enforcement | 42+ RLS endpoint tests, audit hardening | 40.1–40.2 |
| No JS/CDN/localStorage | Template source audits | All |
| No secrets in output/commits | Security audit | All |
| Full regression green | 6 suites, 5292 total | Every step |

---

## 3. What Has NOT Been Proven

| Gap | Reason | Blocking? |
|---|---|---|
| HW scanner E2E (barcode → campaign match) | No physical scanner hardware | 🔴 Pilot |
| Controlled long-run (1h+) | Not executed | 🔴 Pilot |
| Physical manifest delivery to KSO | Not approved | 🔴 Pilot |
| Sidecar sync with live manifest | Not executed | 🔴 Pilot |
| PoP upload from physical device | Not executed | 🔴 Pilot |
| Systemd autostart | Not configured | 🔴 Pilot |

---

## 4. Pilot Scope

**In scope:**
- One physical KSO device: `test-dev-seed` (192.168.110.223, 768×1024 portrait)
- Backend (192.168.110.77:8421), Portal (192.168.110.77:8422)
- Full product workflow: admin creates creative → ad manager creates campaign → approver approves → ad manager creates publication batch → approver approves batch → generate manifest → publish (backend only)
- Verification: manifest JSON contains campaign creative, hash valid, no forbidden keys

**Out of scope:**
- Fleet rollout (3+ KSO devices)
- Production traffic / real advertisers / budgets
- Physical manifest delivery to KSO
- Sidecar sync or runner launch
- PoP upload from physical device
- Systemd autostart
- Performance / scalability benchmarks

---

## 5. Roles

| Role | Persona | Permissions |
|---|---|---|
| System Admin | Full platform access | All |
| Ad Manager | Creates campaigns, creatives | campaigns.manage, creatives.manage, publications.manage |
| Approver | Approves campaigns and batches | campaigns.approve, publications.approve |
| Operator | Observes, publishes batches | publications.publish, publications.read |
| KSO Operator | Physical KSO access | SSH + display access (for future phases) |

---

## 6. Prerequisites

- [x] Backend running on 192.168.110.77:8421
- [x] Portal running on 192.168.110.77:8422
- [x] RBAC roles seeded: system_admin, ad_manager, approver, operator
- [x] Test creative uploaded (image/png)
- [x] Test KSO device registered: test-dev-seed, 768×1024, store-473
- [x] Full regression: 5260 passed, 32 skipped, 0 failed
- [ ] HW scanner E2E executed (BLOCKED — no hardware)
- [ ] Controlled 1h long-run executed (BLOCKED — needs approval)
- [ ] Physical KSO delivery approval token signed

---

## 7. Approval Tokens Required

All tokens must be explicitly approved before proceeding:

| Token | Grants | Status |
|---|---|---|
| `PHASE_SCANNER_E2E_APPROVED` | Run scanner E2E test on physical KSO | ⛔ Pending |
| `PHASE_LONG_RUN_APPROVED` | Run 1h+ controlled long-run | ⛔ Pending |
| `PHASE_PHYSICAL_KSO_ACCESS_APPROVED` | SSH access to KSO for operations | ⛔ Pending |
| `PHASE_MANIFEST_DELIVERY_APPROVED` | Deliver manifest to physical KSO | ⛔ Pending |
| `PHASE_SIDECAR_SYNC_APPROVED` | Run sidecar sync on KSO | ⛔ Pending |
| `PHASE_POP_UPLOAD_APPROVED` | Upload PoP events from KSO | ⛔ Pending |
| `PHASE_SYSTEMD_AUTOSTART_APPROVED` | Enable systemd autostart | ⛔ Pending |

*See `docs/pilot/physical-approval-tokens.md` for full details.*

---

## 8. Run Steps (when approved)

### Phase 1: Scanner E2E (requires PHASE_SCANNER_E2E_APPROVED)
1. Connect physical barcode scanner to KSO
2. Verify scanner input reaches UKM5 application
3. Scan barcode → verify campaign match in backend
4. Confirm no focus steal, no input capture by overlay
5. Document results with evidence

### Phase 2: Controlled 1h Long-Run (requires PHASE_LONG_RUN_APPROVED)
1. Start backend + portal (already running)
2. Start KSO player in controlled mode (1h timer, kill-switch active)
3. Monitor: CPU, memory, display, UKM5 focus
4. After 1h: stop player, verify no resource leaks
5. Document results with evidence

### Phase 3: Manifest Delivery (requires PHASE_MANIFEST_DELIVERY_APPROVED)
1. Generate manifest via batch workflow (already tested backend-only)
2. Deliver manifest to KSO via sidecar sync
3. Verify manifest on KSO filesystem (correct JSON, no secrets)
4. Verify media cache populated

### Phase 4: PoP Upload (requires PHASE_POP_UPLOAD_APPROVED)
1. Run player with manifest for ~60s
2. Wait for sidecar to classify and upload PoP event
3. Verify PoP event visible in backend /api/reports/pop
4. Verify all fields correct: campaign_code, creative_code, device_code

---

## 9. Stop Criteria

Stop immediately if any of:
1. UKM5 application loses focus or becomes unresponsive
2. Payment/checkout screen is obscured
3. CPU > 90% sustained for > 30s
4. Memory leak detected (> 10% growth over 30 min)
5. Barcode/check/payment/customer data appears in logs or PoP events
6. Kill-switch file is triggered
7. Any backend secret/token/URL appears in KSO filesystem or logs
8. Overlay window is visible on top of UKM5 payment screen

---

## 10. Rollback

For any stop condition:
1. Kill KSO player process: `pkill -f kso_player`
2. Remove manifest from KSO: `rm /home/ukm5/kso-agent/manifest/current.json`
3. Restart UKM5 application if needed
4. Verify UKM5 is functional and focused
5. Document rollback in evidence

**No permanent changes to UKM5, openbox, systemd, .profile, or xinitrc.**

---

## 11. Evidence Checklist

All evidence must be captured WITHOUT secrets, tokens, backend URLs, or PII.

- [ ] Scanner E2E: screenshot of UKM5 with scanner input, backend campaign match
- [ ] Long-run: CPU/memory graphs, uptime log, no-focus-loss confirmation
- [ ] Manifest delivery: manifest JSON on KSO (masked paths), no forbidden keys
- [ ] PoP upload: backend PoP report screenshot (event_code, campaign_code, creative_code)
- [ ] Rollback: confirm UKM5 functional after all phases
- [ ] Regression: full suite green after each phase

*Full checklist: `docs/pilot/evidence-checklist.md`*

---

## 12. Communication

- All phase approvals must be explicit — verbal + documented in this runbook
- Any stop event: document immediately in this runbook
- Post-pilot: update `docs/pilot/go-no-go-checklist.md` with verdict

---

## 13. Completion

Pilot is complete when:
1. All approved phases executed
2. All evidence captured
3. Full regression confirmed green
4. GO/NO-GO decision documented in `docs/pilot/go-no-go-checklist.md`
5. This runbook signed off with date and approver name
