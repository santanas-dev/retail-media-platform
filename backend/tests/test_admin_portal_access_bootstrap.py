"""Verify admin portal access bootstrap — roles, permissions, seed integrity.

Tests that system_admin and security_admin have all permissions needed
for portal pages: /admin, /device-dashboard, /readiness, /dashboard, etc.

Uses direct module access via sys.path to avoid PYTHONPATH issues with unittest.
"""

import os
import sys
import unittest

# Ensure backend is importable
_backend = os.path.join(os.path.dirname(__file__), "..")
if _backend not in sys.path:
    sys.path.insert(0, _backend)


class TestRolePermissionSeedIntegrity(unittest.TestCase):
    """Verify seed permission sets match portal page requirements."""

    @classmethod
    def setUpClass(cls):
        from app.domains.identity.seed import ROLE_PERMISSIONS, PERMISSIONS, ROLES
        cls.ROLE_PERMISSIONS = ROLE_PERMISSIONS
        cls.PERMISSIONS = PERMISSIONS
        cls.ROLES = ROLES

    # ── system_admin coverage ──────────────────────────────────────

    def test_system_admin_has_all_portal_permissions(self):
        required = {
            "campaigns.read", "media.read", "scheduling.read",
            "publications.read", "organization.read", "devices.read",
            "reports.read", "campaigns.approve", "users.read",
            "devices.gateway.read",
        }
        sys_perms = set(self.ROLE_PERMISSIONS.get("system_admin", []))
        missing = required - sys_perms
        self.assertFalse(missing, f"system_admin missing: {missing}")

    def test_system_admin_has_audit_read(self):
        self.assertIn("audit.read", self.ROLE_PERMISSIONS.get("system_admin", []))

    def test_system_admin_has_media_read(self):
        self.assertIn("media.read", self.ROLE_PERMISSIONS.get("system_admin", []))

    def test_system_admin_has_devices_read(self):
        self.assertIn("devices.read", self.ROLE_PERMISSIONS.get("system_admin", []))

    def test_system_admin_has_organization_read(self):
        self.assertIn("organization.read", self.ROLE_PERMISSIONS.get("system_admin", []))

    def test_system_admin_has_campaigns_approve(self):
        self.assertIn("campaigns.approve", self.ROLE_PERMISSIONS.get("system_admin", []))

    def test_system_admin_has_devices_gateway_read(self):
        self.assertIn("devices.gateway.read", self.ROLE_PERMISSIONS.get("system_admin", []))

    def test_system_admin_has_scheduling_read(self):
        self.assertIn("scheduling.read", self.ROLE_PERMISSIONS.get("system_admin", []))

    # ── security_admin coverage ────────────────────────────────────

    def test_security_admin_has_audit_read(self):
        self.assertIn("audit.read", self.ROLE_PERMISSIONS.get("security_admin", []))

    def test_security_admin_has_device_gateway_read(self):
        self.assertIn("devices.gateway.read", self.ROLE_PERMISSIONS.get("security_admin", []))

    def test_security_admin_has_publications_read(self):
        self.assertIn("publications.read", self.ROLE_PERMISSIONS.get("security_admin", []))

    def test_security_admin_has_campaigns_read(self):
        self.assertIn("campaigns.read", self.ROLE_PERMISSIONS.get("security_admin", []))

    def test_security_admin_has_users_manage(self):
        self.assertIn("users.manage", self.ROLE_PERMISSIONS.get("security_admin", []))

    def test_security_admin_has_roles_manage(self):
        self.assertIn("roles.manage", self.ROLE_PERMISSIONS.get("security_admin", []))

    def test_security_admin_has_organization_read(self):
        self.assertIn("organization.read", self.ROLE_PERMISSIONS.get("security_admin", []))

    # ── Negative: regular roles must NOT have admin perms ──────────

    def test_advertiser_does_not_have_audit_read(self):
        self.assertNotIn("audit.read", self.ROLE_PERMISSIONS.get("advertiser", []))

    def test_advertiser_does_not_have_users_read(self):
        self.assertNotIn("users.read", self.ROLE_PERMISSIONS.get("advertiser", []))

    def test_advertiser_does_not_have_device_gateway_read(self):
        self.assertNotIn("devices.gateway.read", self.ROLE_PERMISSIONS.get("advertiser", []))

    def test_analyst_does_not_have_audit_read(self):
        self.assertNotIn("audit.read", self.ROLE_PERMISSIONS.get("analyst", []))

    def test_analyst_does_not_have_users_read(self):
        self.assertNotIn("users.read", self.ROLE_PERMISSIONS.get("analyst", []))

    # ── Seed integrity ─────────────────────────────────────────────

    def test_all_role_permissions_exist_in_master_list(self):
        all_codes = {p[0] for p in self.PERMISSIONS}
        for role, perms in self.ROLE_PERMISSIONS.items():
            for perm in perms:
                self.assertIn(perm, all_codes, f"{role}.{perm} not in PERMISSIONS")

    def test_roles_list_has_system_admin(self):
        role_codes = {r[0] for r in self.ROLES}
        self.assertIn("system_admin", role_codes)
        self.assertIn("security_admin", role_codes)

    def test_permission_count(self):
        self.assertGreaterEqual(len(self.PERMISSIONS), 47)
        self.assertEqual(len(self.ROLES), 8)


if __name__ == "__main__":
    unittest.main()
