"""Inventory & Booking domain: API router."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status

from app.core.deps import get_current_user, require_permission, get_db
from app.domains.identity.models import User
from app.domains.inventory import schemas, service

router = APIRouter(prefix="/api", tags=["Inventory & Booking"])


# ═══════════════════════════════════════════════════════════════════════
#  Inventory Units
# ═══════════════════════════════════════════════════════════════════════


@router.get("/inventory-units", response_model=list[schemas.InventoryUnitResponse])
async def list_inventory_units(
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    is_sellable: Optional[bool] = Query(None),
    logical_carrier_id: Optional[UUID] = Query(None),
    display_surface_id: Optional[UUID] = Query(None),
    db=Depends(get_db),
    current_user: User = Depends(require_permission("inventory.read")),
):
    return await service.list_inventory_units(
        db, channel_id, store_id, status, is_sellable,
        logical_carrier_id, display_surface_id,
    )


@router.post(
    "/inventory-units",
    response_model=schemas.InventoryUnitResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_inventory_unit(
    data: schemas.InventoryUnitCreate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("inventory.manage")),
):
    return await service.create_inventory_unit(db, data)


@router.get("/inventory-units/{unit_id}", response_model=schemas.InventoryUnitResponse)
async def get_inventory_unit(
    unit_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("inventory.read")),
):
    return await service.get_inventory_unit(db, unit_id)


@router.put("/inventory-units/{unit_id}", response_model=schemas.InventoryUnitResponse)
async def update_inventory_unit(
    unit_id: UUID,
    data: schemas.InventoryUnitUpdate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("inventory.manage")),
):
    return await service.update_inventory_unit(db, unit_id, data)


# ═══════════════════════════════════════════════════════════════════════
#  Capacity Rules
# ═══════════════════════════════════════════════════════════════════════


@router.get(
    "/inventory-units/{unit_id}/capacity-rules",
    response_model=list[schemas.CapacityRuleResponse],
)
async def list_capacity_rules(
    unit_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("inventory.read")),
):
    return await service.list_capacity_rules(db, unit_id)


@router.post(
    "/inventory-units/{unit_id}/capacity-rules",
    response_model=schemas.CapacityRuleResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_capacity_rule(
    unit_id: UUID,
    data: schemas.CapacityRuleCreate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("inventory.manage")),
):
    return await service.create_capacity_rule(db, unit_id, data)


@router.put("/capacity-rules/{rule_id}", response_model=schemas.CapacityRuleResponse)
async def update_capacity_rule(
    rule_id: UUID,
    data: schemas.CapacityRuleUpdate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("inventory.manage")),
):
    return await service.update_capacity_rule(db, rule_id, data)


# ═══════════════════════════════════════════════════════════════════════
#  Availability
# ═══════════════════════════════════════════════════════════════════════


@router.post("/inventory/availability", response_model=schemas.AvailabilityResponse)
async def check_availability(
    data: schemas.AvailabilityRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("inventory.read")),
):
    return await service.calculate_availability(db, data)


# ═══════════════════════════════════════════════════════════════════════
#  Bookings
# ═══════════════════════════════════════════════════════════════════════


@router.get("/bookings", response_model=list[schemas.BookingResponse])
async def list_bookings(
    campaign_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.read")),
):
    from datetime import date as date_type
    return await service.list_bookings(
        db, campaign_id, status,
        date_type.fromisoformat(date_from) if date_from else None,
        date_type.fromisoformat(date_to) if date_to else None,
    )


@router.post(
    "/bookings",
    response_model=schemas.BookingResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_booking(
    data: schemas.BookingCreate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.manage")),
):
    return await service.create_booking(db, data, current_user.id)


@router.get("/bookings/{booking_id}", response_model=schemas.BookingResponse)
async def get_booking(
    booking_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.read")),
):
    return await service.get_booking(db, booking_id)


@router.put("/bookings/{booking_id}", response_model=schemas.BookingResponse)
async def update_booking(
    booking_id: UUID,
    data: schemas.BookingUpdate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.manage")),
):
    return await service.update_booking(db, booking_id, data)


@router.post("/bookings/{booking_id}/reserve", response_model=schemas.BookingResponse)
async def reserve_booking(
    booking_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.manage")),
):
    return await service.reserve_booking(db, booking_id)


@router.post("/bookings/{booking_id}/confirm", response_model=schemas.BookingResponse)
async def confirm_booking(
    booking_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.approve")),
):
    return await service.confirm_booking(db, booking_id, current_user.id)


@router.post("/bookings/{booking_id}/cancel", response_model=schemas.BookingResponse)
async def cancel_booking(
    booking_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.manage")),
):
    return await service.cancel_booking(db, booking_id)


@router.get("/bookings/{booking_id}/items", response_model=list[schemas.BookingItemResponse])
async def list_booking_items(
    booking_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.read")),
):
    return await service.list_booking_items(db, booking_id)


@router.put("/bookings/{booking_id}/items", response_model=list[schemas.BookingItemResponse])
async def update_booking_items(
    booking_id: UUID,
    data: schemas.BookingItemsUpdate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("bookings.manage")),
):
    return await service.update_booking_items(db, booking_id, data)
