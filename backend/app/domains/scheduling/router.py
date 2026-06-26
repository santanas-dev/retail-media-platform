"""Scheduling domain: FastAPI router (Step 37.5).

Test KSO vertical slice — minimal placement/schedule endpoints.
Safe projection: NO raw UUIDs, commercial fields, or secrets.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.identity.rls import resolve_user_scope_context, assert_object_in_advertiser_scope
from app.domains.scheduling import schemas, service

router = APIRouter(prefix="/api", tags=["scheduling"])

# ── RLS helper ─────────────────────────────────────────────────────────────

async def _resolve_campaign_advertiser(db: AsyncSession, campaign_code: str):
    """Resolve campaign_code → advertiser_id. Returns None if not found."""
    from sqlalchemy import select as sa_select
    from app.domains.campaigns.models import Campaign
    result = await db.execute(
        sa_select(Campaign.advertiser_id).where(Campaign.campaign_code == campaign_code)
    )
    row = result.first()
    return row[0] if row else None

# ── Production Placement API ───────────────────────────────────────────────


@router.get(
    "/placements",
    response_model=list[schemas.KsoPlacementResponse],
)
async def list_placements_prod(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """List all placements with safe projection (production API). RLS enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    placements = await service.list_placements(db, skip, limit)
    # RLS post-filter: only placements whose campaign is in advertiser scope
    if scope_ctx.is_advertiser_scoped:
        filtered = []
        for p in placements:
            adv_id = await _resolve_campaign_advertiser(db, p["campaign_code"])
            if adv_id and adv_id in scope_ctx.advertiser_ids:
                filtered.append(p)
        return filtered
    return placements


@router.post(
    "/placements",
    response_model=schemas.KsoPlacementResponse,
    status_code=201,
)
async def create_placement_prod(
    data: schemas.KsoPlacementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("scheduling.manage")
    ),
):
    """Create a placement linking campaign→creative→device (production API). RLS enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_campaign_advertiser(db, data.campaign_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "create placement")
    return await service.create_placement(db, data, current_user.id)


@router.get(
    "/placements/{placement_code}",
    response_model=schemas.KsoPlacementResponse,
)
async def get_placement_prod(
    placement_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """Get placement by code (production API). RLS enforced."""
    placement = await service.get_placement(db, placement_code)
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_campaign_advertiser(db, placement["campaign_code"])
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view placement")
    return placement


@router.patch(
    "/placements/{placement_code}",
    response_model=schemas.KsoPlacementResponse,
)
async def patch_placement_prod(
    placement_code: str,
    data: schemas.KsoPlacementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Update placement fields. RLS: advertiser scope enforced via campaign_code."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    placement = await service.get_placement(db, placement_code)
    adv_id = await _resolve_campaign_advertiser(db, placement["campaign_code"])
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "modify placement")
    return await service.update_placement(db, placement_code, data)


@router.post(
    "/placements/{placement_code}/archive",
    response_model=schemas.KsoPlacementResponse,
)
async def archive_placement_prod(
    placement_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Archive a placement. RLS: advertiser scope enforced via campaign_code."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    placement = await service.get_placement(db, placement_code)
    adv_id = await _resolve_campaign_advertiser(db, placement["campaign_code"])
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "archive placement")
    return await service.archive_placement(db, placement_code)


# ── Test KSO Vertical Slice (legacy, will be retired) ──────────────────────
# These endpoints are retained for test KSO backward compatibility.
# New code should use /api/placements above.


@router.get(
    "/test-kso",
    response_model=list[schemas.KsoPlacementResponse],
)
async def list_placements(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """List placements for test KSO vertical slice (safe projection)."""
    return await service.list_placements(db, skip, limit)


@router.post(
    "/test-kso",
    response_model=schemas.KsoPlacementResponse,
    status_code=201,
)
async def create_placement(
    data: schemas.KsoPlacementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("scheduling.manage")
    ),
):
    """Create a placement for test KSO technical validation."""
    return await service.create_placement(db, data, current_user.id)


@router.get(
    "/test-kso/{placement_code}",
    response_model=schemas.KsoPlacementResponse,
)
async def get_placement(
    placement_code: str,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """Get a single placement by code (safe projection)."""
    return await service.get_placement(db, placement_code)


# ═══════════════════════════════════════════════════════════════════════════
# Schedule + ScheduleSlot production endpoints (39.1.3)
# RLS: advertiser scope enforced via schedule.campaign_code → campaign.advertiser_id
# ═══════════════════════════════════════════════════════════════════════════


async def _resolve_schedule_advertiser(db: AsyncSession, schedule_code: str):
    """Resolve schedule → campaign → advertiser_id. Returns None if not found."""
    from sqlalchemy import select as sa_select
    from app.domains.scheduling.models import Schedule as SchedModel
    from app.domains.campaigns.models import Campaign as CampModel
    result = await db.execute(
        sa_select(CampModel.advertiser_id)
        .join(SchedModel, SchedModel.campaign_code == CampModel.campaign_code)
        .where(SchedModel.schedule_code == schedule_code)
    )
    row = result.first()
    return row[0] if row else None


@router.get(
    "/schedules",
    response_model=list[schemas.ScheduleResponse],
)
async def list_schedules_prod(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """List schedules. RLS: filtered to advertiser scope via campaign_code join."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    schedules = await service.list_schedules(db, skip, limit)
    if scope_ctx.is_advertiser_scoped:
        filtered = []
        for s in schedules:
            adv_id = await _resolve_schedule_advertiser(db, s["schedule_code"])
            if adv_id and adv_id in scope_ctx.advertiser_ids:
                filtered.append(s)
            elif s.get("campaign_code") is None:
                filtered.append(s)  # unassigned — visible to all scoped users
        return filtered
    return schedules


@router.post(
    "/schedules",
    response_model=schemas.ScheduleResponse,
    status_code=201,
)
async def create_schedule_prod(
    data: schemas.ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Create schedule. RLS: if campaign_code provided, must be in advertiser scope."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    if data.campaign_code:
        adv_id = await _resolve_campaign_advertiser(db, data.campaign_code)
        if adv_id is not None:
            assert_object_in_advertiser_scope(adv_id, scope_ctx, "create schedule")
    return await service.create_schedule(db, data, current_user.id)


@router.get(
    "/schedules/{schedule_code}",
    response_model=schemas.ScheduleResponse,
)
async def get_schedule_prod(
    schedule_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """Get schedule by code. RLS: advertiser scope enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_schedule_advertiser(db, schedule_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view schedule")
    return await service.get_schedule(db, schedule_code)


@router.patch(
    "/schedules/{schedule_code}",
    response_model=schemas.ScheduleResponse,
)
async def patch_schedule_prod(
    schedule_code: str,
    data: schemas.ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Patch schedule. RLS: advertiser scope enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_schedule_advertiser(db, schedule_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "modify schedule")
    return await service.update_schedule(db, schedule_code, data)


@router.post(
    "/schedules/{schedule_code}/archive",
    response_model=schemas.ScheduleResponse,
)
async def archive_schedule_prod(
    schedule_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Archive schedule. RLS: advertiser scope enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_schedule_advertiser(db, schedule_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "archive schedule")
    return await service.archive_schedule(db, schedule_code)


# ── Schedule Slots ────────────────────────────────────────────────────────

@router.get(
    "/schedules/{schedule_code}/items",
    response_model=list[schemas.ScheduleSlotResponse],
)
async def list_slots_prod(
    schedule_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.read")),
):
    """List slots for schedule. RLS: inherited from parent schedule."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_schedule_advertiser(db, schedule_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view schedule slots")
    return await service.list_schedule_slots(db, schedule_code)


@router.post(
    "/schedules/{schedule_code}/items",
    response_model=schemas.ScheduleSlotResponse,
    status_code=201,
)
async def create_slot_prod(
    schedule_code: str,
    data: schemas.ScheduleSlotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Create slot in schedule. RLS: inherited from parent schedule."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_schedule_advertiser(db, schedule_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "create schedule slot")
    return await service.create_schedule_slot(db, schedule_code, data)


@router.patch(
    "/schedules/{schedule_code}/items/{slot_code}",
    response_model=schemas.ScheduleSlotResponse,
)
async def patch_slot_prod(
    schedule_code: str,
    slot_code: str,
    data: schemas.ScheduleSlotUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Patch schedule slot. RLS: inherited from parent schedule."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_schedule_advertiser(db, schedule_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "modify schedule slot")
    return await service.update_schedule_slot(db, schedule_code, slot_code, data)


@router.delete(
    "/schedules/{schedule_code}/items/{slot_code}",
    response_model=schemas.ScheduleSlotResponse,
)
async def disable_slot_prod(
    schedule_code: str,
    slot_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("scheduling.manage")),
):
    """Disable schedule slot. RLS: inherited from parent schedule."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_schedule_advertiser(db, schedule_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "disable schedule slot")
    return await service.disable_schedule_slot(db, schedule_code, slot_code)
