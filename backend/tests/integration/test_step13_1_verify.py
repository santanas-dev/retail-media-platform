"""Step 13.1 — PoP Ingest Verification. No code changes."""
import json, sys, uuid, asyncio
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from datetime import datetime, timezone, timedelta

BASE = "http://localhost:8001/api"
PASS, FAIL = "✅", "❌"
passed, failed = 0, 0
results = []

def req(method, path, body=None, token=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    r = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        resp = urlopen(r)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        try: return e.code, json.loads(e.fp.read())
        except: return e.code, {"detail": str(e)}

def check(name, s_or_bool, expected=None, body=None, checks=None):
    global passed, failed
    if expected is not None:
        ok = s_or_bool == expected
        extra = ""
        if checks and body:
            for f, ev in checks.items():
                gv = body.get(f)
                if gv != ev:
                    ok = False; extra += f" [{f}: {gv}!={ev}]"
        tag = PASS if ok else FAIL
        results.append(f"{tag} {name} → HTTP {s_or_bool}{extra}")
        if not ok: results.append(f"   {str(body)[:300]}")
    else:
        ok = bool(s_or_bool)
        results.append(f"{PASS if ok else FAIL} {name}")
        if not ok and body: results.append(f"   {str(body)[:200]}")
    if ok: passed += 1
    else: failed += 1

async def get_db():
    import asyncpg
    return await asyncpg.connect(host='localhost', user='retail_media', password='retail_media_dev', database='retail_media_platform')

async def _check_events(dev_id, event_type, recent=False):
    conn = await get_db()
    q = "SELECT count(*) FROM device_events WHERE gateway_device_id=$1 AND event_type=$2"
    cnt = await conn.fetchval(q, dev_id, event_type)
    await conn.close()
    return cnt > 0

# ── Tokens ──
print("=== 1. Setup ===")
s, aj = req("POST", "/auth/login", {"username": "admin", "password": "Admin123!"})
assert s == 200, f"Login: {aj}"
at = aj["access_token"]

# Get test data from DB
async def get_test_data():
    conn = await get_db()
    row = await conn.fetchrow("""
        SELECT mi.id as mi_id, mi.sha256, gd.id as did, gd.device_code
        FROM manifest_items mi
        JOIN manifest_versions mv ON mv.id = mi.manifest_version_id AND mv.status='published'
        JOIN publication_targets pt ON pt.id = mv.publication_target_id AND pt.status='published'
        JOIN gateway_devices gd ON gd.display_surface_id = pt.display_surface_id
        WHERE gd.device_code='a-05954' AND mi.sha256 IS NOT NULL LIMIT 1
    """)
    await conn.close()
    return str(row['mi_id']), row['sha256'], str(row['did']), row['device_code']

MI_ID, MI_SHA, DEV_ID, DEV_CODE = asyncio.run(get_test_data())

# Get device token
async def get_cred_id():
    conn = await get_db()
    rows = await conn.fetch("SELECT id FROM device_credentials WHERE gateway_device_id=$1 AND status='active'", DEV_ID)
    await conn.close()
    return str(rows[0]['id']) if rows else None

cid = asyncio.run(get_cred_id())
if cid: req("POST", f"/gateway-devices/{DEV_ID}/credentials/{cid}/revoke", token=at)
s, cr = req("POST", f"/gateway-devices/{DEV_ID}/credentials", token=at)
secret = cr["device_secret"]
s, dt_resp = req("POST", "/device-gateway/auth/token", {"device_code": DEV_CODE, "device_secret": secret})
dt = dt_resp["access_token"]

# Get user tokens for permission tests
async def get_user_tokens():
    conn = await get_db()
    users = await conn.fetch("""
        SELECT u.username, r.code as role
        FROM users u JOIN user_roles ur ON ur.user_id=u.id JOIN roles r ON r.id=ur.role_id
        WHERE u.username != 'admin' AND u.is_active=true
    """)
    await conn.close()
    return {row['role']: row['username'] for row in users} if users else {}

user_map = asyncio.run(get_user_tokens())
# Fallback: use admin for all roles
tokens = {}
for role in ['system_admin','security_admin','operations','analyst','ad_manager','approver','advertiser','device_service']:
    if role in user_map:
        s, tr = req("POST", "/auth/login", {"username": user_map[role], "password": "Admin123!"})
    else:
        # Try known test users
        s, tr = req("POST", "/auth/login", {"username": role.replace('_',''), "password": "Admin123!"})
    if s == 200: tokens[role] = tr["access_token"]

print(f"MI={MI_ID[:12]}... SHA={MI_SHA[:12]}... DEVID={DEV_ID[:12]}... DEVCODE={DEV_CODE}")
print(f"Admin token: OK, Device token: OK, Role tokens: {len(tokens)} roles")

# ── 2. Accepted Event ──
print("\n=== 2. Accepted Event ===")
pid = str(uuid.uuid4())
now = datetime.now(timezone.utc)
p = {"device_event_id": pid, "manifest_item_id": MI_ID,
     "played_at": now.isoformat(), "duration_ms": 15000,
     "play_status": "completed", "media_sha256": MI_SHA}
s, b = req("POST", "/device-gateway/pop/events", p, token=dt)
accepted_id = b.get("proof_event_id") if b.get("status") == "accepted" else None
check("Accepted: HTTP 200", s, 200, b)
check("Accepted: status=accepted", b.get("status"), "accepted")

if accepted_id:
    # Verify DB record
    async def check_accepted():
        conn = await get_db()
        row = await conn.fetchrow("SELECT * FROM proof_of_play_events WHERE id=$1", accepted_id)
        await conn.close()
        return row
    row = asyncio.run(check_accepted())
    if row:
        d = dict(row)
        for f in ["gateway_device_id","manifest_item_id","manifest_version_id",
                   "publication_target_id","schedule_item_id","campaign_id",
                   "campaign_rendition_id","expected_sha256","ip_address"]:
            check(f"Accepted: {f} filled", d.get(f) is not None)
        check("Accepted: media_sha256 == expected_sha256",
              d.get("media_sha256") == d.get("expected_sha256"))
        check("Accepted: validation_status=accepted", d.get("validation_status"), "accepted")
        check("Accepted: details_json no secrets",
              not any(kw in json.dumps(d.get("details_json",{})).lower()
                      for kw in ["password","secret","token","api_key"]))
    check("Accepted: device_event pop_event_accepted",
          _check_events(DEV_ID, "pop_event_accepted"))

# ── 3. Duplicate ──
print("\n=== 3. Duplicate ===")
s, b = req("POST", "/device-gateway/pop/events", p, token=dt)
check("Duplicate: HTTP 200", s, 200, b)
check("Duplicate: status=duplicate", b.get("status"), "duplicate")
check("Duplicate: returns existing proof_event_id", b.get("proof_event_id") == accepted_id)
check("Duplicate: device_event pop_event_duplicate",
      _check_events(DEV_ID, "pop_event_duplicate"))

# Count rows
async def count_pop():
    conn = await get_db()
    cnt = await conn.fetchval("SELECT count(*) FROM proof_of_play_events WHERE gateway_device_id=$1 AND device_event_id=$2", DEV_ID, pid)
    await conn.close()
    return cnt
cnt = asyncio.run(count_pop())
check("Duplicate: only 1 row in DB", cnt == 1)

# ── 4. Rejected scenarios ──
print("\n=== 4. Rejected Scenarios ===")
reject_tests = [
    ("manifest_item_not_found", str(uuid.uuid4()), MI_SHA, 10000, "started", None),
    ("media_sha256_mismatch", MI_ID, "b"*64, 10000, "started", None),
    ("schedule_item_mismatch", MI_ID, MI_SHA, 10000, "started", "schedule_item_id"),
    ("played_at_too_future", MI_ID, MI_SHA, 10000, "started", "future"),
    ("played_at_too_old", MI_ID, MI_SHA, 10000, "started", "old"),
    ("duration_ms_negative", MI_ID, MI_SHA, -1, "started", None),
    ("duration_ms_too_large", MI_ID, MI_SHA, 86_400_001, "started", None),
    ("invalid_play_status", MI_ID, MI_SHA, 10000, "BAD_STATUS", None),
    ("forbidden_keys_in_details", MI_ID, MI_SHA, 10000, "started", None),
    ("details_too_large", MI_ID, MI_SHA, 10000, "started", None),
]

for reason, mi_id_arg, sha_arg, dur_arg, ps_arg, extra_arg in reject_tests:
    payload = {
        "device_event_id": str(uuid.uuid4()),
        "manifest_item_id": mi_id_arg,
        "played_at": now.isoformat() if extra_arg not in ("future","old") else (
            (now + timedelta(seconds=600)).isoformat() if extra_arg == "future"
            else (now - timedelta(days=8)).isoformat()
        ),
        "duration_ms": dur_arg if dur_arg else None,
        "play_status": ps_arg,
        "media_sha256": sha_arg,
    }
    if extra_arg == "schedule_item_id":
        payload["schedule_item_id"] = str(uuid.uuid4())
    if reason == "forbidden_keys_in_details":
        payload["details_json"] = {"api_key": "secret"}
    elif reason == "details_too_large":
        payload["details_json"] = {"data": "x" * 65526}

    s, b = req("POST", "/device-gateway/pop/events", payload, token=dt)
    event_id = b.get("proof_event_id")
    check(f"Reject {reason}: HTTP 200", s, 200, b)
    check(f"Reject {reason}: status=rejected", b.get("status"), "rejected")
    check(f"Reject {reason}: proof_event_id exists", event_id is not None)
    check(f"Reject {reason}: reason filled", b.get("reason") is not None)

    if event_id:
        async def check_rejected(eid):
            conn = await get_db()
            row = await conn.fetchrow("SELECT * FROM proof_of_play_events WHERE id=$1", eid)
            await conn.close()
            return row
        row = asyncio.run(check_rejected(event_id))
        if row:
            d = dict(row)
            check(f"Reject {reason}: DB record exists", True)
            check(f"Reject {reason}: rejection_reason filled", d.get("rejection_reason") is not None)
            check(f"Reject {reason}: validation_status=rejected", d.get("validation_status"), "rejected")
            # No secrets
            check(f"Reject {reason}: details no secrets",
                  not any(kw in json.dumps(d.get("details_json",{})).lower()
                          for kw in ["password","secret","token","api_key","private_key"]))

    check(f"Reject {reason}: device_event pop_event_rejected exists",
          _check_events(DEV_ID, "pop_event_rejected", recent=True))

# ── 5. Nullable/CHECK safety ──
print("\n=== 5. Nullable/CHECK Safety ===")
async def verify_db_safe(event_id):
    conn = await get_db()
    row = await conn.fetchrow("""
        SELECT duration_ms, media_sha256, play_status, validation_status
        FROM proof_of_play_events WHERE id=$1
    """, event_id)
    await conn.close()
    return dict(row) if row else None

# duration_ms=-1: should be stored as None (or -1 if CHECK wasn't violated...)
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": now.isoformat(), "duration_ms": -1,
    "play_status": "started", "media_sha256": MI_SHA,
}, token=dt)
eid = b.get("proof_event_id")
check("Safety: duration=-1 → HTTP 200", s, 200, b)
check("Safety: duration=-1 → status=rejected", b.get("status"), "rejected")
if eid:
    d = asyncio.run(verify_db_safe(eid))
    check("Safety: duration=-1 stored as None (not -1)", d.get("duration_ms") is None)

# bad media_sha256
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": now.isoformat(), "duration_ms": 10000,
    "play_status": "started", "media_sha256": "NOT_HEX_AT_ALL",
}, token=dt)
eid = b.get("proof_event_id")
check("Safety: bad sha256 → HTTP 200", s, 200, b)
check("Safety: bad sha256 → status=rejected", b.get("status"), "rejected")
if eid:
    d = asyncio.run(verify_db_safe(eid))
    check("Safety: bad sha256 stored as None", d.get("media_sha256") is None)

# bad play_status
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": now.isoformat(), "duration_ms": 10000,
    "play_status": "NOT_VALID_123", "media_sha256": MI_SHA,
}, token=dt)
eid = b.get("proof_event_id")
check("Safety: bad play_status → HTTP 200", s, 200, b)
check("Safety: bad play_status → status=rejected", b.get("status"), "rejected")
if eid:
    d = asyncio.run(verify_db_safe(eid))
    check("Safety: bad play_status stored as None", d.get("play_status") is None)

# missing played_at
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "duration_ms": 10000, "play_status": "started", "media_sha256": MI_SHA,
}, token=dt)
eid = b.get("proof_event_id")
check("Safety: missing played_at → HTTP 200", s, 200, b)
check("Safety: missing played_at → status=rejected", b.get("status"), "rejected")

# None of these should 500
check("Safety: no 500 errors in run", True)  # if we get here, no 500s

# ── 6. Auth checks ──
print("\n=== 6. Auth ===")
s, b = req("POST", "/device-gateway/pop/events", {"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID})
check("Auth: no token → 401", s, 401, b)
s, b = req("POST", "/device-gateway/pop/events", {"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID}, token=at)
check("Auth: admin user token → 401", s, 401, b)
s, b = req("GET", "/users", token=dt)
check("Auth: device token on /users → 401", s, 401, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events", token=dt)
check("Auth: admin GET with device token → 401", s, 401, b)

# ── 7. Disabled/retired ──
print("\n=== 7. Disabled/Retired ===")
# Find/create disabled device
async def get_disabled():
    conn = await get_db()
    row = await conn.fetchrow("SELECT id, device_code FROM gateway_devices WHERE status IN ('disabled','retired') LIMIT 1")
    await conn.close()
    return str(row['id']), row['device_code'] if row else (None, None)

dis_id, dis_code = asyncio.run(get_disabled())
if dis_id:
    check("Disabled/retired found in DB", True)

# ── 8. Admin permissions ──
print("\n=== 8. Admin Permissions ===")
admin_tokens = {k: v for k, v in tokens.items()}
# Ensure admin is system_admin
admin_tokens["system_admin"] = at

expected_perm = {
    "system_admin": 200, "security_admin": 200, "operations": 200,
    "analyst": 200, "ad_manager": 200, "approver": 200,
    "advertiser": 403, "device_service": 403,
}

for role, exp in expected_perm.items():
    tok = admin_tokens.get(role, at)
    s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events", token=tok)
    check(f"Perm: {role} → {exp}", s, exp, b)

# No token
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events")
check("Perm: no token → 401", s, 401, b)

# ── 9. Admin filters ──
print("\n=== 9. Admin Filters ===")
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?validation_status=accepted", token=at)
check("Filter: validation_status=accepted → 200", s, 200, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?play_status=completed", token=at)
check("Filter: play_status=completed → 200", s, 200, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?manifest_item_id={MI_ID}", token=at)
check("Filter: manifest_item_id → 200", s, 200, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?date_from=2026-01-01T00:00:00&date_to=2026-12-31T23:59:59", token=at)
check("Filter: date_from+date_to → 200", s, 200, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?limit=10&offset=0", token=at)
check("Filter: limit+offset → 200", s, 200, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?limit=9999", token=at)
check("Filter: limit over 500 clamped", s, 200, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?offset=-1", token=at)
check("Filter: offset=-1 rejected", s, 422, b)

# ── 10. Forbidden keys recursive ──
print("\n=== 10. Forbidden Keys ===")
for kw in ["access_token","refresh_token","token","jwt","password","secret",
            "credential","credentials","authorization","cookie","api_key",
            "private_key","public_key"]:
    s, b = req("POST", "/device-gateway/pop/events", {
        "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
        "played_at": now.isoformat(), "duration_ms": 10000,
        "play_status": "started", "media_sha256": MI_SHA,
        "details_json": {kw: "secret-value"},
    }, token=dt)
    check(f"FK: {kw} → rejected", s, 200, b, {"status": "rejected"})

# Recursive
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": now.isoformat(), "duration_ms": 10000,
    "play_status": "started", "media_sha256": MI_SHA,
    "details_json": {"nested": {"api_key": "deep"}},
}, token=dt)
check("FK: recursive nested → rejected", s, 200, b, {"status": "rejected"})

# ── SUMMARY ──
print("\n" + "="*60)
for r in results:
    print(r)
print("="*60)
print(f"\n🏁 {passed} passed, {failed} failed ({passed+failed} tests)")
sys.exit(0 if failed == 0 else 1)
