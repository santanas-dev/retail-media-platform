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
        self.assertIn("backend-only", content)


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
