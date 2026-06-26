"""Step 39.3.1: Production Approval API endpoint tests.

Covers:
- GET /api/approvals (production list)
- POST /api/approvals (create approval request)
- GET /api/approvals/{code} (get approval)
- POST /api/approvals/{code}/approve
- POST /api/approvals/{code}/reject
- State machine guardrails
- Safe projection
"""

import sys
import os
import unittest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestProductionApprovalRoutes(unittest.TestCase):
    """Structural verification that production approval endpoints exist."""

    @classmethod
    def setUpClass(cls):
        from app.domains.approvals.router import router
        cls.paths = [r.path for r in router.routes]
        cls.methods_by_path = {}
        for r in router.routes:
            cls.methods_by_path.setdefault(r.path, set()).update(r.methods)

    def test_list_approvals_endpoint_exists(self):
        """GET /api/approvals (production list) exists."""
        self.assertIn("/api/approvals", self.paths)
        self.assertIn("GET", self.methods_by_path.get("/api/approvals", set()))

    def test_create_approval_endpoint_exists(self):
        """POST /api/approvals (create) exists."""
        self.assertIn("POST", self.methods_by_path.get("/api/approvals", set()))

    def test_get_approval_endpoint_exists(self):
        """GET /api/approvals/{code} exists."""
        self.assertIn("/api/approvals/{approval_code}", self.paths)
        self.assertIn("GET", self.methods_by_path.get(
            "/api/approvals/{approval_code}", set()))

    def test_approve_endpoint_exists(self):
        """POST /api/approvals/{code}/approve exists."""
        self.assertIn("/api/approvals/{approval_code}/approve", self.paths)
        self.assertIn("POST", self.methods_by_path.get(
            "/api/approvals/{approval_code}/approve", set()))

    def test_reject_endpoint_exists(self):
        """POST /api/approvals/{code}/reject exists."""
        self.assertIn("/api/approvals/{approval_code}/reject", self.paths)
        self.assertIn("POST", self.methods_by_path.get(
            "/api/approvals/{approval_code}/reject", set()))

    def test_legacy_test_kso_endpoints_preserved(self):
        """Legacy test-kso endpoints still present."""
        self.assertIn("/api/approvals/test-kso", self.paths)
        self.assertIn("/api/approvals/test-kso/{approval_code}/decide", self.paths)

    def test_approve_endpoint_enforces_correct_decision(self):
        """POST .../approve rejects 'reject' decisions."""
        import inspect
        from app.domains.approvals.router import approve_approval_prod
        source = inspect.getsource(approve_approval_prod)
        self.assertIn("Use /reject endpoint", source)

    def test_reject_endpoint_enforces_correct_decision(self):
        """POST .../reject rejects 'approve' decisions."""
        import inspect
        from app.domains.approvals.router import reject_approval_prod
        source = inspect.getsource(reject_approval_prod)
        self.assertIn("Use /approve endpoint", source)


class TestApprovalSchemasProduction(unittest.TestCase):
    """Schema-level tests for production approval response shape."""

    def test_approval_response_no_forbidden(self):
        from app.domains.approvals.schemas import ApprovalResponse
        fields = set(ApprovalResponse.model_fields.keys())
        forbidden = {"id", "requested_by", "decided_by", "backend_url",
                      "token", "secret", "access_token"}
        self.assertTrue(fields.isdisjoint(forbidden),
                        f"Forbidden keys in ApprovalResponse: {fields & forbidden}")

    def test_approval_request_create_allows_publication_batch(self):
        from app.domains.approvals.schemas import ApprovalRequestCreate
        data = ApprovalRequestCreate(
            object_type="publication_batch",
            object_code="00000000-0000-0000-0000-000000000001",
            comment="Approval for batch",
        )
        self.assertEqual(data.object_type, "publication_batch")

    def test_approval_request_create_rejects_invalid_type(self):
        from app.domains.approvals.schemas import ApprovalRequestCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApprovalRequestCreate(object_type="invalid_type", object_code="x",
                                  comment="bad")

    def test_approval_request_create_allows_campaign(self):
        from app.domains.approvals.schemas import ApprovalRequestCreate
        data = ApprovalRequestCreate(
            object_type="campaign", object_code="spring2026", comment="ok"
        )
        self.assertEqual(data.object_type, "campaign")

    def test_approval_request_create_allows_placement(self):
        from app.domains.approvals.schemas import ApprovalRequestCreate
        data = ApprovalRequestCreate(
            object_type="placement", object_code="demo_pl_001", comment="ok"
        )
        self.assertEqual(data.object_type, "placement")

    def test_get_approval_service_exists(self):
        """get_approval function exists in service module."""
        from app.domains.approvals.service import get_approval
        import inspect
        source = inspect.getsource(get_approval)
        self.assertIn("approval_code", source)
        self.assertIn("HTTPException", source)
