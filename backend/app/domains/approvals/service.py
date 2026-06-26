"""Approvals domain: business logic (Step 37.6).

Test KSO vertical slice — minimal approval gate with maker-checker.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.approvals import models, schemas
from app.domains.campaigns.models import Campaign
from app.domains.scheduling.models import KsoPlacement

# Status transition mapping: decision → new object status
_DECISION_STATUS_MAP = {
    "approve": "approved",
    "reject": "rejected",
}

# Decision → approval record status
_DECISION_TO_APPROVAL_STATUS = {
    "approve": "approved",
    "reject": "rejected",
}


async def _get_object_or_404(
    db: AsyncSession, object_type: str, object_code: str,
):
    """Look up the target object by type and code. Returns the ORM instance."""
    if object_type == "campaign":
        result = await db.execute(
            select(Campaign).where(Campaign.campaign_code == object_code)
        )
        obj = result.scalar_one_or_none()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign '{object_code}' not found",
            )
        return obj

    elif object_type == "placement":
        result = await db.execute(
            select(KsoPlacement).where(
                KsoPlacement.placement_code == object_code,
            )
        )
        obj = result.scalar_one_or_none()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Placement '{object_code}' not found",
            )
        return obj

    elif object_type == "publication_batch":
        from app.domains.publications.models import PublicationBatch
        from uuid import UUID
        try:
            batch_id = UUID(object_code)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid publication_batch id '{object_code}'",
            )
        result = await db.execute(
            select(PublicationBatch).where(PublicationBatch.id == batch_id)
        )
        obj = result.scalar_one_or_none()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Publication batch '{object_code}' not found",
            )
        return obj

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown object_type '{object_type}'",
    )


async def _check_no_active_pending(
    db: AsyncSession, object_type: str, object_code: str,
) -> None:
    """Ensure no other pending approval exists for this object."""
    result = await db.execute(
        select(models.ApprovalRequest.id).where(
            models.ApprovalRequest.object_type == object_type,
            models.ApprovalRequest.object_code == object_code,
            models.ApprovalRequest.status == "pending",
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active pending approval already exists for "
                   f"{object_type} '{object_code}'",
        )


async def _request_approval_internal(
    db: AsyncSession, object_type: str, object_code: str, user_id,
) -> models.ApprovalRequest:
    """Internal: create ApprovalRequest without FastAPI-level validation.

    Caller MUST validate: object exists, valid state, no duplicate pending.
    Used by publication batch workflow (39.3.4).
    """
    approval_code = f"appr_{object_type}_{object_code.replace('-', '')[:48]}"
    approval = models.ApprovalRequest(
        approval_code=approval_code,
        object_type=object_type,
        object_code=object_code,
        status="pending",
        requested_by=user_id,
    )
    db.add(approval)
    return approval


# ── Public API ──────────────────────────────────────────────────────────


async def request_approval(
    db: AsyncSession,
    data: schemas.ApprovalRequestCreate,
    user_id,
) -> dict:
    """Request approval for a campaign or placement.

    Transitions object status to 'pending_approval'.
    """
    # 1. Validate object exists
    obj = await _get_object_or_404(db, data.object_type, data.object_code)

    # 1.5 Validate object is in a state that allows approval
    if obj.status not in ("draft", "pending_approval"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot request approval for {data.object_type} "
                   f"'{data.object_code}' in status '{obj.status}' "
                   f"(expected 'draft' or 'pending_approval')",
        )

    # 2. Check no active pending approval
    await _check_no_active_pending(db, data.object_type, data.object_code)

    # 3. Generate approval_code from object info
    approval_code = f"appr_{data.object_type}_{data.object_code}"

    # 4. Create approval request
    approval = models.ApprovalRequest(
        approval_code=approval_code,
        object_type=data.object_type,
        object_code=data.object_code,
        status="pending",
        requested_by=user_id,
        comment=data.comment,
    )
    db.add(approval)

    # 5. Transition object status
    obj.status = "pending_approval"

    await db.commit()
    await db.refresh(approval)

    return {
        "approval_code": approval.approval_code,
        "object_type": approval.object_type,
        "object_code": approval.object_code,
        "status": approval.status,
        "decision": approval.decision,
        "comment": approval.comment,
        "requested_at": approval.requested_at,
        "decided_at": approval.decided_at,
    }


async def decide_approval(
    db: AsyncSession,
    approval_code: str,
    data: schemas.ApprovalDecide,
    user_id,
) -> dict:
    """Decide on an approval request: approve or reject.

    Maker-checker: requested_by != decided_by.
    Transitions object status to 'approved' or 'rejected'.
    """
    # 1. Find approval
    result = await db.execute(
        select(models.ApprovalRequest).where(
            models.ApprovalRequest.approval_code == approval_code,
        )
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_code}' not found",
        )

    # 2. Already decided?
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approval '{approval_code}' is already {approval.status}",
        )

    # 3. Maker-checker: cannot decide own request
    if str(approval.requested_by) == str(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot decide your own approval request (maker-checker)",
        )

    # 4. Update approval
    approval.status = _DECISION_TO_APPROVAL_STATUS[data.decision]
    approval.decision = data.decision
    approval.decided_by = user_id
    approval.decided_at = datetime.now(timezone.utc)
    if data.comment:
        approval.comment = data.comment

    # 5. Transition object status
    obj = await _get_object_or_404(db, approval.object_type, approval.object_code)
    new_status = _DECISION_STATUS_MAP[data.decision]
    obj.status = new_status

    await db.commit()
    await db.refresh(approval)

    return {
        "approval_code": approval.approval_code,
        "object_type": approval.object_type,
        "object_code": approval.object_code,
        "status": approval.status,
        "decision": approval.decision,
        "comment": approval.comment,
        "requested_at": approval.requested_at,
        "decided_at": approval.decided_at,
    }


async def get_approval(
    db: AsyncSession,
    approval_code: str,
) -> dict:
    """Get a single approval request by code with safe projection."""
    result = await db.execute(
        select(models.ApprovalRequest).where(
            models.ApprovalRequest.approval_code == approval_code,
        )
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_code}' not found",
        )
    return {
        "approval_code": approval.approval_code,
        "object_type": approval.object_type,
        "object_code": approval.object_code,
        "status": approval.status,
        "decision": approval.decision,
        "comment": approval.comment,
        "requested_at": approval.requested_at,
        "decided_at": approval.decided_at,
    }


async def list_approvals(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[dict]:
    """List approval requests with safe projection — no raw UUIDs."""
    stmt = (
        select(models.ApprovalRequest)
        .order_by(models.ApprovalRequest.requested_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    approvals = result.scalars().all()

    return [
        {
            "approval_code": a.approval_code,
            "object_type": a.object_type,
            "object_code": a.object_code,
            "status": a.status,
            "decision": a.decision,
            "comment": a.comment,
            "requested_at": a.requested_at,
            "decided_at": a.decided_at,
        }
        for a in approvals
    ]
