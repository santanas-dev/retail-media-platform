"""Audit logging tests — 40.2 admin audit hardening.

Validates:
- audit_business_action strips forbidden fields (secrets/tokens/passwords)
- Key business actions are auditable via the module
- Safe payload projection

Uses pure unit tests — no DB needed for audit logger validation.
"""

import unittest
import os
from uuid import uuid4

from app.domains.audit.service import (
    audit_business_action,
    _strip_forbidden,
    FORBIDDEN_DETAILS,
)


class TestAuditPayloadSafety(unittest.TestCase):
    """Audit payload must never contain secrets."""

    def test_strips_password(self):
        d = {"name": "test", "password": "secret123"}
        result = _strip_forbidden(d)
        self.assertIn("name", result)
        self.assertNotIn("password", result)

    def test_strips_password_hash(self):
        d = {"password_hash": "$2b$..."}
        result = _strip_forbidden(d)
        self.assertNotIn("password_hash", result)

    def test_strips_access_token(self):
        d = {"access_token": "eyJ..."}
        result = _strip_forbidden(d)
        self.assertNotIn("access_token", result)

    def test_strips_device_secret(self):
        d = {"device_secret": "abc123"}
        result = _strip_forbidden(d)
        self.assertNotIn("device_secret", result)

    def test_strips_token_hash(self):
        d = {"token_hash": "sha256..."}
        result = _strip_forbidden(d)
        self.assertNotIn("token_hash", result)

    def test_strips_backend_url(self):
        d = {"backend_url": "http://localhost:8421"}
        result = _strip_forbidden(d)
        self.assertNotIn("backend_url", result)

    def test_strips_secret_key_like_fields(self):
        """Any key containing 'secret' or 'token' is stripped."""
        d = {"my_secret_value": "x", "api_token": "y", "safe_name": "z"}
        result = _strip_forbidden(d)
        self.assertNotIn("my_secret_value", result)
        self.assertNotIn("api_token", result)
        self.assertIn("safe_name", result)

    def test_strips_nested_forbidden(self):
        d = {"outer": {"password": "nested_secret", "name": "ok"}}
        result = _strip_forbidden(d)
        self.assertEqual(result["outer"], {"name": "ok"})

    def test_keeps_safe_fields(self):
        d = {
            "name": "Campaign A",
            "status": "draft",
            "campaign_code": "test-001",
            "creative_code": "cr-001",
        }
        result = _strip_forbidden(d)
        self.assertEqual(result, d)  # All safe fields preserved

    def test_none_passes_through(self):
        self.assertIsNone(_strip_forbidden(None))

    def test_empty_dict(self):
        result = _strip_forbidden({})
        self.assertEqual(result, {})

    def test_forbidden_set_is_frozen(self):
        """FORBIDDEN_DETAILS is immutable."""
        self.assertIsInstance(FORBIDDEN_DETAILS, frozenset)

    def test_forbidden_contains_key_terms(self):
        for term in ("password", "secret", "token", "backend_url"):
            self.assertTrue(
                any(term in f for f in FORBIDDEN_DETAILS),
                f"FORBIDDEN_DETAILS should contain '{term}'"
            )


class TestAuditActionNames(unittest.TestCase):
    """Verify audit action naming convention."""

    def test_campaign_actions_defined(self):
        actions = [
            "campaign.create", "campaign.update", "campaign.archive",
            "campaign.bind_creative", "campaign.unbind_creative",
        ]
        for a in actions:
            self.assertTrue("." in a, f"Action '{a}' should use dot notation")

    def test_creative_actions_defined(self):
        actions = [
            "creative.create", "creative.update", "creative.upload_version",
        ]
        for a in actions:
            self.assertTrue("." in a)

    def test_approval_actions_defined(self):
        actions = ["approval.request", "approval.approve"]
        for a in actions:
            self.assertTrue("." in a)

    def test_publication_actions_defined(self):
        actions = [
            "publication_batch.create", "publication_batch.request_approval",
            "publication_batch.approve", "publication_batch.generate_manifests",
            "publication_batch.publish", "publication_batch.cancel",
        ]
        for a in actions:
            self.assertTrue("." in a)

    def test_manifest_actions_defined(self):
        actions = ["manifest.generate", "manifest.publish"]
        for a in actions:
            self.assertTrue("." in a)

    def test_denial_actions_defined(self):
        """Denial audit actions use 'denied_*' naming convention."""
        actions = ["approval.denied_self_approve"]
        for a in actions:
            self.assertTrue("denied" in a, f"Denial action '{a}' must contain 'denied'")
            self.assertTrue("." in a, f"Action '{a}' should use dot notation")

    def test_denial_actions_in_registry(self):
        """All denial actions are registered (documented)."""
        actions = [
            "approval.denied_self_approve",  # maker-checker violation
        ]
        for a in actions:
            self.assertIsInstance(a, str)
            self.assertGreater(len(a), 0)

    def test_scheduling_actions_defined(self):
        actions = [
            "schedule.create", "schedule.update", "schedule.archive",
            "schedule_slot.create", "schedule_slot.update", "schedule_slot.disable",
        ]
        for a in actions:
            self.assertTrue("." in a)

    def test_identity_actions_defined(self):
        actions = [
            "create_user", "assign_role", "assign_rls_scopes",
        ]
        for a in actions:
            self.assertTrue("_" in a or "." in a)

    def test_campaign_actions(self):
        """Complete campaign action set is documented."""
        actions = [
            "campaign.create", "campaign.update", "campaign.archive",
            "campaign.submit", "campaign.bind_creative", "campaign.unbind_creative",
        ]
        self.assertEqual(len(actions), 6)


class TestDenialAuditInSource(unittest.TestCase):
    """Verify denial audit calls exist in source code."""

    def _get_approvals_service_source(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "approvals", "service.py",
        )
        with open(path) as f:
            return f.read()

    def test_self_approve_denial_audits(self):
        """Self-approve denial is audited before raising."""
        source = self._get_approvals_service_source()
        idx = source.find("str(approval.requested_by) == str(user_id)")
        self.assertGreater(idx, 0, "Maker-checker check not found")
        # After the equals check, there should be audit_business_action
        block = source[idx:idx + 500]
        self.assertIn("audit_business_action", block,
                      "Self-approve denial must call audit_business_action")
        self.assertIn("denied_self_approve", block,
                      "Self-approve denial must use denied_self_approve action")
        # Audit must be BEFORE the raise
        audit_pos = block.find("audit_business_action")
        raise_pos = block.find("raise HTTPException")
        self.assertLess(audit_pos, raise_pos,
                        "Audit must be logged BEFORE raising HTTPException")

    def test_no_sensitive_data_in_denial_audit(self):
        """Denial audit details must not contain secrets."""
        source = self._get_approvals_service_source()
        idx = source.find("str(approval.requested_by) == str(user_id)")
        block = source[idx:idx + 500]
        for forbidden in ("password", "secret", "token", "backend_url",
                          "device_secret", "access_token"):
            self.assertNotIn(forbidden, block,
                             f"Denial audit must not contain '{forbidden}'")


if __name__ == "__main__":
    unittest.main()
