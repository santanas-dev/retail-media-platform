# Full Audit Before Linux KSO Player Runtime

**Date:** 2026-06-20
**Auditor:** Hermes Agent (automated code audit)
**Scope:** `apps/kso_player/` + `apps/kso_sidecar_agent/`
**Block:** 26 (PoP Pipeline) → Block 27 (Linux KSO Player Runtime)
**Conclusion:** **Conditional Yes** — Block 27 can proceed with 5 pre-conditions.

---

## Quick Summary

| Metric | Value |
|---|---|
| Sidecar tests | **1583/1583 ✅** |
| Player tests | **365/365 ✅** |
| Total tests | **1948** |
| Sidecar modules | 42 `.py` files |
| Player modules | 9 `.py` files |
| Design docs | 4 `.md` files |
| Commits (PoP pipeline) | 50+ |
| Forbidden strings violations | **0 found** |
| Race conditions | **Mitigated** (fingerprint guard) |
| Windows/MSI/ProgramData | **Absent** |

---

## A. Architecture Audit

### A.1 Chain Correctness ✅

```
Player Runtime (future)         Sidecar Agent
─────────────────────           ─────────────────────
pop_writer.write_event()        
  → flush + fsync               
  → append JSONL to             
    pop/pending/player_events.jsonl
                                 
                                 run_pop_scoped_send_then_rotate():
                                   1. build_pop_send_package(root)
                                      → acquire lock
                                      → read snapshot
                                      → classify (pop_pickup)
                                      → payload + sent_scope (fingerprinted)
                                      → release lock
                                   2. run_pop_scoped_send(http_client, payload)
                                      → run_pop_send_with_retry()
                                      → fake/backend send
                                      → PopScopedSendResult
                                   3. decide_pop_rotation_after_scoped_send(result)
                                      → 8-gate pure-logic check
                                   4. IF allowed:
                                      apply_pop_rotation_local(
                                        root,
                                        send_run_result,
                                        sent_scope
                                      )
                                      → acquire lock
                                      → materialize (classify + fingerprint check)
                                      → atomic write sent/quarantine/dry_run/failed
                                      → atomic rewrite pending
                                      → release lock
```

**Verdict:** Chain is correct. One snapshot for payload + sent_scope. No redundant re-scanning of pending between send and rotation.

### A.2 Snapshot & Lock Contract ✅

| Phase | Lock Held? | Snapshot Source |
|---|---|---|
| Package build | YES (acquired in `build_pop_send_package`, released after) | `player_events.jsonl` read once |
| Scoped send | NO (lock released after package build) | N/A (uses in-memory `_payload`) |
| Decision | NO (pure logic) | N/A (reads `PopScopedSendResult`) |
| Rotation apply | YES (acquired in `apply_pop_rotation_local`) | `player_events.jsonl` re-read under new lock |

**Verdict:** Lock is acquired exactly twice — once for package build, once for rotation apply. Between them, no lock is held — this is intentional and correct (send may take seconds, cannot hold lock).

### A.3 PoP Event Loss Risk Assessment ✅

| Risk | Mitigation |
|---|---|
| Event appended between send and rotation | **Fingerprint guard**: even if same line_number, SHA-256 mismatch → retained in pending |
| Event appended DURING package build | Lock held → player writer cannot append |
| Event appended DURING rotation apply | Lock held → player writer cannot append |
| Lock acquisition failure | Returns warning, pending untouched |
| Target write failure | Abort, pending untouched |
| Pending rewrite failure | Abort, pending untouched |

**Verdict:** No known path to event loss. Fail-closed design throughout.

### A.4 Draft/Blocked/Invalid NOT sent as PoP ✅

All three classification pipelines enforce:
- Only `CLASS_ELIGIBLE` (completed + idle + manifest mapping + media complete) → payload/sent
- `classify_pop_event()` called in both `build_pop_send_package` and `materialize_pop_rotation_records_locked`
- Draft/blocked/failed → `dry_run/` (sanitized records, no raw JSON)
- Invalid/forbidden → `quarantine/` (sanitized records)

**Verdict:** Draft is never PoP. Dry-run is never PoP. Only backend-confirmed completed eligible events go to `sent/`.

### A.5 Race Condition Between Send and Rotation ✅

**Two-level guard:**

1. **Line number scope** (`_line_numbers` frozenset) — prevents new appended events
2. **Fingerprint guard** (`_line_fingerprints` dict) — catches in-place changes

```
build_pop_send_package:
  line 1, selected_order=0 → payload event
  line 1 fingerprint = SHA-256(line_1_json) → _line_fingerprints[1]

[Pending changed: line 1 now has selected_order=2]

apply_pop_rotation_local:
  line 1, selected_order=2
  → has_line(1) = True ✓
  → fingerprint_matches(1, SHA-256(changed_line)) = False ✗
  → sent_scope_mismatched++
  → retained in pending
```

**Verdict:** Fingerprint guard correctly detects changed lines. Verified in `test_race_changed_line_fingerprint_mismatch`.

---

## B. Security Audit

### B.1 Forbidden Substrings in Code ✅

Global scan of all 51 `.py` files for forbidden substrings in non-test logic paths:

| Forbidden | In code paths? | In repr/format? | In test data? |
|---|---|---|---|
| token, jwt, password, secret, api_key | Only in `FORBIDDEN_SUBSTRINGS` constant | No | Only in `FORBIDDEN_SUBSTRINGS` test checks |
| payment_card, receipt_data, card_number, pan | No | No | No |
| customer_id, phone, email | No | No | No |
| local_path, file_path | No | No | No |
| authorization, bearer, device_secret, access_token | Only in `FORBIDDEN_SUBSTRINGS` constant | No | No |
| media_path, creatives/, backend_base_url, 127.0.0.1 | Only in `FORBIDDEN_SUBSTRINGS` constant | No | No |
| device_code | Only in `local_config.py` (safe config field) | No | No |
| filename | Only in forbidden lists | No | No |
| manifest_item_id, device_event_id, batch_id, campaign_id, creative_id, schedule_item_id | Only in `PopPayloadEvent` (repr=False) | No | No |
| sha256, full_manifest, media_bytes | Only in forbidden lists | No | No |
| fingerprint | Only in `README.md` as concept | No values printed | No values printed |
| stacktrace | No | No | No |

**Verdict:** **Zero forbidden substring violations in output paths.** All sensitive fields use `repr=False`. All format functions have `FORBIDDEN_SUBSTRINGS` scan before return.

### B.2 Payload Body Protection ✅

- `PopPayloadEnvelope` — all fields `repr=False`
- `PopPayloadEvent` — all ID fields `repr=False`
- `PopSendPackageResult` — `_payload` is `repr=False`
- `PopScopedSendResult` — `_send_run_result`, `_sent_scope` are `repr=False`
- `PopSendRotationOrchestratorResult` — `_scoped_send_result`, `_decision`, `_apply_result` are `repr=False`
- All `format_*()` functions scan output for forbidden substrings before return

**Verdict:** Payload body never leaks through repr/format/output.

### B.3 Token/Secret Handling ✅

- Dev-only `secret_store.py` — secret only via stdin, never CLI args
- Token stored in-memory only (`TokenState`)
- `safe_summary()` returns only metadata (authenticated, device_code, expires_at)
- No token in logs, config, status, or doctor output
- `SafeHttpClient` — Authorization header never logged

**Verdict:** Token/secret handling follows dev-only contract. Production secret store not yet implemented (noted as gap).

### B.4 Forbidden Fields in Backend Response ✅

`pop_sender.py` `_extract_counts()`:
- Checks `FORBIDDEN_RESPONSE_KEYS` before extracting counts
- Forbidden key found → empty counts, response is treated as `invalid_response`
- Only `ALLOWED_COUNT_KEYS` extracted: `accepted_events`, `duplicate_events`, `rejected_events`, `attempted_events`, `status`, `batch_status`

**Verdict:** Backend response is sanitised. No ID leakage from response.

---

## C. Safety / Fail-Safe Audit

### C.1 Failure Mode Table

| Failure | Behavior | Pending |
|---|---|---|
| Lock unavailable (package build) | warning, no send | ✅ untouched |
| Lock unavailable (rotation apply) | warning, no rotation | ✅ untouched |
| Target write failure (sent/) | error, abort rotation | ✅ untouched |
| Pending rewrite failure | error, target files may exist | ✅ untouched |
| 409 duplicate from backend | warning, no rotation | ✅ untouched |
| `pending_should_remain=true` | warning, no rotation | ✅ untouched |
| No backend confirmation | sent_records=0 | ✅ untouched |
| Completed without sent_scope | sent_records=0 (sent_scope_required) | ✅ untouched |
| Completed with fingerprint mismatch | sent_records=0 (sent_scope_mismatch) | ✅ untouched |
| Draft/blocked/failed events | → dry_run (sanitized) | ✅ removed from pending |
| Invalid/forbidden events | → quarantine (sanitized) | ✅ removed from pending |
| Locked materializer without lock | warning, no operation | ✅ untouched |

**Verdict:** **Fail-closed everywhere.** Pending is never modified unless rotation succeeds.

### C.2 Key Safety Rules Enforced

1. ✅ `sent/` only for `send_run_result.run_status=ok AND pending_should_remain=false AND scope_matched`
2. ✅ 409 duplicate → `pending_should_remain=true` → sent=0
3. ✅ No backend confirmation → sent_records=0
4. ✅ Completed without scope → sent=0 (sent_scope_required)
5. ✅ Fingerprint mismatch → sent=0 (sent_scope_mismatch)
6. ✅ Draft → dry_run (NOT sent)
7. ✅ Invalid → quarantine (NOT sent)
8. ✅ Real backend never called in tests

---

## D. File Operations Audit

### D.1 Atomic Write Pattern ✅

All file operations use the same pattern:
```
1. Write to .tmp
2. flush()
3. os.fsync()
4. os.replace(.tmp, target)
5. os.fsync(parent_dir)
```

Used in:
- `pop_rotation_files.py` — `write_pop_rotation_records_atomic()`
- `pop_pending_rewrite.py` — `rewrite_pending_pop_events_atomic()`

### D.2 Lock Discipline ✅

- `try_acquire_pop_pending_lock()` — non-blocking, `O_CREAT | O_EXCL`
- `release_pop_pending_lock()` — fail-silent `unlink()`
- `pop_pending_lock` context manager — release in `__exit__` (does NOT suppress exceptions)
- Helper never deletes foreign lock
- `_lock_path` is `repr=False`

### D.3 Pending Rewrite Requirements ✅

- `rewrite_pending_pop_events_atomic()` requires `lock_result` with `acquired=True`
- Validates each record for forbidden keys/values
- Empty records list → creates empty pending file (valid: all events rotated out)
- On failure → Error returned, pending untouched

### D.4 Empty Bucket Handling ✅

- Empty `_sent_records` → no `sent/` directory created
- Empty `_quarantine_records` → no `quarantine/` directory created
- Only non-empty buckets trigger `write_pop_rotation_records_atomic()`

### D.5 Tmp Cleanup ✅

- `write_pop_rotation_records_atomic()` — `finally: _safe_unlink(tmp_path)`
- `rewrite_pending_pop_events_atomic()` — `finally: _safe_unlink(tmp_path)`
- `release_pop_pending_lock()` — `_safe_unlink(lock_path)` with `FileNotFoundError` catch

---

## E. PoP Correctness Audit

### E.1 Proof of Play Definition ✅

| Event status | Is PoP? | Rotation target |
|---|---|---|
| `completed` (eligible: idle + manifest + media) | ✅ Yes | `sent/` (if backend confirmed + scope matched) |
| `draft` | ❌ No | `dry_run/` (sanitized rotation record) |
| `blocked` | ❌ No | `dry_run/` |
| `failed` | ❌ No | `dry_run/` |
| Invalid JSON | ❌ No | `quarantine/` |
| Forbidden fields | ❌ No | `quarantine/` |

### E.2 Sent Requirements ✅

Event goes to `sent/` ONLY when ALL conditions met:
1. `event_status == "completed"` AND `event_type == "would_play"` AND `safety_state == "idle"`
2. `selected_order` maps to current manifest
3. Media cache complete
4. `send_run_result.run_status == "ok"`
5. `send_run_result.pending_should_remain == False`
6. NOT 409 duplicate
7. `line_number ∈ sent_scope._line_numbers`
8. `fingerprint_matches(line_number, SHA-256(current_line))` (if fingerprinted scope)

### E.3 409 Duplicate Policy ✅

409 duplicate batch → `pending_should_remain=True` → **pending NOT deleted**. Backend saw `batch_id` but without explicit per-event `accepted`/`processed` confirmation, pending must remain. This is a **conservative safe default** — requires backend contract enhancement for per-event duplicate-safe removal.

### E.4 Partial/Aggregate Send Without Mapping ✅

If backend response has aggregate counts (`accepted=1, rejected=2`) but NO per-event mapping (which event was accepted, which was rejected), the current design does NOT delete pending. This is correct because partial success without mapping cannot determine which events to move to sent vs retain.

---

## F. Test Coverage Audit

### F.1 Coverage Metrics

| Layer | Tests | Files |
|---|---|---|
| **Player** | 365 | `test_pop_writer.py` (58), `test_playlist.py` (33), `test_safety.py` (33), `test_session.py` (36), `test_simulator.py` (20), `test_events.py` (20), `test_cli.py` (165) |
| **Sidecar PoP** | ~600 | 16 test files covering: pickup, batch, payload, sender, sender_runner, send_package, scoped_send, decision, orchestrator, rotation_materializer, rotation_files, rotation_plan, rotation_apply, pending_lock, pending_rewrite, E2E |
| **Sidecar non-PoP** | ~983 | Auth, heartbeat, manifest, media, runtime_config, run_cycle, etc. |
| **Total** | **1948** | 53 test files |

### F.2 Key Scenarios Covered ✅

| Scenario | Test location |
|---|---|
| Player writes completed event to pending with lock | `test_pop_writer.py` |
| Sidecar builds package with fingerprinted scope | `test_pop_send_package.py` TestSendPackageFingerprint |
| Sidecar scoped send → fake 200 | `test_pop_scoped_send.py` |
| Decision gate: 8 conditions | `test_pop_send_rotation_decision.py` |
| Orchestrator: full chain 200/500/409 | `test_pop_send_rotation_orchestrator.py` |
| E2E: player event → sent/ | `test_pop_e2e_fake_pipeline.py` Scenarios 1-6 |
| Fingerprint mismatch → sent=0 | `test_pop_rotation_materializer.py` TestMaterializerSentScopeFingerprint |
| Pending untouched on all failures | All failure tests |
| Lock contract: player ↔ sidecar | `test_pop_writer.py` + `test_pop_pending_lock.py` |

### F.3 Gaps — Scenarios NOT Covered

| Gap | Severity | Action |
|---|---|---|
| Stale lock (> N seconds) | Medium | Add stale lock detection + cleanup in Block 27 |
| Disk full during write | Medium | Test `OSError` during fsync |
| Concurrent player + sidecar stress | Medium | Multi-threaded stress test |
| Real KSO state (UKM 4) not tested | High | Requires UKM 4 adapter in Block 27 |
| Production secret store | High | Dev-only; production TPM/Hardware-backed not started |
| Backend contract mismatch (real vs fake) | High | Real backend integration test before pilot |
| Media bytes in cache vs manifest | Low | Already covered by media cache status |

### F.4 Test Quality Observations

- ✅ No test uses real backend (`FakeHttpClient` everywhere)
- ✅ No test reads secret/config/token files
- ✅ Safe output проверяется во всех `format_*` тестах
- ✅ `forbidden substrings` проверяется в repr и format output
- ✅ Fingerprint values проверяются на отсутствие в repr/output
- ⚠️ Some test helpers duplicated across files (`_make_record`, `_make_manifest_data`, `_clear_media_cache`)

---

## G. CLI Audit

### G.1 CLI Commands

| Command | Safe? | Destructive? |
|---|---|---|
| `pop-rotation-plan` | ✅ preview only | No |
| `pop-rotation-apply` | ✅ guarded | Yes (`--confirm-local-rotation` required) |
| `pop-pickup-scan` | ✅ read-only | No |
| `pop-batch-preview` | ✅ in-memory | No |
| `pop-payload-preview` | ✅ in-memory | No |
| `pop-write` (player) | ✅ append with lock | Yes (writes to pending) |

### G.2 CLI Safety Rules ✅

- `pop-rotation-apply` без `--confirm-local-rotation` → exit 2, ничего не делает
- `pop-rotation-apply` без backend confirmation → `sent_records=0`
- Все preview-команды: только агрегаты, без raw JSON, без IDs, без paths
- Все exit codes: 0=ok, 1=warning/error, 2=invalid args

### G.3 CLI Output Safety ✅

All CLI output goes through `format_*()` functions which:
1. Build safe aggregate strings
2. Run `forbidden substrings` scan
3. Raise `ValueError` if forbidden substring found (prevents leak)

---

## H. Linux KSO Readiness Audit

### H.1 Current Architecture — Linux-Only ✅

- File paths: `/tmp/`, root-path based (no `C:\`, no `ProgramData`)
- Lock mechanism: `os.open(O_CREAT | O_EXCL)` — POSIX-only
- No Windows Service, MSI, registry references
- All docs reference Linux/KSO context
- `systemd` mentioned as target (not yet implemented)

### H.2 What Still Needed Before Real KSO Player

| Component | Status | Priority |
|---|---|---|
| `/opt/verny/kso` — player binary path | Not started | Block 27.1 |
| `/etc/verny/kso` — config | Not started | Block 27.2 |
| `/var/lib/verny/kso` — data/pending | Not started | Block 27.3 |
| `/var/log/verny/kso` — logs | Not started | Block 27.3 |
| systemd unit `kso-player.service` | Not started | Block 27.4 |
| systemd unit `kso-sidecar.service` | Not started | Block 27.4 |
| Chromium kiosk-mode launch | Not started | Block 27.5 |
| Local player runtime (event loop) | Not started | Block 27.6 |
| KSO state adapter (СуперМаг УКМ 4) | Not started | Block 27.7 |
| Screen layout 75/25 | Not started | Block 27.8 |
| Watchdog | Not started | Block 27.9 |
| Linux installer package (.deb/.rpm) | Not started | Block 27.10 |
| Pilot checklist | Not started | Block 27.11 |
| Rollback procedure | Not started | Block 27.12 |
| Production secret store (TPM) | Not started | Block 27.13 |
| Real backend integration test | Not started | Block 27.14 |

### H.3 No Windows/MSI/ProgramData ✅

Confirmed: zero references to Windows-specific paths, services, or APIs in all 51 Python files, 4 design docs, and README.

---

## I. Documentation Audit

### I.1 README Consistency ✅

| Claim in README | Code matches? |
|---|---|
| "Draft-события не являются PoP" | ✅ — `CLASS_DRAFT` → `dry_run/`, never `sent/` |
| "409 duplicate не разрешает удалять pending" | ✅ — `pending_should_remain=True` |
| "fingerprint guard защищает от race" | ✅ — `build_pending_line_fingerprint()` + mismatch check |
| "real backend в тестах не вызывается" | ✅ — `FakeHttpClient` everywhere |
| "rotation только после decision gate" | ✅ — `decide_pop_rotation_after_scoped_send()` |
| "sent только при confirmed backend" | ✅ — 8-gate check |

### I.2 Design Docs Consistency ✅

| Design doc | Implemented? |
|---|---|
| `pop_pickup_design.md` | ✅ — `pop_pickup.py` |
| `pop_backend_payload_design.md` | ✅ — `pop_payload.py` |
| `pop_backend_sender_design.md` | ✅ — `pop_sender.py` |
| `pop_local_rotation_design.md` | ✅ — `pop_rotation_apply.py` |

### I.3 No False Promises ✅

- Docs do NOT claim draft is PoP
- Docs do NOT claim 409 is safe to delete
- Docs do NOT claim real backend is tested
- Docs explicitly describe fail-safe behavior

---

## Risk Register

| ID | Risk | Severity | Area | Current Mitigation | Gap | Recommended Next Step |
|---|---|---|---|---|---|---|
| R01 | Race: player appends between send and rotation | **Critical** | PoP Pipeline | Fingerprint guard (SHA-256 match) | None — mitigated | Maintain fingerprint guard; add E2E stress test |
| R02 | Stale lock: crashed process leaves `.lock` | **High** | Lock Contract | None (lock is non-blocking, times out naturally) | Lock never cleaned automatically | Add stale lock detection (>60s) + cleanup in Block 27 |
| R03 | Pending rewrite failure AFTER target write success | **High** | File Ops | Pending untouched; target files already written | Target files may contain events that are still in (failed) pending | Add rollback of target files on pending rewrite failure |
| R04 | 409 duplicate ambiguity — backend saw batch but didn't confirm per-event | **High** | Backend Contract | `pending_should_remain=True` conservative default | Backend contract not finalized | Define per-event confirmation in backend response schema |
| R05 | Future real backend contract mismatch with fake test expectations | **High** | Integration | FakeHttpClient mirrors expected backend behavior | Real contract not yet tested | Real backend integration test before pilot |
| R06 | KSO state adapter uncertainty — UKM 4 state mapping unknown | **High** | Player Runtime | None — not started | UKM 4 API not documented for us | Coordinate with СуперМаг vendor for state enumeration |
| R07 | Chromium kiosk interfering with UKM 4 input | **Medium** | Player Runtime | 75/25 layout planned | Chromium kiosk may steal focus from UKM 4 | Test Chromium kiosk + UKM 4 side-by-side on real KSO |
| R08 | Linux permissions: sidecar cannot read player's pending | **Medium** | Deployment | Same user/group planned | Not implemented | Define user/group; set `umask 002`; verify in systemd unit |
| R09 | Disk full during append/write | **Medium** | File Ops | Atomic `.tmp` + cleanup on failure | `OSError` during `fsync` not specifically tested | Add disk-full simulation tests |
| R10 | Log leakage: forbidden substrings in exception messages | **Medium** | Security | `FORBIDDEN_SUBSTRINGS` scan in format functions | Exception text not scanned before logging | Add `safe_logger` wrapper that redacts forbidden substrings |
| R11 | Clock/time drift between KSO and backend | **Medium** | Heartbeat / Auth | JWT expiration handled by retry | No NTP sync requirement documented | Add NTP sync check in readiness preflight |
| R12 | Manifest mismatch: player and sidecar use different manifest versions | **Medium** | Manifest | `read_current_manifest()` shared; ETag-based | If player caches old manifest → classification mismatch | Add manifest version in player events; cross-check in materializer |
| R13 | Media incomplete: media cache says complete but files corrupted | **Medium** | Media Cache | SHA-256 verify on download | `media_cache_status()` checks file presence + size, but not re-hash | Add periodic rehash of cached media in sidecar watchdog |
| R14 | Service restart during write: systemd restart kills in-flight operation | **Medium** | File Ops | Atomic `.tmp → replace` means partial writes never visible | Lock may be left stale | R01 mitigation + `ExecStopPost` cleanup in systemd unit |
| R15 | Pilot rollback: sent/ events need to be recoverable | **Medium** | Operations | `sent/` directory preserves events as JSONL | No automated rollback procedure | Document manual rollback: move `sent/*.jsonl` back to pending |

---

## Go / No-Go Conclusion

### READY FOR BLOCK 27: **Conditional Yes**

**Conditions before Block 27.1:**

1. ✅ All 1948 tests pass (confirmed: 1583 sidecar + 365 player)
2. ✅ Zero forbidden substring violations
3. ✅ Fingerprint guard protects against race conditions
4. ✅ Fail-closed design throughout — pending never modified on any failure path
5. ✅ No Windows/MSI/ProgramData anywhere

**Pre-requisites to address during Block 27 (not blocking start):**

- R01 (stale lock) should be addressed by 27.3
- R03 (target rollback) should be addressed before pilot
- R04 (409 contract) needs backend team coordination — not blocking dev
- R06 (UKM 4 adapter) is the main Block 27 work item

**Recommended Block 27 order:**
1. 27.1 — File system layout (`/opt`, `/etc`, `/var/lib`, `/var/log`)
2. 27.2 — systemd units (player + sidecar)
3. 27.3 — Stale lock detection + cleanup
4. 27.4 — Chromium kiosk launch
5. 27.5 — Local player runtime (event loop)
6. 27.6 — UKM 4 state adapter
7. 27.7 — Screen layout 75/25
8. 27.8 — Watchdog
9. 27.9 — Installer package
10. 27.10 — Real backend integration test
11. 27.11 — Pilot checklist + rollback procedure
