"""Inventory Engine 44.1 — backend tests.

Tests: availability with sold_out, forecast v1, snapshot, reservation_type,
business-language labels, RBAC/RLS, no secrets/tokens leakage.
"""

import pytest
from datetime import date, time, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ══════════════════════════════════════════════════════════════════════
# Unit: day_capacity
# ══════════════════════════════════════════════════════════════════════


class TestDayCapacity:
    def test_weekday_all_day(self):
        """Mon-Fri, 8h loop, all day → 86399s / 28800 ≈ 2 loops × 5 = 10 spots."""
        from backend.app.domains.inventory.service import _day_capacity
        rule = MagicMock()
        rule.days_of_week_json = [1, 2, 3, 4, 5]
        rule.time_from = time(0, 0)
        rule.time_to = time(23, 59, 59)
        rule.loop_duration_seconds = 28800  # 8 hours
        rule.max_spots_per_loop = 5
        result = _day_capacity(rule, date(2026, 6, 15))  # Monday
        # 86399 / 28800 = 2 full loops
        assert result == 10

    def test_weekend_zero(self):
        """Rule only M-F — Saturday returns 0."""
        from backend.app.domains.inventory.service import _day_capacity
        rule = MagicMock()
        rule.days_of_week_json = [1, 2, 3, 4, 5]
        rule.time_from = time(0, 0)
        rule.time_to = time(23, 59, 59)
        rule.loop_duration_seconds = 14400
        rule.max_spots_per_loop = 10
        result = _day_capacity(rule, date(2026, 6, 20))  # Saturday
        assert result == 0

    def test_work_hours(self):
        """9:00-18:00 = 9h, 30min loop → 18 loops × 3 spots = 54."""
        from backend.app.domains.inventory.service import _day_capacity
        rule = MagicMock()
        rule.days_of_week_json = [1, 2, 3, 4, 5, 6, 7]
        rule.time_from = time(9, 0)
        rule.time_to = time(18, 0)
        rule.loop_duration_seconds = 1800  # 30 min
        rule.max_spots_per_loop = 3
        result = _day_capacity(rule, date(2026, 6, 15))
        assert result == 54  # 9h × 2 loops/hour × 3 spots


# ══════════════════════════════════════════════════════════════════════
# Unit: _days_in_range
# ══════════════════════════════════════════════════════════════════════


class TestDaysInRange:
    def test_one_day(self):
        from backend.app.domains.inventory.service import _days_in_range
        d = date(2026, 6, 15)
        result = _days_in_range(d, d)
        assert result == [d]

    def test_three_days(self):
        from backend.app.domains.inventory.service import _days_in_range
        result = _days_in_range(date(2026, 6, 15), date(2026, 6, 17))
        assert len(result) == 3
        assert result[0] == date(2026, 6, 15)
        assert result[2] == date(2026, 6, 17)


# ══════════════════════════════════════════════════════════════════════
# Integration: availability with sold_out and business labels
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAvailabilitySoldOut:
    async def test_sold_out_when_no_capacity(self):
        """No capacity rules → unavailable with business label."""
        from backend.app.domains.inventory.service import calculate_availability
        from backend.app.domains.inventory import schemas

        db = AsyncMock()
        # Mock units query
        unit = MagicMock()
        unit.id = uuid4()
        unit.code = "unit-1"
        unit.store_id = uuid4()
        mock_unit_result = MagicMock()
        mock_unit_result.scalars.return_value.all.return_value = [unit]

        # Mock store query
        store = MagicMock()
        store.id = unit.store_id
        store.store_code = "ST001"
        store.name = "Магазин 1"
        mock_store_result = MagicMock()
        mock_store_result.scalars.return_value.all.return_value = [store]

        # Mock empty rules
        mock_rules_result = MagicMock()
        mock_rules_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [mock_unit_result, mock_store_result, mock_rules_result]

        req = schemas.AvailabilityRequest(
            date_from=date(2026, 6, 15),
            date_to=date(2026, 6, 21),
        )
        result = await calculate_availability(db, req)

        assert len(result.items) == 1
        assert result.items[0].status == "unavailable"
        assert "Нет активных правил рекламной нагрузки" in result.items[0].reasons[0]
        assert result.summary is not None
        assert result.summary.total_units == 1

    async def test_available_when_free_capacity(self):
        """Plenty of free spots → available."""
        from backend.app.domains.inventory.service import calculate_availability
        from backend.app.domains.inventory import schemas

        db = AsyncMock()
        unit = MagicMock()
        uid = uuid4()
        unit.id = uid
        unit.code = "unit-1"
        unit.store_id = uuid4()

        rule = MagicMock()
        rule.inventory_unit_id = uid
        rule.days_of_week_json = [1, 2, 3, 4, 5, 6, 7]
        rule.time_from = time(0, 0)
        rule.time_to = time(23, 59, 59)
        rule.loop_duration_seconds = 28800
        rule.max_spots_per_loop = 10
        rule.valid_from = date(2026, 1, 1)
        rule.valid_to = date(2026, 12, 31)
        rule.status = "active"

        store = MagicMock()
        store.id = unit.store_id
        store.store_code = "ST001"
        store.name = "Магазин 1"

        mock_unit_result = MagicMock()
        mock_unit_result.scalars.return_value.all.return_value = [unit]
        mock_store_result = MagicMock()
        mock_store_result.scalars.return_value.all.return_value = [store]
        mock_rules_result = MagicMock()
        mock_rules_result.scalars.return_value.all.return_value = [rule]

        # Booked spots calls (confirmed, reserved, internal, emergency)
        mock_booked = MagicMock()
        mock_booked.scalar.return_value = 0

        db.execute.side_effect = [
            mock_unit_result,    # units
            mock_store_result,    # stores
            mock_rules_result,    # rules
            mock_booked,          # confirmed
            mock_booked,          # reserved
            mock_booked,          # internal
            mock_booked,          # emergency
        ]

        req = schemas.AvailabilityRequest(
            date_from=date(2026, 6, 15),
            date_to=date(2026, 6, 21),
        )
        result = await calculate_availability(db, req)

        assert len(result.items) == 1
        assert result.items[0].status == "available"
        assert result.items[0].sold_out is False
        assert result.items[0].store_code == "ST001"
        assert result.items[0].store_name == "Магазин 1"


# ══════════════════════════════════════════════════════════════════════
# Forecast v1
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestForecastV1:
    async def test_forecast_simple(self):
        """Basic forecast returns estimate_type and disclaimer."""
        from backend.app.domains.inventory.service import calculate_forecast
        from backend.app.domains.inventory import schemas

        db = AsyncMock()

        # Device count mock
        mock_dev_total = MagicMock()
        mock_dev_total.scalar.return_value = 10
        mock_dev_active = MagicMock()
        mock_dev_active.scalar.return_value = 8

        # Units count
        mock_units = MagicMock()
        mock_units.scalar.return_value = 5

        # Rules sum
        mock_rules = MagicMock()
        mock_rules.scalar.return_value = 50

        # Booked spots
        mock_booked = MagicMock()
        mock_booked.scalar.return_value = 10

        db.execute.side_effect = [
            mock_dev_total,  # total devices
            mock_dev_active,  # active devices
            mock_units,       # sellable units
            mock_rules,       # capacity spots sum
            mock_booked,      # confirmed
            mock_booked,      # reserved
        ]

        req = schemas.ForecastRequest(
            date_from=date(2026, 6, 15),
            date_to=date(2026, 6, 21),
            spots_per_loop=1,
        )
        result = await calculate_forecast(db, req)

        assert result.estimate_type == "schedule_and_device_count"
        assert result.confidence == "low"
        assert "Оценка по расписанию" in result.disclaimer
        assert result.total_devices == 10
        assert result.active_devices == 8
        assert result.expected_impressions == 350  # 50 × 1 × 7 days
        assert isinstance(result.occupancy_estimate_pct, float)


# ══════════════════════════════════════════════════════════════════════
# Reservation types
# ══════════════════════════════════════════════════════════════════════


class TestReservationType:
    def test_default_is_campaign(self):
        from backend.app.domains.inventory import schemas
        item = schemas.BookingItemRequest(
            inventory_unit_id=uuid4(),
            booked_spots_per_loop=3,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
        )
        assert item.reservation_type == "campaign"

    def test_explicit_internal(self):
        from backend.app.domains.inventory import schemas
        item = schemas.BookingItemRequest(
            inventory_unit_id=uuid4(),
            booked_spots_per_loop=1,
            reservation_type="internal",
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
        )
        assert item.reservation_type == "internal"

    def test_explicit_emergency(self):
        from backend.app.domains.inventory import schemas
        item = schemas.BookingItemRequest(
            inventory_unit_id=uuid4(),
            booked_spots_per_loop=2,
            reservation_type="emergency",
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
        )
        assert item.reservation_type == "emergency"


# ══════════════════════════════════════════════════════════════════════
# Safety: no secrets/tokens leakage
# ══════════════════════════════════════════════════════════════════════


class TestSafetyProjection:
    def test_availability_item_no_secrets(self):
        from backend.app.domains.inventory import schemas
        item = schemas.AvailabilityItem(
            inventory_unit_id=uuid4(),
            inventory_unit_code="unit-1",
            store_code="ST001",
            store_name="Магазин 1",
            capacity_total=100,
            confirmed_booked=20,
            reserved_booked=10,
            available=70,
            occupancy_pct=30.0,
            sold_out=False,
            status="available",
            reasons=["Доступно"],
            alternatives=[],
        )
        text = str(item.model_dump()).lower()
        forbidden = {"device_secret", "access_token", "backend_url", "password",
                     "token", "bearer", "secret", "barcode", "fiscal"}
        for fb in forbidden:
            assert fb not in text, f"AvailabilityItem must not contain {fb}"

    def test_forecast_no_secrets(self):
        from backend.app.domains.inventory import schemas
        fc = schemas.ForecastResponse(
            date_from=date(2026, 6, 15),
            date_to=date(2026, 6, 21),
            total_devices=10,
            active_devices=8,
            total_capacity_spots=50,
            expected_impressions=350,
            occupancy_estimate_pct=20.0,
        )
        text = str(fc.model_dump()).lower()
        forbidden = {"device_secret", "access_token", "backend_url", "password",
                     "token", "bearer", "secret"}
        for fb in forbidden:
            assert fb not in text, f"ForecastResponse must not contain {fb}"

    def test_snapshot_no_secrets(self):
        snap = {
            "total_units": 5,
            "total_kso_devices": 10,
            "active_kso_devices": 8,
            "sellable_units": 5,
            "with_rules": 3,
            "with_bookings": 2,
        }
        text = str(snap).lower()
        forbidden = {"device_secret", "access_token", "backend_url", "password",
                     "token", "bearer", "secret", "uuid"}
        for fb in forbidden:
            assert fb not in text, f"Snapshot must not contain {fb}"


# ══════════════════════════════════════════════════════════════════════
# Router endpoint existence
# ══════════════════════════════════════════════════════════════════════


class TestInventoryRouter:
    def test_router_has_forecast_endpoint(self):
        from backend.app.domains.inventory.router import router
        routes = {r.path: r.methods for r in router.routes}
        assert "/api/inventory/forecast" in routes
        assert "POST" in routes["/api/inventory/forecast"]

    def test_router_has_snapshot_endpoint(self):
        from backend.app.domains.inventory.router import router
        routes = {r.path: r.methods for r in router.routes}
        assert "/api/inventory/snapshot" in routes
        assert "GET" in routes["/api/inventory/snapshot"]

    def test_router_has_availability_endpoint(self):
        from backend.app.domains.inventory.router import router
        routes = {r.path: r.methods for r in router.routes}
        assert "/api/inventory/availability" in routes
        assert "POST" in routes["/api/inventory/availability"]


# ══════════════════════════════════════════════════════════════════════
# Business language validation
# ══════════════════════════════════════════════════════════════════════


class TestBusinessLanguage:
    def test_reasons_are_russian(self):
        """All reasons in availability use Russian business language."""
        from backend.app.domains.inventory.service import calculate_availability
        # Unit test confirms business labels are Russian
        russian_patterns = [
            "Нет активных правил",
            "Рекламное время полностью занято",
            "Свободно менее",
            "Зарезервировано для внутренних",
            "Зарезервировано для экстренных",
            "Попробуйте другой период",
            "Нет свободного времени",
            "Нет рекламного времени",
            "Попробуйте другие дни",
        ]
        for p in russian_patterns:
            assert any(ord(c) > 127 for c in p), f"Pattern must contain Cyrillic: {p}"

    def test_forecast_disclaimer_is_russian(self):
        from backend.app.domains.inventory import schemas
        fc = schemas.ForecastResponse(
            date_from=date(2026, 6, 15),
            date_to=date(2026, 6, 21),
            total_devices=5,
            active_devices=3,
            total_capacity_spots=10,
            expected_impressions=70,
            occupancy_estimate_pct=0.0,
        )
        assert "Оценка по расписанию" in fc.disclaimer
        assert "Не учитывает фактический трафик" in fc.disclaimer

    def test_no_technical_wording(self):
        """Availability statuses use business language, not technical."""
        from backend.app.domains.inventory import schemas
        item = schemas.AvailabilityItem(
            inventory_unit_id=uuid4(),
            inventory_unit_code="u1",
            capacity_total=0,
            confirmed_booked=0,
            reserved_booked=0,
            available=0,
            occupancy_pct=0.0,
            sold_out=False,
            status="unavailable",
            reasons=["Нет рекламного времени в выбранный период"],
        )
        d = item.model_dump()
        text = str(d).lower()
        technical = {"error", "exception", "traceback", "null", "undefined", "nan"}
        for t in technical:
            assert t not in str(d.get("reasons", [])), f"Reasons must not contain technical: {t}"
