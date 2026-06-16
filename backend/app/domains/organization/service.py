"""
Organization domain: business logic for branches, clusters, stores.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.organization import models, schemas


# ── Branches ──────────────────────────────────────────────────────────────

async def list_branches(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> list[models.Branch]:
    result = await db.execute(
        select(models.Branch)
        .order_by(models.Branch.name)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_branch(db: AsyncSession, branch_id: UUID) -> models.Branch:
    result = await db.execute(
        select(models.Branch).where(models.Branch.id == branch_id)
    )
    branch = result.scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    return branch


async def create_branch(
    db: AsyncSession, data: schemas.BranchCreate
) -> models.Branch:
    branch = models.Branch(**data.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return branch


async def update_branch(
    db: AsyncSession, branch_id: UUID, data: schemas.BranchUpdate
) -> models.Branch:
    branch = await get_branch(db, branch_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(branch, key, value)
    branch.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(branch)
    return branch


# ── Clusters ──────────────────────────────────────────────────────────────

async def list_clusters(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    branch_id: UUID | None = None,
) -> list[models.Cluster]:
    stmt = select(models.Cluster).order_by(models.Cluster.name)
    if branch_id:
        stmt = stmt.where(models.Cluster.branch_id == branch_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_cluster(db: AsyncSession, cluster_id: UUID) -> models.Cluster:
    result = await db.execute(
        select(models.Cluster).where(models.Cluster.id == cluster_id)
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    return cluster


async def create_cluster(
    db: AsyncSession, data: schemas.ClusterCreate
) -> models.Cluster:
    # Verify branch exists
    result = await db.execute(
        select(models.Branch).where(models.Branch.id == data.branch_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    cluster = models.Cluster(**data.model_dump())
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return cluster


async def update_cluster(
    db: AsyncSession, cluster_id: UUID, data: schemas.ClusterUpdate
) -> models.Cluster:
    cluster = await get_cluster(db, cluster_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(cluster, key, value)
    cluster.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(cluster)
    return cluster


# ── Stores ────────────────────────────────────────────────────────────────

async def list_stores(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    cluster_id: UUID | None = None,
    branch_id: UUID | None = None,
) -> list[models.Store]:
    stmt = select(models.Store).order_by(models.Store.name)
    if cluster_id:
        stmt = stmt.where(models.Store.cluster_id == cluster_id)
    if branch_id:
        stmt = stmt.join(models.Cluster).where(models.Cluster.branch_id == branch_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())


async def get_store(db: AsyncSession, store_id: UUID) -> models.Store:
    result = await db.execute(
        select(models.Store).where(models.Store.id == store_id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return store


async def create_store(
    db: AsyncSession, data: schemas.StoreCreate
) -> models.Store:
    # Verify cluster exists
    result = await db.execute(
        select(models.Cluster).where(models.Cluster.id == data.cluster_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    store = models.Store(**data.model_dump())
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return store


async def update_store(
    db: AsyncSession, store_id: UUID, data: schemas.StoreUpdate
) -> models.Store:
    store = await get_store(db, store_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(store, key, value)
    store.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(store)
    return store
