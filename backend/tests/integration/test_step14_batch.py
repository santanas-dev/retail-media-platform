"""Step 14 — PoP Batch Ingest verification."""
import json, sys, uuid, asyncio
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from datetime import datetime, timezone, timedelta

BASE = "http://localhost:8001/api"
PASS, FAIL = "✅", "❌"
passed, failed = 0, 0
results = []

def r(m, p, b=None, t=None):
    url = f"{BASE}{p}"
    data = json.dumps(b).encode() if b else None
    req = Request(url, data=data, method=m, headers={"Content-Type": "application/json"})
    if t: req.add_header("Authorization", f"Bearer {t}")
    try:
        resp = urlopen(req)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        try: return e.code, json.loads(e.fp.read())
        except: return e.code, {"detail": str(e)}

def ck(name, a, b=None, body=None, chk=None):
    global passed, failed
    if b is not None:
        ok = a == b; e = ""
        if chk and body:
            for f, ev in chk.items():
                if body.get(f) != ev: ok = False; e += f" [{f}:{body.get(f)}!={ev}]"
        tag = PASS if ok else FAIL
        results.append(f"{tag} {name} → HTTP {a}{e}")
        if not ok: results.append(f"   {str(body)[:300]}")
    else:
        ok = bool(a)
        results.append(f"{PASS if ok else FAIL} {name}")
        if not ok and body: results.append(f"   {str(body)[:200]}")
    if ok: passed += 1
    else: failed += 1

async def db():
    import asyncpg
    return await asyncpg.connect(host='localhost', user='retail_media', password='retail_media_dev', database='retail_media_platform')

print("=== Setup ===")
_, aj = r("POST", "/auth/login", {"username": "admin", "password": "Admin123!"})
at = aj["access_token"]

async def td():
    c = await db()
    row = await c.fetchrow("""
        SELECT mi.id mi_id, mi.sha256, gd.id did, gd.device_code
        FROM manifest_items mi
        JOIN manifest_versions mv ON mv.id=mi.manifest_version_id AND mv.status='published'
        JOIN publication_targets pt ON pt.id=mv.publication_target_id AND pt.status='published'
        JOIN gateway_devices gd ON gd.display_surface_id=pt.display_surface_id
        WHERE gd.device_code='a-05954' AND mi.sha256 IS NOT NULL LIMIT 1""")
    await c.close()
    return str(row['mi_id']), row['sha256'], str(row['did']), row['device_code']

MI, SHA, DID, DC = asyncio.run(td())
print(f"MI={MI[:12]}... DID={DID[:12]}...")

# Get device token
async def gc():
    c = await db()
    row = await c.fetchrow("SELECT id FROM device_credentials WHERE gateway_device_id=$1 AND status='active'", DID)
    await c.close()
    return str(row['id']) if row else None

cid = asyncio.run(gc())
if cid: r("POST", f"/gateway-devices/{DID}/credentials/{cid}/revoke", t=at)
_, cr = r("POST", f"/gateway-devices/{DID}/credentials", t=at)
dt = r("POST", "/device-gateway/auth/token", {"device_code": DC, "device_secret": cr["device_secret"]})[1]["access_token"]
print("Device token: OK")

now = datetime.now(timezone.utc)

# ── 1. Single-event still works ──
print("\n=== 1. Single-event regression ===")
s, b = r("POST", "/device-gateway/pop/events", {
    "device_event_id": str(uuid.uuid4()), "manifest_item_id": MI,
    "played_at": now.isoformat(), "duration_ms": 10000,
    "play_status": "started", "media_sha256": SHA,
}, t=dt)
ck("Single-event accepted", s, 200, b, {"status": "accepted"})

# ── 2. Normal batch: mixed accepted+rejected ──
print("\n=== 2. Normal batch ===")
BID = str(uuid.uuid4())
e1, e2, e3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
s, b = r("POST", "/device-gateway/pop/events/batch", {
    "batch_id": BID, "sent_at": now.isoformat(),
    "events": [
        {"device_event_id": e1, "manifest_item_id": MI, "played_at": now.isoformat(),
         "duration_ms": 15000, "play_status": "completed", "media_sha256": SHA},
        {"device_event_id": e2, "manifest_item_id": MI, "played_at": now.isoformat(),
         "duration_ms": 10000, "play_status": "started", "media_sha256": "b" * 64},
        {"device_event_id": e3, "manifest_item_id": MI, "played_at": now.isoformat(),
         "duration_ms": 5000, "play_status": "started", "media_sha256": SHA},
    ]
}, t=dt)
ck("HTTP 200", s, 200, b)
ck("status=partially_processed", b.get("status"), "partially_processed")
summary = b.get("summary", {})
ck("total=3", summary.get("total"), 3)
ck("accepted=2", summary.get("accepted"), 2)
ck("rejected=1", summary.get("rejected"), 1)
ck("duplicate=0", summary.get("duplicate"), 0)
ck("results count=3", len(b.get("results", [])), 3)
PBI = b.get("proof_batch_id")
ck("proof_batch_id set", PBI is not None)

# Verify DB
async def ckdb(pbid):
    c = await db()
    b_row = await c.fetchrow("SELECT * FROM proof_of_play_batches WHERE id=$1", pbid)
    evs = await c.fetch("SELECT * FROM proof_of_play_events WHERE batch_id=$1", pbid)
    await c.close()
    return b_row, evs

brow, evs = asyncio.run(ckdb(PBI))
ck("DB: batch exists", brow is not None)
d = dict(brow)
ck("DB: total_events=3", d.get("total_events"), 3)
ck("DB: accepted=2", d.get("accepted_count"), 2)
ck("DB: rejected=1", d.get("rejected_count"), 1)
ck("DB: events=3", len(evs), 3)
ck("DB: batch_id on events", all(str(e['batch_id']) == PBI for e in evs))

# ── 3. Duplicate batch ──
print("\n=== 3. Duplicate batch ===")
s, b = r("POST", "/device-gateway/pop/events/batch", {
    "batch_id": BID, "sent_at": now.isoformat(), "events": [
        {"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI,
         "played_at": now.isoformat(), "duration_ms": 10000,
         "play_status": "started", "media_sha256": SHA},
    ]
}, t=dt)
ck("Dup: HTTP 200", s, 200, b)
ck("Dup: status=duplicate_batch", b.get("status"), "duplicate_batch")
ck("Dup: proof_batch_id matches", b.get("proof_batch_id"), PBI)

async def cnt_batches(bid):
    c = await db()
    n = await c.fetchval("SELECT count(*) FROM proof_of_play_batches WHERE device_batch_id=$1", bid)
    await c.close()
    return n
ck("Dup: only 1 batch row", asyncio.run(cnt_batches(BID)) == 1)

# ── 4. In-batch duplicate ──
print("\n=== 4. In-batch duplicate ===")
did = str(uuid.uuid4())
s, b = r("POST", "/device-gateway/pop/events/batch", {
    "batch_id": str(uuid.uuid4()), "events": [
        {"device_event_id": did, "manifest_item_id": MI, "played_at": now.isoformat(),
         "duration_ms": 10000, "play_status": "started", "media_sha256": SHA},
        {"device_event_id": did, "manifest_item_id": MI, "played_at": now.isoformat(),
         "duration_ms": 10000, "play_status": "started", "media_sha256": SHA},
    ]
}, t=dt)
ck("In-batch: first accepted", b["results"][0]["status"], "accepted")
ck("In-batch: second duplicate", b["results"][1]["status"], "duplicate")
ck("In-batch: accepted=1", b["summary"]["accepted"], 1)
ck("In-batch: duplicate=1", b["summary"]["duplicate"], 1)

# ── 5. Cross-batch duplicate ──
print("\n=== 5. Cross-batch duplicate ===")
s, b = r("POST", "/device-gateway/pop/events/batch", {
    "batch_id": str(uuid.uuid4()), "events": [
        {"device_event_id": e1, "manifest_item_id": MI, "played_at": now.isoformat(),
         "duration_ms": 10000, "play_status": "started", "media_sha256": SHA},
    ]
}, t=dt)
ck("X-batch: duplicate", b["results"][0]["status"], "duplicate")
ck("X-batch: rejected batch", b["status"], "rejected")

# ── 6. Chujoy / wrong manifest ──
print("\n=== 6. Wrong manifest ===")
s, b = r("POST", "/device-gateway/pop/events/batch", {
    "batch_id": str(uuid.uuid4()), "events": [
        {"device_event_id": str(uuid.uuid4()), "manifest_item_id": str(uuid.uuid4()),
         "played_at": now.isoformat(), "duration_ms": 10000, "play_status": "started",
         "media_sha256": "a" * 64},
    ]
}, t=dt)
ck("Wrong MI: rejected", b["results"][0]["status"], "rejected")

# ── 7. Auth ──
print("\n=== 7. Auth ===")
s, b = r("POST", "/device-gateway/pop/events/batch", {"batch_id": str(uuid.uuid4()), "events": [{"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI}]})
ck("No token → 401", s, 401, b)
s, b = r("POST", "/device-gateway/pop/events/batch", {"batch_id": str(uuid.uuid4()), "events": []}, t=dt)
ck("Empty events → 422", s, 422, b)

# ── 8. Limits ──
print("\n=== 8. Limits ===")
many = []
for i in range(501):
    many.append({"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI,
                 "played_at": now.isoformat(), "duration_ms": 10000,
                 "play_status": "started", "media_sha256": SHA})
s, b = r("POST", "/device-gateway/pop/events/batch", {"batch_id": str(uuid.uuid4()), "events": many}, t=dt)
ck("501 events → 400", s, 400, b)

big = {"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI,
       "played_at": now.isoformat(), "duration_ms": 10000, "play_status": "started",
       "media_sha256": SHA, "details_json": {"pad": "x" * 2_100_000}}
s, b = r("POST", "/device-gateway/pop/events/batch", {"batch_id": str(uuid.uuid4()), "events": [big]}, t=dt)
ck(">2MB → 413", s, 413, b)

# ── 9. Forbidden in batch.details ──
print("\n=== 9. Forbidden keys ===")
s, b = r("POST", "/device-gateway/pop/events/batch", {
    "batch_id": str(uuid.uuid4()), "details_json": {"api_key": "leaked"},
    "events": [{"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI,
                "played_at": now.isoformat(), "duration_ms": 10000,
                "play_status": "started", "media_sha256": SHA}]
}, t=dt)
ck("Batch FK: → 400", s, 400, b)

# ── 10. Admin ──
print("\n=== 10. Admin ===")
s, b = r("GET", f"/gateway-devices/{DID}/pop-batches", t=at)
ck("GET pop-batches → 200", s, 200, b)
s, b = r("GET", f"/gateway-devices/{DID}/pop-batches")
ck("No token → 401", s, 401, b)
s, b = r("GET", f"/gateway-devices/{DID}/pop-batches", t=dt)
ck("Device token → 401", s, 401, b)
s, b = r("GET", f"/gateway-devices/{DID}/pop-batches?batch_status=partially_processed", t=at)
ck("Filter batch_status → 200", s, 200, b)
s, b = r("GET", f"/gateway-devices/{DID}/pop-events?batch_id={PBI}", t=at)
ck("Filter pop-events by batch_id → 200", s, 200, b)
ck("Has events", isinstance(b, list) and len(b) > 0)

# ── 11. All accepted → processed ──
print("\n=== 11. processed status ===")
s, b = r("POST", "/device-gateway/pop/events/batch", {
    "batch_id": str(uuid.uuid4()), "events": [
        {"device_event_id": str(uuid.uuid4()), "manifest_item_id": MI,
         "played_at": now.isoformat(), "duration_ms": 10000,
         "play_status": "started", "media_sha256": SHA},
    ]
}, t=dt)
ck("All accepted → processed", b.get("status"), "processed")

# ── 12. All duplicate → rejected ──
print("\n=== 12. rejected status ===")
oe1, oe2 = str(uuid.uuid4()), str(uuid.uuid4())
for oe in [oe1, oe2]:
    r("POST", "/device-gateway/pop/events", {
        "device_event_id": oe, "manifest_item_id": MI,
        "played_at": now.isoformat(), "duration_ms": 10000,
        "play_status": "started", "media_sha256": SHA,
    }, t=dt)
s, b = r("POST", "/device-gateway/pop/events/batch", {
    "batch_id": str(uuid.uuid4()), "events": [
        {"device_event_id": oe1, "manifest_item_id": MI, "played_at": now.isoformat(),
         "duration_ms": 10000, "play_status": "started", "media_sha256": SHA},
        {"device_event_id": oe2, "manifest_item_id": MI, "played_at": now.isoformat(),
         "duration_ms": 10000, "play_status": "started", "media_sha256": SHA},
    ]
}, t=dt)
ck("All dup → rejected", b.get("status"), "rejected")
ck("duplicate=2", b["summary"]["duplicate"], 2)

# ── 13. Audit ──
print("\n=== 13. Audit ===")
s, evs = r("GET", f"/gateway-devices/{DID}/events", t=at)
ets = [e.get("event_type") for e in evs] if isinstance(evs, list) else []
for t in ["pop_batch_processed", "pop_batch_duplicate", "pop_batch_rejected"]:
    ck(f"event_type: {t}", t in ets)

# ── 14. Security ──
print("\n=== 14. Security ===")
s, pl = r("GET", f"/gateway-devices/{DID}/pop-events?batch_id={PBI}", t=at)
if isinstance(pl, list):
    for ev in pl:
        ds = json.dumps(ev.get("details_json", {}))
        clean = not any(kw in ds.lower() for kw in ["password", "secret", "token", "api_key"])
        ck(f"Event details clean", clean)

# ── 15. ip_address ──
if isinstance(pl, list) and pl:
    ck("ip_address filled", pl[0].get("ip_address") is not None)

# ── SUMMARY ──
print("\n" + "=" * 60)
for r_ in results:
    print(r_)
print("=" * 60)
print(f"\n🏁 {passed} passed, {failed} failed ({passed+failed} tests)")
sys.exit(0 if failed == 0 else 1)
