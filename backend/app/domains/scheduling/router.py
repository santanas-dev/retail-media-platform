"""Scheduling Core: FastAPI router — 9 endpoints."""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity.models import User
from app.domains.scheduling import schemas, service

router = APIRouter(prefix="/api", tags=["scheduling"])


# ═══════════════════════════════════════════════════════════════════
#  Schedule Runs
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/schedule-runs",
    response_model=schemas.ScheduleRunResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_schedule_run(
    data: schemas.ScheduleRunCreate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("scheduling.manage")),
):
    return await service.create_schedule_run(db, data, current_user.id)


@router.get(
    "/schedule-runs",
    response_model=list[schemas.ScheduleRunResponse],
)
async def list_schedule_runs(
    booking_id: Optional[UUID] = Query(None),
    campaign_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    db=Depends(get_db),
    current_user: User = Depends(require_permission("scheduling.read")),
):
    return await service.list_schedule_runs(db, booking_id, campaign_id, status)


@router.get(
    "/schedule-runs/{run_id}",
    response_model=schemas.ScheduleRunResponse,
)
async def get_schedule_run(
    run_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("scheduling.read")),
):
    return await service.get_schedule_run(db, run_id)


@router.post(
    "/schedule-runs/{run_id}/generate",
    response_model=schemas.ScheduleRunResponse,
)
async def generate_schedule_run(
    run_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("scheduling.manage")),
):
    return await service.generate_schedule(db, run_id, current_user.id)


@router.post(
    "/schedule-runs/{run_id}/approve",
    response_model=schemas.ScheduleRunResponse,
)
async def approve_schedule_run(
    run_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("scheduling.approve")),
):
    return await service.approve_schedule_run(db, run_id, current_user.id)


@router.post(
    "/schedule-runs/{run_id}/cancel",
    response_model=schemas.ScheduleRunResponse,
)
async def cancel_schedule_run(
    run_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a schedule run. Approved runs require scheduling.approve."""
    user_perms = set(current_user.permissions)
    return await service.cancel_schedule_run(db, run_id, current_user.id, user_perms)


# ═══════════════════════════════════════════════════════════════════
#  Schedule Items
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/schedule-runs/{run_id}/items",
    response_model=list[schemas.ScheduleItemResponse],
)
async def list_schedule_run_items(
    run_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("scheduling.read")),
):
    return await service.list_schedule_items(db, run_id=run_id)


@router.get(
    "/schedule-items",
    response_model=list[schemas.ScheduleItemResponse],
)
async def list_schedule_items(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    inventory_unit_id: Optional[UUID] = Query(None),
    campaign_id: Optional[UUID] = Query(None),
    db=Depends(get_db),
    current_user: User = Depends(require_permission("scheduling.read")),
):
    return await service.list_schedule_items(
        db,
        date_from=date_from,
        date_to=date_to,
        inventory_unit_id=inventory_unit_id,
        campaign_id=campaign_id,
    )


# ═══════════════════════════════════════════════════════════════════
#  Schedule Conflicts
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/schedule-runs/{run_id}/conflicts",
    response_model=list[schemas.ScheduleConflictResponse],
)
async def list_schedule_conflicts(
    run_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("scheduling.read")),
):
    return await service.list_schedule_conflicts(db, run_id)
