"""
Identity & Access: SQLAlchemy ORM models.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

import sqlalchemy as sa  # for __table_args__ Index/UniqueConstraint references

from app.core.database import Base


class User(Base):
    """Portal user (human or service account)."""

    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255))

    # Status
    is_active = Column(Boolean, server_default=func.text("true"))
    is_locked = Column(Boolean, server_default=func.text("false"))
    locked_until = Column(DateTime(timezone=True))
    failed_attempts = Column(Integer, server_default=func.text("0"))

    # MFA (architectural preparation, not implemented yet)
    mfa_enabled = Column(Boolean, server_default=func.text("false"))
    mfa_secret = Column(String(255))

    # Authentication provider
    auth_provider = Column(String(50), server_default=func.text("'local'"))
    is_service_account = Column(Boolean, server_default=func.text("false"))
    ldap_dn = Column(String(512))

    # Activity
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Archived (soft delete)
    is_archived = Column(Boolean, server_default=func.text("false"))
    archived_at = Column(DateTime(timezone=True))
    archived_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    user_roles = relationship(
        "UserRole",
        back_populates="user",
        foreign_keys="[UserRole.user_id]",
        lazy="selectin",
    )
    refresh_tokens = relationship("RefreshToken", back_populates="user", lazy="selectin")

    @property
    def roles(self) -> list[str]:
        """Convenience: list of role codes for serialization."""
        return [ur.role.code for ur in self.user_roles if ur.role]

    @property
    def permissions(self) -> list[str]:
        """Convenience: list of permission codes for serialization."""
        result: set[str] = set()
        for ur in self.user_roles:
            if ur.role:
                for rp in ur.role.role_permissions:
                    result.add(rp.permission.code)
        return sorted(result)


class Role(Base):
    """Named role (RBAC)."""

    __tablename__ = "roles"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    is_system = Column(Boolean, server_default=func.text("false"))
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    user_roles = relationship("UserRole", back_populates="role", lazy="selectin")
    role_permissions = relationship(
        "RolePermission", back_populates="role", lazy="selectin"
    )


class Permission(Base):
    """Granular permission (action on resource)."""

    __tablename__ = "permissions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    resource = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    description = Column(Text)

    # Relationships
    role_permissions = relationship(
        "RolePermission", back_populates="permission", lazy="selectin"
    )


class UserRole(Base):
    """Many-to-many: users ↔ roles."""

    __tablename__ = "user_roles"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    assigned_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    user = relationship(
        "User",
        back_populates="user_roles",
        foreign_keys=[user_id],
    )
    role = relationship("Role", back_populates="user_roles")


class RolePermission(Base):
    """Many-to-many: roles ↔ permissions."""

    __tablename__ = "role_permissions"

    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    permission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    # Relationships
    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class RefreshToken(Base):
    """Stores SHA-256 hash of issued refresh tokens."""

    __tablename__ = "refresh_tokens"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(255), unique=True, nullable=False)
    jti = Column(String(255), unique=True, nullable=False)
    device_info = Column(String(512))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, server_default=func.text("false"))
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    revoked_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")


class UserRlsScope(Base):
    """RLS scope assignment for a user.

    Each row represents one scope grant — e.g. branch_scope=central,
    store_scope=store-001.  Scopes of the same type are OR'd (union).
    Scopes of different types are AND'd (intersection).
    """

    __tablename__ = "user_rls_scopes"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    scope_type = Column(
        String(64),
        nullable=False,
        comment="advertiser_scope | branch_scope | store_scope | campaign_scope | device_scope | approval_scope | report_scope",
    )
    scope_value = Column(String(255), nullable=False)
    starts_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, server_default=func.text("true"))
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    reason = Column(String(512))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        sa.UniqueConstraint("user_id", "scope_type", "scope_value",
                            name="uq_user_rls_scope"),
    )


class LoginAuditEvent(Base):
    """Immutable log of every login attempt (success or failure)."""

    __tablename__ = "login_audit_events"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    username = Column(String(100), nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    success = Column(Boolean, nullable=False)
    result_code = Column(String(50))
    # result_code: 'success' | 'invalid_credentials' | 'locked' | 'inactive' | 'archived' | 'service_account'
    reason_code = Column(String(100))
    occurred_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ip_hash = Column(String(128))
    user_agent_hash = Column(String(128))

    __table_args__ = (
        sa.Index("idx_login_audit_user_time", "user_id", "occurred_at"),
        sa.Index("idx_login_audit_time", "occurred_at"),
    )


class AdminAuditEvent(Base):
    """Immutable log of administrative actions (user/role/RLS changes)."""

    __tablename__ = "admin_audit_events"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    actor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action = Column(String(100), nullable=False)
    # action: 'create_user' | 'block_user' | 'archive_user' | 'unblock_user' |
    #         'assign_role' | 'remove_role' | 'assign_rls_scope' | 'remove_rls_scope'
    target_type = Column(String(64))
    # target_type: 'user' | 'role' | 'rls_scope'
    target_ref = Column(String(255))
    # opaque reference: username, role code, or scope type+value
    details_json = Column(JSONB)
    # structured audit details — only safe fields (no secrets/tokens/passwords)
    occurred_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    actor = relationship("User", foreign_keys=[actor_user_id])

    __table_args__ = (
        sa.Index("idx_admin_audit_actor_time", "actor_user_id", "occurred_at"),
        sa.Index("idx_admin_audit_time", "occurred_at"),
        sa.Index("idx_admin_audit_action_time", "action", "occurred_at"),
    )


class MfaSettings(Base):
    """Per-user MFA configuration.

    Secret is stored as an opaque reference — the actual TOTP secret lives
    in a dedicated secure storage, not in this table.
    """

    __tablename__ = "mfa_settings"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    mfa_required = Column(Boolean, server_default=func.text("false"))
    mfa_enabled = Column(Boolean, server_default=func.text("false"))
    method = Column(String(20))
    # method: 'totp' (future: 'webauthn', 'sms')
    secret_ref = Column(String(255))
    # opaque reference to secure storage; NOT the raw secret
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
