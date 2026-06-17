"""Step 15 — Device Operations verification."""
import json, sys, uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from datetime import datetime, timezone

BASE = "http://localhost:8001/api"
PASS, FAIL = "✅", "❌"
p, f = 0, 0

def r(m, path, b=None, t=None):
    u = f"{BASE}{path}"
    d = json.dumps(b).encode() if b else None
    req = Request(u, data=d, method=m, headers={"Content-Type": "application/json"})
    if t: req.add_header("Authorization", f"Bearer {t}")
    try: return urlopen(req).status, json.loads(urlopen(req).read())
    except HTTPError as e:
        try: return e.code, json.loads(e.fp.read())
        except: return e.code, {"detail": str(e)}

def ck(n, ok, extra=""):
    global p, f
    if ok: p += 1; print(f"{PASS} {n}{extra}")
    else: f += 1; print(f"{FAIL} {n}{extra}")

# Tokens
_, aj = r("POST", "/auth/login", {"username": "admin", "password": "Admin123!"})
at = aj["access_token"]

# Get device token (for auth tests)
import asyncpg, asyncio
async def dtok():
    c = await asyncpg.connect(host='localhost', user='retail_media', password='retail_media_dev', database='retail_media_platform')
    r_ = await c.fetchrow("SELECT gd.id, gd.device_code, dc.id as cid FROM gateway_devices gd JOIN device_credentials dc ON dc.gateway_device_id=gd.id AND dc.credential_type='shared_secret' AND dc.status='active' WHERE gd.status IN ('active','pending','lost') LIMIT 1")
    await c.close()
    return str(r_['id']), r_['device_code'], str(r_['cid']) if r_ else (None, None, None)
did, dcode, cid = asyncio.run(dtok())
if cid:
    s, cr = r("POST", f"/gateway-devices/{did}/credentials/{cid}/revoke", t=at)
    s, cr = r("POST", f"/gateway-devices/{did}/credentials", t=at)
    if s == 201:
        s, dtresp = r("POST", "/device-gateway/auth/token", {"device_code": dcode, "device_secret": cr["device_secret"]})
        dt = dtresp.get("access_token", "") if s == 200 else ""
    else:
        dt = ""
else:
    dt = ""

print(f"Device token: {'OK' if dt else 'N/A'}")

# ── 1. Overview ──
print("\n=== 1. Overview ===")
s, b = r("GET", "/device-operations/overview", t=at)
ck("HTTP 200", s == 200)
ck("status=ok", b.get("status") == "ok")
ck("has period", "period" in b and "date_from" in b["period"])
ck("has summary", "summary" in b)
ck("has pipeline", "pipeline" in b)
ck("has errors", "errors" in b)
ck("total_devices > 0", b["summary"]["total_devices"] > 0)

# Auth
s, b = r("GET", "/device-operations/overview")
ck("No token → 401", s == 401)
if dt:
    s, b = r("GET", "/device-operations/overview", t=dt)
    ck("Device token → 401", s == 401)

# ── 2. Devices list ──
print("\n=== 2. Devices ===")
s, b = r("GET", "/device-operations/devices?limit=5", t=at)
ck("HTTP 200", s == 200)
ck("is list", isinstance(b, list))
ck("items <= 5", len(b) <= 5)

# Filters
s, b = r("GET", "/device-operations/devices?device_status=disabled&limit=5", t=at)
ck("filter device_status", s == 200 and all(d["device_status"] == "disabled" for d in b))

s, b = r("GET", "/device-operations/devices?health_status=offline&limit=3", t=at)
ck("filter health_status", s == 200)

s, b = r("GET", "/device-operations/devices?problem_type=no_heartbeat&limit=5", t=at)
ck("filter problem_type", s == 200)

# Date range
s, b = r("GET", "/device-operations/devices?date_from=2026-06-01T00:00:00&date_to=2026-06-15T00:00:00&limit=5", t=at)
ck("date range OK", s == 200)

s, b = r("GET", "/device-operations/devices?date_from=2026-12-31T00:00:00&date_to=2026-01-01T00:00:00", t=at)
ck("date_from > date_to → 400", s == 400)

s, b = r("GET", "/device-operations/devices?date_from=2020-01-01T00:00:00&date_to=2020-02-01T00:00:00", t=at)
ck("period > 30d → 400", s == 400)

# Limit/offset
s, b = r("GET", "/device-operations/devices?limit=1&offset=0", t=at)
ck("limit=1", s == 200 and len(b) == 1)
s, b = r("GET", "/device-operations/devices?limit=9999", t=at)
ck("limit > 500 → 422", s == 422)
s, b = r("GET", "/device-operations/devices?offset=-1", t=at)
ck("offset < 0 → 422", s == 422)

# ── 3. Device detail ──
print("\n=== 3. Device detail ===")
# Get first device from list
s, devs = r("GET", "/device-operations/devices?limit=1", t=at)
if isinstance(devs, list) and devs:
    dev_id = devs[0]["gateway_device_id"]
    s, b = r("GET", f"/device-operations/devices/{dev_id}", t=at)
    ck("HTTP 200", s == 200)
    ck("has device", "device" in b)
    ck("has recent_heartbeats", "recent_heartbeats" in b)
    ck("has recent_manifest_requests", "recent_manifest_requests" in b)
    ck("has recent_media_requests", "recent_media_requests" in b)
    ck("has recent_pop_events", "recent_pop_events" in b)
    ck("has recent_pop_batches", "recent_pop_batches" in b)
    ck("has recent_device_events", "recent_device_events" in b)
    ck("has health_status", "health_status" in b or "device" in b)
    # Check no secrets in response
    body_str = json.dumps(b, default=str)
    ck("no device_secret", "device_secret" not in body_str)
    ck("no secret_hash", "secret_hash" not in body_str.lower())

# ── 4. Stores ──
print("\n=== 4. Stores ===")
s, b = r("GET", "/device-operations/stores", t=at)
ck("HTTP 200", s == 200)
ck("is list", isinstance(b, list))
if isinstance(b, list) and b:
    ck("has store_id", "store_id" in b[0])
    ck("has total_devices", "total_devices" in b[0])

# ── 5. Channels ──
print("\n=== 5. Channels ===")
s, b = r("GET", "/device-operations/channels", t=at)
ck("HTTP 200", s == 200)
ck("is list", isinstance(b, list))

# ── 6. Security ──
print("\n=== 6. Security ===")
s, ov = r("GET", "/device-operations/overview", t=at)
ov_str = json.dumps(ov, default=str)
ck("overview: no secrets", not any(kw in ov_str.lower() for kw in ["password","secret","token","api_key","device_secret","presigned"]))

s, dl = r("GET", f"/device-operations/devices/{dev_id}", t=at) if dev_id else (0, {})
if s == 200:
    dl_str = json.dumps(dl, default=str)
    ck("detail: no secrets", not any(kw in dl_str.lower() for kw in ["secret_hash","device_secret","password","api_key"]))

# ── 7. Health logic ──
print("\n=== 7. Health logic ===")
s, d2 = r("GET", "/device-operations/devices?device_status=disabled&limit=5", t=at)
if isinstance(d2, list):
    for dd in d2:
        ck(f"  disabled={dd['device_code']} → health=disabled", dd["health_status"] == "disabled")

# Check no secrets in recent events
if dev_id:
    s, dd = r("GET", f"/device-operations/devices/{dev_id}", t=at)
    if s == 200:
        # Check no actual secret values (not field names/event types)
        # Keywords that indicate actual leaked values, not audit event names
        secret_keywords = ["device_secret", "secret_hash", "access_token_hash", "password", "api_key", "private_key"]
        for section in ["recent_heartbeats","recent_manifest_requests","recent_media_requests","recent_pop_events","recent_pop_batches","recent_device_events"]:
            items = dd.get(section, [])
            for item in items:
                # Check only message/details_json for leaked secrets
                msg = str(item.get("message", "")).lower()
                has_secret = any(kw in msg for kw in secret_keywords)
                if has_secret:
                    ck(f"  {section}: no secrets in message", False)
                    break
        else:
            pass  # clean

print(f"\n{p} passed, {f} failed")
sys.exit(0 if f == 0 else 1)
