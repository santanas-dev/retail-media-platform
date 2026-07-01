# KSO Physical Playback Test Protocol

**Version:** 1.0 | **Date:** 2026-07-01 | **Owner:** Ops Team  
**Device:** UKM5 (192.168.110.223) | **OS:** Linux | **Browser:** Chromium kiosk

> **SCOPE:** Lab/stage/pre-pilot only. Does NOT switch to production.  
> **STATUS:** ⬜ Not yet executed — protocol ready.

---

## Prerequisites

- [ ] Physical KSO device powered on and accessible
- [ ] Network connectivity to Gateway confirmed (ping/curl)
- [ ] Linux OS confirmed
- [ ] Chromium installed
- [ ] No active production campaigns on test device
- [ ] Rollback procedure documented and accessible
- [ ] Screen capture / photo evidence capability available

---

## Test Sequence

### Phase 1: Hardware & OS

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 1.1 | Device powers on | Desktop/login visible | Screenshot | ⬜ |
| 1.2 | Linux OS confirmed | `uname -a` | Terminal output | ⬜ |
| 1.3 | No errors in syslog | `dmesg \| tail -20` | Terminal output | ⬜ |
| 1.4 | Free disk space | > 1 GB | `df -h` | ⬜ |
| 1.5 | Free memory | > 500 MB | `free -m` | ⬜ |

### Phase 2: Display & Graphics

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 2.1 | Screen resolution | 768 × 1024 px | `xrandr` | ⬜ |
| 2.2 | Orientation | Portrait | Visual | ⬜ |
| 2.3 | Ad zone dimensions confirmed | 768 × 1024 px occupied | Screenshot with ruler | ⬜ |
| 2.4 | No screen tearing/artifacts | Clean display | Screenshot | ⬜ |

### Phase 3: Chromium Kiosk

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 3.1 | Chromium starts | Window visible | Screenshot | ⬜ |
| 3.2 | Kiosk mode confirmed | Fullscreen, no chrome | Screenshot | ⬜ |
| 3.3 | Local player page loads | `index.html` visible | Screenshot | ⬜ |
| 3.4 | No JS errors in console | Clean console | Console log | ⬜ |

### Phase 4: Network & Gateway

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 4.1 | Ping Gateway | `<1ms` LAN | `ping` output | ⬜ |
| 4.2 | Curl Gateway health | HTTP 200 | `curl` output | ⬜ |
| 4.3 | Gateway auth check | Token obtained | Auth log | ⬜ |
| 4.4 | Manifest preview endpoint | HTTP 200 | Curl output | ⬜ |

### Phase 5: Media Playback

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 5.1 | Media file downloads | mp4/h264 downloaded | File size check | ⬜ |
| 5.2 | Media format validated | ffprobe passes | ffprobe output | ⬜ |
| 5.3 | Playback starts | Video visible in player | Screenshot/video | ⬜ |
| 5.4 | Playback completes | End-to-end play | Video evidence | ⬜ |
| 5.5 | No audio output (KSO) | Silent | Video evidence | ⬜ |
| 5.6 | Ad zone: no overflow/scaling issues | Video fills 768×1024 | Screenshot | ⬜ |
| 5.7 | Ad zone: portrait orientation respected | Correct orientation | Screenshot | ⬜ |

### Phase 6: Playlist / Campaign

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 6.1 | Playlist advances correctly | Next creative plays | Log | ⬜ |
| 6.2 | Campaign targeting respected | Correct creative | Log | ⬜ |
| 6.3 | Campaign scheduling respected | Correct time slot | Log | ⬜ |

### Phase 7: Proof of Play

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 7.1 | PoP event generated | Event in DB | API query | ⬜ |
| 7.2 | PoP visible in analytics | Portal analytics page | Screenshot | ⬜ |
| 7.3 | Heartbeat sent | Heartbeat API | Gateway log | ⬜ |
| 7.4 | Heartbeat visible in portal | Device dashboard | Screenshot | ⬜ |

### Phase 8: Fallback & Rollback

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 8.1 | Fallback to legacy manifest | Legacy plays when universal fails | Log | ⬜ |
| 8.2 | Rollback to legacy mode only | KSO uses legacy endpoint | Log | ⬜ |
| 8.3 | Rollback completed < 5 min | Fast cutover | Timestamp diff | ⬜ |
| 8.4 | Post-rollback: legacy playback OK | Legacy works after rollback | Screenshot | ⬜ |

### Phase 9: Emergency Dry-Run

| # | Check | Expected | Evidence | Result |
|---|---|---|---|---|
| 9.1 | Emergency preview shows device | Device in preview | API response | ⬜ |
| 9.2 | Emergency stop dry-run | 422 on dry_run=false | API response | ⬜ |
| 9.3 | Emergency message dry-run | Preview visible | API response | ⬜ |

---

## Acceptance Criteria

- [ ] All Phase 1–8 checks pass
- [ ] At least 3 full playbacks observed
- [ ] PoP events confirmed for all playbacks
- [ ] Heartbeat received every 60s
- [ ] Rollback tested and confirmed < 5 min
- [ ] Emergency dry-run shows device in scope
- [ ] Evidence collected: screenshots + terminal output + video
- [ ] No production switch triggered

---

## Evidence Checklist

| Artifact | Format | Collected |
|---|---|---|
| Device powered on | Screenshot | ⬜ |
| Resolution confirmed | Screenshot | ⬜ |
| Chromium kiosk | Screenshot | ⬜ |
| Playback (1) | Video (.mp4) | ⬜ |
| Playback (2) | Video (.mp4) | ⬜ |
| PoP in portal | Screenshot | ⬜ |
| Heartbeat in portal | Screenshot | ⬜ |
| Legacy fallback | Screenshot | ⬜ |
| Emergency preview | Screenshot | ⬜ |

---

## Decision

| Gate | Result |
|---|---|
| KSO physical playback passed | ⬜ Yes / ⬜ No / ⬜ Partial |
| Blockers found | ______________ |
| Ready for pilot | ⬜ Yes / ⬜ No |
| Approver | ______________ | Date: __-__-__ |
