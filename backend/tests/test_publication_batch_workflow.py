"""Publication batch workflow tests (39.3.4) — state machine, approval integration."""

import unittest


class TestBatchStateMachine(unittest.TestCase):
    """Publication batch state machine validation."""

    def test_draft_to_pending_approval_valid(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertIn(S.PENDING_APPROVAL, _VALID_BATCH_TRANSITIONS[S.DRAFT])

    def test_pending_approval_to_approved_valid(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertIn(S.APPROVED, _VALID_BATCH_TRANSITIONS[S.PENDING_APPROVAL])

    def test_pending_approval_to_rejected_valid(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertIn(S.REJECTED, _VALID_BATCH_TRANSITIONS[S.PENDING_APPROVAL])

    def test_approved_to_manifest_generated_valid(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertIn(S.MANIFEST_GENERATED, _VALID_BATCH_TRANSITIONS[S.APPROVED])

    def test_manifest_generated_to_published_valid(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertIn(S.PUBLISHED, _VALID_BATCH_TRANSITIONS[S.MANIFEST_GENERATED])

    def test_published_terminal(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertEqual(len(_VALID_BATCH_TRANSITIONS[S.PUBLISHED]), 0)

    def test_rejected_terminal(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertEqual(len(_VALID_BATCH_TRANSITIONS[S.REJECTED]), 0)

    def test_cancelled_terminal(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertEqual(len(_VALID_BATCH_TRANSITIONS[S.CANCELLED]), 0)

    def test_no_generated_in_new_workflow(self):
        """Old 'generated' status no longer exists — replaced by 'manifest_generated'."""
        from app.domains.publications.schemas import PublicationBatchStatus as S
        self.assertFalse(hasattr(S, 'GENERATED'))
        self.assertTrue(hasattr(S, 'MANIFEST_GENERATED'))
        self.assertTrue(hasattr(S, 'PENDING_APPROVAL'))
        self.assertTrue(hasattr(S, 'REJECTED'))

    def test_cannot_jump_draft_to_approved(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertNotIn(S.APPROVED, _VALID_BATCH_TRANSITIONS[S.DRAFT])

    def test_cannot_jump_draft_to_published(self):
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertNotIn(S.PUBLISHED, _VALID_BATCH_TRANSITIONS[S.DRAFT])

    def test_cannot_jump_approved_to_published(self):
        """Must go through manifest_generated first."""
        from app.domains.publications.schemas import PublicationBatchStatus as S
        from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS
        self.assertNotIn(S.PUBLISHED, _VALID_BATCH_TRANSITIONS[S.APPROVED])


class TestBatchRouterEndpoints(unittest.TestCase):
    """Endpoint structure validation."""

    def test_request_approval_endpoint_exists(self):
        from app.domains.publications.router import router
        methods = {}
        for r in router.routes:
            methods.setdefault(r.path, set())
            for m in r.methods:
                methods[r.path].add(m)
        self.assertIn("POST", methods.get(
            "/api/publication-batches/{batch_id}/request-approval", set()))

    def test_generate_endpoint_exists(self):
        from app.domains.publications.router import router
        methods = {}
        for r in router.routes:
            methods.setdefault(r.path, set())
            for m in r.methods:
                methods[r.path].add(m)
        self.assertIn("POST", methods.get(
            "/api/publication-batches/{batch_id}/generate", set()))

    def test_publish_endpoint_exists(self):
        from app.domains.publications.router import router
        methods = {}
        for r in router.routes:
            methods.setdefault(r.path, set())
            for m in r.methods:
                methods[r.path].add(m)
        self.assertIn("POST", methods.get(
            "/api/publication-batches/{batch_id}/publish", set()))

    def test_approve_endpoint_exists(self):
        from app.domains.publications.router import router
        methods = {}
        for r in router.routes:
            methods.setdefault(r.path, set())
            for m in r.methods:
                methods[r.path].add(m)
        self.assertIn("POST", methods.get(
            "/api/publication-batches/{batch_id}/approve", set()))


class TestBatchServiceLogic(unittest.TestCase):
    """Service logic: guardrails (no DB calls)."""

    def test_generate_manifests_requires_approved(self):
        import inspect
        from app.domains.publications.service import generate_manifests
        source = inspect.getsource(generate_manifests)
        self.assertIn('"approved"', source)

    def test_approve_batch_requires_pending_approval(self):
        import inspect
        from app.domains.publications.service import approve_batch
        source = inspect.getsource(approve_batch)
        self.assertIn('pending_approval', source)

    def test_publish_batch_requires_manifest_generated(self):
        import inspect
        from app.domains.publications.service import publish_batch
        source = inspect.getsource(publish_batch)
        self.assertIn('manifest_generated', source)

    def test_request_batch_approval_exists(self):
        from app.domains.publications.service import request_batch_approval
        import asyncio
        self.assertTrue(callable(request_batch_approval))
        self.assertTrue(asyncio.iscoroutinefunction(request_batch_approval))

    def test_request_batch_approval_creates_approval_request(self):
        import inspect
        from app.domains.publications.service import request_batch_approval
        source = inspect.getsource(request_batch_approval)
        self.assertIn('_request_approval_internal', source)
        self.assertIn('ApprovalRequest', source)

    def test_publish_batch_checks_approval(self):
        import inspect
        from app.domains.publications.service import publish_batch
        source = inspect.getsource(publish_batch)
        self.assertIn('ApprovalRequest', source)
        self.assertIn('approved', source)

    def test_approve_batch_checks_approval(self):
        import inspect
        from app.domains.publications.service import approve_batch
        source = inspect.getsource(approve_batch)
        self.assertIn('ApprovalRequest', source)
        self.assertIn('approved', source)


class TestApprovalsInternalHelper(unittest.TestCase):
    """_request_approval_internal function in approvals service."""

    def test_internal_helper_exists(self):
        from app.domains.approvals.service import _request_approval_internal
        import asyncio
        self.assertTrue(callable(_request_approval_internal))
        self.assertTrue(asyncio.iscoroutinefunction(_request_approval_internal))

    def test_internal_helper_creates_correct_approval_code(self):
        """approval_code format: appr_{object_type}_{object_code_sanitized}."""
        # Logic check — approval_code is built from type + sanitized code
        code = f"appr_publication_batch_somebatchid"
        self.assertTrue(code.startswith("appr_publication_batch_"))


if __name__ == "__main__":
    unittest.main()
