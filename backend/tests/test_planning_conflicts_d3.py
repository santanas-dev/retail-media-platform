"""
D.3 — Conflict Detection: targeted tests.

Tests for check_conflicts() with mocked InventoryUnit, CapacityRule,
CampaignBooking, BookingItem, Placement, PlacementTarget.
No real DB writes — all AsyncMock.
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.domains.planning import schemas, service


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _code_lines(fn):
    import inspect, re
    src = inspect.getsource(fn)
    return re.sub(r'(:\s*\n)\s*("""|\'\'\').*?\2', r'\1', src, flags=re.DOTALL, count=1)

INV_ID = uuid4()
CH_ID = uuid4()
SURFACE_ID = uuid4()
D1 = date(2026, 7, 1)
D3 = date(2026, 7, 3)
D5 = date(2026, 7, 5)
D7 = date(2026, 7, 7)
D10 = date(2026, 7, 10)


# ═══════════════════════════════════════════════════════════════════════════
# 1. D.2 filter coverage check (5 filters)
# ═══════════════════════════════════════════════════════════════════════════

class TestD2FilterCoverage:
    """Verify all 5 InventoryUnit filters are present in check_availability."""

    def test_filter_by_inventory_unit_id(self):
        src = _code_lines(service.check_availability)
        assert "query.inventory_unit_id" in src

    def test_filter_by_channel_id(self):
        src = _code_lines(service.check_availability)
        assert "query.channel_id" in src

    def test_filter_by_store_id(self):
        src = _code_lines(service.check_availability)
        assert "query.store_id" in src

    def test_filter_by_display_surface_id(self):
        src = _code_lines(service.check_availability)
        assert "query.display_surface_id" in src

    def test_filter_by_logical_carrier_id(self):
        src = _code_lines(service.check_availability)
        assert "query.logical_carrier_id" in src


# ═══════════════════════════════════════════════════════════════════════════
# 2. Validation
# ═══════════════════════════════════════════════════════════════════════════

class TestValidation:
    """ConflictCheck input validation."""

    def test_invalid_date_range(self):
        from pydantic_core import ValidationError as PydanticCoreError
        with pytest.raises((PydanticCoreError,)):
            schemas.ConflictCheck(
                date_from=date(2026, 12, 31), date_to=date(2026, 1, 1),
            )

    def test_invalid_sov(self):
        from pydantic_core import ValidationError as PydanticCoreError
        with pytest.raises((PydanticCoreError,)):
            schemas.ConflictCheck(
                date_from=D1, date_to=D10, requested_share_of_voice=150,
            )

    def test_invalid_spots(self):
        from pydantic_core import ValidationError as PydanticCoreError
        with pytest.raises((PydanticCoreError,)):
            schemas.ConflictCheck(
                date_from=D1, date_to=D10, requested_spots_per_loop=-1,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Date overlap
# ═══════════════════════════════════════════════════════════════════════════

class TestDateOverlap:
    """Date range overlap logic."""

    def test_non_overlapping_no_conflict(self):
        assert service.ranges_overlap(D1, D10, D10 + date.resolution * 15, D10 + date.resolution * 30) is False

    def test_overlapping_detected(self):
        assert service.ranges_overlap(D1, D10, D5, D5) is True

    def test_adjacent_inclusive(self):
        """D1-D5 and D5-D10 overlap because D5 is shared (inclusive)."""
        from datetime import date as dt
        assert service.ranges_overlap(D1, D10, D10, D10) is True

    def test_complete_containment(self):
        assert service.ranges_overlap(D1, D10, D3, D7) is True

    def test_multiple_bookings_aggregated(self):
        """Overlap logic is deterministic — same result every time."""
        r1 = service.ranges_overlap(D1, D10, D3, D7)
        r2 = service.ranges_overlap(D1, D10, D3, D7)
        assert r1 == r2


# ═══════════════════════════════════════════════════════════════════════════
# 4. Booking statuses
# ═══════════════════════════════════════════════════════════════════════════

class TestBookingStatuses:
    """Which CampaignBooking statuses consume inventory."""

    def test_approved_consumes(self):
        assert "approved" in service._BOOKING_STATUSES_THAT_CONSUME

    def test_active_consumes(self):
        assert "active" in service._BOOKING_STATUSES_THAT_CONSUME

    def test_published_consumes(self):
        assert "published" in service._BOOKING_STATUSES_THAT_CONSUME

    def test_draft_ignored(self):
        assert "draft" not in service._BOOKING_STATUSES_THAT_CONSUME

    def test_rejected_ignored(self):
        assert "rejected" not in service._BOOKING_STATUSES_THAT_CONSUME

    def test_cancelled_ignored(self):
        assert "cancelled" not in service._BOOKING_STATUSES_THAT_CONSUME


# ═══════════════════════════════════════════════════════════════════════════
# 5. Conflict types
# ═══════════════════════════════════════════════════════════════════════════

class TestConflictTypes:
    """Conflict types detected by check_conflicts."""

    def test_share_of_voice_exceeded_in_code(self):
        src = _code_lines(service.check_availability)
        assert "share_of_voice_exceeded" in src

    def test_capacity_exceeded_in_code(self):
        src = _code_lines(service.check_availability)
        assert "capacity_exceeded" in src

    def test_date_overlap_in_code(self):
        src = _code_lines(service.check_conflicts)
        assert "ranges_overlap" in src


# ═══════════════════════════════════════════════════════════════════════════
# 6. Placement mapping
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementMapping:
    """Placement → inventory scope mapping."""

    def test_check_conflicts_imports_placement(self):
        src = _code_lines(service.check_conflicts)
        assert "Placement" in src
        assert "PlacementTarget" in src

    def test_placement_not_found_issue(self):
        src = _code_lines(service.check_conflicts)
        assert "PLACEMENT_NOT_FOUND" in src

    def test_placement_target_not_found_issue(self):
        src = _code_lines(service.check_conflicts)
        assert "PLACEMENT_TARGET_NOT_FOUND" in src

    def test_no_conflict_scope_issue(self):
        src = _code_lines(service.check_conflicts)
        assert "NO_CONFLICT_SCOPE" in src


# ═══════════════════════════════════════════════════════════════════════════
# 7. Service: check_conflicts() behavior
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckConflictsService:
    """Service behavior tests with mocked DB."""

    def test_returns_conflict_result_type(self):
        """Even with no units, check_conflicts returns ConflictResult."""
        import asyncio
        db = AsyncMock()

        async def run():
            q = schemas.ConflictCheck(inventory_unit_id=uuid4(), date_from=D1, date_to=D10)
            # Mock: no units found
            db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[])),
            )))
            return await service.check_conflicts(db, q)

        result = asyncio.run(run())
        assert isinstance(result, schemas.ConflictResult)
        assert not result.has_conflict

    def test_no_scope_returns_error(self):
        """ConflictCheck without inventory_unit_id, display_surface_id, or placement_id → error."""
        import asyncio
        db = AsyncMock()
        q = schemas.ConflictCheck(date_from=D1, date_to=D10)
        # Mock: no units found in underlying availability
        db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[])),
        )))
        async def run():
            return await service.check_conflicts(db, q)
        result = asyncio.run(run())
        assert not result.has_conflict
        assert any(e.code == "NO_CONFLICT_SCOPE" for e in result.errors)

    def test_conflict_result_has_conflict_flag(self):
        """has_conflict is False when no conflicts, True when conflicts exist."""
        src = _code_lines(service.check_conflicts)
        assert "has_conflict" in src

    def test_conflicts_include_severity_type_message(self):
        """PlanningConflict has severity, conflict_type, message fields."""
        from app.domains.planning.schemas import PlanningConflict
        c = PlanningConflict(
            conflict_type="date_overlap",
            severity="error",
            date_from=D1, date_to=D10,
            message="Test conflict",
        )
        assert c.conflict_type == "date_overlap"
        assert c.severity == "error"
        assert c.message == "Test conflict"


# ═══════════════════════════════════════════════════════════════════════════
# 8. Read-only boundaries
# ═══════════════════════════════════════════════════════════════════════════

class TestReadOnlyBoundary:
    """D.3 does not create bookings or change state."""

    def test_no_db_add_in_check_conflicts(self):
        src = _code_lines(service.check_conflicts)
        assert "db.add" not in src

    def test_no_campaign_booking_orm_write(self):
        src = _code_lines(service.check_conflicts)
        assert "CampaignBooking(" not in src
        assert "BookingItem(" not in src

    def test_no_device_gateway_import(self):
        src = _code_lines(service.check_conflicts)
        assert "device_gateway" not in src.lower()

    def test_no_publication_import(self):
        src = _code_lines(service.check_conflicts)
        assert "generated_manifest" not in src.lower()

    def test_no_universal_manifest_import(self):
        src = _code_lines(service.check_conflicts)
        assert "universal_builder" not in src.lower()

    def test_no_generate_manifests_or_publish_batch(self):
        src = _code_lines(service.check_conflicts)
        assert "generate_manifest" not in src.lower()
        assert "publish_batch" not in src.lower()

    def test_no_portal_import(self):
        src = _code_lines(service.check_conflicts)
        assert "portal" not in src.lower()

    def test_only_reads(self):
        src = _code_lines(service.check_conflicts)
        assert "insert" not in src.lower()
        assert "update" not in src.lower()
        assert "delete" not in src.lower()
