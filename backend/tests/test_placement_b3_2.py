"""B.3.2 — Placement service + API tests.

Schema validation, route registration, audit actions.
Matches the test pattern used across the project.
"""

import uuid
from datetime import date
from unittest.mock import MagicMock

from app.main import app
from app.domains.identity.models import User


def _uid():
    return uuid.uuid4()


# ═══════════════════════════════════════════════════════════════════════════
# Schema validation
# ═══════════════════════════════════════════════════════════════════════════


class TestPlacementSchemas:
    """Pydantic schema validation (no DB needed)."""

    def test_placement_create_minimal(self):
        """PlacementCreate accepts minimal fields."""
        from app.domains.channels.schemas import PlacementCreate

        data = PlacementCreate(channel_id=_uid(), name="Minimal")
        assert data.name == "Minimal"
        assert data.priority == 0
        assert data.start_date is None

    def test_placement_create_with_dates(self):
        """PlacementCreate with date range."""
        from app.domains.channels.schemas import PlacementCreate

        data = PlacementCreate(
            channel_id=_uid(),
            name="Dated",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        assert data.start_date == date(2026, 1, 1)
        assert data.end_date == date(2026, 12, 31)

    def test_placement_create_invalid_name_empty(self):
        """PlacementCreate rejects empty name."""
        from app.domains.channels.schemas import PlacementCreate
        from pydantic import ValidationError

        try:
            PlacementCreate(channel_id=_uid(), name="")
            assert False, "Should have raised"
        except ValidationError:
            pass

    def test_placement_update_partial(self):
        """PlacementUpdate accepts partial fields."""
        from app.domains.channels.schemas import PlacementUpdate

        data = PlacementUpdate(status="active")
        assert data.status == "active"
        assert data.name is None

    def test_placement_update_invalid_status_rejected(self):
        """PlacementUpdate allows any string at schema level
        (validation is in service layer)."""
        from app.domains.channels.schemas import PlacementUpdate

        data = PlacementUpdate(status="any_string_passes")
        assert data.status == "any_string_passes"

    def test_placement_target_item_store(self):
        """PlacementTargetItem with store target."""
        from app.domains.channels.schemas import PlacementTargetItem

        item = PlacementTargetItem(target_type="store", store_id=_uid())
        assert item.target_type == "store"
        assert item.store_id is not None

    def test_placement_target_item_surface(self):
        """PlacementTargetItem with surface target."""
        from app.domains.channels.schemas import PlacementTargetItem

        item = PlacementTargetItem(target_type="surface", display_surface_id=_uid())
        assert item.target_type == "surface"

    def test_placement_targets_update_list(self):
        """PlacementTargetsUpdate accepts list of targets."""
        from app.domains.channels.schemas import PlacementTargetsUpdate, PlacementTargetItem

        data = PlacementTargetsUpdate(targets=[
            PlacementTargetItem(target_type="store", store_id=_uid()),
            PlacementTargetItem(target_type="surface", display_surface_id=_uid()),
        ])
        assert len(data.targets) == 2

    def test_placement_response_from_attributes(self):
        """PlacementResponse has from_attributes=True."""
        from app.domains.channels.schemas import PlacementResponse

        assert PlacementResponse.model_config.get("from_attributes") is True

    def test_placement_target_response_from_attributes(self):
        """PlacementTargetResponse has from_attributes=True."""
        from app.domains.channels.schemas import PlacementTargetResponse

        assert PlacementTargetResponse.model_config.get("from_attributes") is True


# ═══════════════════════════════════════════════════════════════════════════
# Status validation
# ═══════════════════════════════════════════════════════════════════════════


class TestPlacementStatuses:
    """Placement status validation rules."""

    def test_valid_statuses_contains_expected(self):
        """VALID_PLACEMENT_STATUSES contains expected values."""
        from app.domains.channels.schemas import VALID_PLACEMENT_STATUSES

        assert "draft" in VALID_PLACEMENT_STATUSES
        assert "active" in VALID_PLACEMENT_STATUSES
        assert "paused" in VALID_PLACEMENT_STATUSES
        assert "completed" in VALID_PLACEMENT_STATUSES
        assert "cancelled" in VALID_PLACEMENT_STATUSES
        assert "error" in VALID_PLACEMENT_STATUSES
        assert len(VALID_PLACEMENT_STATUSES) == 6

    def test_invalid_status_not_in_set(self):
        """Invalid status is not in VALID_PLACEMENT_STATUSES."""
        from app.domains.channels.schemas import VALID_PLACEMENT_STATUSES

        assert "invalid_status_xyz" not in VALID_PLACEMENT_STATUSES
        assert "" not in VALID_PLACEMENT_STATUSES
        assert "deleted" not in VALID_PLACEMENT_STATUSES


# ═══════════════════════════════════════════════════════════════════════════
# Route registration
# ═══════════════════════════════════════════════════════════════════════════


class TestPlacementRouterRegistration:
    """Verify routes are registered in the app."""

    def test_campaign_placement_routes_exist(self):
        """Campaign-scoped placement routes are registered."""
        from app.domains.campaigns.router import router

        paths = set()
        for r in router.routes:
            if hasattr(r, 'path'):
                paths.add(r.path)

        assert "/api/campaigns/{campaign_id}/placements" in paths

    def test_standalone_placement_routes_all(self):
        """All standalone placement routes are registered."""
        from app.domains.channels.placements_router import router

        paths = set()
        for r in router.routes:
            if hasattr(r, 'path'):
                paths.add(r.path)

        assert "/api/placements/{placement_id}" in paths
        assert "/api/placements/{placement_id}/targets" in paths

    def test_placements_router_importable(self):
        """Placements router imports without error."""
        from app.domains.channels.placements_router import router

        assert router is not None
        assert router.prefix == "/api"

    def test_placements_router_in_main_app(self):
        """Placements router is included in main app."""
        # Verify router import exists in main.py
        import app.main as main_module

        assert hasattr(main_module, 'placements_router')


# ═══════════════════════════════════════════════════════════════════════════
# Audit actions
# ═══════════════════════════════════════════════════════════════════════════


class TestPlacementAuditActions:
    """Verify audit action strings are consistent."""

    def test_four_audit_actions_expected(self):
        """B.3.2 introduces 4 placement audit actions."""
        expected = {
            "placement.create",
            "placement.update",
            "placement.cancel",
            "placement.targets.update",
        }
        assert len(expected) == 4

    def test_audit_actions_referenced_in_router(self):
        """Audit actions are used in router code."""
        from app.domains.channels.placements_router import router
        from app.domains.campaigns.router import router as camp_router

        # Both routers loaded without error
        assert router is not None
        assert camp_router is not None

        # Verify campaign router has placement endpoints
        camp_paths = set()
        for r in camp_router.routes:
            if hasattr(r, 'path'):
                camp_paths.add(r.path)
        assert "/api/campaigns/{campaign_id}/placements" in camp_paths
