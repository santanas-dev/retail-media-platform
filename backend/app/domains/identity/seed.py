"""
Identity & Access: idempotent seed — roles, permissions, admin user.

Usage:
    cd backend
    INITIAL_ADMIN_PASSWORD=*** python -m app.domains.identity.seed

Environment variables:
    INITIAL_ADMIN_USERNAME  (default: admin)
    INITIAL_ADMIN_PASSWORD  (required — no default)
    INITIAL_ADMIN_EMAIL    (default: admin@localhost)
"""

import asyncio
import os

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.security import hash_password
from app.domains.identity import models


# ── Permission matrix ────────────────────────────────────────────────────

PERMISSIONS = [
    # (code, name, resource, action, description)
    ("users.read", "View users", "users", "read", "View user list"),
    ("users.create", "Create users", "users", "create", "Create new users"),
    ("users.manage", "Manage users", "users", "manage", "Edit, lock, or delete users"),
    ("roles.read", "View roles", "roles", "read", "View role list"),
    ("roles.manage", "Manage roles", "roles", "manage", "Create/edit/delete roles"),
    ("permissions.read", "View permissions", "permissions", "read", "View permission list"),
    ("permissions.manage", "Manage permissions", "permissions", "manage", "Manage permission assignments"),
    ("channels.read", "View channels", "channels", "read", "View channel list"),
    ("devices.read", "View devices", "devices", "read", "View device list and status"),
    ("devices.manage", "Manage devices", "devices", "manage", "Configure and manage devices"),
    ("campaigns.read", "View campaigns", "campaigns", "read", "View campaign list"),
    ("campaigns.create", "Create campaigns", "campaigns", "create", "Create new campaigns"),
    ("campaigns.manage", "Manage campaigns", "campaigns", "manage", "Edit/delete campaigns"),
    ("campaigns.approve", "Approve campaigns", "campaigns", "approve", "Approve or reject campaigns"),
    ("media.manage", "Manage media", "media", "manage", "Upload and manage media assets"),
    ("media.read", "View media", "media", "read", "View media assets and metadata"),
    ("media.approve", "Approve media", "media", "approve", "Approve or reject creative assets"),
    ("reports.read", "View reports", "reports", "read", "View reports"),
    ("reports.export", "Export reports", "reports", "export", "Export reports to file"),
    ("audit.read", "View audit logs", "audit", "read", "View audit trail"),
    ("emergency.manage", "Emergency actions", "emergency", "manage", "Emergency stop all campaigns"),
    ("organization.read", "View organization", "organization", "read", "View branches, clusters, stores"),
    ("organization.manage", "Manage organization", "organization", "manage", "Create/edit branches, clusters, stores"),
    ("channels.manage", "Manage channels", "channels", "manage", "Create/edit channels"),
    ("advertisers.read", "View advertisers", "advertisers", "read", "View advertiser list"),
    ("advertisers.manage", "Manage advertisers", "advertisers", "manage", "Create/edit advertisers"),
    ("brands.read", "View brands", "brands", "read", "View brand list"),
    ("brands.manage", "Manage brands", "brands", "manage", "Create/edit brands"),
    ("contracts.read", "View contracts", "contracts", "read", "View contract list"),
    ("contracts.manage", "Manage contracts", "contracts", "manage", "Create/edit contracts"),
    ("orders.read", "View orders", "orders", "read", "View order list"),
    ("orders.manage", "Manage orders", "orders", "manage", "Create/edit orders"),
    ("inventory.read", "View inventory", "inventory", "read", "View inventory units and capacity"),
    ("inventory.manage", "Manage inventory", "inventory", "manage", "Create/edit inventory units and capacity"),
    ("bookings.read", "View bookings", "bookings", "read", "View campaign bookings"),
    ("bookings.manage", "Manage bookings", "bookings", "manage", "Create/edit campaign bookings"),
    ("bookings.approve", "Approve bookings", "bookings", "approve", "Confirm campaign bookings"),
]

# ── Roles ────────────────────────────────────────────────────────────────

ROLES = [
    # (code, name, description)
    ("system_admin", "System Administrator", "Full system access"),
    ("security_admin", "Security Administrator", "User management and audit"),
    ("ad_manager", "Ad Manager", "Campaign and media management"),
    ("approver", "Approver", "Campaign approval"),
    ("analyst", "Analyst", "Reports and analytics"),
    ("advertiser", "Advertiser", "Campaign requests and own reports"),
    ("operations", "Operations", "Device management and monitoring"),
    ("device_service", "Device Service", "Technical role for Device Gateway"),
]

# ── Role → permission mapping ────────────────────────────────────────────

ROLE_PERMISSIONS = {
    "system_admin": [
        "users.read", "users.create", "users.manage",
        "roles.read", "roles.manage",
        "permissions.read", "permissions.manage",
        "channels.read", "channels.manage", "devices.read", "devices.manage",
        "organization.read", "organization.manage",
        "advertisers.read", "advertisers.manage",
        "brands.read", "brands.manage",
        "contracts.read", "contracts.manage",
        "orders.read", "orders.manage",
        "campaigns.read", "campaigns.create", "campaigns.manage", "campaigns.approve",
        "media.read", "media.manage", "media.approve",
        "inventory.read", "inventory.manage",
        "bookings.read", "bookings.manage", "bookings.approve",
        "reports.read", "reports.export",
        "audit.read",
        "emergency.manage",
    ],
    "security_admin": [
        "users.read", "users.manage",
        "roles.read", "roles.manage",
        "permissions.read",
        "organization.read", "channels.read",
        "advertisers.read", "brands.read", "contracts.read", "orders.read",
        "media.read",
        "campaigns.read",
        "inventory.read",
        "bookings.read",
        "audit.read",
    ],
    "ad_manager": [
        "channels.read", "devices.read",
        "organization.read",
        "advertisers.read", "advertisers.manage",
        "brands.read", "brands.manage",
        "contracts.read", "contracts.manage",
        "orders.read", "orders.manage",
        "campaigns.read", "campaigns.create", "campaigns.manage",
        "media.read", "media.manage",
        "inventory.read",
        "bookings.read", "bookings.manage",
        "reports.read",
    ],
    "approver": [
        "channels.read", "devices.read",
        "organization.read",
        "advertisers.read", "brands.read", "contracts.read", "orders.read",
        "campaigns.read", "campaigns.approve",
        "media.read", "media.approve",
        "inventory.read",
        "bookings.read", "bookings.approve",
        "reports.read",
    ],
    "analyst": [
        "channels.read", "devices.read",
        "organization.read",
        "advertisers.read", "brands.read", "contracts.read", "orders.read",
        "campaigns.read",
        "media.read",
        "inventory.read",
        "bookings.read",
        "reports.read", "reports.export",
    ],
    "advertiser": [
        "campaigns.read",
        "reports.read",
    ],
    "operations": [
        "channels.read", "channels.manage", "devices.read", "devices.manage",
        "organization.read",
        "advertisers.read",
        "media.read",
        "campaigns.read",
        "inventory.read", "inventory.manage",
        "bookings.read",
    ],
    "device_service": [
        # No interactive permissions — service account only
    ],
}


async def seed() -> None:
    """Run idempotent seed."""
    settings = get_settings()

    if not settings.INITIAL_ADMIN_PASSWORD:
        print("ERROR: INITIAL_ADMIN_PASSWORD is required for seed.")
        print("Usage: INITIAL_ADMIN_PASSWORD=*** python -m app.domains.identity.seed")
        return

    engine = get_engine(settings)
    async with engine.begin() as conn:
        # ── Permissions ────────────────────────────────────────────
        for code, name, resource, action, description in PERMISSIONS:
            await conn.execute(
                pg_insert(models.Permission)
                .values(
                    code=code,
                    name=name,
                    resource=resource,
                    action=action,
                    description=description,
                )
                .on_conflict_do_nothing(index_elements=["code"])
            )

        # ── Roles ──────────────────────────────────────────────────
        for code, name, description in ROLES:
            await conn.execute(
                pg_insert(models.Role)
                .values(
                    code=code,
                    name=name,
                    description=description,
                    is_system=True,
                )
                .on_conflict_do_nothing(index_elements=["code"])
            )

        # ── Role → permission assignments ─────────────────────────
        # Get role IDs
        role_result = await conn.execute(select(models.Role))
        roles_by_code = {r.code: r.id for r in role_result}

        # Get permission IDs
        perm_result = await conn.execute(select(models.Permission))
        perms_by_code = {p.code: p.id for p in perm_result}

        for role_code, perm_codes in ROLE_PERMISSIONS.items():
            role_id = roles_by_code.get(role_code)
            if not role_id:
                continue
            for perm_code in perm_codes:
                perm_id = perms_by_code.get(perm_code)
                if not perm_id:
                    continue
                await conn.execute(
                    pg_insert(models.RolePermission)
                    .values(role_id=role_id, permission_id=perm_id)
                    .on_conflict_do_nothing(
                        index_elements=["role_id", "permission_id"]
                    )
                )

        # ── Admin user ─────────────────────────────────────────────
        admin_result = await conn.execute(
            select(models.User.id).where(
                models.User.username == settings.INITIAL_ADMIN_USERNAME
            )
        )
        admin_id = admin_result.scalar_one_or_none()

        if admin_id is None:
            # Create admin user
            admin_result = await conn.execute(
                pg_insert(models.User)
                .values(
                    username=settings.INITIAL_ADMIN_USERNAME,
                    email=settings.INITIAL_ADMIN_EMAIL,
                    password_hash=hash_password(settings.INITIAL_ADMIN_PASSWORD),
                    display_name="System Administrator",
                    is_active=True,
                )
                .on_conflict_do_nothing(index_elements=["username"])
                .returning(models.User.id)
            )
            row = admin_result.fetchone()
            if row:
                admin_id = row[0]
                print(f"Created admin user: {settings.INITIAL_ADMIN_USERNAME}")
            else:
                print(f"Admin user already exists: {settings.INITIAL_ADMIN_USERNAME}")

        # Assign system_admin role to admin
        if admin_id:
            admin_role_id = roles_by_code.get("system_admin")
            if admin_role_id:
                await conn.execute(
                    pg_insert(models.UserRole)
                    .values(user_id=admin_id, role_id=admin_role_id)
                    .on_conflict_do_nothing(
                        index_elements=["user_id", "role_id"]
                    )
                )

    print("Seed complete.")
    print(f"  Roles: {len(ROLES)}")
    print(f"  Permissions: {len(PERMISSIONS)}")
    print(f"  Admin: {settings.INITIAL_ADMIN_USERNAME}")


def main():
    """Entry point for `python -m app.domains.identity.seed`."""
    asyncio.run(seed())


if __name__ == "__main__":
    main()
