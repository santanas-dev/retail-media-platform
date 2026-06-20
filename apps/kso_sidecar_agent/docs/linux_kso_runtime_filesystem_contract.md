# Linux KSO Runtime Filesystem Contract

**Date:** 2026-06-20
**Version:** 1.0
**Status:** Contract (not yet implemented)
**Block:** 27.1 — Linux KSO Runtime

## 1. Overview

This document defines the production Linux filesystem layout, ownership, permissions,
and operational contract for the KSO (ServPlus Sherman-J 5.1) advertising player and
sidecar agent running alongside СуперМаг УКМ 4.

**Target hardware:** ServPlus Sherman-J 5.1
**OS:** Linux
**POS software:** СуперМаг УКМ 4 (right 25% of screen)
**Player:** Chromium kiosk-mode (left 75% of screen)
**Init system:** systemd
**Resolution:** 1920×1080 (Full HD)

## 2. Base Paths

| Path | Purpose | Lifecycle |
|---|---|---|
| `/opt/verny/kso/` | Application binaries (immutable) | Updated by installer only |
| `/etc/verny/kso/` | Configuration files | Updated by admin/installer |
| `/var/lib/verny/kso/` | Application data (mutable) | Written by player and sidecar at runtime |
| `/var/log/verny/kso/` | Application logs | Written by player and sidecar; rotated by logrotate |
| `/run/verny/kso/` | Runtime state (tmpfs, cleared on reboot) | Created at service start; cleared on reboot |

## 3. Full Directory Tree

```
/opt/verny/kso/                    # Immutable application binaries
├── sidecar/                       # KSO Sidecar Agent
│   ├── bin/                       # Entry-point scripts / compiled binaries
│   └── lib/                       # Python packages / vendored deps
└── player/                        # KSO Player
    ├── bin/                       # Entry-point scripts
    ├── lib/                       # Python packages
    └── html/                      # Player UI (HTML/JS for Chromium kiosk)

/etc/verny/kso/                    # Configuration (read-only at runtime)
├── sidecar.env                    # Sidecar environment (non-secret)
├── player.env                     # Player environment (non-secret)
└── device.env                     # Device identity (non-secret: device_code, NOT secret)

/var/lib/verny/kso/                # Mutable application data
├── manifest/                      # Current advertising manifest
│   └── current_manifest.json
├── media/                         # Cached media files
│   ├── current/                   # Ready-to-play media
│   └── staging/                   # In-progress downloads
├── pop/                           # Proof-of-Play pipeline
│   ├── pending/                   # Player writes events here
│   │   ├── player_events.jsonl    # Append-only JSONL
│   │   └── player_events.lock     # Shared player↔sidecar lock
│   ├── sent/                      # Backend-confirmed PoP events (archived)
│   ├── quarantine/                # Unsafe/schema-violation events
│   ├── dry_run/                   # Draft/diagnostic events (NOT PoP)
│   └── failed/                    # Retry-exhausted events
├── state/                         # KSO operational state
│   ├── kso_state.json             # Current UKM 4 state (written by player state adapter)
│   └── agent_status.json          # Sidecar agent status
├── config/                        # Runtime config cache
│   └── runtime_config.json        # Cached backend runtime config
└── tmp/                           # Temporary files (cleanup-tolerant)

/var/log/verny/kso/                # Logs
├── sidecar/                       # Sidecar logs
│   ├── agent.log
│   └── error.log
└── player/                        # Player logs
    ├── player.log
    └── error.log

/run/verny/kso/                    # tmpfs — cleared on reboot
├── locks/                         # Runtime lock files (alternative to data dir locks)
└── runtime/                       # PID files, sockets, etc.
```

## 4. User and Group

### 4.1 Proposed Identity

```
User:  verny-kso
Group: verny-kso
```

### 4.2 Principles

| Principle | Rationale |
|---|---|
| **No root at runtime** | Player and sidecar run as `verny-kso` user — minimal privilege |
| **Root only for installer/systemd** | Root privileges needed only for initial directory creation, package install, and systemd unit enablement |
| **Player has no backend secrets** | Player is read-only network: reads local manifest/media/state, writes local PoP pending. No backend URL, no token, no secret |
| **Sidecar has outbound-only network** | Sidecar syncs from backend, sends PoP/heartbeats. Runtime token only in memory |
| **Shared lock between player and sidecar** | Both use `pop/pending/player_events.lock` via `O_CREAT \| O_EXCL` |

### 4.3 Ownership Matrix

| Path | Owner | Group | Mode | Notes |
|---|---|---|---|---|
| `/opt/verny/kso` | root | root | 0755 | Immutable — installer writes |
| `/opt/verny/kso/player` | root | root | 0755 | Read-only for verny-kso |
| `/opt/verny/kso/sidecar` | root | root | 0755 | Read-only for verny-kso |
| `/etc/verny/kso` | root | verny-kso | 0750 | Admin writes, sidecar reads |
| `/etc/verny/kso/*.env` | root | verny-kso | 0640 | No secrets in env files! |
| `/var/lib/verny/kso` | verny-kso | verny-kso | 0750 | Runtime data |
| `/var/lib/verny/kso/manifest` | verny-kso | verny-kso | 0750 | |
| `/var/lib/verny/kso/media` | verny-kso | verny-kso | 0750 | |
| `/var/lib/verny/kso/pop` | verny-kso | verny-kso | 0750 | |
| `/var/lib/verny/kso/pop/pending` | verny-kso | verny-kso | 0750 | **Shared** player↔sidecar |
| `/var/lib/verny/kso/state` | verny-kso | verny-kso | 0750 | Player writes, sidecar reads |
| `/var/lib/verny/kso/tmp` | verny-kso | verny-kso | 0750 | Cleanup-tolerant |
| `/var/log/verny/kso` | verny-kso | verny-kso | 0750 | |
| `/run/verny/kso` | verny-kso | verny-kso | 0750 | tmpfs |

## 5. Player / Sidecar Separation

### 5.1 Player (Chromium kiosk)

| Responsibility | Restriction |
|---|---|
| Reads: `manifest/`, `media/`, `state/` | No network access to backend |
| Writes: `pop/pending/player_events.jsonl` | Append-only, with lock |
| Displays ads via Chromium kiosk | 1440×1080 left zone |
| Reads KSO screen state from UKM 4 (via state adapter) | UKM 4 integration is future work |
| Shows ads ONLY when state = `idle` | Fail-closed: any other state → hold/stop |
| Does NOT store: token, secret, backend URL, customer data | Read-only player |
| Does NOT read: `sent/`, `quarantine/`, `dry_run/`, `failed/` | Sidecar-managed dirs |

### 5.2 Sidecar Agent

| Responsibility | Restriction |
|---|---|
| Outbound HTTPS to backend only | No inbound listening ports |
| Syncs: manifest, media, runtime config | |
| Sends: heartbeats, PoP events, media cache reports | |
| Reads: `pop/pending/player_events.jsonl` | With lock |
| Writes: `pop/sent/`, `pop/quarantine/`, `pop/dry_run/`, `pop/failed/` | Atomic writes |
| Stores runtime token **only in memory** | Never on disk |
| Does NOT read: customer payment/receipt/card/fiscal data | |
| Does NOT access UKM 4 directly | Reads state from `state/kso_state.json` (written by player) |

## 6. State Contract

### 6.1 State File

```
/var/lib/verny/kso/state/kso_state.json
```

Written by player's KSO state adapter (future). Read by sidecar's player readiness check.

### 6.2 Allowed States

| State | Meaning | Play Ads? | Player behavior |
|---|---|---|---|
| `idle` | KSO not in use | **Yes** | Play ads in Chromium kiosk |
| `transaction` | Cashier processing sale | No | Hold/stop |
| `payment` | Customer payment in progress | No | Hold/stop |
| `receipt` | Printing receipt | No | Hold/stop |
| `service` | KSO service menu open | No | Hold/stop |
| `error` | KSO error state | No | Hold/stop |
| `maintenance` | Maintenance mode | No | Hold/stop |
| `offline` | Network disconnected | No | Hold/stop |
| `unknown` | State cannot be determined | No | Hold/stop (fail-safe) |

### 6.3 State JSON Format (proposal)

```json
{
  "schema_version": 1,
  "state": "idle",
  "updated_at": "2026-06-20T12:00:00+03:00",
  "source": "uksm4_adapter"
}
```

### 6.4 Safety Rule

> **Ads play ONLY at `idle`. All other states → hold/stop.**
>
> This includes `unknown` — if the state adapter cannot determine the KSO state,
> advertising MUST be held. False negative (not playing ads when KSO is idle) is
> acceptable. False positive (playing ads during transaction) is NOT acceptable.

## 7. Screen Layout Contract

### 7.1 Physical Layout

```
┌──────────────────────────────────────┬──────────┐
│                                      │          │
│          Advertising Zone            │ UKM 4    │
│          (Chromium Kiosk)            │ Zone     │
│                                      │          │
│          1440 × 1080                 │ 480×1080 │
│                                      │          │
└──────────────────────────────────────┴──────────┘
               1920 × 1080 Full HD
```

### 7.2 Chromium Kiosk Parameters (proposal)

```
--kiosk
--window-position=0,0
--window-size=1440,1080
--disable-infobars
--disable-session-crashed-bubble
--no-first-run
--disable-pinch
--overscroll-history-navigation=0
```

### 7.3 UKM 4 Zone

Right 480×1080 pixels reserved for СуперМаг УКМ 4 software. The player MUST NOT render into this zone. UKM 4 is managed by the KSO vendor software — player only reads state from it.

## 8. systemd Context (proposal — unit files NOT created here)

### 8.1 Planned Services

```
verny-kso-sidecar.service   — KSO Sidecar Agent
verny-kso-player.service    — KSO Player (Chromium kiosk)
```

### 8.2 Startup Order

```
network-online.target
  → verny-kso-sidecar.service   (requires network)
    → verny-kso-player.service  (requires sidecar readiness for manifest/media)
```

### 8.3 Dependencies

| Service | Requires | After |
|---|---|---|
| `verny-kso-sidecar` | `network-online.target` | `local-fs.target` |
| `verny-kso-player` | `verny-kso-sidecar.service` | `graphical.target` |

### 8.4 Restart Policy (proposal)

```
Restart=on-failure
RestartSec=5s
```

If Chromium crashes → systemd restarts player. UKM 4 is unaffected (separate process, separate screen zone).

## 9. Security Requirements

### 9.1 Forbidden in Logs, Config, State, Env Files

The following MUST NEVER appear in any file under `/var/log/`, `/etc/`, `/var/lib/state/`,
or any runtime output:

- `token`, `jwt`, `password`, `secret`, `api_key`, `private_key`
- `payment_card`, `receipt_data`, `card_number`, `pan`
- `customer_id`, `phone`, `email`, `receipt_number`, `fiscal_data`
- `authorization`, `bearer`, `device_secret`, `access_token`
- `backend_base_url` (in player context)
- `media_path`, `creatives/`
- Payload body (raw JSON of sent PoP events)
- Raw PoP JSON with `manifest_item_id`, `device_event_id`, `batch_id`, `campaign_id`, `creative_id`, `schedule_item_id`
- `sha256` (of media), `fingerprint` values
- `full_manifest`
- `media_bytes`
- `stacktrace` with sensitive data

### 9.2 Allowed

- `receipt` as a `safety_state` value (KSO state)
- `device_code` in `device.env` (non-secret config)
- `fingerprint` as a concept name in documentation (NOT values)

### 9.3 Network Isolation

- Sidecar: outbound HTTPS only (no inbound ports)
- Player: no network access (reads local files only)
- UKM 4: vendor-managed, not controlled by this system

### 9.4 Secret Storage

- Production secret storage (TPM, hardware-backed) — **future work (Block 27.13)**
- Dev-only secret store exists in `apps/kso_sidecar_agent/kso_sidecar_agent/secret_store.py`
- Secrets MUST NOT be stored in `.env` files, config files, or any world-readable path

## 10. Failure Modes

| Failure | Behavior |
|---|---|
| No manifest | Player → hold (no ads to play) |
| No media files | Player → hold |
| No state file | Player → hold (state = unknown) |
| State = unknown | Player → hold (fail-closed) |
| Lock unavailable (player) | Skip write; player continues without PoP recording |
| Lock unavailable (sidecar pickup) | Skip operation; retry on next cycle |
| Disk full | Pending untouched; sidecar skips rotation; logs error |
| Backend send failed | Pending untouched; rotation not applied; retry on next cycle |
| 409 duplicate | Pending untouched; rotation not applied |
| Fingerprint mismatch | Changed line retained in pending; not moved to sent |
| Chromium crash | systemd restarts player; UKM 4 unaffected (separate process) |
| Sidecar crash | systemd restarts sidecar; player continues with cached manifest/media |
| systemd restart (both) | tmpfs `/run/` cleared; data in `/var/lib/` preserved; stale lock possible (see R02 in audit) |

## 11. Not In Scope (Block 27.2+)

This contract does NOT include (will be separate documents/steps):

- Actual systemd unit files (27.4)
- Chromium kiosk launch script (27.5)
- Player runtime event loop (27.6)
- UKM 4 state adapter (27.7)
- Screen layout implementation (27.8)
- Watchdog (27.9)
- Linux installer package (27.10)
- Production secret storage (27.13)

## 12. Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-06-20 | Initial contract — filesystem layout, ownership, player/sidecar separation, state contract, screen layout, security requirements |
