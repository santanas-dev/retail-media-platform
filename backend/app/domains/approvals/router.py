"""Approvals domain: FastAPI router (Step 37.6).

Test KSO vertical slice — minimal approval gate.
Safe projection: NO raw UUIDs, backend_url, tokens.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.approvals import schemas, service

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get(
    "/test-kso",
    response_model=list[schemas.ApprovalResponse],
)
async def list_approvals(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.read")),
):
    """List approval requests (safe projection)."""
    return await service.list_approvals(db, skip, limit)


@router.post(
    "/test-kso/request",
    response_model=schemas.ApprovalResponse,
    status_code=201,
)
async def request_approval(
    data: schemas.ApprovalRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("campaigns.manage")
    ),
):
    """Request approval for a campaign or placement.

    Transitions object status to 'pending_approval'.
    """
    return await service.request_approval(db, data, current_user.id)


@router.post(
    "/test-kso/{approval_code}/decide",
    response_model=schemas.ApprovalResponse,
)
async def decide_approval(
    approval_code: str,
    data: schemas.ApprovalDecide,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("campaigns.approve")
    ),
):
    """Decide on an approval request (approve/reject).

    Maker-checker: cannot decide own request.
    Transitions object status to 'approved' or 'rejected'.
    """
    return await service.decide_approval(db, approval_code, data, current_user.id)
