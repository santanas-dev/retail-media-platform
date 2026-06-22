"""Step 28.7 — KSO media delivery endpoint integration test.

Verifies:
- media/kso/{mediaRef} endpoint error handling (no auth)
- Forbidden fields in error responses
- mediaRef validation (unit)
- Resolver integration (unit)
- Consistency: projection ↔ resolver roundtrip

No external dependencies needed for pure tests.
HTTP tests require running backend — gracefully skipped.
"""

import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "http://localhost:8001/api"

PASS = "✅"
FAIL = "❌"
passed = 0
failed = 0
results = []


def r(path, token=None):
    url = f"{BASE}{path}"
    req = Request(url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers, resp.read()
    except HTTPError as e:
        return e.code, e.headers, e.read()
    except URLError:
        return None, None, None
    except Exception:
        return None, None, None


def check(name, condition, detail=""):
    global passed, failed, results
    if condition:
        passed += 1
        results.append(f"{PASS} {name}")
    else:
        failed += 1
        results.append(f"{FAIL} {name}")
        if detail:
            results.append(f"   Detail: {detail}")


# ══════════════════════════════════════════════════════════════════════
# Forbidden substrings in error responses
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_IN_ERROR = frozenset({
    "rendition_id", "creative_id", "campaign_id",
    "manifest_item_id", "schedule_item_id", "batch_id",
    "storage_key", "minio", "s3://", "bucket",
    "file_path", "media_path", "creatives/",
    "sha256", "streaxcept", "Traceback",
    "token", "secret", "password",
    "stacktrace", "127.0.0.1",
})


def _check_error_safety(response_text, label):
    lower = response_text.lower()
    for fb in FORBIDDEN_IN_ERROR:
        check(
            f"{label}: no '{fb}' in error response",
            fb not in lower,
            f"found '{fb}' in: {response_text[:150]}"
        )


# ══════════════════════════════════════════════════════════════════════
# HTTP Tests (skip if backend not running)
# ══════════════════════════════════════════════════════════════════════

status, headers, body = r("/device-gateway/media/kso/media/current/slot-000")

if status is None:
    results.append("ℹ️  Backend not reachable — skipping HTTP tests")
else:
    body_text = body.decode() if body else ""

    check("unauth KSO media → 401", status == 401,
          f"got {status}, body: {body_text[:100]}")
    _check_error_safety(body_text, "unauth KSO")

    # Test unsafe mediaRef (should be rejected before auth if strictly routed,
    # but our router authenticates first — so still 401 for invalid mediaRef)
    status2, h2, b2 = r("/device-gateway/media/kso/../etc/passwd")
    check("path traversal → rejected", status2 in (401, 404, 403),
          f"got {status2}")


# ══════════════════════════════════════════════════════════════════════
# Resolver Unit Tests (pure, no backend needed)
# ══════════════════════════════════════════════════════════════════════

from app.domains.publications.kso_media_ref_resolver import (
    KsoMediaRefSourceItem,
    resolve_kso_media_ref_source,
    _validate_media_ref_slot,
    STATUS_OK, STATUS_ERROR, STATUS_NOT_FOUND,
    REASON_RESOLVED, REASON_NOT_FOUND,
    REASON_UNSAFE_MEDIA_REF, REASON_NO_VALID_ITEMS,
)

from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 6, 19, 10, 0, 0, tzinfo=timezone.utc)
RID = "11111111-1111-1111-1111-111111111111"


def _make_item(**kw):
    defaults = dict(
        channel_code="kso", campaign_status="approved",
        creative_status="approved", rendition_status="valid",
        publication_status="published", device_status="active",
        store_is_active=True, store_code="s1", device_code="d1",
        content_type="image/png", duration_ms=5000, slot_order=0,
        internal_source_rendition_id=RID,
    )
    defaults.update(kw)
    return KsoMediaRefSourceItem(**defaults)


# ── Basic resolution ───────────────────────────────────────────────

r0 = resolve_kso_media_ref_source([_make_item()], "media/current/slot-000", NOW)
check("resolver: valid slot-000 → ok", r0.status == STATUS_OK)
check("resolver: valid slot-000 → resolved", r0.resolved)
check("resolver: internal source accessible",
      r0._internal_source_rendition_id == RID)
check("resolver: repr hides internal source", RID not in repr(r0))
check("resolver: content_type correct", r0.content_type == "image/png")

# ── Out of range ───────────────────────────────────────────────────

r1 = resolve_kso_media_ref_source([_make_item()], "media/current/slot-999", NOW)
check("resolver: out-of-range → not_found", r1.status == STATUS_NOT_FOUND)
check("resolver: not_found reason", r1.reason == REASON_NOT_FOUND)

# ── Unsafe mediaRef ────────────────────────────────────────────────

r2 = resolve_kso_media_ref_source([_make_item()], "../etc/passwd", NOW)
check("resolver: path traversal → error", r2.status == STATUS_ERROR)
check("resolver: traversal reason", r2.reason == REASON_UNSAFE_MEDIA_REF)

r3 = resolve_kso_media_ref_source([_make_item()], "http://x.com/slot-000", NOW)
check("resolver: URL → error", r3.status == STATUS_ERROR)

r4 = resolve_kso_media_ref_source([_make_item()], "/media/current/slot-000", NOW)
check("resolver: absolute → error", r4.status == STATUS_ERROR)

# ── MediaRef validator ─────────────────────────────────────────────

check("validator: slot-000 → 0", _validate_media_ref_slot("media/current/slot-000") == 0)
check("validator: slot-001 → 1", _validate_media_ref_slot("media/current/slot-001") == 1)
check("validator: ../ → None", _validate_media_ref_slot("../etc/passwd") is None)
check("validator: http → None", _validate_media_ref_slot("http://x.com/slot-000") is None)

# ── Filter tests ───────────────────────────────────────────────────

r5 = resolve_kso_media_ref_source(
    [_make_item(campaign_status="draft")], "media/current/slot-000", NOW)
check("filter: inactive campaign → excluded", r5.reason == REASON_NO_VALID_ITEMS)

r6 = resolve_kso_media_ref_source(
    [_make_item(creative_status="pending")], "media/current/slot-000", NOW)
check("filter: non-approved creative → excluded", r6.reason == REASON_NO_VALID_ITEMS)

r7 = resolve_kso_media_ref_source(
    [_make_item(rendition_status="invalid")], "media/current/slot-000", NOW)
check("filter: invalid rendition → excluded", r7.reason == REASON_NO_VALID_ITEMS)

r8 = resolve_kso_media_ref_source(
    [_make_item(publication_status="draft")], "media/current/slot-000", NOW)
check("filter: draft publication → excluded", r8.reason == REASON_NO_VALID_ITEMS)

r9 = resolve_kso_media_ref_source(
    [_make_item(content_type="application/pdf")], "media/current/slot-000", NOW)
check("filter: unsupported MIME → excluded", r9.reason == REASON_NO_VALID_ITEMS)

r10 = resolve_kso_media_ref_source(
    [_make_item(store_is_active=False)], "media/current/slot-000", NOW)
check("filter: inactive store → excluded", r10.reason == REASON_NO_VALID_ITEMS)

r11 = resolve_kso_media_ref_source(
    [_make_item(device_status="disabled")], "media/current/slot-000", NOW)
check("filter: disabled device → excluded", r11.reason == REASON_NO_VALID_ITEMS)

# ── Multiple items sorting ─────────────────────────────────────────

items_multi = [
    _make_item(slot_order=2, internal_source_rendition_id="ccc"),
    _make_item(slot_order=0, internal_source_rendition_id="aaa"),
    _make_item(slot_order=1, internal_source_rendition_id="bbb"),
]
r12 = resolve_kso_media_ref_source(items_multi, "media/current/slot-000", NOW)
check("sort: slot-000 → aaa", r12._internal_source_rendition_id == "aaa")
r13 = resolve_kso_media_ref_source(items_multi, "media/current/slot-001", NOW)
check("sort: slot-001 → bbb", r13._internal_source_rendition_id == "bbb")
r14 = resolve_kso_media_ref_source(items_multi, "media/current/slot-002", NOW)
check("sort: slot-002 → ccc", r14._internal_source_rendition_id == "ccc")

# ── Consistency: projection ↔ resolver ─────────────────────────────

from app.domains.publications.kso_manifest_projection import (
    build_kso_safe_manifest_projection, ManifestSourceItem,
)

ms_items = [
    ManifestSourceItem(
        channel_code="kso", campaign_status="approved",
        creative_status="approved", rendition_status="valid",
        publication_status="published", device_status="active",
        store_is_active=True, store_code="s1", device_code="d1",
        content_type="image/png", duration_ms=5000, slot_order=1,  # non-zero
    ),
]
proj = build_kso_safe_manifest_projection(ms_items, NOW)
ref_from_proj = proj.manifest["items"][0]["mediaRef"]

resolver_items = [
    _make_item(slot_order=1),
]
resolved = resolve_kso_media_ref_source(resolver_items, ref_from_proj, NOW)
check("roundtrip: projection mediaRef → resolver resolved", resolved.resolved)
check("roundtrip: slot index matches", resolved.slot_index == 0)
check("roundtrip: internal source matches", resolved._internal_source_rendition_id == RID)


# ══════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════

print("\n".join(results))
print(f"\n{passed} passed, {failed} failed")

sys.exit(0 if failed == 0 else 1)
