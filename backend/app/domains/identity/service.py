"""
Identity & Access: business logic — auth, user management, permission checks.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import sqlalchemy as sa

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
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
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
    if user.is_archived:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is archived",
        )
    if user.is_service_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service accounts cannot login through portal",
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
    """Create a new portal user, optionally assign roles."""
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
    await db.flush()  # get user.id

    # Assign roles if requested
    if data.role_codes:
        # Deduplicate
        codes = list(dict.fromkeys(data.role_codes))

        result = await db.execute(
            select(models.Role).where(models.Role.code.in_(codes))
        )
        roles = {r.code: r for r in result.scalars().all()}

        missing = set(codes) - set(roles.keys())
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Roles not found: {', '.join(sorted(missing))}",
            )

        if "device_service" in codes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign device_service role via user API",
            )

        for role in roles.values():
            db.add(models.UserRole(user_id=user.id, role_id=role.id))

    await db.commit()
    # Reload with roles
    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.user_roles).selectinload(
                models.UserRole.role
            )
        )
        .where(models.User.id == user.id)
    )
    new_user = result.scalar_one()

    # Audit
    from app.domains.identity.audit import record_admin_action
    await record_admin_action(
        db=db,
        actor_user_id="system",  # TODO: pass actor from request context
        action="create_user",
        target_type="user",
        target_ref=data.username,
        details={"roles": data.role_codes} if data.role_codes else None,
    )

    return new_user


async def list_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[models.User]:
    """List all users (paginated), with roles eager-loaded."""
    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.user_roles).selectinload(
                models.UserRole.role
            )
        )
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


# ── User role management ────────────────────────────────────────────────

async def update_user_roles(
    db: AsyncSession,
    user_id: UUID,
    data: schemas.UserRoleUpdate,
) -> models.User:
    """Replace all roles for a user."""
    # Deduplicate
    codes = list(dict.fromkeys(data.role_codes))

    # 1. Check user exists
    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.user_roles).selectinload(
                models.UserRole.role
            )
        )
        .where(models.User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # 2. Check all roles exist
    result = await db.execute(
        select(models.Role).where(models.Role.code.in_(codes))
    )
    new_roles_by_code = {r.code: r for r in result.scalars().all()}
    missing = set(codes) - set(new_roles_by_code.keys())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Roles not found: {', '.join(sorted(missing))}",
        )

    # 3. Disallow device_service
    if "device_service" in codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign device_service role via user API",
        )

    # 4. Protect last active system_admin
    # Get system_admin role id
    result = await db.execute(
        select(models.Role.id).where(models.Role.code == "system_admin")
    )
    sa_role_id = result.scalar_one()
    current_role_ids = {ur.role_id for ur in user.user_roles}
    had_sa = sa_role_id in current_role_ids
    will_have_sa = "system_admin" in codes

    if had_sa and not will_have_sa:
        # Check if there's another active user with system_admin
        result = await db.execute(
            select(models.UserRole).join(
                models.User,
                models.UserRole.user_id == models.User.id,
            ).where(
                models.UserRole.role_id == sa_role_id,
                models.User.is_active == True,
                models.User.id != user_id,
            )
        )
        other_admins = result.scalars().all()
        if not other_admins:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove system_admin from the last active system administrator",
            )

    # 5. Replace: delete old, insert new
    for ur in list(user.user_roles):
        await db.delete(ur)
    await db.flush()
    for code in codes:
        role = new_roles_by_code[code]
        db.add(models.UserRole(user_id=user_id, role_id=role.id))

    await db.commit()

    # Audit
    from app.domains.identity.audit import record_admin_action
    await record_admin_action(
        db=db,
        actor_user_id="system",  # TODO: pass actor from request context
        action="assign_role",
        target_type="user",
        target_ref=user.username,
        details={"roles": codes},
    )

    # Reload user with new roles — expire to bypass identity map cache
    db.expire_all()
    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.user_roles).selectinload(
                models.UserRole.role
            )
        )
        .where(models.User.id == user_id)
    )
    return result.scalar_one()


async def require_user_permission(
    db: AsyncSession, user: models.User, permission: str
) -> None:
    """Check permission on a given user (reloads from DB to be current)."""
    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.user_roles)
            .selectinload(models.UserRole.role)
            .selectinload(models.Role.role_permissions)
            .selectinload(models.RolePermission.permission)
        )
        .where(models.User.id == user.id)
    )
    fresh_user = result.scalar_one()
    require_permission(fresh_user, permission)


# ── User detail ──────────────────────────────────────────────────────────

async def get_user_by_username(db: AsyncSession, username: str) -> models.User:
    """Get a single user by username with roles and permissions eager-loaded.

    Eager-loads the full chain: user_roles → role → role_permissions → permission.
    This avoids lazy-loading MissingGreenlet errors in sync TestClient contexts
    and eliminates N+1 queries when the caller needs get_user_permissions().

    Raises 404 if not found.
    """
    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.user_roles)
            .selectinload(models.UserRole.role)
            .selectinload(models.Role.role_permissions)
            .selectinload(models.RolePermission.permission)
        )
        .where(models.User.username == username)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found",
        )
    return user


# ── User status management ───────────────────────────────────────────────

async def update_user_status(
    db: AsyncSession,
    username: str,
    data: schemas.UserStatusUpdate,
    actor_user_id: UUID,
) -> models.User:
    """Block, activate, or archive a user.

    Safety rules:
    - Cannot (un)archive yourself
    - Cannot block yourself
    - Archiving is logical (is_archived = true)
    - Blocking sets is_locked = true
    - All changes are audited via admin_audit_events
    """
    user = await get_user_by_username(db, username)

    # Safety: cannot modify yourself
    if str(user.id) == str(actor_user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own status",
        )

    # Protect last active system_admin
    if data.status in ("blocked", "archived"):
        if "system_admin" in user.roles:
            # Check if there's another active system_admin
            result = await db.execute(
                select(models.UserRole)
                .join(models.User, models.UserRole.user_id == models.User.id)
                .join(models.Role, models.UserRole.role_id == models.Role.id)
                .where(
                    models.Role.code == "system_admin",
                    models.User.is_active == True,
                    models.User.is_archived == False,
                    models.User.is_locked == False,
                    models.User.id != user.id,
                )
            )
            other_admins = result.scalars().all()
            if not other_admins:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot block/archive the last active system administrator",
                )

    if data.status == "active":
        user.is_locked = False
        user.locked_until = None
        user.failed_attempts = 0
        user.is_archived = False
        user.is_active = True
    elif data.status == "blocked":
        user.is_locked = True
        user.locked_until = None  # indefinite until admin unblocks
        user.is_archived = False
    elif data.status == "archived":
        user.is_archived = True
        user.archived_at = datetime.now(timezone.utc)
        user.archived_by = actor_user_id
        user.is_active = False

    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Audit
    from app.domains.identity.audit import record_admin_action
    await record_admin_action(
        db=db,
        actor_user_id=str(actor_user_id),
        action=f"{data.status}_user",
        target_type="user",
        target_ref=username,
        details={"reason": data.reason} if data.reason else None,
    )

    await db.commit()
    return await get_user_by_username(db, username)


# ── User RLS scopes management ───────────────────────────────────────────

ALLOWED_RLS_SCOPE_TYPES = frozenset({
    "advertiser_scope", "branch_scope", "store_scope",
    "campaign_scope", "device_scope", "approval_scope", "report_scope",
})


async def update_user_rls_scopes(
    db: AsyncSession,
    username: str,
    data: schemas.UserRlsScopeUpdate,
    actor_user_id: UUID,
) -> models.User:
    """Replace all RLS scopes for a user.

    Deletes existing scopes and inserts new ones.
    Duplicate (user_id, scope_type, scope_value) safely skipped.
    """
    user = await get_user_by_username(db, username)

    # Validate scope types
    for item in data.scopes:
        if item.scope_type not in ALLOWED_RLS_SCOPE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown scope type: {item.scope_type}",
            )

    # Delete existing scopes for this user
    await db.execute(
        sa.delete(models.UserRlsScope).where(
            models.UserRlsScope.user_id == user.id
        )
    )

    # Insert new scopes (deduplicate by unique constraint)
    for item in data.scopes:
        db.add(
            models.UserRlsScope(
                user_id=user.id,
                scope_type=item.scope_type,
                scope_value=item.scope_value,
                is_active=item.is_active,
                created_by=actor_user_id,
                reason=item.reason,
            )
        )

    await db.flush()

    # Audit
    from app.domains.identity.audit import record_admin_action
    scope_summary = [
        f"{s.scope_type}={s.scope_value}"
        for s in data.scopes if s.is_active
    ]
    await record_admin_action(
        db=db,
        actor_user_id=str(actor_user_id),
        action="assign_rls_scopes",
        target_type="rls_scope",
        target_ref=username,
        details={"scopes": scope_summary},
    )

    await db.commit()
    return await get_user_by_username(db, username)


# ── Admin audit ──────────────────────────────────────────────────────────

async def list_admin_audit(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[models.AdminAuditEvent]:
    """List admin audit events, newest first."""
    result = await db.execute(
        select(models.AdminAuditEvent)
        .order_by(models.AdminAuditEvent.occurred_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


# ── User RLS scopes read ─────────────────────────────────────────────────

async def get_user_rls_scopes(db: AsyncSession, user_id: UUID) -> list[dict]:
    """Get active RLS scopes for a user as dicts."""
    result = await db.execute(
        select(models.UserRlsScope)
        .where(
            models.UserRlsScope.user_id == user_id,
            models.UserRlsScope.is_active == True,
        )
    )
    scopes = result.scalars().all()
    return [
        {
            "scope_type": s.scope_type,
            "scope_value": s.scope_value,
            "is_active": s.is_active,
            "created_at": s.created_at,
            "expires_at": s.expires_at,
            "reason": s.reason,
        }
        for s in scopes
    ]
