"""Test KSO Seed Service — idempotent synthetic chain creation.

Creates a full one-KSO test chain:
  User → Branch → Cluster → Store → KsoDevice →
  Campaign → Creative → CampaignCreative →
  KsoPlacement → GeneratedManifest (published)

All entities are synthetic. No real device, no secrets, no URLs.

Idempotent: repeated calls with same codes do not create duplicates.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.test_kso_readiness.schemas import SeedSummary


# ── Safe codes for synthetic entities ───────────────────────────────────
SYNTHETIC_USER = "synthetic_seed_user"
SYNTHETIC_BRANCH = "syn-branch"
SYNTHETIC_CLUSTER = "syn-cluster"
SYNTHETIC_STORE = "syn-store"


async def seed_test_kso_chain(
    db: AsyncSession,
    device_code: str = "test-dev-seed",
    creative_code: str = "test-creative-seed",
    campaign_code: str = "test-camp-seed",
    placement_code: str = "test-place-seed",
    manifest_code: str = "test-manifest-seed",
) -> SeedSummary:
    """Seed a complete synthetic one-KSO test chain. Idempotent.

    Returns a safe SeedSummary — no UUIDs, no secrets, no paths.
    """
    summary = SeedSummary()
    now = datetime.now(timezone.utc)
    uid = uuid4().hex
    branch_id = uuid4().hex
    cluster_id = uuid4().hex
    store_id = uuid4().hex
    device_id = uuid4().hex
    campaign_id = uuid4().hex
    creative_id = uuid4().hex
    cc_id = uuid4().hex
    placement_id = uuid4().hex
    manifest_id = uuid4().hex

    parts: list[str] = []

    # ── 1. User ──────────────────────────────────────────────────────
    await db.execute(sa_text(
        "INSERT OR IGNORE INTO users (id, username, password_hash, display_name) "
        "VALUES (:id, :un, :ph, :dn)"
    ), {"id": uid, "un": SYNTHETIC_USER, "ph": "synthetic_hash_no_real_password",
        "dn": "Synthetic Seed User"})

    # ── 2. Branch → Cluster → Store ──────────────────────────────────
    await db.execute(sa_text(
        "INSERT OR IGNORE INTO branches (id, name, code) "
        "VALUES (:id, :n, :c)"
    ), {"id": branch_id, "n": "Synthetic Branch", "c": SYNTHETIC_BRANCH})

    await db.execute(sa_text(
        "INSERT OR IGNORE INTO clusters (id, name, code, branch_id) "
        "VALUES (:id, :n, :c, :bid)"
    ), {"id": cluster_id, "n": "Synthetic Cluster", "c": SYNTHETIC_CLUSTER,
        "bid": branch_id})

    await db.execute(sa_text(
        "INSERT OR IGNORE INTO stores (id, name, code, cluster_id) "
        "VALUES (:id, :n, :c, :cid)"
    ), {"id": store_id, "n": "Synthetic Store", "c": SYNTHETIC_STORE,
        "cid": cluster_id})

    # ── 3. Device ────────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM kso_devices WHERE device_code = :dc"
    ), {"dc": device_code})
    existing_device = result.scalar_one_or_none()

    if existing_device:
        summary.was_already_seeded = True
        device_id = existing_device
        parts.append(f"Device '{device_code}' already exists (idempotent)")
    else:
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

    # ── 4. Campaign ──────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM campaigns WHERE campaign_code = :cc"
    ), {"cc": campaign_code})
    existing_camp = result.scalar_one_or_none()

    if existing_camp:
        summary.was_already_seeded = True
        campaign_id = existing_camp
        parts.append(f"Campaign '{campaign_code}' already exists (idempotent)")
    else:
        await db.execute(sa_text(
            "INSERT INTO campaigns "
            "(id, order_id, campaign_code, name, status, "
            " planned_start_date, planned_end_date, created_by) "
            "VALUES (:id, :oid, :cc, :n, 'active', :psd, :ped, :cb)"
        ), {"id": campaign_id, "oid": uuid4().hex, "cc": campaign_code,
            "n": "Synthetic Campaign", "psd": "2026-01-01", "ped": "2026-12-31",
            "cb": uid})
        parts.append(f"Campaign '{campaign_code}' created")

    summary.campaign_seeded = True
    summary.campaign_code = campaign_code

    # ── 5. Creative ──────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM creatives WHERE creative_code = :cc"
    ), {"cc": creative_code})
    existing_cr = result.scalar_one_or_none()

    if existing_cr:
        summary.was_already_seeded = True
        creative_id = existing_cr
        parts.append(f"Creative '{creative_code}' already exists (idempotent)")
    else:
        await db.execute(sa_text(
            "INSERT INTO creatives "
            "(id, creative_code, name, status, created_by) "
            "VALUES (:id, :cc, :n, 'active', :cb)"
        ), {"id": creative_id, "cc": creative_code,
            "n": "Synthetic Creative", "cb": uid})
        parts.append(f"Creative '{creative_code}' created")

        # Also create a creative_version row so creative_ready check works
        cv_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO creative_versions "
            "(id, creative_id, version, original_filename, file_path, "
            " mime_type, file_size, sha256, width, height, "
            " duration_seconds, uploaded_by, status) "
            "VALUES (:id, :cid, 1, 'synthetic_test.png', 'synthetic/test.png', "
            " 'image/png', 1024, 'synthetic_sha256_no_real_hash', 768, 1024, "
            " 30.0, :ub, 'uploaded')"
        ), {"id": cv_id, "cid": creative_id, "ub": uid})

    summary.creative_seeded = True
    summary.creative_code = creative_code

    # ── 6. CampaignCreative link ─────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM campaign_creatives "
        "WHERE campaign_id = :cid AND creative_code = :cc"
    ), {"cid": campaign_id, "cc": creative_code})
    existing_cc = result.scalar_one_or_none()

    if existing_cc:
        cc_id = existing_cc
        parts.append("CampaignCreative link already exists (idempotent)")
    else:
        await db.execute(sa_text(
            "INSERT INTO campaign_creatives "
            "(id, campaign_id, creative_code, slot_order) "
            "VALUES (:id, :cid, :cc, 0)"
        ), {"id": cc_id, "cid": campaign_id, "cc": creative_code})
        parts.append("CampaignCreative link created")

    summary.campaign_creative_linked = True

    # ── 7. Placement ─────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM kso_placements WHERE placement_code = :pc"
    ), {"pc": placement_code})
    existing_pl = result.scalar_one_or_none()

    if existing_pl:
        summary.was_already_seeded = True
        placement_id = existing_pl
        parts.append(f"Placement '{placement_code}' already exists (idempotent)")
    else:
        await db.execute(sa_text(
            "INSERT INTO kso_placements "
            "(id, placement_code, campaign_code, creative_code, device_code, "
            " starts_at, ends_at, status, created_by) "
            "VALUES (:id, :pc, :cc, :cr, :dc, :sa, :ea, 'active', :cb)"
        ), {"id": placement_id, "pc": placement_code,
            "cc": campaign_code, "cr": creative_code, "dc": device_code,
            "sa": now - timedelta(days=1), "ea": now + timedelta(days=365),
            "cb": uid})
        parts.append(f"Placement '{placement_code}' created")

    summary.placement_seeded = True
    summary.placement_code = placement_code

    # ── 8. Manifest ──────────────────────────────────────────────────
    result = await db.execute(sa_text(
        "SELECT id FROM generated_manifests WHERE manifest_code = :mc"
    ), {"mc": manifest_code})
    existing_mf = result.scalar_one_or_none()

    if existing_mf:
        summary.was_already_seeded = True
        manifest_id = existing_mf
        parts.append(f"Manifest '{manifest_code}' already exists (idempotent)")
        # Check if already published
        result2 = await db.execute(sa_text(
            "SELECT status, item_count, manifest_body_json "
            "FROM generated_manifests WHERE manifest_code = :mc"
        ), {"mc": manifest_code})
        row = result2.fetchone()
        if row:
            summary.manifest_published = (row[0] == "published")
            summary.manifest_item_count = row[1] or 0
            body = json.loads(row[2] or "{}")
            items = body.get("items", [])
            if isinstance(items, list) and items:
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
            "items": [
                {
                    "slotOrder": 0,
                    "contentType": "image/png",
                    "creativeCode": creative_code,
                    "mediaRef": "media/current/slot-000",
                },
            ],
        }
        await db.execute(sa_text(
            "INSERT INTO generated_manifests "
            "(id, manifest_code, device_code, placement_code, campaign_code, "
            " status, schema_version, manifest_body_json, item_count, "
            " media_ref_format, generated_by, published_by, "
            " generated_at, published_at) "
            "VALUES (:id, :mc, :dc, :pc, :cc, 'published', 1, :mb, 1, "
            " 'media/current/slot-NNN', :gb, :pb, :ga, :pa)"
        ), {"id": manifest_id, "mc": manifest_code,
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
    if summary.was_already_seeded:
        summary.summary = "Chain already existed (idempotent): " + "; ".join(parts)
    else:
        summary.summary = "Chain seeded: " + "; ".join(parts)

    return summary
