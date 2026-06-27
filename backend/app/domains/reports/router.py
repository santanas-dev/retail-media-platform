"""Reports export API endpoints — CSV downloads with RLS.

GET /api/reports/campaigns/export      — campaign status CSV
GET /api/reports/airtime/export        — airtime occupancy CSV
GET /api/reports/conflicts/export      — schedule conflicts CSV
GET /api/reports/publications/export   — publication batches CSV

All require reports.read permission.
Safe: no raw UUIDs in non-admin CSV, no tokens/secrets/backend URLs.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.identity.rls import resolve_user_scope_context
from app.domains.reports import service

router = APIRouter(prefix="/api/reports", tags=["reports-export"])


@router.get("/campaigns/export")
async def export_campaigns(
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
):
    """Download campaigns as CSV (RLS applied)."""
    ctx = await resolve_user_scope_context(db, current_user)
    return await service.export_campaigns_csv(db, current_user, ctx)


@router.get("/airtime/export")
async def export_airtime(
    device_codes: str = Query(..., description="Comma-separated device codes"),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
):
    """Download airtime occupancy as CSV (RLS applied)."""
    ctx = await resolve_user_scope_context(db, current_user)
    codes = [c.strip() for c in device_codes.split(",") if c.strip()]
    return await service.export_airtime_csv(db, current_user, ctx, codes)


@router.get("/conflicts/export")
async def export_conflicts(
    device_codes: str = Query(..., description="Comma-separated device codes"),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
):
    """Download schedule conflicts as CSV (RLS + anonymization applied)."""
    ctx = await resolve_user_scope_context(db, current_user)
    codes = [c.strip() for c in device_codes.split(",") if c.strip()]
    return await service.export_conflicts_csv(db, current_user, ctx, codes)


@router.get("/publications/export")
async def export_publications(
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
):
    """Download publication batches as CSV (RLS applied)."""
    ctx = await resolve_user_scope_context(db, current_user)
    return await service.export_publications_csv(db, current_user, ctx)
