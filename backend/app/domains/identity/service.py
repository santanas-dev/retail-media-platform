"""
Identity & Access: business logic — auth, user management, permission checks.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.domains.identity import models, schemas


# ── Authentication ───────────────────────────────────────────────────────

async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
    settings: Settings,
) -> schemas.TokenResponse:
    """Validate credentials and issue tokens."""
    result = await db.execute(
        select(models.User).where(models.User.username == username)
    )
    user: models.User | None = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        # Increment failed attempts
        if user:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= 5:
                user.is_locked = True
                user.locked_until = datetime.now(timezone.utc).replace(
                    minute=(datetime.now(timezone.utc).minute + 15) % 60
                )
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Check account status
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    if user.is_locked:
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account is locked. Try again later.",
            )
        # Lock expired — reset
        user.is_locked = False
        user.failed_attempts = 0
        user.locked_until = None

    # Reset failed attempts on success
    user.failed_attempts = 0
    user.last_login_at = datetime.now(timezone.utc)

    # Issue tokens
    token_data = {"sub": str(user.id), "username": user.username}
    access_token, _ = create_access_token(token_data, settings)
    refresh_token, jti, expires_at = create_refresh_token(token_data, settings)

    # Store refresh token hash
    refresh_hash = hash_refresh_token(refresh_token)
    db.add(
        models.RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            jti=jti,
            expires_at=expires_at,
        )
    )

    await db.commit()

    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def refresh_access_token(
    db: AsyncSession,
    refresh_token_str: str,
    settings: Settings,
) -> schemas.TokenResponse:
    """Validate refresh token and issue a new access token."""
    # Decode the refresh token
    try:
        payload = decode_token(refresh_token_str, settings)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # Check the token hash in DB
    token_hash = hash_refresh_token(refresh_token_str)
    result = await db.execute(
        select(models.RefreshToken).where(
            models.RefreshToken.token_hash == token_hash,
            models.RefreshToken.revoked == False,
        )
    )
    stored: models.RefreshToken | None = result.scalar_one_or_none()

    if not stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or not found",
        )

    # Check expiry
    if stored.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    # Rotate: revoke old, issue new
    stored.revoked = True
    stored.revoked_at = datetime.now(timezone.utc)

    # Get user
    result = await db.execute(
        select(models.User).where(models.User.id == stored.user_id)
    )
    user: models.User | None = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Issue new tokens
    token_data = {"sub": str(user.id), "username": user.username}
    access_token, _ = create_access_token(token_data, settings)
    new_refresh, new_jti, new_expires = create_refresh_token(token_data, settings)

    db.add(
        models.RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(new_refresh),
            jti=new_jti,
            expires_at=new_expires,
        )
    )

    await db.commit()

    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def logout(
    db: AsyncSession,
    refresh_token_str: str,
    settings: Settings,
) -> None:
    """Revoke a refresh token (logout)."""
    token_hash = hash_refresh_token(refresh_token_str)
    result = await db.execute(
        select(models.RefreshToken).where(
            models.RefreshToken.token_hash == token_hash,
            models.RefreshToken.revoked == False,
        )
    )
    stored: models.RefreshToken | None = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
        stored.revoked_at = datetime.now(timezone.utc)
        await db.commit()


# ── Current user ─────────────────────────────────────────────────────────

async def get_current_user_from_token(
    db: AsyncSession,
    token: str,
    settings: Settings,
) -> models.User:
    """Validate access token and return the user.

    Raises HTTPException if: invalid JWT, expired, user not found,
    user inactive, or user locked.
    """
    try:
        payload = decode_token(token, settings)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.user_roles).selectinload(
                models.UserRole.role
            ).selectinload(
                models.Role.role_permissions
            ).selectinload(
                models.RolePermission.permission
            )
        )
        .where(models.User.id == user_id)
    )
    user: models.User | None = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    if user.is_locked:
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account is locked",
            )
        # Expired lock — let it pass, but don't auto-unlock
        # (unlock happens on successful login, not here)

    return user


def get_user_roles(user: models.User) -> list[str]:
    """Extract role codes from a loaded User model."""
    return [ur.role.code for ur in user.user_roles]


def get_user_permissions(user: models.User) -> list[str]:
    """Extract permission codes from a loaded User model."""
    perms: set[str] = set()
    for ur in user.user_roles:
        for rp in ur.role.role_permissions:
            perms.add(rp.permission.code)
    return sorted(perms)


def require_permission(user: models.User, permission: str) -> None:
    """Raise 403 if the user does not have the required permission."""
    if permission not in get_user_permissions(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission}",
        )


# ── User management ──────────────────────────────────────────────────────

async def create_user(
    db: AsyncSession,
    data: schemas.UserCreateRequest,
) -> models.User:
    """Create a new portal user."""
    # Check uniqueness
    result = await db.execute(
        select(models.User).where(
            (models.User.username == data.username)
            | (models.User.email == data.email if data.email else False)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.username == data.username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already taken",
        )

    user = models.User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[models.User]:
    """List all users (paginated)."""
    result = await db.execute(
        select(models.User)
        .order_by(models.User.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_roles(db: AsyncSession) -> list[models.Role]:
    """List all roles."""
    result = await db.execute(
        select(models.Role).order_by(models.Role.code)
    )
    return list(result.scalars().all())


async def list_permissions(db: AsyncSession) -> list[models.Permission]:
    """List all permissions."""
    result = await db.execute(
        select(models.Permission).order_by(models.Permission.code)
    )
    return list(result.scalars().all())
