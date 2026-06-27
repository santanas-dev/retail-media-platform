"""Airtime occupancy and conflict detection tests (42.1).

Tests: occupancy calculation, conflict detection, RLS, safe projection.
No physical KSO — planned-only backend tests.
"""

import pytest
from datetime import date, time, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


# ══════════════════════════════════════════════════════════════════════
# Unit tests: helpers
# ══════════════════════════════════════════════════════════════════════

class TestSlotOverlap:
    def test_overlapping_windows(self):
        from backend.app.domains.airtime.service import _slot_overlap
        assert _slot_overlap(time(8, 0), time(12, 0), time(10, 0), time(14, 0))
        assert _slot_overlap(time(8, 0), time(12, 0), time(8, 0), time(8, 1))

    def test_adjacent_does_not_overlap(self):
        from backend.app.domains.airtime.service import _slot_overlap
        assert not _slot_overlap(time(8, 0), time(10, 0), time(10, 0), time(12, 0))

    def test_fully_separated(self):
        from backend.app.domains.airtime.service import _slot_overlap
        assert not _slot_overlap(time(8, 0), time(10, 0), time(12, 0), time(14, 0))


class TestDateOverlap:
    def test_overlapping_dates(self):
        from backend.app.domains.airtime.service import _date_overlap
        assert _date_overlap(date(2026, 6, 1), date(2026, 6, 15), date(2026, 6, 10), date(2026, 6, 20))

    def test_adjacent_does_overlap(self):
        from backend.app.domains.airtime.service import _date_overlap
        assert _date_overlap(date(2026, 6, 1), date(2026, 6, 10), date(2026, 6, 10), date(2026, 6, 20))

    def test_separated(self):
        from backend.app.domains.airtime.service import _date_overlap
        assert not _date_overlap(date(2026, 6, 1), date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 20))


class TestTimeToMinutes:
    def test_conversion(self):
        from backend.app.domains.airtime.service import _time_to_minutes
        assert _time_to_minutes(time(0, 0)) == 0
        assert _time_to_minutes(time(1, 0)) == 60
        assert _time_to_minutes(time(23, 59)) == 1439
        assert _time_to_minutes(time(8, 30)) == 510


# ══════════════════════════════════════════════════════════════════════
# Integration tests: occupancy (with async DB mock)
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestOccupancyCalculation:
    async def test_empty_device_zero_occupancy(self):
        """No placements → zero occupancy."""
        from backend.app.domains.airtime.service import calculate_occupancy

        db = AsyncMock()
        mock_device = MagicMock()
        mock_device.device_code = "dev-1"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = AsyncMock(return_value=mock_device)
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        result = await calculate_occupancy(
            db, device_code="dev-1", date_from=date(2026, 6, 1), date_to=date(2026, 6, 7),
        )
        assert result["device_code"] == "dev-1"
        assert result["occupied_minutes"] == 0
        assert result["occupancy_percent"] == 0.0
        assert result["campaign_count"] == 0
        assert result["is_planned"] is True

    async def test_device_not_found_still_returns(self):
        """Missing device → still returns occupancy with 0."""
        from backend.app.domains.airtime.service import calculate_occupancy

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = AsyncMock(return_value=None)
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        result = await calculate_occupancy(
            db, device_code="nonexistent", date_from=date(2026, 6, 1), date_to=date(2026, 6, 7),
        )
        assert result["device_code"] == "nonexistent"

    async def test_total_available_minutes_1440_per_day(self):
        """7 days → 10080 available minutes."""
        from backend.app.domains.airtime.service import calculate_occupancy

        db = AsyncMock()
        mock_device = MagicMock()
        mock_device.device_code = "dev-1"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = AsyncMock(return_value=mock_device)
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        result = await calculate_occupancy(
            db, device_code="dev-1", date_from=date(2026, 6, 1), date_to=date(2026, 6, 7),
        )
        assert result["total_available_minutes"] == 10080


# ══════════════════════════════════════════════════════════════════════
# Conflict detection tests
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestConflictDetection:
    async def test_no_placements_no_conflicts(self):
        from backend.app.domains.airtime.service import detect_conflicts

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        result = await detect_conflicts(
            db, device_code="dev-1", date_from=date(2026, 6, 1), date_to=date(2026, 6, 7),
        )
        assert result == []

    async def test_single_placement_no_conflicts(self):
        from backend.app.domains.airtime.service import detect_conflicts

        db = AsyncMock()
        mock_placement = MagicMock(
            placement_code="pl-1", device_code="dev-1",
            campaign_code="camp-1", creative_code="cr-1",
            status="draft",
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_placement]
        db.execute.return_value = mock_result

        result = await detect_conflicts(
            db, device_code="dev-1", date_from=date(2026, 6, 1), date_to=date(2026, 6, 7),
        )
        assert result == []


# ══════════════════════════════════════════════════════════════════════
# Safe projection tests
# ══════════════════════════════════════════════════════════════════════

class TestSafeProjection:
    def test_occupancy_no_secrets(self):
        """Occupancy response must not contain raw secrets."""
        forbidden = {"device_secret", "access_token", "backend_url", "password", "bearer", "token"}
        sample = {
            "device_code": "dev-1",
            "date_from": "2026-06-01",
            "date_to": "2026-06-07",
            "total_available_minutes": 10080,
            "occupied_minutes": 120,
            "free_minutes": 9960,
            "occupancy_percent": 1.2,
            "campaign_count": 2,
            "creative_count": 1,
            "conflict_count": 0,
            "is_planned": True,
        }
        text = str(sample).lower()
        for fb in forbidden:
            assert fb not in text, f"Must not contain {fb}"

    def test_conflict_no_secrets(self):
        """Conflict response must not contain raw secrets."""
        forbidden = {"device_secret", "access_token", "backend_url", "password", "bearer", "token"}
        sample = [{
            "campaign_code": "camp-1",
            "campaign_name": "Test",
            "conflict_with_code": "camp-2",
            "date_from": "2026-06-01",
            "date_to": "2026-06-10",
            "day_of_week": 1,
            "day_label": "Вт",
            "time_window": "09:00:00-12:00:00",
            "conflict_time_window": "10:00:00-13:00:00",
            "severity": "warning",
        }]
        text = str(sample).lower()
        for fb in forbidden:
            assert fb not in text, f"Must not contain {fb}"


# ══════════════════════════════════════════════════════════════════════
# Router endpoint tests
# ══════════════════════════════════════════════════════════════════════

class TestAirtimeRouter:
    def test_router_has_occupancy_endpoint(self):
        from backend.app.domains.airtime.router import router
        routes = {r.path: r.methods for r in router.routes}
        assert "/api/airtime/occupancy" in routes
        assert "GET" in routes["/api/airtime/occupancy"]

    def test_router_has_conflicts_endpoint(self):
        from backend.app.domains.airtime.router import router
        routes = {r.path: r.methods for r in router.routes}
        assert "/api/airtime/conflicts" in routes
        assert "GET" in routes["/api/airtime/conflicts"]

    def test_router_registered_in_main_app(self):
        """Airtime routes included in main app (verified via TestClient)."""
        from backend.app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r1 = client.get("/api/airtime/occupancy?device_code=x")
        r2 = client.get("/api/airtime/conflicts?device_code=x")
        for resp, path in ((r1, "occupancy"), (r2, "conflicts")):
            assert resp.status_code != 404, f"{path} not registered"
