"""
Identity & Access: SQLAlchemy ORM models.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

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
