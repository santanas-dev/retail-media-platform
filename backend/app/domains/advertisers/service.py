"""Advertisers & Commercial Base domain: business logic."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.advertisers import models, schemas


# ── Helpers ────────────────────────────────────────────────────────────────

async def _check_advertiser_exists(db: AsyncSession, advertiser_id: UUID) -> models.Advertiser:
    result = await db.execute(
        select(models.Advertiser).where(models.Advertiser.id == advertiser_id)
    )
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Advertiser not found"
        )
    return advertiser


# ── Advertisers ────────────────────────────────────────────────────────────

async def list_advertisers(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> list[models.Advertiser]:
    result = await db.execute(
        select(models.Advertiser)
        .order_by(models.Advertiser.name)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_advertiser(db: AsyncSession, advertiser_id: UUID) -> models.Advertiser:
    return await _check_advertiser_exists(db, advertiser_id)


async def create_advertiser(
    db: AsyncSession, data: schemas.AdvertiserCreate
) -> models.Advertiser:
    advertiser = models.Advertiser(**data.model_dump())
    db.add(advertiser)
    await db.commit()
    await db.refresh(advertiser)
    return advertiser


async def update_advertiser(
    db: AsyncSession, advertiser_id: UUID, data: schemas.AdvertiserUpdate
) -> models.Advertiser:
    advertiser = await _check_advertiser_exists(db, advertiser_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(advertiser, key, value)
    advertiser.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(advertiser)
    return advertiser


# ── Brands ─────────────────────────────────────────────────────────────────

async def list_brands(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    advertiser_id: UUID | None = None,
) -> list[models.Brand]:
    stmt = select(models.Brand).order_by(models.Brand.name)
    if advertiser_id:
        stmt = stmt.where(models.Brand.advertiser_id == advertiser_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_brand(db: AsyncSession, brand_id: UUID) -> models.Brand:
    result = await db.execute(
        select(models.Brand).where(models.Brand.id == brand_id)
    )
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


async def create_brand(
    db: AsyncSession, data: schemas.BrandCreate
) -> models.Brand:
    await _check_advertiser_exists(db, data.advertiser_id)
    brand = models.Brand(**data.model_dump())
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return brand


async def update_brand(
    db: AsyncSession, brand_id: UUID, data: schemas.BrandUpdate
) -> models.Brand:
    brand = await get_brand(db, brand_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    brand.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(brand)
    return brand


# ── Contracts ──────────────────────────────────────────────────────────────

async def list_contracts(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    advertiser_id: UUID | None = None,
    status: str | None = None,
) -> list[models.Contract]:
    stmt = select(models.Contract).order_by(models.Contract.created_at.desc())
    if advertiser_id:
        stmt = stmt.where(models.Contract.advertiser_id == advertiser_id)
    if status:
        stmt = stmt.where(models.Contract.status == status)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_contract(db: AsyncSession, contract_id: UUID) -> models.Contract:
    result = await db.execute(
        select(models.Contract).where(models.Contract.id == contract_id)
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found"
        )
    return contract


async def create_contract(
    db: AsyncSession, data: schemas.ContractCreate
) -> models.Contract:
    await _check_advertiser_exists(db, data.advertiser_id)
    contract = models.Contract(**data.model_dump())
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def update_contract(
    db: AsyncSession, contract_id: UUID, data: schemas.ContractUpdate
) -> models.Contract:
    contract = await get_contract(db, contract_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(contract, key, value)
    contract.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(contract)
    return contract


# ── Orders ─────────────────────────────────────────────────────────────────

async def list_orders(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    advertiser_id: UUID | None = None,
    brand_id: UUID | None = None,
    contract_id: UUID | None = None,
    status: str | None = None,
) -> list[models.Order]:
    stmt = select(models.Order).order_by(models.Order.created_at.desc())
    if advertiser_id:
        stmt = stmt.where(models.Order.advertiser_id == advertiser_id)
    if brand_id:
        stmt = stmt.where(models.Order.brand_id == brand_id)
    if contract_id:
        stmt = stmt.where(models.Order.contract_id == contract_id)
    if status:
        stmt = stmt.where(models.Order.status == status)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_order(db: AsyncSession, order_id: UUID) -> models.Order:
    result = await db.execute(
        select(models.Order).where(models.Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


async def create_order(
    db: AsyncSession, data: schemas.OrderCreate
) -> models.Order:
    advertiser = await _check_advertiser_exists(db, data.advertiser_id)

    # If brand_id is set, verify brand belongs to this advertiser
    if data.brand_id:
        brand = await db.get(models.Brand, data.brand_id)
        if not brand:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found"
            )
        if brand.advertiser_id != data.advertiser_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Brand does not belong to this advertiser",
            )

    # If contract_id is set, verify contract belongs to this advertiser
    if data.contract_id:
        contract = await db.get(models.Contract, data.contract_id)
        if not contract:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found"
            )
        if contract.advertiser_id != data.advertiser_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contract does not belong to this advertiser",
            )

    order = models.Order(**data.model_dump())
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def update_order(
    db: AsyncSession, order_id: UUID, data: schemas.OrderUpdate
) -> models.Order:
    order = await get_order(db, order_id)

    # If brand_id is being changed, verify it belongs to order's advertiser
    if data.brand_id is not None:
        brand = await db.get(models.Brand, data.brand_id)
        if not brand:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found"
            )
        if brand.advertiser_id != order.advertiser_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Brand does not belong to this advertiser",
            )

    # If contract_id is being changed, verify it belongs to order's advertiser
    if data.contract_id is not None:
        contract = await db.get(models.Contract, data.contract_id)
        if not contract:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found"
            )
        if contract.advertiser_id != order.advertiser_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contract does not belong to this advertiser",
            )

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(order, key, value)
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)
    return order
