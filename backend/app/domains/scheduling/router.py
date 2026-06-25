"""Scheduling domain: FastAPI router (Step 37.5).

Test KSO vertical slice — minimal placement/schedule endpoints.
Safe projection: NO raw UUIDs, commercial fields, or secrets.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.scheduling import schemas, service

router = APIRouter(prefix="/api", tags=["scheduling"])

# ── Production Placement API ───────────────────────────────────────────────


@router.get(
    "/placements",
    response_model=list[schemas.KsoPlacementResponse],
)
async def list_placements_prod(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """List all placements with safe projection (production API)."""
    return await service.list_placements(db, skip, limit)


@router.post(
    "/placements",
    response_model=schemas.KsoPlacementResponse,
    status_code=201,
)
async def create_placement_prod(
    data: schemas.KsoPlacementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("scheduling.manage")
    ),
):
    """Create a placement linking campaign→creative→device (production API)."""
    return await service.create_placement(db, data, current_user.id)


@router.get(
    "/placements/{placement_code}",
    response_model=schemas.KsoPlacementResponse,
)
async def get_placement_prod(
    placement_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """Get a single placement by code (safe projection)."""
    return await service.get_placement(db, placement_code)


@router.patch(
    "/placements/{placement_code}",
    response_model=schemas.KsoPlacementResponse,
)
async def patch_placement_prod(
    placement_code: str,
    data: schemas.KsoPlacementUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Update placement fields (production API)."""
    return await service.update_placement(db, placement_code, data)


@router.post(
    "/placements/{placement_code}/archive",
    response_model=schemas.KsoPlacementResponse,
)
async def archive_placement_prod(
    placement_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Archive a placement (status → archived)."""
    return await service.archive_placement(db, placement_code)


# ── Test KSO Vertical Slice (legacy, will be retired) ──────────────────────
# These endpoints are retained for test KSO backward compatibility.
# New code should use /api/placements above.


@router.get(
    "/test-kso",
    response_model=list[schemas.KsoPlacementResponse],
)
async def list_placements(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """List placements for test KSO vertical slice (safe projection)."""
    return await service.list_placements(db, skip, limit)


@router.post(
    "/test-kso",
    response_model=schemas.KsoPlacementResponse,
    status_code=201,
)
async def create_placement(
    data: schemas.KsoPlacementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("scheduling.manage")
    ),
):
    """Create a placement for test KSO technical validation."""
    return await service.create_placement(db, data, current_user.id)


@router.get(
    "/test-kso/{placement_code}",
    response_model=schemas.KsoPlacementResponse,
)
async def get_placement(
    placement_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """Get a single placement by code (safe projection)."""
    return await service.get_placement(db, placement_code)


# ═══════════════════════════════════════════════════════════════════════════
# Schedule + ScheduleSlot production endpoints (39.1.3)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/schedules",
    response_model=list[schemas.ScheduleResponse],
)
async def list_schedules_prod(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    return await service.list_schedules(db, skip, limit)


@router.post(
    "/schedules",
    response_model=schemas.ScheduleResponse,
    status_code=201,
)
async def create_schedule_prod(
    data: schemas.ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    return await service.create_schedule(db, data, current_user.id)


@router.get(
    "/schedules/{schedule_code}",
    response_model=schemas.ScheduleResponse,
)
async def get_schedule_prod(
    schedule_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    return await service.get_schedule(db, schedule_code)


@router.patch(
    "/schedules/{schedule_code}",
    response_model=schemas.ScheduleResponse,
)
async def patch_schedule_prod(
    schedule_code: str,
    data: schemas.ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    return await service.update_schedule(db, schedule_code, data)


@router.post(
    "/schedules/{schedule_code}/archive",
    response_model=schemas.ScheduleResponse,
)
async def archive_schedule_prod(
    schedule_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    return await service.archive_schedule(db, schedule_code)


# ── Schedule Slots ────────────────────────────────────────────────────────

@router.get(
    "/schedules/{schedule_code}/items",
    response_model=list[schemas.ScheduleSlotResponse],
)
async def list_slots_prod(
    schedule_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    return await service.list_schedule_slots(db, schedule_code)


@router.post(
    "/schedules/{schedule_code}/items",
    response_model=schemas.ScheduleSlotResponse,
    status_code=201,
)
async def create_slot_prod(
    schedule_code: str,
    data: schemas.ScheduleSlotCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    return await service.create_schedule_slot(db, schedule_code, data)


@router.patch(
    "/schedules/{schedule_code}/items/{slot_code}",
    response_model=schemas.ScheduleSlotResponse,
)
async def patch_slot_prod(
    schedule_code: str,
    slot_code: str,
    data: schemas.ScheduleSlotUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    return await service.update_schedule_slot(db, schedule_code, slot_code, data)


@router.delete(
    "/schedules/{schedule_code}/items/{slot_code}",
    response_model=schemas.ScheduleSlotResponse,
)
async def disable_slot_prod(
    schedule_code: str,
    slot_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    return await service.disable_schedule_slot(db, schedule_code, slot_code)
