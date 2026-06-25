"""Step 38.4 — Test KSO Readiness Control Plane — Backend Tests.

Tests for the safe readiness endpoint and synthetic seed helper.
No physical KSO, no X11, no Chromium, no secrets.
"""

import json
import re
import unittest
from datetime import datetime, timezone

import nest_asyncio
nest_asyncio.apply()

from sqlalchemy import event as sa_event, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ══════════════════════════════════════════════════════════════════════
# Test DB (SQLite in-memory)
# ══════════════════════════════════════════════════════════════════════

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

ALL_DDL = [
    "CREATE TABLE IF NOT EXISTS users (id VARCHAR(36) PRIMARY KEY, username VARCHAR(100) UNIQUE, password_hash VARCHAR(255) DEFAULT '', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS branches (id VARCHAR(36) PRIMARY KEY, name VARCHAR(255), code VARCHAR(50) UNIQUE)",
    "CREATE TABLE IF NOT EXISTS clusters (id VARCHAR(36) PRIMARY KEY, name VARCHAR(255), code VARCHAR(50), branch_id VARCHAR(36) REFERENCES branches(id))",
    "CREATE TABLE IF NOT EXISTS stores (id VARCHAR(36) PRIMARY KEY, name VARCHAR(255), code VARCHAR(50) UNIQUE, cluster_id VARCHAR(36) REFERENCES clusters(id), status VARCHAR(20) DEFAULT 'active')",
    "CREATE TABLE IF NOT EXISTS kso_devices (id VARCHAR(36) PRIMARY KEY, store_id VARCHAR(36) REFERENCES stores(id), device_code VARCHAR(64) UNIQUE, display_name VARCHAR(255), status VARCHAR(20) DEFAULT 'active', screen_width INTEGER DEFAULT 1920, screen_height INTEGER DEFAULT 1080, ad_zone_width INTEGER DEFAULT 1440, ad_zone_height INTEGER DEFAULT 1080, channel VARCHAR(20) DEFAULT 'kso', runtime_version VARCHAR(32), player_version VARCHAR(32), sidecar_version VARCHAR(32), state_adapter_version VARCHAR(32), manifest_version VARCHAR(64), last_seen_at DATETIME, comment TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS campaigns (id VARCHAR(36) PRIMARY KEY, order_id VARCHAR(36), advertiser_id VARCHAR(36), brand_id VARCHAR(36), campaign_code VARCHAR(64) UNIQUE, name VARCHAR(255), objective VARCHAR(100), status VARCHAR(20) DEFAULT 'draft', planned_start_date DATE, planned_end_date DATE, priority INTEGER DEFAULT 0, budget NUMERIC, currency VARCHAR(3) DEFAULT 'RUB', comment TEXT, created_by VARCHAR(36) REFERENCES users(id), approved_by VARCHAR(36) REFERENCES users(id), approved_at DATETIME, rejection_reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS campaign_channels (id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) REFERENCES campaigns(id), channel_id VARCHAR(36), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS channels (id VARCHAR(36) PRIMARY KEY, channel_code VARCHAR(64) UNIQUE, name VARCHAR(255))",
    "CREATE TABLE IF NOT EXISTS campaign_targets (id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) REFERENCES campaigns(id), target_type VARCHAR(20), branch_id VARCHAR(36), cluster_id VARCHAR(36), store_id VARCHAR(36), logical_carrier_id VARCHAR(36), display_surface_id VARCHAR(36), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS campaign_renditions (id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) REFERENCES campaigns(id), rendition_id VARCHAR(36), weight INTEGER DEFAULT 1, position INTEGER, is_active BOOLEAN DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS creatives (id VARCHAR(36) PRIMARY KEY, advertiser_id VARCHAR(36), brand_id VARCHAR(36), creative_code VARCHAR(64) UNIQUE, name VARCHAR(255), status VARCHAR(20) DEFAULT 'draft', comment TEXT, created_by VARCHAR(36) REFERENCES users(id), created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS creative_versions (id VARCHAR(36) PRIMARY KEY, creative_id VARCHAR(36) REFERENCES creatives(id), version INTEGER, original_filename VARCHAR(500), file_path VARCHAR(1000), mime_type VARCHAR(100), file_size BIGINT, sha256 VARCHAR(64), width INTEGER, height INTEGER, duration_seconds FLOAT, uploaded_by VARCHAR(36) REFERENCES users(id), status VARCHAR(20) DEFAULT 'uploaded', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(creative_id, version))",
    "CREATE TABLE IF NOT EXISTS campaign_creatives (id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) REFERENCES campaigns(id), creative_code VARCHAR(64) REFERENCES creatives(creative_code), slot_order INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(campaign_id, creative_code))",
    "CREATE TABLE IF NOT EXISTS kso_placements (id VARCHAR(36) PRIMARY KEY, placement_code VARCHAR(64) UNIQUE, campaign_code VARCHAR(64) REFERENCES campaigns(campaign_code), creative_code VARCHAR(64) REFERENCES creatives(creative_code), device_code VARCHAR(64) REFERENCES kso_devices(device_code), starts_at DATETIME, ends_at DATETIME, status VARCHAR(20) DEFAULT 'draft', slot_order INTEGER DEFAULT 0, created_by VARCHAR(36) REFERENCES users(id), created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS generated_manifests (id VARCHAR(36) PRIMARY KEY, manifest_code VARCHAR(64) UNIQUE, device_code VARCHAR(64) REFERENCES kso_devices(device_code), placement_code VARCHAR(64) REFERENCES kso_placements(placement_code), campaign_code VARCHAR(64) REFERENCES campaigns(campaign_code), status VARCHAR(30) DEFAULT 'generated', manifest_body_json TEXT DEFAULT '{}', item_count INTEGER DEFAULT 0, media_ref_format VARCHAR(50), generated_by VARCHAR(36) REFERENCES users(id), published_by VARCHAR(36) REFERENCES users(id), generated_at DATETIME DEFAULT CURRENT_TIMESTAMP, published_at DATETIME, schema_version INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS kso_proof_of_play_events (id VARCHAR(36) PRIMARY KEY, event_code VARCHAR(128) UNIQUE, device_code VARCHAR(64) REFERENCES kso_devices(device_code), placement_code VARCHAR(64) REFERENCES kso_placements(placement_code), campaign_code VARCHAR(64) REFERENCES campaigns(campaign_code), creative_code VARCHAR(64) REFERENCES creatives(creative_code), manifest_code VARCHAR(64) REFERENCES generated_manifests(manifest_code), media_ref VARCHAR(128), event_type VARCHAR(32) DEFAULT 'impression', status VARCHAR(32) DEFAULT 'accepted', played_at DATETIME, duration_ms INTEGER, received_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
]

FORBIDDEN_KEYS = frozenset({
    "id", "password", "password_hash", "token", "api_key", "access_token",
    "refresh_token", "device_secret", "client_secret", "backend_url",
    "manifest_version_id", "manifest_hash", "sha256", "file_path",
    "absolute_path", "local_path", "storage_ref", "minio", "s3",
    "barcode", "scanner", "key_value", "key_payload",
    "receipt", "payment", "fiscal", "customer", "card", "pan", "phone", "email",
})

FORBIDDEN_VALUES = frozenset({
    "token", "api_key", "backend_url",
    "barcode", "scanner", "receipt", "payment", "fiscal",
    "customer", "card", "pan", "sha256", "file_path",
})

UUID_PAT = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE,
)


def _run_async(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def _assert_no_forbidden_keys(test, data: dict, label: str = ""):
    for key, value in data.items():
        test.assertNotIn(key, FORBIDDEN_KEYS, f"{label}: forbidden key '{key}'")
        if isinstance(value, dict):
            _assert_no_forbidden_keys(test, value, label)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _assert_no_forbidden_keys(test, item, label)


def _assert_no_forbidden_values(test, text: str):
    lower = text.lower()
    for fb in FORBIDDEN_VALUES:
        test.assertNotIn(fb, lower, f"Forbidden value '{fb}' in output")


def _assert_no_raw_uuid(test, text: str):
    test.assertIsNone(UUID_PAT.search(text), f"Raw UUID in: {text[:80]}")


# ══════════════════════════════════════════════════════════════════════
# DB init + seed helper
# ══════════════════════════════════════════════════════════════════════

_db_initialized = False


def _patch_uuids():
    import sqlalchemy as sa
    import app.domains.organization.models as om
    import app.domains.identity.models as im
    import app.domains.hierarchy.models as hm
    import app.domains.campaigns.models as cm
    import app.domains.media.models as mm
    import app.domains.scheduling.models as sm
    import app.domains.manifests.models as gmm
    import app.domains.proof_of_play.models as pm
    for mod in [om, im, hm, cm, mm, sm, gmm, pm]:
        for table in mod.Base.metadata.tables.values():
            for col in table.columns:
                if 'UUID' in str(col.type).upper():
                    col.type = sa.String(36)


def _install_defaults():
    import app.domains.organization.models as om
    import app.domains.identity.models as im
    import app.domains.hierarchy.models as hm
    import app.domains.campaigns.models as cm
    import app.domains.media.models as mm
    import app.domains.scheduling.models as sm
    import app.domains.manifests.models as gmm
    import app.domains.proof_of_play.models as pm
    from uuid import uuid4

    def _make_set_id():
        def _set_id(mapper, connection, target):
            if hasattr(target, 'id') and target.id is None:
                target.id = uuid4().hex
            for col in mapper.columns:
                val = getattr(target, col.key, None)
                if val is not None and isinstance(val, uuid4().__class__):
                    setattr(target, col.key, val.hex)
        return _set_id

    model_map = [
        (om, ["Branch", "Cluster", "Store"]),
        (im, ["User"]),
        (hm, ["KsoDevice"]),
        (cm, ["Campaign", "CampaignCreative"]),
        (mm, ["Creative"]),
        (sm, ["KsoPlacement"]),
        (gmm, ["GeneratedManifest"]),
        (pm, ["KsoProofOfPlayEvent"]),
    ]
    for mod, names in model_map:
        for name in names:
            cls = getattr(mod, name, None)
            if cls:
                sa_event.listen(cls, "before_insert", _make_set_id())


async def _init_db():
    global _db_initialized
    if _db_initialized:
        return
    _db_initialized = True
    _patch_uuids()
    _install_defaults()
    async with _test_engine.begin() as conn:
        for ddl in ALL_DDL:
            await conn.execute(sa_text(ddl))


async def _seed_full_chain(
    device_code="test-dev-readiness",
    creative_code="test-creative-readiness",
    campaign_code="test-camp-readiness",
    placement_code="test-place-readiness",
    manifest_code="test-manifest-readiness",
):
    """Seed a complete synthetic backend chain for readiness tests."""
    from uuid import uuid4
    from datetime import timedelta
    async with TestSession() as db:
        now = datetime.now(timezone.utc)
        uid = uuid4().hex

        await db.execute(sa_text("INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (:id,'u','h')"), {"id": uid})
        await db.execute(sa_text("INSERT OR IGNORE INTO branches (id, name, code) VALUES (:id,'b','br')"), {"id": uuid4().hex})
        await db.execute(sa_text("INSERT OR IGNORE INTO clusters (id, name, code, branch_id) VALUES (:id,'c','cl', (SELECT id FROM branches LIMIT 1))"), {"id": uuid4().hex})
        await db.execute(sa_text("INSERT OR IGNORE INTO stores (id, name, code, cluster_id) VALUES (:id,'s','st', (SELECT id FROM clusters LIMIT 1))"), {"id": uuid4().hex})
        await db.execute(sa_text("INSERT INTO kso_devices (id, store_id, device_code, status) VALUES (:id, (SELECT id FROM stores LIMIT 1), :dc, 'active')"), {"id": uuid4().hex, "dc": device_code})

        await db.execute(sa_text("INSERT INTO campaigns (id, order_id, campaign_code, name, status, planned_start_date, planned_end_date, created_by) VALUES (:id, :oid, :cc, 'C', 'active', '2026-01-01', '2026-12-31', :cb)"), {"id": uuid4().hex, "oid": uuid4().hex, "cc": campaign_code, "cb": uid})
        await db.execute(sa_text("INSERT INTO creatives (id, creative_code, name, status, created_by) VALUES (:id, :cc, 'C', 'active', :cb)"), {"id": uuid4().hex, "cc": creative_code, "cb": uid})
        cid = uuid4().hex
        await db.execute(sa_text("INSERT INTO campaign_creatives (id, campaign_id, creative_code, slot_order) VALUES (:id, (SELECT id FROM campaigns WHERE campaign_code=:cc), :cr, 0)"), {"id": cid, "cc": campaign_code, "cr": creative_code})
        await db.execute(sa_text("INSERT INTO kso_placements (id, placement_code, campaign_code, creative_code, device_code, starts_at, ends_at, status, created_by) VALUES (:id, :pc, :cc, :cr, :dc, :sa, :ea, 'active', :cb)"), {"id": uuid4().hex, "pc": placement_code, "cc": campaign_code, "cr": creative_code, "dc": device_code, "sa": now - timedelta(days=1), "ea": now + timedelta(days=365), "cb": uid})

        body = json.dumps({"items": [{"slotOrder": 0, "contentType": "image/png", "creativeCode": creative_code, "mediaRef": "media/current/slot-000"}]})
        await db.execute(sa_text("INSERT INTO generated_manifests (id, manifest_code, device_code, placement_code, campaign_code, status, manifest_body_json, item_count, published_by, generated_by, generated_at, published_at) VALUES (:id, :mc, :dc, :pc, :cc, 'published', :mb, 1, :pb, :gb, :ga, :pa)"), {"id": uuid4().hex, "mc": manifest_code, "dc": device_code, "pc": placement_code, "cc": campaign_code, "mb": body, "pb": uid, "gb": uid, "ga": now, "pa": now})
        await db.commit()


# ══════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════

class TestReadinessEndpoint(unittest.TestCase):
    """GET /api/test-kso/readiness returns safe readiness summary."""

    @classmethod
    def setUpClass(cls):
        _run_async(_init_db())
        _run_async(_seed_full_chain())

    def test_01_readiness_all_ready(self):
        """Full chain → overall_ready=True."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        self.assertTrue(status.overall_ready)
        self.assertTrue(status.device_registered)
        self.assertTrue(status.manifest_published)
        self.assertTrue(status.manifest_has_creative_code)
        self.assertTrue(status.manifest_has_media_ref)
        self.assertTrue(status.campaign_registered)
        self.assertTrue(status.placement_registered)
        self.assertTrue(status.creative_registered)

    def test_02_readiness_no_forbidden_keys(self):
        """Readiness response has no forbidden keys."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        data = status.model_dump()
        _assert_no_forbidden_keys(self, data, "ReadinessStatus")

    def test_03_readiness_no_forbidden_values(self):
        """Readiness JSON has no forbidden value substrings."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        data_str = json.dumps(status.model_dump(mode="json"), default=str)
        _assert_no_forbidden_values(self, data_str)

    def test_04_readiness_no_raw_uuid(self):
        """Readiness response has no raw UUIDs."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        data_str = json.dumps(status.model_dump(mode="json"), default=str)
        _assert_no_raw_uuid(self, data_str)

    def test_05_phase_d_blocked(self):
        """Phase D always blocked — requires manual approval."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        self.assertTrue(status.phase_d_requires_approval)
        self.assertTrue(status.phase_d_blocked)
        self.assertIn("manual approval", status.phase_d_block_reason.lower())

    def test_06_unknown_device_not_ready(self):
        """Unknown device → overall_ready=False."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "no-such-device")
        status = _run_async(_do())
        self.assertFalse(status.overall_ready)
        self.assertFalse(status.device_registered)

    def test_07_device_name_present(self):
        """device_code is in response (safe string)."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        self.assertEqual(status.device_code, "test-dev-readiness")

    def test_08_manifest_code_present(self):
        """manifest_code is in response."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        self.assertEqual(status.manifest_code, "test-manifest-readiness")

    def test_09_creative_code_campaign_placement_present(self):
        """Campaign/placement/creative codes in response."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        self.assertEqual(status.campaign_code, "test-camp-readiness")
        self.assertEqual(status.placement_code, "test-place-readiness")
        self.assertEqual(status.creative_code, "test-creative-readiness")

    def test_10_sidecar_config_hints(self):
        """Sidecar config fields list is safe (no actual secrets)."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        self.assertTrue(status.sidecar_config_required)
        self.assertGreater(len(status.sidecar_config_fields), 0)
        # Fields are names only — no actual values
        for field in status.sidecar_config_fields:
            self.assertIsInstance(field, str)
            self.assertNotIn("=", field, "Field hint must not contain value")

    def test_11_pop_endpoint_ready(self):
        """PoP endpoint is always marked ready (exists in code)."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        self.assertTrue(status.pop_endpoint_ready)

    def test_12_portal_report_ready(self):
        """Portal report is always marked ready."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "test-dev-readiness")
        status = _run_async(_do())
        self.assertTrue(status.portal_report_ready)
        self.assertTrue(status.portal_report_filter_creative_code)

    def test_13_schema_no_forbidden_fields(self):
        """ReadinessStatus schema class has no forbidden field names."""
        from app.domains.test_kso_readiness.schemas import ReadinessStatus
        fields = ReadinessStatus.model_fields.keys()
        for f in fields:
            self.assertNotIn(f, FORBIDDEN_KEYS, f"ReadinessStatus has forbidden field '{f}'")
            self.assertNotIn(f.lower(), FORBIDDEN_VALUES, f"ReadinessStatus field '{f}' matches forbidden value")

    def test_14_schema_allowed_fields_only(self):
        """ReadinessStatus has only safe, expected fields."""
        from app.domains.test_kso_readiness.schemas import ReadinessStatus
        fields = set(ReadinessStatus.model_fields.keys())
        allowed = {
            "overall_ready", "backend_healthy",
            "device_registered", "device_code",
            "manifest_published", "manifest_code",
            "manifest_has_creative_code", "manifest_has_media_ref",
            "manifest_item_count",
            "campaign_registered", "campaign_code",
            "placement_registered", "placement_code",
            "creative_registered", "creative_code",
            "sidecar_config_required", "sidecar_config_fields",
            "media_cache_ready", "media_cache_items_expected",
            "pop_endpoint_ready", "pop_last_count",
            "portal_report_ready", "portal_report_filter_creative_code",
            "phase_d_requires_approval", "phase_d_blocked",
            "phase_d_block_reason",
            "readiness_reasons", "checked_at",
        }
        for f in fields:
            self.assertIn(f, allowed, f"Unexpected field '{f}' in ReadinessStatus")
        for a in allowed:
            self.assertIn(a, fields, f"Missing expected field '{a}' in ReadinessStatus")

    def test_15_readiness_reasons_safe(self):
        """Readiness reasons contain no forbidden substrings."""
        async def _do():
            db = TestSession()
            async with db as session:
                from app.domains.test_kso_readiness.service import build_readiness_summary
                return await build_readiness_summary(session, "no-such-device")
        status = _run_async(_do())
        for reason in status.readiness_reasons:
            self.assertIsInstance(reason, str)
            _assert_no_forbidden_values(self, reason)
