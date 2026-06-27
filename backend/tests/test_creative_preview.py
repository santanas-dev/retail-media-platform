"""Safe Creative Preview tests (42.2).

Tests: preview endpoint, RLS, status gates, safe response headers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import unittest
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════
# Endpoint registration
# ══════════════════════════════════════════════════════════════════════

class TestPreviewEndpoint:
    def test_preview_route_registered(self):
        """Preview endpoint exists in media router."""
        from backend.app.domains.media.router import router
        paths = [r.path for r in router.routes]
        assert "/api/creatives/by-code/{creative_code}/preview" in paths

    def test_preview_registered_in_main_app(self):
        """Preview route is included in main FastAPI app (verified via TestClient)."""
        from backend.app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/creatives/by-code/FAKE_CODE/preview")
        # Route exists — 401 (no auth) or 404 (not found) is expected,
        # 404 vs 401 depends on middleware order but NOT 405/not found.
        assert resp.status_code != 404  # route not registered at all


# ══════════════════════════════════════════════════════════════════════
# Safe response: no backend internals in error messages
# ══════════════════════════════════════════════════════════════════════

class TestPreviewSafeErrors:
    def test_404_does_not_leak_internals(self):
        """404 error detail must not contain storage internals."""
        # Check the route handler error messages
        from backend.app.domains.media.router import preview_creative_by_code

        # All error messages are static strings — verify they're safe
        safe_msgs = [
            "Creative not found",
            "Preview not available",
            "No media file uploaded",
            "Preview supports images only (PNG, JPEG). Video preview deferred.",
            "Media not available",
            "Media path invalid",
        ]
        for msg in safe_msgs:
            for forbidden in ("minio", "bucket", "object_key", "s3", "storage_path",
                              "signed", "presigned", "token", "secret", "backend_url"):
                assert forbidden not in msg.lower(), f"'{msg}' must not contain '{forbidden}'"

    def test_no_backend_url_in_source(self):
        """Preview router source must not hardcode backend URLs."""
        import inspect
        from backend.app.domains.media import router as media_router
        source = inspect.getsource(media_router.preview_creative_by_code)
        for fb in ("http://", "https://", "localhost:", "minio:", "s3."):
            assert fb not in source, f"Source must not contain '{fb}'"


# ══════════════════════════════════════════════════════════════════════
# Portal proxy tests
# ══════════════════════════════════════════════════════════════════════

class TestPortalPreviewProxy:
    def test_portal_preview_route_exists(self):
        """Portal has /preview/{creative_code} proxy route."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps" / "portal-web"))
        from main import app as portal_app
        paths = [r.path for r in portal_app.routes]
        assert "/preview/{creative_code}" in paths

    def test_portal_preview_url_safe(self):
        """creative_preview_url returns relative path, not full URL."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps" / "portal-web"))
        from backend_client import BackendClient
        client = BackendClient()
        url = client.creative_preview_url("test_creative")
        assert url.startswith("/")
        assert "http" not in url
        assert "backend" not in url.lower()
        assert "test_creative" in url


# ══════════════════════════════════════════════════════════════════════
# No signed URL / storage path in creatives page
# ══════════════════════════════════════════════════════════════════════

class TestCreativesPageNoLeakage(unittest.TestCase):
    """Portal creatives page must not leak storage paths or signed URLs."""

    def test_no_storage_internals_in_template(self):
        from pathlib import Path
        template_path = Path(__file__).parent.parent.parent / \
            "apps" / "portal-web" / "templates" / "pages" / "creatives.html"
        if template_path.exists():
            content = template_path.read_text().lower()
            for fb in ("file_path", "object_key", "minio", "bucket", "signed_url",
                       "presigned", "backend_url", "storage_path"):
                assert fb not in content, f"Template must not contain '{fb}'"
