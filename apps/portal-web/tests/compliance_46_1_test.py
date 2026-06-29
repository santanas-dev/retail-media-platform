# -*- coding: utf-8 -*-
"""Compliance tests — 46.1: login notice, deactivation, PII visibility, security.

These are pytest-style tests (not unittest.TestCase).
"""
import os
import sys
import pytest
from starlette.testclient import TestClient

from main import app

client = TestClient(app)

# ── Helper: path to repo root ────────────────────────────────────────
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _add_backend_to_path():
    """Add backend/ dir to sys.path so backend model imports work."""
    backend_path = os.path.join(REPO_ROOT, "backend")
    for p in (REPO_ROOT, backend_path):
        if p not in sys.path:
            sys.path.insert(0, p)


class TestLoginPrivacyNotice:
    """Verify the privacy notice is present on the login page."""

    def test_login_page_shows_privacy_notice(self):
        """The login page should show the compliance notice block."""
        response = client.get("/login")
        assert response.status_code == 200
        html = response.text
        assert "Уведомление о работе с данными" in html
        assert "служебного использования" in html
        assert "журналируются" in html
        assert "Не вводите персональные данные" in html

    def test_login_page_has_compliance_link(self):
        """Login page should link to the full compliance page."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "/compliance" in response.text


class TestCompliancePages:
    """Verify public compliance pages are accessible."""

    def test_compliance_page_public(self):
        response = client.get("/compliance")
        assert response.status_code == 200
        assert "Правила использования" in response.text
        assert "Назначение системы" in response.text
        assert "Журналирование действий" in response.text

    def test_compliance_retention_page_public(self):
        response = client.get("/compliance/retention")
        assert response.status_code == 200
        assert "Сроки хранения данных" in response.text

    def test_compliance_pages_no_auth_required(self):
        for url in ["/compliance", "/compliance/retention"]:
            response = client.get(url)
            assert response.status_code == 200, f"{url} should be public"


class TestDeactivationDocs:
    """Verify deactivation procedure documentation exists."""

    def test_deactivation_docs_exist(self):
        doc_path = os.path.join(REPO_ROOT, "docs", "compliance",
                                "deletion-deactivation-procedure-46-1.md")
        assert os.path.exists(doc_path), f"Missing: {doc_path}"

    def test_retention_policy_docs_exist(self):
        doc_path = os.path.join(REPO_ROOT, "docs", "compliance",
                                "data-retention-policy-46-1.md")
        assert os.path.exists(doc_path), f"Missing: {doc_path}"


class TestBackendModelsCompliance:
    """Verify backend models have expected compliance-related fields."""

    @classmethod
    def setup_class(cls):
        _add_backend_to_path()

    def test_user_model_has_archive_fields(self):
        from backend.app.domains.identity.models import User
        assert hasattr(User, "is_archived")
        assert hasattr(User, "archived_by")
        assert hasattr(User, "archived_at")

    def test_user_model_has_is_active(self):
        from backend.app.domains.identity.models import User
        assert hasattr(User, "is_active")
        assert hasattr(User, "is_locked")

    def test_backend_has_status_user_schema(self):
        from backend.app.domains.identity.schemas import UserStatusUpdate
        assert UserStatusUpdate is not None

    def test_login_audit_uses_hashes(self):
        from backend.app.domains.identity.models import LoginAuditEvent
        assert hasattr(LoginAuditEvent, "ip_hash")
        assert hasattr(LoginAuditEvent, "user_agent_hash")
        assert not hasattr(LoginAuditEvent, "ip_address")
        assert not hasattr(LoginAuditEvent, "user_agent")

    def test_admin_audit_has_details_json(self):
        from backend.app.domains.identity.models import AdminAuditEvent
        assert hasattr(AdminAuditEvent, "details_json")


class TestPiiVisibility:
    """Verify PII is not exposed in public/regular-user UI."""

    def test_login_page_no_email_field(self):
        response = client.get("/login")
        assert 'type="email"' not in response.text.lower()
        assert 'name="email"' not in response.text

    def test_compliance_page_no_internal_urls(self):
        response = client.get("/compliance")
        html = response.text
        assert "127.0.0.1" not in html
        assert "localhost" not in html
        assert "192.168" not in html


class TestSecurityCookieHeaders:
    """Verify security-related cookie and session behavior."""

    def test_portal_session_cookie_name(self):
        from portal_session import SESSION_COOKIE_NAME
        assert SESSION_COOKIE_NAME == "portal_session_id"

    def test_no_localstorage_in_templates(self):
        templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        for root, dirs, files in os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    filepath = os.path.join(root, f)
                    with open(filepath) as fh:
                        content = fh.read()
                    assert "localStorage" not in content, f"localStorage in {filepath}"

    def test_no_js_cdn_in_templates(self):
        templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        cdn_patterns = [
            "cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com",
            "ajax.googleapis.com", "code.jquery.com",
        ]
        for root, dirs, files in os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    filepath = os.path.join(root, f)
                    with open(filepath) as fh:
                        content = fh.read()
                    for pattern in cdn_patterns:
                        assert pattern not in content, f"CDN {pattern} in {filepath}"


class TestComplianceDocsExist:
    """Verify all compliance documentation files exist."""

    def test_all_compliance_docs_present(self):
        docs_dir = os.path.join(REPO_ROOT, "docs", "compliance")
        expected_docs = [
            "personal-data-inventory-46-1.md",
            "data-retention-policy-46-1.md",
            "deletion-deactivation-procedure-46-1.md",
            "login-notice-46-1.md",
            "login-logout-audit-mapping-46-1.md",
            "security-headers-cookie-review-46-1.md",
            "compliance-readiness-46-1.md",
        ]
        for doc in expected_docs:
            path = os.path.join(docs_dir, doc)
            assert os.path.exists(path), f"Missing compliance doc: {doc}"


class TestAuditSchemaNoLeaks:
    """Verify audit response schemas don't leak secrets/PII."""

    @classmethod
    def setup_class(cls):
        _add_backend_to_path()

    def test_admin_audit_response_no_email(self):
        from backend.app.domains.identity.schemas import AdminAuditResponse
        if hasattr(AdminAuditResponse, "__annotations__"):
            assert "email" not in AdminAuditResponse.__annotations__
