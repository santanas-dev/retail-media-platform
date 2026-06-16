"""Advertisers & Commercial Base domain: FastAPI router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.advertisers import schemas, service

router = APIRouter(prefix="/api", tags=["advertisers"])


# ── Advertisers ────────────────────────────────────────────────────────────

@router.get("/advertisers", response_model=list[schemas.AdvertiserResponse])
async def list_advertisers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("advertisers.read")),
):
    return await service.list_advertisers(db, skip, limit)


@router.post(
    "/advertisers",
    response_model=schemas.AdvertiserResponse,
    status_code=201,
)
async def create_advertiser(
    body: schemas.AdvertiserCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("advertisers.manage")),
):
    return await service.create_advertiser(db, body)


@router.get("/advertisers/{advertiser_id}", response_model=schemas.AdvertiserResponse)
async def get_advertiser(
    advertiser_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("advertisers.read")),
):
    return await service.get_advertiser(db, advertiser_id)


@router.put("/advertisers/{advertiser_id}", response_model=schemas.AdvertiserResponse)
async def update_advertiser(
    advertiser_id: UUID,
    body: schemas.AdvertiserUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("advertisers.manage")),
):
    return await service.update_advertiser(db, advertiser_id, body)


# ── Brands ─────────────────────────────────────────────────────────────────

@router.get("/brands", response_model=list[schemas.BrandResponse])
async def list_brands(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    advertiser_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("brands.read")),
):
    return await service.list_brands(db, skip, limit, advertiser_id)


@router.post("/brands", response_model=schemas.BrandResponse, status_code=201)
async def create_brand(
    body: schemas.BrandCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("brands.manage")),
):
    return await service.create_brand(db, body)


@router.get("/brands/{brand_id}", response_model=schemas.BrandResponse)
async def get_brand(
    brand_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("brands.read")),
):
    return await service.get_brand(db, brand_id)


@router.put("/brands/{brand_id}", response_model=schemas.BrandResponse)
async def update_brand(
    brand_id: UUID,
    body: schemas.BrandUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("brands.manage")),
):
    return await service.update_brand(db, brand_id, body)


# ── Contracts ──────────────────────────────────────────────────────────────

@router.get("/contracts", response_model=list[schemas.ContractResponse])
async def list_contracts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    advertiser_id: UUID | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("contracts.read")),
):
    return await service.list_contracts(db, skip, limit, advertiser_id, status)


@router.post("/contracts", response_model=schemas.ContractResponse, status_code=201)
async def create_contract(
    body: schemas.ContractCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("contracts.manage")),
):
    return await service.create_contract(db, body)


@router.get("/contracts/{contract_id}", response_model=schemas.ContractResponse)
async def get_contract(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("contracts.read")),
):
    return await service.get_contract(db, contract_id)


@router.put("/contracts/{contract_id}", response_model=schemas.ContractResponse)
async def update_contract(
    contract_id: UUID,
    body: schemas.ContractUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("contracts.manage")),
):
    return await service.update_contract(db, contract_id, body)


# ── Orders ─────────────────────────────────────────────────────────────────

@router.get("/orders", response_model=list[schemas.OrderResponse])
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    advertiser_id: UUID | None = Query(None),
    brand_id: UUID | None = Query(None),
    contract_id: UUID | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("orders.read")),
):
    return await service.list_orders(
        db, skip, limit, advertiser_id, brand_id, contract_id, status
    )


@router.post("/orders", response_model=schemas.OrderResponse, status_code=201)
async def create_order(
    body: schemas.OrderCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("orders.manage")),
):
    return await service.create_order(db, body)


@router.get("/orders/{order_id}", response_model=schemas.OrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("orders.read")),
):
    return await service.get_order(db, order_id)


@router.put("/orders/{order_id}", response_model=schemas.OrderResponse)
async def update_order(
    order_id: UUID,
    body: schemas.OrderUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("orders.manage")),
):
    return await service.update_order(db, order_id, body)
