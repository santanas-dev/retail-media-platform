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


# ── User Status ──────────────────────────────────────────────────────────

class UserStatusUpdate(BaseModel):
    """PATCH /api/users/{username}/status"""
    status: str = Field(..., pattern="^(active|blocked|archived)$")
    reason: str | None = Field(None, max_length=512)


# ── User RLS Scopes ──────────────────────────────────────────────────────

class RlsScopeItem(BaseModel):
    """Single RLS scope assignment."""
    scope_type: str = Field(
        ...,
        pattern="^(advertiser_scope|branch_scope|store_scope|"
                "campaign_scope|device_scope|approval_scope|report_scope)$",
    )
    scope_value: str = Field(..., min_length=1, max_length=255)
    is_active: bool = True
    reason: str | None = Field(None, max_length=512)


class UserRlsScopeUpdate(BaseModel):
    """PATCH /api/users/{username}/rls-scopes"""
    scopes: list[RlsScopeItem] = Field(min_length=0, max_length=100)


# ── RLS Scope Response ───────────────────────────────────────────────────

class RlsScopeResponse(BaseModel):
    """Single RLS scope in response."""
    scope_type: str
    scope_value: str
    is_active: bool
    created_at: datetime | None = None
    expires_at: datetime | None = None
    reason: str | None = None


# ── Admin Audit ──────────────────────────────────────────────────────────

class AdminAuditResponse(BaseModel):
    """GET /api/admin/audit — single audit event."""
    id: UUID
    action: str
    target_type: str | None = None
    target_ref: str | None = None
    occurred_at: datetime
    details_summary: dict | None = None

    model_config = {"from_attributes": True}
