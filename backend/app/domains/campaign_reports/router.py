"""Campaign Delivery Reporting Core: API router."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity.models import User
from app.domains.campaign_reports import schemas, service

router = APIRouter(
    prefix="/api/campaign-reports",
    tags=["campaign-reports"],
)


# ── Helpers ───────────────────────────────────────────────────────

def _parse_dates(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be <= date_to")
    return date_from, date_to


# ── Summary ───────────────────────────────────────────────────────

@router.get(
    "/{campaign_id}/summary",
    response_model=schemas.SummaryResponse,
)
async def get_summary(
    campaign_id: UUID,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("campaign_reports.read")),
):
    date_from, date_to = _parse_dates(date_from, date_to)
    result = await service.get_summary(db, campaign_id, date_from, date_to)
    if result is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return result


# ── By Store ──────────────────────────────────────────────────────

@router.get(
    "/{campaign_id}/by-store",
    response_model=list[schemas.StoreReportItem],
)
async def get_by_store(
    campaign_id: UUID,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("campaign_reports.read")),
):
    date_from, date_to = _parse_dates(date_from, date_to)
    return await service.get_by_store(db, campaign_id, date_from, date_to)


# ── By Channel ────────────────────────────────────────────────────

@router.get(
    "/{campaign_id}/by-channel",
    response_model=list[schemas.ChannelReportItem],
)
async def get_by_channel(
    campaign_id: UUID,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("campaign_reports.read")),
):
    date_from, date_to = _parse_dates(date_from, date_to)
    return await service.get_by_channel(db, campaign_id, date_from, date_to)


# ── By Device ─────────────────────────────────────────────────────

@router.get(
    "/{campaign_id}/by-device",
    response_model=list[schemas.DeviceReportItem],
)
async def get_by_device(
    campaign_id: UUID,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    store_id: Optional[UUID] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("campaign_reports.read")),
):
    date_from, date_to = _parse_dates(date_from, date_to)
    return await service.get_by_device(
        db, campaign_id, date_from, date_to,
        store_id, channel_id, limit, offset,
    )


# ── By Creative ───────────────────────────────────────────────────

@router.get(
    "/{campaign_id}/by-creative",
    response_model=list[schemas.CreativeReportItem],
)
async def get_by_creative(
    campaign_id: UUID,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("campaign_reports.read")),
):
    date_from, date_to = _parse_dates(date_from, date_to)
    return await service.get_by_creative(db, campaign_id, date_from, date_to)


# ── Snapshots ─────────────────────────────────────────────────────

@router.post(
    "/{campaign_id}/snapshots",
    response_model=schemas.SnapshotResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_snapshot(
    campaign_id: UUID,
    body: schemas.SnapshotCreateRequest = schemas.SnapshotCreateRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("campaign_reports.manage")),
):
    snap = await service.create_snapshot(
        db, campaign_id, current_user.id,
        body.period_from, body.period_to,
    )
    if snap is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.commit()
    return snap


@router.get(
    "/{campaign_id}/snapshots",
    response_model=list[schemas.SnapshotResponse],
)
async def list_snapshots(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("campaign_reports.read")),
):
    return await service.list_snapshots(db, campaign_id)


@router.get(
    "/{campaign_id}/snapshots/{snapshot_id}",
    response_model=schemas.SnapshotDetailResponse,
)
async def get_snapshot(
    campaign_id: UUID,
    snapshot_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("campaign_reports.read")),
):
    snap = await service.get_snapshot(db, campaign_id, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snap
