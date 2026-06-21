"""Step 28.3 — KSO safe manifest gateway integration smoke test.

Verifies:
- Existing manifest endpoint still works (regression)
- Response safety enforced (no forbidden fields in output)
- Invalid auth safe error (no internals leaked)
- No unit test assertions — integration-only.

Note: Uses existing test device data from Step 13 infrastructure.
If no published KSO manifest exists, tests gracefully handle "no_manifest".
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://localhost:8001/api"

PASS = "✅"
FAIL = "❌"
passed = 0
failed = 0
results = []


def r(method, path, body=None, token=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req_obj = Request(url, data=data, method=method, headers=hdrs)
    try:
        resp = urlopen(req_obj)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        try:
            return e.code, json.loads(e.fp.read())
        except Exception:
            return e.code, {"detail": str(e)}


def check(name, a, b=None, body=None, field_checks=None):
    global passed, failed
    if b is None and field_checks is None:
        ok = bool(a)
        status_got = None
    else:
        status_got, expected = a, b
        ok = status_got == expected
    extra = ""
    if field_checks and body:
        for f, ev in field_checks.items():
            got = body.get(f)
            if got != ev:
                ok = False
                extra += f" [{f}: got={got}, expected={ev}]"
    tag = PASS if ok else FAIL
    if status_got is not None:
        results.append(f"{tag} {name} -> HTTP {status_got}{extra}")
    else:
        results.append(f"{tag} {name}")
    if not ok and body:
        results.append(f"   {str(body)[:300]}")
    if ok:
        passed += 1
    else:
        failed += 1


# ══════════════════════════════════════════════════════════════════════
# Admin login
# ══════════════════════════════════════════════════════════════════════

s, aj = r("POST", "/auth/login", {"username": "admin", "password": "Admin123!"})
assert s == 200, f"Admin login failed: {aj}"
at = aj["access_token"]

# ══════════════════════════════════════════════════════════════════════
# Find a KSO gateway device
# ══════════════════════════════════════════════════════════════════════

# First, find KSO channel ID
s, ch_list = r("GET", "/channels", token=at)
assert s == 200
kso_chan = next((c for c in ch_list if c.get("code") == "kso"), None)
check("KSO channel exists", kso_chan is not None)

if kso_chan:
    kso_channel_id = kso_chan["id"]

    # Find KSO device
    s, devs = r("GET", f"/gateway-devices?limit=50", token=at)
    kso_dev = None
    if s == 200:
        for d in devs:
            if d.get("channel_id") == kso_channel_id and \
                    d.get("status") in ("pending", "active", "lost"):
                kso_dev = d
                break

    check("KSO active device found", kso_dev is not None)

    if kso_dev:
        dev_id = kso_dev["id"]
        dev_code = kso_dev["device_code"]

        # Create credential
        s, cr = r("POST", f"/gateway-devices/{dev_id}/credentials",
                  token=at)
        if s == 401:  # duplicate - get existing
            s, cr = r("POST", f"/gateway-devices/{dev_id}/credentials",
                      token=at)

        if s in (200, 201) and "device_secret" in cr:
            secret = cr["device_secret"]

            # Get device token
            s, dt_resp = r("POST", "/device-gateway/auth/token", {
                "device_code": dev_code,
                "device_secret": secret,
            })
            check("Device auth", s == 200)
            if s == 200:
                dt = dt_resp["access_token"]

                # ── Manifest endpoint test ──────────────────────────
                s, manifest = r("GET", "/device-gateway/manifest/current",
                                token=dt)

                # Allowed responses: 200 (served/no_manifest) or 403 (disabled)
                check("Manifest endpoint responds",
                      s in (200, 403),
                      body=manifest)

                if s == 200:
                    check("Response has status field",
                          "status" in manifest)

                    if manifest.get("status") == "served" and \
                            manifest.get("manifest"):
                        mf = manifest["manifest"]

                        # Check safe fields present
                        check("schemaVersion present",
                              mf.get("schemaVersion") is not None)
                        check("channel field present",
                              "channel" in mf)
                        check("storeCode present",
                              "storeCode" in mf)
                        check("deviceCode present",
                              "deviceCode" in mf)
                        check("items array present",
                              isinstance(mf.get("items"), list))

                        # Check items format
                        for item in mf.get("items", []):
                            mr = item.get("mediaRef", "")
                            if mr:
                                check(f"mediaRef format: {mr}",
                                      mr.startswith("media/current/slot-"))

                        # Check forbidden fields absent
                        mf_json = json.dumps(mf, sort_keys=True).lower()
                        forbidden = [
                            "token", "secret", "api_key", "password",
                            "credential", "authorization",
                            "file_path", "media_path", "creatives/",
                            "manifest_item_id", "campaign_id",
                            "creative_id", "rendition_id",
                            "schedule_item_id", "batch_id",
                            "budget", "price", "currency",
                            "customer_id", "phone", "email",
                            "card_number", "receipt_data", "fiscal_data",
                            "backend_base_url", "device_secret",
                            "sha256",
                        ]
                        clean = True
                        for fb in forbidden:
                            if fb in mf_json:
                                clean = False
                                results.append(
                                    f"   ❌ forbidden '{fb}' in KSO manifest")
                        check("No forbidden fields in KSO manifest", clean)

                    elif manifest.get("status") == "no_manifest":
                        check("No manifest — valid empty response", True)

# ══════════════════════════════════════════════════════════════════════
# Output safety — error responses
# ══════════════════════════════════════════════════════════════════════

s, body = r("GET", "/device-gateway/manifest/current",
            token="invalid_token_12345")
check("Invalid token → 401", s == 401, body=body)
if s == 401:
    body_str = json.dumps(body).lower()
    safe = True
    for fb in ("stacktrace", "at line", "traceback", "file \"",
                "minio", "postgresql", "database"):
        if fb in body_str:
            safe = False
            results.append(f"   ❌ error response leaks '{fb}'")
    check("Error response safe (no internals)", safe)

# ══════════════════════════════════════════════════════════════════════
# Unit test coverage: projection builder tests
# ══════════════════════════════════════════════════════════════════════

# Verify builder tests pass (separate process)
import subprocess
proc = subprocess.run(
    [sys.executable, "-m", "pytest",
     "app/domains/publications/test_kso_manifest_projection.py", "-q"],
    capture_output=True, text=True, timeout=30,
)
check("Projection builder tests", proc.returncode == 0,
      body={"output": proc.stdout[:200] + proc.stderr[:200]})

# ══════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════

print("\n".join(results))
print(f"\n{passed} passed, {failed} failed")
if failed:
    sys.exit(1)
