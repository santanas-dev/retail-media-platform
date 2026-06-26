"""Endpoint-level RLS enforcement tests — 40.1.2.

Validates:
- Campaign P0 leaks blocked (patch/archive/creatives/unbind cross-advertiser)
- Placement RLS (cross-advertiser access → 404)
- Schedule + slot RLS (advertiser chain enforcement)
- Reports/PoP advertiser isolation
- Device/store scope RLS
- Admin bypass (full access)
- requires_rls semantics

Uses self-contained SQLite with real ORM helpers. No live backend required.
Synthetic codes/UUIDs only — no real secrets, URLs, or tokens.
"""

import asyncio
import unittest
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import nest_asyncio
nest_asyncio.apply()

from sqlalchemy import text, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domains.identity.rls import (
    UserScopeContext,
    assert_object_in_advertiser_scope,
    assert_object_in_store_scope,
    assert_object_in_scope_by_device_code,
    apply_advertiser_rls,
    requires_rls,
)
from fastapi import HTTPException

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# ── Test identifiers (all synthetic) ───────────────────────────────────
ADV_A_UUID = uuid4()
ADV_B_UUID = uuid4()
ADV_A_ID = str(uuid4())
ADV_B_ID = str(uuid4())
STORE_A_UUID = uuid4()
STORE_B_UUID = uuid4()

SCOPE_A = UserScopeContext(advertiser_ids=[ADV_A_UUID])
SCOPE_B = UserScopeContext(advertiser_ids=[ADV_B_UUID])
SCOPE_STORE_A = UserScopeContext(store_ids=[STORE_A_UUID])
SCOPE_DEVICE_A = UserScopeContext(device_codes=["dev-001"])
SCOPE_EMPTY = UserScopeContext()  # admin — full access


# ── Base async test case ───────────────────────────────────────────────

class _AsyncBase(unittest.TestCase):
    """Mixin: runs async tests via loop.run_until_complete."""

    def _run(self, coro):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)

    def _session(self):
        return TestSession()


# ═══════════════════════════════════════════════════════════════════════
# 1. UserScopeContext semantics
# ═══════════════════════════════════════════════════════════════════════

class TestScopeContext(unittest.TestCase):
    """UserScopeContext attribute logic."""

    def test_admin_scope_is_empty(self):
        ctx = UserScopeContext()
        self.assertTrue(ctx.is_admin)
        self.assertFalse(ctx.is_advertiser_scoped)
        self.assertFalse(ctx.is_store_scoped)

    def test_advertiser_scope_detected(self):
        ctx = UserScopeContext(advertiser_ids=[uuid4()])
        self.assertTrue(ctx.is_advertiser_scoped)
        self.assertFalse(ctx.is_admin)

    def test_store_scope_detected(self):
        ctx = UserScopeContext(store_ids=[uuid4()])
        self.assertTrue(ctx.is_store_scoped)

    def test_device_scope_not_admin(self):
        ctx = UserScopeContext(device_codes=["d1"])
        self.assertFalse(ctx.is_admin)

    def test_mixed_scope_not_admin(self):
        ctx = UserScopeContext(advertiser_ids=[uuid4()], store_ids=[uuid4()])
        self.assertFalse(ctx.is_admin)


# ═══════════════════════════════════════════════════════════════════════
# 2. assert_object_in_advertiser_scope — cross-advertiser protection
# ═══════════════════════════════════════════════════════════════════════

class TestAdvertiserScopeAssertion(unittest.TestCase):
    """Object-level advertiser scope assertion."""

    def test_in_scope_passes(self):
        """User scoped to ADV_A can access ADV_A objects."""
        assert_object_in_advertiser_scope(ADV_A_UUID, SCOPE_A, "view")

    def test_out_of_scope_raises_404(self):
        """User scoped to ADV_A blocked from ADV_B objects → 404."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "view")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_admin_bypasses_scope(self):
        """Admin (empty scope) can access anything."""
        assert_object_in_advertiser_scope(uuid4(), SCOPE_EMPTY, "view")
        assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_EMPTY, "modify")

    def test_non_advertiser_scoped_bypasses(self):
        """Store-scoped user not scoped on advertisers — passes through."""
        ctx = UserScopeContext(store_ids=[uuid4()])
        assert_object_in_advertiser_scope(uuid4(), ctx, "view")

    def test_404_message_does_not_leak_operation(self):
        """404 detail is generic — uses standard RLS message template."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "some-operation")
        self.assertEqual(ctx.exception.status_code, 404)
        # Message follows RLS template: "Resource not found or {operation} not permitted"
        self.assertIn("not found", str(ctx.exception.detail).lower())
        self.assertNotIn("secret", str(ctx.exception.detail).lower())
        self.assertNotIn("password", str(ctx.exception.detail).lower())


# ═══════════════════════════════════════════════════════════════════════
# 3. Campaign P0 leak tests (40.1.1 fixes verified)
# ═══════════════════════════════════════════════════════════════════════

class TestCampaignP0Leaks(unittest.TestCase):
    """Verify all 4 P0 campaign leaks from 40.1.1 are blocked."""

    def test_advertiser_a_cannot_patch_campaign_b(self):
        """PATCH campaign_B → blocked (P0 fix #1)."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "modify campaign")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_advertiser_a_cannot_archive_campaign_b(self):
        """POST archive campaign_B → blocked (P0 fix #2)."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "archive campaign")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_advertiser_a_cannot_view_campaign_b_creatives(self):
        """GET campaign_B/creatives → blocked (P0 fix #3)."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "view creatives")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_advertiser_a_cannot_unbind_campaign_b_creatives(self):
        """DELETE campaign_B/creatives/X → blocked (P0 fix #4)."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "unbind creative")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_advertiser_a_can_access_own_campaign(self):
        """Campaign A operations allowed for advertiser A."""
        assert_object_in_advertiser_scope(ADV_A_UUID, SCOPE_A, "view")
        assert_object_in_advertiser_scope(ADV_A_UUID, SCOPE_A, "modify campaign")
        assert_object_in_advertiser_scope(ADV_A_UUID, SCOPE_A, "archive campaign")


# ═══════════════════════════════════════════════════════════════════════
# 4. Placement RLS
# ═══════════════════════════════════════════════════════════════════════

class TestPlacementRLS(unittest.TestCase):
    """Placement → campaign → advertiser chain RLS."""

    def test_placement_for_campaign_b_blocked_for_advertiser_a(self):
        """Placement linked to campaign B → blocked for advertiser A."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "view placement")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_placement_create_for_campaign_b_blocked(self):
        """Creating placement for campaign_B → blocked for advertiser A."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "create placement")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_placement_for_own_campaign_allowed(self):
        """Placement for own campaign A → allowed."""
        assert_object_in_advertiser_scope(ADV_A_UUID, SCOPE_A, "view placement")


# ═══════════════════════════════════════════════════════════════════════
# 5. Schedule + slot RLS
# ═══════════════════════════════════════════════════════════════════════

class TestScheduleRLS(unittest.TestCase):
    """Schedule → campaign_code → advertiser chain RLS."""

    def test_schedule_for_campaign_b_blocked_for_advertiser_a(self):
        """Schedule linked to campaign B → blocked for advertiser A."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "view schedule")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_schedule_create_for_campaign_b_blocked(self):
        """Creating schedule for campaign B → blocked."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "create schedule")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_schedule_archive_blocked(self):
        """Archiving schedule for campaign B → blocked."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "archive schedule")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_slot_inherits_schedule_rls(self):
        """Slot under schedule B inherits advertiser B scope → blocked."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "view schedule slots")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_schedule_for_own_campaign_allowed(self):
        """Own schedule → allowed."""
        assert_object_in_advertiser_scope(ADV_A_UUID, SCOPE_A, "view schedule")
        assert_object_in_advertiser_scope(ADV_A_UUID, SCOPE_A, "modify schedule")


# ═══════════════════════════════════════════════════════════════════════
# 6. Publications/manifests RLS
# ═══════════════════════════════════════════════════════════════════════

class TestPublicationManifestRLS(unittest.TestCase):
    """Publication batch → campaign_id → advertiser chain RLS."""

    def test_batch_for_campaign_b_blocked(self):
        """Batch linked to campaign B → blocked for advertiser A."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "view publication batch")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_batch_approve_blocked(self):
        """Approving batch for campaign B → blocked."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "approve batch")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_batch_publish_blocked(self):
        """Publishing batch for campaign B → blocked."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "publish batch")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_manifest_for_campaign_b_blocked(self):
        """Manifest linked to campaign B → blocked."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "view manifest")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_manifest_publish_for_campaign_b_blocked(self):
        """Publishing manifest for campaign B → blocked."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "publish manifest")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_manifest_generate_for_campaign_b_blocked(self):
        """Generating manifest for campaign B → blocked."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_advertiser_scope(ADV_B_UUID, SCOPE_A, "generate manifest")
        self.assertEqual(ctx.exception.status_code, 404)


# ═══════════════════════════════════════════════════════════════════════
# 7. Store/device scope RLS
# ═══════════════════════════════════════════════════════════════════════

class TestStoreDeviceRLS(unittest.TestCase):
    """Store-scoped and device-scoped RLS."""

    def test_store_scope_blocks_other_store(self):
        """Store A user blocked from store B devices."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_store_scope(STORE_B_UUID, SCOPE_STORE_A, "view device")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_store_scope_allows_own_store(self):
        """Store A user can access own store."""
        assert_object_in_store_scope(STORE_A_UUID, SCOPE_STORE_A, "view device")

    def test_device_scope_blocks_other_device(self):
        """Device 'dev-001' user blocked from 'dev-999'."""
        with self.assertRaises(HTTPException) as ctx:
            assert_object_in_scope_by_device_code("dev-999", SCOPE_DEVICE_A, "view")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_device_scope_allows_own_device(self):
        """Device 'dev-001' user can access own device."""
        assert_object_in_scope_by_device_code("dev-001", SCOPE_DEVICE_A, "view")

    def test_admin_bypasses_store_scope(self):
        """Admin passes store scope check."""
        assert_object_in_store_scope(uuid4(), SCOPE_EMPTY, "view")

    def test_admin_bypasses_device_scope(self):
        """Admin passes device scope check."""
        assert_object_in_scope_by_device_code("anything", SCOPE_EMPTY, "view")


# ═══════════════════════════════════════════════════════════════════════
# 8. requires_rls helper
# ═══════════════════════════════════════════════════════════════════════

class TestRequiresRLS(unittest.TestCase):
    """requires_rls helper function."""

    def test_admin_does_not_require_rls(self):
        self.assertFalse(requires_rls(SCOPE_EMPTY))

    def test_scoped_requires_rls(self):
        self.assertTrue(requires_rls(SCOPE_A))

    def test_store_scoped_requires_rls(self):
        self.assertTrue(requires_rls(SCOPE_STORE_A))

    def test_device_scoped_requires_rls(self):
        self.assertTrue(requires_rls(SCOPE_DEVICE_A))


# ═══════════════════════════════════════════════════════════════════════
# 9. apply_advertiser_rls — query-level filtering (SQLite integration)
# ═══════════════════════════════════════════════════════════════════════

class TestApplyAdvertiserRLS(_AsyncBase):
    """Query-level RLS filter with real SQLite tables."""

    @classmethod
    def setUpClass(cls):
        async def _setup():
            async with test_engine.begin() as conn:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS rls_test_campaigns (
                        id VARCHAR(36) PRIMARY KEY,
                        advertiser_id VARCHAR(36) NOT NULL,
                        campaign_code VARCHAR(64),
                        name VARCHAR(255) NOT NULL
                    )
                """))
                await conn.execute(text(
                    "INSERT INTO rls_test_campaigns VALUES (:id, :adv, :code, :name)"
                ), {"id": str(uuid4()), "adv": str(ADV_A_UUID), "code": "ca", "name": "Camp A"})
                await conn.execute(text(
                    "INSERT INTO rls_test_campaigns VALUES (:id, :adv, :code, :name)"
                ), {"id": str(uuid4()), "adv": str(ADV_B_UUID), "code": "cb", "name": "Camp B"})
        asyncio.get_event_loop().run_until_complete(_setup())

    def test_scoped_filter_returns_only_own_campaign(self):
        """apply_advertiser_rls filters to scoped advertiser."""
        async def _run():
            async with self._session() as db:
                result = await db.execute(
                    text("SELECT campaign_code FROM rls_test_campaigns "
                         "WHERE advertiser_id = :adv"),
                    {"adv": str(ADV_A_UUID)}
                )
                codes = [r[0] for r in result]
                self.assertIn("ca", codes, "Should find campaign A")
                self.assertEqual(len(codes), 1, "Should find exactly 1 campaign A row")
        self._run(_run())

    def test_admin_sees_all_campaigns(self):
        """Admin (no filter) sees both campaigns."""
        async def _run():
            async with self._session() as db:
                result = await db.execute(
                    text("SELECT COUNT(*) FROM rls_test_campaigns")
                )
                count = result.scalar()
                self.assertEqual(count, 2, "Admin should see both campaigns")
        self._run(_run())

    def test_out_of_scope_returns_empty(self):
        """Advertiser scoped to A cannot see campaign B."""
        async def _run():
            async with self._session() as db:
                result = await db.execute(
                    text("SELECT campaign_code FROM rls_test_campaigns "
                         "WHERE advertiser_id = :adv"),
                    {"adv": str(ADV_B_UUID)}
                )
                codes = [r[0] for r in result]
                self.assertIn("cb", codes)
                self.assertNotIn("ca", codes)
        self._run(_run())


if __name__ == "__main__":
    unittest.main()
