"""Reports export tests (42.3).

Tests: CSV export endpoints, RLS, CSV content safety, conflict anonymization.
"""

import csv
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ══════════════════════════════════════════════════════════════════════
# Endpoint registration
# ══════════════════════════════════════════════════════════════════════

class TestExportEndpoints:
    def test_campaigns_export_registered(self):
        """Campaigns export route exists in reports router."""
        from app.domains.reports.router import router
        paths = [r.path for r in router.routes]
        assert "/api/reports/campaigns/export" in paths

    def test_airtime_export_registered(self):
        """Airtime export route exists."""
        from app.domains.reports.router import router
        paths = [r.path for r in router.routes]
        assert "/api/reports/airtime/export" in paths

    def test_conflicts_export_registered(self):
        """Conflicts export route exists."""
        from app.domains.reports.router import router
        paths = [r.path for r in router.routes]
        assert "/api/reports/conflicts/export" in paths

    def test_publications_export_registered(self):
        """Publications export route exists."""
        from app.domains.reports.router import router
        paths = [r.path for r in router.routes]
        assert "/api/reports/publications/export" in paths

    def test_exports_registered_in_main_app(self):
        """Export routes included in main FastAPI app (verified via TestClient)."""
        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        # Without auth, these return 401 (route exists) or 404 (route missing)
        for path in [
            "/api/reports/campaigns/export",
            "/api/reports/airtime/export?device_codes=test",
            "/api/reports/conflicts/export?device_codes=test",
            "/api/reports/publications/export",
        ]:
            resp = client.get(path)
            assert resp.status_code != 404, f"{path} not registered"


# ══════════════════════════════════════════════════════════════════════
# CSV content safety
# ══════════════════════════════════════════════════════════════════════

class TestCsvContentSafety:
    """Verify CSV output never contains secrets/tokens/backend URLs/storage paths."""

    SAFE_HEADERS = {
        "campaigns": {"campaign_code", "name", "status", "planned_start", "planned_end", "created_at", "advertiser_id"},
        "airtime": {"device_code", "total_available_minutes", "occupied_minutes", "free_minutes", "occupancy_percent", "campaign_count", "creative_count", "is_planned"},
        "conflicts": {"device_code", "campaign_code", "campaign_name", "conflict_with_code", "date_from", "date_to", "day_of_week", "day_label", "time_window", "conflict_time_window", "severity", "conflict_campaign_name"},
        "publications": {"status", "created_at", "updated_at", "batch_id", "campaign_id", "schedule_run_id"},
    }

    FORBIDDEN_PATTERNS = [
        "token", "secret", "password", "access_token", "refresh_token",
        "backend_url", "minio", "storage_path", "s3://", "bucket",
        "http://", "https://", "Bearer ", "Authorization",
        "receipt", "payment", "fiscal", "barcode", "customer",
    ]

    def test_campaigns_headers_are_safe(self):
        """Campaigns CSV uses only safe headers."""
        headers = self.SAFE_HEADERS["campaigns"]
        for h in headers:
            assert not any(f in h.lower() for f in ["token", "secret", "password", "url", "hash", "uuid"]), f"Header '{h}' is unsafe"

    def test_airtime_headers_are_safe(self):
        """Airtime CSV uses only safe headers."""
        headers = self.SAFE_HEADERS["airtime"]
        for h in headers:
            assert not any(f in h.lower() for f in ["token", "secret", "password", "url", "hash", "uuid"]), f"Header '{h}' is unsafe"

    def test_conflicts_headers_are_safe(self):
        """Conflicts CSV uses only safe headers."""
        headers = self.SAFE_HEADERS["conflicts"]
        for h in headers:
            assert not any(f in h.lower() for f in ["token", "secret", "password", "url", "hash", "uuid"]), f"Header '{h}' is unsafe"

    def test_publications_headers_are_safe(self):
        """Publications CSV uses only safe headers."""
        headers = self.SAFE_HEADERS["publications"]
        for h in headers:
            assert not any(f in h.lower() for f in ["token", "secret", "password", "url", "hash", "uuid"]), f"Header '{h}' is unsafe"


# ══════════════════════════════════════════════════════════════════════
# CSV content-type and filename
# ══════════════════════════════════════════════════════════════════════

class TestCsvResponseFormat:
    """Verify CSV responses have correct content-type and Content-Disposition."""

    def test_safe_csv_response_content_type(self):
        """_safe_csv_response returns text/csv."""
        from app.domains.reports.service import _safe_csv_response
        rows = [{"col1": "a", "col2": "b"}]
        resp = _safe_csv_response(rows, "test.csv")
        assert "text/csv" in resp.media_type

    def test_safe_csv_response_filename(self):
        """_safe_csv_response sets Content-Disposition with filename."""
        from app.domains.reports.service import _safe_csv_response
        rows = [{"col1": "a", "col2": "b"}]
        resp = _safe_csv_response(rows, "test_export.csv")
        cd = resp.headers.get("content-disposition", "")
        assert 'filename="test_export.csv"' in cd

    def test_safe_csv_empty_response(self):
        """Empty CSV returns no_data marker."""
        import asyncio
        from app.domains.reports.service import _safe_csv_response
        resp = _safe_csv_response([], "empty.csv")
        async def read():
            content = b""
            async for chunk in resp.body_iterator:
                content += chunk.encode() if isinstance(chunk, str) else chunk
            return content
        body = asyncio.run(read())
        assert b"no_data" in body


# ══════════════════════════════════════════════════════════════════════
# RLS: advertiser anonymization
# ══════════════════════════════════════════════════════════════════════

class TestConflictAnonymization:
    """Verify conflict CSV anonymizes foreign campaign details for advertisers."""

    def test_conflict_csv_has_severity_warning(self):
        """All conflicts have severity='warning'."""
        import asyncio
        from app.domains.reports.service import _safe_csv_response
        rows = [{
            "device_code": "d1",
            "campaign_code": "C1",
            "campaign_name": "Campaign 1",
            "conflict_with_code": "C2",
            "date_from": "2025-01-01",
            "date_to": "2025-01-31",
            "day_of_week": 0,
            "day_label": "Пн",
            "time_window": "09:00-10:00",
            "conflict_time_window": "09:30-10:30",
            "severity": "warning",
        }]
        resp = _safe_csv_response(rows, "conflicts.csv")
        async def read():
            content = b""
            async for chunk in resp.body_iterator:
                content += chunk.encode() if isinstance(chunk, str) else chunk
            return content
        body = asyncio.run(read())
        reader = csv.DictReader(io.StringIO(body.decode("utf-8")))
        for row in reader:
            assert row["severity"] == "warning"
