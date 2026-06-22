"""Scheduling domain: FastAPI router (Step 37.5).

Test KSO vertical slice — minimal placement/schedule endpoints.
Safe projection: NO raw UUIDs, commercial fields, or secrets.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.scheduling import schemas, service

router = APIRouter(prefix="/api/schedule", tags=["scheduling"])


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
    """List placements for test KSO vertical slice (safe projection).

    Response: placement_code, campaign_code, creative_code, device_code,
    status, starts_at, ends_at, slot_order, created_at, updated_at.
    NO raw UUIDs, file_path, sha256, storage_ref, minio, backend_url, tokens.
    """
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
    """Create a placement for test KSO technical validation.

    Links campaign_code → creative_code → device_code in a time window.
    Validates: campaign exists, creative linked to campaign, device exists,
    no overlapping placements on same device.  Returns safe fields only.
    """
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
