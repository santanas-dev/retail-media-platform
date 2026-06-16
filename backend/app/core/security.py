"""
Security utilities: JWT tokens, password hashing, manifest signatures.
"""

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.core.config import Settings


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def hash_refresh_token(token: str) -> str:
    """SHA-256 hash of a refresh token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(data: dict, settings: Settings) -> tuple[str, datetime]:
    """Create a JWT access token. Returns (token, expires_at)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update(
        {"exp": expire, "type": "access", "jti": uuid.uuid4().hex}
    )
    token = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token, expire


def create_refresh_token(data: dict, settings: Settings) -> tuple[str, str, datetime]:
    """Create a JWT refresh token. Returns (token, jti, expires_at)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    jti = uuid.uuid4().hex
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    token = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token, jti, expire


def decode_token(token: str, settings: Settings) -> dict:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    return jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


def sign_manifest(manifest_json: str, settings: Settings) -> str:
    """Sign a manifest payload. Stub — real implementation later."""
    return hmac.new(
        settings.SECRET_KEY.encode(),
        manifest_json.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_manifest_signature(
    manifest_json: str, signature: str, settings: Settings
) -> bool:
    """Verify a manifest signature. Stub — real implementation later."""
    return hmac.compare_digest(
        sign_manifest(manifest_json, settings),
        signature,
    )
