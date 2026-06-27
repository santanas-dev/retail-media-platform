# Physical Approval Tokens

> **Date:** 2026-06-16  
> **Status:** All tokens **PENDING** ⛔  
> **Principle:** No physical KSO action without explicit per-phase approval token.

---

## Token Lifecycle

1. **Pending** — token not yet approved
2. **Approved** — explicit sign-off received, dated and named
3. **Revoked** — previously approved, now withdrawn (e.g., blocker found)
4. **Executed** — phase completed, evidence captured

Once a token is approved, it stays approved until execution or explicit revocation.

---

## PHASE_SCANNER_E2E_APPROVED

| Field | Value |
|---|---|
| **What it allows** | Connect physical barcode scanner to KSO; run scanner E2E test (Phase S1–S4 per validation plan) |
| **What it does NOT allow** | Long-run, manifest delivery, PoP upload, systemd changes |
| **Who approves** | Product Owner + KSO Operator |
| **Rollback** | Disconnect scanner; verify UKM5 functional |
| **Stop criteria** | Any focus loss, input capture by overlay, sensitive data in logs |
| **Status** | ⛔ Pending |

---

## PHASE_LONG_RUN_APPROVED

| Field | Value |
|---|---|
| **What it allows** | Run controlled long-run on KSO (1h minimum); start player with kill-switch active; monitor CPU/memory/display |
| **What it does NOT allow** | Scanner test, manifest delivery, PoP upload, systemd changes |
| **Who approves** | Product Owner + KSO Operator + Security Lead |
| **Rollback** | Kill player process; remove manifest; restart UKM5 |
| **Stop criteria** | CPU > 90% sustained 30s, memory leak > 10%/30min, UKM5 focus loss, payment screen obscured |
| **Status** | ⛔ Pending |

---

## PHASE_PHYSICAL_KSO_ACCESS_APPROVED

| Field | Value |
|---|---|
| **What it allows** | SSH access to KSO (192.168.110.223) for pilot operations: config application, file inspection, process management |
| **What it does NOT allow** | Modifying UKM5, openbox, Chromium, systemd, .profile, xinitrc, or index.html |
| **Who approves** | KSO Operator + Security Lead |
| **Rollback** | Close SSH session; verify no permanent changes |
| **Stop criteria** | Any modification to production KSO config outside pilot scope |
| **Status** | ⛔ Pending |

---

## PHASE_MANIFEST_DELIVERY_APPROVED

| Field | Value |
|---|---|
| **What it allows** | Deliver generated manifest JSON to KSO filesystem (`/home/ukm5/kso-agent/manifest/`); run sidecar manifest sync |
| **What it does NOT allow** | Start player, upload PoP, systemd autostart, modify scanner/barcode flow |
| **Who approves** | Product Owner + Security Lead |
| **Rollback** | Delete manifest from KSO; verify no stale media cache |
| **Stop criteria** | Manifest contains forbidden keys (secrets, tokens, URLs); media sync fails |
| **Status** | ⛔ Pending |

---

## PHASE_SIDECAR_SYNC_APPROVED

| Field | Value |
|---|---|
| **What it allows** | Run sidecar agent sync-manifest + sync-media on KSO; validate manifest + media cache locally |
| **What it does NOT allow** | Start player/Chromium/X11, upload PoP, systemd autostart |
| **Who approves** | Product Owner + KSO Operator |
| **Rollback** | Stop sidecar; clear manifest and media cache |
| **Stop criteria** | Sync fails with network error; manifest invalid; forbidden content in manifest |
| **Status** | ⛔ Pending |

---

## PHASE_POP_UPLOAD_APPROVED

| Field | Value |
|---|---|
| **What it allows** | Start player with manifest; allow sidecar to classify PoP events and upload to backend |
| **What it does NOT allow** | Systemd autostart, fleet rollout, production traffic |
| **Who approves** | Product Owner + Security Lead |
| **Rollback** | Kill player; stop sidecar; verify no stale PoP events |
| **Stop criteria** | PoP event contains sensitive data (barcode, payment, customer); upload fails repeatedly |
| **Status** | ⛔ Pending |

---

## PHASE_SYSTEMD_AUTOSTART_APPROVED

| Field | Value |
|---|---|
| **What it allows** | Configure systemd service for KSO player + sidecar autostart on boot |
| **What it does NOT allow** | Unattended fleet rollout; disabling manual kill-switch |
| **Who approves** | KSO Operator + Security Lead + Product Owner |
| **Rollback** | Disable systemd service; remove unit file |
| **Stop criteria** | Autostart interferes with UKM5 boot sequence; kill-switch not reachable |
| **Status** | ⛔ Pending |

---

## Approval Log

| Date | Token | Approved By | Decision | Notes |
|---|---|---|---|---|
| — | — | — | — | No tokens approved yet |
