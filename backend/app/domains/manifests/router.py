"""Manifest generation router.

Routes definition order is critical:
  - Literal paths (e.g. /test-kso) BEFORE parameterized paths (/{manifest_code}).
  - This prevents /{manifest_code} from matching "test-kso" as a code.
"""

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity.models import User
from app.domains.manifests import schemas, service

router = APIRouter(prefix="/api/manifests", tags=["manifests"])

# ═══════════════════════════════════════════════════════════════════
#  Legacy Test KSO endpoints (must precede /{manifest_code})
# ═══════════════════════════════════════════════════════════════════


@router.post(
    "/test-kso/generate",
    response_model=schemas.ManifestResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def generate_manifest_legacy(
    data: schemas.ManifestGenerateRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.publish")),
):
    """Legacy: generate manifest. Delegates to unified builder."""
    mf = await service.generate_manifest(db, data, current_user.id)
    return schemas.ManifestResponse(**service._safe_response(mf))


@router.get(
    "/test-kso",
    response_model=list[schemas.ManifestListItem],
)
async def list_manifests_legacy(
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    """Legacy: list manifests. Delegates to same service as production."""
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
async def get_manifest_legacy(
    manifest_code: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    """Legacy: get manifest by code."""
    mf = await service.get_manifest(db, manifest_code)
    return schemas.ManifestResponse(**service._safe_response(mf))


@router.post(
    "/test-kso/{manifest_code}/publish",
    response_model=schemas.ManifestResponse,
)
async def publish_manifest_legacy(
    manifest_code: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.publish")),
):
    """Legacy: publish manifest. Delegates to same service as production."""
    mf = await service.publish_manifest(db, manifest_code, current_user.id)
    return schemas.ManifestResponse(**service._safe_response(mf))


# ═══════════════════════════════════════════════════════════════════
#  Production endpoints (39.2.3.1, 39.3.2)
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "",
    response_model=list[schemas.ManifestListItem],
)
async def list_manifests_prod(
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    """List all manifests — safe projection, no UUIDs (production)."""
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


@router.post(
    "",
    response_model=schemas.ManifestResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def generate_manifest_prod(
    data: schemas.ManifestGenerateRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.publish")),
):
    """Generate manifest from approved placement — production path.

    Uses the unified build_manifest_from_placement() builder.
    """
    mf = await service.generate_manifest(db, data, current_user.id)
    return schemas.ManifestResponse(**service._safe_response(mf))


@router.get(
    "/{manifest_code}",
    response_model=schemas.ManifestResponse,
)
async def get_manifest_prod(
    manifest_code: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.read")),
):
    """Get a single manifest by code — safe projection (production)."""
    mf = await service.get_manifest(db, manifest_code)
    return schemas.ManifestResponse(**service._safe_response(mf))


@router.post(
    "/{manifest_code}/publish",
    response_model=schemas.ManifestResponse,
)
async def publish_manifest_prod(
    manifest_code: str,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("publications.publish")),
):
    """Publish a generated manifest — production path (idempotent)."""
    mf = await service.publish_manifest(db, manifest_code, current_user.id)
    return schemas.ManifestResponse(**service._safe_response(mf))
