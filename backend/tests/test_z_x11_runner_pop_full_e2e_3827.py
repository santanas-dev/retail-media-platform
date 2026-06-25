"""Step 38.2.7 — Full Dev E2E: Player JSONL → Sidecar → Backend → Report.

Validates the complete dev-only chain:
  PoP draft → JSONL record → sidecar classify → sidecar payload →
  backend ingest → backend list/report filter.

No KSO, no X11, no Chromium, no physical run.
All data is synthetic. All security surfaces audited.
"""

import asyncio
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import nest_asyncio
nest_asyncio.apply()

from sqlalchemy import event as sa_event, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ══════════════════════════════════════════════════════════════════════
# Test DB setup (same pattern as 3826)
# ══════════════════════════════════════════════════════════════════════

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

ALL_DDL = [
    """CREATE TABLE IF NOT EXISTS branches (
        id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL,
        code VARCHAR(50) UNIQUE NOT NULL, timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
        is_active BOOLEAN DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS clusters (
        id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL, code VARCHAR(50),
        branch_id VARCHAR(36) NOT NULL REFERENCES branches(id),
        is_active BOOLEAN DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(branch_id, code))""",
    """CREATE TABLE IF NOT EXISTS stores (
        id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL,
        code VARCHAR(50) UNIQUE NOT NULL, cluster_id VARCHAR(36) NOT NULL REFERENCES clusters(id),
        address TEXT, format VARCHAR(50), status VARCHAR(20) NOT NULL DEFAULT 'active',
        timezone VARCHAR(50) DEFAULT 'Europe/Moscow', is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(36) PRIMARY KEY, username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL DEFAULT '', display_name VARCHAR(255),
        is_active BOOLEAN DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS kso_devices (
        id VARCHAR(36) PRIMARY KEY, store_id VARCHAR(36) NOT NULL REFERENCES stores(id),
        device_code VARCHAR(64) UNIQUE NOT NULL, display_name VARCHAR(255),
        status VARCHAR(20) NOT NULL DEFAULT 'inactive', channel VARCHAR(20) NOT NULL DEFAULT 'kso',
        runtime_version VARCHAR(32), player_version VARCHAR(32),
        sidecar_version VARCHAR(32), state_adapter_version VARCHAR(32),
        manifest_version VARCHAR(64),
        screen_width INTEGER NOT NULL DEFAULT 1920, screen_height INTEGER NOT NULL DEFAULT 1080,
        ad_zone_width INTEGER NOT NULL DEFAULT 1440, ad_zone_height INTEGER NOT NULL DEFAULT 1080,
        last_seen_at DATETIME, comment TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS campaigns (
        id VARCHAR(36) PRIMARY KEY, order_id VARCHAR(36) NOT NULL,
        campaign_code VARCHAR(64) UNIQUE, name VARCHAR(255) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        planned_start_date DATE NOT NULL DEFAULT '2026-01-01',
        planned_end_date DATE NOT NULL DEFAULT '2026-12-31',
        priority INTEGER NOT NULL DEFAULT 0, currency VARCHAR(3) NOT NULL DEFAULT 'RUB',
        created_by VARCHAR(36) NOT NULL REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS creatives (
        id VARCHAR(36) PRIMARY KEY, creative_code VARCHAR(64) UNIQUE NOT NULL,
        name VARCHAR(255) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'draft',
        created_by VARCHAR(36) NOT NULL REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS campaign_creatives (
        id VARCHAR(36) PRIMARY KEY,
        campaign_id VARCHAR(36) NOT NULL REFERENCES campaigns(id),
        creative_code VARCHAR(64) NOT NULL REFERENCES creatives(creative_code),
        slot_order INTEGER NOT NULL DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id, creative_code))""",
    """CREATE TABLE IF NOT EXISTS kso_placements (
        id VARCHAR(36) PRIMARY KEY, placement_code VARCHAR(64) UNIQUE NOT NULL,
        campaign_code VARCHAR(64) NOT NULL REFERENCES campaigns(campaign_code),
        creative_code VARCHAR(64) NOT NULL REFERENCES creatives(creative_code),
        device_code VARCHAR(64) NOT NULL REFERENCES kso_devices(device_code),
        starts_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ends_at DATETIME NOT NULL DEFAULT '2099-12-31',
        status VARCHAR(20) NOT NULL DEFAULT 'draft', slot_order INTEGER NOT NULL DEFAULT 0,
        created_by VARCHAR(36) NOT NULL REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS generated_manifests (
        id VARCHAR(36) PRIMARY KEY, manifest_code VARCHAR(64) UNIQUE NOT NULL,
        device_code VARCHAR(64) NOT NULL REFERENCES kso_devices(device_code),
        placement_code VARCHAR(64) NOT NULL REFERENCES kso_placements(placement_code),
        campaign_code VARCHAR(64) NOT NULL REFERENCES campaigns(campaign_code),
        status VARCHAR(30) NOT NULL DEFAULT 'generated', schema_version INTEGER NOT NULL DEFAULT 1,
        manifest_body_json TEXT NOT NULL DEFAULT '{}', item_count INTEGER NOT NULL DEFAULT 0,
        media_ref_format VARCHAR(50),
        generated_by VARCHAR(36) REFERENCES users(id),
        published_by VARCHAR(36) REFERENCES users(id),
        generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, published_at DATETIME,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS kso_proof_of_play_events (
        id VARCHAR(36) PRIMARY KEY, event_code VARCHAR(128) UNIQUE NOT NULL,
        device_code VARCHAR(64) NOT NULL REFERENCES kso_devices(device_code),
        placement_code VARCHAR(64) NOT NULL REFERENCES kso_placements(placement_code),
        campaign_code VARCHAR(64) NOT NULL REFERENCES campaigns(campaign_code),
        creative_code VARCHAR(64) NOT NULL REFERENCES creatives(creative_code),
        manifest_code VARCHAR(64) NOT NULL REFERENCES generated_manifests(manifest_code),
        media_ref VARCHAR(128) NOT NULL, event_type VARCHAR(32) NOT NULL DEFAULT 'impression',
        status VARCHAR(32) NOT NULL DEFAULT 'accepted', played_at DATETIME,
        duration_ms INTEGER, received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
]

ALL_MODEL_TABLES = [
    "branches", "clusters", "stores", "users",
    "kso_devices", "campaigns", "campaign_creatives", "creatives",
    "kso_placements", "generated_manifests", "kso_proof_of_play_events",
]

FORBIDDEN_VALUES = frozenset({
    "token", "secret", "api_key", "backend_url",
    "barcode", "scanner", "receipt", "payment", "fiscal",
    "customer", "card", "pan", "sha256", "file_path",
    "device_secret", "minio", "s3",
})

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

UUID_PAT = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE,
)


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _assert_no_forbidden_keys(test, data: dict, label: str = ""):
    for key, value in data.items():
        test.assertNotIn(key, FORBIDDEN_KEYS, f"{label} contains forbidden key '{key}'")
        if isinstance(value, dict):
            _assert_no_forbidden_keys(test, value, label)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _assert_no_forbidden_keys(test, item, label)


def _assert_no_forbidden_values(test, text: str):
    lower = text.lower()
    for fb in FORBIDDEN_VALUES:
        test.assertNotIn(fb, lower, f"Output contains forbidden value '{fb}'")


def _assert_no_raw_uuid(test, text: str):
    test.assertIsNone(UUID_PAT.search(text), f"Output contains raw UUID: {text[:80]}")


# ══════════════════════════════════════════════════════════════════════
# DB init + seed
# ══════════════════════════════════════════════════════════════════════

def _patch_uuid_columns():
    import sqlalchemy as sa
    import app.domains.organization.models as org_m
    import app.domains.identity.models as id_m
    import app.domains.hierarchy.models as hier_m
    import app.domains.campaigns.models as camp_m
    import app.domains.media.models as media_m
    import app.domains.scheduling.models as sched_m
    import app.domains.manifests.models as man_m
    import app.domains.proof_of_play.models as pop_m
    for mod in [org_m, id_m, hier_m, camp_m, media_m, sched_m, man_m, pop_m]:
        for table in mod.Base.metadata.tables.values():
            if table.name not in ALL_MODEL_TABLES:
                continue
            for col in table.columns:
                if 'UUID' in str(col.type).upper():
                    col.type = sa.String(36)


def _install_uuid_defaults_all():
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


async def _init_db():
    global _db_initialized
    if _db_initialized:
        return
    _db_initialized = True
    _patch_uuid_columns()
    _install_uuid_defaults_all()
    async with _test_engine.begin() as conn:
        for ddl in ALL_DDL:
            await conn.execute(sa_text(ddl))


async def _seed_backend(
    device_code="e2e-dev", creative_code="e2e-creative",
    campaign_code="e2e-camp", placement_code="e2e-place",
    manifest_code="e2e-manifest",
):
    """Seed synthetic backend data."""
    async with TestSession() as db:
        now = datetime.now(timezone.utc)
        user_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (:id, :u, :ph)"
        ), {"id": user_id, "u": "e2e_user", "ph": "hash"})

        branch_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO branches (id, name, code) VALUES (:id, :n, :c)"
        ), {"id": branch_id, "n": "E2E Branch", "c": "e2e-branch"})
        cluster_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO clusters (id, name, code, branch_id) VALUES (:id, :n, :c, :bid)"
        ), {"id": cluster_id, "n": "E2E Cluster", "c": "e2e-cluster", "bid": branch_id})
        store_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT OR IGNORE INTO stores (id, name, code, cluster_id) VALUES (:id, :n, :c, :cid)"
        ), {"id": store_id, "n": "E2E Store", "c": "e2e-store", "cid": cluster_id})

        kd_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO kso_devices (id, store_id, device_code, display_name, status) "
            "VALUES (:id, :sid, :dc, :dn, :st)"
        ), {"id": kd_id, "sid": store_id, "dc": device_code, "dn": "E2E Device", "st": "active"})

        camp_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO campaigns (id, order_id, campaign_code, name, status, "
            "planned_start_date, planned_end_date, created_by) "
            "VALUES (:id, :oid, :cc, :n, :st, :psd, :ped, :cb)"
        ), {"id": camp_id, "oid": uuid4().hex, "cc": campaign_code,
            "n": "E2E Campaign", "st": "active",
            "psd": "2026-01-01", "ped": "2026-12-31", "cb": user_id})

        creative_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO creatives (id, creative_code, name, status, created_by) "
            "VALUES (:id, :cc, :n, :st, :cb)"
        ), {"id": creative_id, "cc": creative_code, "n": "E2E Creative", "st": "active", "cb": user_id})

        cc_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO campaign_creatives (id, campaign_id, creative_code, slot_order) "
            "VALUES (:id, :cid, :cc, :so)"
        ), {"id": cc_id, "cid": camp_id, "cc": creative_code, "so": 0})

        kp_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO kso_placements (id, placement_code, campaign_code, "
            "creative_code, device_code, starts_at, ends_at, status, created_by) "
            "VALUES (:id, :pc, :cc, :cr, :dc, :sa, :ea, :st, :cb)"
        ), {"id": kp_id, "pc": placement_code, "cc": campaign_code,
            "cr": creative_code, "dc": device_code,
            "sa": now - timedelta(days=1), "ea": now + timedelta(days=365),
            "st": "active", "cb": user_id})

        manifest_body = {
            "manifestVersion": 1, "deviceCode": device_code,
            "generatedAt": now.isoformat(),
            "items": [{"slotOrder": 0, "contentType": "image/png",
                       "mediaRef": "media/current/slot-000"}],
        }
        gm_id = uuid4().hex
        await db.execute(sa_text(
            "INSERT INTO generated_manifests (id, manifest_code, device_code, "
            "placement_code, campaign_code, status, schema_version, "
            "manifest_body_json, item_count, generated_by, published_by, "
            "generated_at, published_at) "
            "VALUES (:id, :mc, :dc, :pc, :cc, :st, :sv, :mb, :ic, :gb, :pb, :ga, :pa)"
        ), {"id": gm_id, "mc": manifest_code, "dc": device_code,
            "pc": placement_code, "cc": campaign_code,
            "st": "published", "sv": 1, "mb": json.dumps(manifest_body), "ic": 1,
            "gb": user_id, "pb": user_id, "ga": now, "pa": now})
        await db.commit()


def _make_jsonl_line(filepath, record):
    """Write a single JSONL record to a temp file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl_line(filepath):
    """Read the first JSONL line from a file."""
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                return json.loads(stripped)
    return None


# ══════════════════════════════════════════════════════════════════════
# HELPER: build a valid ScreensaverPoPDraft
# ══════════════════════════════════════════════════════════════════════

def _make_draft(creative_code, media_available=True, event_type="playback_completed",
                visible=True, duration_ms=15000):
    """Create a synthetic ScreensaverPoPDraft with safe defaults."""
    from kso_player.screensaver_creative import ScreensaverPoPDraft
    now = datetime.now(timezone.utc)
    return ScreensaverPoPDraft(
        event_type=event_type,
        creative_code=creative_code,
        visible=visible,
        media_available=media_available,
        duration_ms=duration_ms,
        started_at_utc=now.isoformat(),
        ended_at_utc=(now + timedelta(seconds=duration_ms // 1000)).isoformat(),
    )


def _build_record(draft, safety_state="idle", slot_order=0, content_type="image/png"):
    """Call build_screensaver_pop_record and assert success."""
    from kso_player.screensaver_pop_bridge import build_screensaver_pop_record
    result = build_screensaver_pop_record(
        draft, safety_state=safety_state, slot_order=slot_order, content_type=content_type,
    )
    return result


# ══════════════════════════════════════════════════════════════════════
# Full E2E chain: Player JSONL → Sidecar classify → Backend ingest → Report
# ══════════════════════════════════════════════════════════════════════

class TestFullDevE2EChain(unittest.TestCase):
    """Complete dev-only chain: player JSONL → sidecar → backend → report."""

    CC = "e2e-fullchain-creative"
    DEV = "e2e-fullchain-device"
    CAMP = "e2e-fullchain-camp"
    PLACE = "e2e-fullchain-place"
    MANIFEST = "e2e-fullchain-manifest"
    EVENT = "e2e-fullchain-event-001"
    MEDIA_REF = "media/current/slot-000"

    @classmethod
    def setUpClass(cls):
        _run_async(_init_db())
        _run_async(_seed_backend(
            device_code=cls.DEV, creative_code=cls.CC,
            campaign_code=cls.CAMP, placement_code=cls.PLACE,
            manifest_code=cls.MANIFEST,
        ))

    def test_01_player_screensaver_pop_draft_to_jsonl(self):
        """Step 1-2: ScreensaverPoPDraft → JSONL record via screensaver_pop_bridge."""
        from kso_player.screensaver_pop_bridge import build_screensaver_event_code

        now = datetime.now(timezone.utc)
        event_code = build_screensaver_event_code(
            self.CC, "playback_completed", now.isoformat(), 0,
        )
        self.assertTrue(event_code.startswith("scr-"))

        draft = _make_draft(self.CC)
        result = _build_record(draft)
        self.assertTrue(result.built, f"Record not built: {result.reason}")
        self.assertEqual(result.event_type, "playback_completed")
        self.assertEqual(result.event_status, "completed")
        self.assertEqual(result.creative_code, self.CC)
        self.assertIsNotNone(result._record)

        rec = result._record
        self.assertEqual(rec["creative_code"], self.CC)
        self.assertEqual(rec["media_available"], True)
        self.assertEqual(rec["playback_allowed"], True)
        self.assertEqual(rec["event_status"], "completed")
        self.assertEqual(rec["safety_state"], "idle")

        _assert_no_forbidden_keys(self, rec, "JSONL record")
        _assert_no_forbidden_values(self, json.dumps(rec))
        _assert_no_raw_uuid(self, json.dumps(rec))

    def test_02_jsonl_write_and_read_back(self):
        """Step 3: Write JSONL to disk, read back — creative_code preserved."""
        draft = _make_draft(self.CC)
        result = _build_record(draft)
        self.assertTrue(result.built)

        with tempfile.TemporaryDirectory() as tmpdir:
            pending = os.path.join(tmpdir, "pop", "pending")
            os.makedirs(pending, exist_ok=True)
            path = os.path.join(pending, "player_events.jsonl")
            _make_jsonl_line(path, result._record)
            rec = _read_jsonl_line(path)
            self.assertIsNotNone(rec)
            self.assertEqual(rec["creative_code"], self.CC)
            self.assertEqual(rec["event_status"], "completed")
            self.assertEqual(rec["event_type"], "playback_completed")
            self.assertEqual(rec["media_available"], True)
            _assert_no_forbidden_keys(self, rec, "Read-back JSONL")
            _assert_no_forbidden_values(self, json.dumps(rec))

    def test_03_sidecar_classify_eligible(self):
        """Step 4: Sidecar classify — playback_completed + idle → CLASS_ELIGIBLE."""
        from kso_sidecar_agent.pop_pickup import classify_pop_event, CLASS_ELIGIBLE

        draft = _make_draft(self.CC)
        result = _build_record(draft)
        rec = result._record

        manifest_items = [{"order": 0, "content_type": "image/png"}]
        classification = classify_pop_event(
            rec, manifest_items=manifest_items, media_cache_complete=True,
        )
        self.assertEqual(classification.classification, CLASS_ELIGIBLE,
                         f"Expected CLASS_ELIGIBLE, got {classification.classification}: {classification.reason}")
        self.assertTrue(classification.backend_eligible)
        self.assertEqual(classification.event_type, "playback_completed")
        self.assertEqual(classification.event_status, "completed")
        self.assertEqual(classification.safety_state, "idle")

        data = {
            "classification": classification.classification,
            "reason": classification.reason,
            "event_type": classification.event_type,
            "event_status": classification.event_status,
            "safety_state": classification.safety_state,
            "selected_order": classification.selected_order,
        }
        _assert_no_forbidden_keys(self, data, "Classification")
        _assert_no_forbidden_values(self, json.dumps(data))

    def test_04_sidecar_build_payload_with_creative_code(self):
        """Step 5: PopPayloadEvent contains creative_code from JSONL record."""
        from kso_sidecar_agent.pop_payload import PopPayloadEvent

        draft = _make_draft(self.CC)
        result = _build_record(draft)
        rec = result._record

        payload = PopPayloadEvent(
            device_event_id=uuid4().hex,
            played_at=rec.get("started_at"),
            duration_ms=rec.get("duration_ms", 0),
            play_status="completed",
            selected_order=rec.get("selected_order"),
            selected_content_type=rec.get("selected_content_type"),
            creative_code=rec.get("creative_code"),
        )
        self.assertEqual(payload.creative_code, self.CC)
        self.assertEqual(payload.play_status, "completed")
        self.assertEqual(payload.duration_ms, 15000)

        safe_fields = {
            "play_status": payload.play_status,
            "selected_order": payload.selected_order,
            "selected_content_type": payload.selected_content_type,
            "creative_code": payload.creative_code,
        }
        _assert_no_forbidden_keys(self, safe_fields, "Payload safe fields")
        _assert_no_forbidden_values(self, json.dumps(safe_fields, default=str))

    def test_05_backend_ingest_accepts_event(self):
        """Step 6: Backend ingest_kso_pop accepts event with creative_code."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        from app.domains.proof_of_play.service import ingest_kso_pop

        async def _do():
            db = TestSession()
            async with db as session:
                req = KsoPoPIngestRequest(
                    event_code=self.EVENT, media_ref=self.MEDIA_REF,
                    event_type="playback_completed", duration_ms=15000,
                )
                resp, err = await ingest_kso_pop(session, self.DEV, req)
                await session.commit()
                return resp, err
        resp, err = _run_async(_do())
        self.assertIsNone(err, f"Backend error: {err}")
        self.assertEqual(resp.status, "accepted")
        self.assertEqual(resp.creative_code, self.CC)
        self.assertEqual(resp.device_code, self.DEV)
        self.assertEqual(resp.campaign_code, self.CAMP)
        self.assertEqual(resp.placement_code, self.PLACE)
        self.assertEqual(resp.event_code, self.EVENT)

        data = resp.model_dump()
        _assert_no_forbidden_keys(self, data, "Ingest response")
        _assert_no_forbidden_values(self, json.dumps(data, default=str))
        _assert_no_raw_uuid(self, json.dumps(data, default=str))

    def test_06_backend_list_finds_event_by_creative_code(self):
        """Step 7: list_kso_pop_events finds event by creative_code filter."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        from app.domains.proof_of_play.service import ingest_kso_pop, list_kso_pop_events

        unique = f"{self.EVENT}-list"
        async def _do():
            db = TestSession()
            async with db as session:
                req = KsoPoPIngestRequest(
                    event_code=unique, media_ref=self.MEDIA_REF,
                    event_type="playback_completed", duration_ms=15000,
                )
                await ingest_kso_pop(session, self.DEV, req)
                await session.commit()
                rows = await list_kso_pop_events(session, creative_code=self.CC)
                return rows
        rows = _run_async(_do())
        self.assertGreaterEqual(len(rows), 1)
        found = [r for r in rows if r.event_code == unique]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].creative_code, self.CC)
        self.assertEqual(found[0].device_code, self.DEV)
        self.assertEqual(found[0].campaign_code, self.CAMP)
        self.assertEqual(found[0].placement_code, self.PLACE)

        for r in found:
            _assert_no_forbidden_keys(self, r.model_dump(), "List response")
        _assert_no_forbidden_values(
            self, json.dumps([r.model_dump(mode="json") for r in rows], default=str),
        )

    def test_07_full_creative_code_trace(self):
        """Trace creative_code through all 6 stages."""
        from kso_player.screensaver_pop_bridge import build_screensaver_event_code
        from kso_sidecar_agent.pop_pickup import classify_pop_event, CLASS_ELIGIBLE
        from kso_sidecar_agent.pop_payload import PopPayloadEvent
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        from app.domains.proof_of_play.service import ingest_kso_pop, list_kso_pop_events

        t_cc = "e2e-trace-cc-2025"
        t_dev = "e2e-trace-dev"
        t_camp = "e2e-trace-camp"
        t_place = "e2e-trace-place"
        t_manifest = "e2e-trace-manifest"
        t_event = "e2e-trace-event"

        _run_async(_seed_backend(
            device_code=t_dev, creative_code=t_cc,
            campaign_code=t_camp, placement_code=t_place,
            manifest_code=t_manifest,
        ))

        # Stage 1: PoP draft
        draft = _make_draft(t_cc)
        self.assertEqual(draft.creative_code, t_cc, "Stage 1: PoP draft")

        # Stage 2: JSONL record
        result = _build_record(draft)
        rec = result._record
        self.assertEqual(rec["creative_code"], t_cc, "Stage 2: JSONL record")

        # Stage 3: Sidecar classify
        manifest_items = [{"order": 0, "content_type": "image/png"}]
        classification = classify_pop_event(
            rec, manifest_items=manifest_items, media_cache_complete=True,
        )
        self.assertEqual(classification.classification, CLASS_ELIGIBLE, "Stage 3: classify")
        self.assertTrue(classification.backend_eligible)

        # Stage 4: Payload
        payload = PopPayloadEvent(
            device_event_id=uuid4().hex,
            played_at=rec.get("started_at"),
            duration_ms=rec.get("duration_ms", 0),
            play_status="completed",
            selected_order=rec.get("selected_order"),
            selected_content_type=rec.get("selected_content_type"),
            creative_code=rec.get("creative_code"),
        )
        self.assertEqual(payload.creative_code, t_cc, "Stage 4: payload")

        # Stage 5: Backend ingest
        async def _ingest():
            db = TestSession()
            async with db as session:
                req = KsoPoPIngestRequest(
                    event_code=t_event, media_ref=self.MEDIA_REF,
                    event_type="playback_completed", duration_ms=15000,
                )
                resp, err = await ingest_kso_pop(session, t_dev, req)
                await session.commit()
                return resp, err
        resp, err = _run_async(_ingest())
        self.assertIsNone(err, f"Stage 5 error: {err}")
        self.assertEqual(resp.creative_code, t_cc, "Stage 5: backend ingest")

        # Stage 6: Report filter
        async def _list():
            db = TestSession()
            async with db as session:
                return await list_kso_pop_events(session, creative_code=t_cc)
        rows = _run_async(_list())
        self.assertGreaterEqual(len(rows), 1, "Stage 6: report list")
        self.assertEqual(rows[0].creative_code, t_cc, "Stage 6: report filter")


# ══════════════════════════════════════════════════════════════════════
# Negative paths
# ══════════════════════════════════════════════════════════════════════

class TestE2ENegativePaths(unittest.TestCase):
    """Blocked/draft events don't reach backend as completed."""

    CC = "e2e-neg-creative"
    DEV = "e2e-neg-device"
    CAMP = "e2e-neg-camp"
    PLACE = "e2e-neg-place"
    MANIFEST = "e2e-neg-manifest"

    @classmethod
    def setUpClass(cls):
        _run_async(_init_db())
        _run_async(_seed_backend(
            device_code=cls.DEV, creative_code=cls.CC,
            campaign_code=cls.CAMP, placement_code=cls.PLACE,
            manifest_code=cls.MANIFEST,
        ))

    def test_media_available_false_becomes_blocked(self):
        """media_available=False → blocked event, not eligible."""
        from kso_sidecar_agent.pop_pickup import classify_pop_event, CLASS_DRAFT

        draft = _make_draft(self.CC, media_available=False)
        result = _build_record(draft)
        self.assertTrue(result.built)
        self.assertEqual(result.event_type, "blocked", "media_available=False → blocked")
        self.assertEqual(result.event_status, "draft", "blocked → draft")

        rec = result._record
        manifest_items = [{"order": 0, "content_type": "image/png"}]
        classification = classify_pop_event(
            rec, manifest_items=manifest_items, media_cache_complete=True,
        )
        self.assertEqual(classification.classification, CLASS_DRAFT,
                         "Blocked → CLASS_DRAFT, not eligible")
        self.assertFalse(classification.backend_eligible)

    def test_non_idle_safety_state_quarantined(self):
        """non-idle safety_state → quarantined by sidecar."""
        from kso_sidecar_agent.pop_pickup import classify_pop_event

        draft = _make_draft(self.CC)
        result = _build_record(draft, safety_state="transaction")
        self.assertTrue(result.built)

        rec = result._record
        manifest_items = [{"order": 0, "content_type": "image/png"}]
        classification = classify_pop_event(
            rec, manifest_items=manifest_items, media_cache_complete=True,
        )
        self.assertEqual(classification.classification, "quarantine",
                         f"non-idle → quarantine, got {classification.classification}: {classification.reason}")
        self.assertFalse(classification.backend_eligible)

    def test_duplicate_event_code_idempotent(self):
        """Duplicate event_code → idempotent accepted."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        from app.domains.proof_of_play.service import ingest_kso_pop

        async def _do():
            db = TestSession()
            async with db as session:
                req = KsoPoPIngestRequest(
                    event_code="e2e-neg-dup", media_ref="media/current/slot-000",
                    event_type="playback_completed", duration_ms=15000,
                )
                r1, e1 = await ingest_kso_pop(session, self.DEV, req)
                await session.commit()
                r2, e2 = await ingest_kso_pop(session, self.DEV, req)
                await session.commit()
                return r1, e1, r2, e2
        r1, e1, r2, e2 = _run_async(_do())
        self.assertIsNone(e1)
        self.assertIsNone(e2)
        self.assertEqual(r1.status, "accepted")
        self.assertEqual(r2.status, "accepted")

    def test_unknown_media_ref_rejected(self):
        """media_ref not in manifest → safe reject."""
        from app.domains.proof_of_play.schemas import KsoPoPIngestRequest
        from app.domains.proof_of_play.service import ingest_kso_pop

        async def _do():
            db = TestSession()
            async with db as session:
                req = KsoPoPIngestRequest(
                    event_code="e2e-neg-unknown-media",
                    media_ref="media/current/no-such-slot",
                    event_type="playback_completed",
                )
                return await ingest_kso_pop(session, self.DEV, req)
        resp, err = _run_async(_do())
        self.assertIsNone(resp)
        self.assertEqual(err, "unknown_media_ref")

    def test_missing_creative_code_produces_empty(self):
        """Missing creative_code → empty string in bridge."""
        draft = _make_draft("")  # empty creative_code
        result = _build_record(draft)
        self.assertTrue(result.built)
        self.assertEqual(result.creative_code, "")


# ══════════════════════════════════════════════════════════════════════
# Component-level safety audit (6 surfaces)
# ══════════════════════════════════════════════════════════════════════

class TestE2ESecurityAudit(unittest.TestCase):
    """All output surfaces verified — no forbidden fields."""

    def test_surface_1_screensaver_pop_record_result(self):
        """ScreensaverPopRecordResult.to_safe_dict()"""
        from kso_player.screensaver_pop_bridge import ScreensaverPopRecordResult
        r = ScreensaverPopRecordResult(
            built=True, reason="built", event_type="playback_completed",
            event_status="completed", creative_code="safe-cc",
        )
        data = r.to_safe_dict()
        _assert_no_forbidden_keys(self, data, "ScreensaverPopRecordResult")
        _assert_no_forbidden_values(self, json.dumps(data))

    def test_surface_2_pop_write_result(self):
        """PopWriteResult"""
        from kso_player.pop_writer import PopWriteResult
        r = PopWriteResult(status="written", written=True, reason="written",
                           event_type="would_play", event_status="completed")
        data = {k: getattr(r, k) for k in [
            "status", "written", "reason", "event_type", "event_status", "line_size_bytes",
        ]}
        _assert_no_forbidden_keys(self, data, "PopWriteResult")
        _assert_no_forbidden_values(self, json.dumps(data))

    def test_surface_3_pop_pickup_scan_result(self):
        """PopPickupScanResult"""
        from kso_sidecar_agent.pop_pickup import PopPickupScanResult
        r = PopPickupScanResult(
            status="ok", total_lines=10, valid_events=9, invalid_lines=1,
            draft_events=3, eligible_events=2, diagnostic_events=1,
            quarantine_events=1, backend_eligible_events=2,
        )
        data = {k: getattr(r, k) for k in [
            "status", "total_lines", "valid_events", "invalid_lines",
            "draft_events", "eligible_events", "diagnostic_events",
            "quarantine_events", "backend_eligible_events",
        ]}
        _assert_no_forbidden_keys(self, data, "PopPickupScanResult")
        _assert_no_forbidden_values(self, json.dumps(data))

    def test_surface_4_pop_payload_build_result(self):
        """PopPayloadBuildResult"""
        from kso_sidecar_agent.pop_payload import PopPayloadBuildResult
        r = PopPayloadBuildResult(
            status="ok", payload_events=2, skipped_events=1,
            invalid_events=0, quarantine_events=0, diagnostic_events=0,
            draft_events=1, batch_limited=False, max_events=100,
        )
        data = {k: getattr(r, k) for k in [
            "status", "payload_events", "skipped_events", "invalid_events",
            "quarantine_events", "diagnostic_events", "draft_events",
            "batch_limited", "max_events",
        ]}
        _assert_no_forbidden_keys(self, data, "PopPayloadBuildResult")
        _assert_no_forbidden_values(self, json.dumps(data))

    def test_surface_5_ingest_response(self):
        """KsoPoPIngestResponse"""
        from app.domains.proof_of_play.schemas import KsoPoPIngestResponse
        resp = KsoPoPIngestResponse(
            status="accepted", event_code="safe", device_code="dev",
            placement_code="place", campaign_code="camp", creative_code="cc",
            received_at=datetime.now(timezone.utc),
        )
        data = resp.model_dump()
        _assert_no_forbidden_keys(self, data, "KsoPoPIngestResponse")
        _assert_no_forbidden_values(self, json.dumps(data, default=str))

    def test_surface_6_list_response(self):
        """KsoPoPListResponse"""
        from app.domains.proof_of_play.schemas import KsoPoPListResponse
        resp = KsoPoPListResponse(
            event_code="safe", device_code="dev", placement_code="place",
            campaign_code="camp", creative_code="cc", media_ref="m1",
            event_type="impression", status="accepted",
            received_at=datetime.now(timezone.utc),
        )
        data = resp.model_dump()
        _assert_no_forbidden_keys(self, data, "KsoPoPListResponse")
        _assert_no_forbidden_values(self, json.dumps(data, default=str))

    def test_surface_7_full_jsonl_record(self):
        """Actual JSONL record built from screensaver pop bridge."""
        draft = _make_draft("security-audit-cc")
        result = _build_record(draft)
        rec = result._record
        _assert_no_forbidden_keys(self, rec, "Full JSONL record")
        _assert_no_forbidden_values(self, json.dumps(rec))
        _assert_no_raw_uuid(self, json.dumps(rec))
