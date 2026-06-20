# Linux KSO systemd Service Contract

**Date:** 2026-06-20
**Version:** 1.0
**Status:** Contract (unit files NOT created in this step)
**Block:** 27.2 — Linux KSO systemd Service Contract

## 1. Overview

This document defines the future systemd service architecture for the KSO
(ServPlus Sherman-J 5.1) advertising system running alongside СуперМаг УКМ 4.

**Target hardware:** ServPlus Sherman-J 5.1
**OS:** Linux
**POS software:** СуперМаг УКМ 4 (right 25% of screen)
**Player:** Chromium kiosk-mode (left 75% of screen)
**Init system:** systemd
**Resolution:** 1920×1080 (Full HD)

> **Important:** This is a **contract document only**. No `.service` files are
> created in this step. Real unit files will be written in a future step (27.4)
> after all service requirements are validated against the actual
> ServPlus Sherman-J 5.1 environment.

## 2. Planned Services

| Service name | Component | Purpose |
|---|---|---|
| `verny-kso-state-adapter.service` | UKM 4 State Adapter | Writes `kso_state.json` — the single source of truth for KSO operational state |
| `verny-kso-sidecar.service` | KSO Sidecar Agent | Syncs manifest/media, sends heartbeats/PoP to backend (outbound only) |
| `verny-kso-player.service` | KSO Player (Chromium kiosk) | Reads local manifest/media/state, plays ads when safe |

### 2.1 Service Status

| Service | Status | Notes |
|---|---|---|
| `verny-kso-state-adapter.service` | **Future** — not yet implemented | Will poll UKM 4 or receive state events; writes `kso_state.json` atomically |
| `verny-kso-sidecar.service` | **Future** — not yet implemented | Core logic exists in `kso_sidecar_agent/`; CLI tested; unit file not created |
| `verny-kso-player.service` | **Future** — not yet implemented | Core logic exists in `kso_player/`; CLI tested; Chromium kiosk launch not written |

## 3. Startup Order

### 3.1 Recommended Boot Sequence

```
network-online.target                              ← prerequisite for sidecar
  │
  └─→ verny-kso-state-adapter.service              ← writes kso_state.json
       │
       └─→ verny-kso-sidecar.service               ← syncs manifest/media; needs network
            │
            └─→ verny-kso-player.service            ← needs manifest/media + state
```

### 3.2 systemd Dependency Graph

```
network-online.target
  ↓ (Wants + After)
verny-kso-state-adapter.service
  ↓ (Wants + After)
verny-kso-sidecar.service
  ↓ (Wants + After)
verny-kso-player.service
```

### 3.3 Rationale

| Ordering | Reason |
|---|---|
| network-online first | Sidecar needs HTTPS to sync manifest/media and send PoP/heartbeats |
| State adapter before sidecar | Sidecar may read `kso_state.json` for diagnostics/heartbeat; state should be available |
| Sidecar before player | Player needs cached manifest/media + state file to decide play/hold |
| Player CAN start without network | Player reads local files only; `Wants=` (not `Requires=`) for dependencies. If network is down, player holds but does not crash |

### 3.4 What Each Service Depends On

| Service | Requires | Wants | After |
|---|---|---|---|
| `verny-kso-state-adapter` | — | `network-online.target` | `local-fs.target` |
| `verny-kso-sidecar` | — | `network-online.target`, `verny-kso-state-adapter.service` | `local-fs.target` |
| `verny-kso-player` | — | `verny-kso-sidecar.service` | `local-fs.target`, `graphical.target` |

> `Wants=` (not `Requires=`) is intentional: player should NOT fail to start
> if sidecar or network is unavailable. It simply holds until manifest/media/state
> become ready.

## 4. Service Ownership — What Each Component Writes / Reads

### 4.1 Write/Read Matrix

| Component | Writes | Reads | Never Writes | Never Reads |
|---|---|---|---|---|
| **State Adapter** | `state/kso_state.json` (atomic) | — (polls UKM 4) | manifest, media, pop, config | player_events.jsonl, backend config |
| **Sidecar** | `manifest/`, `media/`, `pop/sent/`, `pop/quarantine/`, `pop/dry_run/`, `pop/failed/`, `config/runtime_config.json` | `manifest/`, `media/`, `pop/pending/`, `state/kso_state.json` (diagnostics), `config/` | `kso_state.json` (source of truth) | UKM 4 internals, payment/fiscal data |
| **Player** | `pop/pending/player_events.jsonl` (append-only, with lock) | `manifest/`, `media/`, `state/kso_state.json` | `kso_state.json` (source of truth), `pop/sent/`, `pop/quarantine/`, `pop/dry_run/`, `pop/failed/` | Backend, network, UKM 4 directly |

### 4.2 State Ownership (reiterated)

```
Writer (single source of truth):
  verny-kso-state-adapter.service → /var/lib/verny/kso/state/kso_state.json

Reader (primary consumer):
  verny-kso-player.service → reads kso_state.json to decide play/hold

Reader (diagnostics):
  verny-kso-sidecar.service → may include state in heartbeat/report
```

> **Critical rule:** Player MUST NOT write state. If player writes `kso_state.json`,
> it could falsify `idle` to itself and play ads during a transaction. State must
> come from an external source of truth (the UKM 4 state adapter).

## 5. User and Group

### 5.1 Base Model (simplicity, Block 27)

```
User:  verny-kso
Group: verny-kso
```

All three services run under the same `verny-kso` user. This keeps the initial
systemd configuration simple. The player's logical contract prohibits state writes
even though the user technically has filesystem permission to `state/`.

### 5.2 Future Split (security hardening, NOT implemented now)

```
verny-kso-state   — state adapter only (writes kso_state.json)
verny-kso-sidecar — sidecar only (outbound network, no UKM 4 access)
verny-kso-player  — player only (no state write, no network)
```

| User | Writable dirs | Network |
|---|---|---|
| `verny-kso-state` | `state/` | None (reads UKM 4 locally) |
| `verny-kso-sidecar` | `manifest/`, `media/`, `pop/sent/`, `pop/quarantine/`, `pop/dry_run/`, `pop/failed/`, `config/` | Outbound HTTPS only |
| `verny-kso-player` | `pop/pending/` | None |

**Risk:** With the base model, player *could* write to `state/` at the filesystem level.
**Mitigation:** Logical contract enforcement — player code MUST NOT write state. Future user separation will add filesystem-level enforcement.

## 6. systemd Hardening Proposal

### 6.1 Recommended Unit-Level Protections

> These are **proposals**. Actual values must be verified on ServPlus Sherman-J 5.1
> and may be relaxed if Chromium or UKM 4 integration requires broader access.

#### verny-kso-state-adapter.service

```ini
[Service]
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/verny/kso/state
ReadOnlyPaths=/opt/verny/kso /etc/verny/kso
RestrictAddressFamilies=AF_UNIX
RestrictRealtime=true
```

#### verny-kso-sidecar.service

```ini
[Service]
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/verny/kso /var/log/verny/kso/sidecar /run/verny/kso
ReadOnlyPaths=/opt/verny/kso /etc/verny/kso
RestrictAddressFamilies=AF_INET AF_INET6
RestrictRealtime=true
```

#### verny-kso-player.service

```ini
[Service]
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/verny/kso/pop/pending /var/log/verny/kso/player /run/verny/kso
ReadOnlyPaths=/opt/verny/kso /etc/verny/kso /var/lib/verny/kso/manifest /var/lib/verny/kso/media /var/lib/verny/kso/state
RestrictAddressFamilies=none
RestrictRealtime=true
```

### 6.2 Hardening Options Explained

| Option | Effect | Why |
|---|---|---|
| `NoNewPrivileges=true` | Blocks setuid, capabilities escalation | Defense-in-depth |
| `PrivateTmp=true` | Isolated `/tmp` per service | Prevents cross-service tmp leaks |
| `ProtectSystem=strict` | `/usr`, `/boot`, `/etc` mounted read-only | Cannot modify OS |
| `ProtectHome=true` | `/home`, `/root` invisible | No home directory access |
| `ReadWritePaths=...` | Whitelist for writable paths | Minimal surface |
| `ReadOnlyPaths=...` | Explicit read-only paths | Explicit intent |
| `Restart=always` | Always restart on exit | Crash resilience |
| `RestartSec=5s` | 5-second cooldown | Avoid tight crash loops |
| `RestrictAddressFamilies=...` | Network access control | Player = none, Sidecar = INET only, State adapter = UNIX only |

### 6.3 Restart Policy

| Service | Restart | RestartSec | Rate Limit |
|---|---|---|---|
| `verny-kso-state-adapter` | `always` | 5s | systemd default (5 restarts in 10s → failure) |
| `verny-kso-sidecar` | `always` | 5s | systemd default |
| `verny-kso-player` | `always` | 5s | systemd default |

**Restart behavior:**

```
Restart=always    → restart regardless of exit code (including exit 0)
RestartSec=5      → wait 5 seconds between attempts
StartLimitBurst=5 → 5 restarts in 10 seconds → service enters failed state
StartLimitIntervalSec=10
```

## 7. Restart and Fail-Safe Behavior

### 7.1 Crash Scenarios

| Failure | Effect | Mitigation |
|---|---|---|
| **Sidecar crash** | systemd restarts sidecar; player continues with cached manifest/media | Restart=always; pending events untouched |
| **Player crash** | systemd restarts player; UKM 4 unaffected (separate process) | Restart=always; UKM 4 on separate screen zone |
| **State adapter crash** | Player detects stale state (>30s) → hold | Staleness check in player; state adapter restarted by systemd |
| **Chromium crash** | Chromium exit → player service exits → systemd restarts | Restart=always |
| **Repeated crashes** | systemd rate-limit kicks in → service in failed state | Operator notified; UKM 4 continues unaffected |
| **Disk full** | No destructive cleanup; writes fail gracefully | Pending untouched; sidecar skips rotation; logs error |
| **Lock unavailable** | Skip operation (fail-safe) | Player skips PoP write; sidecar skips rotation; retry on next cycle |
| **Backend unavailable** | Pending retained; no rotation applied | Retry on next sidecar run-once cycle |
| **State file missing** | Player → hold (state = unknown) | Fail-closed |

### 7.2 systemd Restart During Runtime

```
systemctl restart verny-kso-player.service
  → Chromium exits gracefully (SIGTERM → SIGKILL after TimeoutStopSec)
  → Player event loop stops
  → systemd starts new instance
  → Player re-reads manifest/media/state from disk
  → Resumes play/hold decision
  → UKM 4 unaffected (separate process, separate screen zone)
```

### 7.3 systemd Boot-time Behavior

```
Boot sequence:
  1. local-fs.target            — /var/lib, /opt, /etc mounted
  2. network-online.target       — network ready (sidecar prerequisite)
  3. state adapter starts        — writes kso_state.json
  4. sidecar starts              — syncs manifest/media
  5. player starts               — reads local files, decides play/hold

If network is down at boot:
  → network-online.target may time out
  → sidecar starts but syncs fail (degraded mode)
  → player starts with cached manifest/media (hold if nothing cached)
```

## 8. Environment Files

### 8.1 Proposed Env Files

| File | Service | Content | Secrets? |
|---|---|---|---|
| `/etc/verny/kso/device.env` | State adapter, Sidecar | `DEVICE_CODE`, non-secret identity | ❌ No secrets |
| `/etc/verny/kso/sidecar.env` | Sidecar | Runtime flags, log level, non-secret config | ❌ No secrets |
| `/etc/verny/kso/player.env` | Player | Screen geometry, kiosk flags, non-secret config | ❌ No secrets |

### 8.2 Env File Rules

**Must NOT contain:**
- `token`, `jwt`, `password`, `secret`, `api_key`, `private_key`
- `device_secret`, `access_token`, `bearer`, `authorization`
- `backend_base_url` (in `player.env` context)
- `customer_id`, `phone`, `email`
- `receipt_data`, `card_number`, `pan`, `fiscal_data`
- `payment_card`, `receipt_number`

**May contain:**
- `DEVICE_CODE` (non-secret device identity)
- `LOG_LEVEL`, runtime flags
- `KSO_STATE_TIMEOUT`, `HEARTBEAT_INTERVAL`
- Screen geometry parameters
- `receipt` as a `safety_state` value (KSO state name)

**Production secret storage:**
- Secrets (device_secret, backend tokens) are NOT stored in `.env` files.
- Preferred: enrollment flow → runtime memory token (sidecar).
- Future: TPM / hardware-backed storage (Block 27.13).

## 9. Logging

### 9.1 Log Directories

| Service | Log path |
|---|---|
| State adapter | `/var/log/verny/kso/state-adapter/state_adapter.log`, `error.log` |
| Sidecar | `/var/log/verny/kso/sidecar/agent.log`, `error.log` |
| Player | `/var/log/verny/kso/player/player.log`, `error.log` |

### 9.2 Forbidden in Logs

The following MUST NEVER appear in any log file, journal output, or service stdout:

- `token`, `jwt`, `password`, `secret`, `api_key`, `private_key`
- `device_secret`, `access_token`, `authorization`, `bearer`
- `payment_card`, `receipt_data`, `card_number`, `pan`
- `customer_id`, `phone`, `email`, `receipt_number`, `fiscal_data`
- `backend_base_url` (in player context)
- `media_path`, `creatives/`
- Payload body (raw JSON of sent PoP events)
- Raw PoP JSON with `manifest_item_id`, `device_event_id`, `batch_id`, `campaign_id`, `creative_id`, `schedule_item_id`
- `sha256` (of media), `fingerprint` values
- `full_manifest`
- `media_bytes`
- `stacktrace` with sensitive data

### 9.3 Allowed in Logs

- `receipt` as a `safety_state` value (KSO operational state)
- `device_code` (non-secret identity)
- Aggregate counts (items synced, events sent, etc.)
- Safe status strings, error codes, diagnostic summaries
- `fingerprint` as a concept name in documentation or log level strings (NOT values)

### 9.4 Log Rotation

Managed by `logrotate` with configuration in `/etc/logrotate.d/verny-kso` (future step):

```
/var/log/verny/kso/**/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

## 10. Chromium Kiosk Note

### 10.1 Conceptual Description (no launch command in this step)

The player service will launch Chromium in kiosk mode:

```
Window:          1440 × 1080 (left zone)
Position:        (0, 0) — top-left corner
UKM 4 zone:      480 × 1080 (right zone, not controlled by player)
```

Chromium renders the player UI (HTML/JS) from `/opt/verny/kso/player/html/`.
The actual launch command and flags will be defined in a future step (27.5 —
Chromium kiosk launch script), after all security and kiosk-mode flags are
validated.

### 10.2 Key Principles

- Chromium kiosk runs as `verny-kso` user (NOT root).
- No network access required (player serves local HTML/JS, reads local media).
- UKM 4 screen zone is reserved and not touched by Chromium.
- Player does NOT interact with UKM 4 directly — only reads `kso_state.json`.

## 11. Security Boundaries Summary

```
┌─────────────────────────────────────────────────┐
│  ServPlus Sherman-J 5.1                         │
│                                                 │
│  ┌──────────────┐  ┌──────────┐  ┌───────────┐ │
│  │ State Adapter│  │ Sidecar  │  │  Player   │ │
│  │              │  │          │  │           │ │
│  │ writes state │  │ outbound │  │ no net    │ │
│  │              │  │ HTTPS    │  │ reads     │ │
│  │              │  │          │  │ local     │ │
│  └──────┬───────┘  └────┬─────┘  └─────┬─────┘ │
│         │               │              │       │
│         │ writes        │ reads        │ reads │
│         ▼               ▼              ▼       │
│  ┌──────────────────────────────────────────┐  │
│  │         /var/lib/verny/kso/               │  │
│  │  state/   manifest/   media/   pop/      │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────┐  ┌────────────────┐  │
│  │    UKM 4             │  │   Backend      │  │
│  │    (vendor-managed)  │  │   (remote)     │  │
│  │    right 25% screen  │  │   HTTPS only   │  │
│  └──────────────────────┘  └────────────────┘  │
│         ▲                             ▲         │
│         │ reads                       │ sends   │
│    State Adapter                 Sidecar        │
└─────────────────────────────────────────────────┘
```

## 12. Not In Scope (future steps)

This contract does NOT include:

| Step | What | When |
|---|---|---|
| 27.4 | Actual `.service` unit files | After all requirements validated |
| 27.5 | Chromium kiosk launch script | After security flags reviewed |
| 27.6 | Player runtime event loop | After kiosk launch defined |
| 27.7 | UKM 4 state adapter implementation | After UKM 4 API confirmed |
| 27.8 | Screen layout implementation | After kiosk window positioning |
| 27.9 | Watchdog service | After all services stable |
| 27.10 | Linux installer package | After all components defined |
| 27.13 | Production secret storage | After TPM/hardware evaluation |

## 13. Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-06-20 | Initial contract — 3 services, startup order, ownership matrix, hardening proposal, restart/fail-safe, env files, logging rules, Chromium kiosk note |
