# KSO Player Shell Snapshot Delivery Contract

**Date:** 2026-06-20
**Version:** 1.0
**Status:** Contract (not yet implemented)
**Block:** 27.13 — Snapshot Delivery Contract
**Applies to:** KSO Player HTML Shell (`player_shell/`)

## 1. Overview

This document defines the delivery contract for runtime snapshots into the
KSO Player HTML shell. The shell itself (`index.html`, `player.js`, `bootstrap.js`,
`styles.css`) is production code that lives in an immutable `/opt` directory.
Runtime snapshots change frequently and must be delivered without modifying
the immutable shell source.

**Key constraint:** `/opt/verny/kso/player/` is **read-only at runtime**.
We cannot write bootstrap snapshots into `/opt`.

## 2. The Problem

| Constraint | Reasoning |
|---|---|
| `/opt` is read-only at runtime | Immutable application code; updated only by installer/package |
| Shell cannot use `fetch`/`XMLHttpRequest`/`WebSocket` | CSP `connect-src 'none'` — no network access |
| Shell cannot call backend | Fully local kiosk; no backend URL, no auth, no token |
| Snapshot must change every tick | Runtime loop selects different items frequently |
| Writing to `/opt` at runtime is unsafe | Risk of corrupting installed shell; permission issues |

## 3. Recommended Model

### 3.1 Immutable Shell Source

```
/opt/verny/kso/player/player_shell/
├── index.html              ← Immutable
├── styles.css              ← Immutable
├── player.js               ← Immutable
└── bootstrap.js            ← Immutable
```

`/opt` shell is installed once (package/installer) and never modified at runtime.

### 3.2 Runtime Shell Working Copy

```
/var/lib/verny/kso/runtime/player_shell/
├── index.html              ← Copied from /opt at player startup
├── styles.css              ← Copied from /opt at player startup
├── player.js               ← Copied from /opt at player startup
├── bootstrap.js            ← Copied from /opt at player startup
└── bootstrap_snapshot.js   ← Atomically written at each runtime tick
```

`/var/lib` is mutable application data — the correct place for runtime state.

### 3.3 Future Runtime Flow

1. **Installer** places shell files in `/opt/verny/kso/player/player_shell/`
2. **Player runtime** at startup copies shell from `/opt` to `/var/lib/verny/kso/runtime/player_shell/`
3. **Player runtime** atomically writes `bootstrap_snapshot.js` in the runtime copy
4. **Chromium** opens the runtime copy: `file:///var/lib/verny/kso/runtime/player_shell/index.html`

### 3.4 Why Not `/opt`

- `/opt` is for immutable application code — writing snapshots there violates the OS contract
- Risk of corrupting the installed shell (partial write, disk full, permission error)
- Shell updates must go through the installer/package manager, not runtime
- Runtime state belongs in `/var/lib` per Linux FHS

### 3.5 Why Not `fetch` JSON

- CSP `connect-src 'none'` blocks all network access
- No backend URL, no local HTTP server, no network stack
- Smaller attack surface: no network listeners, no CORS, no HTTP parsing
- Simpler: snapshot is delivered as a local script file, no deserialization risk

## 4. Snapshot Script Contract

### 4.1 File Location

```
/var/lib/verny/kso/runtime/player_shell/bootstrap_snapshot.js
```

### 4.2 Content Format

**Hold:**
```js
window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT = {
  schemaVersion: 1,
  mode: "hold",
  method: "setHold",
  payload: { reason: "hold" }
};
```

**Render (image):**
```js
window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT = {
  schemaVersion: 1,
  mode: "render",
  method: "setRenderPlan",
  payload: {
    mediaType: "image",
    durationBucket: "short",
    mediaRef: "media/current/slot-000"
  }
};
```

**Render (video):**
```js
window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT = {
  schemaVersion: 1,
  mode: "render",
  method: "setRenderPlan",
  payload: {
    mediaType: "video",
    durationBucket: "medium",
    mediaRef: "media/current/slot-001"
  }
};
```

### 4.3 Forbidden in Snapshot Script

The snapshot script MUST NOT contain:

| Category | Forbidden values |
|---|---|
| Paths | Absolute paths, relative paths with `..`, real filenames, `/opt`, `/var` |
| IDs | `manifest_item_id`, `campaign_id`, `creative_id`, `schedule_item_id`, `device_event_id`, `batch_id` |
| Hashes | `sha256`, `fingerprint` |
| Secrets | `token`, `jwt`, `password`, `secret`, `api_key`, `private_key`, `bearer`, `access_token`, `device_secret` |
| Backend | `backend_base_url`, `127.0.0.1`, `backend` |
| Customer | `customer_id`, `phone`, `email`, `payment_card`, `card_number`, `pan`, `receipt_number`, `fiscal_data`, `receipt_data` |
| Raw data | `full_manifest`, `media_bytes`, raw JSON, `stacktrace` |
| Environment | `local_path`, `file_path`, `media_path`, `creatives/`, `device_code` |
| Process | `boot_id`, `pid` |

**Note:** `mediaRef` is the ONLY safe reference to media content. It is a local alias
(`media/current/slot-NNN`), NOT an absolute path, filename, ID, or hash.

## 5. Index Include Order (Future)

When the runtime copy system is implemented, `index.html` in the runtime copy
should load scripts in this order:

```html
<script src="player.js"></script>            <!-- 1. Create window.KsoPlayerShell -->
<script src="bootstrap_snapshot.js"></script>  <!-- 2. Set window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT -->
<script src="bootstrap.js"></script>           <!-- 3. Apply snapshot or hold -->
```

**Rationale:**
- `player.js` runs first — creates the `KsoPlayerShell` API
- `bootstrap_snapshot.js` runs second — sets `window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT`
- `bootstrap.js` runs third — reads the snapshot and calls `applySnapshot()` or `setHold()`

**IMPORTANT:** The current immutable `index.html` does NOT include `bootstrap_snapshot.js`.
The include order change will happen in the runtime copy at startup. Do NOT modify
the immutable `/opt` `index.html` to include a non-existent file.

## 6. Atomic Write Contract

### 6.1 Write Protocol

```
1. Write content to bootstrap_snapshot.js.tmp
2. flush() + fsync() the .tmp file
3. Atomic rename: bootstrap_snapshot.js.tmp → bootstrap_snapshot.js
4. fsync() the parent directory
5. Best-effort: on error, do NOT delete the existing snapshot
```

### 6.2 Safety Guarantees

| Guarantee | How |
|---|---|
| No partial reads | Atomic rename — the reader sees either old file or new file, never partial |
| No corruption on crash | `.tmp` may be orphaned; next write cycle cleans it up |
| Old snapshot preserved on error | Error → existing `bootstrap_snapshot.js` untouched |
| Hold on missing file | `bootstrap.js` sees `undefined` snapshot → `setHold("hold")` |

### 6.3 Error Behavior

- **Write failure:** Old snapshot remains; shell may show stale ad or hold (fail-safe)
- **Rename failure:** `.tmp` orphaned; old snapshot remains; next tick retries
- **fsync failure:** Best-effort; atomic rename provides partial protection
- **Disk full:** Write fails; old snapshot preserved; shell holds

## 7. MediaRef Contract

| Property | Value |
|---|---|
| Format | `media/current/slot-{order:03d}` |
| Example | `media/current/slot-000` |
| Is NOT | Absolute path, real filename, campaign/creative ID, sha256 hash, backend URL |
| Validation | `^[a-z0-9/_-]+$` + no `..`, `~`, `\`, `://`, `file:`, `http:`, `https:`, `%2e`, `%2f` |

## 8. Failure Modes

| Failure | Behavior |
|---|---|
| `bootstrap_snapshot.js` missing | `bootstrap.js` → `setHold("hold")` — neutral hold screen |
| Snapshot invalid JSON/structure | `applySnapshot()` internal validation → `setHold("hold")` |
| Partial snapshot write | Atomic rename prevents visibility of partial writes |
| Runtime shell copy missing | Player service should detect and hold/retry (future implementation) |
| `mediaRef` invalid | `applySnapshot` whitelist reject → `setHold("hold")` |
| Media file missing | Browser may show broken image; future runtime must handle via readiness checks |
| Chromium crash | Future systemd auto-restart (`Restart=always`) |
| State stale (>30s) | Runtime decision → hold; snapshot reflects hold |
| Non-idle KSO state | Runtime gate → hold; snapshot is hold |

## 9. Security Summary

- **No network:** CSP `connect-src 'none'`, no `fetch`/`XHR`/`WebSocket`
- **No backend:** No backend URL, no auth, no tokens, no secrets
- **No file reads:** Shell does not read files (browser resolves `src` from `mediaRef`)
- **No injection vectors:** `document.createElement` only, no `innerHTML`/`eval`
- **No absolute paths in snapshot:** Only whitelist-validated `mediaRef` aliases
- **No IDs/hashes in snapshot:** Snapshot contains only `schemaVersion`, `mode`, `method`, `payload`
- **Atomic writes:** No partial-snapshot exposure

## 10. Go / No-Go

**Decision:** ✅ **Conditional Yes — Ready for snapshot writer implementation**

**Conditions:**
1. Writer MUST target `/var/lib/verny/kso/runtime/player_shell/` (runtime copy), never `/opt`
2. Writer MUST use atomic write protocol (`.tmp` → `rename` → `fsync`)
3. Snapshot MUST contain only safe fields (no paths, IDs, hashes, secrets)
4. Index include order MUST be fixed before runtime demo:
   `player.js` → `bootstrap_snapshot.js` → `bootstrap.js`
5. Runtime shell copier MUST run before first snapshot write at player startup
6. Media files MUST be available at `{runtime_copy}/media/current/` (symlink or copy)

**Risks:**
- Runtime copy synchronization not yet implemented (future player launcher step)
- Media file path resolution in Chromium from local `file://` needs validation
- Systemd integration not yet implemented (restart on crash)

---

## Appendix A: Separation from Sidecar

This contract covers the **KSO Player shell only**. The KSO Sidecar Agent
lives in `/opt/verny/kso/sidecar/` and runs as a separate systemd service.
The sidecar does NOT write snapshots — the player's own runtime loop
(built on `shell_snapshot.py` + `media_reference.py`) will write them.

## Appendix B: Related Documents

- `linux_kso_runtime_filesystem_contract.md` — Filesystem layout for all KSO components
- `linux_kso_systemd_service_contract.md` — systemd service definitions
- `pop_local_writer_design.md` — PoP writer contract (separate concern)
- `full_audit_before_kso_runtime.md` — Audit before runtime block
