"""Campaigns Core domain: FastAPI router.

13 endpoints:
  GET    /api/campaigns
  POST   /api/campaigns
  GET    /api/campaigns/{id}
  PUT    /api/campaigns/{id}
  POST   /api/campaigns/{id}/submit
  POST   /api/campaigns/{id}/approve
  POST   /api/campaigns/{id}/reject
  GET    /api/campaigns/{id}/channels
  PUT    /api/campaigns/{id}/channels
  GET    /api/campaigns/{id}/targets
  PUT    /api/campaigns/{id}/targets
  GET    /api/campaigns/{id}/renditions
  PUT    /api/campaigns/{id}/renditions
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.identity.rls import (
    resolve_user_scope_context,
    assert_object_in_advertiser_scope,
    apply_advertiser_rls,
)
from app.domains.campaigns import schemas, service, models as campaign_models
from app.domains.audit.service import audit_business_action

router = APIRouter(prefix="/api", tags=["campaigns"])


# ── Campaign CRUD ──────────────────────────────────────────────────────────

@router.get("/campaigns", response_model=list[schemas.CampaignResponse])
async def list_campaigns(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    advertiser_id: UUID | None = Query(None),
    brand_id: UUID | None = Query(None),
    order_id: UUID | None = Query(None),
    status: str | None = Query(None),
    channel_id: UUID | None = Query(None),
    planned_start_date_from: date | None = Query(None),
    planned_start_date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.read")),
):
    scope_ctx = await resolve_user_scope_context(db, current_user)
    return await service.list_campaigns(
        db, skip, limit,
        advertiser_id=advertiser_id,
        brand_id=brand_id,
        order_id=order_id,
        status_filter=status,
        channel_id=channel_id,
        planned_start_date_from=planned_start_date_from,
        planned_start_date_to=planned_start_date_to,
        scope_ctx=scope_ctx,
    )


@router.post("/campaigns", response_model=schemas.CampaignResponse, status_code=201)
async def create_campaign(
    data: schemas.CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.create")),
):
    result = await service.create_campaign(db, data, current_user.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="campaign.create", target_type="campaign",
        target_ref=result.campaign_code if hasattr(result, 'campaign_code') else "unknown",
        details={"name": data.name},
    )
    return result


@router.get("/campaigns/{campaign_id}", response_model=schemas.CampaignResponse)
async def get_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.read")),
):
    return await service.get_campaign(db, campaign_id)


@router.put("/campaigns/{campaign_id}", response_model=schemas.CampaignResponse)
async def update_campaign(
    campaign_id: UUID,
    data: schemas.CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    result = await service.update_campaign(db, campaign_id, data)
    await audit_business_action(
        db, actor_user_id=str(current_user.id) if 'current_user' in dir() else "unknown",
        action="campaign.update", target_type="campaign",
        target_ref=str(campaign_id),
        details={"updated_fields": list(data.dict(exclude_unset=True).keys()) if hasattr(data, 'dict') else []},
    )
    return result


# ── Lifecycle ──────────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/submit", response_model=schemas.CampaignResponse)
async def submit_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    return await service.submit_campaign(db, campaign_id)


@router.post("/campaigns/{campaign_id}/approve", response_model=schemas.CampaignResponse)
async def approve_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.approve")),
):
    return await service.approve_campaign(db, campaign_id, current_user.id)


@router.post("/campaigns/{campaign_id}/reject", response_model=schemas.CampaignResponse)
async def reject_campaign(
    campaign_id: UUID,
    data: schemas.RejectRequest,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.approve")),
):
    return await service.reject_campaign(db, campaign_id, data.rejection_reason)


# ── Channels ───────────────────────────────────────────────────────────────

@router.get(
    "/campaigns/{campaign_id}/channels",
    response_model=list[schemas.CampaignChannelResponse],
)
async def get_campaign_channels(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.read")),
):
    return await service.get_campaign_channels(db, campaign_id)


@router.put(
    "/campaigns/{campaign_id}/channels",
    response_model=list[schemas.CampaignChannelResponse],
)
async def set_campaign_channels(
    campaign_id: UUID,
    data: schemas.CampaignChannelPut,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    return await service.set_campaign_channels(db, campaign_id, data)


# ── Targets ────────────────────────────────────────────────────────────────

@router.get(
    "/campaigns/{campaign_id}/targets",
    response_model=list[schemas.CampaignTargetResponse],
)
async def get_campaign_targets(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.read")),
):
    return await service.get_campaign_targets(db, campaign_id)


@router.put(
    "/campaigns/{campaign_id}/targets",
    response_model=list[schemas.CampaignTargetResponse],
)
async def set_campaign_targets(
    campaign_id: UUID,
    data: schemas.CampaignTargetPut,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    return await service.set_campaign_targets(db, campaign_id, data)


# ── Renditions ─────────────────────────────────────────────────────────────

@router.get(
    "/campaigns/{campaign_id}/renditions",
    response_model=list[schemas.CampaignRenditionResponse],
)
async def get_campaign_renditions(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.read")),
):
    return await service.get_campaign_renditions(db, campaign_id)


@router.put(
    "/campaigns/{campaign_id}/renditions",
    response_model=list[schemas.CampaignRenditionResponse],
)
async def set_campaign_renditions(
    campaign_id: UUID,
    data: schemas.CampaignRenditionPut,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    return await service.set_campaign_renditions(db, campaign_id, data)


# ═══════════════════════════════════════════════════════════════════════════
# Test KSO Vertical Slice — Safe Campaign Create + List (Step 37.4)
# ═══════════════════════════════════════════════════════════════════════════
# TEMPORARY safe wrappers for the one-KSO technical validation.
# These endpoints create standard Campaigns using synthetic dev technical
# context — NOT a separate business model.  Will be superseded by the
# full campaign workflow in Phase 5.


@router.get(
    "/campaigns/test-kso",
    response_model=list[schemas.CampaignSafeResponse],
)
async def list_test_kso_campaigns(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("campaigns.read")),
):
    """List campaigns for test KSO vertical slice (safe projection).

    Only campaigns with a campaign_code are returned.
    Response: campaign_code, name, status, description, creative_codes,
    created_at, updated_at.  NO raw UUIDs, order_id, advertiser_id,
    brand_id, budget, currency, file_path, sha256, storage_ref,
    minio, backend_url, tokens.
    """
    return await service.list_test_kso_campaigns(db, skip, limit)


@router.post(
    "/campaigns/test-kso",
    response_model=schemas.CampaignSafeResponse,
    status_code=201,
)
async def create_test_kso_campaign(
    data: schemas.CampaignTestKsoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("campaigns.create")
    ),
):
    """Create a standard Campaign for test KSO technical validation.

    Uses synthetic dev technical context internally (demo_advertiser_technical,
    demo_brand_technical, demo_order_technical).  Links creatives by stable
    creative_code.  Returns safe fields only — NO raw UUIDs, commercial fields,
    or secrets.
    """
    campaign = await service.create_test_kso_campaign(
        db, data, current_user.id,
    )
    creative_codes = sorted([
        cc.creative_code for cc in (campaign.creatives or [])
    ])
    return schemas.CampaignSafeResponse(
        campaign_code=campaign.campaign_code,
        name=campaign.name,
        status=campaign.status,
        description=campaign.comment,
        creative_codes=creative_codes,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Production campaign creation by code (39.2.2.1)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/campaigns/by-code",
    response_model=schemas.CampaignSafeResponse,
    status_code=201,
)
async def create_campaign_by_code(
    data: schemas.CampaignCreateByCode,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.create")),
):
    """Create a campaign via production-safe code-based input (no UUIDs)."""
    return await service.create_campaign_by_code(db, data, current_user.id)


# ═══════════════════════════════════════════════════════════════════════════
# Code-based campaign lookups (production API)
# Lookup by campaign_code instead of raw UUID — safe for frontend.
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/campaigns/by-code/{campaign_code}",
    response_model=schemas.CampaignResponse,
)
async def get_campaign_by_code(
    campaign_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.read")),
):
    """Get campaign by campaign_code (safe external identifier)."""
    from fastapi import HTTPException
    campaign = await service.get_campaign_by_code(db, campaign_code)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "view campaign")
    return campaign


@router.patch(
    "/campaigns/by-code/{campaign_code}",
    response_model=schemas.CampaignResponse,
)
async def patch_campaign_by_code(
    campaign_code: str,
    data: schemas.CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    """Update campaign by campaign_code. RLS: advertiser scope enforced."""
    from fastapi import HTTPException
    campaign = await service.get_campaign_by_code(db, campaign_code)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "modify campaign")
    result = await service.update_campaign(db, campaign.id, data)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="campaign.update", target_type="campaign",
        target_ref=campaign_code,
        details={"status": result.status if hasattr(result, 'status') else "updated"},
    )
    return result


@router.post(
    "/campaigns/by-code/{campaign_code}/archive",
    response_model=schemas.CampaignResponse,
)
async def archive_campaign_by_code(
    campaign_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    """Archive campaign by campaign_code. RLS: advertiser scope enforced."""
    from fastapi import HTTPException
    campaign = await service.get_campaign_by_code(db, campaign_code)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "archive campaign")
    result = await service.archive_campaign(db, campaign.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="campaign.archive", target_type="campaign",
        target_ref=campaign_code,
    )
    return result


@router.post(
    "/campaigns/by-code/{campaign_code}/submit",
    response_model=schemas.CampaignSafeResponse,
)
async def submit_campaign_by_code(
    campaign_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    """Submit campaign for approval via production ApprovalRequest flow.

    Creates an ApprovalRequest (object_type=campaign), transitions campaign
    to pending_approval.  Validates completeness: creative binding + schedule.
    Maker-checker enforced by approval domain.
    """
    from fastapi import HTTPException
    from app.domains.approvals import service as approvals_service
    from app.domains.approvals.schemas import ApprovalRequestCreate

    campaign = await service.get_campaign_by_code(db, campaign_code)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "submit campaign")

    # ═══════════════════════════════════════════════════════════════
    # Completeness validation
    # ═══════════════════════════════════════════════════════════════
    from sqlalchemy import select as sa_select
    from app.domains.campaigns.models import CampaignCreative as CC
    from app.domains.scheduling.models import Schedule as SchedModel, ScheduleSlot
    from app.domains.media.models import Creative as CreativeModel

    # 1. Has at least one creative binding
    cc_result = await db.execute(
        sa_select(CC).where(CC.campaign_id == campaign.id)
    )
    active_bindings = cc_result.scalars().all()
    if not active_bindings:
        raise HTTPException(
            status_code=400,
            detail="Cannot submit: campaign has no active creative bindings",
        )

    # 2. Bound creatives are not archived/rejected
    creative_codes_check = [cc.creative_code for cc in active_bindings]
    creative_check = await db.execute(
        sa_select(CreativeModel).where(
            CreativeModel.creative_code.in_(creative_codes_check)
        )
    )
    creatives_by_code = {c.creative_code: c for c in creative_check.scalars().all()}
    for cc in creative_codes_check:
        creative = creatives_by_code.get(cc)
        if not creative:
            raise HTTPException(status_code=400, detail=f"Cannot submit: creative '{cc}' not found")
        if creative.status in ("archived", "rejected"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot submit: creative '{cc}' is {creative.status}",
            )

    # 3. Has schedule (at least one schedule linked to this campaign)
    sched_result = await db.execute(
        sa_select(SchedModel).where(SchedModel.campaign_code == campaign_code)
    )
    schedules = sched_result.scalars().all()
    if not schedules:
        raise HTTPException(
            status_code=400,
            detail="Cannot submit: campaign has no schedule",
        )

    # 4. Schedule has at least one slot
    has_slots = False
    for s in schedules:
        slot_result = await db.execute(
            sa_select(ScheduleSlot).where(
                ScheduleSlot.schedule_id == s.id,
                ScheduleSlot.is_active == True,
            )
        )
        if slot_result.scalars().first():
            has_slots = True
            break
    if not has_slots:
        raise HTTPException(
            status_code=400,
            detail="Cannot submit: campaign has no active schedule slots",
        )

    # ═══════════════════════════════════════════════════════════════
    # Create ApprovalRequest via production approval flow
    # ═══════════════════════════════════════════════════════════════
    approval_data = ApprovalRequestCreate(
        object_type="campaign",
        object_code=campaign_code,
        comment=f"Submit by {current_user.username if hasattr(current_user, 'username') else 'user'}",
    )
    approval_result = await approvals_service.request_approval(
        db, approval_data, current_user.id, scope_ctx=scope_ctx,
    )

    # Reload campaign to get updated status
    await db.refresh(campaign)
    creative_codes = sorted([cc.creative_code for cc in (campaign.creatives or [])])

    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="campaign.submit", target_type="campaign",
        target_ref=campaign_code,
        details={
            "new_status": campaign.status,
            "approval_code": approval_result.get("approval_code"),
        },
    )
    return schemas.CampaignSafeResponse(
        campaign_code=campaign.campaign_code or campaign_code,
        name=campaign.name,
        status=campaign.status,
        description=campaign.comment,
        creative_codes=creative_codes,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Campaign-Creative Binding (production API)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/campaigns/by-code/{campaign_code}/creatives",
    response_model=list[schemas.CampaignCreativeSafeResponse],
)
async def list_campaign_creatives(
    campaign_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.read")),
):
    """List creatives bound to a campaign (safe projection). RLS enforced."""
    from fastapi import HTTPException
    campaign = await service.get_campaign_by_code(db, campaign_code)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "view creatives")
    return await service.list_campaign_creatives(db, campaign.id)


@router.post(
    "/campaigns/by-code/{campaign_code}/creatives",
    response_model=schemas.CampaignCreativeSafeResponse,
    status_code=201,
)
async def bind_campaign_creative(
    campaign_code: str,
    data: schemas.CampaignCreativeBind,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    """Bind a creative to a campaign."""
    from fastapi import HTTPException
    campaign = await service.get_campaign_by_code(db, campaign_code)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "modify campaign")
    # Also verify creative belongs to scope
    creative_adv = await service.get_creative_advertiser(db, data.creative_code)
    if creative_adv is not None:
        assert_object_in_advertiser_scope(creative_adv, scope_ctx, "bind creative")
    result = await service.bind_campaign_creative(db, campaign.id, data.creative_code)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="campaign.bind_creative", target_type="campaign",
        target_ref=campaign_code,
        details={"creative_code": data.creative_code},
    )
    return result


@router.delete(
    "/campaigns/by-code/{campaign_code}/creatives/{creative_code}",
    response_model=schemas.CampaignCreativeSafeResponse,
)
async def unbind_campaign_creative(
    campaign_code: str,
    creative_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.manage")),
):
    """Remove a creative binding from a campaign (deactivate). RLS enforced."""
    from fastapi import HTTPException
    campaign = await service.get_campaign_by_code(db, campaign_code)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    assert_object_in_advertiser_scope(campaign.advertiser_id, scope_ctx, "modify campaign")
    result = await service.unbind_campaign_creative(db, campaign.id, creative_code)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="campaign.unbind_creative", target_type="campaign",
        target_ref=campaign_code,
        details={"creative_code": creative_code},
    )
    return result
