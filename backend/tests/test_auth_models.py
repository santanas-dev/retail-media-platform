"""Test auth RBAC RLS DB models, migration, and seed.

Validates:
- Models import cleanly
- Tables have correct columns
- Users table has password_hash but NO plaintext password
- RefreshTokens stores token_hash, NOT raw token
- Roles seed contains all 8 required roles
- Permissions seed contains required backend permissions
- device_service has only service permissions (no human portal)
- UserRlsScope supports all 7 scope types
- Audit tables exist with safe columns (no raw secrets)
- MfaSettings does NOT store raw secret — only secret_ref
- Seed is idempotent

No real users, emails, phones, tokens, or secrets.
"""

import unittest
from pathlib import Path

# Ensure backend is on path
_BACKEND = Path(__file__).resolve().parent.parent
import sys
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class TestAuthModelsExist(unittest.TestCase):
    """All new models import cleanly and have correct table names."""

    def test_user_model_has_archived_fields(self):
        from app.domains.identity.models import User
        self.assertTrue(hasattr(User, "is_archived"),
                        "User must have is_archived")
        self.assertTrue(hasattr(User, "archived_at"),
                        "User must have archived_at")
        self.assertTrue(hasattr(User, "archived_by"),
                        "User must have archived_by")

    def test_user_model_has_password_hash_not_plaintext(self):
        from app.domains.identity.models import User
        self.assertTrue(hasattr(User, "password_hash"),
                        "User must have password_hash")
        # No plaintext password column
        self.assertFalse(hasattr(User, "password"),
                         "User must NOT have plaintext 'password' column")

    def test_refresh_token_stores_hash_not_raw(self):
        from app.domains.identity.models import RefreshToken
        self.assertTrue(hasattr(RefreshToken, "token_hash"),
                        "RefreshToken must have token_hash")
        # Must NOT store raw token
        self.assertFalse(hasattr(RefreshToken, "token"),
                         "RefreshToken must NOT store raw 'token'")
        self.assertFalse(hasattr(RefreshToken, "refresh_token"),
                         "RefreshToken must NOT store 'refresh_token'")

    def test_user_rls_scopes_table_exists(self):
        from app.domains.identity.models import UserRlsScope
        self.assertEqual(UserRlsScope.__tablename__, "user_rls_scopes")
        cols = {c.name for c in UserRlsScope.__table__.columns}
        required = {"id", "user_id", "scope_type", "scope_value",
                     "is_active", "created_by", "created_at", "reason"}
        self.assertTrue(required.issubset(cols),
                        f"Missing columns: {required - cols}")

    def test_login_audit_events_table_exists(self):
        from app.domains.identity.models import LoginAuditEvent
        self.assertEqual(LoginAuditEvent.__tablename__, "login_audit_events")
        cols = {c.name for c in LoginAuditEvent.__table__.columns}
        required = {"id", "username", "user_id", "success",
                     "result_code", "reason_code", "occurred_at"}
        self.assertTrue(required.issubset(cols),
                        f"Missing columns: {required - cols}")

    def test_admin_audit_events_table_exists(self):
        from app.domains.identity.models import AdminAuditEvent
        self.assertEqual(AdminAuditEvent.__tablename__, "admin_audit_events")
        cols = {c.name for c in AdminAuditEvent.__table__.columns}
        required = {"id", "actor_user_id", "action", "target_type",
                     "target_ref", "occurred_at"}
        self.assertTrue(required.issubset(cols),
                        f"Missing columns: {required - cols}")

    def test_mfa_settings_has_secret_ref_not_raw(self):
        from app.domains.identity.models import MfaSettings
        self.assertEqual(MfaSettings.__tablename__, "mfa_settings")
        self.assertTrue(hasattr(MfaSettings, "secret_ref"),
                        "MfaSettings must have secret_ref")
        # Must NOT store raw secret
        self.assertFalse(hasattr(MfaSettings, "secret"),
                         "MfaSettings must NOT store raw 'secret'")
        self.assertFalse(hasattr(MfaSettings, "mfa_secret"),
                         "MfaSettings must NOT store 'mfa_secret'")

    def test_all_models_in_module(self):
        """Verify all required model classes are importable."""
        from app.domains.identity import models as m
        expected = {
            "User", "Role", "Permission", "UserRole", "RolePermission",
            "RefreshToken", "UserRlsScope", "LoginAuditEvent",
            "AdminAuditEvent", "MfaSettings",
        }
        actual = {name for name in dir(m)
                  if isinstance(getattr(m, name, None), type)
                  and hasattr(getattr(m, name), "__tablename__")}
        self.assertTrue(expected.issubset(actual),
                        f"Missing models: {expected - actual}")


class TestSeedRolesAndPermissions(unittest.TestCase):
    """Seed data contains required roles and permissions."""

    @classmethod
    def setUpClass(cls):
        from app.domains.identity import seed
        cls.roles = seed.ROLES
        cls.permissions = seed.PERMISSIONS
        cls.role_perms = seed.ROLE_PERMISSIONS
        cls.role_codes = {r[0] for r in cls.roles}
        cls.perm_codes = {p[0] for p in cls.permissions}

    def test_roles_contain_all_8_required(self):
        required = {
            "system_admin", "security_admin", "ad_manager",
            "approver", "analyst", "advertiser", "operations",
            "device_service",
        }
        self.assertTrue(required.issubset(self.role_codes),
                        f"Missing roles: {required - self.role_codes}")

    def test_permissions_contain_backend_required(self):
        required_backend = {
            "users.read", "users.create", "users.manage",
            "roles.read", "roles.manage",
            "audit.read",
            "devices.read", "devices.manage",
            "campaigns.read", "campaigns.create", "campaigns.manage",
            "campaigns.approve",
            "publications.read", "publications.publish",
            "reports.read", "reports.export",
        }
        self.assertTrue(required_backend.issubset(self.perm_codes),
                        f"Missing permissions: {required_backend - self.perm_codes}")

    def test_device_service_has_only_service_permissions(self):
        perms = self.role_perms.get("device_service", [])
        # device_service must have only service/gateway permissions
        for perm in perms:
            self.assertTrue(
                perm.startswith("devices.gateway."),
                f"device_service must not have human portal permission: {perm}"
            )
        # Must have at least gateway read
        self.assertIn("devices.gateway.read", perms,
                      "device_service must have devices.gateway.read")

    def test_device_service_has_no_human_portal_permissions(self):
        perms = self.role_perms.get("device_service", [])
        forbidden_for_machine = {
            "users.read", "users.create", "users.manage",
            "roles.read", "roles.manage",
            "audit.read",
            "campaigns.read", "campaigns.create", "campaigns.approve",
            "media.read", "media.manage", "media.approve",
            "reports.read", "reports.export",
            "publications.read", "publications.manage",
            "publications.approve", "publications.publish",
            "emergency.manage",
        }
        overlap = set(perms) & forbidden_for_machine
        self.assertEqual(
            len(overlap), 0,
            f"device_service must not have human portal permissions: {sorted(overlap)}"
        )

    def test_system_admin_has_all_permissions(self):
        perms = self.role_perms.get("system_admin", [])
        self.assertGreater(len(perms), 20,
                           "system_admin must have broad permission set")
        self.assertIn("emergency.manage", perms)

    def test_advertiser_has_limited_permissions(self):
        perms = self.role_perms.get("advertiser", [])
        self.assertLess(len(perms), 10,
                        "advertiser must have very limited permissions")


class TestUserRlsScopeTypes(unittest.TestCase):
    """UserRlsScope supports all 7 scope types."""

    VALID_SCOPE_TYPES = frozenset({
        "advertiser_scope",
        "branch_scope",
        "store_scope",
        "campaign_scope",
        "device_scope",
        "approval_scope",
        "report_scope",
    })

    def test_all_7_scope_types_are_recognized(self):
        from app.domains.identity.models import UserRlsScope
        comment = UserRlsScope.__table__.columns["scope_type"].comment
        for scope in self.VALID_SCOPE_TYPES:
            self.assertIn(scope, comment or "",
                          f"scope_type comment must mention {scope}")

    def test_user_rls_scope_has_unique_constraint(self):
        from app.domains.identity.models import UserRlsScope
        uq_names = {c.name for c in UserRlsScope.__table__.constraints
                    if hasattr(c, 'name')}
        self.assertIn("uq_user_rls_scope", uq_names,
                      "user_rls_scopes must have unique constraint")


class TestAuditTablesSafety(unittest.TestCase):
    """Audit tables do not expose raw secrets/tokens/passwords."""

    def test_login_audit_has_no_secret_columns(self):
        from app.domains.identity.models import LoginAuditEvent
        cols = {c.name for c in LoginAuditEvent.__table__.columns}
        forbidden = {"password", "password_hash", "token", "access_token",
                      "refresh_token", "secret", "authorization",
                      "plaintext", "raw_token"}
        overlap = cols & forbidden
        self.assertEqual(len(overlap), 0,
                         f"login_audit_events must not have: {sorted(overlap)}")

    def test_admin_audit_has_no_secret_columns(self):
        from app.domains.identity.models import AdminAuditEvent
        cols = {c.name for c in AdminAuditEvent.__table__.columns}
        forbidden = {"password", "password_hash", "token", "access_token",
                      "refresh_token", "secret", "authorization",
                      "plaintext", "raw_token"}
        overlap = cols & forbidden
        self.assertEqual(len(overlap), 0,
                         f"admin_audit_events must not have: {sorted(overlap)}")

    def test_mfa_settings_has_no_raw_secret(self):
        from app.domains.identity.models import MfaSettings
        cols = {c.name for c in MfaSettings.__table__.columns}
        # Only secret_ref, never secret or mfa_secret
        self.assertIn("secret_ref", cols)
        self.assertNotIn("secret", cols)
        self.assertNotIn("mfa_secret", cols)


class TestSeedIdempotencyDesign(unittest.TestCase):
    """Seed uses ON CONFLICT DO NOTHING — idempotent by design."""

    def test_seed_uses_on_conflict_do_nothing(self):
        seed_path = _BACKEND / "app" / "domains" / "identity" / "seed.py"
        content = seed_path.read_text()
        self.assertIn("on_conflict_do_nothing", content,
                      "Seed must use on_conflict_do_nothing for idempotency")

    def test_seed_does_not_create_real_users(self):
        seed_path = _BACKEND / "app" / "domains" / "identity" / "seed.py"
        content = seed_path.read_text()
        # Admin user is created from env var, not hardcoded
        self.assertIn("INITIAL_ADMIN_PASSWORD", content,
                      "Seed must require INITIAL_ADMIN_PASSWORD env var")


class TestMigrationExists(unittest.TestCase):
    """Migration 023 exists."""

    def test_migration_023_exists(self):
        mig = _BACKEND / "alembic" / "versions" / "023_auth_rbac_rls.py"
        self.assertTrue(mig.exists(), "Migration 023 must exist")

    def test_migration_has_upgrade_and_downgrade(self):
        mig = _BACKEND / "alembic" / "versions" / "023_auth_rbac_rls.py"
        content = mig.read_text()
        self.assertIn("def upgrade()", content)
        self.assertIn("def downgrade()", content)


if __name__ == "__main__":
    unittest.main()
