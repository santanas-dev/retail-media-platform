"""
Identity & Access: Pydantic schemas for request/response validation.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ── Auth ────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """POST /api/auth/login"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Response containing access + refresh tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """POST /api/auth/refresh"""
    refresh_token: str


class LogoutRequest(BaseModel):
    """POST /api/auth/logout"""
    refresh_token: str


# ── User ────────────────────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    """POST /api/users"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    email: EmailStr | None = None
    display_name: str | None = Field(None, max_length=255)
    role_codes: list[str] | None = None


class UserResponse(BaseModel):
    """User in list / detail responses (no password hash)."""
    id: UUID
    username: str
    email: str | None
    display_name: str | None
    is_active: bool
    is_locked: bool
    auth_provider: str
    is_service_account: bool
    roles: list[str]
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserMeResponse(BaseModel):
    """GET /api/auth/me — current user + roles + permissions."""
    id: UUID
    username: str
    email: str | None
    display_name: str | None
    is_active: bool
    is_locked: bool
    auth_provider: str
    roles: list[str]
    permissions: list[str]

    model_config = {"from_attributes": True}


# ── Role ────────────────────────────────────────────────────────────────

class RoleResponse(BaseModel):
    """GET /api/roles"""
    id: UUID
    code: str
    name: str
    description: str | None
    is_system: bool

    model_config = {"from_attributes": True}


# ── Permission ──────────────────────────────────────────────────────────

class PermissionResponse(BaseModel):
    """GET /api/permissions"""
    id: UUID
    code: str
    name: str
    resource: str
    action: str
    description: str | None

    model_config = {"from_attributes": True}


# ── User Roles ──────────────────────────────────────────────────────────

class UserRoleUpdate(BaseModel):
    """PUT /api/users/{user_id}/roles"""
    role_codes: list[str] = Field(min_length=1)
