"""
B.3.2 — Placement API router.

Standalone placement endpoints:
  GET    /api/placements/{id}
  PUT    /api/placements/{id}
  DELETE /api/placements/{id}
  GET    /api/placements/{id}/targets
  PUT    /api/placements/{id}/targets

Campaign-scoped endpoints (in campaigns/router.py):
  GET    /api/campaigns/{id}/placements
  POST   /api/campaigns/{id}/placements
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.channels import schemas, service
from app.domains.audit.service import audit_business_action

router = APIRouter(prefix="/api", tags=["placements"])


# ── Placement CRUD ──────────────────────────────────────────────────────────


@router.get("/placements/{placement_id}", response_model=schemas.PlacementResponse)
async def get_placement(
    placement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.read")),
):
    return await service.get_placement(db, placement_id, current_user)


@router.put("/placements/{placement_id}", response_model=schemas.PlacementResponse)
async def update_placement(
    placement_id: UUID,
    data: schemas.PlacementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    result = await service.update_placement(db, placement_id, data, current_user)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="placement.update", target_type="placement",
        target_ref=result.placement_code,
        details={"changed_fields": list(data.model_dump(exclude_unset=True).keys())},
    )
    return result


@router.delete("/placements/{placement_id}", response_model=schemas.PlacementResponse)
async def cancel_placement(
    placement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    result = await service.cancel_placement(db, placement_id, current_user)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="placement.cancel", target_type="placement",
        target_ref=result.placement_code,
    )
    return result


# ── Placement Targets ───────────────────────────────────────────────────────


@router.get(
    "/placements/{placement_id}/targets",
    response_model=list[schemas.PlacementTargetResponse],
)
async def get_placement_targets(
    placement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.read")),
):
    return await service.get_placement_targets(db, placement_id, current_user)


@router.put(
    "/placements/{placement_id}/targets",
    response_model=list[schemas.PlacementTargetResponse],
)
async def set_placement_targets(
    placement_id: UUID,
    data: schemas.PlacementTargetsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    result = await service.set_placement_targets(db, placement_id, data, current_user)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="placement.targets.update", target_type="placement",
        target_ref=str(placement_id),
        details={"target_count": len(result)},
    )
    return result
