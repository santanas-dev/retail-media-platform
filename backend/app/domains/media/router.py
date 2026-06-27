"""Media Library domain: FastAPI router.

12 endpoints:
  GET    /api/creatives
  POST   /api/creatives
  GET    /api/creatives/{id}
  PUT    /api/creatives/{id}           (media.manage OR media.approve)
  POST   /api/creatives/{id}/versions/upload
  GET    /api/creatives/{id}/versions
  GET    /api/creative-versions/{id}
  GET    /api/renditions
  POST   /api/renditions
  GET    /api/renditions/{id}
  POST   /api/renditions/{id}/validate
  GET    /api/renditions/{id}/validations
"""

from typing import Callable

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, require_permission
from app.domains.identity import models as identity_models
from app.domains.identity.rls import (
    resolve_user_scope_context,
    assert_object_in_advertiser_scope,
)
from app.domains.media import schemas, service
from app.domains.audit.service import audit_business_action

router = APIRouter(prefix="/api", tags=["media"])



# ── Creatives ──────────────────────────────────────────────────────────────

@router.get("/creatives", response_model=list[schemas.CreativeResponse])
async def list_creatives(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    advertiser_id: UUID | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("media.read")),
):
    scope_ctx = await resolve_user_scope_context(db, current_user)
    creatives = await service.list_creatives(db, skip, limit, advertiser_id, status, scope_ctx)
    return await _enrich_creatives(db, creatives)


@router.post(
    "/creatives",
    response_model=schemas.CreativeResponse,
    status_code=201,
)
async def create_creative(
    data: schemas.CreativeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("media.manage")),
):
    scope_ctx = await resolve_user_scope_context(db, current_user)
    if data.advertiser_id is not None:
        assert_object_in_advertiser_scope(data.advertiser_id, scope_ctx, "create")
    result = await service.create_creative(db, data, current_user.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="creative.create", target_type="creative",
        target_ref=result.creative_code if hasattr(result, 'creative_code') else str(result.id),
        details={"name": data.name},
    )
    return result


@router.get("/creatives/{creative_id}", response_model=schemas.CreativeResponse)
async def get_creative(
    creative_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("media.read")),
):
    creative = await service.get_creative(db, creative_id)
    scope_ctx = await resolve_user_scope_context(db, current_user)
    if creative.advertiser_id is not None:
        assert_object_in_advertiser_scope(creative.advertiser_id, scope_ctx, "access")
    return creative


@router.put("/creatives/{creative_id}", response_model=schemas.CreativeResponse)
async def update_creative(
    creative_id: UUID,
    data: schemas.CreativeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(get_current_user),
):
    """Update creative. Requires media.manage OR media.approve.

    If the user only has media.approve, only status changes to
    approved/rejected are allowed."""
    user_perms = set(current_user.permissions)

    if "media.manage" not in user_perms and "media.approve" not in user_perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires media.manage or media.approve",
        )

    # If user only has media.approve (no media.manage), restrict to status-only
    if "media.manage" not in user_perms:
        if data.status not in ("approved", "rejected"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="media.approve only allows status changes to approved/rejected",
            )
        if data.name is not None or data.comment is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="media.approve only allows status changes",
            )
    result = await service.update_creative(db, creative_id, data)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="creative.update", target_type="creative",
        target_ref=str(creative_id),
        details={"status": data.status} if data.status else None,
    )
    return result


# ── Creative Versions ─────────────────────────────────────────────────────

@router.post(
    "/creatives/{creative_id}/versions/upload",
    response_model=schemas.UploadVersionResponse,
    status_code=201,
)
async def upload_version(
    creative_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("media.manage")),
):
    result = await service.upload_version(db, creative_id, file, current_user.id)
    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="creative.upload_version", target_type="creative",
        target_ref=str(creative_id),
    )
    return result


@router.get(
    "/creatives/{creative_id}/versions",
    response_model=list[schemas.CreativeVersionResponse],
)
async def list_versions(
    creative_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("media.read")),
):
    return await service.list_versions(db, creative_id)


@router.get(
    "/creative-versions/{version_id}",
    response_model=schemas.CreativeVersionResponse,
)
async def get_version(
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("media.read")),
):
    return await service.get_version(db, version_id)


# ── Renditions ────────────────────────────────────────────────────────────

@router.get("/renditions", response_model=list[schemas.RenditionResponse])
async def list_renditions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    creative_version_id: UUID | None = Query(None),
    channel_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("media.read")),
):
    return await service.list_renditions(db, skip, limit, creative_version_id, channel_id)


@router.post(
    "/renditions",
    response_model=schemas.RenditionResponse,
    status_code=201,
)
async def create_rendition(
    data: schemas.RenditionCreate,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("media.manage")),
):
    return await service.create_rendition(db, data)


@router.get("/renditions/{rendition_id}", response_model=schemas.RenditionResponse)
async def get_rendition(
    rendition_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("media.read")),
):
    return await service.get_rendition(db, rendition_id)


@router.post(
    "/renditions/{rendition_id}/validate",
    response_model=list[schemas.ValidationResponse],
)
async def validate_rendition(
    rendition_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("media.manage")),
):
    return await service.validate_rendition(db, rendition_id, current_user.id)


@router.get(
    "/renditions/{rendition_id}/validations",
    response_model=list[schemas.ValidationResponse],
)
async def list_validations(
    rendition_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("media.read")),
):
    return await service.list_validations(db, rendition_id)


# ── Combined Creative Upload (Step 37.3) ──────────────────────────────────

@router.post(
    "/creatives/upload",
    response_model=schemas.CreativeUploadResponse,
    status_code=201,
)
async def upload_creative(
    creative_code: str = Form(...),
    name: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(
        require_permission("media.manage"),
    ),
):
    """Combined creative create + upload for one-KSO pilot (Step 37.3).

    Accepts multipart/form-data: creative_code, name, file.
    Validates: MIME type (png/jpeg/mp4), image dimensions (1440×1080),
    max 50 MB, audio forbidden.

    Stores in MinIO via existing storage abstraction.
    Response NEVER contains file_path, sha256, or storage_ref.
    """
    data = schemas.CreativeUploadRequest(
        creative_code=creative_code,
        name=name,
    )
    result = await service.upload_creative_combined(db, data, file, current_user.id)
    # Assert advertiser scope on the created creative
    scope_ctx = await resolve_user_scope_context(db, current_user)
    creative = await service.get_creative_by_code(db, data.creative_code)
    if creative is not None and creative.advertiser_id is not None:
        assert_object_in_advertiser_scope(creative.advertiser_id, scope_ctx, "upload")
    return result



async def _enrich_creatives(db: AsyncSession, creatives: list) -> list[schemas.CreativeResponse]:
    """Enrich creative list with advertiser_name and version metadata."""
    from sqlalchemy import select
    from app.domains.advertisers.models import Advertiser

    # Collect unique advertiser IDs
    adv_ids = {c.advertiser_id for c in creatives if c.advertiser_id}
    advertisers = {}
    if adv_ids:
        result = await db.execute(
            select(Advertiser).where(Advertiser.id.in_(adv_ids))
        )
        advertisers = {a.id: a.name for a in result.scalars().all()}

    # Build enriched responses
    enriched = []
    for c in creatives:
        latest = None
        if c.versions:
            latest = max(c.versions, key=lambda v: v.version)

        enriched.append(schemas.CreativeResponse(
            id=c.id,
            advertiser_id=c.advertiser_id,
            advertiser_code=advertisers.get(c.advertiser_id) if c.advertiser_id else None,
            advertiser_name=advertisers.get(c.advertiser_id) if c.advertiser_id else None,
            brand_id=c.brand_id,
            creative_code=c.creative_code,
            name=c.name,
            status=c.status,
            comment=c.comment,
            content_type=latest.mime_type if latest else None,
            width=latest.width if latest else None,
            height=latest.height if latest else None,
            duration_ms=int(latest.duration_seconds * 1000) if (latest and latest.duration_seconds) else None,
            file_size_bytes=latest.file_size if latest else None,
            current_version=latest.version if latest else None,
            created_by=c.created_by,
            created_at=c.created_at,
            updated_at=c.updated_at,
        ))
    return enriched

# ── By-Code Access & Archive (41.1) ──────────────────────────────────────

@router.get("/creatives/by-code/{creative_code}", response_model=schemas.CreativeResponse)
async def get_creative_by_code_ep(
    creative_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("media.read")),
):
    creative = await service.get_creative_by_code(db, creative_code)
    if not creative:
        raise HTTPException(status_code=404, detail="Creative not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    if creative.advertiser_id is not None:
        assert_object_in_advertiser_scope(creative.advertiser_id, scope_ctx, "access")
    return creative


@router.post("/creatives/by-code/{creative_code}/archive")
async def archive_creative_by_code(
    creative_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("media.manage")),
):
    creative = await service.get_creative_by_code(db, creative_code)
    if not creative:
        raise HTTPException(status_code=404, detail="Creative not found")
    scope_ctx = await resolve_user_scope_context(db, current_user)
    if creative.advertiser_id is not None:
        assert_object_in_advertiser_scope(creative.advertiser_id, scope_ctx, "archive")

    creative.status = "archived"
    await db.commit()
    await db.refresh(creative)

    await audit_business_action(
        db, actor_user_id=str(current_user.id),
        action="creative.archive", target_type="creative",
        target_ref=creative_code,
        details={"name": creative.name},
    )
    return {"ok": True, "creative_code": creative_code, "status": "archived"}


# ── Safe Creative Preview (42.2) ──────────────────────────────────────────

from fastapi.responses import StreamingResponse
from minio import Minio
from minio.error import S3Error
from app.core.config import get_settings


def _get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


@router.get("/creatives/by-code/{creative_code}/preview")
async def preview_creative_by_code(
    creative_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("media.read")),
):
    """Safe creative preview — streams image file with no storage internals exposed.

    - Auth: media.read
    - RLS: advertiser scope enforced (404 if foreign)
    - Archived/rejected: 404 (no preview for non-active)
    - Images only in this step: image/png, image/jpeg
    - Video: 415 Unsupported Media Type (deferred)
    - Response headers: Content-Type, Content-Length, Cache-Control only
    - NO signed URLs, NO MinIO paths, NO storage keys in response
    """
    from app.domains.media.models import Creative, CreativeVersion

    # Look up creative by code
    creative = await service.get_creative_by_code(db, creative_code)
    if not creative:
        raise HTTPException(status_code=404, detail="Creative not found")

    # RLS check
    scope_ctx = await resolve_user_scope_context(db, current_user)
    if creative.advertiser_id is not None:
        assert_object_in_advertiser_scope(creative.advertiser_id, scope_ctx, "preview")

    # Status gate: no preview for archived/rejected
    if creative.status in ("archived", "rejected"):
        raise HTTPException(status_code=404, detail="Preview not available")

    # Find latest version with a file
    from sqlalchemy import select
    cv_result = await db.execute(
        select(CreativeVersion)
        .where(CreativeVersion.creative_id == creative.id)
        .order_by(CreativeVersion.version.desc())
        .limit(1)
    )
    version = cv_result.scalar_one_or_none()
    if not version or not version.file_path:
        raise HTTPException(status_code=404, detail="No media file uploaded")

    # Only images in this step
    if version.mime_type not in ("image/png", "image/jpeg"):
        raise HTTPException(
            status_code=415,
            detail="Preview supports images only (PNG, JPEG). Video preview deferred.",
        )

    # Validate object key format
    if not version.file_path or ".." in version.file_path or "\n" in version.file_path:
        raise HTTPException(status_code=403, detail="Media path invalid")

    # Stream from MinIO
    settings = get_settings()
    try:
        minio_client = _get_minio_client()
        obj_info = minio_client.stat_object(settings.MINIO_BUCKET, version.file_path)
        content_length = obj_info.size
        response_obj = minio_client.get_object(settings.MINIO_BUCKET, version.file_path)
    except S3Error:
        raise HTTPException(status_code=404, detail="Media not available")

    def _close():
        try:
            response_obj.close()
            response_obj.release_conn()
        except Exception:
            pass

    return StreamingResponse(
        response_obj.stream(amt=64 * 1024),
        status_code=200,
        media_type=version.mime_type,
        headers={
            "Content-Length": str(content_length),
            "Content-Type": version.mime_type,
            "Content-Disposition": "inline",
            "Cache-Control": "private, max-age=3600",
        },
        background=_close,
    )
