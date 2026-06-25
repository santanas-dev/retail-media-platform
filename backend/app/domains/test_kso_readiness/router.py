"""Test KSO Readiness router — read-only, no auth required (TEST_ONLY)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.domains.test_kso_readiness.schemas import ReadinessStatus
from app.domains.test_kso_readiness import service

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
    in manifest, campaign/placement/creative chain, PoP events.

    TEST_ONLY — no auth. Never exposes secrets.
    """
    if not device_code or not device_code.strip():
        raise HTTPException(status_code=400, detail="device_code is required")

    return await service.build_readiness_summary(db, device_code.strip())
