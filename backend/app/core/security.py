"""
Security utilities: JWT tokens, hashing, manifest signatures.

On Step 1 these are stubs — real implementation comes with Identity domain.
"""

from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import Settings


def create_access_token(data: dict, settings: Settings) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict, settings: Settings) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, settings: Settings) -> dict:
    """Decode and validate a JWT token."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def hash_password(password: str) -> str:
    """Hash a password using passlib bcrypt."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.verify(plain_password, hashed_password)


def sign_manifest(manifest_json: str, settings: Settings) -> str:
    """Sign a manifest payload. Stub — real implementation later."""
    import hashlib
    import hmac
    return hmac.new(
        settings.SECRET_KEY.encode(),
        manifest_json.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_manifest_signature(manifest_json: str, signature: str, settings: Settings) -> bool:
    """Verify a manifest signature. Stub — real implementation later."""
    import hmac
    return hmac.compare_digest(
        sign_manifest(manifest_json, settings),
        signature,
    )
