"""Approvals domain: FastAPI router (Step 37.6 + 39.3.1 production).

Test KSO vertical slice — minimal approval gate with maker-checker.
Safe projection: NO raw UUIDs, backend_url, tokens.
Production endpoints added in 39.3.1 — test-kso retained as legacy.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.approvals import schemas, service

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# ══════════════════════════════════════════════════════════════════════
# Production endpoints (39.3.1)
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "",
    response_model=list[schemas.ApprovalResponse],
)
async def list_approvals_prod(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("approvals.read")),
):
    """List approval requests (production, safe projection)."""
    return await service.list_approvals(db, skip, limit)


@router.get(
    "/{approval_code}",
    response_model=schemas.ApprovalResponse,
)
async def get_approval_prod(
    approval_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("approvals.read")),
):
    """Get a single approval request by code (production, safe projection)."""
    return await service.get_approval(db, approval_code)


@router.post(
    "",
    response_model=schemas.ApprovalResponse,
    status_code=201,
)
async def request_approval_prod(
    data: schemas.ApprovalRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("approvals.manage")
    ),
):
    """Request approval for an object (production).

    Supported object_types: campaign, placement, publication_batch.
    Transitions object status to 'pending_approval'.
    """
    return await service.request_approval(db, data, current_user.id)


@router.post(
    "/{approval_code}/approve",
    response_model=schemas.ApprovalResponse,
)
async def approve_approval_prod(
    approval_code: str,
    data: schemas.ApprovalDecide,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("approvals.approve")
    ),
):
    """Approve an approval request (production).

    Maker-checker: cannot approve own request.
    Transitions object status to 'approved'.
    """
    if data.decision != "approve":
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Use /reject endpoint to reject")
    return await service.decide_approval(db, approval_code, data, current_user.id)


@router.post(
    "/{approval_code}/reject",
    response_model=schemas.ApprovalResponse,
)
async def reject_approval_prod(
    approval_code: str,
    data: schemas.ApprovalDecide,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("approvals.approve")
    ),
):
    """Reject an approval request (production).

    Maker-checker: cannot reject own request.
    Transitions object status to 'rejected'.
    """
    if data.decision != "reject":
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Use /approve endpoint to approve")
    return await service.decide_approval(db, approval_code, data, current_user.id)


# ══════════════════════════════════════════════════════════════════════
# Legacy test-kso endpoints (retained as dev helper)
# ══════════════════════════════════════════════════════════════════════

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
    """[LEGACY] List approval requests (safe projection)."""
    return await service.list_approvals(db, skip, limit)


@router.post(
    "/test-kso/request",
    response_model=schemas.ApprovalResponse,
    status_code=201,
)
async def request_approval_legacy(
    data: schemas.ApprovalRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("campaigns.manage")
    ),
):
    """[LEGACY] Request approval for a campaign or placement."""
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
    """[LEGACY] Decide on an approval request (approve/reject)."""
    return await service.decide_approval(db, approval_code, data, current_user.id)
