# Identity & Access Domain

## Overview

Identity domain provides authentication (JWT), user management, role-based access control (RBAC), and permission enforcement for the Retail Media Platform.

## Tables (6)

| Table | Purpose |
|-------|---------|
| `users` | Portal users (human + service accounts) |
| `roles` | Named RBAC roles |
| `permissions` | Granular permissions (resource.action) |
| `user_roles` | Many-to-many: users ↔ roles |
| `role_permissions` | Many-to-many: roles ↔ permissions |
| `refresh_tokens` | SHA-256 hashes of issued refresh tokens |

## Auth Flow

1. `POST /api/auth/login` → access token (15 min) + refresh token (7 days)
2. All protected endpoints require `Authorization: Bearer <access_token>`
3. When access token expires: `POST /api/auth/refresh`
4. Logout: `POST /api/auth/logout` (revokes refresh token)

## Seed

```bash
cd backend
INITIAL_ADMIN_PASSWORD=*** python -m app.domains.identity.seed
```

Idempotent — safe to run multiple times. Creates:
- 8 roles
- 19 permissions
- role-to-permission assignments
- Admin user from env vars (`INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`, `INITIAL_ADMIN_EMAIL`)

## API

| Method | Path | Auth | Permission |
|--------|------|------|------------|
| POST | `/api/auth/login` | None | — |
| POST | `/api/auth/refresh` | Refresh token | — |
| POST | `/api/auth/logout` | Refresh token | — |
| GET | `/api/auth/me` | Access token | — |
| GET | `/api/users` | Access token | `users.read` |
| POST | `/api/users` | Access token | `users.create` |
| GET | `/api/roles` | Access token | `roles.read` |
| GET | `/api/permissions` | Access token | `permissions.read` |

## Security

- Passwords: bcrypt via `bcrypt` library
- Access tokens: JWT HS256, 15 minutes
- Refresh tokens: JWT HS256, 7 days, stored as SHA-256 hash
- Account lockout: 5 failed attempts → locked for 15 minutes
- Permission enforcement: decorator-based, checks current user's permission set

## Future

- LDAP/AD integration (`ldap_dn`, `auth_provider` columns ready)
- MFA (TOTP) — `mfa_enabled`/`mfa_secret` columns ready
- Service accounts (`is_service_account` column ready)
- Audit logging (`auth_events` table — separate step)
