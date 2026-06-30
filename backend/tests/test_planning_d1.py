"""
D.1 — Inventory/Planning Schema & Service Contracts: targeted tests.

Validates Pydantic schemas and service skeleton functions.
No DB writes. No Placement/Campaign/Publication changes.
"""

import pytest
from datetime import date
from uuid import uuid4

from app.domains.planning import schemas, service


# ═══════════════════════════════════════════════════════════════════════════
# 1. Schema validation: AvailabilityQuery
# ═══════════════════════════════════════════════════════════════════════════

class TestAvailabilityQuerySchema:
    """AvailabilityQuery Pydantic model."""

    def test_valid_minimal(self):
        q = schemas.AvailabilityQuery(date_from=date(2026, 7, 1), date_to=date(2026, 7, 7))
        assert q.date_from == date(2026, 7, 1)
        assert q.date_to == date(2026, 7, 7)
        assert q.requested_share_of_voice is None

    def test_valid_full(self):
        q = schemas.AvailabilityQuery(
            channel_id=uuid4(), store_id=uuid4(),
            display_surface_id=uuid4(), logical_carrier_id=uuid4(),
            inventory_unit_id=uuid4(),
            date_from=date(2026, 9, 1), date_to=date(2026, 10, 1),
            target_type="surface",
            requested_share_of_voice=25.5,
            requested_spots_per_loop=3,
            advertiser_id=uuid4(), campaign_id=uuid4(),
        )
        assert q.requested_share_of_voice == 25.5
        assert q.requested_spots_per_loop == 3

    def test_invalid_date_range_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.AvailabilityQuery(date_from=date(2026, 12, 31), date_to=date(2026, 1, 1))

    def test_equal_dates_accepted(self):
        q = schemas.AvailabilityQuery(date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
        assert q.date_from == q.date_to

    def test_share_of_voice_gt_100_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.AvailabilityQuery(
                date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
                requested_share_of_voice=150.0,
            )

    def test_share_of_voice_negative_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.AvailabilityQuery(
                date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
                requested_share_of_voice=-1.0,
            )

    def test_spots_per_loop_negative_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.AvailabilityQuery(
                date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
                requested_spots_per_loop=-1,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Schema validation: ConflictCheck
# ═══════════════════════════════════════════════════════════════════════════

class TestConflictCheckSchema:
    """ConflictCheck Pydantic model."""

    def test_valid(self):
        c = schemas.ConflictCheck(
            campaign_id=uuid4(), placement_id=uuid4(),
            inventory_unit_id=uuid4(), display_surface_id=uuid4(),
            date_from=date(2026, 7, 1), date_to=date(2026, 8, 1),
            requested_share_of_voice=50.0, requested_spots_per_loop=2,
        )
        assert c.requested_share_of_voice == 50.0

    def test_invalid_date_range_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.ConflictCheck(
                date_from=date(2026, 12, 31), date_to=date(2026, 1, 1),
            )

    def test_minimal_valid(self):
        c = schemas.ConflictCheck(
            date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
        )
        assert c.campaign_id is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. Schema validation: OccupancyQuery
# ═══════════════════════════════════════════════════════════════════════════

class TestOccupancyQuerySchema:
    """OccupancyQuery Pydantic model."""

    def test_valid(self):
        q = schemas.OccupancyQuery(
            inventory_unit_id=uuid4(), display_surface_id=uuid4(),
            channel_id=uuid4(), store_id=uuid4(),
            date_from=date(2026, 7, 1), date_to=date(2026, 7, 31),
            granularity="day",
        )
        assert q.granularity == "day"

    def test_invalid_granularity_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.OccupancyQuery(
                date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
                granularity="minute",
            )

    def test_invalid_date_range_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.OccupancyQuery(
                date_from=date(2026, 12, 31), date_to=date(2026, 1, 1),
            )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Schema validation: PlanningScenario
# ═══════════════════════════════════════════════════════════════════════════

class TestPlanningScenarioSchema:
    """PlanningScenario Pydantic model."""

    def test_dry_run_defaults_true(self):
        s = schemas.PlanningScenario(
            scenario_id="test-001",
            query=schemas.AvailabilityQuery(
                date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
            ),
        )
        assert s.dry_run is True

    def test_explicit_dry_run_false_allowed(self):
        s = schemas.PlanningScenario(
            query=schemas.AvailabilityQuery(
                date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
            ),
            dry_run=False,
        )
        assert s.dry_run is False

    def test_with_minimal_query(self):
        s = schemas.PlanningScenario(
            query=schemas.AvailabilityQuery(
                date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
            ),
        )
        assert s.availability_result is None
        assert s.conflict_result is None
        assert s.occupancy_result is None


# ═══════════════════════════════════════════════════════════════════════════
# 5. PlanningIssue
# ═══════════════════════════════════════════════════════════════════════════

class TestPlanningIssue:
    """PlanningIssue schema."""

    def test_structured_minimal(self):
        issue = schemas.PlanningIssue(
            code="TEST_CODE",
            severity="info",
            message="Test message",
        )
        assert issue.code == "TEST_CODE"
        assert issue.severity == "info"

    def test_with_field_and_details(self):
        issue = schemas.PlanningIssue(
            code="FIELD_ERR",
            severity="error",
            message="Invalid value",
            field="date_from",
            details={"actual": "2026-12-31", "expected": "<= date_to"},
        )
        assert issue.field == "date_from"
        assert issue.details is not None
        assert issue.details["actual"] == "2026-12-31"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Service contracts
# ═══════════════════════════════════════════════════════════════════════════

class TestServiceContracts:
    """Planning service skeleton functions."""

    @pytest.fixture
    def db(self):
        from unittest.mock import AsyncMock
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_check_availability_returns_result(self, db):
        q = schemas.AvailabilityQuery(
            channel_id=uuid4(),
            date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
        )
        result = await service.check_availability(db, q)
        assert isinstance(result, schemas.AvailabilityResult)
        assert result.ok is True
        assert result.available is False  # not computed yet

    @pytest.mark.asyncio
    async def test_check_availability_bad_dates(self, db):
        """Pydantic rejects date_from > date_to at schema level."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.AvailabilityQuery(
                date_from=date(2026, 12, 31), date_to=date(2026, 1, 1),
            )
    @pytest.mark.asyncio
    async def test_check_conflicts_returns_result(self, db):
        q = schemas.ConflictCheck(
            date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
        )
        result = await service.check_conflicts(db, q)
        assert isinstance(result, schemas.ConflictResult)
        assert result.has_conflict is False

    @pytest.mark.asyncio
    async def test_calculate_occupancy_returns_result(self, db):
        q = schemas.OccupancyQuery(
            channel_id=uuid4(),
            date_from=date(2026, 7, 1), date_to=date(2026, 7, 31),
        )
        result = await service.calculate_occupancy(db, q)
        assert isinstance(result, schemas.OccupancyResult)
        assert result.occupancy_percent == 0.0  # not computed yet

    @pytest.mark.asyncio
    async def test_simulate_planning_scenario(self, db):
        s = schemas.PlanningScenario(
            query=schemas.AvailabilityQuery(
                channel_id=uuid4(),
                date_from=date(2026, 7, 1), date_to=date(2026, 7, 7),
            ),
        )
        result = await service.simulate_planning_scenario(db, s)
        assert result.dry_run is True
        assert isinstance(result, schemas.PlanningScenario)

    @pytest.mark.asyncio
    async def test_map_placement_to_availability_query(self, db):
        result = await service.map_placement_to_availability_query(db, uuid4())
        assert isinstance(result, schemas.AvailabilityQuery)
        assert result.date_from <= result.date_to


# ═══════════════════════════════════════════════════════════════════════════
# 7. Validation helpers
# ═══════════════════════════════════════════════════════════════════════════

class TestValidationHelpers:
    """Validation helper functions."""

    def test_validate_date_range_valid(self):
        issues = service.validate_date_range(date(2026, 7, 1), date(2026, 7, 31))
        assert len(issues) == 0

    def test_validate_date_range_invalid(self):
        issues = service.validate_date_range(date(2026, 12, 31), date(2026, 1, 1))
        assert len(issues) == 1
        assert issues[0].code == "DATE_RANGE_INVALID"

    def test_validate_requested_capacity_valid(self):
        issues = service.validate_requested_capacity(50.0, 3)
        assert len(issues) == 0

    def test_validate_requested_capacity_share_too_high(self):
        issues = service.validate_requested_capacity(150.0, None)
        assert len(issues) == 1
        assert issues[0].code == "INVALID_SHARE_OF_VOICE"

    def test_validate_requested_capacity_spots_negative(self):
        issues = service.validate_requested_capacity(None, -5)
        assert len(issues) == 1
        assert issues[0].code == "INVALID_SPOTS_PER_LOOP"

    def test_build_planning_issue_minimal(self):
        issue = service.build_planning_issue("E001", "error", "Something broken")
        assert issue.code == "E001"
        assert issue.severity == "error"
        assert issue.message == "Something broken"
        assert issue.field is None

    def test_build_planning_issue_with_field(self):
        issue = service.build_planning_issue(
            "E002", "warning", "Check value",
            field="date_from", details={"example": 1},
        )
        assert issue.field == "date_from"
        assert issue.details == {"example": 1}


# ═══════════════════════════════════════════════════════════════════════════
# 8. Boundary: no CampaignBooking/BookingItem/Placement changes
# ═══════════════════════════════════════════════════════════════════════════

class TestD1Boundary:
    """D.1 does NOT create/change CampaignBooking, BookingItem, Placement."""

    def test_no_campaign_booking_in_service(self):
        src = _code_lines(service.check_availability)
        # BookingItem/CampaignBooking may appear in comments describing future work
        # The critical check: no ORM import or DB write
        assert "db.add" not in src  # no writes
        assert "CampaignBooking" not in src  # no ORM model usage
        assert "db.add" not in src

    def test_no_placement_change_in_service(self):
        src = _code_lines(service.check_availability)
        assert "Placement" not in src
        assert "placement" not in src.lower()

    def test_no_generated_manifest_in_service(self):
        src = _code_lines(service.check_availability)
        assert "generated_manifest" not in src.lower()

    def test_no_device_gateway_import(self):
        import inspect
        src = inspect.getsource(service)
        assert "device_gateway" not in src

    def test_no_publication_flow_import(self):
        import inspect
        src = inspect.getsource(service)
        assert "publications" not in src.lower()
        assert "generate_manifest" not in src.lower()
        assert "publish_batch" not in src.lower()

    def test_no_orchestrator_delivery_import(self):
        src = _code_lines(service.check_availability)
        assert "Orchestrator" not in src
        assert "orchestrator" not in src

    def test_no_portal_import(self):
        import inspect
        src = inspect.getsource(service)
        assert "portal" not in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 9. Compatibility: inventory models still accessible
# ═══════════════════════════════════════════════════════════════════════════

class TestInventoryCompatibility:
    """Existing inventory models still importable."""

    def test_inventory_models_import(self):
        from app.domains.inventory.models import (
            InventoryUnit, CapacityRule, CampaignBooking, BookingItem,
        )
        assert InventoryUnit is not None
        assert CapacityRule is not None
        assert CampaignBooking is not None
        assert BookingItem is not None

    def test_inventory_schemas_import(self):
        from app.domains.inventory.schemas import (
            InventoryUnitCreate, InventoryUnitUpdate, InventoryUnitResponse,
        )
        assert InventoryUnitCreate is not None
        assert InventoryUnitUpdate is not None
        assert InventoryUnitResponse is not None


# ═══════════════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════════════

def _code_lines(fn):
    """Get source lines of a function, excluding docstrings (handles single-line and multi-line)."""
    import inspect, re
    src = inspect.getsource(fn)
    # Remove function docstring via regex: triple-quoted string after colon+newline
    # Matches both single-line and multi-line docstrings
    result = re.sub(r'(:\s*\n)\s*("""|\'\'\').*?\2', r'\1', src, flags=re.DOTALL, count=1)
    return result
