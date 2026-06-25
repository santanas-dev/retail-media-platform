"""Test KSO Seed Service — idempotent synthetic chain creation.

Creates a full one-KSO test chain:
  User → Branch → Cluster → Store → KsoDevice →
  Campaign → Creative → CampaignCreative →
  KsoPlacement → GeneratedManifest (published)

All entities are synthetic. No real device, no secrets, no URLs.

Idempotent: repeated calls with same codes do not create duplicates.
Uses INSERT ... ON CONFLICT DO NOTHING + fetch-IDs pattern for Postgres.
"""

import json
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.test_kso_readiness.schemas import SeedSummary


# ── Safe codes for synthetic entities ───────────────────────────────────
SYNTHETIC_USER = "synthetic_seed_user"
SYNTHETIC_BRANCH = "syn-branch"
SYNTHETIC_CLUSTER = "syn-cluster"
SYNTHETIC_STORE = "syn-store"
SYNTHETIC_ADVERTISER = "Synthetic Advertiser"
SYNTHETIC_ORDER_NUMBER = "SYN-00001"


async def _insert_get_id(db, insert_sql, select_sql, params, id_param="id"):
    """INSERT ON CONFLICT DO NOTHING, then SELECT the real ID.

    Returns the actual ID (newly inserted or pre-existing).
    """
    await db.execute(sa_text(insert_sql), params)
    result = await db.execute(sa_text(select_sql), params)
    row = result.fetchone()
    return row[0] if row else params[id_param]


async def seed_test_kso_chain(
    db: AsyncSession,
    device_code: str = "test-dev-seed",
    creative_code: str = "test-creative-seed",
    campaign_code: str = "test-camp-seed",
    placement_code: str = "test-place-seed",
    manifest_code: str = "test-manifest-seed",
) -> SeedSummary:
    """Seed a complete synthetic one-KSO test chain. Idempotent."""
    summary = SeedSummary()
    now = datetime.now(timezone.utc)
    parts: list[str] = []

    # ── 1. User ──────────────────────────────────────────────────────
    uid = await _insert_get_id(
        db,
        "INSERT INTO users (id, username, password_hash, display_name) "
        "VALUES (:id, :un, :ph, :dn) ON CONFLICT (username) DO NOTHING",
        "SELECT id FROM users WHERE username = :un",
        {"id": uuid4().hex, "un": SYNTHETIC_USER,
         "ph": "synthetic_hash_no_real_password", "dn": "Synthetic Seed User"},
    )

    # ── 2. Branch ────────────────────────────────────────────────────
    branch_id = await _insert_get_id(
        db,
        "INSERT INTO branches (id, name, code) "
        "VALUES (:id, 'Synthetic Branch', :c) ON CONFLICT (code) DO NOTHING",
        "SELECT id FROM branches WHERE code = :c",
        {"id": uuid4().hex, "c": SYNTHETIC_BRANCH},
    )

    # ── 3. Cluster ───────────────────────────────────────────────────
    cluster_id = await _insert_get_id(
        db,
        "INSERT INTO clusters (id, name, code, branch_id) "
        "VALUES (:id, 'Synthetic Cluster', :c, :bid) "
        "ON CONFLICT (branch_id, code) DO NOTHING",
        "SELECT id FROM clusters WHERE branch_id = :bid AND code = :c",
        {"id": uuid4().hex, "c": SYNTHETIC_CLUSTER, "bid": branch_id},
    )

    # ── 4. Store ─────────────────────────────────────────────────────
    store_id = await _insert_get_id(
        db,
        "INSERT INTO stores (id, name, code, cluster_id) "
        "VALUES (:id, 'Synthetic Store', :c, :cid) "
        "ON CONFLICT (code) DO NOTHING",
        "SELECT id FROM stores WHERE code = :c",
        {"id": uuid4().hex, "c": SYNTHETIC_STORE, "cid": cluster_id},
    )

    # ── 5. Advertiser ────────────────────────────────────────────────
    advertiser_id = await _insert_get_id(
        db,
        "INSERT INTO advertisers (id, name, status) "
        "VALUES (:id, :n, 'active') ON CONFLICT DO NOTHING",
        "SELECT id FROM advertisers WHERE name = :n",
        {"id": uuid4().hex, "n": SYNTHETIC_ADVERTISER},
    )

    # ── 6. Order ─────────────────────────────────────────────────────
    order_id = await _insert_get_id(
        db,
        "INSERT INTO orders (id, advertiser_id, name, number, status, currency) "
        "VALUES (:id, :aid, 'Synthetic Order', :num, 'approved', 'RUB') "
        "ON CONFLICT DO NOTHING",
        "SELECT id FROM orders WHERE advertiser_id = :aid AND number = :num",
        {"id": uuid4().hex, "aid": advertiser_id, "num": SYNTHETIC_ORDER_NUMBER},
    )

    # ── 7. Device ────────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM kso_devices WHERE device_code = :dc"
    ), {"dc": device_code})
    existing = result.scalar_one_or_none()

    if existing:
        summary.was_already_seeded = True
        device_id = existing
        parts.append(f"Device '{device_code}' already exists (idempotent)")
    else:
        device_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO kso_devices "
            "(id, store_id, device_code, display_name, status, "
            " screen_width, screen_height, ad_zone_width, ad_zone_height) "
            "VALUES (:id, :sid, :dc, :dn, 'active', 768, 1024, 768, 1024)"
        ), {"id": device_id, "sid": store_id, "dc": device_code,
            "dn": "Synthetic KSO Device"})
        parts.append(f"Device '{device_code}' created")

    summary.device_seeded = True
    summary.device_code = device_code

    # ── 8. Campaign ──────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM campaigns WHERE campaign_code = :cc"
    ), {"cc": campaign_code})
    existing = result.scalar_one_or_none()

    if existing:
        summary.was_already_seeded = True
        campaign_id = existing
        parts.append(f"Campaign '{campaign_code}' already exists (idempotent)")
    else:
        campaign_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO campaigns "
            "(id, order_id, advertiser_id, campaign_code, name, status, "
            " planned_start_date, planned_end_date, created_by) "
            "VALUES (:id, :oid, :aid, :cc, :n, 'active', :psd, :ped, :cb)"
        ), {"id": campaign_id, "oid": order_id, "aid": advertiser_id,
            "cc": campaign_code, "n": "Synthetic Campaign",
            "psd": date(2026, 1, 1), "ped": date(2026, 12, 31), "cb": uid})
        parts.append(f"Campaign '{campaign_code}' created")

    summary.campaign_seeded = True
    summary.campaign_code = campaign_code

    # ── 9. Creative (+ version) ──────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM creatives WHERE creative_code = :cc"
    ), {"cc": creative_code})
    existing = result.scalar_one_or_none()

    if existing:
        summary.was_already_seeded = True
        creative_id = existing
        parts.append(f"Creative '{creative_code}' already exists (idempotent)")
    else:
        creative_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO creatives "
            "(id, creative_code, name, status, created_by) "
            "VALUES (:id, :cc, :n, 'active', :cb)"
        ), {"id": creative_id, "cc": creative_code,
            "n": "Synthetic Creative", "cb": uid})
        parts.append(f"Creative '{creative_code}' created")

        # Also create creative_versions row for creative_ready check
        await db.execute(sa_text(
            "INSERT INTO creative_versions (id, creative_id, version, "
            " original_filename, file_path, mime_type, file_size, sha256, "
            " width, height, duration_seconds, uploaded_by, status) "
            "VALUES (:id, :cid, 1, 'synthetic_test.png', 'synthetic/test.png', "
            " 'image/png', 1024, 'synthetic_sha256_no_real_hash', 768, 1024, "
            " 30.0, :ub, 'uploaded') "
            "ON CONFLICT (creative_id, version) DO NOTHING"
        ), {"id": uuid4().hex, "cid": creative_id, "ub": uid})

    summary.creative_seeded = True
    summary.creative_code = creative_code

    # ── 10. CampaignCreative link ────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM campaign_creatives "
        "WHERE campaign_id = :cid AND creative_code = :cc"
    ), {"cid": campaign_id, "cc": creative_code})
    existing = result.scalar_one_or_none()

    if existing:
        parts.append("CampaignCreative link already exists (idempotent)")
    else:
        await db.execute(sa_text(
            "INSERT INTO campaign_creatives "
            "(id, campaign_id, creative_code, slot_order) "
            "VALUES (:id, :cid, :cc, 0)"
        ), {"id": uuid4().hex, "cid": campaign_id, "cc": creative_code})
        parts.append("CampaignCreative link created")

    summary.campaign_creative_linked = True

    # ── 11. Placement ────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM kso_placements WHERE placement_code = :pc"
    ), {"pc": placement_code})
    existing = result.scalar_one_or_none()

    if existing:
        summary.was_already_seeded = True
        parts.append(f"Placement '{placement_code}' already exists (idempotent)")
    else:
        await db.execute(sa_text(
            "INSERT INTO kso_placements "
            "(id, placement_code, campaign_code, creative_code, device_code, "
            " starts_at, ends_at, status, created_by) "
            "VALUES (:id, :pc, :cc, :cr, :dc, :sa, :ea, 'active', :cb)"
        ), {"id": uuid4().hex, "pc": placement_code,
            "cc": campaign_code, "cr": creative_code, "dc": device_code,
            "sa": now - timedelta(days=1), "ea": now + timedelta(days=365),
            "cb": uid})
        parts.append(f"Placement '{placement_code}' created")

    summary.placement_seeded = True
    summary.placement_code = placement_code

    # ── 12. Manifest ─────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id, status, item_count, manifest_body_json "
        "FROM generated_manifests WHERE manifest_code = :mc"
    ), {"mc": manifest_code})
    row = result.fetchone()

    if row:
        summary.was_already_seeded = True
        parts.append(f"Manifest '{manifest_code}' already exists (idempotent)")
        summary.manifest_published = (row[1] == "published")
        summary.manifest_item_count = row[2] or 0
        body = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")
        items = body.get("items", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    if item.get("creativeCode"):
                        summary.manifest_has_creative_code = True
                    if item.get("mediaRef"):
                        summary.manifest_has_media_ref = True
    else:
        manifest_body = {
            "manifestVersion": 1,
            "deviceCode": device_code,
            "generatedAt": now.isoformat(),
            "items": [{
                "slotOrder": 0,
                "contentType": "image/png",
                "creativeCode": creative_code,
                "mediaRef": "media/current/slot-000",
            }],
        }
        await db.execute(sa_text(
            "INSERT INTO generated_manifests "
            "(id, manifest_code, device_code, placement_code, campaign_code, "
            " status, schema_version, manifest_body_json, item_count, "
            " media_ref_format, generated_by, published_by, "
            " generated_at, published_at) "
            "VALUES (:id, :mc, :dc, :pc, :cc, 'published', 1, :mb, 1, "
            " 'media/current/slot-NNN', :gb, :pb, :ga, :pa)"
        ), {"id": uuid4().hex, "mc": manifest_code,
            "dc": device_code, "pc": placement_code, "cc": campaign_code,
            "mb": json.dumps(manifest_body), "gb": uid, "pb": uid,
            "ga": now, "pa": now})
        summary.manifest_published = True
        summary.manifest_item_count = 1
        summary.manifest_has_creative_code = True
        summary.manifest_has_media_ref = True
        parts.append(f"Manifest '{manifest_code}' generated and published")

    summary.manifest_generated = True
    summary.manifest_code = manifest_code

    # ── Final ────────────────────────────────────────────────────────
    await db.commit()

    summary.seeded_at = now
    prefix = "Chain already existed (idempotent): " if summary.was_already_seeded else "Chain seeded: "
    summary.summary = prefix + "; ".join(parts)

    return summary
