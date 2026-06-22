"""Proof-of-Play KSO router — test KSO technical validation.

TEST_ONLY — no auth.  Production MUST use device gateway auth / mTLS.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_db
from app.domains.proof_of_play.schemas import (
    KsoPoPIngestRequest,
    KsoPoPIngestResponse,
)
from app.domains.proof_of_play.service import ingest_kso_pop

router = APIRouter(prefix="/api", tags=["proof-of-play-kso"])


# ══════════════════════════════════════════════════════════════════════
# TEST_ONLY: unauthenticated KSO PoP ingest for technical validation.
# Not a production security model.  Production must use device auth /
# gateway credentials / mTLS.
# ══════════════════════════════════════════════════════════════════════

@router.post(
    "/device-gateway/kso/{device_code}/pop",
    response_model=KsoPoPIngestResponse,
)
async def kso_pop_ingest(
    device_code: str,
    data: KsoPoPIngestRequest,
    db=Depends(get_db),
):
    """Ingest PoP event for test KSO technical validation chain.

    TEST_ONLY: unauthenticated endpoint.  NOT production.
    """
    response, error = await ingest_kso_pop(db, device_code, data)
    if error:
        status_map: dict[str, int] = {
            "device_not_found": 404,
            "no_published_manifest": 404,
            "manifest_version_mismatch": 422,
            "manifest_hash_mismatch": 422,
            "unknown_media_ref": 422,
            "placement_not_found": 404,
            "creative_not_in_campaign": 422,
        }
        code = status_map.get(error, 400)
        raise HTTPException(status_code=code, detail=error)

    return response
