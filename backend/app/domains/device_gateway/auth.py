"""Device Gateway: authentication function (not a FastAPI dependency)."""

import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, Request
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.device_gateway import models


async def authenticate_device(
    request: Request,
    db: AsyncSession,
) -> tuple[models.GatewayDevice, models.DeviceSession]:
    """Validate device JWT from Authorization header. Returns (device, session)."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.effective_device_jwt_secret,
            algorithms=[settings.JWT_ALGORITHM],
            audience="device-gateway",
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != "device":
        raise HTTPException(status_code=401, detail="Invalid token type")
    if payload.get("aud") != "device-gateway":
        raise HTTPException(status_code=401, detail="Invalid token audience")

    device_id_str = payload.get("sub", "")
    if not device_id_str.startswith("device:"):
        raise HTTPException(status_code=401, detail="Invalid token subject")
    device_id = UUID(device_id_str[7:])

    session_id_str = payload.get("session_id")
    if not session_id_str:
        raise HTTPException(status_code=401, detail="Missing session_id")
    session_id = UUID(session_id_str)

    device = await db.get(models.GatewayDevice, device_id)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    if device.status in ("disabled", "retired"):
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    session = await db.get(models.DeviceSession, session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    if session.gateway_device_id != device_id:
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    if session.revoked_at:
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    if session.expires_at and session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Token expired")

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if not _timing_safe_compare(token_hash, session.access_token_hash):
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    credential = await db.get(models.DeviceCredential, session.credential_id)
    if not credential or credential.status != "active":
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    if credential.revoked_at:
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    session.last_used_at = datetime.now(timezone.utc)
    session.client_ip = request.client.host if request.client else None
    await db.commit()

    return device, session


def _timing_safe_compare(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0
