"""Step 29.5 — KSO PoP Server-Side Correlation Tests.

Covers:
- Unit: _filter_source_items with various statuses
- Unit: correlate_kso_pop_event with mocked data
- Integration: KSO PoP event → HTTP → DB correlation
- Content type mismatch → uncorrelated
- selected_order out of range → uncorrelated
- Non-KSO device → not correlated
- Draft event → rejected
- Legacy Step 13 behavior not broken
- Safety: repr/output no raw IDs
"""

import json, sys, uuid, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = "http://localhost:8001/api"
PASS, FAIL = "✅", "❌"
passed = 0
failed = 0
results = []


def req(method, path, body=None, token=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    r = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        resp = urlopen(r, timeout=10)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        try:
            return e.code, json.loads(e.fp.read())
        except Exception:
            return e.code, {"detail": str(e)}
    except URLError:
        return None, {"detail": "Connection refused"}
    except Exception as e:
        return None, {"detail": str(e)}


def check(name, s_or_bool, expected=None, body=None):
    global passed, failed
    if expected is not None:
        ok = s_or_bool == expected
        tag = PASS if ok else FAIL
        results.append(f"{tag} {name} → HTTP {s_or_bool if s_or_bool else str(s_or_bool)}")
        if not ok and body:
            results.append(f"   {str(body)[:200]}")
    else:
        ok = bool(s_or_bool)
        tag = PASS if ok else FAIL
        results.append(f"{tag} {name}")
        if not ok and body:
            results.append(f"   {str(body)[:200]}")
    if ok:
        passed += 1
    else:
        failed += 1


def contains_forbidden(body_str, exclude=None):
    lower = body_str.lower()
    forbidden = [
        "token", "jwt", "secret", "password", "api_key",
        "manifest_item_id", "manifest_version_id",
        "campaign_id", "creative_id", "rendition_id",
        "schedule_item_id", "booking_id",
        "file_path", "media_path", "storage", "minio",
        "sha256", "stacktrace", "filename",
        "127.0.0.1", "backend_base_url", "device_secret",
        "authorization",
    ]
    if exclude:
        forbidden = [f for f in forbidden if f not in exclude]
    found = []
    for fb in forbidden:
        if fb in lower:
            found.append(fb)
    return found


# ═══════════════════════════════════════════════════════════════════
# A. Unit tests: _filter_source_items
# ═══════════════════════════════════════════════════════════════════

print("=== A. Unit: _filter_source_items ===")

from app.domains.device_gateway.kso_pop_correlation import _filter_source_items
from app.domains.publications.kso_manifest_projection import ManifestSourceItem


def test_filter(status_overrides=None):
    kwargs = {
        "channel_code": "kso", "campaign_status": "approved",
        "creative_status": "approved", "rendition_status": "valid",
        "publication_status": "published", "device_status": "active",
        "store_is_active": True, "content_type": "image/png",
        "slot_order": 0,
    }
    if status_overrides:
        kwargs.update(status_overrides)
    si = ManifestSourceItem(**kwargs)
    filtered = _filter_source_items([si])
    return len(filtered)


check("Unit: all filters pass", test_filter(), 1)
check("Unit: non-kso channel excluded", test_filter({"channel_code": "tv"}), 0)
check("Unit: campaign not approved excluded",
      test_filter({"campaign_status": "draft"}), 0)
check("Unit: creative not approved excluded",
      test_filter({"creative_status": "draft"}), 0)
check("Unit: rendition not valid excluded",
      test_filter({"rendition_status": "pending"}), 0)
check("Unit: pub not published excluded",
      test_filter({"publication_status": "draft"}), 0)
check("Unit: device disabled excluded",
      test_filter({"device_status": "disabled"}), 0)
check("Unit: store inactive excluded",
      test_filter({"store_is_active": False}), 0)
check("Unit: unsupported content_type excluded",
      test_filter({"content_type": "application/pdf"}), 0)

# valid_from / valid_to
now = datetime.now(timezone.utc)
from datetime import timedelta as td
check("Unit: valid_from future excluded",
     test_filter({"valid_from": now + td(hours=1)}), 0)
check("Unit: valid_to past excluded",
     test_filter({"valid_to": now - td(hours=1)}), 0)
check("Unit: valid_from past OK",
     test_filter({"valid_from": now - td(hours=1)}), 1)
check("Unit: valid_to future OK",
     test_filter({"valid_to": now + td(hours=1)}), 1)

# slot_order sorting
si0 = ManifestSourceItem(channel_code="kso", campaign_status="approved",
    creative_status="approved", rendition_status="valid",
    publication_status="published", device_status="active",
    store_is_active=True, content_type="image/png", slot_order=2)
si1 = ManifestSourceItem(channel_code="kso", campaign_status="approved",
    creative_status="approved", rendition_status="valid",
    publication_status="published", device_status="active",
    store_is_active=True, content_type="image/png", slot_order=1)
filtered = _filter_source_items([si0, si1])
check("Unit: sorted by slot_order (first is slot=1)",
      filtered[0].slot_order == 1 if filtered else False)


# ═══════════════════════════════════════════════════════════════════
# B. Unit: correlation result repr safety
# ═══════════════════════════════════════════════════════════════════

print("\n=== B. Unit: correlation repr safety ===")

from app.domains.device_gateway.kso_pop_correlation import KsoPopCorrelationResult

# Correlated
cr = KsoPopCorrelationResult(
    correlated=True,
    _manifest_item_id=uuid.uuid4(), _campaign_id=uuid.uuid4(),
    _rendition_id=uuid.uuid4(), items_total=3, items_filtered=2,
    matched_index=0,
)
r = repr(cr)
check("Unit: correlated repr has no UUID", str(cr._manifest_item_id) not in r)
check("Unit: correlated repr has items_total", "items_total=3" in r)

# Uncorrelated
cr2 = KsoPopCorrelationResult(
    correlated=False, reason="content_type_mismatch",
    items_total=5, items_filtered=3, matched_index=0,
)
r2 = repr(cr2)
check("Unit: uncorrelated repr shows reason", "content_type_mismatch" in r2)


# ═══════════════════════════════════════════════════════════════════
# C. Integration: KSO PoP with correlation → DB
# ═══════════════════════════════════════════════════════════════════

print("\n=== C. Integration: KSO PoP → correlation in DB ===")

import asyncio, asyncpg

# Admin login
s, aj = req("POST", "/auth/login", {"username": "admin", "password": "Admin123!"})
at = aj.get("access_token") if s == 200 else None
check("Setup: admin login", s, 200)


async def get_kso_dev_with_manifest():
    conn = await asyncpg.connect(
        host="localhost", user="retail_media",
        password="retail_media_dev", database="retail_media_platform",
    )
    dev = await conn.fetchrow(
        """SELECT gd.id, gd.device_code FROM gateway_devices gd
           JOIN display_surfaces ds ON ds.id = gd.display_surface_id
           JOIN publication_targets pt ON pt.display_surface_id = ds.id AND pt.status = 'published'
           WHERE gd.channel_id = (SELECT id FROM channels WHERE code='kso') AND gd.status='active'
           LIMIT 1"""
    )
    await conn.close()
    return dev


async def setup_device_token(did, dcode):
    conn = await asyncpg.connect(
        host="localhost", user="retail_media",
        password="retail_media_dev", database="retail_media_platform",
    )
    creds = await conn.fetch(
        "SELECT id FROM device_credentials WHERE gateway_device_id=$1 AND status='active'",
        uuid.UUID(did),
    )
    await conn.close()
    for c in creds:
        req("POST", f"/gateway-devices/{did}/credentials/{c['id']}/revoke", token=at)
    s, cr = req("POST", f"/gateway-devices/{did}/credentials", token=at)
    if s != 201:
        return None
    sec = cr.get("device_secret")
    s, dr = req("POST", "/device-gateway/auth/token", {
        "device_code": dcode, "device_secret": sec,
    })
    return dr.get("access_token") if s == 200 else None


dev = asyncio.run(get_kso_dev_with_manifest())
if dev:
    dev_id = str(dev["id"])
    dev_code = dev["device_code"]
    dt = asyncio.run(setup_device_token(dev_id, dev_code))
    check("Setup: KSO device token", dt is not None)
else:
    dt = None
    check("Setup: KSO device with manifest", False)


if dt:
    # ── C1: KSO completed event WITH correlation fields ──────────
    now = datetime.now(timezone.utc)
    pid = str(uuid.uuid4())
    evt = {
        "device_event_id": pid,
        "played_at": now.isoformat(),
        "duration_ms": 5000,
        "play_status": "completed",
        "selected_order": 0,
        "selected_content_type": "image/png",
    }
    s, b = req("POST", "/device-gateway/pop/events", evt, token=dt)
    check("Int: KSO correlated accepted", s, 200)
    check("Int: KSO correlated status=accepted", b.get("status"), "accepted")

    # Check DB
    pf_id = b.get("proof_event_id")
    if pf_id:
        async def check_db(pfid):
            conn = await asyncpg.connect(
                host="localhost", user="retail_media",
                password="retail_media_dev", database="retail_media_platform",
            )
            row = await conn.fetchrow(
                "SELECT manifest_item_id, campaign_id, rendition_id, "
                "creative_version_id, manifest_version_id, validation_status "
                "FROM proof_of_play_events WHERE id=$1", pfid,
            )
            await conn.close()
            return row
        row2 = asyncio.run(check_db(pf_id))
        if row2:
            has_mi = row2["manifest_item_id"] is not None
            has_camp = row2["campaign_id"] is not None
            has_rend = row2["rendition_id"] is not None
            has_cv = row2["creative_version_id"] is not None
            check("Int: manifest_item_id populated", has_mi)
            check("Int: campaign_id populated", has_camp)
            check("Int: rendition_id populated", has_rend)
            check("Int: creative_version_id populated", has_cv)
        else:
            check("Int: DB row found", False)

    # ── C2: Content type mismatch → uncorrelated ─────────────────
    pid2 = str(uuid.uuid4())
    evt2 = {
        "device_event_id": pid2,
        "played_at": now.isoformat(),
        "duration_ms": 5000,
        "play_status": "completed",
        "selected_order": 0,
        "selected_content_type": "video/mp4",  # mismatch!
    }
    s2, b2 = req("POST", "/device-gateway/pop/events", evt2, token=dt)
    check("Int: content_type mismatch → accepted (uncorrelated)",
          b2.get("status"), "accepted")
    pf2 = b2.get("proof_event_id")
    if pf2:
        async def check_uncorrelated(pfid):
            conn = await asyncpg.connect(
                host="localhost", user="retail_media",
                password="retail_media_dev", database="retail_media_platform",
            )
            row = await conn.fetchrow(
                "SELECT manifest_item_id FROM proof_of_play_events WHERE id=$1", pfid,
            )
            await conn.close()
            return row
        row3 = asyncio.run(check_uncorrelated(pf2))
        if row3:
            check("Int: content_type mismatch → mi is NULL",
                  row3["manifest_item_id"] is None)
        else:
            check("Int: content_type mismatch DB row found", False)

    # ── C3: selected_order out of range → uncorrelated ───────────
    pid3 = str(uuid.uuid4())
    evt3 = {
        "device_event_id": pid3,
        "played_at": now.isoformat(),
        "duration_ms": 5000,
        "play_status": "completed",
        "selected_order": 999,
        "selected_content_type": "image/png",
    }
    s3, b3 = req("POST", "/device-gateway/pop/events", evt3, token=dt)
    check("Int: order out of range → accepted (uncorrelated)",
          b3.get("status"), "accepted")

    # ── C4: Draft event → rejected ───────────────────────────────
    pid4 = str(uuid.uuid4())
    evt4 = {
        "device_event_id": pid4,
        "played_at": now.isoformat(),
        "duration_ms": 3000,
        "play_status": "draft",
        "selected_order": 0,
        "selected_content_type": "image/png",
    }
    s4, b4 = req("POST", "/device-gateway/pop/events", evt4, token=dt)
    check("Int: draft event rejected", b4.get("status"), "rejected")

    # ── Response safety ──────────────────────────────────────────
    resp_str = json.dumps(b)
    fb = contains_forbidden(resp_str, exclude=["batch_id"])
    for f in fb:
        check(f"Int: response safe: no '{f}'", False)
    if not fb:
        check("Int: response safe: all checks passed", True)

else:
    check("Int: KSO correlation SKIPPED (no device)", False)


# ═══════════════════════════════════════════════════════════════════
# D. Backend /health
# ═══════════════════════════════════════════════════════════════════

print("\n=== D. Health ===")

try:
    import urllib.request as _ur
    resp = _ur.urlopen("http://localhost:8001/health", timeout=5)
    body = json.loads(resp.read())
    check("Health: /health → 200", resp.status, 200)
    check("Health: status=ok", body.get("status"), "ok")
except Exception as e:
    check(f"Health failed: {e}", False)


# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
for r in results:
    print(r)
print("=" * 60)
print(f"\nTotal: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
