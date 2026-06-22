"""Step 13 verification — PoP Ingest Core. Final version."""
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
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        resp = urlopen(r)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        try:
            return e.code, json.loads(e.fp.read())
        except Exception:
            return e.code, {"detail": str(e)}

def check(name, a, b=None, body=None, field_checks=None):
    global passed, failed
    # Two modes: (name, bool) or (name, status, expected)
    if b is None and field_checks is None:
        ok = bool(a)
        status_got = None
    else:
        status_got, expected = a, b
        ok = status_got == expected
    extra = ""
    if field_checks and body:
        for f, ev in field_checks.items():
            if body.get(f) != ev:
                ok = False
                extra += f" [{f}: got={body.get(f)}, expected={ev}]"
    tag = PASS if ok else FAIL
    if status_got is not None:
        results.append(f"{tag} {name} -> HTTP {status_got}{extra}")
    else:
        results.append(f"{tag} {name}")
    if not ok and body:
        results.append(f"   {str(body)[:300]}")
    if ok: passed += 1
    else: failed += 1

async def get_active_cred_id(dev_id):
    import asyncpg
    conn = await asyncpg.connect(host='localhost', user='retail_media', password='retail_media_dev', database='retail_media_platform')
    rows = await conn.fetch("SELECT id FROM device_credentials WHERE gateway_device_id = $1 AND status = 'active'", dev_id)
    await conn.close()
    return str(rows[0]['id']) if rows else None

async def get_test_data():
    import asyncpg
    conn = await asyncpg.connect(host='localhost', user='retail_media', password='retail_media_dev', database='retail_media_platform')
    row = await conn.fetchrow("""
        SELECT mi.id as mi_id, mi.sha256, gd.id as did, gd.device_code
        FROM manifest_items mi
        JOIN manifest_versions mv ON mv.id = mi.manifest_version_id AND mv.status = 'published'
        JOIN publication_targets pt ON pt.id = mv.publication_target_id AND pt.status = 'published'
        JOIN gateway_devices gd ON gd.display_surface_id = pt.display_surface_id
        WHERE gd.device_code = 'a-05954' AND mi.sha256 IS NOT NULL
        LIMIT 1
    """)
    await conn.close()
    if row:
        return str(row['mi_id']), row['sha256'], str(row['did']), row['device_code']
    return None, None, None, None

print("=== Setup ===")
MI_ID, MI_SHA, DEV_ID, DEV_CODE = asyncio.run(get_test_data())
assert all([MI_ID, MI_SHA, DEV_ID, DEV_CODE]), "No test data found"
print(f"MI: {MI_ID[:16]}... SHA: {MI_SHA[:16]}... Device: {DEV_CODE}")

# Admin login
s, aj = req("POST", "/auth/login", {"username": "admin", "password": "Admin123!"})
assert s == 200, f"Login: {aj}"
at = aj["access_token"]

# Get device token: if active cred exists, revoke it first
cred_id = asyncio.run(get_active_cred_id(DEV_ID))
if cred_id:
    print(f"Revoking cred {cred_id[:16]}...")
    req("POST", f"/gateway-devices/{DEV_ID}/credentials/{cred_id}/revoke", token=at)

s, cr = req("POST", f"/gateway-devices/{DEV_ID}/credentials", token=at)
assert s == 201, f"Cred create: {s} {cr}"
secret = cr["device_secret"]
s, dt_resp = req("POST", "/device-gateway/auth/token", {"device_code": DEV_CODE, "device_secret": secret})
assert s == 200, f"Device auth: {dt_resp}"
dt = dt_resp["access_token"]
print(f"Device token: OK")

# Verify manifest_item accessible
s, m = req("GET", "/device-gateway/manifest/current", token=dt)
print(f"Manifest: {m.get('status')}")

# ===== TESTS =====
print("\n======= Step 13 Tests =======\n")
accepted_event_id = None

# 01
s, b = req("POST", "/device-gateway/pop/events", {"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID})
check("01. No token -> 401", s, 401, b)

# 02
s, b = req("POST", "/device-gateway/pop/events", {"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID}, token=at)
check("02. Admin token -> 401", s, 401, b)

# 03 — valid
pid = str(uuid.uuid4())
p = {"device_event_id": pid, "manifest_item_id": MI_ID,
     "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 15000,
     "play_status": "completed", "media_sha256": MI_SHA}
s, b = req("POST", "/device-gateway/pop/events", p, token=dt)
if s == 200 and b.get("status") == "accepted":
    accepted_event_id = b.get("proof_event_id")
check("03. Valid PoP -> accepted", s, 200, b, {"status": "accepted"})

# 04 — duplicate
s, b = req("POST", "/device-gateway/pop/events", p, token=dt)
check("04. Duplicate -> duplicate", s, 200, b, {"status": "duplicate"})

# 05 — nonexistent mi
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": str(uuid.uuid4()),
    "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 10000,
    "play_status": "started", "media_sha256": "a" * 64,
}, token=dt)
check("05. Nonexistent mi -> rejected", s, 200, b, {"status": "rejected"})

# 06 — sha256 mismatch
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 10000,
    "play_status": "started", "media_sha256": "b" * 64,
}, token=dt)
check("06. sha256 mismatch -> rejected", s, 200, b, {"status": "rejected"})

# 07 — played_at too future
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": (datetime.now(timezone.utc) + timedelta(seconds=600)).isoformat(),
    "duration_ms": 10000, "play_status": "started", "media_sha256": MI_SHA,
}, token=dt)
check("07. played_at too future -> rejected", s, 200, b, {"status": "rejected"})

# 08 — played_at too old
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
    "duration_ms": 10000, "play_status": "started", "media_sha256": MI_SHA,
}, token=dt)
check("08. played_at too old -> rejected", s, 200, b, {"status": "rejected"})

# 09 — duration < 0
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": -1,
    "play_status": "started", "media_sha256": MI_SHA,
}, token=dt)
check("09. duration < 0 -> rejected", s, 200, b, {"status": "rejected"})

# 10 — duration > 24h
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 86_400_001,
    "play_status": "started", "media_sha256": MI_SHA,
}, token=dt)
check("10. duration > 24h -> rejected", s, 200, b, {"status": "rejected"})

# 11 — invalid play_status
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 10000,
    "play_status": "INVALID_ZZZ", "media_sha256": MI_SHA,
}, token=dt)
check("11. Invalid play_status -> rejected", s, 200, b, {"status": "rejected"})

# 12 — forbidden key
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 10000,
    "play_status": "started", "media_sha256": MI_SHA,
    "details_json": {"api_key": "leaked"},
}, token=dt)
check("12. Forbidden key -> rejected", s, 200, b, {"status": "rejected"})

# 13 — details too large
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 10000,
    "play_status": "started", "media_sha256": MI_SHA,
    "details_json": {"data": "x" * 65526},
}, token=dt)
check("13. details too large -> rejected", s, 200, b, {"status": "rejected"})

# 14-18: valid play_status values
for ps in ["started", "completed", "interrupted", "skipped", "failed"]:
    s, b = req("POST", "/device-gateway/pop/events", {
        "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
        "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 5000,
        "play_status": ps, "media_sha256": MI_SHA,
    }, token=dt)
    check(f"play_status={ps}", s, 200, b, {"status": "accepted"})

# Admin API
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events", token=at)
check("Admin GET -> 200", s, 200, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events")
check("Admin GET no token -> 401", s, 401, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events", token=dt)
check("Admin GET device token -> 401", s, 401, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?validation_status=accepted", token=at)
check("Admin filter status -> 200", s, 200, b)
s, b = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?play_status=completed", token=at)
check("Admin filter play_status -> 200", s, 200, b)

# Audit events
s, events = req("GET", f"/gateway-devices/{DEV_ID}/events", token=at)
etypes = [e.get("event_type") for e in events] if isinstance(events, list) else []
for t in ["pop_event_accepted", "pop_event_duplicate", "pop_event_rejected"]:
    check(f"Audit: {t}", t in etypes)

# Accepted event fields
if accepted_event_id:
    s, popl = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?validation_status=accepted&limit=1", token=at)
    if isinstance(popl, list) and popl:
        ev = popl[0]
        for f in ["manifest_version_id", "publication_target_id", "campaign_id", "expected_sha256", "ip_address"]:
            check(f"Field {f}", ev.get(f) is not None)
        ds = json.dumps(ev.get("details_json", {}))
        check("No secrets in details", not any(kw in ds.lower() for kw in ["password", "secret", "token", "api_key"]))

# Rejected event reason
s, popl = req("GET", f"/gateway-devices/{DEV_ID}/pop-events?validation_status=rejected&limit=1", token=at)
if isinstance(popl, list) and popl:
    check("Rejected has reason", bool(popl[0].get("rejection_reason")))

# Device token on human API
s, b = req("GET", "/users", token=dt)
check("Device token on /users -> 401", s, 401, b)

# Wrong schedule_item_id
s, b = req("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI_ID,
    "played_at": datetime.now(timezone.utc).isoformat(), "duration_ms": 5000,
    "play_status": "started", "media_sha256": MI_SHA,
    "schedule_item_id": str(uuid.uuid4()),
}, token=dt)
check("Wrong schedule_item_id -> rejected", s, 200, b, {"status": "rejected"})

# SUMMARY
print("\n" + "=" * 60)
for r in results:
    print(r)
print("=" * 60)
print(f"\n{passed} passed, {failed} failed ({passed+failed} tests)")
sys.exit(0 if failed == 0 else 1)
