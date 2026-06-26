"""Manifest generation router.
RLS: advertiser scope enforced via placement_code → campaign_code → campaign.advertiser_id.

Routes definition order is critical:
  - Literal paths (e.g. /test-kso) BEFORE parameterized paths (/{manifest_code}).
  - This prevents /{manifest_code} from matching "test-kso" as a code.
"""

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity.models import User
from app.domains.identity.rls import resolve_user_scope_context, assert_object_in_advertiser_scope
from app.domains.manifests import schemas, service
from app.domains.audit.service import audit_business_action

router = APIRouter(prefix="/api/manifests", tags=["manifests"])


async def _resolve_manifest_advertiser(db, manifest_code: str):
    """Resolve manifest → placement → campaign_code → campaign.advertiser_id."""
    from sqlalchemy import select as sa_select
    from app.domains.manifests.models import GeneratedManifest
    from app.domains.scheduling.models import KsoPlacement
    from app.domains.campaigns.models import Campaign
    result = await db.execute(
        sa_select(Campaign.advertiser_id)
        .join(KsoPlacement, KsoPlacement.campaign_code == Campaign.campaign_code)
        .join(GeneratedManifest, GeneratedManifest.placement_code == KsoPlacement.placement_code)
        .where(GeneratedManifest.manifest_code == manifest_code)
    )
    row = result.first()
    return row[0] if row else None


async def _resolve_placement_advertiser(db, placement_code: str):
    """Resolve placement → campaign_code → campaign.advertiser_id."""
    from sqlalchemy import select as sa_select
    from app.domains.scheduling.models import KsoPlacement
    from app.domains.campaigns.models import Campaign
    result = await db.execute(
        sa_select(Campaign.advertiser_id)
        .join(KsoPlacement, KsoPlacement.campaign_code == Campaign.campaign_code)
        .where(KsoPlacement.placement_code == placement_code)
    )
    row = result.first()
    return row[0] if row else None


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
    """Legacy: generate manifest. RLS: placement_code must be in advertiser scope."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_placement_advertiser(db, data.placement_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "generate manifest")
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
    """Legacy: list manifests. RLS: filtered to advertiser scope."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    manifests = await service.list_manifests(db)
    if scope_ctx.is_advertiser_scoped:
        filtered = []
        for m in manifests:
            adv_id = await _resolve_manifest_advertiser(db, str(m.manifest_code))
            if adv_id and adv_id in scope_ctx.advertiser_ids:
                filtered.append(m)
        return [
            schemas.ManifestListItem(
                manifest_code=str(m.manifest_code),
                device_code=str(m.device_code),
                placement_code=str(m.placement_code),
                campaign_code=str(m.campaign_code),
                status=str(m.status),
                schema_version=int(m.schema_version),
                item_count=int(m.item_count),
                generated_at=m.generated_at,
                published_at=m.published_at,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in filtered
        ]
    return [
        schemas.ManifestListItem(
            manifest_code=str(m.manifest_code),
            device_code=str(m.device_code),
            placement_code=str(m.placement_code),
            campaign_code=str(m.campaign_code),
            status=str(m.status),
            schema_version=int(m.schema_version),
            item_count=int(m.item_count),
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
    """Legacy: get manifest by code. RLS enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_manifest_advertiser(db, manifest_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view manifest")
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
    """Legacy: publish manifest. RLS enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_manifest_advertiser(db, manifest_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "publish manifest")
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
    """List all manifests. RLS: filtered to advertiser scope."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    manifests = await service.list_manifests(db)
    if scope_ctx.is_advertiser_scoped:
        filtered = []
        for m in manifests:
            adv_id = await _resolve_manifest_advertiser(db, str(m.manifest_code))
            if adv_id and adv_id in scope_ctx.advertiser_ids:
                filtered.append(m)
        return [
            schemas.ManifestListItem(
                manifest_code=str(m.manifest_code),
                device_code=str(m.device_code),
                placement_code=str(m.placement_code),
                campaign_code=str(m.campaign_code),
                status=str(m.status),
                schema_version=int(m.schema_version),
                item_count=int(m.item_count),
                generated_at=m.generated_at,
                published_at=m.published_at,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in filtered
        ]
    return [
        schemas.ManifestListItem(
            manifest_code=str(m.manifest_code),
            device_code=str(m.device_code),
            placement_code=str(m.placement_code),
            campaign_code=str(m.campaign_code),
            status=str(m.status),
            schema_version=int(m.schema_version),
            item_count=int(m.item_count),
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
    """Generate manifest from approved placement. RLS: placement_code must be in scope."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_placement_advertiser(db, data.placement_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "generate manifest")
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
    """Get a single manifest by code. RLS enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_manifest_advertiser(db, manifest_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "view manifest")
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
    """Publish a generated manifest. RLS enforced."""
    scope_ctx = await resolve_user_scope_context(db, current_user)
    adv_id = await _resolve_manifest_advertiser(db, manifest_code)
    if adv_id is not None:
        assert_object_in_advertiser_scope(adv_id, scope_ctx, "publish manifest")
    mf = await service.publish_manifest(db, manifest_code, current_user.id)
    return schemas.ManifestResponse(**service._safe_response(mf))
