"""
RLS (Row-Level Security) enforcement layer.

Resolves user scopes from `user_rls_scopes` table and provides 
query-filtering helpers for each domain.

Architecture:
- `resolve_user_scope_context(db, user)` → UserScopeContext (concrete IDs)
- `requires_rls(scope_context)` → True if RLS should be applied (non-admin)
- Per-domain helpers: apply WHERE clauses to SELECT queries.

Admin roles (system_admin, security_admin): empty scope context = full access.
"""

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.domains.identity.models import User, UserRlsScope
from app.domains.identity.service import get_user_roles


# Admin role codes — users with these roles bypass RLS entirely.
ADMIN_ROLE_CODES: frozenset[str] = frozenset({"system_admin", "security_admin"})


@dataclass
class UserScopeContext:
    """Concrete scope identifiers for query filtering.

    Empty lists mean NO restriction (admin/global access).
    Non-empty lists mean the user can only see these specific objects.
    """
    # Advertiser IDs (resolved from advertiser_scope + brand_scope)
    advertiser_ids: list[UUID] = field(default_factory=list)
    # Branch IDs (resolved from branch_scope)
    branch_ids: list[UUID] = field(default_factory=list)
    # Store IDs (resolved from store_scope)
    store_ids: list[UUID] = field(default_factory=list)
    # Device codes (resolved from device_scope)
    device_codes: list[str] = field(default_factory=list)
    # Campaign codes (resolved from campaign_scope)
    campaign_codes: list[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        """True if user has full access (no scope restriction)."""
        return (
            not self.advertiser_ids
            and not self.branch_ids
            and not self.store_ids
            and not self.device_codes
            and not self.campaign_codes
        )

    @property
    def is_advertiser_scoped(self) -> bool:
        """True if advertiser-level RLS should be applied."""
        return bool(self.advertiser_ids)

    @property
    def is_store_scoped(self) -> bool:
        """True if store-level RLS should be applied."""
        return bool(self.store_ids)

    @property
    def is_branch_scoped(self) -> bool:
        """True if branch-level RLS should be applied."""
        return bool(self.branch_ids)


async def resolve_user_scope_context(
    db: AsyncSession,
    user: User,
) -> UserScopeContext:
    """Resolve RLS scopes from user_rls_scopes to concrete domain IDs.

    Returns UserScopeContext with empty lists (full access) if user is admin
    (system_admin or security_admin role).
    """
    role_codes = get_user_roles(user)

    # Admin roles bypass RLS entirely
    if ADMIN_ROLE_CODES & set(role_codes):
        return UserScopeContext()

    # Load active scopes
    result = await db.execute(
        select(UserRlsScope)
        .where(
            UserRlsScope.user_id == user.id,
            UserRlsScope.is_active == True,
        )
    )
    scopes = result.scalars().all()

    if not scopes:
        # No scopes assigned — default to empty (no access, except public endpoints)
        return UserScopeContext()

    ctx = UserScopeContext()

    for s in scopes:
        scope_type = s.scope_type
        scope_value = s.scope_value

        if scope_type == "advertiser_scope":
            try:
                ctx.advertiser_ids.append(UUID(scope_value))
            except (ValueError, AttributeError):
                pass

        elif scope_type == "brand_scope":
            # Resolve brand → advertiser
            from app.domains.advertisers.models import Brand
            br_result = await db.execute(
                select(Brand.advertiser_id).where(Brand.id == UUID(scope_value))
            )
            adv_id = br_result.scalar_one_or_none()
            if adv_id and adv_id not in ctx.advertiser_ids:
                ctx.advertiser_ids.append(adv_id)

        elif scope_type == "branch_scope":
            # Resolve branch code → branch ID
            from app.domains.organization.models import Branch
            br_result = await db.execute(
                select(Branch.id).where(Branch.code == scope_value)
            )
            branch_id = br_result.scalar_one_or_none()
            if branch_id:
                ctx.branch_ids.append(branch_id)

        elif scope_type == "store_scope":
            # Resolve store code → store ID
            from app.domains.organization.models import Store
            st_result = await db.execute(
                select(Store.id).where(Store.code == scope_value)
            )
            store_id = st_result.scalar_one_or_none()
            if store_id:
                ctx.store_ids.append(store_id)

        elif scope_type == "device_scope":
            ctx.device_codes.append(scope_value)

        elif scope_type == "campaign_scope":
            ctx.campaign_codes.append(scope_value)

    return ctx


def requires_rls(ctx: UserScopeContext) -> bool:
    """True if at least one scope dimension is restricted."""
    return not ctx.is_admin


# ── Query-level RLS filters ──────────────────────────────────────────

def apply_advertiser_rls(
    query: Select,
    ctx: UserScopeContext,
    advertiser_id_column,
) -> Select:
    """Filter query by advertiser scope.

    Args:
        query: SQLAlchemy SELECT statement
        ctx: Resolved UserScopeContext
        advertiser_id_column: The column containing advertiser_id (e.g., Campaign.advertiser_id)
    """
    if not ctx.is_advertiser_scoped:
        return query
    if not ctx.advertiser_ids:
        # Scoped but no advertisers matched — return empty
        return query.where(advertiser_id_column == None).where(
            advertiser_id_column != None
        )  # always-false
    return query.where(advertiser_id_column.in_(ctx.advertiser_ids))


def apply_store_rls(
    query: Select,
    ctx: UserScopeContext,
    store_id_column,
) -> Select:
    """Filter query by store scope."""
    if not ctx.is_store_scoped:
        return query
    if not ctx.store_ids:
        return query.where(store_id_column == None).where(store_id_column != None)
    return query.where(store_id_column.in_(ctx.store_ids))


def apply_branch_rls(
    query: Select,
    ctx: UserScopeContext,
    branch_id_column,
) -> Select:
    """Filter query by branch scope."""
    if not ctx.is_branch_scoped:
        return query
    if not ctx.branch_ids:
        return query.where(branch_id_column == None).where(branch_id_column != None)
    return query.where(branch_id_column.in_(ctx.branch_ids))


def assert_object_in_advertiser_scope(
    advertiser_id: UUID,
    ctx: UserScopeContext,
    operation: str = "access",
) -> None:
    """Raise 404 if object's advertiser is outside user scope.

    Uses 404 (not 403) to avoid leaking object existence.
    """
    from fastapi import HTTPException, status as http_status

    if not ctx.is_admin and ctx.is_advertiser_scoped:
        if advertiser_id not in ctx.advertiser_ids:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found or {operation} not permitted",
            )


def assert_object_in_store_scope(
    store_id: UUID,
    ctx: UserScopeContext,
    operation: str = "access",
) -> None:
    """Raise 404 if object's store is outside user scope."""
    from fastapi import HTTPException, status as http_status

    if not ctx.is_admin and ctx.is_store_scoped:
        if store_id not in ctx.store_ids:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found or {operation} not permitted",
            )


def assert_object_in_scope_by_device_code(
    device_code: str,
    ctx: UserScopeContext,
    operation: str = "access",
) -> None:
    """Raise 404 if device_code is outside user device_scope."""
    from fastapi import HTTPException, status as http_status

    if not ctx.is_admin and ctx.device_codes:
        if device_code not in ctx.device_codes:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found or {operation} not permitted",
            )
