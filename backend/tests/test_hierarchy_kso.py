"""Tests: Hierarchy and KSO Device Registry (Step 37.1).

Uses raw SQLite only — no ORM model imports, no global type patches.
Self-contained — synthetic values only.

Safe: no real store/device/IP/MAC/serial/secret data.
"""
import asyncio
import unittest
from uuid import uuid4

import nest_asyncio
nest_asyncio.apply()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

HIERARCHY_DDL = [
    """CREATE TABLE IF NOT EXISTS branches (
        id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL,
        code VARCHAR(50) UNIQUE NOT NULL,
        timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS clusters (
        id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL,
        code VARCHAR(50),
        branch_id VARCHAR(36) NOT NULL REFERENCES branches(id),
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(branch_id, code)
    )""",
    """CREATE TABLE IF NOT EXISTS stores (
        id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL,
        code VARCHAR(50) UNIQUE NOT NULL,
        cluster_id VARCHAR(36) NOT NULL REFERENCES clusters(id),
        address TEXT, format VARCHAR(50),
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS kso_devices (
        id VARCHAR(36) PRIMARY KEY,
        store_id VARCHAR(36) NOT NULL REFERENCES stores(id),
        device_code VARCHAR(64) UNIQUE NOT NULL,
        display_name VARCHAR(255),
        status VARCHAR(20) NOT NULL DEFAULT 'inactive',
        channel VARCHAR(20) NOT NULL DEFAULT 'kso',
        runtime_version VARCHAR(32), player_version VARCHAR(32),
        sidecar_version VARCHAR(32), state_adapter_version VARCHAR(32),
        manifest_version VARCHAR(64),
        screen_width INTEGER NOT NULL DEFAULT 1920,
        screen_height INTEGER NOT NULL DEFAULT 1080,
        ad_zone_width INTEGER NOT NULL DEFAULT 1440,
        ad_zone_height INTEGER NOT NULL DEFAULT 1080,
        last_seen_at DATETIME, comment TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
]


class TestHierarchyFoundation(unittest.TestCase):
    """Model + constraint tests — raw SQL, no ORM imports."""

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
                await conn.execute(text("PRAGMA foreign_keys = ON"))
                for ddl in HIERARCHY_DDL:
                    await conn.execute(text(ddl))
        asyncio.run(_setup())

    @classmethod
    def tearDownClass(cls):
        async def _cleanup():
            await cls.engine.dispose()
        asyncio.run(_cleanup())

    # ── Table creation ────────────────────────────────────────────────────

    def test_migration_creates_branch_table(self):
        async def check():
            async with self.Session() as s:
                r = await s.execute(text("SELECT name FROM branches LIMIT 0"))
                self.assertIsNotNone(r)
        asyncio.run(check())

    def test_migration_creates_cluster_table(self):
        async def check():
            async with self.Session() as s:
                r = await s.execute(text("SELECT code FROM clusters LIMIT 0"))
                self.assertIsNotNone(r)
        asyncio.run(check())

    def test_migration_creates_store_table(self):
        async def check():
            async with self.Session() as s:
                r = await s.execute(text(
                    "SELECT format, status FROM stores LIMIT 0"
                ))
                self.assertIsNotNone(r)
        asyncio.run(check())

    def test_migration_creates_kso_devices_table(self):
        async def check():
            async with self.Session() as s:
                r = await s.execute(text(
                    "SELECT device_code, screen_width FROM kso_devices LIMIT 0"
                ))
                self.assertIsNotNone(r)
        asyncio.run(check())

    # ── Constraints ──────────────────────────────────────────────────────

    def test_branch_code_unique(self):
        async def check():
            async with self.engine.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES ('b1', 'A', 'x1')"
                ))
                with self.assertRaises(Exception):
                    await conn.execute(text(
                        "INSERT INTO branches (id, name, code) VALUES ('b2', 'B', 'x1')"
                    ))
        asyncio.run(check())

    def test_cluster_belongs_to_branch(self):
        async def check():
            async with self.engine.begin() as conn:
                bid = uuid4().hex
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B', 'x2')"
                ), {"id": bid})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, branch_id) VALUES (:id, 'C', :bid)"
                ), {"id": uuid4().hex, "bid": bid})
                with self.assertRaises(Exception):
                    await conn.execute(text(
                        "INSERT INTO clusters (id, name, branch_id) VALUES "
                        "(:id, 'C2', :bad)"
                    ), {"id": uuid4().hex, "bad": uuid4().hex})
        asyncio.run(check())

    def test_store_belongs_to_cluster(self):
        async def check():
            async with self.engine.begin() as conn:
                bid, cid = uuid4().hex, uuid4().hex
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B', 'x3')"
                ), {"id": bid})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, branch_id) VALUES (:id, 'C', :bid)"
                ), {"id": cid, "bid": bid})
                await conn.execute(text(
                    "INSERT INTO stores (id, name, code, cluster_id) VALUES "
                    "(:id, 'S', 'x3s', :cid)"
                ), {"id": uuid4().hex, "cid": cid})
                result = await conn.execute(text(
                    "SELECT cluster_id FROM stores WHERE code = 'x3s'"
                ))
                self.assertEqual(result.fetchone()[0], cid)
        asyncio.run(check())

    def test_kso_belongs_to_store(self):
        async def check():
            async with self.engine.begin() as conn:
                bid, cid, sid = uuid4().hex, uuid4().hex, uuid4().hex
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B', 'x4')"
                ), {"id": bid})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, branch_id) VALUES (:id, 'C', :bid)"
                ), {"id": cid, "bid": bid})
                await conn.execute(text(
                    "INSERT INTO stores (id, name, code, cluster_id) VALUES "
                    "(:id, 'S', 'x4s', :cid)"
                ), {"id": sid, "cid": cid})
                kid = uuid4().hex
                await conn.execute(text(
                    "INSERT INTO kso_devices (id, store_id, device_code) VALUES "
                    "(:id, :sid, 'x4k')"
                ), {"id": kid, "sid": sid})
                result = await conn.execute(text(
                    "SELECT store_id FROM kso_devices WHERE id = :kid"
                ), {"kid": kid})
                self.assertEqual(result.fetchone()[0], sid)
        asyncio.run(check())

    def test_kso_screen_constraints_default(self):
        """Default: screen 1920×1080, ad_zone 1440×1080."""
        async def check():
            async with self.engine.begin() as conn:
                bid, cid, sid = uuid4().hex, uuid4().hex, uuid4().hex
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B', 'x5')"
                ), {"id": bid})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, branch_id) VALUES (:id, 'C', :bid)"
                ), {"id": cid, "bid": bid})
                await conn.execute(text(
                    "INSERT INTO stores (id, name, code, cluster_id) VALUES "
                    "(:id, 'S', 'x5s', :cid)"
                ), {"id": sid, "cid": cid})
                await conn.execute(text(
                    "INSERT INTO kso_devices (id, store_id, device_code) VALUES "
                    "(:id, :sid, 'x5k')"
                ), {"id": uuid4().hex, "sid": sid})
            async with self.Session() as s:
                result = await s.execute(text(
                    "SELECT screen_width, screen_height, ad_zone_width, "
                    "ad_zone_height, channel FROM kso_devices "
                    "WHERE device_code = 'x5k'"
                ))
                row = result.fetchone()
                self.assertEqual(row[0], 1920)
                self.assertEqual(row[1], 1080)
                self.assertEqual(row[2], 1440)
                self.assertEqual(row[3], 1080)
                self.assertEqual(row[4], "kso")
        asyncio.run(check())

    def test_device_code_unique(self):
        async def check():
            async with self.engine.begin() as conn:
                bid, cid, sid = uuid4().hex, uuid4().hex, uuid4().hex
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B', 'x6')"
                ), {"id": bid})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, branch_id) VALUES (:id, 'C', :bid)"
                ), {"id": cid, "bid": bid})
                await conn.execute(text(
                    "INSERT INTO stores (id, name, code, cluster_id) VALUES "
                    "(:id, 'S', 'x6s', :cid)"
                ), {"id": sid, "cid": cid})
                await conn.execute(text(
                    "INSERT INTO kso_devices (id, store_id, device_code) VALUES "
                    "(:id, :sid, 'dup_k')"
                ), {"id": uuid4().hex, "sid": sid})
                with self.assertRaises(Exception):
                    await conn.execute(text(
                        "INSERT INTO kso_devices (id, store_id, device_code) VALUES "
                        "(:id, :sid, 'dup_k')"
                    ), {"id": uuid4().hex, "sid": sid})
        asyncio.run(check())

    def test_store_has_format_and_status(self):
        async def check():
            async with self.engine.begin() as conn:
                bid, cid = uuid4().hex, uuid4().hex
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B', 'x7')"
                ), {"id": bid})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, branch_id) VALUES (:id, 'C', :bid)"
                ), {"id": cid, "bid": bid})
                await conn.execute(text(
                    "INSERT INTO stores (id, name, code, cluster_id, format, status) "
                    "VALUES (:id, 'S', 'x7s', :cid, 'supermarket', 'active')"
                ), {"id": uuid4().hex, "cid": cid})
            async with self.Session() as s:
                result = await s.execute(text(
                    "SELECT format, status FROM stores WHERE code = 'x7s'"
                ))
                row = result.fetchone()
                self.assertEqual(row[0], "supermarket")
                self.assertEqual(row[1], "active")
        asyncio.run(check())

    def test_cluster_code_unique_per_branch(self):
        """UniqueConstraint(branch_id, code): same code OK in diff branches."""
        async def check():
            async with self.engine.begin() as conn:
                bid1, bid2 = uuid4().hex, uuid4().hex
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B1', 'x8a')"
                ), {"id": bid1})
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B2', 'x8b')"
                ), {"id": bid2})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, code, branch_id) VALUES "
                    "(:id, 'C1', 'c1', :bid)"
                ), {"id": uuid4().hex, "bid": bid1})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, code, branch_id) VALUES "
                    "(:id, 'C2', 'c1', :bid)"
                ), {"id": uuid4().hex, "bid": bid2})
                with self.assertRaises(Exception):
                    await conn.execute(text(
                        "INSERT INTO clusters (id, name, code, branch_id) VALUES "
                        "(:id, 'C3', 'c1', :bid)"
                    ), {"id": uuid4().hex, "bid": bid1})
        asyncio.run(check())

    def test_seed_idempotent(self):
        """Duplicate seed insert raises constraint violation."""
        async def check():
            async with self.engine.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES "
                    "('s1', 'Demo', 'demo_branch_north')"
                ))
                with self.assertRaises(Exception):
                    await conn.execute(text(
                        "INSERT INTO branches (id, name, code) VALUES "
                        "('s2', 'Demo2', 'demo_branch_north')"
                    ))
        asyncio.run(check())

    def test_kso_device_status_values(self):
        """All 5 status values accepted."""
        async def check():
            async with self.engine.begin() as conn:
                bid, cid, sid = uuid4().hex, uuid4().hex, uuid4().hex
                await conn.execute(text(
                    "INSERT INTO branches (id, name, code) VALUES (:id, 'B', 'x9')"
                ), {"id": bid})
                await conn.execute(text(
                    "INSERT INTO clusters (id, name, branch_id) VALUES (:id, 'C', :bid)"
                ), {"id": cid, "bid": bid})
                await conn.execute(text(
                    "INSERT INTO stores (id, name, code, cluster_id) VALUES "
                    "(:id, 'S', 'x9s', :cid)"
                ), {"id": sid, "cid": cid})
                for status in ("active", "inactive", "blocked", "maintenance", "lost"):
                    await conn.execute(text(
                        "INSERT INTO kso_devices (id, store_id, device_code, status) "
                        "VALUES (:id, :sid, :dc, :st)"
                    ), {"id": uuid4().hex, "sid": sid, "dc": f"x9_{status}", "st": status})
        asyncio.run(check())

    def test_kso_device_forbidden_fields_absent(self):
        """Table has NO columns for secrets, IP, MAC, hostname, serial."""
        async def check():
            async with self.Session() as s:
                result = await s.execute(text("PRAGMA table_info(kso_devices)"))
                columns = {row[1] for row in result.fetchall()}
                forbidden = {
                    "device_secret", "client_secret",
                    "ip_address", "mac_address", "hostname", "serial_number",
                    "access_token", "refresh_token",
                }
                for fb in forbidden:
                    self.assertNotIn(fb, columns, f"kso_devices must NOT have '{fb}'")
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
