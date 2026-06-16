"""
Identity & Access: FastAPI router — auth, users, roles, permissions.
"""

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
    _: models.User = Depends(require_permission("users.create")),
):
    """Create a new user. Requires users.create permission."""
    user = await service.create_user(db, body)
    return user


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
