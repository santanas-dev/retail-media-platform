"""Test KSO Readiness router — read-only readiness + idempotent seed.

DEV-ONLY / TEST-KSO endpoints. Require authentication (any valid user).
Never returns secrets, URLs, tokens, or UUIDs.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.domains.identity import models as identity_models
from app.domains.test_kso_readiness.schemas import ReadinessStatus, SeedRequest, SeedSummary
from app.domains.test_kso_readiness import seed as seed_module, service

router = APIRouter(prefix="/api/test-kso", tags=["test-kso-readiness"])


@router.get(
    "/readiness",
    response_model=ReadinessStatus,
    summary="Test KSO E2E readiness",
    description="Safe read-only readiness check for a test KSO device. "
    "Requires authentication. Never returns secrets, URLs, tokens, or UUIDs.",
)
async def get_readiness(
    device_code: str = Query(..., min_length=1, max_length=64),
    db: AsyncSession = Depends(get_db),
    _current_user: identity_models.User = Depends(get_current_user),
) -> ReadinessStatus:
    """Return safe readiness summary for a test KSO device.

    DEV-ONLY / TEST-KSO. Requires authentication.
    Checks: device registration, published manifest, creative_code/mediaRef
    in manifest, campaign/placement/creative chain, PoP events,
    publication status, remaining steps.

    Never exposes secrets.
    """
    if not device_code or not device_code.strip():
        raise HTTPException(status_code=400, detail="device_code is required")

    return await service.build_readiness_summary(db, device_code.strip())


@router.post(
    "/seed",
    response_model=SeedSummary,
    status_code=201,
    summary="Seed synthetic test KSO chain",
    description="Create a complete synthetic one-KSO test chain (idempotent). "
    "Requires authentication. Never returns UUIDs, secrets, or paths.",
)
async def seed_test_chain(
    body: SeedRequest = SeedRequest(),
    db: AsyncSession = Depends(get_db),
    _current_user: identity_models.User = Depends(get_current_user),
) -> SeedSummary:
    """Seed a complete synthetic one-KSO test chain.

    DEV-ONLY / TEST-KSO. Requires authentication.

    Creates: User → Branch → Cluster → Store → KsoDevice →
    Campaign → Creative (with version) → CampaignCreative →
    KsoPlacement → GeneratedManifest (published).

    Idempotent: repeated calls with same codes do not create duplicates.
    All data is synthetic. Never stores or returns secrets.
    """
    return await seed_module.seed_test_kso_chain(
        db,
        device_code=body.device_code,
        creative_code=body.creative_code,
        campaign_code=body.campaign_code,
        placement_code=body.placement_code,
        manifest_code=body.manifest_code,
    )
