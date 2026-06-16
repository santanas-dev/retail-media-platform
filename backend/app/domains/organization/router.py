"""
Organization domain: FastAPI router — branches, clusters, stores.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.organization import schemas, service

router = APIRouter(prefix="/api", tags=["organization"])


# ── Branches ──────────────────────────────────────────────────────────────

@router.get("/branches", response_model=list[schemas.BranchResponse])
async def list_branches(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.read")),
):
    return await service.list_branches(db, skip, limit)


@router.post("/branches", response_model=schemas.BranchResponse, status_code=201)
async def create_branch(
    body: schemas.BranchCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.manage")),
):
    return await service.create_branch(db, body)


@router.get("/branches/{branch_id}", response_model=schemas.BranchResponse)
async def get_branch(
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.read")),
):
    return await service.get_branch(db, branch_id)


@router.put("/branches/{branch_id}", response_model=schemas.BranchResponse)
async def update_branch(
    branch_id: UUID,
    body: schemas.BranchUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.manage")),
):
    return await service.update_branch(db, branch_id, body)


# ── Clusters ──────────────────────────────────────────────────────────────

@router.get("/clusters", response_model=list[schemas.ClusterResponse])
async def list_clusters(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    branch_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.read")),
):
    return await service.list_clusters(db, skip, limit, branch_id)


@router.post("/clusters", response_model=schemas.ClusterResponse, status_code=201)
async def create_cluster(
    body: schemas.ClusterCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.manage")),
):
    return await service.create_cluster(db, body)


@router.get("/clusters/{cluster_id}", response_model=schemas.ClusterResponse)
async def get_cluster(
    cluster_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.read")),
):
    return await service.get_cluster(db, cluster_id)


@router.put("/clusters/{cluster_id}", response_model=schemas.ClusterResponse)
async def update_cluster(
    cluster_id: UUID,
    body: schemas.ClusterUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.manage")),
):
    return await service.update_cluster(db, cluster_id, body)


# ── Stores ────────────────────────────────────────────────────────────────

@router.get("/stores", response_model=list[schemas.StoreResponse])
async def list_stores(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    cluster_id: UUID | None = Query(None),
    branch_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.read")),
):
    return await service.list_stores(db, skip, limit, cluster_id, branch_id)


@router.post("/stores", response_model=schemas.StoreResponse, status_code=201)
async def create_store(
    body: schemas.StoreCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.manage")),
):
    return await service.create_store(db, body)


@router.get("/stores/{store_id}", response_model=schemas.StoreResponse)
async def get_store(
    store_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.read")),
):
    return await service.get_store(db, store_id)


@router.put("/stores/{store_id}", response_model=schemas.StoreResponse)
async def update_store(
    store_id: UUID,
    body: schemas.StoreUpdate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("organization.manage")),
):
    return await service.update_store(db, store_id, body)
