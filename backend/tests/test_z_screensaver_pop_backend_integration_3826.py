"""Step 38.2.6 — Backend PoP Integration E2E with Test DB.

Real SQLite in-memory database with synthetic device, campaign, creative,
placement, generated manifest. Tests full ingest→list chain without mocks.

Key differences from 3825 (mock-based):
  - Real SQLAlchemy session with SQLite in-memory
  - Actual ingest_kso_pop / list_kso_pop_events functions
  - Real DB rows (no MagicMock)
  - FK constraints verified
  - Duplicate idempotency via real UNIQUE constraint

Safe: synthetic data only. No passwords/tokens/secrets/URLs/real codes.
"""

import asyncio
import json
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import nest_asyncio
nest_asyncio.apply()

from sqlalchemy import event as sa_event, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# ══════════════════════════════════════════════════════════════════════
# Test DB setup — separate engine from test_user_crud_api
# ══════════════════════════════════════════════════════════════════════

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# Full DDL — all tables required by PoP ingest chain
ALL_DDL = [
    # ── Organization ──
    """CREATE TABLE IF NOT EXISTS branches (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL, code VARCHAR(50) UNIQUE NOT NULL,
        timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS clusters (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL, code VARCHAR(50),
        branch_id VARCHAR(36) NOT NULL REFERENCES branches(id),
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(branch_id, code)
    )""",
    """CREATE TABLE IF NOT EXISTS stores (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL, code VARCHAR(50) UNIQUE NOT NULL,
        cluster_id VARCHAR(36) NOT NULL REFERENCES clusters(id),
        address TEXT,
        format VARCHAR(50),
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    # ── Users (needed for FK in campaign.created_by, creative.created_by, placement.created_by) ──
    """CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE,
        password_hash VARCHAR(255) NOT NULL DEFAULT '',
        display_name VARCHAR(255),
        is_active BOOLEAN DEFAULT 1,
        is_locked BOOLEAN DEFAULT 0,
        locked_until DATETIME,
        failed_attempts INTEGER DEFAULT 0,
        mfa_enabled BOOLEAN DEFAULT 0,
        mfa_secret VARCHAR(255),
        auth_provider VARCHAR(50) DEFAULT 'local',
        is_service_account BOOLEAN DEFAULT 0,
        ldap_dn VARCHAR(512),
        last_login_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_archived BOOLEAN DEFAULT 0,
        archived_at DATETIME,
        archived_by VARCHAR(36) REFERENCES users(id)
    )""",
    # ── Hierarchy ──
    """CREATE TABLE IF NOT EXISTS kso_devices (
        id VARCHAR(36) PRIMARY KEY,
        store_id VARCHAR(36) NOT NULL REFERENCES stores(id),
        device_code VARCHAR(64) UNIQUE NOT NULL,
        display_name VARCHAR(255),
        status VARCHAR(20) NOT NULL DEFAULT 'inactive',
        channel VARCHAR(20) NOT NULL DEFAULT 'kso',
        runtime_version VARCHAR(32),
        player_version VARCHAR(32),
        sidecar_version VARCHAR(32),
        state_adapter_version VARCHAR(32),
        manifest_version VARCHAR(64),
        screen_width INTEGER NOT NULL DEFAULT 1920,
        screen_height INTEGER NOT NULL DEFAULT 1080,
        ad_zone_width INTEGER NOT NULL DEFAULT 1440,
        ad_zone_height INTEGER NOT NULL DEFAULT 1080,
        last_seen_at DATETIME,
        comment TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    # ── Campaigns ──
    """CREATE TABLE IF NOT EXISTS campaigns (
        id VARCHAR(36) PRIMARY KEY,
        order_id VARCHAR(36) NOT NULL,
        advertiser_id VARCHAR(36),
        brand_id VARCHAR(36),
        campaign_code VARCHAR(64) UNIQUE,
        name VARCHAR(255) NOT NULL,
        objective VARCHAR(100),
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        planned_start_date DATE NOT NULL DEFAULT '2026-01-01',
        planned_end_date DATE NOT NULL DEFAULT '2026-12-31',
        priority INTEGER NOT NULL DEFAULT 0,
        budget NUMERIC(15,2),
        currency VARCHAR(3) NOT NULL DEFAULT 'RUB',
        comment TEXT,
        created_by VARCHAR(36) NOT NULL REFERENCES users(id),
        approved_by VARCHAR(36) REFERENCES users(id),
        approved_at DATETIME,
        rejection_reason TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS campaign_creatives (
        id VARCHAR(36) PRIMARY KEY,
        campaign_id VARCHAR(36) NOT NULL REFERENCES campaigns(id),
        creative_code VARCHAR(64) NOT NULL REFERENCES creatives(creative_code),
        slot_order INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id, creative_code)
    )""",
    # ── Media ──
    """CREATE TABLE IF NOT EXISTS creatives (
        id VARCHAR(36) PRIMARY KEY,
        advertiser_id VARCHAR(36),
        brand_id VARCHAR(36),
        creative_code VARCHAR(64) UNIQUE NOT NULL,
        name VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        comment TEXT,
        created_by VARCHAR(36) NOT NULL REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    # ── Scheduling ──
    """CREATE TABLE IF NOT EXISTS kso_placements (
        id VARCHAR(36) PRIMARY KEY,
        placement_code VARCHAR(64) UNIQUE NOT NULL,
        campaign_code VARCHAR(64) NOT NULL REFERENCES campaigns(campaign_code),
        creative_code VARCHAR(64) NOT NULL REFERENCES creatives(creative_code),
        device_code VARCHAR(64) NOT NULL REFERENCES kso_devices(device_code),
        starts_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ends_at DATETIME NOT NULL DEFAULT '2099-12-31',
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        slot_order INTEGER NOT NULL DEFAULT 0,
        created_by VARCHAR(36) NOT NULL REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    # ── Manifests ──
    """CREATE TABLE IF NOT EXISTS generated_manifests (
        id VARCHAR(36) PRIMARY KEY,
        manifest_code VARCHAR(64) UNIQUE NOT NULL,
        device_code VARCHAR(64) NOT NULL REFERENCES kso_devices(device_code),
        placement_code VARCHAR(64) NOT NULL REFERENCES kso_placements(placement_code),
        campaign_code VARCHAR(64) NOT NULL REFERENCES campaigns(campaign_code),
        status VARCHAR(30) NOT NULL DEFAULT 'generated',
        schema_version INTEGER NOT NULL DEFAULT 1,
        manifest_body_json TEXT NOT NULL DEFAULT '{}',
        item_count INTEGER NOT NULL DEFAULT 0,
        media_ref_format VARCHAR(50),
        generated_by VARCHAR(36) REFERENCES users(id),
        published_by VARCHAR(36) REFERENCES users(id),
        generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        published_at DATETIME,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    # ── Proof of Play ──
    """CREATE TABLE IF NOT EXISTS kso_proof_of_play_events (
        id VARCHAR(36) PRIMARY KEY,
        event_code VARCHAR(128) UNIQUE NOT NULL,
        device_code VARCHAR(64) NOT NULL REFERENCES kso_devices(device_code),
        placement_code VARCHAR(64) NOT NULL REFERENCES kso_placements(placement_code),
        campaign_code VARCHAR(64) NOT NULL REFERENCES campaigns(campaign_code),
        creative_code VARCHAR(64) NOT NULL REFERENCES creatives(creative_code),
        manifest_code VARCHAR(64) NOT NULL REFERENCES generated_manifests(manifest_code),
        media_ref VARCHAR(128) NOT NULL,
        event_type VARCHAR(32) NOT NULL DEFAULT 'impression',
        status VARCHAR(32) NOT NULL DEFAULT 'accepted',
        played_at DATETIME,
        duration_ms INTEGER,
        received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
]

# Models whose UUID columns need patching to String(36) for SQLite
ALL_MODEL_TABLES = [
    "branches", "clusters", "stores",
    "users",
    "kso_devices",
    "campaigns", "campaign_creatives",
    "creatives",
    "kso_placements",
    "generated_manifests",
    "kso_proof_of_play_events",
]


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ══════════════════════════════════════════════════════════════════════
# UUID patch + before_insert listeners
# ══════════════════════════════════════════════════════════════════════

def _patch_uuid_columns():
    """Patch all UUID columns to String(36) for SQLite compatibility."""
    import sqlalchemy as sa
    # Gather all models
    import app.domains.organization.models as org_m
    import app.domains.identity.models as id_m
    import app.domains.hierarchy.models as hier_m
    import app.domains.campaigns.models as camp_m
    import app.domains.media.models as media_m
    import app.domains.scheduling.models as sched_m
    import app.domains.manifests.models as man_m
    import app.domains.proof_of_play.models as pop_m

    all_models = [org_m, id_m, hier_m, camp_m, media_m, sched_m, man_m, pop_m]
    for mod in all_models:
        for table in mod.Base.metadata.tables.values():
            if table.name not in ALL_MODEL_TABLES:
                continue
            for col in table.columns:
                tname = str(col.type).upper()
                if 'UUID' in tname:
                    col.type = sa.String(36)


def _install_uuid_defaults_all():
    """Install before_insert listeners to generate client-side UUIDs for all models."""
    import app.domains.organization.models as org_m
    import app.domains.identity.models as id_m
    import app.domains.hierarchy.models as hier_m
    import app.domains.campaigns.models as camp_m
    import app.domains.media.models as media_m
    import app.domains.scheduling.models as sched_m
    import app.domains.manifests.models as man_m
    import app.domains.proof_of_play.models as pop_m

    model_classes = [
        (org_m, ["Branch", "Cluster", "Store"]),
        (id_m, ["User"]),
        (hier_m, ["KsoDevice"]),
        (camp_m, ["Campaign", "CampaignCreative"]),
        (media_m, ["Creative"]),
        (sched_m, ["KsoPlacement"]),
        (man_m, ["GeneratedManifest"]),
        (pop_m, ["KsoProofOfPlayEvent"]),
    ]

    def _make_set_id():
        def _set_id(mapper, connection, target):
            if hasattr(target, 'id') and target.id is None:
                target.id = uuid4().hex
            # Convert any UUID objects on any column to hex strings
            for col in mapper.columns:
                val = getattr(target, col.key, None)
                if val is not None and isinstance(val, uuid4().__class__):
                    setattr(target, col.key, val.hex)
        return _set_id

    for mod, names in model_classes:
        for name in names:
            cls = getattr(mod, name, None)
            if cls is not None:
                sa_event.listen(cls, "before_insert", _make_set_id())


_db_initialized = False


async def _init_integration_db():
    """Create all tables + seed synthetic data."""
    global _db_initialized
    if _db_initialized:
        return
    _db_initialized = True

    _patch_uuid_columns()
    _install_uuid_defaults_all()

    async with test_engine.begin() as conn:
        for ddl in ALL_DDL:
            await conn.execute(sa_text(ddl))


# ══════════════════════════════════════════════════════════════════════
# Seed helpers
# ══════════════════════════════════════════════════════════════════════

async def _seed_integration_data(
    device_code="int-dev-001",
    creative_code="int-creative-summer",
    campaign_code="int-camp-summer",
    placement_code="int-place-001",
    manifest_code="int-manifest-001",
    extra_creative_code=None,      # for multi-creative or filter tests
    extra_campaign_code=None,
    extra_placement_code=None,
    extra_device_code=None,
):
    """Seed synthetic branch→store→device→campaign→creative→placement→manifest chain."""
    async with TestSession() as db:
        now = datetime.now(timezone.utc)

        # Shared entities — INSERT OR IGNORE for idempotent re-seed
        user_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO users (id, username, password_hash, display_name) "
            "VALUES (:id, :u, :ph, :dn)"
        ), {"id": user_id, "u": "int_test_user", "ph": "hash", "dn": "Integration Test"})

        branch_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO branches (id, name, code) VALUES (:id, :n, :c)"
        ), {"id": branch_id, "n": "Integration Branch", "c": "int-branch"})

        cluster_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO clusters (id, name, code, branch_id) "
            "VALUES (:id, :n, :c, :bid)"
        ), {"id": cluster_id, "n": "Integration Cluster", "c": "int-cluster", "bid": branch_id})

        store_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO stores (id, name, code, cluster_id) "
            "VALUES (:id, :n, :c, :cid)"
        ), {"id": store_id, "n": "Integration Store", "c": "int-store", "cid": cluster_id})

        # KsoDevice
        kd_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO kso_devices (id, store_id, device_code, display_name, status) "
            "VALUES (:id, :sid, :dc, :dn, :st)"
        ), {"id": kd_id, "sid": store_id, "dc": device_code,
            "dn": "Integration Device", "st": "active"})

        # Campaign
        camp_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO campaigns (id, order_id, campaign_code, name, status, "
            "planned_start_date, planned_end_date, created_by) "
            "VALUES (:id, :oid, :cc, :n, :st, :psd, :ped, :cb)"
        ), {"id": camp_id, "oid": uuid4().hex, "cc": campaign_code,
            "n": "Integration Campaign", "st": "active",
            "psd": "2026-01-01", "ped": "2026-12-31", "cb": user_id})

        # Creative
        creative_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO creatives (id, creative_code, name, status, created_by) "
            "VALUES (:id, :cc, :n, :st, :cb)"
        ), {"id": creative_id, "cc": creative_code,
            "n": "Integration Creative", "st": "active", "cb": user_id})

        # CampaignCreative link
        cc_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO campaign_creatives (id, campaign_id, creative_code, slot_order) "
            "VALUES (:id, :cid, :cc, :so)"
        ), {"id": cc_id, "cid": camp_id, "cc": creative_code, "so": 0})

        # KsoPlacement
        kp_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO kso_placements (id, placement_code, campaign_code, "
            "creative_code, device_code, starts_at, ends_at, status, created_by) "
            "VALUES (:id, :pc, :cc, :cr, :dc, :sa, :ea, :st, :cb)"
        ), {
            "id": kp_id, "pc": placement_code, "cc": campaign_code,
            "cr": creative_code, "dc": device_code,
            "sa": now - timedelta(days=1), "ea": now + timedelta(days=365),
            "st": "active", "cb": user_id,
        })

        # GeneratedManifest
        manifest_body = {
            "manifestVersion": 1,
            "deviceCode": device_code,
            "generatedAt": now.isoformat(),
            "items": [
                {"slotOrder": 0, "contentType": "image/png",
                 "mediaRef": "media/current/slot-000"},
                {"slotOrder": 1, "contentType": "image/png",
                 "mediaRef": "media/current/slot-001"},
            ],
        }
        gm_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO generated_manifests (id, manifest_code, device_code, "
            "placement_code, campaign_code, status, schema_version, "
            "manifest_body_json, item_count, generated_by, published_by, "
            "generated_at, published_at) "
            "VALUES (:id, :mc, :dc, :pc, :cc, :st, :sv, :mb, :ic, :gb, :pb, :ga, :pa)"
        ), {
            "id": gm_id, "mc": manifest_code, "dc": device_code,
            "pc": placement_code, "cc": campaign_code,
            "st": "published", "sv": 1,
            "mb": json.dumps(manifest_body), "ic": 2,
            "gb": user_id, "pb": user_id,
            "ga": now, "pa": now,
        })

        # Optional extra data for filter/negative tests
        seed_extra = {}
        if extra_campaign_code and extra_campaign_code != campaign_code:
            extra_camp_id = uuid4().hex
            await db.execute(sa_text(
                "INSERT INTO campaigns (id, order_id, campaign_code, name, status, "
                "planned_start_date, planned_end_date, created_by) "
                "VALUES (:id, :oid, :cc, :n, :st, :psd, :ped, :cb)"
            ), {"id": extra_camp_id, "oid": uuid4().hex, "cc": extra_campaign_code,
                "n": "Extra Campaign", "st": "active",
                "psd": "2026-01-01", "ped": "2026-12-31", "cb": user_id})
            seed_extra["extra_camp_id"] = extra_camp_id

        if extra_creative_code and extra_creative_code != creative_code:
            extra_cr_id = uuid4().hex
            await db.execute(sa_text(
                "INSERT INTO creatives (id, creative_code, name, status, created_by) "
                "VALUES (:id, :cc, :n, :st, :cb)"
            ), {"id": extra_cr_id, "cc": extra_creative_code,
                "n": "Extra Creative", "st": "active", "cb": user_id})
            seed_extra["extra_cr_id"] = extra_cr_id

        # Link extra campaign+creative if both exist
        if extra_campaign_code and extra_creative_code and \
           extra_campaign_code != campaign_code and extra_creative_code != creative_code:
            extra_cc_id = uuid4().hex
            await db.execute(sa_text(
                "INSERT OR IGNORE INTO campaign_creatives "
                "(id, campaign_id, creative_code, slot_order) "
                "VALUES (:id, :cid, :cc, :so)"
            ), {"id": extra_cc_id, "cid": extra_camp_id,
                "cc": extra_creative_code, "so": 0})

        if extra_device_code and extra_device_code != device_code:
            # Need another store
            extra_store_id = uuid4().hex
            await db.execute(sa_text(
                "INSERT INTO stores (id, name, code, cluster_id) "
                "VALUES (:id, :n, :c, :cid)"
            ), {"id": extra_store_id, "n": "Extra Store", "c": "xtra-store", "cid": cluster_id})
            extra_kd_id = uuid4().hex
            await db.execute(sa_text(
                "INSERT INTO kso_devices (id, store_id, device_code, display_name, status) "
                "VALUES (:id, :sid, :dc, :dn, :st)"
            ), {"id": extra_kd_id, "sid": extra_store_id, "dc": extra_device_code,
                "dn": "Extra Device", "st": "active"})
            seed_extra["extra_kd_id"] = extra_kd_id

            # Create placement + manifest for extra device (needed for PoP ingest)
            if extra_placement_code and extra_campaign_code and extra_creative_code:
                extra_kp_id = uuid4().hex
                await db.execute(sa_text(
                    "INSERT INTO kso_placements (id, placement_code, campaign_code, "
                    "creative_code, device_code, starts_at, ends_at, status, created_by) "
                    "VALUES (:id, :pc, :cc, :cr, :dc, :sa, :ea, :st, :cb)"
                ), {
                    "id": extra_kp_id, "pc": extra_placement_code,
                    "cc": extra_campaign_code,
                    "cr": extra_creative_code, "dc": extra_device_code,
                    "sa": now - timedelta(days=1), "ea": now + timedelta(days=365),
                    "st": "active", "cb": user_id,
                })

                extra_manifest_body = {
                    "manifestVersion": 1,
                    "deviceCode": extra_device_code,
                    "generatedAt": now.isoformat(),
                    "items": [
                        {"slotOrder": 0, "contentType": "image/png",
                         "mediaRef": "media/current/slot-000"},
                    ],
                }
                extra_gm_id = uuid4().hex
                await db.execute(sa_text(
                    "INSERT INTO generated_manifests (id, manifest_code, device_code, "
                    "placement_code, campaign_code, status, schema_version, "
                    "manifest_body_json, item_count, generated_by, published_by, "
                    "generated_at, published_at) "
                    "VALUES (:id, :mc, :dc, :pc, :cc, :st, :sv, :mb, :ic, :gb, :pb, :ga, :pa)"
                ), {
                    "id": extra_gm_id,
                    "mc": f"{extra_placement_code}-manifest",
                    "dc": extra_device_code,
                    "pc": extra_placement_code, "cc": extra_campaign_code,
                    "st": "published", "sv": 1,
                    "mb": json.dumps(extra_manifest_body), "ic": 1,
                    "gb": user_id, "pb": user_id,
                    "ga": now, "pa": now,
                })

        await db.commit()
        return seed_extra


# ══════════════════════════════════════════════════════════════════════
# Test helpers
# ══════════════════════════════════════════════════════════════════════

async def _ingest(db, device_code, event_code, media_ref="media/current/slot-000",
                  event_type="playback_completed", duration_ms=15000,
                  manifest_version_id=None, manifest_hash=None):
    """Call ingest_kso_pop with a real DB session."""
    from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
    from app.domains.proof_of_play.service import ingest_kso_pop

    req = KsoPoPIngestRequest(
        event_code=event_code,
        media_ref=media_ref,
        event_type=event_type,
        duration_ms=duration_ms,
        manifest_version_id=manifest_version_id,
        manifest_hash=manifest_hash,
    )
    return await ingest_kso_pop(db, device_code, req)


async def _list_events(db, **filters):
    """Call list_kso_pop_events with a real DB session."""
    from app.domains.proof_of_play.service import list_kso_pop_events
    return await list_kso_pop_events(db, **filters)


async def _count_events(db, event_code):
    """Count rows with given event_code in kso_proof_of_play_events."""
    from app.domains.proof_of_play.models import KsoProofOfPlayEvent
    from sqlalchemy import select as _select, func
    result = await db.execute(
        _select(func.count()).select_from(KsoProofOfPlayEvent)
        .where(KsoProofOfPlayEvent.event_code == event_code)
    )
    return result.scalar()


# ══════════════════════════════════════════════════════════════════════
# Forbidden fields audit helpers
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_KEYS = frozenset({
    "id", "password", "password_hash", "token", "api_key", "access_token",
    "refresh_token", "device_secret", "client_secret", "backend_url",
    "manifest_version_id", "manifest_hash",
    "sha256", "file_path", "absolute_path", "local_path",
    "storage_ref", "minio", "s3",
    "barcode", "scanner", "key_value", "key_payload",
    "receipt", "payment", "fiscal",
    "customer", "card", "pan", "phone", "email",
    "stacktrace",
})

# For REQUEST schema audit — fields that must never appear even in request payloads
REQUEST_FORBIDDEN_KEYS = frozenset({
    "password", "password_hash", "token", "api_key", "access_token",
    "refresh_token", "device_secret", "client_secret", "backend_url",
    "sha256", "file_path", "absolute_path", "local_path",
    "storage_ref", "minio", "s3",
    "barcode", "scanner", "key_value", "key_payload",
    "receipt", "payment", "fiscal",
    "customer", "card", "pan", "phone", "email",
    "stacktrace",
})

FORBIDDEN_VALUES = frozenset({
    "token", "secret", "api_key", "backend_url",
    "barcode", "scanner", "receipt", "payment",
    "fiscal", "customer", "card", "pan",
})


def _assert_no_forbidden_keys(test, data: dict, label: str = ""):
    """Check that no forbidden keys exist in dict (recursive for nested dicts)."""
    for key, value in data.items():
        test.assertNotIn(key, FORBIDDEN_KEYS,
                         f"{label} contains forbidden key '{key}'")
        if isinstance(value, dict):
            _assert_no_forbidden_keys(test, value, label)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _assert_no_forbidden_keys(test, item, label)


def _assert_no_forbidden_values(test, text: str):
    """Check that forbidden substrings don't appear in serialized text."""
    lower = text.lower()
    for fb in FORBIDDEN_VALUES:
        test.assertNotIn(fb, lower, f"Output contains forbidden value '{fb}'")


# ══════════════════════════════════════════════════════════════════════
# Test: Happy Path — full ingest→list chain with real DB
# ══════════════════════════════════════════════════════════════════════

class TestPoPIntegrationHappyPath(unittest.TestCase):
    """Full integration: ingest→DB write→list read, all with real SQLite."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_integration_db())
        _run_async(_seed_integration_data(
            device_code="happy-dev-001",
            creative_code="happy-creative",
            campaign_code="happy-camp",
            placement_code="happy-place",
            manifest_code="happy-manifest",
        ))

    def test_ingest_returns_creative_code(self):
        """Happy path: ingest returns creative_code from placement chain."""
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(
                    session, "happy-dev-001", "e2e-happy-001",
                    event_type="playback_completed", duration_ms=15000,
                )
                return resp, err
        resp, err = _run_async(_do())
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.creative_code, "happy-creative")
        self.assertEqual(resp.device_code, "happy-dev-001")
        self.assertEqual(resp.campaign_code, "happy-camp")
        self.assertEqual(resp.placement_code, "happy-place")
        self.assertIsNotNone(resp.event_code)
        self.assertEqual(resp.event_code, "e2e-happy-001")
        self.assertIsNotNone(resp.received_at)

    def test_event_persisted_in_db(self):
        """Ingest writes to kso_proof_of_play_events."""
        async def _do():
            db = TestSession()
            async with db as session:
                await _ingest(session, "happy-dev-001", "e2e-persist-001")
                await session.commit()
                cnt = await _count_events(session, "e2e-persist-001")
                return cnt
        cnt = _run_async(_do())
        self.assertEqual(cnt, 1, "Event must be written to DB")

    def test_event_fields_in_db(self):
        """All safe fields are stored correctly."""
        async def _do():
            db = TestSession()
            async with db as session:
                await _ingest(session, "happy-dev-001", "e2e-fields-001",
                              event_type="playback_completed", duration_ms=12345)
                await session.commit()

                from app.domains.proof_of_play.models import KsoProofOfPlayEvent
                from sqlalchemy import select as _select
                result = await session.execute(
                    _select(KsoProofOfPlayEvent)
                    .where(KsoProofOfPlayEvent.event_code == "e2e-fields-001")
                )
                row = result.scalar_one()
                return row
        row = _run_async(_do())
        self.assertEqual(row.event_code, "e2e-fields-001")
        self.assertEqual(row.device_code, "happy-dev-001")
        self.assertEqual(row.placement_code, "happy-place")
        self.assertEqual(row.campaign_code, "happy-camp")
        self.assertEqual(row.creative_code, "happy-creative")
        self.assertEqual(row.manifest_code, "happy-manifest")
        self.assertEqual(row.media_ref, "media/current/slot-000")
        self.assertEqual(row.event_type, "playback_completed")
        self.assertEqual(row.duration_ms, 12345)
        self.assertEqual(row.status, "accepted")
        self.assertIsNotNone(row.received_at)

    def test_list_returns_event(self):
        """list_kso_pop_events finds ingested event."""
        async def _do():
            db = TestSession()
            async with db as session:
                await _ingest(session, "happy-dev-001", "e2e-list-001")
                await session.commit()
                rows = await _list_events(session)
                return rows
        rows = _run_async(_do())
        self.assertGreaterEqual(len(rows), 1)
        codes = [r.event_code for r in rows]
        self.assertIn("e2e-list-001", codes)

    def test_list_filters_by_creative_code(self):
        """Filter list by creative_code."""
        async def _do():
            db = TestSession()
            async with db as session:
                await _ingest(session, "happy-dev-001", "e2e-filter-cr-001")
                await session.commit()
                rows = await _list_events(session, creative_code="happy-creative")
                return rows
        rows = _run_async(_do())
        self.assertGreaterEqual(len(rows), 1)
        for r in rows:
            self.assertEqual(r.creative_code, "happy-creative")

    def test_list_filters_by_device_code(self):
        """Filter list by device_code."""
        async def _do():
            db = TestSession()
            async with db as session:
                rows = await _list_events(session, device_code="happy-dev-001")
                return rows
        rows = _run_async(_do())
        self.assertGreaterEqual(len(rows), 1)
        for r in rows:
            self.assertEqual(r.device_code, "happy-dev-001")

    def test_list_filters_by_campaign_code(self):
        """Filter list by campaign_code."""
        async def _do():
            db = TestSession()
            async with db as session:
                rows = await _list_events(session, campaign_code="happy-camp")
                return rows
        rows = _run_async(_do())
        self.assertGreaterEqual(len(rows), 1)
        for r in rows:
            self.assertEqual(r.campaign_code, "happy-camp")

    def test_list_filters_by_placement_code(self):
        """Filter list by placement_code."""
        async def _do():
            db = TestSession()
            async with db as session:
                rows = await _list_events(session, placement_code="happy-place")
                return rows
        rows = _run_async(_do())
        self.assertGreaterEqual(len(rows), 1)
        for r in rows:
            self.assertEqual(r.placement_code, "happy-place")

    def test_list_empty_for_unknown_creative(self):
        """Filter by unknown creative_code returns empty."""
        async def _do():
            db = TestSession()
            async with db as session:
                rows = await _list_events(session, creative_code="no-such-creative")
                return rows
        rows = _run_async(_do())
        self.assertEqual(len(rows), 0)

    def test_list_pagination(self):
        """limit+offset pagination works."""
        async def _do():
            db = TestSession()
            async with db as session:
                # Ingest 5 events
                for i in range(5):
                    await _ingest(session, "happy-dev-001", f"e2e-page-{i:03d}")
                await session.commit()
                rows_2 = await _list_events(session, limit=2, offset=0)
                rows_2b = await _list_events(session, limit=2, offset=2)
                return rows_2, rows_2b
        rows_2, rows_2b = _run_async(_do())
        self.assertEqual(len(rows_2), 2)
        self.assertEqual(len(rows_2b), 2)
        # Pages should not overlap
        page1_codes = {r.event_code for r in rows_2}
        page2_codes = {r.event_code for r in rows_2b}
        self.assertTrue(page1_codes.isdisjoint(page2_codes),
                        "Pagination pages must not overlap")

    def test_list_ordered_by_received_at_desc(self):
        """Events are ordered newest first."""
        async def _do():
            db = TestSession()
            async with db as session:
                rows = await _list_events(session, limit=10)
                return rows
        rows = _run_async(_do())
        if len(rows) >= 2:
            self.assertGreaterEqual(rows[0].received_at, rows[1].received_at,
                                    "Newest must come first")


# ══════════════════════════════════════════════════════════════════════
# Test: Duplicate Idempotency (real UNIQUE constraint)
# ══════════════════════════════════════════════════════════════════════

class TestPoPIntegrationIdempotency(unittest.TestCase):
    """Duplicate event_code → idempotent accepted, single DB row."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_integration_db())
        _run_async(_seed_integration_data(
            device_code="idem-dev-001",
            creative_code="idem-creative",
            campaign_code="idem-camp",
            placement_code="idem-place",
            manifest_code="idem-manifest",
        ))

    def test_duplicate_accepted_same_response(self):
        """Second POST with same event_code returns accepted, same data."""
        async def _do():
            db = TestSession()
            async with db as session:
                resp1, err1 = await _ingest(session, "idem-dev-001", "e2e-dup-001")
                await session.commit()
                resp2, err2 = await _ingest(session, "idem-dev-001", "e2e-dup-001")
                await session.commit()
                return resp1, err1, resp2, err2
        resp1, err1, resp2, err2 = _run_async(_do())
        self.assertIsNone(err1)
        self.assertIsNone(err2)
        self.assertEqual(resp1.status, "accepted")
        self.assertEqual(resp2.status, "accepted")
        self.assertEqual(resp1.creative_code, resp2.creative_code)
        self.assertEqual(resp1.event_code, resp2.event_code)

    def test_duplicate_single_db_row(self):
        """Only one row in DB for duplicate event_code."""
        async def _do():
            db = TestSession()
            async with db as session:
                await _ingest(session, "idem-dev-001", "e2e-single-001")
                await session.commit()
                await _ingest(session, "idem-dev-001", "e2e-single-001")
                await session.commit()
                cnt = await _count_events(session, "e2e-single-001")
                return cnt
        cnt = _run_async(_do())
        self.assertEqual(cnt, 1, "Duplicate event_code must not create second row")


# ══════════════════════════════════════════════════════════════════════
# Test: Negative Paths
# ══════════════════════════════════════════════════════════════════════

class TestPoPIntegrationNegative(unittest.TestCase):
    """Negative scenarios — unknown device, missing manifest, etc."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_integration_db())
        _run_async(_seed_integration_data(
            device_code="neg-dev-001",
            creative_code="neg-creative",
            campaign_code="neg-camp",
            placement_code="neg-place",
            manifest_code="neg-manifest",
        ))

    def test_unknown_device(self):
        """Non-existent device_code → device_not_found."""
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(session, "nonexistent-device", "e2e-nodev-001")
                return resp, err
        resp, err = _run_async(_do())
        self.assertIsNone(resp)
        self.assertEqual(err, "device_not_found")

    def test_unknown_media_ref(self):
        """media_ref not in manifest → unknown_media_ref."""
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(
                    session, "neg-dev-001", "e2e-nomedia-001",
                    media_ref="media/current/nonexistent-slot",
                )
                return resp, err
        resp, err = _run_async(_do())
        self.assertIsNone(resp)
        self.assertEqual(err, "unknown_media_ref")

    def test_no_published_manifest(self):
        """Device has no published manifest → no_published_manifest."""
        async def _do():
            db = TestSession()
            async with db as session:
                # Seed a second device WITHOUT a published manifest
                from app.domains.proof_of_play.service import ingest_kso_pop
                from app.domains.proof_of_play.schemas import KsoPoPIngestRequest

                # Create device without manifest
                user_id = uuid4().hex
                store_id = uuid4().hex
                cluster_id = uuid4().hex
                branch_id = uuid4().hex
                await db.execute(sa_text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, :n, :c)"
                ), {"id": branch_id, "n": "NoManifest Branch", "c": "nomf-branch"})
                await db.execute(sa_text(
                    "INSERT INTO clusters (id, name, code, branch_id) VALUES (:id, :n, :c, :bid)"
                ), {"id": cluster_id, "n": "NoManifest Cluster", "c": "nomf-cluster",
                    "bid": branch_id})
                await db.execute(sa_text(
                    "INSERT INTO stores (id, name, code, cluster_id) VALUES (:id, :n, :c, :cid)"
                ), {"id": store_id, "n": "NoManifest Store", "c": "nomf-store",
                    "cid": cluster_id})
                await db.execute(sa_text(
                    "INSERT INTO users (id, username, password_hash) VALUES (:id, :u, :ph)"
                ), {"id": user_id, "u": "nomf_user", "ph": "hash"})
                await db.execute(sa_text(
                    "INSERT INTO kso_devices (id, store_id, device_code, status) "
                    "VALUES (:id, :sid, :dc, :st)"
                ), {"id": uuid4().hex, "sid": store_id, "dc": "nomf-dev-001", "st": "active"})
                await db.commit()

                req = KsoPoPIngestRequest(
                    event_code="e2e-nomf-001",
                    media_ref="media/current/slot-000",
                )
                return await ingest_kso_pop(session, "nomf-dev-001", req)
        resp, err = _run_async(_do())
        self.assertIsNone(resp)
        self.assertEqual(err, "no_published_manifest")

    def test_manifest_hash_mismatch(self):
        """Wrong manifest_hash → manifest_hash_mismatch."""
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(
                    session, "neg-dev-001", "e2e-badhash-001",
                    manifest_hash="0" * 64,  # will not match actual
                )
                return resp, err
        resp, err = _run_async(_do())
        self.assertIsNone(resp)
        self.assertEqual(err, "manifest_hash_mismatch")

    def test_placement_not_found(self):
        """Device with manifest but placement_code not in kso_placements → placement_not_found."""
        async def _do():
            db = TestSession()
            async with db as session:
                # Create device + manifest without matching placement
                user_id = uuid4().hex
                store_id = uuid4().hex
                cluster_id = uuid4().hex
                branch_id = uuid4().hex
                await db.execute(sa_text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, :n, :c)"
                ), {"id": branch_id, "n": "NoPlace Branch", "c": "nopl-branch"})
                await db.execute(sa_text(
                    "INSERT INTO clusters (id, name, code, branch_id) VALUES (:id, :n, :c, :bid)"
                ), {"id": cluster_id, "n": "NoPlace Cluster", "c": "nopl-cluster",
                    "bid": branch_id})
                await db.execute(sa_text(
                    "INSERT INTO stores (id, name, code, cluster_id) VALUES (:id, :n, :c, :cid)"
                ), {"id": store_id, "n": "NoPlace Store", "c": "nopl-store",
                    "cid": cluster_id})
                await db.execute(sa_text(
                    "INSERT INTO users (id, username, password_hash) VALUES (:id, :u, :ph)"
                ), {"id": user_id, "u": "nopl_user", "ph": "hash"})
                kd_id = uuid4().hex
                await db.execute(sa_text(
                    "INSERT INTO kso_devices (id, store_id, device_code, status) "
                    "VALUES (:id, :sid, :dc, :st)"
                ), {"id": kd_id, "sid": store_id, "dc": "nopl-dev-001", "st": "active"})

                # Manifest references placement_code that doesn't exist
                gm_id = uuid4().hex
                manifest_body = {
                    "items": [{"slotOrder": 0, "contentType": "image/png",
                               "mediaRef": "media/current/slot-000"}],
                }
                now = datetime.now(timezone.utc)
                await db.execute(sa_text(
                    "INSERT INTO generated_manifests (id, manifest_code, device_code, "
                    "placement_code, campaign_code, status, manifest_body_json, "
                    "item_count, generated_by, generated_at, published_at) "
                    "VALUES (:id, :mc, :dc, :pc, :cc, :st, :mb, :ic, :gb, :ga, :pa)"
                ), {"id": gm_id, "mc": "nopl-manifest", "dc": "nopl-dev-001",
                    "pc": "nonexistent-placement", "cc": "nonexistent-camp",
                    "st": "published", "mb": json.dumps(manifest_body), "ic": 1,
                    "gb": user_id, "ga": now, "pa": now})
                await db.commit()

                from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
                from app.domains.proof_of_play.service import ingest_kso_pop
                req = KsoPoPIngestRequest(
                    event_code="e2e-noplace-001",
                    media_ref="media/current/slot-000",
                )
                return await ingest_kso_pop(session, "nopl-dev-001", req)
        resp, err = _run_async(_do())
        self.assertIsNone(resp)
        self.assertEqual(err, "placement_not_found")

    def test_forbidden_fields_not_in_ingest_request(self):
        """KsoPoPIngestRequest must not accept forbidden fields."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        req = KsoPoPIngestRequest(
            event_code="e2e-safe-req",
            media_ref="media/current/slot-000",
        )
        data = req.model_dump()
        for key in data:
            self.assertNotIn(key, REQUEST_FORBIDDEN_KEYS,
                             f"Ingest request contains forbidden key '{key}'")
        _assert_no_forbidden_values(self, json.dumps(data))


# ══════════════════════════════════════════════════════════════════════
# Test: Safety — responses must be clean
# ══════════════════════════════════════════════════════════════════════

class TestPoPIntegrationResponseSafety(unittest.TestCase):
    """Ingest and list responses must contain only safe fields."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_integration_db())
        _run_async(_seed_integration_data(
            device_code="safe-dev-001",
            creative_code="safe-creative",
            campaign_code="safe-camp",
            placement_code="safe-place",
            manifest_code="safe-manifest",
        ))

    def test_ingest_response_has_only_safe_keys(self):
        """Response contains only allowed keys."""
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(session, "safe-dev-001", "e2e-safe-001")
                await session.commit()
                return resp
        resp = _run_async(_do())
        data = resp.model_dump()
        allowed = {"status", "event_code", "device_code",
                   "placement_code", "campaign_code", "creative_code",
                   "received_at"}
        for key in data:
            self.assertIn(key, allowed, f"Unexpected key '{key}' in ingest response")

    def test_ingest_response_no_forbidden_strings(self):
        """Response JSON contains no forbidden substrings."""
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(session, "safe-dev-001", "e2e-fb-001")
                await session.commit()
                return resp
        resp = _run_async(_do())
        data = resp.model_dump()
        _assert_no_forbidden_keys(self, data, "Ingest response")
        _assert_no_forbidden_values(self, json.dumps(data, default=str))

    def test_list_response_no_forbidden(self):
        """List response contains no forbidden fields."""
        async def _do():
            db = TestSession()
            async with db as session:
                await _ingest(session, "safe-dev-001", "e2e-listfb-001")
                await session.commit()
                rows = await _list_events(session, creative_code="safe-creative")
                return rows
        rows = _run_async(_do())
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            data = row.model_dump()
            _assert_no_forbidden_keys(self, data, "List response")
        data_str = json.dumps(
            [r.model_dump(mode="json") for r in rows], default=str
        )
        _assert_no_forbidden_values(self, data_str)

    def test_ingest_response_no_raw_uuid(self):
        """Response must not expose raw UUIDs."""
        import re
        uuid_pat = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            re.IGNORECASE,
        )
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(session, "safe-dev-001", "e2e-nouuid-001")
                return resp
        resp = _run_async(_do())
        data_str = json.dumps(resp.model_dump(mode="json"))
        self.assertIsNone(
            uuid_pat.search(data_str),
            "Ingest response contains raw UUID"
        )

    def test_list_response_no_raw_uuid(self):
        """List response must not expose raw UUIDs."""
        import re
        uuid_pat = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            re.IGNORECASE,
        )
        async def _do():
            db = TestSession()
            async with db as session:
                await _ingest(session, "safe-dev-001", "e2e-listnouuid-001")
                await session.commit()
                rows = await _list_events(session, creative_code="safe-creative")
                return rows
        rows = _run_async(_do())
        self.assertGreaterEqual(len(rows), 1)
        data_str = json.dumps(
            [r.model_dump(mode="json") for r in rows]
        )
        self.assertIsNone(
            uuid_pat.search(data_str),
            "List response contains raw UUID"
        )

    def test_list_response_has_only_safe_keys(self):
        """List response keys are all allowed."""
        from app.domains.proof_of_play.schemas import KsoPoPListResponse
        now = datetime.now(timezone.utc)
        resp = KsoPoPListResponse(
            event_code="e2e-safe-keys", device_code="d1",
            placement_code="p1", campaign_code="c1",
            creative_code="cr1", media_ref="m1",
            event_type="impression", status="accepted",
            received_at=now,
        )
        data = resp.model_dump()
        allowed = {"event_code", "device_code", "placement_code",
                   "campaign_code", "creative_code", "media_ref",
                   "event_type", "status", "played_at", "duration_ms",
                   "received_at"}
        for key in data:
            self.assertIn(key, allowed, f"Unexpected key '{key}' in list response")


# ══════════════════════════════════════════════════════════════════════
# Test: Blocked/draft event handling
# ══════════════════════════════════════════════════════════════════════

class TestPoPIntegrationBlockedEvents(unittest.TestCase):
    """Blocked/draft events — stored but handled safely."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_integration_db())
        _run_async(_seed_integration_data(
            device_code="blocked-dev-001",
            creative_code="blocked-creative",
            campaign_code="blocked-camp",
            placement_code="blocked-place",
            manifest_code="blocked-manifest",
        ))

    def test_blocked_event_type_accepted(self):
        """'blocked' event_type is accepted (stored as-is)."""
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(
                    session, "blocked-dev-001", "e2e-blocked-001",
                    event_type="blocked",
                )
                await session.commit()
                return resp, err
        resp, err = _run_async(_do())
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.creative_code, "blocked-creative")

    def test_blocked_event_persisted(self):
        """'blocked' event is written to DB with event_type preserved."""
        async def _do():
            db = TestSession()
            async with db as session:
                # First ingest
                resp, err = await _ingest(
                    session, "blocked-dev-001", "e2e-blocked-persist",
                    event_type="blocked",
                )
                await session.commit()

                from app.domains.proof_of_play.models import KsoProofOfPlayEvent
                from sqlalchemy import select as _select
                result = await session.execute(
                    _select(KsoProofOfPlayEvent)
                    .where(KsoProofOfPlayEvent.event_code == "e2e-blocked-persist")
                )
                row = result.scalar_one()
                return row
        row = _run_async(_do())
        self.assertEqual(row.event_type, "blocked")
        self.assertEqual(row.status, "accepted")


# ══════════════════════════════════════════════════════════════════════
# Test: Multi-event / filter interactions
# ══════════════════════════════════════════════════════════════════════

class TestPoPIntegrationMultiEvent(unittest.TestCase):
    """Multiple events with different creative_codes — filters work correctly."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_integration_db())

        # Seed TWO devices+campaigns+creatives
        _run_async(_seed_integration_data(
            device_code="multi-dev-A",
            creative_code="creative-A",
            campaign_code="camp-A",
            placement_code="place-A",
            manifest_code="manifest-A",
            extra_device_code="multi-dev-B",
            extra_creative_code="creative-B",
            extra_campaign_code="camp-B",
            extra_placement_code="place-B",
        ))

    def test_two_devices_independent(self):
        """Events from different devices are separate."""
        async def _do():
            db = TestSession()
            async with db as session:
                # Ingest for device A
                await _ingest(session, "multi-dev-A", "e2e-multi-A-001",
                              event_type="impression")
                await session.commit()
                # Ingest for device B
                await _ingest(session, "multi-dev-B", "e2e-multi-B-001",
                              event_type="impression")
                await session.commit()

                rows_a = await _list_events(session, device_code="multi-dev-A")
                rows_b = await _list_events(session, device_code="multi-dev-B")
                return rows_a, rows_b
        rows_a, rows_b = _run_async(_do())
        self.assertGreaterEqual(len(rows_a), 1)
        self.assertGreaterEqual(len(rows_b), 1)
        for r in rows_a:
            self.assertEqual(r.device_code, "multi-dev-A")
        for r in rows_b:
            self.assertEqual(r.device_code, "multi-dev-B")

    def test_different_creative_codes_filtered(self):
        """Filter by creative_code works across multiple creatives."""
        async def _do():
            db = TestSession()
            async with db as session:
                await _ingest(session, "multi-dev-A", "e2e-cr-A-filt",
                              event_type="impression")
                await session.commit()
                await _ingest(session, "multi-dev-B", "e2e-cr-B-filt",
                              event_type="impression")
                await session.commit()

                rows_a = await _list_events(session, creative_code="creative-A")
                rows_b = await _list_events(session, creative_code="creative-B")
                return rows_a, rows_b
        rows_a, rows_b = _run_async(_do())
        self.assertGreaterEqual(len(rows_a), 1)
        self.assertGreaterEqual(len(rows_b), 1)
        for r in rows_a:
            self.assertEqual(r.creative_code, "creative-A")
        for r in rows_b:
            self.assertEqual(r.creative_code, "creative-B")


# ══════════════════════════════════════════════════════════════════════
# Test: Event type variants
# ══════════════════════════════════════════════════════════════════════

class TestPoPIntegrationEventTypes(unittest.TestCase):
    """All expected event_types accepted."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_integration_db())
        _run_async(_seed_integration_data(
            device_code="etypes-dev",
            creative_code="etypes-creative",
            campaign_code="etypes-camp",
            placement_code="etypes-place",
            manifest_code="etypes-manifest",
        ))

    def test_impression_event_type(self):
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(
                    session, "etypes-dev", "e2e-imp-001",
                    event_type="impression",
                )
                return resp, err
        resp, err = _run_async(_do())
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")

    def test_playback_completed_event_type(self):
        async def _do():
            db = TestSession()
            async with db as session:
                resp, err = await _ingest(
                    session, "etypes-dev", "e2e-pc-001",
                    event_type="playback_completed",
                )
                return resp, err
        resp, err = _run_async(_do())
        self.assertIsNone(err)
        self.assertEqual(resp.status, "accepted")

    def test_implicit_default_event_type(self):
        """KsoPoPIngestRequest defaults to 'impression'."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        req = KsoPoPIngestRequest(
            event_code="e2e-default",
            media_ref="media/current/slot-000",
        )
        self.assertEqual(req.event_type, "impression")
