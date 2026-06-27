"""Airtime occupancy and conflict API endpoints.

GET /api/airtime/occupancy  — planned airtime occupancy
GET /api/airtime/conflicts   — schedule slot conflicts
"""

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.airtime import service

router = APIRouter(prefix="/api/airtime", tags=["airtime"])


def _parse_date(value: str, label: str) -> date_type:
    """Parse YYYY-MM-DD with safe error."""
    try:
        return date_type.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label}: '{value}'. Use YYYY-MM-DD.",
        )


@router.get("/occupancy")
async def get_occupancy(
    device_code: str = Query(..., min_length=1, max_length=64, description="Device code"),
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    placement_code: str | None = Query(None, max_length=64, description="Optional placement filter"),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
):
    """Calculate planned airtime occupancy for a device.

    Returns minutes occupied, free, and occupancy percent.
    All planned — no physical PoP data.
    """
    df = _parse_date(date_from, "date_from")
    dt = _parse_date(date_to, "date_to")
    if df > dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must not be after date_to",
        )

    return await service.calculate_occupancy(
        db, device_code=device_code, date_from=df, date_to=dt,
        placement_code=placement_code,
    )


@router.get("/conflicts")
async def get_conflicts(
    device_code: str = Query(..., min_length=1, max_length=64, description="Device code"),
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    campaign_code: str | None = Query(None, max_length=64, description="Optional campaign filter"),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("reports.read")),
):
    """Detect schedule slot conflicts on a device.

    Advertiser sees anonymized conflicts (no foreign campaign names).
    Admin sees full details.
    """
    df = _parse_date(date_from, "date_from")
    dt = _parse_date(date_to, "date_to")
    if df > dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must not be after date_to",
        )

    # Determine if user is admin-level (sees full conflict details)
    is_admin = False
    if current_user.roles:
        role_names = {r.name for r in current_user.roles if hasattr(r, "name")}
        is_admin = bool({"system_admin", "security_admin", "manager"} & role_names)

    return await service.detect_conflicts(
        db, device_code=device_code, date_from=df, date_to=dt,
        campaign_code=campaign_code, is_admin=is_admin,
    )
