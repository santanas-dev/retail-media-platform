"""Identity & Access: FastAPI router - auth, users, roles, permissions."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db, require_permission
from app.domains.identity import models, schemas, service

router = APIRouter(prefix="/api", tags=["identity"])


# ── Auth ─────────────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=schemas.TokenResponse)
async def login(
    body: schemas.LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and receive access + refresh tokens."""
    settings = get_settings()
    return await service.authenticate_user(
        db=db,
        username=body.username,
        password=body.password,
        settings=settings,
    )


@router.post("/auth/refresh", response_model=schemas.TokenResponse)
async def refresh(
    body: schemas.RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh an expired access token using a refresh token."""
    settings = get_settings()
    return await service.refresh_access_token(
        db=db,
        refresh_token_str=body.refresh_token,
        settings=settings,
    )


@router.post("/auth/logout", status_code=204)
async def logout(
    body: schemas.LogoutRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revoke a refresh token (logout)."""
    settings = get_settings()
    await service.logout(
        db=db,
        refresh_token_str=body.refresh_token,
        settings=settings,
    )


@router.get("/auth/me", response_model=schemas.UserMeResponse)
async def me(
    current_user: models.User = Depends(get_current_user),
):
    """Get current authenticated user with roles and permissions."""
    return schemas.UserMeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        is_locked=current_user.is_locked,
        auth_provider=current_user.auth_provider,
        roles=service.get_user_roles(current_user),
        permissions=service.get_user_permissions(current_user),
    )


# ── Users ────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[schemas.UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("users.read")),
):
    """List all users."""
    users = await service.list_users(db, skip=skip, limit=limit)
    return users


@router.post("/users", response_model=schemas.UserResponse, status_code=201)
async def create_user(
    body: schemas.UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a new user. Requires users.create.
    If role_codes is provided, also requires roles.manage."""
    # Always require users.create
    service.require_permission(current_user, "users.create")
    # If roles are being assigned, also require roles.manage
    if body.role_codes:
        await service.require_user_permission(db, current_user, "roles.manage")
    user = await service.create_user(db, body)
    return user


@router.put("/users/{user_id}/roles", response_model=schemas.UserResponse)
async def update_user_roles(
    user_id: UUID,
    body: schemas.UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("roles.manage")),
):
    """Replace all roles for a user. Requires roles.manage."""
    return await service.update_user_roles(db, user_id, body)


# ── Roles ────────────────────────────────────────────────────────────────

@router.get("/roles", response_model=list[schemas.RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("roles.read")),
):
    """List all roles."""
    roles = await service.list_roles(db)
    return roles


# ── Permissions ──────────────────────────────────────────────────────────

@router.get("/permissions", response_model=list[schemas.PermissionResponse])
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("permissions.read")),
):
    """List all permissions."""
    perms = await service.list_permissions(db)
    return perms


# ── User Detail ──────────────────────────────────────────────────────────

@router.get("/users/{username}", response_model=schemas.UserMeResponse)
async def get_user(
    username: str,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("users.read")),
):
    """Get a single user by username."""
    user = await service.get_user_by_username(db, username)
    rls = await service.get_user_rls_scopes(db, user.id)
    return schemas.UserMeResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_locked=user.is_locked,
        auth_provider=user.auth_provider,
        roles=service.get_user_roles(user),
        permissions=service.get_user_permissions(user),
    )


# ── User Status ──────────────────────────────────────────────────────────

@router.patch("/users/{username}/status", response_model=schemas.UserMeResponse)
async def update_user_status(
    username: str,
    body: schemas.UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Block, activate, or archive a user. Requires users.manage."""
    service.require_permission(current_user, "users.manage")
    user = await service.update_user_status(
        db, username, body, current_user.id
    )
    rls = await service.get_user_rls_scopes(db, user.id)
    return schemas.UserMeResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_locked=user.is_locked,
        auth_provider=user.auth_provider,
        roles=service.get_user_roles(user),
        permissions=service.get_user_permissions(user),
    )


# ── User RLS Scopes ──────────────────────────────────────────────────────

@router.patch("/users/{username}/rls-scopes", response_model=schemas.UserMeResponse)
async def update_user_rls_scopes(
    username: str,
    body: schemas.UserRlsScopeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Replace all RLS scopes for a user. Requires roles.manage."""
    service.require_permission(current_user, "roles.manage")
    user = await service.update_user_rls_scopes(
        db, username, body, current_user.id
    )
    rls = await service.get_user_rls_scopes(db, user.id)
    return schemas.UserMeResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_locked=user.is_locked,
        auth_provider=user.auth_provider,
        roles=service.get_user_roles(user),
        permissions=service.get_user_permissions(user),
    )


# ── Admin Audit ──────────────────────────────────────────────────────────

@router.get("/admin/audit", response_model=list[schemas.AdminAuditResponse])
async def list_admin_audit(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_permission("audit.read")),
):
    """List admin audit events. Requires audit.read."""
    events = await service.list_admin_audit(db, skip=skip, limit=limit)
    return [
        schemas.AdminAuditResponse(
            id=e.id,
            action=e.action,
            target_type=e.target_type,
            target_ref=e.target_ref,
            occurred_at=e.occurred_at,
            details_summary=e.details_json,
        )
        for e in events
    ]
