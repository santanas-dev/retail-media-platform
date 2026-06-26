"""
RLS enforcement unit tests — verify scope resolution, query filtering,
and object-level access checks.

Covers:
  - UserScopeContext semantics (admin, scoped, empty)
  - apply_advertiser_rls filtering
  - assert_object_in_advertiser_scope (allowed, blocked, admin bypass)
  - Store/device scope detection
  - No raw secrets/uuids in repr
"""

import unittest
from uuid import UUID, uuid4


class TestUserScopeContext(unittest.TestCase):
    """Unit tests for UserScopeContext dataclass."""

    def test_empty_scope_is_admin(self):
        from app.domains.identity.rls import UserScopeContext
        ctx = UserScopeContext()
        self.assertTrue(ctx.is_admin)
        self.assertFalse(ctx.is_advertiser_scoped)
        self.assertFalse(ctx.is_store_scoped)
        self.assertFalse(ctx.is_branch_scoped)

    def test_advertiser_scoped_detection(self):
        from app.domains.identity.rls import UserScopeContext
        ctx = UserScopeContext(advertiser_ids=[uuid4()])
        self.assertFalse(ctx.is_admin)
        self.assertTrue(ctx.is_advertiser_scoped)
        self.assertFalse(ctx.is_store_scoped)

    def test_store_scoped_detection(self):
        from app.domains.identity.rls import UserScopeContext
        ctx = UserScopeContext(store_ids=[uuid4()])
        self.assertFalse(ctx.is_admin)
        self.assertTrue(ctx.is_store_scoped)

    def test_multiple_scopes_not_admin(self):
        from app.domains.identity.rls import UserScopeContext
        ctx = UserScopeContext(advertiser_ids=[uuid4()], store_ids=[uuid4()])
        self.assertFalse(ctx.is_admin)

    def test_device_scoped_detection(self):
        from app.domains.identity.rls import UserScopeContext
        ctx = UserScopeContext(device_codes=["dev-001"])
        self.assertFalse(ctx.is_admin)

    def test_no_raw_secrets_in_repr(self):
        from app.domains.identity.rls import UserScopeContext
        ctx = UserScopeContext(advertiser_ids=[uuid4()])
        r = repr(ctx)
        self.assertNotIn("password", r.lower())
        self.assertNotIn("secret", r.lower())
        self.assertNotIn("token", r.lower())


class TestAdminRoleCodes(unittest.TestCase):
    """Verify admin role constants."""

    def test_admin_roles_contain_expected(self):
        from app.domains.identity.rls import ADMIN_ROLE_CODES
        self.assertIn("system_admin", ADMIN_ROLE_CODES)
        self.assertIn("security_admin", ADMIN_ROLE_CODES)
        self.assertNotIn("advertiser", ADMIN_ROLE_CODES)

    def test_admin_roles_is_frozenset(self):
        from app.domains.identity.rls import ADMIN_ROLE_CODES
        self.assertIsInstance(ADMIN_ROLE_CODES, frozenset)


class TestApplyAdvertiserRLS(unittest.TestCase):
    """Unit tests for apply_advertiser_rls query filter."""

    def test_admin_scope_returns_unchanged_query(self):
        from app.domains.identity.rls import UserScopeContext, apply_advertiser_rls
        from app.domains.campaigns.models import Campaign
        from sqlalchemy import select
        ctx = UserScopeContext()
        stmt = select(Campaign.id)
        result = apply_advertiser_rls(stmt, ctx, Campaign.advertiser_id)
        self.assertIs(result, stmt)

    def test_scoped_returns_filtered_query(self):
        from app.domains.identity.rls import UserScopeContext, apply_advertiser_rls
        from app.domains.campaigns.models import Campaign
        from sqlalchemy import select
        ctx = UserScopeContext(advertiser_ids=[uuid4()])
        stmt = select(Campaign.id)
        result = apply_advertiser_rls(stmt, ctx, Campaign.advertiser_id)
        self.assertIsNot(result, stmt)

    def test_empty_advertiser_ids_means_no_scope(self):
        from app.domains.identity.rls import UserScopeContext, apply_advertiser_rls
        from app.domains.campaigns.models import Campaign
        from sqlalchemy import select
        # Empty advertiser_ids list = no scope restriction (pass-through)
        ctx = UserScopeContext(advertiser_ids=[])
        stmt = select(Campaign.id)
        result = apply_advertiser_rls(stmt, ctx, Campaign.advertiser_id)
        # Empty list means no restriction — query unchanged
        self.assertIs(result, stmt)


class TestAssertObjectInAdvertiserScope(unittest.TestCase):
    """Unit tests for object-level scope assertion."""

    def test_in_scope_passes(self):
        from app.domains.identity.rls import UserScopeContext, assert_object_in_advertiser_scope
        adv_id = uuid4()
        ctx = UserScopeContext(advertiser_ids=[adv_id])
        assert_object_in_advertiser_scope(adv_id, ctx, "view")

    def test_out_of_scope_raises_404(self):
        from app.domains.identity.rls import UserScopeContext, assert_object_in_advertiser_scope
        from fastapi import HTTPException
        ctx = UserScopeContext(advertiser_ids=[uuid4()])
        with self.assertRaises(HTTPException) as cm:
            assert_object_in_advertiser_scope(uuid4(), ctx, "view")
        self.assertEqual(cm.exception.status_code, 404)

    def test_admin_bypasses_scope_check(self):
        from app.domains.identity.rls import UserScopeContext, assert_object_in_advertiser_scope
        ctx = UserScopeContext()
        assert_object_in_advertiser_scope(uuid4(), ctx, "view")

    def test_not_in_scope_but_not_scoped_passes(self):
        from app.domains.identity.rls import UserScopeContext, assert_object_in_advertiser_scope
        ctx = UserScopeContext(store_ids=[uuid4()])
        assert_object_in_advertiser_scope(uuid4(), ctx, "view")


class TestRequiresRLS(unittest.TestCase):
    """Test requires_rls helper."""

    def test_admin_does_not_require_rls(self):
        from app.domains.identity.rls import requires_rls, UserScopeContext
        self.assertFalse(requires_rls(UserScopeContext()))

    def test_scoped_requires_rls(self):
        from app.domains.identity.rls import requires_rls, UserScopeContext
        ctx = UserScopeContext(advertiser_ids=[uuid4()])
        self.assertTrue(requires_rls(ctx))


if __name__ == "__main__":
    unittest.main()
