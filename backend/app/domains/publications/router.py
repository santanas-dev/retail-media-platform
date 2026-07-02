"""Manifest & Publication Core: FastAPI router — 11 endpoints.
RLS: advertiser scope enforced via batch.campaign_id → campaign.advertiser_id.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permission
from app.core.config import get_settings
from app.domains.identity.models import User
from app.domains.identity.rls import resolve_user_scope_context, assert_object_in_advertiser_scope
from app.domains.publications import schemas, service
from app.domains.audit.service import audit_business_action

router = APIRouter(prefix="/api", tags=["publications"])


async def _resolve_batch_advertiser(db: AsyncSession, batch_id: UUID):
    """Resolve batch → campaign → advertiser_id. Returns None if not found."""
    from sqlalchemy import select as sa_select
    from app.domains.publications.models import PublicationBatch
    from app.domains.campaigns.models import Campaign
    result = await db.execute(
        sa_select(Campaign.advertiser_id)
        .join(PublicationBatch, PublicationBatch.campaign_id == Campaign.id)
        .where(PublicationBatch.id == batch_id)
    )
    row = result.first()
    return row[0] if row else None


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
    """Create publication batch. campaign_id is derived server-side from schedule_run."""
    result = await service.create_batch(db, data, current_user.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="publication_batch.create", target_type="publication_batch",
        target_ref=str(result.id),
    )
    return result


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
    """List batches. RLS: filtered to advertiser scope."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    batches = await service.list_batches(
        db,
        schedule_run_id=UUID(schedule_run_id) if schedule_run_id else None,
        campaign_id=UUID(campaign_id) if campaign_id else None,
        status=status,
    )
    if scope_ctx.is_advertiser_scoped:
        from uuid import UUID as _UUID
        filtered = []
        for b in batches:
            bid = b.id if isinstance(b.id, _UUID) else _UUID(str(b.id))
            adv_id = await _resolve_batch_advertiser(db, bid)
            if adv_id and adv_id in scope_ctx.advertiser_ids:
                filtered.append(b)
        return filtered
    return batches


@router.get(
    "/publication-batches/{batch_id}",
    response_model=schemas.PublicationBatchResponse,
)
async def get_batch(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    """Get batch. RLS: advertiser scope enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_batch_advertiser(db, UUID(batch_id))
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view publication batch")
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
    """Request approval. RLS: advertiser scope enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_batch_advertiser(db, UUID(batch_id))
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "request approval")
    batch = await service.get_batch(db, UUID(batch_id))
    result = await service.request_batch_approval(db, batch, current_user.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="publication_batch.request_approval", target_type="publication_batch",
        target_ref=batch_id,
    )
    return result


@router.post(
    "/publication-batches/{batch_id}/generate",
    response_model=schemas.PublicationBatchResponse,
)
async def generate_manifests(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.manage")),
):
    """Generate manifests. RLS: advertiser scope enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_batch_advertiser(db, UUID(batch_id))
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "generate manifests")
    batch = await service.get_batch(db, UUID(batch_id))
    result = await service.generate_manifests(db, batch, current_user.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="publication_batch.generate_manifests", target_type="publication_batch",
        target_ref=batch_id,
    )
    return result


@router.post(
    "/publication-batches/{batch_id}/approve",
    response_model=schemas.PublicationBatchResponse,
)
async def approve_batch(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.approve")),
):
    """Approve batch. RLS: advertiser scope enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_batch_advertiser(db, UUID(batch_id))
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "approve batch")
    batch = await service.get_batch(db, UUID(batch_id))
    result = await service.approve_batch(db, batch, current_user.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="publication_batch.approve", target_type="publication_batch",
        target_ref=batch_id,
    )
    return result


@router.post(
    "/publication-batches/{batch_id}/publish",
    response_model=schemas.PublishBatchResult,
)
async def publish_batch(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.publish")),
):
    """Publish batch. RLS: advertiser scope enforced.

    BACKEND.1.1 — gated by ENABLE_REAL_PUBLICATION feature flag.
    When OFF: returns 422 (real publication disabled).
    When ON: existing publish_batch() executes, but GeneratedManifest is NOT created.
    """
    settings = get_settings()
    if not settings.ENABLE_REAL_PUBLICATION:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "real_publication_disabled",
                "message": "Real publication is disabled by feature flag "
                           "(ENABLE_REAL_PUBLICATION=false). "
                           "Set ENABLE_REAL_PUBLICATION=true to enable.",
                "batch_id": batch_id,
            },
        )

    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_batch_advertiser(db, UUID(batch_id))
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "publish batch")
    batch = await service.get_batch(db, UUID(batch_id))
    result = await service.publish_batch(db, batch, current_user.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="publication_batch.publish", target_type="publication_batch",
        target_ref=batch_id,
    )
    return schemas.PublishBatchResult(
        batch=schemas.PublicationBatchResponse.model_validate(result),
        generated_manifest_created=False,
        next_step="generated_manifest_write_disabled",
    )


@router.post(
    "/publication-batches/{batch_id}/cancel",
    response_model=schemas.PublicationBatchResponse,
)
async def cancel_batch(
    batch_id: str,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel batch. RLS: advertiser scope NOT enforced (any authorized user can cancel)."""
    batch = await service.get_batch(db, UUID(batch_id))
    result = await service.cancel_batch(
        db, batch, current_user.id, current_user.permissions,
    )
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="publication_batch.cancel", target_type="publication_batch",
        target_ref=batch_id,
    )
    return result

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
    """Get batch targets. RLS: inherited from parent batch."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_batch_advertiser(db, UUID(batch_id))
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view targets")
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
    """Get batch manifests. RLS: inherited from parent batch."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_batch_advertiser(db, UUID(batch_id))
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view manifests")
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
    """Get manifest version. RLS: advertiser scope enforced via batch chain."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    from sqlalchemy import select as sa_select
    from app.domains.publications.models import ManifestVersion, PublicationBatch
    from app.domains.campaigns.models import Campaign
    result = await db.execute(
        sa_select(Campaign.advertiser_id)
        .join(PublicationBatch, PublicationBatch.campaign_id == Campaign.id)
        .join(ManifestVersion, ManifestVersion.publication_batch_id == PublicationBatch.id)
        .where(ManifestVersion.id == UUID(version_id))
    )
    row = result.first()
    adv_id = row[0] if row else None
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view manifest version")
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
    """Get batch events. RLS: inherited from parent batch."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_batch_advertiser(db, UUID(batch_id))
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view events")
    return await service.get_events(db, UUID(batch_id))
