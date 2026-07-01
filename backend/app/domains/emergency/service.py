"""Emergency Management service — G.2 implementation.

Enhanced target resolution with DB queries, no-secrets validation,
rich preview/simulation. All functions are read-only / dry-run.
No real stop, no DB writes, no API, no portal, no production switch.
"""

from __future__ import annotations

from typing import Any

from app.domains.emergency.schemas import (
    EmergencyActionCreate,
    EmergencyActionPreview,
    EmergencyActionResult,
    EmergencyActionStatus,
    EmergencyActionType,
    EmergencyIssue,
    EmergencyPriority,
    EmergencyTarget,
)

# ── Forbidden keys for no-secrets validation ──────────────────────────
FORBIDDEN_EMERGENCY_KEYS = frozenset({
    "password", "passwd", "pwd",
    "secret", "client_secret",
    "token", "access_token", "refresh_token",
    "api_key", "access_key", "private_key",
    "authorization", "bearer",
    "signed_url", "signature",
    "credential", "credentials",
    "cookie", "session", "jwt",
})


# ═══════════════════════════════════════════════════════════════════════════
# Validation helpers
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


def validate_no_secrets_in_emergency_payload(
    payload: dict[str, Any],
    path: str = "",
) -> list[EmergencyIssue]:
    """Recursively check emergency payload for forbidden secret keys/values.

    Does NOT write to DB. Pure validation.
    """
    issues: list[EmergencyIssue] = []
    for key, value in payload.items():
        current = f"{path}.{key}" if path else key
        lower_key = key.lower()
        for fw in FORBIDDEN_EMERGENCY_KEYS:
            if fw in lower_key:
                issues.append(build_emergency_issue(
                    "secret_key_detected", "error",
                    f"Forbidden key '{key}' at '{current}'",
                    field=current,
                    details={"forbidden_word": fw},
                ))
                break
        if isinstance(value, str):
            for fw in FORBIDDEN_EMERGENCY_KEYS:
                if fw in value.lower():
                    issues.append(build_emergency_issue(
                        "secret_value_detected", "error",
                        f"Forbidden value for '{fw}' at '{current}'",
                        field=current,
                        details={"forbidden_word": fw},
                    ))
                    break
        elif isinstance(value, dict):
            issues.extend(
                validate_no_secrets_in_emergency_payload(value, current)
            )
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    issues.extend(
                        validate_no_secrets_in_emergency_payload(
                            item, f"{current}[{i}]"
                        )
                    )
    return issues


def validate_emergency_action(
    request: EmergencyActionCreate,
) -> list[EmergencyIssue]:
    """Validate an emergency action request.

    Returns list of EmergencyIssue (empty = valid).
    Does NOT write to DB. Does NOT execute anything.
    """
    issues: list[EmergencyIssue] = []

    if not request.action_type:
        issues.append(build_emergency_issue(
            "missing_action_type", "error",
            "action_type is required", field="action_type",
        ))

    if not request.reason or not request.reason.strip():
        issues.append(build_emergency_issue(
            "missing_reason", "error",
            "reason is required", field="reason",
        ))

    if not request.priority:
        issues.append(build_emergency_issue(
            "missing_priority", "error",
            "priority is required", field="priority",
        ))

    if request.target.is_empty:
        issues.append(build_emergency_issue(
            "empty_target", "error",
            "target must specify at least one dimension",
            field="target",
        ))

    if request.action_type == EmergencyActionType.EMERGENCY_MESSAGE:
        if request.message is None:
            issues.append(build_emergency_issue(
                "missing_message_content", "error",
                "emergency_message action requires message content",
                field="message",
            ))

    if request.starts_at and request.ends_at:
        if request.starts_at > request.ends_at:
            issues.append(build_emergency_issue(
                "invalid_date_range", "error",
                "starts_at must be <= ends_at",
                field="starts_at",
            ))

    if request.message and request.message.duration_seconds is not None:
        if request.message.duration_seconds <= 0:
            issues.append(build_emergency_issue(
                "invalid_duration", "error",
                "duration_seconds must be > 0",
                field="message.duration_seconds",
            ))

    if not request.dry_run:
        issues.append(build_emergency_issue(
            "dry_run_required", "error",
            "dry_run=false is not supported — real execution is disabled",
            field="dry_run",
        ))

    if request.target.is_broad:
        issues.append(build_emergency_issue(
            "broad_emergency_scope", "warning",
            "Target scope is broad — this will affect many devices.",
            field="target",
        ))

    if request.priority == EmergencyPriority.CRITICAL:
        if not request.requires_approval:
            issues.append(build_emergency_issue(
                "critical_requires_approval", "warning",
                "Critical priority should require approval.",
                field="requires_approval",
            ))

    return issues


# ═══════════════════════════════════════════════════════════════════════════
# Target resolution (read-only, DB queries)
# ═══════════════════════════════════════════════════════════════════════════

def _safe_entity_dict(
    entity_type: str,
    id_val: Any = None,
    code: str | None = None,
    name: str | None = None,
    store_code: str | None = None,
    channel_code: str | None = None,
) -> dict[str, Any]:
    """Build a safe affected-entity dict with no secrets."""
    d: dict[str, Any] = {"entity_type": entity_type}
    if id_val is not None:
        d["id"] = str(id_val) if hasattr(id_val, "__str__") else None
    if code:
        d["code"] = code
    if name:
        d["name"] = name
    if store_code:
        d["store_code"] = store_code
    if channel_code:
        d["channel_code"] = channel_code
    return d


async def resolve_emergency_targets(
    db: Any,  # AsyncSession
    target: EmergencyTarget,
) -> dict[str, Any]:
    """Resolve emergency target to affected dimensions.

    G.2: queries DB via existing models (Channel, PhysicalDevice, Placement,
    Campaign, Store). Returns structured result with counts and safe entity lists.
    Does NOT write to DB.
    """
    from sqlalchemy import select as _select
    from app.domains.channels.models import (
        Channel, PhysicalDevice, Placement,
    )
    from app.domains.campaigns.models import Campaign
    from app.domains.organization.models import Store

    result: dict[str, Any] = {
        "ok": True,
        "dimensions": target.affected_dimensions,
        "affected_channels": 0,
        "affected_stores": 0,
        "affected_devices": 0,
        "affected_campaigns": 0,
        "affected_placements": 0,
        "affected_entities": [],
        "warnings": [],
        "errors": [],
    }

    if target.is_empty:
        result["ok"] = False
        result["errors"].append(build_emergency_issue(
            "empty_target", "error",
            "Cannot resolve empty target", field="target",
        ).model_dump())
        return result

    entities: list[dict[str, Any]] = []

    # ── Channel target ──────────────────────────────────────────────
    if target.channel_id or target.channel_code:
        try:
            stmt = _select(Channel)
            if target.channel_id:
                stmt = stmt.where(Channel.id == target.channel_id)
            elif target.channel_code:
                stmt = stmt.where(Channel.code == target.channel_code)
            ch_result = await db.execute(stmt)
            channel = ch_result.scalar_one_or_none()
            if channel:
                result["affected_channels"] = 1
                entities.append(_safe_entity_dict(
                    "channel", id_val=channel.id, code=channel.code,
                    name=channel.name,
                ))
                # Count devices in this channel
                dev_stmt = _select(PhysicalDevice).join(
                    PhysicalDevice.device_type
                ).where(PhysicalDevice.device_type.has(channel_id=channel.id))
                dev_result = await db.execute(dev_stmt)
                devices = dev_result.scalars().all()
                result["affected_devices"] = len(devices)
                for d in devices:
                    entities.append(_safe_entity_dict(
                        "device", id_val=d.id, code=d.external_code,
                    ))
        except Exception:
            result["warnings"].append(build_emergency_issue(
                "target_resolution_partial", "warning",
                "Could not fully resolve channel target",
                field="target.channel",
            ).model_dump())

    # ── Store target ────────────────────────────────────────────────
    if target.store_id or target.store_code:
        try:
            stmt = _select(Store)
            if target.store_id:
                stmt = stmt.where(Store.id == target.store_id)
            elif target.store_code:
                stmt = stmt.where(Store.code == target.store_code)
            st_result = await db.execute(stmt)
            store = st_result.scalar_one_or_none()
            if store:
                result["affected_stores"] = 1
                entities.append(_safe_entity_dict(
                    "store", id_val=store.id, code=store.code,
                    name=store.name,
                ))
                # Devices in this store
                dev_stmt = _select(PhysicalDevice).where(
                    PhysicalDevice.store_id == store.id
                )
                dev_result = await db.execute(dev_stmt)
                devices = dev_result.scalars().all()
                result["affected_devices"] = max(
                    result["affected_devices"], len(devices)
                )
                for d in devices:
                    entities.append(_safe_entity_dict(
                        "device", id_val=d.id, code=d.external_code,
                        store_code=store.code,
                    ))
        except Exception:
            result["warnings"].append(build_emergency_issue(
                "target_resolution_partial", "warning",
                "Could not fully resolve store target",
                field="target.store",
            ).model_dump())

    # ── Device target ───────────────────────────────────────────────
    if target.physical_device_id or target.gateway_device_id or target.device_code:
        try:
            stmt = _select(PhysicalDevice)
            if target.physical_device_id:
                stmt = stmt.where(PhysicalDevice.id == target.physical_device_id)
            elif target.gateway_device_id:
                # Gateway device lookup — use external_code if available
                stmt = stmt.where(
                    PhysicalDevice.external_code == str(target.gateway_device_id)
                )
            elif target.device_code:
                stmt = stmt.where(
                    PhysicalDevice.external_code == target.device_code
                )
            dev_result = await db.execute(stmt)
            device = dev_result.scalar_one_or_none()
            if device:
                result["affected_devices"] = max(
                    result["affected_devices"], 1
                )
                entities.append(_safe_entity_dict(
                    "device", id_val=device.id, code=device.external_code,
                ))
        except Exception:
            result["warnings"].append(build_emergency_issue(
                "target_resolution_partial", "warning",
                "Could not resolve device target — relation may not exist",
                field="target.device",
            ).model_dump())

    # ── Campaign target ─────────────────────────────────────────────
    if target.campaign_id or target.campaign_code:
        try:
            stmt = _select(Campaign)
            if target.campaign_id:
                stmt = stmt.where(Campaign.id == target.campaign_id)
            elif target.campaign_code:
                stmt = stmt.where(Campaign.code == target.campaign_code)
            cm_result = await db.execute(stmt)
            campaign = cm_result.scalar_one_or_none()
            if campaign:
                result["affected_campaigns"] = 1
                entities.append(_safe_entity_dict(
                    "campaign", id_val=campaign.id, code=campaign.code,
                    name=campaign.name,
                ))
                # Placements for this campaign
                pl_stmt = _select(Placement).where(
                    Placement.campaign_id == campaign.id
                )
                pl_result = await db.execute(pl_stmt)
                placements = pl_result.scalars().all()
                result["affected_placements"] += len(placements)
                for p in placements:
                    entities.append(_safe_entity_dict(
                        "placement", id_val=p.id, code=p.code,
                    ))
        except Exception:
            result["warnings"].append(build_emergency_issue(
                "target_resolution_partial", "warning",
                "Could not resolve campaign target",
                field="target.campaign",
            ).model_dump())

    # ── Placement target ────────────────────────────────────────────
    if target.placement_id or target.placement_code:
        try:
            stmt = _select(Placement)
            if target.placement_id:
                stmt = stmt.where(Placement.id == target.placement_id)
            elif target.placement_code:
                stmt = stmt.where(Placement.code == target.placement_code)
            pl_result = await db.execute(stmt)
            placement = pl_result.scalar_one_or_none()
            if placement:
                result["affected_placements"] = max(
                    result["affected_placements"], 1
                )
                entities.append(_safe_entity_dict(
                    "placement", id_val=placement.id, code=placement.code,
                ))
                if placement.campaign_id:
                    entities.append(_safe_entity_dict(
                        "campaign", id_val=placement.campaign_id,
                    ))
                    result["affected_campaigns"] = max(
                        result["affected_campaigns"], 1
                    )
        except Exception:
            result["warnings"].append(build_emergency_issue(
                "target_resolution_partial", "warning",
                "Could not resolve placement target",
                field="target.placement",
            ).model_dump())

    # ── Display surface target ──────────────────────────────────────
    if target.display_surface_id:
        try:
            from app.domains.channels.models import DisplaySurface
            stmt = _select(DisplaySurface).where(
                DisplaySurface.id == target.display_surface_id
            )
            ds_result = await db.execute(stmt)
            surface = ds_result.scalar_one_or_none()
            if surface:
                entities.append(_safe_entity_dict(
                    "display_surface", id_val=surface.id,
                ))
        except Exception:
            result["warnings"].append(build_emergency_issue(
                "target_resolution_partial", "warning",
                "Could not resolve display_surface target",
                field="target.display_surface",
            ).model_dump())

    result["affected_entities"] = entities
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Preview (dry-run)
# ═══════════════════════════════════════════════════════════════════════════

async def preview_emergency_action(
    db: Any,  # AsyncSession
    request: EmergencyActionCreate,
    current_user: Any = None,
) -> EmergencyActionPreview:
    """Preview an emergency action — full dry-run with DB target resolution.

    Validates, resolves targets against DB, returns preview with affected counts.
    Does NOT execute anything. Does NOT write to DB.
    """
    issues = validate_emergency_action(request)
    warnings = [i for i in issues if i.severity != "error"]
    errors = [i for i in issues if i.severity == "error"]

    target_info = await resolve_emergency_targets(db, request.target)

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

    # No-secrets check on affected entities
    sec_issues = validate_no_secrets_in_emergency_payload(
        {"affected_entities": target_info.get("affected_entities", [])}
    )
    errors.extend(sec_issues)

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
# Simulators (always dry-run)
# ═══════════════════════════════════════════════════════════════════════════

_STOP_TYPES = frozenset({
    EmergencyActionType.STOP_CAMPAIGN,
    EmergencyActionType.STOP_PLACEMENT,
    EmergencyActionType.STOP_CHANNEL,
    EmergencyActionType.STOP_STORE,
    EmergencyActionType.STOP_DEVICE,
    EmergencyActionType.RESUME,
})


async def simulate_emergency_stop(
    db: Any,
    request: EmergencyActionCreate,
    current_user: Any = None,
) -> EmergencyActionResult:
    """Simulate an emergency stop — always dry-run.

    Does NOT stop any real campaigns/devices.
    Does NOT write to DB.
    Does NOT change Campaign/Placement/Publication.
    Does NOT create GeneratedManifest.
    Does NOT call Device Gateway.
    """
    preview = await preview_emergency_action(db, request, current_user)

    if request.action_type not in _STOP_TYPES:
        preview.errors.append(build_emergency_issue(
            "invalid_action_for_stop", "error",
            f"Action type '{request.action_type.value}' is not a stop/resume action",
            field="action_type",
        ))
        preview.ok = False

    # No-secrets on result payload
    result_payload = preview.model_dump()
    sec_issues = validate_no_secrets_in_emergency_payload(result_payload)
    preview.errors.extend(sec_issues)
    if sec_issues:
        preview.ok = False

    summary = (
        f"Dry-run stop: {preview.affected_devices} device(s), "
        f"{preview.affected_campaigns} campaign(s), "
        f"{preview.affected_placements} placement(s) affected. "
        f"Real execution disabled."
    )

    return EmergencyActionResult(
        ok=preview.ok,
        action_id=None,
        status=EmergencyActionStatus.DRAFT,
        dry_run=True,
        action_type=request.action_type,
        target=request.target,
        message=request.message,
        warnings=preview.warnings + [
            build_emergency_issue(
                "real_execution_disabled", "info",
                summary, field="dry_run",
            )
        ],
        errors=preview.errors,
    )


async def simulate_emergency_message(
    db: Any,
    request: EmergencyActionCreate,
    current_user: Any = None,
) -> EmergencyActionResult:
    """Simulate an emergency message broadcast — always dry-run.

    Does NOT send any real messages to devices.
    Does NOT write to DB.
    Does NOT create manifests.
    Does NOT call Device Gateway.
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

    # No-secrets on message content
    if request.message:
        msg_payload = request.message.model_dump()
        sec_issues = validate_no_secrets_in_emergency_payload(msg_payload)
        preview.errors.extend(sec_issues)
        if sec_issues:
            preview.ok = False

    summary = (
        f"Dry-run message: {preview.affected_devices} device(s), "
        f"{preview.affected_stores} store(s) targeted. "
        f"Real broadcast disabled."
    )

    return EmergencyActionResult(
        ok=preview.ok,
        action_id=None,
        status=EmergencyActionStatus.DRAFT,
        dry_run=True,
        action_type=request.action_type,
        target=request.target,
        message=request.message,
        warnings=preview.warnings + [
            build_emergency_issue(
                "real_execution_disabled", "info",
                summary, field="dry_run",
            )
        ],
        errors=preview.errors,
    )
