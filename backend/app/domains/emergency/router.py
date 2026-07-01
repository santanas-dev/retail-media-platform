"""Emergency API — read-only / dry-run endpoints.

G.3: preview + simulate only. No execute/activate/approve/cancel.
All endpoints require emergency.read permission.

Endpoints:
  GET  /api/emergency/capabilities   — list action types, statuses, priorities
  POST /api/emergency/preview         — preview emergency action
  POST /api/emergency/simulate-stop   — simulate stop/resume
  POST /api/emergency/simulate-message — simulate emergency message
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.domains.audit.service import audit_business_action
from app.domains.emergency.schemas import (
    EmergencyActionCreate,
    EmergencyActionPreview,
    EmergencyActionResult,
    EmergencyActionStatus,
    EmergencyActionType,
    EmergencyPriority,
)
from app.domains.emergency.service import (
    preview_emergency_action,
    simulate_emergency_stop,
    simulate_emergency_message,
    validate_no_secrets_in_emergency_payload,
)
from app.domains.identity import models as identity_models

router = APIRouter(prefix="/api/emergency", tags=["emergency"])


async def _audit(db: AsyncSession, user: identity_models.User, action: str, result_summary: str = ""):
    """Fire-and-forget audit for emergency actions."""
    await audit_business_action(
        db,
        actor_user_id=str(user.id),
        action=action,
        target_type="emergency",
        target_ref="dry-run",
        details={"result_summary": result_summary},
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Capabilities
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/capabilities")
async def emergency_capabilities(
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("emergency.read")),
):
    """List available emergency action types, statuses, and priorities.

    Requires emergency.read permission.
    """
    result = {
        "ok": True,
        "dry_run_only": True,
        "action_types": [t.value for t in EmergencyActionType],
        "statuses": [s.value for s in EmergencyActionStatus],
        "priorities": [p.value for p in EmergencyPriority],
    }
    await _audit(db, current_user, "emergency.capabilities.viewed")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. Preview
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/preview", response_model=EmergencyActionPreview)
async def emergency_preview(
    body: EmergencyActionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("emergency.read")),
) -> EmergencyActionPreview:
    """Preview an emergency action — dry-run only.

    Requires emergency.read permission.
    No real execution. No DB writes.
    """
    result = await preview_emergency_action(db, body, current_user)

    sec = validate_no_secrets_in_emergency_payload(result.model_dump())
    if sec:
        result.errors.extend(sec)
        result.ok = False

    await _audit(db, current_user, "emergency.action.previewed",
                 f"type={body.action_type.value}, affected_devices={result.affected_devices}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 3. Simulate Stop
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/simulate-stop", response_model=EmergencyActionResult)
async def emergency_simulate_stop(
    body: EmergencyActionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("emergency.read")),
) -> EmergencyActionResult:
    """Simulate an emergency stop/resume — dry-run only.

    Requires emergency.read permission.
    No real stop. No DB writes. No Campaign/Placement changes.
    """
    result = await simulate_emergency_stop(db, body, current_user)

    sec = validate_no_secrets_in_emergency_payload(result.model_dump())
    if sec:
        result.errors.extend(sec)
        result.ok = False

    await _audit(db, current_user, "emergency.stop.simulated",
                 f"type={body.action_type.value}, ok={result.ok}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 4. Simulate Message
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/simulate-message", response_model=EmergencyActionResult)
async def emergency_simulate_message(
    body: EmergencyActionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: identity_models.User = Depends(require_permission("emergency.read")),
) -> EmergencyActionResult:
    """Simulate an emergency message broadcast — dry-run only.

    Requires emergency.read permission.
    No real message sent. No DB writes. No Device Gateway calls.
    """
    result = await simulate_emergency_message(db, body, current_user)

    sec = validate_no_secrets_in_emergency_payload(result.model_dump())
    if sec:
        result.errors.extend(sec)
        result.ok = False

    await _audit(db, current_user, "emergency.message.simulated",
                 f"ok={result.ok}")
    return result
