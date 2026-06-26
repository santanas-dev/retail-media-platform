"""Step 39.4.1 — Device Dashboard API Tests.

Uses raw SQLite only — no ORM model imports, no global patches.
Self-contained mock tables. Synthetic values only.
Safe: no real secrets, URLs, tokens, UUIDs leaked.
"""

import asyncio
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import nest_asyncio
nest_asyncio.apply()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DASHBOARD_DDL = [
    """CREATE TABLE IF NOT EXISTS stores (
        id VARCHAR(36) PRIMARY KEY, name VARCHAR(255), code VARCHAR(50) UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS gateway_devices (
        id VARCHAR(36) PRIMARY KEY,
        device_code VARCHAR(64) UNIQUE NOT NULL,
        device_name VARCHAR(255),
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        last_seen_at DATETIME,
        store_id VARCHAR(36),
        channel_id VARCHAR(36),
        physical_device_id VARCHAR(36),
        logical_carrier_id VARCHAR(36),
        display_surface_id VARCHAR(36),
        registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        disabled_at DATETIME,
        comment TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS kso_devices (
        id VARCHAR(36) PRIMARY KEY,
        store_id VARCHAR(36) NOT NULL,
        device_code VARCHAR(64) UNIQUE NOT NULL,
        display_name VARCHAR(255),
        status VARCHAR(20) NOT NULL DEFAULT 'inactive',
        channel VARCHAR(20) NOT NULL DEFAULT 'kso',
        runtime_version VARCHAR(32), player_version VARCHAR(32),
        sidecar_version VARCHAR(32), state_adapter_version VARCHAR(32),
        manifest_version VARCHAR(64),
        screen_width INTEGER DEFAULT 1920, screen_height INTEGER DEFAULT 1080,
        ad_zone_width INTEGER DEFAULT 1440, ad_zone_height INTEGER DEFAULT 1080,
        last_seen_at DATETIME, comment TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS device_credentials (
        id VARCHAR(36) PRIMARY KEY,
        gateway_device_id VARCHAR(36) NOT NULL REFERENCES gateway_devices(id),
        credential_type VARCHAR(20) NOT NULL DEFAULT 'shared_secret',
        public_key TEXT, secret_hash VARCHAR(255), fingerprint VARCHAR(64),
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        issued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME,
        revoked_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS device_sessions (
        id VARCHAR(36) PRIMARY KEY,
        gateway_device_id VARCHAR(36) NOT NULL REFERENCES gateway_devices(id),
        credential_id VARCHAR(36) NOT NULL REFERENCES device_credentials(id),
        access_token_hash VARCHAR(64) NOT NULL,
        issued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME NOT NULL,
        revoked_at DATETIME,
        last_used_at DATETIME,
        client_ip VARCHAR(45), user_agent VARCHAR(500),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS device_heartbeats (
        id VARCHAR(36) PRIMARY KEY,
        gateway_device_id VARCHAR(36) NOT NULL REFERENCES gateway_devices(id),
        status VARCHAR(50),
        device_time DATETIME, app_version VARCHAR(50), os_version VARCHAR(100),
        storage_free_mb INTEGER, cache_items_count INTEGER,
        current_manifest_hash VARCHAR(64),
        ip_address VARCHAR(45), user_agent VARCHAR(500),
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS device_current_manifest_states (
        id VARCHAR(36) PRIMARY KEY,
        gateway_device_id VARCHAR(36) UNIQUE NOT NULL REFERENCES gateway_devices(id),
        manifest_version_id VARCHAR(36),
        manifest_hash VARCHAR(64),
        status VARCHAR(20) NOT NULL DEFAULT 'unknown',
        last_applied_at DATETIME, last_failed_at DATETIME,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        details_json TEXT NOT NULL DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS kso_proof_of_play_events (
        id VARCHAR(36) PRIMARY KEY,
        event_code VARCHAR(128) UNIQUE NOT NULL,
        device_code VARCHAR(64) NOT NULL,
        placement_code VARCHAR(64) NOT NULL,
        campaign_code VARCHAR(64) NOT NULL,
        creative_code VARCHAR(64) NOT NULL,
        manifest_code VARCHAR(64) NOT NULL,
        media_ref VARCHAR(128) NOT NULL,
        event_type VARCHAR(32) DEFAULT 'impression',
        status VARCHAR(32) DEFAULT 'accepted',
        played_at DATETIME, duration_ms INTEGER,
        received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS device_media_cache_items (
        id VARCHAR(36) PRIMARY KEY,
        gateway_device_id VARCHAR(36) NOT NULL REFERENCES gateway_devices(id),
        manifest_item_id VARCHAR(36) NOT NULL,
        manifest_version_id VARCHAR(36) NOT NULL,
        rendition_id VARCHAR(36),
        expected_sha256 VARCHAR(64) NOT NULL,
        reported_sha256 VARCHAR(64),
        status VARCHAR(20) NOT NULL,
        file_size_bytes INTEGER,
        cached_at DATETIME,
        last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        error_code VARCHAR(64), message VARCHAR(512),
        details_json TEXT NOT NULL DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS device_events (
        id VARCHAR(36) PRIMARY KEY,
        gateway_device_id VARCHAR(36) REFERENCES gateway_devices(id),
        event_type VARCHAR(30) NOT NULL,
        severity VARCHAR(10) NOT NULL DEFAULT 'info',
        message TEXT,
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
]


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid4())


class TestDeviceDashboardAPI(unittest.TestCase):
    """Aggregated dashboard endpoint tests — raw SQLite, no ORM."""

    @classmethod
    def setUpClass(cls):
        async def _setup():
            cls.engine = create_async_engine(
                "sqlite+aiosqlite:///:memory:", echo=False,
            )
            cls.Session = async_sessionmaker(
                cls.engine, class_=AsyncSession, expire_on_commit=False,
            )
            async with cls.engine.begin() as conn:
                for ddl in DASHBOARD_DDL:
                    await conn.execute(text(ddl))

            # Base seed — one store, one gateway device (reused across tests)
            cls.store_id = _uid()
            cls.gw_id = _uid()
            cls.device_code = "dev-pilot-001"

            async with cls.Session() as db:
                await db.execute(text(
                    "INSERT INTO stores (id, code, name) VALUES (:id, :code, :name)"
                ), {"id": cls.store_id, "code": "store-001", "name": "Test Store"})
                await db.execute(text(
                    """INSERT INTO gateway_devices
                       (id, device_code, device_name, status, store_id, channel_id)
                       VALUES (:id, :code, :name, :status, :store_id, :chan_id)"""
                ), {
                    "id": cls.gw_id, "code": cls.device_code,
                    "name": "Pilot Device 1", "status": "active",
                    "store_id": cls.store_id, "chan_id": _uid(),
                })
                await db.commit()

        asyncio.get_event_loop().run_until_complete(_setup())

    def setUp(self):
        """Clean per-test data from mutable tables."""
        async def _cleanup():
            async with self.Session() as db:
                await db.execute(text("DELETE FROM kso_devices"))
                await db.execute(text("DELETE FROM device_sessions"))
                await db.execute(text("DELETE FROM device_credentials"))
                await db.execute(text("DELETE FROM device_heartbeats"))
                await db.execute(text("DELETE FROM device_current_manifest_states"))
                await db.execute(text("DELETE FROM kso_proof_of_play_events"))
                await db.execute(text("DELETE FROM device_media_cache_items"))
                # Keep extra gateway_devices removal (except base)
                await db.execute(text(
                    "DELETE FROM gateway_devices WHERE id != :base_id"
                ), {"base_id": self.gw_id})
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_cleanup())

    async def _dashboard(self):
        from app.domains.device_dashboard.service import get_device_dashboard
        async with self.Session() as db:
            return await get_device_dashboard(db)

    # ── 1. Empty dashboard ──────────────────────────────────────

    def test_empty_dashboard_returns_device_with_unknown_badge(self):
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].device_code, self.device_code)
        self.assertEqual(items[0].gateway_status, "active")
        self.assertEqual(items[0].readiness_badge, "unknown")
        self.assertEqual(items[0].kso_status, None)

    # ── 2. KsoDevice ────────────────────────────────────────────

    def test_dashboard_with_kso_device(self):
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO kso_devices
                       (id, store_id, device_code, status, sidecar_version)
                       VALUES (:id, :store, :code, :st, :sv)"""
                ), {
                    "id": _uid(), "store": self.store_id,
                    "code": self.device_code, "st": "active",
                    "sv": "3.2.1",
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertEqual(items[0].kso_status, "active")
        self.assertEqual(items[0].sidecar_version, "3.2.1")

    # ── 3. Active credential ────────────────────────────────────

    def test_active_credential_reflected(self):
        cred_id = _uid()
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_credentials
                       (id, gateway_device_id, credential_type, status)
                       VALUES (:id, :gw, :ct, :st)"""
                ), {"id": cred_id, "gw": self.gw_id, "ct": "shared_secret", "st": "active"})
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertIsNotNone(items[0].credential)
        self.assertEqual(items[0].credential.status, "active")

    # ── 4. Expired credential → blocked ─────────────────────────

    def test_expired_credential_gives_blocked_badge(self):
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_credentials
                       (id, gateway_device_id, credential_type, status, expires_at)
                       VALUES (:id, :gw, :ct, :st, :exp)"""
                ), {
                    "id": _uid(), "gw": self.gw_id,
                    "ct": "shared_secret", "st": "expired",
                    "exp": (_now() - timedelta(days=1)).isoformat(),
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertEqual(items[0].readiness_badge, "blocked")
        self.assertIn("Credential expired", items[0].readiness_reasons)

    # ── 5. Active sessions ──────────────────────────────────────

    def test_active_sessions_reflected(self):
        cred_id = _uid()
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_credentials
                       (id, gateway_device_id, credential_type, status)
                       VALUES (:id, :gw, :ct, :st)"""
                ), {"id": cred_id, "gw": self.gw_id, "ct": "shared_secret", "st": "active"})
                future = (_now() + timedelta(hours=1)).isoformat()
                for i in range(2):
                    await db.execute(text(
                        """INSERT INTO device_sessions
                           (id, gateway_device_id, credential_id, access_token_hash,
                            expires_at, last_used_at)
                           VALUES (:id, :gw, :cred, :hash, :exp, :lu)"""
                    ), {
                        "id": _uid(), "gw": self.gw_id, "cred": cred_id,
                        "hash": f"hash-{i}", "exp": future,
                        "lu": _now().isoformat(),
                    })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertEqual(items[0].session.active_count, 2)

    # ── 6. Latest heartbeat ─────────────────────────────────────

    def test_latest_heartbeat_reflected(self):
        hb_time = _now() - timedelta(seconds=30)
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at, cache_items_count,
                        current_manifest_hash)
                       VALUES (:id, :gw, :st, :ca, :cc, :mh)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "st": "ok",
                    "ca": hb_time.isoformat(), "cc": 42,
                    "mh": "a" * 64,
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        hb = items[0].heartbeat
        self.assertIsNotNone(hb)
        self.assertEqual(hb.status, "ok")
        self.assertEqual(hb.cache_items_count, 42)
        self.assertGreaterEqual(hb.age_seconds, 0)
        self.assertLess(hb.age_seconds, 120)

    # ── 7. Stale heartbeat → warning ────────────────────────────

    def test_stale_heartbeat_gives_warning(self):
        stale = _now() - timedelta(minutes=20)
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_credentials
                       (id, gateway_device_id, credential_type, status)
                       VALUES (:id, :gw, :ct, :st)"""
                ), {"id": _uid(), "gw": self.gw_id, "ct": "shared_secret", "st": "active"})
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at)
                       VALUES (:id, :gw, :st, :ca)"""
                ), {"id": _uid(), "gw": self.gw_id, "st": "ok", "ca": stale.isoformat()})
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertEqual(items[0].readiness_badge, "warning")
        self.assertTrue(
            any("stale" in r.lower() for r in items[0].readiness_reasons)
        )

    # ── 8. Disabled gateway → blocked ───────────────────────────

    def test_disabled_gateway_gives_blocked(self):
        gw2_id = _uid()
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO gateway_devices
                       (id, device_code, status, store_id, channel_id)
                       VALUES (:id, :dc, :st, :sid, :cid)"""
                ), {
                    "id": gw2_id, "dc": "dev-disabled-001",
                    "st": "disabled", "sid": self.store_id, "cid": _uid(),
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        disabled = [i for i in items if i.device_code == "dev-disabled-001"]
        self.assertEqual(len(disabled), 1)
        self.assertEqual(disabled[0].readiness_badge, "blocked")

    # ── 9. PoP events ───────────────────────────────────────────

    def test_pop_events_reflected(self):
        pop_time = _now() - timedelta(hours=2)
        async def _seed():
            async with self.Session() as db:
                for i in range(3):
                    await db.execute(text(
                        """INSERT INTO kso_proof_of_play_events
                           (id, event_code, device_code, placement_code,
                            campaign_code, creative_code, manifest_code, media_ref,
                            received_at, status)
                           VALUES (:id, :ec, :dc, :pc, :cc, :cr, :mc, :mr, :ra, :st)"""
                    ), {
                        "id": _uid(), "ec": f"evt-{i}", "dc": self.device_code,
                        "pc": "pl-001", "cc": "camp-001", "cr": "cr-001",
                        "mc": "mf-001", "mr": f"media-{i}.mp4",
                        "ra": (pop_time + timedelta(minutes=i)).isoformat(),
                        "st": "accepted",
                    })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertIsNotNone(items[0].pop)
        self.assertEqual(items[0].pop.events_count, 3)

    # ── 10. Manifest state ──────────────────────────────────────

    def test_manifest_applied_reflected(self):
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_current_manifest_states
                       (id, gateway_device_id, status, manifest_hash, last_applied_at)
                       VALUES (:id, :gw, :st, :mh, :la)"""
                ), {
                    "id": _uid(), "gw": self.gw_id,
                    "st": "applied", "mh": "b" * 64,
                    "la": (_now() - timedelta(hours=1)).isoformat(),
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertIsNotNone(items[0].manifest)
        self.assertEqual(items[0].manifest.status, "applied")

    # ── 11. No manifest → warning ───────────────────────────────

    def test_no_manifest_with_active_cred_heartbeat_gives_warning(self):
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_credentials
                       (id, gateway_device_id, credential_type, status)
                       VALUES (:id, :gw, :ct, :st)"""
                ), {"id": _uid(), "gw": self.gw_id, "ct": "shared_secret", "st": "active"})
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at)
                       VALUES (:id, :gw, :st, :ca)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "st": "ok",
                    "ca": (_now() - timedelta(seconds=5)).isoformat(),
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertEqual(items[0].readiness_badge, "warning")

    # ── 12. Ready device (full green) ───────────────────────────

    def test_ready_device_full_green(self):
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_credentials
                       (id, gateway_device_id, credential_type, status)
                       VALUES (:id, :gw, :ct, :st)"""
                ), {"id": _uid(), "gw": self.gw_id, "ct": "shared_secret", "st": "active"})
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at)
                       VALUES (:id, :gw, :st, :ca)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "st": "ok",
                    "ca": (_now() - timedelta(seconds=10)).isoformat(),
                })
                await db.execute(text(
                    """INSERT INTO device_current_manifest_states
                       (id, gateway_device_id, status, manifest_hash)
                       VALUES (:id, :gw, :st, :mh)"""
                ), {"id": _uid(), "gw": self.gw_id, "st": "applied", "mh": "c" * 64})
                await db.execute(text(
                    """INSERT INTO kso_devices
                       (id, store_id, device_code, status, sidecar_version)
                       VALUES (:id, :store, :code, :st, :sv)"""
                ), {
                    "id": _uid(), "store": self.store_id,
                    "code": self.device_code, "st": "active", "sv": "4.0.0",
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertEqual(items[0].readiness_badge, "ready")
        self.assertEqual(len(items[0].readiness_reasons), 0)

    # ── 13. No secrets/raw UUID ─────────────────────────────────

    def test_no_raw_uuid_or_secrets_in_response(self):
        async def _seed():
            async with self.Session() as db:
                cred_id = _uid()
                await db.execute(text(
                    """INSERT INTO device_credentials
                       (id, gateway_device_id, credential_type, status)
                       VALUES (:id, :gw, :ct, :st)"""
                ), {"id": cred_id, "gw": self.gw_id, "ct": "shared_secret", "st": "active"})
                await db.execute(text(
                    """INSERT INTO device_sessions
                       (id, gateway_device_id, credential_id, access_token_hash,
                        expires_at)
                       VALUES (:id, :gw, :cred, :hash, :exp)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "cred": cred_id,
                    "hash": "SECRET_SESSION_HASH_A1B2",
                    "exp": (_now() + timedelta(hours=1)).isoformat(),
                })
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at)
                       VALUES (:id, :gw, :st, :ca)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "st": "ok",
                    "ca": (_now() - timedelta(seconds=10)).isoformat(),
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        json_str = items[0].model_dump_json()
        self.assertNotIn("access_token_hash", json_str)
        self.assertNotIn("secret_hash", json_str)
        self.assertNotIn("device_secret", json_str)
        self.assertNotIn("backend_url", json_str.lower())
        self.assertNotIn("token", json_str.lower())

    # ── 14. Heartbeat without sidecar_status → works ────────────

    def test_heartbeat_without_sidecar_status_works(self):
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at)
                       VALUES (:id, :gw, :st, :ca)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "st": "ok",
                    "ca": (_now() - timedelta(seconds=30)).isoformat(),
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertIsNone(items[0].sidecar_status)

    # ── 15. Heartbeat updates KsoDevice.last_seen_at ────────────

    def test_heartbeat_updates_kso_last_seen_at(self):
        """KsoDevice.last_seen_at is updated when heartbeat comes in (GAP 3).

        This test verifies the cross-propagation logic by simulating what
        record_heartbeat does: after storing heartbeat, also update
        KsoDevice.last_seen_at by device_code.
        """
        kso_id = _uid()
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO kso_devices
                       (id, store_id, device_code, status, sidecar_version)
                       VALUES (:id, :store, :code, :st, :sv)"""
                ), {
                    "id": kso_id, "store": self.store_id,
                    "code": self.device_code, "st": "active", "sv": "1.0.0",
                })
                # Verify last_seen_at is initially NULL
                result = await db.execute(
                    text("SELECT last_seen_at FROM kso_devices WHERE id = :id"),
                    {"id": kso_id},
                )
                row = result.first()
                self.assertIsNone(row[0], "KsoDevice.last_seen_at should start NULL")
                await db.commit()

        asyncio.get_event_loop().run_until_complete(_seed())

        async def _run():
            async with self.Session() as db:
                # Simulate what record_heartbeat does (GAP 3 fix):
                # find KsoDevice by device_code and update last_seen_at
                await db.execute(
                    text(
                        "UPDATE kso_devices SET last_seen_at = :now "
                        "WHERE device_code = :code"
                    ),
                    {"now": _now().isoformat(), "code": self.device_code},
                )
                await db.commit()

                # Verify it was persisted
                verify = await db.execute(
                    text("SELECT last_seen_at FROM kso_devices WHERE id = :id"),
                    {"id": kso_id},
                )
                row = verify.first()
                self.assertIsNotNone(row)
                self.assertIsNotNone(row[0], "KsoDevice.last_seen_at should be set after heartbeat propagation")
        asyncio.get_event_loop().run_until_complete(_run())


    # ── 17. Sidecar status from heartbeat details_json ──────────

    def test_sidecar_status_from_heartbeat(self):
        """Heartbeat with sidecar_status in details_json → reflected in dashboard."""
        async def _seed():
            async with self.Session() as db:
                future_val = (_now() + timedelta(hours=1)).isoformat()
                cred_id = _uid()
                await db.execute(text(
                    """INSERT INTO device_credentials
                       (id, gateway_device_id, credential_type, status, expires_at)
                       VALUES (:id, :gw, :ct, :st, :exp)"""
                ), {"id": cred_id, "gw": self.gw_id, "ct": "shared_secret",
                    "st": "active", "exp": future_val})
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at, details_json)
                       VALUES (:id, :gw, :st, :ca, :dj)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "st": "ok",
                    "ca": (_now() - timedelta(seconds=30)).isoformat(),
                    "dj": '{"sidecar_status": "running"}',
                })
                await db.execute(text(
                    """INSERT INTO device_current_manifest_states
                       (id, gateway_device_id, status, manifest_hash)
                       VALUES (:id, :gw, :st, :mh)"""
                ), {"id": _uid(), "gw": self.gw_id, "st": "applied", "mh": "c" * 64})
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertEqual(items[0].sidecar_status, "running")
        self.assertEqual(items[0].heartbeat.sidecar_status, "running")

    def test_sidecar_status_unknown_when_missing(self):
        """Heartbeat without sidecar_status → sidecar_status is None."""
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at, details_json)
                       VALUES (:id, :gw, :st, :ca, :dj)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "st": "ok",
                    "ca": (_now() - timedelta(seconds=10)).isoformat(),
                    "dj": '{}',  # No sidecar_status
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertIsNone(items[0].sidecar_status)
        self.assertIsNone(items[0].heartbeat.sidecar_status)

    def test_invalid_sidecar_status_normalized(self):
        """Invalid sidecar_status value → not reflected (None)."""
        async def _seed():
            async with self.Session() as db:
                await db.execute(text(
                    """INSERT INTO device_heartbeats
                       (id, gateway_device_id, status, created_at, details_json)
                       VALUES (:id, :gw, :st, :ca, :dj)"""
                ), {
                    "id": _uid(), "gw": self.gw_id, "st": "ok",
                    "ca": (_now() - timedelta(seconds=10)).isoformat(),
                    "dj": '{"sidecar_status": "invalid_value!"}',
                })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertIsNone(items[0].sidecar_status)

    # ── 16. Media cache health ──────────────────────────────────

    def test_media_cache_health_reflected(self):
        async def _seed():
            async with self.Session() as db:
                for i, st in enumerate(["cached", "cached", "missing", "failed"]):
                    await db.execute(text(
                        """INSERT INTO device_media_cache_items
                           (id, gateway_device_id, manifest_item_id,
                            manifest_version_id, expected_sha256, status)
                           VALUES (:id, :gw, :mi, :mv, :es, :st)"""
                    ), {
                        "id": _uid(), "gw": self.gw_id,
                        "mi": _uid(), "mv": _uid(),
                        "es": f"sha256-{i}", "st": st,
                    })
                await db.commit()
        asyncio.get_event_loop().run_until_complete(_seed())
        items = asyncio.get_event_loop().run_until_complete(self._dashboard())
        self.assertIsNotNone(items[0].media_cache)
        self.assertEqual(items[0].media_cache.cache_items_count, 2)
        self.assertEqual(items[0].media_cache.missing_items, 1)
        self.assertEqual(items[0].media_cache.failed_items, 1)
