"""Test KSO Readiness router — read-only readiness + idempotent seed, no auth (TEST_ONLY)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.domains.test_kso_readiness.schemas import ReadinessStatus, SeedRequest, SeedSummary
from app.domains.test_kso_readiness import seed as seed_module, service

router = APIRouter(prefix="/api/test-kso", tags=["test-kso-readiness"])


@router.get(
    "/readiness",
    response_model=ReadinessStatus,
    summary="Test KSO E2E readiness",
    description="Safe read-only readiness check for a test KSO device. "
    "No auth required (TEST_ONLY). Never returns secrets, URLs, tokens, or UUIDs.",
)
async def get_readiness(
    device_code: str = Query(..., min_length=1, max_length=64),
    db: AsyncSession = Depends(get_db),
) -> ReadinessStatus:
    """Return safe readiness summary for a test KSO device.

    Checks: device registration, published manifest, creative_code/mediaRef
    in manifest, campaign/placement/creative chain, PoP events,
    publication status, remaining steps.

    TEST_ONLY — no auth. Never exposes secrets.
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
    "No auth required (TEST_ONLY). Never returns UUIDs, secrets, or paths.",
)
async def seed_test_chain(
    body: SeedRequest = SeedRequest(),
    db: AsyncSession = Depends(get_db),
) -> SeedSummary:
    """Seed a complete synthetic one-KSO test chain.

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
