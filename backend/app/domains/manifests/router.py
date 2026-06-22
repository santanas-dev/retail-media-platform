"""Manifest generation router — test KSO minimal."""

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity.models import User
from app.domains.manifests import schemas, service

router = APIRouter(prefix="/api/manifests", tags=["manifests"])

# ═══════════════════════════════════════════════════════════════════
#  Test KSO endpoints
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/test-kso/generate",
    response_model=schemas.ManifestResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def generate_manifest(
    data: schemas.ManifestGenerateRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.publish")),
):
    mf = await service.generate_manifest(db, data, current_user.id)
    return schemas.ManifestResponse(**service._safe_response(mf))


@router.get(
    "/test-kso",
    response_model=list[schemas.ManifestListItem],
)
async def list_manifests(
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    manifests = await service.list_manifests(db)
    return [
        schemas.ManifestListItem(
            manifest_code=m.manifest_code,
            device_code=m.device_code,
            placement_code=m.placement_code,
            campaign_code=m.campaign_code,
            status=m.status,
            schema_version=m.schema_version,
            item_count=m.item_count,
            generated_at=m.generated_at,
            published_at=m.published_at,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in manifests
    ]


@router.get(
    "/test-kso/{manifest_code}",
    response_model=schemas.ManifestResponse,
)
async def get_manifest(
    manifest_code: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    mf = await service.get_manifest(db, manifest_code)
    return schemas.ManifestResponse(**service._safe_response(mf))


@router.post(
    "/test-kso/{manifest_code}/publish",
    response_model=schemas.ManifestResponse,
)
async def publish_manifest(
    manifest_code: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.publish")),
):
    mf = await service.publish_manifest(db, manifest_code, current_user.id)
    return schemas.ManifestResponse(**service._safe_response(mf))
