# Security Hardening Plan (45.6)

## Current State

Portal uses:
- Session middleware (`starlette.middleware.sessions.SessionMiddleware`)
- Cookie: `portal_session`, `max_age=3600`, `same_site=lax`, `https_only=False`
- No CSRF protection on forms
- No rate limiting
- No session expiration enforcement beyond cookie max_age

## Hardening Plan

### 1. Rate Limiting

| Endpoint | Limit | Window | Rationale |
|----------|-------|--------|-----------|
| `/login` | 10 | 5 min | Brute-force prevention |
| `/creatives/upload` | 5 | 1 min | DoS prevention |
| `/approvals/decide` | 20 | 1 min | Prevents approval spam |
| All POST | 60 | 1 min | Global write throttle |

Implementation: in-memory token bucket (portal), Redis for production.
Graceful: returns 429 with Russian error page, not raw JSON.

### 2. CSRF Protection

Server-side forms need CSRF tokens:
- Generate per-session CSRF token at login
- Embed as hidden `<input>` in all `<form>` tags
- Validate on POST/PUT/DELETE
- Reject with 403 if missing/invalid

Implementation: middleware that injects token into Jinja2 context,
validates on mutation endpoints.

### 3. Cookie Flags

Current: `same_site=lax`, `https_only=False`
Plan:
- `HttpOnly: true` — already set via SessionMiddleware
- `Secure: true` — enable when TLS is deployed
- `SameSite: Strict` — stronger than Lax
- Shorter `max_age`: 30 min with sliding expiry

### 4. Session Expiration

- Server-side session store already supports expiration
- Add absolute timeout: 8 hours from login, regardless of activity
- Invalidate session on role change (already done via `/me` re-fetch)

### 5. Audit Trail Viewer

- `/admin/audit` — server-side rendered table
- Filters: user, action type, date range, object type
- No raw UUIDs, no technical codes
- Pagination: 50 per page
- Export: CSV (same sanitization as reports)
- RBAC: `audit.read`

### 6. Password Policy

- Min 8 characters
- Require: uppercase, lowercase, digit
- No common passwords (check against top-1000 list)
- Password change on first login for new accounts

### Implementation Order

1. CSRF tokens (critical — prevents form forgery)
2. Rate limiting (high — prevents brute force)
3. Cookie hardening (medium — requires TLS for Secure flag)
4. Session expiration (medium)
5. Audit viewer (nice-to-have)
6. Password policy (backend-side, requires backend changes)

### What NOT to do
- No JWT in URL or localStorage
- No client-side crypto
- No roll-your-own auth
- No exposing internal permission names in UI
