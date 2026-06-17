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
from app.domains.campaigns import schemas, service

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
    _: identity_models.User = Depends(require_permission("campaigns.read")),
):
    return await service.list_campaigns(
        db, skip, limit,
        advertiser_id=advertiser_id,
        brand_id=brand_id,
        order_id=order_id,
        status_filter=status,
        channel_id=channel_id,
        planned_start_date_from=planned_start_date_from,
        planned_start_date_to=planned_start_date_to,
    )


@router.post("/campaigns", response_model=schemas.CampaignResponse, status_code=201)
async def create_campaign(
    data: schemas.CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("campaigns.create")),
):
    return await service.create_campaign(db, data, current_user.id)


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
    return await service.update_campaign(db, campaign_id, data)


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
