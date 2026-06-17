"""Device Gateway Foundation: business logic."""

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from jose import jwt
from minio import Minio
from minio.error import S3Error
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.core.config import get_settings
from app.domains.device_gateway import models, schemas
from app.domains.media.storage import _get_client as _get_minio_client
from app.domains.publications.models import (
    ManifestItem, ManifestVersion, PublicationBatch, PublicationTarget,
)

# Forbidden keys (same as publications)
FORBIDDEN_KEYS = frozenset({
    "access_token", "refresh_token", "token", "jwt", "password",
    "secret", "credential", "credentials", "authorization",
    "cookie", "api_key", "private_key", "public_key",
})

HEARTBEAT_STATUSES = frozenset({"ok", "warning", "error"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_no_forbidden_keys(obj: dict, path: str = "") -> list[str]:
    """Recursively check for forbidden keys."""
    hits: list[str] = []
    for key, value in obj.items():
        if key.lower() in FORBIDDEN_KEYS:
            hits.append(f"{path}.{key}" if path else key)
        if isinstance(value, dict):
            hits.extend(_validate_no_forbidden_keys(value, f"{path}.{key}" if path else key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    hits.extend(_validate_no_forbidden_keys(
                        item, f"{path}.{key}[{i}]" if path else f"{key}[{i}]"))
    return hits


async def _log_event(
    db: AsyncSession,
    event_type: str,
    message: str,
    gateway_device_id: UUID | None = None,
    severity: str = "info",
    details_json: dict | None = None,
) -> None:
    event = models.DeviceEvent(
        gateway_device_id=gateway_device_id,
        event_type=event_type,
        severity=severity,
        message=message,
        details_json=details_json or {},
    )
    db.add(event)


# ── Device CRUD ────────────────────────────────────────────────────


async def create_device(
    db: AsyncSession, data: schemas.GatewayDeviceCreate,
) -> models.GatewayDevice:
    """Register a new gateway device."""
    # Check uniqueness
    existing = await db.execute(
        select(models.GatewayDevice).where(
            models.GatewayDevice.device_code == data.device_code
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Device code already exists")

    # Validate linkage
    await _validate_device_linkage(db, data)

    device = models.GatewayDevice(
        device_code=data.device_code,
        device_name=data.device_name,
        physical_device_id=data.physical_device_id,
        logical_carrier_id=data.logical_carrier_id,
        display_surface_id=data.display_surface_id,
        channel_id=data.channel_id,
        store_id=data.store_id,
        status=data.status,
        comment=data.comment,
    )
    db.add(device)
    await db.flush()

    await _log_event(
        db, "device_registered", f"Device {data.device_code} registered",
        device.id,
    )
    await db.commit()
    await db.refresh(device)
    return device


async def list_devices(
    db: AsyncSession,
    status: str | None = None,
    store_id: UUID | None = None,
) -> list[models.GatewayDevice]:
    stmt = select(models.GatewayDevice).order_by(
        models.GatewayDevice.created_at.desc()
    )
    if status:
        stmt = stmt.where(models.GatewayDevice.status == status)
    if store_id:
        stmt = stmt.where(models.GatewayDevice.store_id == store_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_device(db: AsyncSession, device_id: UUID) -> models.GatewayDevice:
    device = await db.get(models.GatewayDevice, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Gateway device not found")
    return device


async def update_device(
    db: AsyncSession, device: models.GatewayDevice, data: schemas.GatewayDeviceUpdate,
) -> models.GatewayDevice:
    """Update device fields and handle status transitions."""
    old_status = device.status

    if data.device_name is not None:
        device.device_name = data.device_name
    if data.comment is not None:
        device.comment = data.comment

    # Handle status transitions
    if data.status is not None and data.status != device.status:
        if data.status == "disabled":
            device.disabled_at = _now()
            device.status = "disabled"
            await _log_event(
                db, "device_disabled", f"Device disabled", device.id, "warning",
            )
        elif data.status == "retired":
            device.disabled_at = _now()
            device.status = "retired"
            await _log_event(
                db, "device_disabled", f"Device retired", device.id, "warning",
            )
        elif data.status in ("active", "pending", "lost"):
            if old_status in ("disabled", "retired"):
                device.disabled_at = None
                await _log_event(
                    db, "device_reactivated",
                    f"Device reactivated from {old_status}", device.id, "info",
                )
            device.status = data.status
        else:
            raise HTTPException(status_code=400, detail="Invalid status")

    # Update linkage fields
    for field in ("physical_device_id", "logical_carrier_id",
                  "display_surface_id", "channel_id", "store_id"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(device, field, val)

    # Re-validate linkage if changed
    await _validate_device_linkage(db, schemas.GatewayDeviceCreate(
        device_code=device.device_code,
        physical_device_id=device.physical_device_id,
        logical_carrier_id=device.logical_carrier_id,
        display_surface_id=device.display_surface_id,
        channel_id=device.channel_id,
        store_id=device.store_id,
    ), exclude_code=True)

    device.updated_at = _now()
    await db.commit()
    await db.refresh(device)
    return device


async def _validate_device_linkage(
    db: AsyncSession, data: schemas.GatewayDeviceCreate, exclude_code: bool = False,
) -> None:
    """Validate physical_device → logical_carrier → display_surface → store chain."""
    # Status requiring linkage
    if data.status not in ("active", "pending", "lost"):
        return  # disabled/retired don't need linkage

    has_link = bool(data.physical_device_id or data.logical_carrier_id or
                    data.display_surface_id)
    if not has_link:
        raise HTTPException(
            status_code=400,
            detail="Active/pending/lost devices must be linked to at least "
                   "physical_device, logical_carrier, or display_surface",
        )

    # Validate display_surface → logical_carrier → physical_device → store chain
    if data.display_surface_id:
        from app.domains.channels.models import DisplaySurface, LogicalCarrier
        ds = await db.get(DisplaySurface, data.display_surface_id)
        if not ds:
            raise HTTPException(status_code=400, detail="Display surface not found")

        if data.logical_carrier_id and ds.logical_carrier_id != data.logical_carrier_id:
            raise HTTPException(
                status_code=400,
                detail="Display surface does not belong to the specified logical carrier",
            )

        if data.logical_carrier_id or ds.logical_carrier_id:
            lc_id = data.logical_carrier_id or ds.logical_carrier_id
            lc = await db.get(LogicalCarrier, lc_id)
            if lc and data.physical_device_id and lc.physical_device_id != data.physical_device_id:
                raise HTTPException(
                    status_code=400,
                    detail="Logical carrier does not belong to the specified physical device",
                )

    # Validate store via physical_device chain if available
    if data.physical_device_id and data.store_id:
        from app.domains.channels.models import PhysicalDevice
        pd = await db.get(PhysicalDevice, data.physical_device_id)
        if pd and pd.store_id != data.store_id:
            raise HTTPException(
                status_code=400,
                detail="Physical device does not belong to the specified store",
            )


# ── Credential management ──────────────────────────────────────────


async def create_credential(
    db: AsyncSession, device: models.GatewayDevice,
) -> schemas.DeviceCredentialCreatedResponse:
    """Issue a new shared_secret credential. Returns plaintext secret ONCE."""

    # Check no active shared_secret exists
    existing = await db.execute(
        select(models.DeviceCredential).where(
            models.DeviceCredential.gateway_device_id == device.id,
            models.DeviceCredential.credential_type == "shared_secret",
            models.DeviceCredential.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Device already has an active shared_secret credential. Revoke it first.",
        )

    # Generate secret
    device_secret = secrets.token_hex(32)
    secret_hash = bcrypt.hashpw(
        device_secret.encode(), bcrypt.gensalt()
    ).decode()
    fingerprint = hashlib.sha256(device_secret.encode()).hexdigest()

    credential = models.DeviceCredential(
        gateway_device_id=device.id,
        credential_type="shared_secret",
        secret_hash=secret_hash,
        fingerprint=fingerprint,
        status="active",
    )
    db.add(credential)
    await db.flush()

    await _log_event(
        db, "credential_issued",
        f"Credential issued for device {device.device_code}",
        device.id, "info",
    )

    await db.commit()

    return schemas.DeviceCredentialCreatedResponse(
        id=credential.id,
        gateway_device_id=device.id,
        credential_type="shared_secret",
        status="active",
        device_secret=device_secret,
        issued_at=credential.issued_at,
        fingerprint=fingerprint,
    )


async def revoke_credential(
    db: AsyncSession,
    credential: models.DeviceCredential,
) -> models.DeviceCredential:
    """Revoke a credential and all sessions issued through it."""
    if credential.status == "revoked":
        raise HTTPException(status_code=400, detail="Credential already revoked")

    now = _now()
    credential.status = "revoked"
    credential.revoked_at = now

    # Revoke all active sessions for this credential
    session_result = await db.execute(
        select(models.DeviceSession).where(
            models.DeviceSession.credential_id == credential.id,
            models.DeviceSession.revoked_at.is_(None),
        )
    )
    for session in session_result.scalars().all():
        session.revoked_at = now

    await _log_event(
        db, "credential_revoked",
        f"Credential revoked for device",
        credential.gateway_device_id, "warning",
    )
    await db.commit()
    return credential


async def get_credential(
    db: AsyncSession, credential_id: UUID,
) -> models.DeviceCredential:
    cred = await db.get(models.DeviceCredential, credential_id)
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    return cred


# ── Device auth ────────────────────────────────────────────────────


async def device_auth(
    db: AsyncSession, data: schemas.DeviceAuthRequest, client_ip: str | None = None,
) -> schemas.DeviceAuthResponse:
    """Authenticate a device with device_code + device_secret."""

    # Load device
    device_result = await db.execute(
        select(models.GatewayDevice).where(
            models.GatewayDevice.device_code == data.device_code,
        )
    )
    device = device_result.scalar_one_or_none()
    if not device:
        await _log_event(db, "device_login_failed", "Unknown device_code")
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    if device.status in ("disabled", "retired"):
        await _log_event(
            db, "device_login_failed",
            f"Device {device.device_code} is {device.status}", device.id, "warning",
        )
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    # Find active shared_secret credential
    cred_result = await db.execute(
        select(models.DeviceCredential).where(
            models.DeviceCredential.gateway_device_id == device.id,
            models.DeviceCredential.credential_type == "shared_secret",
            models.DeviceCredential.status == "active",
        )
    )
    credential = cred_result.scalar_one_or_none()
    if not credential:
        await _log_event(
            db, "device_login_failed", "No active credential", device.id, "warning",
        )
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    # Verify secret
    if not credential.secret_hash:
        await _log_event(
            db, "device_login_failed", "Credential has no secret_hash",
            device.id, "error",
        )
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    try:
        if not bcrypt.checkpw(
            data.device_secret.encode(), credential.secret_hash.encode()
        ):
            await _log_event(
                db, "device_login_failed",
                "Invalid device_secret", device.id, "warning",
            )
            raise HTTPException(status_code=401, detail="Invalid device credentials")
    except ValueError:
        await _log_event(
            db, "device_login_failed",
            "Invalid secret_hash format", device.id, "error",
        )
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    # Create session
    settings = get_settings()
    now = _now()
    expires_at = now + timedelta(minutes=settings.DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES)

    session = models.DeviceSession(
        gateway_device_id=device.id,
        credential_id=credential.id,
        access_token_hash="",  # filled after JWT creation
        issued_at=now,
        expires_at=expires_at,
        client_ip=client_ip,
    )
    db.add(session)
    await db.flush()

    # Create JWT
    claims = {
        "sub": f"device:{device.id}",
        "type": "device",
        "aud": "device-gateway",
        "device_id": str(device.id),
        "device_code": device.device_code,
        "session_id": str(session.id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    secret = settings.effective_device_jwt_secret
    access_token = jwt.encode(claims, secret, algorithm=settings.JWT_ALGORITHM)

    # Store token hash
    token_hash = hashlib.sha256(access_token.encode()).hexdigest()
    session.access_token_hash = token_hash

    await _log_event(
        db, "device_login_success",
        f"Device {device.device_code} authenticated", device.id,
    )
    await db.commit()

    return schemas.DeviceAuthResponse(
        access_token=access_token,
        expires_in=settings.DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        device_id=device.id,
        device_code=device.device_code,
        status=device.status,
    )


# ── Heartbeat ──────────────────────────────────────────────────────


async def record_heartbeat(
    db: AsyncSession,
    device: models.GatewayDevice,
    data: schemas.DeviceHeartbeatRequest,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> models.DeviceHeartbeat:
    """Record a heartbeat and update device status."""

    # Validate status
    if data.status and data.status not in HEARTBEAT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid heartbeat status")

    # Validate non-negative
    if data.storage_free_mb is not None and data.storage_free_mb < 0:
        raise HTTPException(status_code=400, detail="storage_free_mb must be >= 0")
    if data.cache_items_count is not None and data.cache_items_count < 0:
        raise HTTPException(status_code=400, detail="cache_items_count must be >= 0")

    # Validate manifest hash format
    if data.current_manifest_hash and (
        len(data.current_manifest_hash) != 64 or
        not all(c in "0123456789abcdef" for c in data.current_manifest_hash.lower())
    ):
        raise HTTPException(
            status_code=400,
            detail="current_manifest_hash must be 64 hex characters",
        )

    # Check forbidden keys
    if data.details_json:
        hits = _validate_no_forbidden_keys(data.details_json)
        if hits:
            await _log_event(
                db, "validation_failed",
                f"Heartbeat details_json contains forbidden keys: {', '.join(hits)}",
                device.id, "error",
            )
            raise HTTPException(
                status_code=400,
                detail="Details contain forbidden keys",
            )

    # Check size limit
    settings = get_settings()
    details_str = json.dumps(data.details_json, ensure_ascii=False)
    if len(details_str.encode("utf-8")) > settings.DEVICE_HEARTBEAT_DETAILS_MAX_BYTES:
        await _log_event(
            db, "validation_failed",
            f"Heartbeat details_json exceeds {settings.DEVICE_HEARTBEAT_DETAILS_MAX_BYTES} bytes",
            device.id, "error",
        )
        raise HTTPException(status_code=400, detail="Details too large")

    heartbeat = models.DeviceHeartbeat(
        gateway_device_id=device.id,
        status=data.status or "ok",
        device_time=data.device_time,
        app_version=data.app_version,
        os_version=data.os_version,
        storage_free_mb=data.storage_free_mb,
        cache_items_count=data.cache_items_count,
        current_manifest_hash=data.current_manifest_hash,
        ip_address=client_ip,
        user_agent=user_agent,
        details_json=data.details_json,
    )
    db.add(heartbeat)

    # Update device
    device.last_seen_at = _now()
    if device.status in ("pending", "lost"):
        device.status = "active"
    device.updated_at = _now()

    await _log_event(
        db, "heartbeat_received",
        f"Heartbeat from {device.device_code}", device.id,
    )
    await db.commit()
    await db.refresh(heartbeat)
    return heartbeat


# ── Heartbeats & Events (read) ─────────────────────────────────────


async def get_heartbeats(
    db: AsyncSession, device_id: UUID,
) -> list[models.DeviceHeartbeat]:
    result = await db.execute(
        select(models.DeviceHeartbeat)
        .where(models.DeviceHeartbeat.gateway_device_id == device_id)
        .order_by(models.DeviceHeartbeat.created_at.desc())
    )
    return list(result.scalars().all())


async def get_events(
    db: AsyncSession, device_id: UUID,
) -> list[models.DeviceEvent]:
    result = await db.execute(
        select(models.DeviceEvent)
        .where(models.DeviceEvent.gateway_device_id == device_id)
        .order_by(models.DeviceEvent.created_at.desc())
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════
#  Manifest Delivery
# ═══════════════════════════════════════════════════════════════════

# ── Forbidden key validation (rejects, does NOT sanitize) ──────────


def _find_first_forbidden_key(obj: dict, path: str = "") -> tuple[str, str] | None:
    """Recursively find the first forbidden key. Returns (key_name, path) or None."""
    for key, value in obj.items():
        if key.lower() in FORBIDDEN_KEYS:
            return key, f"{path}.{key}" if path else key
        if isinstance(value, dict):
            hit = _find_first_forbidden_key(
                value, f"{path}.{key}" if path else key,
            )
            if hit:
                return hit
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    hit = _find_first_forbidden_key(
                        item,
                        f"{path}.{key}[{i}]" if path else f"{key}[{i}]",
                    )
                    if hit:
                        return hit
    return None


# ── Target matching ────────────────────────────────────────────────


async def _match_publication_targets(
    device: models.GatewayDevice, db: AsyncSession,
) -> list[UUID]:
    """Return matching publication_target IDs for a device."""
    # Priority 1: display_surface
    if device.display_surface_id:
        result = await db.execute(
            select(PublicationTarget.id).where(
                PublicationTarget.display_surface_id == device.display_surface_id,
                PublicationTarget.channel_id == device.channel_id,
                PublicationTarget.store_id == device.store_id,
            )
        )
        return [row[0] for row in result.all()]

    # Priority 2: logical_carrier
    if device.logical_carrier_id:
        result = await db.execute(
            select(PublicationTarget.id).where(
                PublicationTarget.logical_carrier_id == device.logical_carrier_id,
                PublicationTarget.channel_id == device.channel_id,
                PublicationTarget.store_id == device.store_id,
            )
        )
        return [row[0] for row in result.all()]

    # Priority 3: physical_device → logical_carriers → targets
    if device.physical_device_id:
        # Find all logical_carriers for this physical_device
        from app.domains.channels.models import LogicalCarrier

        lc_result = await db.execute(
            select(LogicalCarrier.id).where(
                LogicalCarrier.physical_device_id == device.physical_device_id,
            )
        )
        lc_ids = [row[0] for row in lc_result.all()]
        if not lc_ids:
            return []

        # Match publication_targets by logical_carrier_id or display_surface_id
        # (display_surfaces belong to those logical_carriers)
        from app.domains.channels.models import DisplaySurface

        ds_result = await db.execute(
            select(DisplaySurface.id).where(
                DisplaySurface.logical_carrier_id.in_(lc_ids),
            )
        )
        ds_ids = [row[0] for row in ds_result.all()]

        conditions = [
            PublicationTarget.channel_id == device.channel_id,
            PublicationTarget.store_id == device.store_id,
        ]
        or_conditions = []
        if lc_ids:
            or_conditions.append(PublicationTarget.logical_carrier_id.in_(lc_ids))
        if ds_ids:
            or_conditions.append(PublicationTarget.display_surface_id.in_(ds_ids))

        if not or_conditions:
            return []

        from sqlalchemy import or_

        conditions.append(or_(*or_conditions))
        result = await db.execute(
            select(PublicationTarget.id).where(*conditions)
        )
        return [row[0] for row in result.all()]

    return []


# ── Current manifest ───────────────────────────────────────────────


async def get_current_manifest(
    device: models.GatewayDevice,
    db: AsyncSession,
    current_manifest_hash: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> schemas.DeviceManifestCurrentResponse:
    """Return the current published manifest for a device."""

    # Status check
    if device.status in ("disabled", "retired"):
        await _record_manifest_request(
            db, device, None, None, "forbidden",
            client_manifest_hash=current_manifest_hash,
            ip_address=client_ip, user_agent=user_agent,
            message=f"Device {device.status}",
        )
        await _log_event(
            db, "manifest_forbidden",
            f"Manifest forbidden: device {device.status}",
            device.id, "warning",
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Device not authorized for manifest delivery")

    # Match targets (get_current_manifest)
    target_ids = await _match_publication_targets(device, db)
    if not target_ids:
        await _record_manifest_request(
            db, device, None, None, "not_found",
            client_manifest_hash=current_manifest_hash,
            ip_address=client_ip, user_agent=user_agent,
            message="No matching publication target",
        )
        await _log_event(
            db, "manifest_not_found",
            "No manifest: no matching target", device.id,
        )
        return schemas.DeviceManifestCurrentResponse(status="no_manifest")

    # Find the most recent published manifest_version
    result = await db.execute(
        select(ManifestVersion)
        .join(PublicationTarget, ManifestVersion.publication_target_id == PublicationTarget.id)
        .join(PublicationBatch, ManifestVersion.publication_batch_id == PublicationBatch.id)
        .where(
            ManifestVersion.status == "published",
            PublicationTarget.status == "published",
            PublicationBatch.status == "published",
            PublicationTarget.id.in_(target_ids),
        )
        .order_by(ManifestVersion.published_at.desc().nullslast())
        .order_by(ManifestVersion.manifest_version.desc())
        .limit(1)
    )
    manifest = result.scalar_one_or_none()

    if not manifest:
        await _record_manifest_request(
            db, device, None, None, "not_found",
            client_manifest_hash=current_manifest_hash,
            ip_address=client_ip, user_agent=user_agent,
            message="No published manifest for targets",
        )
        await _log_event(
            db, "manifest_not_found",
            "No published manifest found", device.id,
        )
        return schemas.DeviceManifestCurrentResponse(status="no_manifest")

    target_id = manifest.publication_target_id

    # Forbidden key check
    manifest_json = manifest.manifest_json or {}
    hit = _find_first_forbidden_key(manifest_json)
    if hit:
        key_name, path = hit
        await _record_manifest_request(
            db, device, manifest.id, target_id, "validation_failed",
            client_manifest_hash=current_manifest_hash,
            ip_address=client_ip, user_agent=user_agent,
            message=f"Forbidden key in manifest: {path}",
            details_json={"forbidden_key": key_name, "path": path},
        )
        await _log_event(
            db, "validation_failed",
            f"Manifest forbidden key '{path}': {key_name}",
            device.id, "error",
            details_json={"forbidden_key": key_name, "path": path},
        )
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail="Manifest validation failed",
        )

    # Not-modified check (get_current_manifest)
    if current_manifest_hash and current_manifest_hash == manifest.manifest_hash:
        await _record_manifest_request(
            db, device, manifest.id, target_id, "not_modified",
            response_hash=manifest.manifest_hash,
            client_manifest_hash=current_manifest_hash,
            ip_address=client_ip, user_agent=user_agent,
        )
        await _log_event(
            db, "manifest_not_modified",
            f"Manifest not modified: {manifest.manifest_hash[:16]}",
            device.id,
        )
        _touch_device(device)
        await db.commit()
        return schemas.DeviceManifestCurrentResponse(
            status="not_modified",
            manifest_version_id=manifest.id,
            manifest_hash=manifest.manifest_hash,
        )

    # Serve
    await _record_manifest_request(
        db, device, manifest.id, target_id, "served",
        response_hash=manifest.manifest_hash,
        client_manifest_hash=current_manifest_hash,
        ip_address=client_ip, user_agent=user_agent,
    )
    await _log_event(
        db, "manifest_served",
        f"Manifest served: {manifest.manifest_hash[:16]}",
        device.id,
    )
    _touch_device(device)
    await db.commit()

    return schemas.DeviceManifestCurrentResponse(
        status="served",
        manifest_version_id=manifest.id,
        manifest_hash=manifest.manifest_hash,
        published_at=manifest.published_at,
        manifest=manifest_json,
    )


# ── Specific manifest by ID ────────────────────────────────────────


async def get_device_manifest_by_id(
    device: models.GatewayDevice,
    db: AsyncSession,
    manifest_version_id: UUID,
    client_ip: str | None,
    user_agent: str | None,
) -> schemas.DeviceManifestResponse:
    """Return a specific manifest version — only if it belongs to the device."""

    if device.status in ("disabled", "retired"):
        await _record_manifest_request(
            db, device, manifest_version_id, None, "forbidden",
            ip_address=client_ip, user_agent=user_agent,
            message=f"Device {device.status}",
        )
        await _log_event(
            db, "manifest_forbidden",
            f"Manifest forbidden: device {device.status}",
            device.id, "warning",
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Device not authorized for manifest delivery")

    # Load manifest (get_device_manifest_by_id)
    result = await db.execute(
        select(ManifestVersion)
        .join(PublicationTarget, ManifestVersion.publication_target_id == PublicationTarget.id)
        .join(PublicationBatch, ManifestVersion.publication_batch_id == PublicationBatch.id)
        .where(
            ManifestVersion.id == manifest_version_id,
            ManifestVersion.status == "published",
            PublicationTarget.status == "published",
            PublicationBatch.status == "published",
        )
    )
    manifest = result.scalar_one_or_none()

    if not manifest:
        # 404 — don't reveal existence of non-published manifests
        await _record_manifest_request(
            db, device, manifest_version_id, None, "not_found",
            ip_address=client_ip, user_agent=user_agent,
            message="Manifest not found or not published",
        )
        raise HTTPException(status_code=404, detail="Manifest not found")

    # Verify this manifest belongs to the device
    target_ids = await _match_publication_targets(device, db)
    if manifest.publication_target_id not in target_ids:
        await _record_manifest_request(
            db, device, manifest_version_id, manifest.publication_target_id, "forbidden",
            ip_address=client_ip, user_agent=user_agent,
            message="Manifest does not belong to this device",
        )
        await _log_event(
            db, "manifest_forbidden",
            f"Cross-device manifest access attempt",
            device.id, "warning",
            details_json={"manifest_version_id": str(manifest_version_id)},
        )
        raise HTTPException(status_code=404, detail="Manifest not found")

    # Forbidden key check
    manifest_json = manifest.manifest_json or {}
    hit = _find_first_forbidden_key(manifest_json)
    if hit:
        key_name, path = hit
        await _record_manifest_request(
            db, device, manifest.id, manifest.publication_target_id, "validation_failed",
            ip_address=client_ip, user_agent=user_agent,
            message=f"Forbidden key in manifest: {path}",
            details_json={"forbidden_key": key_name, "path": path},
        )
        await _log_event(
            db, "validation_failed",
            f"Manifest forbidden key '{path}': {key_name}",
            device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="Manifest validation failed")

    # Serve (get_device_manifest_by_id)
    await _record_manifest_request(
        db, device, manifest.id, manifest.publication_target_id, "served",
        response_hash=manifest.manifest_hash,
        ip_address=client_ip, user_agent=user_agent,
    )
    await _log_event(
        db, "manifest_served",
        f"Manifest served by ID: {manifest.manifest_hash[:16]}",
        device.id,
    )
    _touch_device(device)
    await db.commit()

    return schemas.DeviceManifestResponse(
        status="served",
        manifest_version_id=manifest.id,
        manifest_hash=manifest.manifest_hash,
        published_at=manifest.published_at,
        manifest=manifest_json,
    )


# ── Helpers ────────────────────────────────────────────────────────


def _touch_device(device: models.GatewayDevice) -> None:
    """Update last_seen_at on the device (in-memory, caller must commit)."""
    device.last_seen_at = _now()
    device.updated_at = _now()


async def _record_manifest_request(
    db: AsyncSession,
    device: models.GatewayDevice,
    manifest_version_id: UUID | None,
    publication_target_id: UUID | None,
    request_status: str,
    response_hash: str | None = None,
    client_manifest_hash: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    message: str | None = None,
    details_json: dict | None = None,
) -> None:
    """Create a device_manifest_request audit record."""
    # Validate details_json size
    settings = get_settings()
    if details_json:
        details_str = json.dumps(details_json, ensure_ascii=False)
        if len(details_str.encode("utf-8")) > settings.DEVICE_MANIFEST_REQUEST_DETAILS_MAX_BYTES:
            details_json = {
                "_truncated": True,
                "original_keys": list(details_json.keys()),
            }

    record = models.DeviceManifestRequest(
        gateway_device_id=device.id,
        manifest_version_id=manifest_version_id,
        publication_target_id=publication_target_id,
        request_status=request_status,
        response_hash=response_hash,
        client_manifest_hash=client_manifest_hash,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] if user_agent else None,
        message=message,
        details_json=details_json or {},
    )
    db.add(record)


# ── Admin: manifest requests ───────────────────────────────────────


async def get_device_manifest_requests(
    db: AsyncSession,
    device_id: UUID,
    request_status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
) -> list[models.DeviceManifestRequest]:
    """List manifest requests for a device (admin)."""
    conditions = [models.DeviceManifestRequest.gateway_device_id == device_id]
    if request_status:
        conditions.append(models.DeviceManifestRequest.request_status == request_status)
    if date_from:
        conditions.append(models.DeviceManifestRequest.created_at >= date_from)
    if date_to:
        conditions.append(models.DeviceManifestRequest.created_at <= date_to)

    result = await db.execute(
        select(models.DeviceManifestRequest)
        .where(*conditions)
        .order_by(models.DeviceManifestRequest.created_at.desc())
        .limit(min(limit, 500))
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════
#  Media Delivery Constants
# ═══════════════════════════════════════════════════════════════════

MEDIA_DELIVERY_ALLOWED_MIME = frozenset({
    "image/jpeg",
    "image/png",
    "video/mp4",
    "video/webm",
})

_VALID_OBJECT_KEY_RE = re.compile(r'^[A-Za-z0-9._/-]+$')
_FORBIDDEN_OBJECT_KEY_CHARS = frozenset({'\\', '?', '#', '%'})
_FORBIDDEN_CONTROL = frozenset(chr(c) for c in range(0x20))


# ═══════════════════════════════════════════════════════════════════
#  Media Delivery Helpers
# ═══════════════════════════════════════════════════════════════════

def _validate_object_key(path: str | None) -> str | None:
    """Validate a MinIO object key. Returns error message or None."""
    if not path:
        return "media_path is empty"
    if len(path) > 500:
        return "media_path exceeds 500 characters"
    if not path.startswith("creatives/"):
        return "media_path must start with 'creatives/'"
    if path.startswith("/"):
        return "media_path must not be absolute"
    if path.endswith("/"):
        return "media_path must not end with '/'"
    if ".." in path:
        return "media_path must not contain '..'"
    if any(c in _FORBIDDEN_OBJECT_KEY_CHARS for c in path):
        return "media_path contains forbidden characters (\\, ?, #, %)"
    if any(c in _FORBIDDEN_CONTROL for c in path):
        return "media_path contains control characters"
    if not _VALID_OBJECT_KEY_RE.match(path):
        return "media_path contains invalid characters"
    return None


def _validate_sha256_hex(value: str | None) -> str | None:
    """Validate sha256 is 64 hex chars. Returns error or None."""
    if not value:
        return "sha256 is empty"
    if len(value) != 64:
        return "sha256 must be 64 hex characters"
    if not all(c in "0123456789abcdef" for c in value.lower()):
        return "sha256 contains non-hex characters"
    return None


async def _record_media_request(
    db: AsyncSession,
    device: models.GatewayDevice,
    manifest_item_id: UUID | None,
    manifest_version_id: UUID | None,
    publication_target_id: UUID | None,
    status: str,
    *,
    media_path: str | None = None,
    expected_sha256: str | None = None,
    client_cached_sha256: str | None = None,
    response_size_bytes: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    message: str | None = None,
    details_json: dict | None = None,
    commit: bool = True,
) -> None:
    """Record a media request. Must be called before HTTPException if commit=True."""
    settings = get_settings()
    max_bytes = settings.DEVICE_MEDIA_REQUEST_DETAILS_MAX_BYTES

    details = dict(details_json or {})
    cleaned = {}
    for k, v in details.items():
        if k.lower() in FORBIDDEN_KEYS:
            continue
        if isinstance(v, str) and len(v) > 1024:
            cleaned[k] = v[:1020] + "..."
        else:
            cleaned[k] = v
    details_str = json.dumps(cleaned, default=str)
    if len(details_str) > max_bytes:
        details_str = details_str[:max_bytes - 3] + "..."

    entry = models.DeviceMediaRequest(
        gateway_device_id=device.id,
        manifest_item_id=manifest_item_id,
        manifest_version_id=manifest_version_id,
        publication_target_id=publication_target_id,
        request_status=status,
        media_path=media_path[:1000] if media_path else None,
        expected_sha256=expected_sha256[:64] if expected_sha256 else None,
        client_cached_sha256=client_cached_sha256[:64] if client_cached_sha256 else None,
        response_size_bytes=response_size_bytes,
        ip_address=ip_address[:45] if ip_address else None,
        user_agent=user_agent[:500] if user_agent else None,
        message=message[:500] if message else None,
        details_json=cleaned,
    )
    db.add(entry)
    if commit:
        await db.commit()


# ═══════════════════════════════════════════════════════════════════
#  Media Delivery Public Functions
# ═══════════════════════════════════════════════════════════════════

async def get_media_metadata(
    device: models.GatewayDevice,
    manifest_item_id: UUID,
    client_cached_sha256: str | None,
    client_ip: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> dict:
    """Return safe metadata for a manifest item."""
    from app.domains.media.models import CreativeVersion, Rendition

    result = await db.execute(
        select(
            ManifestItem,
            ManifestVersion,
            PublicationTarget,
            PublicationBatch,
            CreativeVersion,
            Rendition,
        )
        .join(ManifestVersion, ManifestItem.manifest_version_id == ManifestVersion.id)
        .join(PublicationTarget, ManifestVersion.publication_target_id == PublicationTarget.id)
        .join(PublicationBatch, ManifestVersion.publication_batch_id == PublicationBatch.id)
        .outerjoin(CreativeVersion, ManifestItem.creative_version_id == CreativeVersion.id)
        .outerjoin(Rendition, ManifestItem.rendition_id == Rendition.id)
        .where(ManifestItem.id == manifest_item_id)
    )
    row = result.one_or_none()
    if not row:
        await _record_media_request(
            db, device, None, None, None, "not_found",
            ip_address=client_ip, user_agent=user_agent,
            message="Manifest item not found",
        )
        raise HTTPException(status_code=404, detail="Not found")

    mi, mv, pt, pb, cv, rend = row

    if pb.status != "published" or pt.status != "published" or mv.status != "published":
        await _record_media_request(
            db, device, manifest_item_id, mv.id, pt.id, "not_found",
            ip_address=client_ip, user_agent=user_agent,
            message="Manifest not published",
        )
        raise HTTPException(status_code=404, detail="Not found")

    target_ids = await _match_publication_targets(device, db)
    if pt.id not in target_ids:
        await _record_media_request(
            db, device, manifest_item_id, mv.id, pt.id, "not_found",
            ip_address=client_ip, user_agent=user_agent,
            message="Publication target does not match device",
        )
        raise HTTPException(status_code=404, detail="Not found")

    key_error = _validate_object_key(mi.media_path)
    sha_error = _validate_sha256_hex(mi.sha256)
    if key_error or sha_error:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "validation_failed",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            ip_address=client_ip, user_agent=user_agent,
            message=key_error or sha_error,
            details_json={
                "validation_key": key_error,
                "validation_sha256": sha_error,
            },
        )
        await _log_event(
            db, "media_validation_failed",
            (key_error or "") + (sha_error or ""),
            device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="Media validation failed")

    mime_type = None
    if rend and rend.mime_type:
        mime_type = rend.mime_type
    elif cv and cv.mime_type:
        mime_type = cv.mime_type

    if not mime_type or mime_type not in MEDIA_DELIVERY_ALLOWED_MIME:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "validation_failed",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            ip_address=client_ip, user_agent=user_agent,
            message=f"MIME type not allowed: {mime_type}",
            details_json={"mime_type": mime_type},
        )
        await _log_event(
            db, "media_validation_failed",
            f"MIME not allowed: {mime_type}", device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="Media validation failed")

    duration_seconds = None
    if rend and rend.duration_seconds is not None:
        duration_seconds = rend.duration_seconds
    elif cv and cv.duration_seconds is not None:
        duration_seconds = cv.duration_seconds
    duration_ms = int(duration_seconds * 1000) if duration_seconds is not None else None

    try:
        minio_client = _get_minio_client()
        settings = get_settings()
        obj_info = minio_client.stat_object(settings.MINIO_BUCKET, mi.media_path)
        size_bytes = obj_info.size
    except S3Error:
        size_bytes = None

    if client_cached_sha256 and client_cached_sha256 == mi.sha256:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "not_modified",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            client_cached_sha256=client_cached_sha256,
            ip_address=client_ip, user_agent=user_agent,
        )
        await _log_event(
            db, "media_not_modified",
            f"Media not modified: {mi.id}", device.id,
        )
        await db.commit()
        return {
            "status": "not_modified",
            "manifest_item_id": str(manifest_item_id),
            "sha256": mi.sha256,
        }

    await _record_media_request(
        db, device, mi.id, mv.id, pt.id, "served",
        media_path=mi.media_path, expected_sha256=mi.sha256,
        ip_address=client_ip, user_agent=user_agent,
    )
    await _log_event(
        db, "media_served",
        f"Media metadata served: {mi.id}", device.id,
    )
    await db.commit()

    return {
        "status": "ok",
        "manifest_item_id": str(manifest_item_id),
        "media": {
            "sha256": mi.sha256,
            "content_type": mime_type,
            "size_bytes": size_bytes,
            "duration_ms": duration_ms,
        },
    }


async def get_media_download(
    device: models.GatewayDevice,
    manifest_item_id: UUID,
    client_cached_sha256: str | None,
    client_ip: str | None,
    user_agent: str | None,
    request: Request,
    db: AsyncSession,
) -> StreamingResponse | dict:
    """Stream a media file for an authorized device."""
    from app.domains.media.models import CreativeVersion, Rendition

    result = await db.execute(
        select(
            ManifestItem,
            ManifestVersion,
            PublicationTarget,
            PublicationBatch,
            CreativeVersion,
            Rendition,
        )
        .join(ManifestVersion, ManifestItem.manifest_version_id == ManifestVersion.id)
        .join(PublicationTarget, ManifestVersion.publication_target_id == PublicationTarget.id)
        .join(PublicationBatch, ManifestVersion.publication_batch_id == PublicationBatch.id)
        .outerjoin(CreativeVersion, ManifestItem.creative_version_id == CreativeVersion.id)
        .outerjoin(Rendition, ManifestItem.rendition_id == Rendition.id)
        .where(ManifestItem.id == manifest_item_id)
    )
    row = result.one_or_none()
    if not row:
        await _record_media_request(
            db, device, None, None, None, "not_found",
            ip_address=client_ip, user_agent=user_agent,
            message="Manifest item not found",
        )
        raise HTTPException(status_code=404, detail="Not found")

    mi, mv, pt, pb, cv, rend = row

    if pb.status != "published" or pt.status != "published" or mv.status != "published":
        await _record_media_request(
            db, device, manifest_item_id, mv.id, pt.id, "not_found",
            ip_address=client_ip, user_agent=user_agent,
            message="Manifest not published",
        )
        raise HTTPException(status_code=404, detail="Not found")

    target_ids = await _match_publication_targets(device, db)
    if pt.id not in target_ids:
        await _record_media_request(
            db, device, manifest_item_id, mv.id, pt.id, "not_found",
            ip_address=client_ip, user_agent=user_agent,
            message="Publication target does not match device",
        )
        raise HTTPException(status_code=404, detail="Not found")

    key_error = _validate_object_key(mi.media_path)
    if key_error:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "validation_failed",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            ip_address=client_ip, user_agent=user_agent,
            message=key_error,
            details_json={"validation_key": key_error},
        )
        await _log_event(
            db, "media_validation_failed", key_error, device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Media path invalid")

    sha_error = _validate_sha256_hex(mi.sha256)
    if sha_error:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "validation_failed",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            ip_address=client_ip, user_agent=user_agent,
            message=sha_error,
            details_json={"validation_sha256": sha_error},
        )
        await _log_event(
            db, "media_validation_failed", sha_error, device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="Media validation failed")

    mime_type = None
    if rend and rend.mime_type:
        mime_type = rend.mime_type
    elif cv and cv.mime_type:
        mime_type = cv.mime_type

    if not mime_type or mime_type not in MEDIA_DELIVERY_ALLOWED_MIME:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "validation_failed",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            ip_address=client_ip, user_agent=user_agent,
            message=f"MIME type not allowed: {mime_type}",
            details_json={"mime_type": mime_type},
        )
        await _log_event(
            db, "media_validation_failed",
            f"MIME not allowed: {mime_type}", device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="Media validation failed")

    if client_cached_sha256 and client_cached_sha256 == mi.sha256:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "not_modified",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            client_cached_sha256=client_cached_sha256,
            ip_address=client_ip, user_agent=user_agent,
        )
        await _log_event(
            db, "media_not_modified",
            f"Media not modified: {mi.id}", device.id,
        )
        await db.commit()
        raise HTTPException(status_code=304)

    try:
        minio_client = _get_minio_client()
        settings = get_settings()
        obj_info = minio_client.stat_object(settings.MINIO_BUCKET, mi.media_path)
        content_length = obj_info.size
        etag = obj_info.etag
        minio_content_type = obj_info.content_type
    except S3Error as e:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "storage_error",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            ip_address=client_ip, user_agent=user_agent,
            message="MinIO object not accessible",
            details_json={"error_category": type(e).__name__},
        )
        await _log_event(
            db, "media_storage_error",
            f"MinIO error for {mi.media_path}: {type(e).__name__}",
            device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=404, detail="Media not available")

    if minio_content_type and minio_content_type != mime_type:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "validation_failed",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            ip_address=client_ip, user_agent=user_agent,
            message=f"MIME mismatch: DB={mime_type} MinIO={minio_content_type}",
            details_json={"db_mime": mime_type, "minio_mime": minio_content_type},
        )
        await _log_event(
            db, "media_validation_failed",
            f"MIME mismatch for {mi.id}: DB={mime_type} MinIO={minio_content_type}",
            device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="Media validation failed")

    try:
        response = minio_client.get_object(settings.MINIO_BUCKET, mi.media_path)
    except S3Error as e:
        await _record_media_request(
            db, device, mi.id, mv.id, pt.id, "storage_error",
            media_path=mi.media_path, expected_sha256=mi.sha256,
            ip_address=client_ip, user_agent=user_agent,
            message="MinIO get_object failed",
            details_json={"error_category": type(e).__name__},
        )
        await _log_event(
            db, "media_storage_error",
            f"MinIO get_object failed for {mi.media_path}: {type(e).__name__}",
            device.id, "error",
        )
        await db.commit()
        raise HTTPException(status_code=404, detail="Media not available")

    await _record_media_request(
        db, device, mi.id, mv.id, pt.id, "served",
        media_path=mi.media_path, expected_sha256=mi.sha256,
        response_size_bytes=content_length,
        ip_address=client_ip, user_agent=user_agent,
    )
    await _log_event(
        db, "media_served",
        f"Media download started: {mi.id}", device.id,
    )
    await db.commit()

    def _close_response():
        try:
            response.close()
            response.release_conn()
        except Exception:
            pass

    return StreamingResponse(
        response.stream(amt=64 * 1024),
        status_code=200,
        media_type=mime_type,
        headers={
            "Content-Length": str(content_length),
            "X-Content-SHA256": mi.sha256,
            "ETag": etag or "",
            "Cache-Control": "private, max-age=86400",
        },
        background=BackgroundTask(_close_response),
    )


async def get_media_requests(
    db: AsyncSession,
    device_id: UUID,
    *,
    request_status: str | None = None,
    manifest_item_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[models.DeviceMediaRequest]:
    """Get media requests for a device (admin)."""
    conditions = [models.DeviceMediaRequest.gateway_device_id == device_id]
    if request_status:
        conditions.append(models.DeviceMediaRequest.request_status == request_status)
    if manifest_item_id:
        conditions.append(models.DeviceMediaRequest.manifest_item_id == manifest_item_id)

    result = await db.execute(
        select(models.DeviceMediaRequest)
        .where(*conditions)
        .order_by(models.DeviceMediaRequest.created_at.desc())
        .offset(offset)
        .limit(min(limit, 500))
    )
    return list(result.scalars().all())
