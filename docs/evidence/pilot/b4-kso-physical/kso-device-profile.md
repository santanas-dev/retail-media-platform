# B4 — KSO Device Profile

**Date:** 2026-07-02 | **Status:** 🟡 PROFILE DOCUMENTED — physical verification pending

## Device Information

| Field | Value | Verified |
|---|---|---|
| **IP Address** | 192.168.110.223 | 🟡 Assumed |
| **Device Type** | KSO (UKM5) | 🟡 Assumed |
| **OS** | Linux | ⬜ Needs `uname -a` |
| **Browser** | Chromium (kiosk mode) | ⬜ Needs visual |
| **Screen** | 768 × 1024 px | ⬜ Needs `xrandr` |
| **Orientation** | Portrait | ⬜ Needs visual |
| **Network** | Internal LAN (192.168.110.0/24) | ⬜ Needs `ping` |
| **User** | ukm5 | 🟡 Assumed |

## Manual Verification Commands

```bash
# Run on KSO device (ssh ukm5@192.168.110.223)
uname -a                    # OS version
xrandr                      # Resolution + orientation
df -h                       # Disk space
free -m                     # Memory
ping -c 3 192.168.110.77    # Gateway connectivity
curl http://192.168.110.77:8421/health   # Backend health
```

## Status

- Profile documented: ✅
- Physical verification: ⬜ Pending manual access
