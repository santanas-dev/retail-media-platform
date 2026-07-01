"""Emergency Management service — G.1 contracts only.

All functions are read-only / dry-run. No real stop, no DB writes,
no API, no portal, no production switch.
"""

from __future__ import annotations

from typing import Any

from app.domains.emergency.schemas import (
    EmergencyActionCreate,
    EmergencyActionPreview,
    EmergencyActionRecord,
    EmergencyActionResult,
    EmergencyActionStatus,
    EmergencyActionType,
    EmergencyIssue,
    EmergencyMessageContent,
    EmergencyPriority,
    EmergencyTarget,
)


# ═══════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════

def build_emergency_issue(
    code: str,
    severity: str = "warning",
    message: str = "",
    field: str | None = None,
    details: dict[str, Any] | None = None,
) -> EmergencyIssue:
    """Build a structured EmergencyIssue."""
    return EmergencyIssue(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        message=message,
        field=field,
        details=details,
    )


def validate_emergency_action(
    request: EmergencyActionCreate,
) -> list[EmergencyIssue]:
    """Validate an emergency action request.

    Returns list of EmergencyIssue (empty = valid).
    Does NOT write to DB. Does NOT execute anything.
    """
    issues: list[EmergencyIssue] = []

    # action_type required
    if not request.action_type:
        issues.append(build_emergency_issue(
            "missing_action_type", "error",
            "action_type is required", field="action_type",
        ))

    # reason required
    if not request.reason or not request.reason.strip():
        issues.append(build_emergency_issue(
            "missing_reason", "error",
            "reason is required", field="reason",
        ))

    # priority required
    if not request.priority:
        issues.append(build_emergency_issue(
            "missing_priority", "error",
            "priority is required", field="priority",
        ))

    # target must not be empty
    if request.target.is_empty:
        issues.append(build_emergency_issue(
            "empty_target", "error",
            "target must specify at least one dimension (channel/store/device/campaign/placement)",
            field="target",
        ))

    # emergency_message requires message content
    if request.action_type == EmergencyActionType.EMERGENCY_MESSAGE:
        if request.message is None:
            issues.append(build_emergency_issue(
                "missing_message_content", "error",
                "emergency_message action requires message content",
                field="message",
            ))
    else:
        # stop actions do not require message — that's fine
        pass

    # date range validation
    if request.starts_at and request.ends_at:
        if request.starts_at > request.ends_at:
            issues.append(build_emergency_issue(
                "invalid_date_range", "error",
                "starts_at must be <= ends_at",
                field="starts_at",
            ))

    # duration validation (on message)
    if request.message and request.message.duration_seconds is not None:
        if request.message.duration_seconds <= 0:
            issues.append(build_emergency_issue(
                "invalid_duration", "error",
                "duration_seconds must be > 0",
                field="message.duration_seconds",
            ))

    # dry_run false forbidden in G.1
    if not request.dry_run:
        issues.append(build_emergency_issue(
            "dry_run_required", "error",
            "dry_run=false is not supported in G.1 — real execution is disabled",
            field="dry_run",
        ))

    # Broad scope warning
    if request.target.is_broad:
        issues.append(build_emergency_issue(
            "broad_emergency_scope", "warning",
            "Target scope is broad (channel/store-level without specific device/campaign). "
            "This will affect many devices.",
            field="target",
        ))

    # Critical priority approval
    if request.priority == EmergencyPriority.CRITICAL:
        if not request.requires_approval:
            issues.append(build_emergency_issue(
                "critical_requires_approval", "warning",
                "Critical priority actions should require approval. "
                "Consider setting requires_approval=True.",
                field="requires_approval",
            ))

    # Resume requires target
    if request.action_type == EmergencyActionType.RESUME:
        # Already validated target.is_empty above — just note it's important
        pass

    return issues


# ═══════════════════════════════════════════════════════════════════════════
# Target resolution (read-only)
# ═══════════════════════════════════════════════════════════════════════════

def resolve_emergency_targets(
    target: EmergencyTarget,
) -> dict[str, Any]:
    """Resolve emergency target to affected dimensions.

    G.1: pure schema-level resolution. No DB queries, no API calls.
    Returns structured dict with count estimates per dimension.

    Does NOT write to DB.
    """
    result: dict[str, Any] = {
        "ok": True,
        "dimensions": target.affected_dimensions,
        "affected_channels": 0,
        "affected_stores": 0,
        "affected_devices": 0,
        "affected_campaigns": 0,
        "affected_placements": 0,
        "warnings": [],
        "errors": [],
    }

    if target.is_empty:
        result["ok"] = False
        result["errors"].append(build_emergency_issue(
            "empty_target", "error",
            "Cannot resolve empty target",
            field="target",
        ).model_dump())
        return result

    # In G.1, we can only provide estimates — real resolution requires DB
    # Count 1 per specific ID/code, 0 for broad dimensions
    dims = target.affected_dimensions
    if "channel" in dims:
        result["affected_channels"] = 1
    if "store" in dims:
        result["affected_stores"] = 1
    if "device" in dims:
        result["affected_devices"] = max(
            1 if target.gateway_device_id or target.physical_device_id or target.device_code else 0,
            0,
        )
    if "campaign" in dims:
        result["affected_campaigns"] = 1
    if "placement" in dims:
        result["affected_placements"] = 1

    result["warnings"].append(build_emergency_issue(
        "target_resolution_estimated", "info",
        "Target resolution in G.1 is schema-level only. "
        "Real device/campaign counts require DB queries (deferred to G.2+).",
        field="target",
    ).model_dump())

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Preview (dry-run)
# ═══════════════════════════════════════════════════════════════════════════

async def preview_emergency_action(
    db: Any,  # AsyncSession — not used in G.1, placeholder for G.2+
    request: EmergencyActionCreate,
    current_user: Any = None,
) -> EmergencyActionPreview:
    """Preview an emergency action — full dry-run.

    Validates the request, resolves targets, returns preview.
    Does NOT execute anything. Does NOT write to DB.

    G.1: dry_run is always True. Real execution disabled.
    """
    issues = validate_emergency_action(request)
    warnings = [i for i in issues if i.severity != "error"]
    errors = [i for i in issues if i.severity == "error"]

    target_info = resolve_emergency_targets(request.target)

    # Merge target resolution warnings
    for w in target_info.get("warnings", []):
        if isinstance(w, dict):
            warnings.append(EmergencyIssue(**w))
        else:
            warnings.append(w)
    for e in target_info.get("errors", []):
        if isinstance(e, dict):
            errors.append(EmergencyIssue(**e))
        else:
            errors.append(e)

    return EmergencyActionPreview(
        ok=len(errors) == 0,
        dry_run=True,
        action_type=request.action_type,
        target=request.target,
        affected_channels=target_info.get("affected_channels", 0),
        affected_stores=target_info.get("affected_stores", 0),
        affected_devices=target_info.get("affected_devices", 0),
        affected_campaigns=target_info.get("affected_campaigns", 0),
        affected_placements=target_info.get("affected_placements", 0),
        warnings=warnings,
        errors=errors,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Simulators (always dry-run in G.1)
# ═══════════════════════════════════════════════════════════════════════════

async def simulate_emergency_stop(
    db: Any,
    request: EmergencyActionCreate,
    current_user: Any = None,
) -> EmergencyActionResult:
    """Simulate an emergency stop — always dry-run in G.1.

    Does NOT stop any real campaigns/devices.
    Does NOT write to DB.
    Does NOT change Campaign/Placement/Publication.
    """
    preview = await preview_emergency_action(db, request, current_user)

    # Stop-specific validation
    stop_types = {
        EmergencyActionType.STOP_CAMPAIGN,
        EmergencyActionType.STOP_PLACEMENT,
        EmergencyActionType.STOP_CHANNEL,
        EmergencyActionType.STOP_STORE,
        EmergencyActionType.STOP_DEVICE,
    }
    if request.action_type not in stop_types:
        preview.errors.append(build_emergency_issue(
            "invalid_action_for_stop", "error",
            f"Action type '{request.action_type.value}' is not a stop action",
            field="action_type",
        ))
        preview.ok = False

    return EmergencyActionResult(
        ok=preview.ok,
        action_id=None,  # No action created in G.1
        status=EmergencyActionStatus.DRAFT,
        dry_run=True,
        action_type=request.action_type,
        target=request.target,
        message=request.message,
        warnings=preview.warnings,
        errors=preview.errors,
    )


async def simulate_emergency_message(
    db: Any,
    request: EmergencyActionCreate,
    current_user: Any = None,
) -> EmergencyActionResult:
    """Simulate an emergency message broadcast — always dry-run in G.1.

    Does NOT send any real messages to devices.
    Does NOT write to DB.
    Does NOT change Device Gateway.
    """
    preview = await preview_emergency_action(db, request, current_user)

    if request.action_type != EmergencyActionType.EMERGENCY_MESSAGE:
        preview.errors.append(build_emergency_issue(
            "invalid_action_for_message", "error",
            f"Action type '{request.action_type.value}' is not an emergency message",
            field="action_type",
        ))
        preview.ok = False

    if request.message is None:
        preview.errors.append(build_emergency_issue(
            "missing_message_content", "error",
            "Emergency message requires content",
            field="message",
        ))
        preview.ok = False

    return EmergencyActionResult(
        ok=preview.ok,
        action_id=None,
        status=EmergencyActionStatus.DRAFT,
        dry_run=True,
        action_type=request.action_type,
        target=request.target,
        message=request.message,
        warnings=preview.warnings,
        errors=preview.errors,
    )
