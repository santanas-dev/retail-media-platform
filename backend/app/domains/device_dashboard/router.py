"""Device Dashboard: FastAPI router — aggregation endpoint for pilot dashboard.

Endpoint:
  GET /api/device-dashboard

Permission:
  devices.gateway.read (reuse existing, safe read permission)

Safe projection: NO secrets, NO tokens, NO raw UUIDs, NO backend URLs.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.device_dashboard import schemas, service
from app.domains.identity import models as identity_models

router = APIRouter(prefix="/api", tags=["device-dashboard"])


@router.get(
    "/device-dashboard",
    response_model=list[schemas.DeviceDashboardItem],
)
async def device_dashboard(
    keyword: Optional[str] = Query(
        None, max_length=100,
        description="Search by device_code or device_name (ILIKE %keyword%)",
    ),
    channel_code: Optional[str] = Query(
        None, max_length=50, description="Filter by channel code",
    ),
    store_code: Optional[str] = Query(
        None, max_length=50, description="Filter by store code",
    ),
    readiness_badge: Optional[str] = Query(
        None, max_length=20,
        description="Filter: ready / warning / blocked / unknown",
    ),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: identity_models.User = Depends(require_permission("devices.gateway.read")),
):
    """Aggregated device dashboard for pilot operator.

    Crosses KsoDevice + GatewayDevice + credentials + sessions + heartbeats
    + manifest state + PoP events into one safe projection.

    Requires ``devices.gateway.read`` permission.

    Response contract (per device):
      - device_code, store_code, store_name
      - kso_status, gateway_status
      - heartbeat (status, age_seconds, app_version, cache_items_count, manifest_hash)
      - sidecar_version, sidecar_status (deferred)
      - credential (status, type, expires_at)
      - session (active_count, last_used_at)
      - manifest (status, hash, last_applied_at)
      - media_cache (items, missing, failed, health)
      - pop (last_pop_at, events_count)
      - readiness_badge (ready / warning / blocked / unknown)
      - readiness_reasons (safe strings only)

    NEVER RETURNED: raw UUIDs, device_secret, secret_hash, access_token_hash,
    tokens, full backend URL, IP, MAC, serial, filesystem paths, password,
    barcode, receipt, payment, fiscal, customer, card, personal data.
    """
    return await service.get_device_dashboard(
        db,
        keyword=keyword,
        channel_code=channel_code,
        store_code=store_code,
        readiness_badge=readiness_badge,
        limit=limit,
        offset=offset,
    )
