"""Manifest & Publication Core: FastAPI router — 11 endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity.models import User
from app.domains.publications import schemas, service

router = APIRouter(prefix="/api", tags=["publications"])


# ═══════════════════════════════════════════════════════════════════
#  Publication Batches
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/publication-batches",
    response_model=schemas.PublicationBatchResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_batch(
    data: schemas.PublicationBatchCreate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.manage")),
):
    return await service.create_batch(db, data, current_user.id)


@router.get(
    "/publication-batches",
    response_model=list[schemas.PublicationBatchListResponse],
)
async def list_batches(
    db=Depends(get_db),
    schedule_run_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_permission("publications.read")),
):
    return await service.list_batches(
        db,
        schedule_run_id=UUID(schedule_run_id) if schedule_run_id else None,
        campaign_id=UUID(campaign_id) if campaign_id else None,
        status=status,
    )


@router.get(
    "/publication-batches/{batch_id}",
    response_model=schemas.PublicationBatchResponse,
)
async def get_batch(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    return await service.get_batch(db, UUID(batch_id))


# ═══════════════════════════════════════════════════════════════════
#  Batch lifecycle actions
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/publication-batches/{batch_id}/request-approval",
    response_model=schemas.PublicationBatchResponse,
)
async def request_batch_approval(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.manage")),
):
    """Request approval for a draft batch → creates ApprovalRequest (39.3.4)."""
    batch = await service.get_batch(db, UUID(batch_id))
    return await service.request_batch_approval(db, batch, current_user.id)


@router.post(
    "/publication-batches/{batch_id}/generate",
    response_model=schemas.PublicationBatchResponse,
)
async def generate_manifests(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.manage")),
):
    batch = await service.get_batch(db, UUID(batch_id))
    return await service.generate_manifests(db, batch, current_user.id)


@router.post(
    "/publication-batches/{batch_id}/approve",
    response_model=schemas.PublicationBatchResponse,
)
async def approve_batch(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.approve")),
):
    batch = await service.get_batch(db, UUID(batch_id))
    return await service.approve_batch(db, batch, current_user.id)


@router.post(
    "/publication-batches/{batch_id}/publish",
    response_model=schemas.PublicationBatchResponse,
)
async def publish_batch(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.publish")),
):
    batch = await service.get_batch(db, UUID(batch_id))
    return await service.publish_batch(db, batch, current_user.id)


@router.post(
    "/publication-batches/{batch_id}/cancel",
    response_model=schemas.PublicationBatchResponse,
)
async def cancel_batch(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = await service.get_batch(db, UUID(batch_id))
    return await service.cancel_batch(
        db, batch, current_user.id, current_user.permissions,
    )


# ═══════════════════════════════════════════════════════════════════
#  Targets, Manifests, Events
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/publication-batches/{batch_id}/targets",
    response_model=list[schemas.PublicationTargetResponse],
)
async def get_targets(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    return await service.get_targets(db, UUID(batch_id))


@router.get(
    "/publication-batches/{batch_id}/manifests",
    response_model=list[schemas.ManifestVersionListResponse],
)
async def get_manifests(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    return await service.get_manifests(db, UUID(batch_id))


@router.get(
    "/manifest-versions/{version_id}",
    response_model=schemas.ManifestVersionResponse,
)
async def get_manifest_version(
    version_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    return await service.get_manifest_version(db, UUID(version_id))


@router.get(
    "/publication-batches/{batch_id}/events",
    response_model=list[schemas.PublicationEventResponse],
)
async def get_events(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    return await service.get_events(db, UUID(batch_id))
