"""Device Operations: health + alert rules API router."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import get_current_user, get_db, require_permission
from app.domains.device_operations import schemas, service
from app.domains.identity.models import User

router = APIRouter(prefix="/api/device-operations", tags=["device-operations"])


# ═══════════════════════════════════════════════════════════════════════
#  Health endpoints (Step 15)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/overview", response_model=schemas.OverviewResponse)
async def get_overview(
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_overview(
        db, date_from=date_from, date_to=date_to,
        channel_id=channel_id, store_id=store_id,
    )


@router.get("/devices", response_model=list[schemas.DeviceHealthItem])
async def get_devices(
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    device_status: Optional[str] = Query(None),
    health_status: Optional[str] = Query(None),
    problem_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_devices(
        db, date_from=date_from, date_to=date_to,
        channel_id=channel_id, store_id=store_id,
        device_status=device_status, health_status=health_status,
        problem_type=problem_type, limit=limit, offset=offset,
    )


@router.get("/devices/{device_id}", response_model=schemas.DeviceHealthDetail)
async def get_device_detail(
    device_id: UUID,
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    result = await service.get_device_detail(
        db, device_id, date_from=date_from, date_to=date_to,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    return result


@router.get("/stores", response_model=list[schemas.StoreHealthItem])
async def get_stores_health(
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_stores_health(
        db, date_from=date_from, date_to=date_to,
        channel_id=channel_id, store_id=store_id,
    )


@router.get("/channels", response_model=list[schemas.ChannelHealthItem])
async def get_channels_health(
    db=Depends(get_db),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_channels_health(
        db, date_from=date_from, date_to=date_to,
        channel_id=channel_id, store_id=store_id,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Alert Rules endpoints (Step 16)
# ═══════════════════════════════════════════════════════════════════════


# ── Rules ──────────────────────────────────────────────────────────────


@router.get("/alert-rules", response_model=list[schemas.AlertRuleResponse])
async def list_alert_rules(
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_alert_rules(db)


@router.post("/alert-rules", response_model=schemas.AlertRuleResponse, status_code=201)
async def create_alert_rule(
    data: schemas.AlertRuleCreate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.manage")),
):
    return await service.create_alert_rule(db, data.model_dump())


@router.put("/alert-rules/{rule_id}", response_model=schemas.AlertRuleResponse)
async def update_alert_rule(
    rule_id: UUID,
    data: schemas.AlertRuleUpdate,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.manage")),
):
    return await service.update_alert_rule(db, rule_id, data.model_dump(exclude_none=True))


@router.post("/alert-rules/{rule_id}/enable", response_model=schemas.AlertRuleResponse)
async def enable_alert_rule(
    rule_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.manage")),
):
    return await service.set_rule_enabled(db, rule_id, True)


@router.post("/alert-rules/{rule_id}/disable", response_model=schemas.AlertRuleResponse)
async def disable_alert_rule(
    rule_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.manage")),
):
    return await service.set_rule_enabled(db, rule_id, False)


# ── Alerts ─────────────────────────────────────────────────────────────


@router.get("/alerts", response_model=list[schemas.AlertResponse])
async def list_alerts(
    db=Depends(get_db),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    gateway_device_id: Optional[UUID] = Query(None),
    store_id: Optional[UUID] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_alerts(
        db, status=status, severity=severity, alert_type=alert_type,
        gateway_device_id=gateway_device_id, store_id=store_id,
        channel_id=channel_id, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )


@router.get("/alerts/{alert_id}", response_model=schemas.AlertDetailResponse)
async def get_alert_detail(
    alert_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    alert, events = await service.get_alert_detail(db, alert_id)
    result = schemas.AlertResponse.model_validate(alert).model_dump()
    result["events"] = [
        schemas.AlertEventResponse.model_validate(e).model_dump() for e in events
    ]
    return result


@router.get("/alerts/{alert_id}/events", response_model=list[schemas.AlertEventResponse])
async def get_alert_events(
    alert_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_alert_events(db, alert_id)


@router.post("/alerts/{alert_id}/acknowledge", response_model=schemas.AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    data: schemas.AlertAcknowledgeRequest = None,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.manage")),
):
    return await service.acknowledge_alert(
        db, alert_id, current_user.id,
        message=data.message if data else None,
    )


@router.post("/alerts/{alert_id}/resolve", response_model=schemas.AlertResponse)
async def resolve_alert(
    alert_id: UUID,
    data: schemas.AlertResolveRequest = None,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.manage")),
):
    return await service.resolve_alert(
        db, alert_id, current_user.id,
        message=data.message if data else None,
    )


# ── Evaluate ───────────────────────────────────────────────────────────


@router.post("/alerts/evaluate", response_model=schemas.EvaluateResponse)
async def evaluate_alerts(
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.manage")),
):
    return await service.evaluate_alerts_with_run(db, current_user.id)


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation Run History endpoints (Step 17)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/alert-evaluations", response_model=list[schemas.EvaluationRunResponse])
async def list_evaluation_runs(
    db=Depends(get_db),
    status: Optional[str] = Query(None),
    trigger_type: Optional[str] = Query(None),
    triggered_by: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from must be before or equal to date_to",
        )
    return await service.get_evaluation_runs(
        db, status=status, trigger_type=trigger_type, triggered_by=triggered_by,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )


@router.get("/alert-evaluations/{run_id}", response_model=schemas.EvaluationRunDetailResponse)
async def get_evaluation_run_detail(
    run_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    run, rules = await service.get_evaluation_run_detail(db, run_id)
    result = schemas.EvaluationRunResponse.model_validate(run).model_dump()
    result["rule_results"] = [
        schemas.EvaluationRuleResultResponse.model_validate(r).model_dump()
        for r in rules
    ]
    return result


@router.get(
    "/alert-evaluations/{run_id}/rules",
    response_model=list[schemas.EvaluationRuleResultResponse],
)
async def get_evaluation_run_rules(
    run_id: UUID,
    db=Depends(get_db),
    current_user: User = Depends(require_permission("devices.gateway.read")),
):
    return await service.get_evaluation_run_rules(db, run_id)
