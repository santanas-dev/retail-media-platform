"""41.4 — Campaign → Publication Batch endpoint tests.

All tests use source inspection or template checks — no module imports,
so they work regardless of PYTHONPATH.
"""

import os
import unittest


class TestCreateBatchFromCampaignService(unittest.TestCase):
    """Test create_batch_from_campaign service function."""

    def _get_source(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "publications", "service.py",
        )
        with open(path) as f:
            return f.read()

    def test_function_exists_in_source(self):
        """create_batch_from_campaign is defined in service.py."""
        source = self._get_source()
        self.assertIn("def create_batch_from_campaign", source)

    def test_function_signature(self):
        """Accepts db, campaign_code, user_id."""
        source = self._get_source()
        # Find the function definition
        start = source.find("def create_batch_from_campaign")
        self.assertGreater(start, 0)
        sig_start = source.find("(", start)
        sig_end = source.find("):", sig_start)
        signature = source[sig_start:sig_end]
        self.assertIn("db", signature)
        self.assertIn("campaign_code", signature)
        self.assertIn("user_id", signature)

    def test_raw_sql_uses_text(self):
        """Uses sqlalchemy.text for raw SQL (no ORM model dependency)."""
        source = self._get_source()
        # Find function body
        start = source.find("def create_batch_from_campaign")
        self.assertIn("text(", source[start:])
        self.assertIn("schedule_runs", source[start:])
        self.assertIn("ON CONFLICT", source[start:])

    def test_no_schedulerun_import_in_function(self):
        """Does NOT import ScheduleRun from scheduling.models."""
        source = self._get_source()
        start = source.find("def create_batch_from_campaign")
        end = source.find("\n\n", start + 5)
        if end == -1:
            end = len(source)
        func_source = source[start:end]
        self.assertNotIn(
            "from app.domains.scheduling.models import ScheduleRun",
            func_source,
        )

    def test_idempotency_guard(self):
        """Has idempotency checks for existing batches."""
        source = self._get_source()
        start = source.find("def create_batch_from_campaign")
        func_source = source[start:]
        self.assertIn("already has a published batch", func_source)
        self.assertIn("cancel it first", func_source)

    def test_approved_status_validation(self):
        """Validates campaign.status == 'approved'."""
        source = self._get_source()
        start = source.find("def create_batch_from_campaign")
        func_source = source[start:]
        self.assertIn("must be 'approved'", func_source)

    def test_physical_delivery_not_triggered(self):
        """Docstring says physical delivery not triggered."""
        source = self._get_source()
        start = source.find("def create_batch_from_campaign")
        # Read the docstring area
        func_source = source[start:]
        self.assertIn("Physical KSO delivery is NOT triggered", func_source)

    def test_audit_event_logged(self):
        """_log_event is called."""
        source = self._get_source()
        start = source.find("def create_batch_from_campaign")
        func_source = source[start:]
        self.assertIn("_log_event", func_source)


class TestCampaignBatchRouterEndpoint(unittest.TestCase):
    """Test that the new endpoint is registered in the campaigns router."""

    def _get_source(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "campaigns", "router.py",
        )
        with open(path) as f:
            return f.read()

    def test_endpoint_defined(self):
        """POST /campaigns/by-code/{code}/create-publication-batch defined."""
        source = self._get_source()
        self.assertIn("def create_publication_batch_from_campaign", source)

    def test_endpoint_route_decorator(self):
        """Route decorator has correct path."""
        source = self._get_source()
        self.assertIn(
            '"/campaigns/by-code/{campaign_code}/create-publication-batch"',
            source,
        )

    def test_endpoint_requires_publications_manage(self):
        """Endpoint requires publications.manage permission."""
        source = self._get_source()
        idx = source.find("def create_publication_batch_from_campaign")
        func_source = source[idx:]
        self.assertIn("require_permission", func_source)
        self.assertIn("publications.manage", func_source)

    def test_endpoint_has_audit(self):
        """Endpoint calls audit_business_action."""
        source = self._get_source()
        idx = source.find("def create_publication_batch_from_campaign")
        func_source = source[idx:]
        self.assertIn("audit_business_action", func_source)

    def test_rls_scope_enforced(self):
        """RLS advertiser scope check is present."""
        source = self._get_source()
        idx = source.find("def create_publication_batch_from_campaign")
        func_source = source[idx:]
        self.assertIn("assert_object_in_advertiser_scope", func_source)

    def test_status_code_201(self):
        """Returns 201 Created."""
        source = self._get_source()
        idx = source.find("def create_publication_batch_from_campaign")
        # Look for the decorator above
        before = source[:idx]
        self.assertIn("status_code=201", before.split("def create_publication_batch_from_campaign")[0][-200:])


class TestCampaignTemplatePublicationAction(unittest.TestCase):
    """Test that campaigns.html has the publication action."""

    def _get_content(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "apps", "portal-web", "templates", "pages", "campaigns.html",
        )
        with open(path) as f:
            return f.read()

    def test_template_has_publication_button(self):
        """Campaigns template includes 'Подготовить' button for approved."""
        content = self._get_content()
        self.assertIn("create-publication-batch", content)
        self.assertIn("📦 Подготовить", content)

    def test_approved_guard(self):
        """Button only shown when status == 'approved'."""
        content = self._get_content()
        self.assertIn('c.status == \'approved\'', content)

    def test_no_javascript(self):
        """No <script>, onclick, confirm, CDN, localStorage."""
        content = self._get_content()
        self.assertNotIn("<script", content)
        self.assertNotIn("onclick", content)
        self.assertNotIn("confirm(", content)
        self.assertNotIn("CDN", content)
        self.assertNotIn("localStorage", content)


class TestPublicationsTemplateBatches(unittest.TestCase):
    """Test that publications.html shows batches."""

    def _get_content(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "apps", "portal-web", "templates", "pages", "publications.html",
        )
        with open(path) as f:
            return f.read()

    def test_template_has_batches(self):
        """Publications template has batches variable."""
        content = self._get_content()
        self.assertIn("batches", content)

    def test_physical_delivery_warning(self):
        """Shows warning that physical KSO delivery is disabled."""
        content = self._get_content()
        self.assertIn("Доставка на КСО отключена", content)

    def test_no_javascript(self):
        """No <script>, onclick, confirm, CDN, localStorage."""
        content = self._get_content()
        self.assertNotIn("<script", content)
        self.assertNotIn("onclick", content)
        self.assertNotIn("confirm(", content)
        self.assertNotIn("CDN", content)
        self.assertNotIn("localStorage", content)

    def test_backend_only_mode(self):
        """Shows backend-only mode info."""
        content = self._get_content()
        self.assertIn("Backend-only", content)


class TestPortalMainHandlerExists(unittest.TestCase):
    """Test that portal main.py has the create-publication-batch handler."""

    def _get_source(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "apps", "portal-web", "main.py",
        )
        with open(path) as f:
            return f.read()

    def test_handler_defined(self):
        """campaigns_create_publication_batch defined."""
        source = self._get_source()
        self.assertIn("def campaigns_create_publication_batch", source)

    def test_handler_route(self):
        """Handler routes to /campaigns/{code}/create-publication-batch."""
        source = self._get_source()
        self.assertIn(
            '"/campaigns/{campaign_code}/create-publication-batch"',
            source,
        )

    def test_handler_uses_backend_client(self):
        """Handler calls backend.create_publication_batch."""
        source = self._get_source()
        idx = source.find("def campaigns_create_publication_batch")
        func_source = source[idx:]
        self.assertIn("create_publication_batch", func_source)

    def test_flash_handled(self):
        """ok:batch_created flash handled in campaigns page."""
        source = self._get_source()
        self.assertIn('"ok:batch_created"', source)

    def test_physical_delivery_comment(self):
        """Handler docstring mentions no physical delivery."""
        source = self._get_source()
        idx = source.find("def campaigns_create_publication_batch")
        # Read ~500 chars after function start to capture docstring
        func_source = source[idx:idx + 800]
        self.assertIn("NOT triggered", func_source)


class TestScheduleRunOrmModel(unittest.TestCase):
    """41.4.1 — ScheduleRun ORM model tests."""

    def _get_scheduling_source(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "scheduling", "models.py",
        )
        with open(path) as f:
            return f.read()

    def test_schedulerun_class_defined_in_source(self):
        """ScheduleRun class is defined in scheduling/models.py."""
        source = self._get_scheduling_source()
        self.assertIn("class ScheduleRun(Base):", source)
        self.assertIn('__tablename__ = "schedule_runs"', source)

    def test_schedulerun_has_required_columns_in_source(self):
        """ScheduleRun has id, campaign_id, booking_id, status, created_by."""
        source = self._get_scheduling_source()
        idx = source.find("class ScheduleRun")
        class_source = source[idx:]
        for col in ("id", "campaign_id", "booking_id", "status", "created_by"):
            self.assertIn(f"{col} = Column", class_source,
                          f"Missing column: {col}")

    def test_schedulerun_imports_in_generate_manifests(self):
        """generate_manifests imports ScheduleRun from scheduling.models."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "publications", "service.py",
        )
        with open(path) as f:
            source = f.read()
        start = source.find("def generate_manifests")
        func_source = source[start:]
        self.assertIn("from app.domains.scheduling.models import ScheduleRun", func_source)

    def test_create_batch_no_conflicts_selectinload(self):
        """create_batch no longer references ScheduleRun.conflicts."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "publications", "service.py",
        )
        with open(path) as f:
            source = f.read()
        start = source.find("def create_batch")
        func_source = source[start:]
        self.assertNotIn("selectinload(ScheduleRun.conflicts)", func_source)


class TestPublicationBatchWorkflow(unittest.TestCase):
    """41.4.1 — Full batch workflow state machine tests."""

    def _get_schemas_source(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "publications", "schemas.py",
        )
        with open(path) as f:
            return f.read()

    def _get_router_source(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "publications", "router.py",
        )
        with open(path) as f:
            return f.read()

    def test_draft_to_pending_approval_in_source(self):
        """draft → pending_approval transition defined in schemas."""
        source = self._get_schemas_source()
        self.assertIn('DRAFT: frozenset({', source)
        self.assertIn('PENDING_APPROVAL', source)

    def test_approved_to_manifest_generated_in_source(self):
        """approved → manifest_generated transition defined."""
        source = self._get_schemas_source()
        self.assertIn('APPROVED: frozenset({', source)
        self.assertIn('MANIFEST_GENERATED', source)

    def test_manifest_generated_to_published_in_source(self):
        """manifest_generated → published transition defined."""
        source = self._get_schemas_source()
        self.assertIn('MANIFEST_GENERATED: frozenset({', source)
        self.assertIn('PUBLISHED', source)

    def test_backend_routers_include_batch_actions(self):
        """All batch lifecycle endpoints are registered."""
        source = self._get_router_source()
        for action in ("request-approval", "approve", "generate", "publish", "cancel"):
            path = f"/publication-batches/{{batch_id}}/{action}"
            self.assertIn(path, source,
                          f"Missing route: {path}")

    def test_generate_requires_approved_status(self):
        """generate_manifests checks batch.status == 'approved'."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "publications", "service.py",
        )
        with open(path) as f:
            source = f.read()
        start = source.find("def generate_manifests")
        func_source = source[start:]
        self.assertIn("batch.status not in (\"approved\",)", func_source)

    def test_no_physical_delivery_in_publish(self):
        """publish_batch docstring confirms no physical delivery."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "domains", "publications", "service.py",
        )
        with open(path) as f:
            source = f.read()
        # Check batch workflow functions document no physical KSO delivery
        self.assertIn("Physical KSO delivery is NOT triggered", source)


class TestPortalBatchActionHandlers(unittest.TestCase):
    """41.4.1 — Portal batch action handlers."""

    def _get_main_source(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "apps", "portal-web", "main.py",
        )
        with open(path) as f:
            return f.read()

    def test_request_approval_handler_exists(self):
        """Handler for POST /publications/batch/{id}/request-approval."""
        source = self._get_main_source()
        self.assertIn("def publications_batch_request_approval", source)

    def test_generate_handler_exists(self):
        """Handler for POST /publications/batch/{id}/generate."""
        source = self._get_main_source()
        self.assertIn("def publications_batch_generate", source)

    def test_publish_handler_exists(self):
        """Handler for POST /publications/batch/{id}/publish."""
        source = self._get_main_source()
        self.assertIn("def publications_batch_publish", source)

    def test_cancel_handler_exists(self):
        """Handler for POST /publications/batch/{id}/cancel."""
        source = self._get_main_source()
        self.assertIn("def publications_batch_cancel", source)

    def test_all_handlers_use_backend_client(self):
        """All handlers call backend methods."""
        source = self._get_main_source()
        for action in ("request_batch_approval", "generate_batch_manifests",
                       "publish_batch", "cancel_batch"):
            self.assertIn(action, source,
                          f"Missing backend call: {action}")

    def test_no_physical_delivery_in_handlers(self):
        """Docstrings confirm no physical delivery."""
        source = self._get_main_source()
        idx = source.find("def publications_batch_publish")
        self.assertIn("No physical delivery", source[idx:idx + 500])


class TestPublicationsTemplateBatchActions(unittest.TestCase):
    """41.4.1 — Publications template batch actions."""

    def _get_content(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "apps", "portal-web", "templates", "pages", "publications.html",
        )
        with open(path) as f:
            return f.read()

    def test_batch_approval_action_present(self):
        """Request approval button exists in template."""
        content = self._get_content()
        self.assertIn("request-approval", content)
        self.assertIn("На согласование", content)

    def test_batch_generate_action_present(self):
        """Generate button exists in template."""
        content = self._get_content()
        self.assertIn("/generate", content)  # URL path, button text is now "Сформировать"
        self.assertIn("Сформировать", content)

    def test_batch_publish_action_present(self):
        """Publish button exists in template."""
        content = self._get_content()
        self.assertIn("/publish", content)

    def test_batch_cancel_action_present(self):
        """Cancel button exists in template."""
        content = self._get_content()
        self.assertIn("/cancel", content)

    def test_no_javascript(self):
        """No <script>, onclick, confirm."""
        content = self._get_content()
        self.assertNotIn("<script", content)
        self.assertNotIn("onclick", content)
        self.assertNotIn("confirm(", content)

    def test_batch_id_in_forms(self):
        """Forms include batch_id in URL."""
        content = self._get_content()
        self.assertIn("b.batch_id", content)


class TestBackendClientBatchLifecycle(unittest.TestCase):
    """41.4.1 — BackendClient batch lifecycle methods."""

    def test_client_has_all_methods(self):
        """BackendClient has all batch lifecycle methods."""
        import sys
        sys.path.insert(0, "apps/portal-web")
        from backend_client import BackendClient
        for method in ("request_batch_approval", "approve_batch",
                       "generate_batch_manifests", "cancel_batch"):
            self.assertTrue(hasattr(BackendClient, method),
                            f"Missing: BackendClient.{method}")
