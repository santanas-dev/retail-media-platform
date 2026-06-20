# Linux KSO Stale Lock Cleanup — Mini-Design

**Date:** 2026-06-20
**Version:** 1.0
**Status:** Design only — no implementation in this step
**Block:** 27.3 — Linux KSO Stale Lock Cleanup
**Audit ref:** R02 (Stale lock — High severity)

## 1. Overview

### 1.1 Problem Statement

The PoP lock file `player_events.lock` is created atomically via `O_CREAT | O_EXCL`
and released via `os.unlink()` by the lock owner. If the owning process crashes
(SIGKILL, power loss, systemd forced restart, OOM kill) between `acquire` and
`release`, the lock file persists indefinitely. Since the lock is non-blocking
(fail-silent on acquisition failure), both player and sidecar will skip their
operations forever until the stale lock is removed.

### 1.2 Scope

| In scope | Out of scope |
|---|---|
| Design a safe stale-lock detection and cleanup policy | Implementation code |
| Define v1 marker behavior and limitations | systemd unit files |
| Propose v2 marker format for future implementation | Chromium kiosk |
| Define atomic quarantine cleanup pattern | UKM 4 state adapter |
| Risk analysis and Go/No-Go recommendation | Deleting any lock file now |

### 1.3 Target Environment

| Parameter | Value |
|---|---|
| Hardware | ServPlus Sherman-J 5.1 |
| OS | Linux |
| Filesystem | ext4 (default for `/var/lib`) |
| Lock path | `/var/lib/verny/kso/pop/pending/player_events.lock` |
| Lock users | KSO Player (write), KSO Sidecar Agent (rotation/scan) |
| Init system | systemd |

## 2. Current Lock Behavior (v1)

### 2.1 Lock Mechanism

```
Acquire:  os.open(path, O_CREAT | O_EXCL | O_WRONLY)  → atomic create-or-fail
Marker:   write("locked\n")                            → minimal marker
Release:  os.unlink(path)                              → delete lock file
```

**Both player and sidecar read/write the SAME lock file** in
`pop/pending/player_events.lock`.

### 2.2 Marker Content (v1)

```
locked
```

The v1 marker is a single string `"locked\n"` — **no PID, no timestamp, no
component identifier, no boot ID.** This is intentional for the initial
implementation (minimal surface, no secrets, no paths).

### 2.3 Lock Acquisition by Component

| Component | Operation | Expected Lock Duration | Lock Failure Behavior |
|---|---|---|---|
| KSO Player | `pop-write` | < 1 second (append + flush + fsync) | Skip write, return `lock_unavailable` |
| KSO Sidecar | `pop-rotation-plan` | < 5 seconds (read + classify + aggregate) | Skip operation |
| KSO Sidecar | `pop-rotation-apply` | < 30 seconds (materialize + atomic writes) | Skip operation |
| KSO Sidecar | `pop-scoped-send` (package build) | < 5 seconds (snapshot + classify + payload) | Skip operation |

### 2.4 Release Paths

| Scenario | Lock Released? |
|---|---|
| Normal write/rotation completes | ✅ Yes — `finally` block calls `_release_lock()` |
| Write/fsync fails (disk full) | ✅ Yes — `finally` block always runs |
| Python exception during operation | ✅ Yes — `finally` block always runs |
| Process receives SIGTERM (graceful) | ✅ Yes — `finally` block runs during cleanup |
| Process receives SIGKILL | ❌ **No** — kernel kills immediately, no Python cleanup |
| Power loss | ❌ **No** — machine stops, no code runs |
| OOM killer | ❌ **No** — kernel kills immediately |
| systemd `SIGKILL` after `TimeoutStopSec` | ❌ **No** — same as SIGKILL |
| systemd restart (both services) | ❌ **Possible** — if previous instance crashed |

## 3. Stale Lock Policy

### 3.1 v1 Lock Marker Policy

```
Marker: "locked\n" (no metadata)

Rule: AUTOMATIC CLEANUP IS FORBIDDEN for v1 locks.

Allowed actions:
  ✅ Detect stale lock (stat → age > threshold)
  ✅ Log safe aggregate (stale_detected: true, age_seconds: N)
  ✅ Report via diagnostic heartbeat (sidecar)
  ✅ Operator/manual recovery (separate documented procedure)

Forbidden actions:
  ❌ Automatic deletion based on age alone
  ❌ Automatic deletion based on any v1 heuristic
  ❌ Direct os.unlink() without full stale verification
  ❌ Any destructive action on lock file
  ❌ Any modification of pending data during cleanup
```

**Why:** Without PID, component, or boot_id in the marker, it is impossible to
reliably distinguish a genuinely stale lock from an actively held lock owned by
a slow operation, a different component, or a process restarted after PID reuse.

### 3.2 Future v2 Lock Marker (proposal — NOT implemented in this step)

```json
{
  "schema_version": 2,
  "component": "player",
  "operation": "pop_write",
  "created_at_utc": "2026-06-20T10:00:00Z",
  "pid": 1234,
  "boot_id_hash": "sha256_internal_only"
}
```

#### v2 Marker Fields

| Field | Type | Required | Safe to log? | Notes |
|---|---|---|---|---|
| `schema_version` | int | ✅ Yes | ✅ Yes | Must be 2 |
| `component` | string | ✅ Yes | ✅ Yes | `player` or `sidecar` |
| `operation` | string | ✅ Yes | ✅ Yes | `pop_write`, `rotation_apply`, `rotation_plan`, `send_package` |
| `created_at_utc` | ISO8601 string | ✅ Yes | ✅ Yes | UTC timestamp — no timezone ambiguity |
| `pid` | int | ✅ Yes | ❌ **Never log** | Process ID — internal only, never in output/report/log |
| `boot_id_hash` | string | Optional | ❌ **Never log** | SHA-256 of `/proc/sys/kernel/random/boot_id` — internal only, never exposed |

#### Forbidden in v2 Marker

- `hostname` — identifies the machine in logs
- `username` — identifies the service user
- `paths` — absolute paths are sensitive
- `token`, `secret`, `jwt`, `password` — never in lock files
- `backend_base_url` — never in local files
- `device_code`, `device_id` — device identity
- `payload`, `json_data` — no data payloads in lock files
- `stacktrace` — never in lock files
- `manifest_item_id`, `fingerprint`, `sha256` — PoP-identifying data
- `media_bytes`, `media_path`, `creatives/` — media data
- `customer_id`, `email`, `phone`, `receipt_number`, `fiscal_data`, `card_number`, `pan` — customer/PII data

#### V2 `boot_id_hash` Design Decision

`boot_id_hash` is proposed as **optional** for the reasons below:

| Pro | Con |
|---|---|
| Detects stale locks after system reboot (reliable signal) | Requires reading `/proc` — Linux-specific |
| PID reuse within same boot is the main false-positive risk; boot_id_hash eliminates it | Internal only — must never be logged or exposed in safe output |
| Simple: SHA-256 of known kernel interface (no secrets) | Adds dependency on `/proc` being mounted (always true on systemd Linux) |

**Recommendation:** Implement `boot_id_hash` as optional. If `/proc/sys/kernel/random/boot_id`
is not readable, treat as "boot_id unknown" and apply stricter PID-verification-only rules.
Never log `boot_id_hash` value — use only for internal comparison (current vs. marker).

## 4. Safe Cleanup Conditions

### 4.1 For v2 Locks Only

Automatic cleanup may be permitted ONLY when ALL conditions are true:

| # | Condition | How verified |
|---|---|---|
| 1 | Lock age > configured threshold (default: 10 min) | `stat()` → `mtime` |
| 2 | Marker JSON is valid and `schema_version == 2` | `json.loads()` |
| 3 | `component` field is `player` or `sidecar` | String match |
| 4 | `operation` field is a known operation | String match |
| 5 | Process with `pid` does NOT exist | `os.kill(pid, 0)` → `ProcessLookupError` |
| 6 | OR: Process with `pid` exists but `boot_id` has changed | Compare current vs. marker `boot_id_hash` |
| 7 | Cleanup itself holds NO lock (idempotent) | Atomic rename, no acquisition before rename |

### 4.2 For v1 Locks — DETECT ONLY

| # | Condition | Action |
|---|---|---|
| 1 | Lock age > configured threshold | Log `stale_detected: true, age_seconds: N, marker_version: 1` |
| 2 | Lock age > 30 min (emergency threshold) | Log `stale_critical: true, age_seconds: N` — escalate to operator |
| 3 | Any age | **Never delete** — detection only |

### 4.3 Expected Lock Duration vs. Stale Threshold

| Operation | Expected Duration | Stale Threshold | Safety Margin |
|---|---|---|---|
| `pop_write` (player) | < 1 sec | 10 min | 600× |
| `rotation_plan` (sidecar) | < 5 sec | 10 min | 120× |
| `send_package` (sidecar) | < 5 sec | 10 min | 120× |
| `rotation_apply` (sidecar) | < 30 sec | 10 min | 20× |

**Proposed thresholds** (to be validated on ServPlus Sherman-J 5.1):

| Threshold | Value | Use |
|---|---|---|
| `LOCK_STALE_SECONDS` | 600 (10 min) | Warn — log `stale_detected` |
| `LOCK_STALE_CRITICAL_SECONDS` | 1800 (30 min) | Alert — escalate to operator |
| `LOCK_STALE_CLEANUP_SECONDS` | 600 (10 min) | Auto-cleanup (v2 only) |

## 5. Atomic Quarantine Cleanup Pattern

**When permitted (v2 marker only, all conditions met):**

```
Step 1:  stat(lock_path)                                  → read mtime, size
Step 2:  open(lock_path, O_RDONLY)                        → read marker JSON
Step 3:  json.loads(marker_bytes)                         → parse marker
Step 4:  validate_marker_v2(marker)                       → check schema, component, operation
Step 5:  verify_pid_dead_or_boot_changed(marker)          → os.kill(pid, 0), compare boot_id_hash
Step 6:  os.rename(lock_path, lock_path + ".stale.<ISO8601>")  → ATOMIC RENAME (same filesystem)
Step 7:  if rename successful → cleanup_complete
Step 8:  if rename failed (race) → another process handled it → report "cleanup_race"
```

**Key properties:**

| Property | Guarantee |
|---|---|
| `rename()` is atomic on same filesystem (ext4) | ✅ No intermediate state |
| Stale artifact is never `unlink()`ed directly | ✅ Always quarantined first |
| If rename fails — another process beat us | ✅ Idempotent — no double-cleanup |
| Pending data (`player_events.jsonl`) is never touched | ✅ Read-only during cleanup |
| No `unlink()` before rename | ✅ Cannot accidentally delete active lock |
| Stale artifacts deletable later by logrotate | ✅ Quarantine → eventual cleanup |

**Forbidden actions during cleanup:**

- Direct `os.unlink(lock_path)` without rename first
- Reading, writing, or modifying `player_events.jsonl`
- Creating files in `sent/`, `quarantine/`, `dry_run/`, `failed/`
- Creating a new lock before the old one is quarantined
- Exposing `pid`, `boot_id_hash`, or absolute paths in output

## 6. systemd Interaction

### 6.1 Service Lifecycle

| Event | Lock Behavior | Cleanup Action |
|---|---|---|
| `systemctl start` | No stale lock check on startup | Future step: `ExecStartPre` could run detect-only check |
| `systemctl stop` (graceful SIGTERM) | Lock released in `finally` | No stale lock left |
| `systemctl restart` (SIGTERM → new start) | Old lock released; new instance acquires | No stale lock unless SIGKILL forced |
| `systemctl kill` (SIGKILL) | ⚠️ Lock leaked | Stale lock detect-only on next sidecar cycle |
| `systemctl daemon-reload` | No effect on lock | N/A |
| System reboot (power loss) | ⚠️ Lock leaked | Stale lock detect-only after boot |
| systemd rate-limit (crash loop) | ⚠️ Locks may leak each crash | Detect-only — do NOT auto-cleanup until stable |

### 6.2 Cleanup Timing

| When | Who | What |
|---|---|---|
| Sidecar `run-once` preflight | Sidecar | Stale lock detect-only check before cycle |
| Player `pop-write` | Player | Lock unavailable → skip, **never initiate cleanup** |
| systemd `ExecStartPre` | Future step | Detect-only stale check (v1) or cleanup check (v2) |
| systemd `ExecStopPost` | Future step | Force-release own lock if held (pid check) |
| Operator intervention | Manual | Documented `verny-kso-lock-cleanup` CLI tool (future) |

### 6.3 Player Lock Unavailability

When player cannot acquire lock:

```
write_pop_event() → _acquire_lock() returns False
  → PopWriteResult(status=skipped, reason=lock_unavailable)
  → Player continues event loop WITHOUT PoP recording
  → No retry, no backoff, no cleanup attempt
  → Next event-dry-run → next pop-write → retry lock acquisition
```

**Critical:** Player MUST NOT attempt to clean up a stale lock. Player has no
PID/boot_id context. If player deletes the lock while sidecar holds it (slow
rotation), it violates mutual exclusion.

## 7. Safe Result / Logging Contract

### 7.1 Future Cleanup Result (proposal — v2 only)

```python
@dataclass
class StaleLockCleanupResult:
    status: str           # "ok" | "warning" | "error"
    stale_detected: bool  # Was stale lock found?
    cleanup_attempted: bool  # Was the quarantine rename attempted?
    cleanup_done: bool    # Did the rename succeed?
    reason: str           # Safe reason string (never contains path/pid/boot_id)
    age_seconds: int      # Lock age at time of check
    marker_version: int   # 1 or 2
```

### 7.2 Allowed in Result / Logs

- `status`, `stale_detected`, `cleanup_attempted`, `cleanup_done`
- `reason` (safe string from allowed set)
- `age_seconds`, `marker_version`
- `component` from v2 marker (`player` / `sidecar`)
- `operation` from v2 marker (`pop_write` / `rotation_apply` / etc.)
- `schema_version` from v2 marker
- `created_at_utc` from v2 marker

### 7.3 Forbidden in Result / Logs

- `pid` value — never exposed
- `boot_id_hash` value — never exposed
- Absolute file path — never exposed
- `token`, `jwt`, `password`, `secret`, `api_key`, `private_key`
- `payment_card`, `receipt_data`, `card_number`, `pan`
- `customer_id`, `phone`, `email`, `receipt_number`, `fiscal_data`
- `authorization`, `bearer`, `device_secret`, `access_token`
- `backend_base_url`
- Payload body (raw JSON of sent PoP events)
- Raw PoP JSON with `manifest_item_id`, `device_event_id`, `batch_id`, `campaign_id`, `creative_id`, `schedule_item_id`
- `sha256` (of media), `fingerprint` values
- `full_manifest`, `media_bytes`
- `stacktrace` with sensitive data

### 7.4 Allowed Reason Strings (safe set)

```
"stale_detected_v1_no_cleanup"
"stale_detected_v2_cleanup_done"
"stale_detected_v2_pid_alive"
"stale_detected_v2_boot_id_match"
"stale_detected_v2_marker_invalid"
"stale_detected_v2_cleanup_race"
"cleanup_not_needed"
"cleanup_disabled_v1_marker"
"cleanup_rename_failed"
"stale_critical_escalate_operator"
```

## 8. Risk Analysis

### 8.1 Primary Risks

| # | Risk | Severity | Mitigation | Remaining Gap |
|---|---|---|---|---|
| R‑L1 | Deleting active lock (sidecar holds lock, cleanup deletes it) | **Critical** | Atomic rename quarantine pattern; v2 marker with PID+boot_id check; no direct `unlink()` | Race window: between PID check and rename, a new process could start with same PID. Mitigated by boot_id_hash. |
| R‑L2 | PID reuse (process dies, new process gets same PID, cleanup kills active lock) | **High** | `boot_id_hash` in v2 marker; PID alone never sufficient | Without boot_id_hash, PID reuse is a real risk on long-running systems |
| R‑L3 | Clock drift / mtime unreliable | **Medium** | Use `stat().st_mtime` which is filesystem time, not wall clock; ext4 uses server monotonic time | NTP sync issues could make `created_at_utc` vs. `mtime` disagree. Threshold margin mitigates |
| R‑L4 | Invalid v2 marker JSON (corrupt lock file) | **Medium** | `json.loads()` with strict validation; if marker invalid → treat as v1 (detect-only, no cleanup) | Partial writes (power loss during write) could leave corrupt JSON |
| R‑L5 | v1 marker without metadata (cannot distinguish genuine from stale) | **High** | **Detect-only** — no auto-cleanup under any circumstances | Manual operator intervention required. Sidecar logs `stale_detected_v1` at every cycle while lock exists |
| R‑L6 | Disk full — rename fails, lock persists | **Medium** | `rename()` on same filesystem requires only directory entry change, not new data blocks | If `/var/lib` is 100% full, even rename may fail. Sidecar reports `cleanup_rename_failed`. Lock persists as-is |
| R‑L7 | Permission denied — cleanup cannot read/rename lock | **Medium** | All components run as same `verny-kso` user (base model) | Future user split could cause permission mismatch. Test in integration |
| R‑L8 | Crash during cleanup rename (SIGKILL after rename but before marker re-read) | **Low** | `rename()` is atomic — either old name or new name exists, never both. No partial state | Stale artifact `player_events.lock.stale.<ts>` persists but is harmless (logrotate cleans later) |
| R‑L9 | Cleanup while player writes (race: player starts write between PID check and rename) | **Critical** | Player acquires lock BEFORE any file write — if lock is renamed mid-acquisition, player's `O_CREAT \| O_EXCL` will succeed (old lock is gone → new lock created) | Race window exists but consequence is benign: player creates new valid lock. Sidecar's rename of OLD lock does not affect player's NEW lock (different inode after rename) |
| R‑L10 | Cleanup while sidecar rotation runs (race: rotation holds lock, cleanup renames it) | **Critical** | PID check (`os.kill(pid, 0)`) before rename — if rotation process exists, cleanup stops. Atomic rename — even if race occurs, rename on ext4 returns `ENOENT` if source is already gone | If sidecar releases lock between PID check and rename, rename succeeds on now-released lock — harmless (would have been unlinked by sidecar anyway) |

### 8.2 Risk L1–L2 Deep Dive: The PID Reuse Problem

```
Timeline (worst case without boot_id_hash):
  T0:  sidecar PID=5000 acquires lock, writes v2 marker with pid=5000
  T1:  SIGKILL kills sidecar PID=5000
  T2:  Stale lock persists on disk
  T3:  Cleanup reads marker: pid=5000, age=15 min
  T4:  os.kill(5000, 0) → ProcessLookupError → PID not alive → seems stale!
  T5:  Meanwhile, system spawns NEW process with PID=5000 (unrelated daemon)
  T6:  Cleanup renames lock → lock is "cleaned"
  T7:  Meanwhile, sidecar restarts, acquires NEW lock → OK (rename was on old inode)

  In this scenario: cleanup is actually safe because:
    - Old lock file was genuinely stale (owned by dead process)
    - New process PID=5000 is irrelevant (not a lock owner)
    - New sidecar instance creates fresh lock via O_CREAT | O_EXCL

  BUT — what if the scenario is:
  T0:  sidecar PID=5000 acquires lock for rotation (slow: 25 sec remaining)
  T1:  Cleanup reads marker: pid=5000, age=15 min → WRONG (lock is 5 sec old, clock is wrong)
  T4:  os.kill(5000, 0) → Process EXISTS (sidecar still running) → cleanup stops ✅

  Clock-dependent mitigation: age is from mtime, not from marker `created_at_utc`.
  Marker `created_at_utc` is v2 metadata for diagnostics only — the cleanup
  decision uses filesystem `st_mtime` (reliable for age calculation).
```

### 8.3 Risk Matrix Summary

```
                    │ PID alive? │ PID dead? │ PID dead + boot changed?
────────────────────┼────────────┼───────────┼─────────────────────────
v1 marker           │  DETECT    │  DETECT   │  DETECT (no cleanup)
v2 marker, no boot  │  SKIP      │  ⚠️ RISK   │  ⚠️ RISK (PID reuse)
v2 marker + boot    │  SKIP      │  CLEANUP  │  CLEANUP (safe)
```

## 9. Go / No-Go for Implementation

### 9.1 Conclusion: **Conditional Go**

**Conditions before v2 auto-cleanup implementation:**

| # | Condition | Status |
|---|---|---|
| 1 | v2 marker format implemented in player and sidecar lock acquisition | ❌ Not yet (v1 marker only) |
| 2 | `boot_id_hash` implemented or documented as optional with PID-only fallback | ❌ Not yet |
| 3 | Lock acquisition functions patched to write v2 marker JSON instead of `"locked\n"` | ❌ Not yet |
| 4 | Validated on ServPlus Sherman-J 5.1 (ext4, monotonic clock, `/proc` availability) | ❌ Not yet |
| 5 | Tests covering: stale v2 lock, active v2 lock, v1 fallback, corrupt marker, rename race | ❌ Not yet |

### 9.2 Phased Approach Recommendation

```
Phase A (now — this design):
  ✅ Document v1 limitations
  ✅ Propose v2 marker format
  ✅ Define safe cleanup pattern
  ✅ Risk analysis

Phase B (future step — marker upgrade):
  ⬜ Implement v2 marker in pop_writer._acquire_lock()
  ⬜ Implement v2 marker in pop_pending_lock.acquire()
  ⬜ Backward compatible: reader handles both v1 and v2
  ⬜ Tests: v2 marker format, validation

Phase C (future step — detect-only):
  ⬜ Implement StaleLockDetector (read-only, no cleanup)
  ⬜ Sidecar preflight: detect + report stale locks
  ⬜ Heartbeat includes stale_lock_detected flag
  ⬜ CLI: stale-lock-check --root (read-only)
  ⬜ Tests: v1 detect, v2 detect, active skip

Phase D (future step — cleanup):
  ⬜ Implement StaleLockCleanup with atomic quarantine rename
  ⬜ Sidecar preflight: detect → cleanup (v2 only)
  ⬜ Operator manual cleanup CLI: stale-lock-cleanup --root --confirm
  ⬜ Tests: stale v2 cleanup, active v2 skip, v1 skip, rename race
  ⬜ Integration test: crash sidecar mid-rotation → stale lock → next cycle cleans up
```

### 9.3 Immediate Actions (no code changes)

| Action | Block/Step |
|---|---|
| Accept this design document | 27.3 ✅ (current) |
| Implement v2 lock marker (player + sidecar) | 27.3.1 (next) |
| Implement detect-only stale lock check | 27.3.2 |
| Implement atomic quarantine cleanup (v2 only) | 27.3.3 |

## 10. Not In Scope

This design does NOT cover:

- Implementation of v2 marker in code
- Implementation of detect-only or cleanup logic
- systemd `ExecStartPre` / `ExecStopPost` scripts
- Operator manual cleanup CLI tool
- Integration tests with real SIGKILL
- Windows lock handling (Windows not supported)
- Lock files for other resources (only `player_events.lock`)

## 11. References

| Document | Relevance |
|---|---|
| `apps/kso_player/kso_player/pop_writer.py` | Lock acquire/release, marker `"locked\n"` |
| `apps/kso_sidecar_agent/kso_sidecar_agent/pop_pending_lock.py` | Sidecar lock context manager |
| `apps/kso_sidecar_agent/docs/full_audit_before_kso_runtime.md` | R02 — Stale lock (High severity) |
| `apps/kso_sidecar_agent/docs/linux_kso_runtime_filesystem_contract.md` | §10 — Failure modes, stale lock on systemd restart |
| `apps/kso_sidecar_agent/docs/linux_kso_systemd_service_contract.md` | §7 — Restart/fail-safe, lock-unavailable behavior |

## 12. Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-06-20 | Initial design — v1 limitations, v2 marker proposal, atomic quarantine pattern, risk analysis, Conditional Go conclusion |
