"""46.0 — Status lifecycle and publication cleanup tests."""

import os
import re
import unittest

TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "apps", "portal-web", "templates", "pages",
)


def _read(path):
    with open(os.path.join(TEMPLATES_DIR, path)) as f:
        return f.read()


class TestCampaignLifecycle(unittest.TestCase):

    def test_known_statuses(self):
        known = {"draft", "in_review", "approved", "rejected", "archived", "active"}
        for page in ["campaigns.html", "campaigns_detail.html"]:
            content = _read(page)
            badges = re.findall(r"status-badge-(\w+)", content)
            for badge in badges:
                self.assertIn(badge, known | {"pending", "uploaded",
                    "manifest_generated", "published", "cancelled",
                    "pending_approval", "generated", "failed"},
                    f"Unknown status badge '{badge}' in {page}")

    def test_no_pending_approval_for_campaign(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                           "backend", "app", "domains", "campaigns", "service.py")
        with open(path) as f:
            content = f.read()
        self.assertNotIn("pending_approval", content)

    def test_submit_from_draft_or_rejected(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                           "backend", "app", "domains", "campaigns", "service.py")
        with open(path) as f:
            content = f.read()
        self.assertIn('"draft", "rejected"', content)


class TestPortalStatusLabels(unittest.TestCase):

    def test_campaign_detail_has_russian_labels(self):
        content = _read("campaigns_detail.html")
        self.assertIn("Черновик", content)
        self.assertIn("На согласовании", content)
        self.assertIn("Одобрена", content)
        self.assertIn("Отклонена", content)

    def test_publications_have_russian_batch_labels(self):
        content = _read("publications.html")
        self.assertIn("Черновик", content)
        self.assertIn("На согласовании", content)
        self.assertIn("Пакет показа готов", content)
        self.assertIn("Опубликовано", content)

    def test_publications_have_dead_end_guidance(self):
        content = _read("publications.html")
        self.assertIn("Действие завершено", content)

    def test_schedule_has_russian_labels(self):
        content = _read("schedule.html")
        self.assertIn("Черновик", content)
        self.assertIn("Активно", content)
        self.assertIn("Архив", content)

    def test_no_raw_english_status(self):
        for page in ["campaigns_detail.html", "schedule.html",
                     "publications.html", "approvals.html"]:
            content = _read(page)
            for raw in ["draft", "in_review", "pending_approval",
                       "manifest_generated"]:
                standalone = re.findall(r'>%s</' % raw, content)
                self.assertEqual(len(standalone), 0,
                    "%s: raw status '%s' displayed" % (page, raw))


class TestPublicationLifecycle(unittest.TestCase):

    def test_batch_statuses_defined(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                           "backend", "app", "domains", "publications", "schemas.py")
        with open(path) as f:
            content = f.read()
        for status in ["DRAFT", "PENDING_APPROVAL", "APPROVED",
                       "MANIFEST_GENERATED", "PUBLISHED", "REJECTED",
                       "FAILED", "CANCELLED"]:
            self.assertIn(status, content)

    def test_no_physical_delivery_leak(self):
        content = _read("publications.html")
        self.assertIn("заблокирована", content.lower())

    def test_generate_requires_approved(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                           "backend", "app", "domains", "publications", "service.py")
        with open(path) as f:
            content = f.read()
        self.assertIn('batch.status not in ("approved",)', content)


class TestApprovalLifecycle(unittest.TestCase):

    def test_decision_map_defined(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                           "backend", "app", "domains", "approvals", "service.py")
        with open(path) as f:
            content = f.read()
        self.assertIn('"approve": "approved"', content)
        self.assertIn('"reject": "rejected"', content)

    def test_approvals_have_russian_labels(self):
        content = _read("approvals.html")
        self.assertIn("На согласовании", content)
        self.assertIn("Одобрено", content)
        self.assertIn("Отклонено", content)


class TestScheduleLifecycle(unittest.TestCase):

    def test_slot_statuses(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                           "backend", "app", "domains", "scheduling", "models.py")
        with open(path) as f:
            content = f.read()
        self.assertIn('default="active"', content)


class TestAPISchemaStatusConsistency(unittest.TestCase):

    def test_status_field_names(self):
        schemas_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                  "backend", "app", "domains")
        for domain in ["campaigns", "approvals", "publications", "scheduling"]:
            schema_path = os.path.join(schemas_dir, domain, "schemas.py")
            if not os.path.exists(schema_path):
                continue
            with open(schema_path) as f:
                content = f.read()
            self.assertIn("status", content,
                         "%s/schemas.py must define status fields" % domain)

    def test_no_unknown_status_codes(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                           "backend", "app", "domains", "publications", "service.py")
        with open(path) as f:
            content = f.read()
        # Check that status comparisons use known statuses
        known = {"DRAFT", "PENDING_APPROVAL", "APPROVED", "MANIFEST_GENERATED",
                 "PUBLISHED", "REJECTED", "FAILED", "CANCELLED",
                 "draft", "pending_approval", "approved", "manifest_generated",
                 "published", "rejected", "failed", "cancelled",
                 "generated", "pending"}
        status_refs = re.findall(r'batch\.status\s*[!=]=\s*["\'](\w+)["\']', content)
        for ref in status_refs:
            self.assertIn(ref, known,
                         "Unknown batch status reference: %s" % ref)


class TestNoRawStatusVisible(unittest.TestCase):

    def test_no_raw_json_in_status_pages(self):
        for page in ["campaigns_detail.html", "publications.html",
                     "schedule.html", "approvals.html"]:
            content = _read(page)
            self.assertNotIn("application/json", content)

    def test_no_js_in_status_pages(self):
        for page in ["campaigns_detail.html", "publications.html",
                     "schedule.html", "approvals.html"]:
            content = _read(page)
            self.assertNotIn("<script", content)
            self.assertNotIn("onclick", content)


if __name__ == "__main__":
    unittest.main()
