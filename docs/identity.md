# Identity & Access Domain

## Overview

Identity domain provides authentication (JWT), user management, role-based access control (RBAC), and permission enforcement for the Retail Media Platform.

## Tables (6)

| Table | Purpose |
|-------|---------|
| `users` | Portal users (human + service accounts) |
| `roles` | Named RBAC roles |
| `permissions` | Granular permissions (resource.action) |
| `user_roles` | Many-to-many: users <-> roles |
| `role_permissions` | Many-to-many: roles <-> permissions |
| `refresh_tokens` | SHA-256 hashes of issued refresh tokens |

## Auth Flow

1. `POST /api/auth/login` -> access token (15 min) + refresh token (7 days)
2. All protected endpoints require `Authorization: Bearer ***
3. When access token expires: `POST /api/auth/refresh`
4. Logout: `POST /api/auth/logout` (revokes refresh token)

## Seed

```bash
cd backend
INITIAL_ADMIN_PASSWORD=*** python -m app.domains.identity.seed
```

Idempotent — safe to run multiple times. Creates:
- 8 roles
- 30 permissions
- role-to-permission assignments
- Admin user from env vars (`INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`, `INITIAL_ADMIN_EMAIL`)

## API

| Method | Path | Auth | Permission | Notes |
|--------|------|------|------------|-------|
| POST | `/api/auth/login` | None | — | |
| POST | `/api/auth/refresh` | Refresh token | — | |
| POST | `/api/auth/logout` | Refresh token | — | |
| GET | `/api/auth/me` | Access token | — | Returns roles + permissions |
| GET | `/api/users` | Access token | `users.read` | Returns roles for each user |
| POST | `/api/users` | Access token | `users.create` | If `role_codes` provided, also requires `roles.manage` |
| PUT | `/api/users/{id}/roles` | Access token | `roles.manage` | Replace all roles for a user |
| GET | `/api/roles` | Access token | `roles.read` | |
| GET | `/api/permissions` | Access token | `permissions.read` | |

### POST /api/users

```json
{
  "username": "new_user",
  "password": "***"***  "email": "user@example.com",
  "display_name": "New User",
  "role_codes": ["analyst"]
}
```

- `role_codes` is optional. If omitted, user is created without roles.
- Assigning roles requires BOTH `users.create` AND `roles.manage`.
- `device_service` role cannot be assigned via this endpoint.
- Non-existent role codes return 400.

### PUT /api/users/{id}/roles

```json
{
  "role_codes": ["ad_manager", "analyst"]
}
```

- Requires `roles.manage` permission.
- Completely replaces the user's role list.
- `device_service` role cannot be assigned via this endpoint.
- Cannot remove `system_admin` from the last active system administrator.

### Permission checking

Permissions are loaded from the database on every request (via `selectinload` in `get_current_user_from_token`). After a role change via `PUT /api/users/{id}/roles`, the user's existing access tokens immediately reflect the new permissions — no re-login required.

## Security

- Passwords: bcrypt via `bcrypt` library
- Access tokens: JWT HS256, 15 minutes
- Refresh tokens: JWT HS256, 7 days, stored as SHA-256 hash
- Account lockout: 5 failed attempts -> locked for 15 minutes
- Permission enforcement: checks current user's permission set fresh from DB on every request
- `device_service` role is blocked from user-facing API (reserved for Device Gateway service accounts)

## Future

- LDAP/AD integration (`ldap_dn`, `auth_provider` columns ready)
- MFA (TOTP) — `mfa_enabled`/`mfa_secret` columns ready
- Service accounts (`is_service_account` column ready)
- Audit logging (`auth_events` table — separate step)
