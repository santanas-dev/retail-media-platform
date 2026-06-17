"""Campaigns Core domain: business logic."""

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.campaigns import models, schemas
from app.domains.advertisers.models import Order, Brand
from app.domains.media.models import Rendition, CreativeVersion, Creative
from app.domains.channels.models import Channel, LogicalCarrier, DisplaySurface
from app.domains.organization.models import Branch, Cluster, Store


EDITABLE_STATUSES = frozenset({"draft", "rejected"})
SUBMIT_FROM_STATUSES = frozenset({"draft", "rejected"})


# ── Helpers ───────────────────────────────────────────────────────────────

async def _get_campaign_or_404(db: AsyncSession, campaign_id: UUID) -> models.Campaign:
    result = await db.execute(
        select(models.Campaign).where(models.Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
        )
    return campaign


async def _get_order_or_404(db: AsyncSession, order_id: UUID) -> Order:
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _check_editable(campaign: models.Campaign) -> None:
    if campaign.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit campaign in status '{campaign.status}'. "
                   f"Only draft/rejected campaigns are editable.",
        )


# ── Validation helpers ────────────────────────────────────────────────────

async def _validate_order_consistency(
    db: AsyncSession, data: schemas.CampaignCreate
) -> Order:
    """Validate order exists and campaign data is consistent with it."""
    order = await _get_order_or_404(db, data.order_id)

    # advertiser_id check
    expected_adv_id = order.advertiser_id
    if data.advertiser_id is not None and data.advertiser_id != expected_adv_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"advertiser_id must match order.advertiser_id ({expected_adv_id})",
        )

    # brand_id check
    if order.brand_id is not None:
        # Order has a brand — campaign must match
        if data.brand_id is not None and data.brand_id != order.brand_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"brand_id must match order.brand_id ({order.brand_id})",
            )
    elif data.brand_id is not None:
        # Order has no brand — check brand belongs to advertiser
        br = await db.execute(
            select(Brand.id).where(
                Brand.id == data.brand_id,
                Brand.advertiser_id == expected_adv_id,
            )
        )
        if br.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="brand_id does not belong to order.advertiser_id",
            )

    # Date range check against order
    start = data.planned_start_date
    end = data.planned_end_date
    if order.planned_start_date is not None and start < order.planned_start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"planned_start_date {start} is before order.planned_start_date "
                   f"{order.planned_start_date}",
        )
    if order.planned_end_date is not None and end > order.planned_end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"planned_end_date {end} exceeds order.planned_end_date "
                   f"{order.planned_end_date}",
        )

    return order


async def _check_campaign_ready(
    db: AsyncSession, campaign: models.Campaign, step: str = "submit"
) -> None:
    """Validate campaign has required sub-resources for submit/approve.

    Checks:
    - At least 1 channel
    - At least 1 target
    - At least 1 rendition with: is_active=true, rendition.status=valid,
      creative.status=approved, creative!=archived, version!=archived,
      rendition channel in campaign_channels.
    """
    prefix = f"Cannot {step}:"

    # Channels
    if not campaign.channels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{prefix} campaign has no channels",
        )

    # Targets
    if not campaign.targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{prefix} campaign has no targets",
        )

    # Renditions
    valid_renditions = []
    campaign_channel_ids = {c.channel_id for c in campaign.channels}

    for cr in campaign.renditions:
        if not cr.is_active:
            continue

        rendition = await db.execute(
            select(Rendition)
            .options(
                selectinload(Rendition.creative_version).selectinload(CreativeVersion.creative)
            )
            .where(Rendition.id == cr.rendition_id)
        )
        rendition = rendition.scalar_one_or_none()
        if not rendition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{prefix} rendition {cr.rendition_id} not found",
            )

        if rendition.status != "valid":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{prefix} rendition {cr.rendition_id} status is "
                       f"'{rendition.status}', must be 'valid'",
            )

        ver = rendition.creative_version
        if ver.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{prefix} creative version {ver.id} is archived",
            )

        creative = ver.creative
        if creative.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{prefix} creative {creative.id} status is "
                       f"'{creative.status}', must be 'approved'",
            )
        if creative.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{prefix} creative {creative.id} is archived",
            )

        if rendition.channel_id not in campaign_channel_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{prefix} rendition channel {rendition.channel_id} "
                       f"not in campaign channels",
            )

        valid_renditions.append(cr)

    if not valid_renditions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{prefix} campaign has no active valid renditions",
        )


# ── Campaign CRUD ─────────────────────────────────────────────────────────

async def list_campaigns(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    advertiser_id: UUID | None = None,
    brand_id: UUID | None = None,
    order_id: UUID | None = None,
    status_filter: str | None = None,
    channel_id: UUID | None = None,
    planned_start_date_from: date | None = None,
    planned_start_date_to: date | None = None,
) -> list[models.Campaign]:
    stmt = select(models.Campaign).order_by(models.Campaign.created_at.desc())

    if advertiser_id is not None:
        stmt = stmt.where(models.Campaign.advertiser_id == advertiser_id)
    if brand_id is not None:
        stmt = stmt.where(models.Campaign.brand_id == brand_id)
    if order_id is not None:
        stmt = stmt.where(models.Campaign.order_id == order_id)
    if status_filter is not None:
        stmt = stmt.where(models.Campaign.status == status_filter)
    if channel_id is not None:
        stmt = stmt.join(
            models.CampaignChannel,
            models.Campaign.id == models.CampaignChannel.campaign_id,
        ).where(models.CampaignChannel.channel_id == channel_id)
    if planned_start_date_from is not None:
        stmt = stmt.where(models.Campaign.planned_start_date >= planned_start_date_from)
    if planned_start_date_to is not None:
        stmt = stmt.where(models.Campaign.planned_start_date <= planned_start_date_to)

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_campaign(db: AsyncSession, campaign_id: UUID) -> models.Campaign:
    return await _get_campaign_or_404(db, campaign_id)


async def create_campaign(
    db: AsyncSession, data: schemas.CampaignCreate, user_id: UUID
) -> models.Campaign:
    order = await _validate_order_consistency(db, data)

    campaign = models.Campaign(
        order_id=data.order_id,
        advertiser_id=order.advertiser_id,  # always from order
        brand_id=data.brand_id if data.brand_id else order.brand_id,
        name=data.name,
        objective=data.objective,
        status="draft",
        planned_start_date=data.planned_start_date,
        planned_end_date=data.planned_end_date,
        priority=data.priority,
        budget=data.budget,
        currency=data.currency,
        comment=data.comment,
        created_by=user_id,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def update_campaign(
    db: AsyncSession, campaign_id: UUID, data: schemas.CampaignUpdate
) -> models.Campaign:
    campaign = await _get_campaign_or_404(db, campaign_id)
    _check_editable(campaign)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(campaign, key, value)
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)
    return campaign


# ── Lifecycle ─────────────────────────────────────────────────────────────

async def submit_campaign(
    db: AsyncSession, campaign_id: UUID
) -> models.Campaign:
    campaign = await _get_campaign_or_404(db, campaign_id)
    if campaign.status not in SUBMIT_FROM_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit campaign in status '{campaign.status}'. "
                   f"Must be draft or rejected.",
        )
    await _check_campaign_ready(db, campaign, "submit")
    campaign.status = "in_review"
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def approve_campaign(
    db: AsyncSession, campaign_id: UUID, user_id: UUID
) -> models.Campaign:
    campaign = await _get_campaign_or_404(db, campaign_id)
    if campaign.status != "in_review":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve campaign in status '{campaign.status}'. "
                   f"Must be in_review.",
        )
    await _check_campaign_ready(db, campaign, "approve")
    campaign.status = "approved"
    campaign.approved_by = user_id
    campaign.approved_at = datetime.now(timezone.utc)
    campaign.rejection_reason = None
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def reject_campaign(
    db: AsyncSession, campaign_id: UUID, reason: str
) -> models.Campaign:
    campaign = await _get_campaign_or_404(db, campaign_id)
    if campaign.status != "in_review":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject campaign in status '{campaign.status}'. "
                   f"Must be in_review.",
        )
    campaign.status = "rejected"
    campaign.rejection_reason = reason
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)
    return campaign


# ── Channels ──────────────────────────────────────────────────────────────

async def get_campaign_channels(
    db: AsyncSession, campaign_id: UUID
) -> list[models.CampaignChannel]:
    await _get_campaign_or_404(db, campaign_id)
    result = await db.execute(
        select(models.CampaignChannel)
        .where(models.CampaignChannel.campaign_id == campaign_id)
    )
    return list(result.scalars().all())


async def set_campaign_channels(
    db: AsyncSession, campaign_id: UUID, data: schemas.CampaignChannelPut
) -> list[models.CampaignChannel]:
    campaign = await _get_campaign_or_404(db, campaign_id)
    _check_editable(campaign)

    # Deduplicate
    channel_ids = list(dict.fromkeys(data.channel_ids))

    # Validate all channels exist
    if channel_ids:
        result = await db.execute(
            select(Channel.id).where(Channel.id.in_(channel_ids))
        )
        existing_ids = {r[0] for r in result}
        missing = set(channel_ids) - existing_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Channels not found: {missing}",
            )

    # Replace: delete old, insert new
    campaign.channels.clear()
    new_channels = [
        models.CampaignChannel(campaign_id=campaign_id, channel_id=cid)
        for cid in channel_ids
    ]
    db.add_all(new_channels)
    await db.commit()
    return new_channels


# ── Targets ───────────────────────────────────────────────────────────────

async def get_campaign_targets(
    db: AsyncSession, campaign_id: UUID
) -> list[models.CampaignTarget]:
    await _get_campaign_or_404(db, campaign_id)
    result = await db.execute(
        select(models.CampaignTarget)
        .where(models.CampaignTarget.campaign_id == campaign_id)
    )
    return list(result.scalars().all())


async def set_campaign_targets(
    db: AsyncSession, campaign_id: UUID, data: schemas.CampaignTargetPut
) -> list[models.CampaignTarget]:
    campaign = await _get_campaign_or_404(db, campaign_id)
    _check_editable(campaign)

    # Validate FK existence
    _TABLE_MAP = {
        "branch": Branch,
        "cluster": Cluster,
        "store": Store,
        "logical_carrier": LogicalCarrier,
        "display_surface": DisplaySurface,
    }
    for item in data.targets:
        if item.target_type == "all_stores":
            continue
        id_field = item.target_type + "_id"
        fk_value = getattr(item, id_field)
        table = _TABLE_MAP.get(item.target_type)
        if table and fk_value:
            result = await db.execute(
                select(table.id).where(table.id == fk_value)
            )
            if result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{item.target_type} with id {fk_value} not found",
                )

    # Replace
    campaign.targets.clear()
    new_targets = [
        models.CampaignTarget(
            campaign_id=campaign_id,
            target_type=item.target_type,
            branch_id=item.branch_id,
            cluster_id=item.cluster_id,
            store_id=item.store_id,
            logical_carrier_id=item.logical_carrier_id,
            display_surface_id=item.display_surface_id,
        )
        for item in data.targets
    ]
    db.add_all(new_targets)
    await db.commit()
    return new_targets


# ── Renditions ────────────────────────────────────────────────────────────

async def get_campaign_renditions(
    db: AsyncSession, campaign_id: UUID
) -> list[models.CampaignRendition]:
    await _get_campaign_or_404(db, campaign_id)
    result = await db.execute(
        select(models.CampaignRendition)
        .where(models.CampaignRendition.campaign_id == campaign_id)
    )
    return list(result.scalars().all())


async def set_campaign_renditions(
    db: AsyncSession, campaign_id: UUID, data: schemas.CampaignRenditionPut
) -> list[models.CampaignRendition]:
    campaign = await _get_campaign_or_404(db, campaign_id)
    _check_editable(campaign)

    # Deduplicate rendition_ids
    seen = set()
    unique_items = []
    for item in data.renditions:
        if item.rendition_id not in seen:
            seen.add(item.rendition_id)
            unique_items.append(item)

    # Validate all renditions exist and are valid
    rendition_ids = [item.rendition_id for item in unique_items]
    result = await db.execute(
        select(Rendition)
        .options(
            selectinload(Rendition.creative_version).selectinload(CreativeVersion.creative)
        )
        .where(Rendition.id.in_(rendition_ids))
    )
    renditions_by_id = {r.id: r for r in result.scalars().all()}

    campaign_channel_ids = {c.channel_id for c in campaign.channels}

    for item in unique_items:
        rendition = renditions_by_id.get(item.rendition_id)
        if not rendition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rendition {item.rendition_id} not found",
            )
        if rendition.status != "valid":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rendition {item.rendition_id} status is "
                       f"'{rendition.status}', must be 'valid'",
            )
        ver = rendition.creative_version
        if ver.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Creative version {ver.id} is archived",
            )
        creative = ver.creative
        if creative.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Creative {creative.id} status is "
                       f"'{creative.status}', must be 'approved'",
            )
        if creative.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Creative {creative.id} is archived",
            )
        if rendition.channel_id not in campaign_channel_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rendition channel {rendition.channel_id} not in "
                       f"campaign channels",
            )

    # Replace
    campaign.renditions.clear()
    new_renditions = [
        models.CampaignRendition(
            campaign_id=campaign_id,
            rendition_id=item.rendition_id,
            weight=item.weight,
            position=item.position,
        )
        for item in unique_items
    ]
    db.add_all(new_renditions)
    await db.commit()
    return new_renditions
