"""Portal RBAC guard foundation (Step 36.7).

Checks portal user permissions against backend-provided permission set.
Uses server-side token store — never exposes tokens to caller.

Architecture:
- get_current_user_permissions(request) → set of permission codes
- require_portal_permission(request, permission) → raises 403 or redirects
- Permission check uses the permissions from /api/auth/me (already cached
  in server-side session after login).

For /admin page: requires "users.read" AND "roles.read".
"""

from typing import FrozenSet

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from portal_session import get_current_portal_user, get_portal_tokens
from backend_client import BackendClient

__all__ = [
    "require_portal_permission",
    "require_admin_access",
    "require_auth_for_page",
    "get_current_user_permissions",
    "refresh_user_permissions",
    "ADMIN_REQUIRED_PERMISSIONS",
    "PAGE_PERMISSION_MAP",
    "forbidden_response",
]

# Permissions required to access /admin page (read-only)
ADMIN_REQUIRED_PERMISSIONS: FrozenSet[str] = frozenset({
    "users.read",
    "roles.read",
})

_client = BackendClient()


async def get_current_user_permissions(request: Request) -> FrozenSet[str]:
    """Return current user's backend permissions (cached in server-side session).

    Returns empty frozenset if not authenticated.
    """
    user = get_current_portal_user(request)
    if not user:
        return frozenset()

    # Permissions are stored in the server-side session after login
    tokens = get_portal_tokens(request)
    if not tokens.get("access_token"):
        return frozenset()

    # Call /api/auth/me to get current permissions
    result = await _client.me(tokens["access_token"])
    if not result["ok"]:
        return frozenset()

    perms = result["data"].get("permissions", [])
    return frozenset(perms)


async def refresh_user_permissions(request: Request) -> FrozenSet[str]:
    """Force-refresh permissions from backend (use after role changes)."""
    return await get_current_user_permissions(request)


def _has_admin_access(permissions: FrozenSet[str]) -> bool:
    """Check if permission set grants read-only admin access."""
    return ADMIN_REQUIRED_PERMISSIONS.issubset(permissions)


async def require_portal_permission(
    request: Request,
    permission: str,
    *,
    redirect_to_login: bool = True,
) -> Response | None:
    """Check portal user has a backend permission. Returns None if allowed.

    Returns:
        None — permission granted, proceed
        RedirectResponse — unauthenticated, redirects to /login
        Response(403) — authenticated but insufficient permissions

    Safe: never reveals internal permission names in user-facing messages.
    """
    user = get_current_portal_user(request)

    # Not logged in
    if not user:
        if redirect_to_login:
            return _redirect_to_login(request)
        return forbidden_response()

    # Get permissions from backend
    perms = await get_current_user_permissions(request)

    if not perms:
        # Token might be expired, but user has session — redirect to login
        if redirect_to_login:
            return _redirect_to_login(request)
        return forbidden_response()

    if permission not in perms:
        return forbidden_response()

    return None  # Allowed


async def require_admin_access(request: Request) -> Response | None:
    """Check user has all ADMIN_REQUIRED_PERMISSIONS for /admin page.

    Returns None if allowed, Response(403) or RedirectResponse otherwise.
    """
    user = get_current_portal_user(request)
    if not user:
        return _redirect_to_login(request)

    perms = await get_current_user_permissions(request)
    if not perms or not _has_admin_access(perms):
        return forbidden_response()

    return None


# ═══════════════════════════════════════════════════════════════════════
# Route-level RBAC — session-only, no backend call (Step 36.13)
# ═══════════════════════════════════════════════════════════════════════

from portal_session import get_current_portal_user as _get_user
from portal_session import get_session_permissions as _get_perms

# Mapping: route → required permission (real backend permission codes)
PAGE_PERMISSION_MAP: dict[str, str] = {
    "/": "campaigns.read",
    "/dashboard": "campaigns.read",
    "/campaigns": "campaigns.read",
    "/creatives": "media.read",
    "/schedule": "scheduling.read",
    "/publications": "publications.read",
    "/stores": "organization.read",
    "/devices": "devices.read",
    "/proof-of-play": "reports.read",
    "/reports": "reports.read",
    "/deployment": "campaigns.read",
    "/approvals": "campaigns.approve",
    "/admin": "users.read",
    "/device-dashboard": "devices.gateway.read",
    "/readiness": "devices.gateway.read",
    "/readiness/business-acceptance": "devices.gateway.read",
}

# Public routes — no auth required
PUBLIC_ROUTES: frozenset[str] = frozenset({
    "/login", "/logout", "/health", "/static",
    "/compliance", "/compliance/retention",
})


async def require_auth_for_page(request: Request, route: str) -> Response | None:
    """Check session auth + route permission for page rendering.

    Session-only check — NO backend API call.
    Forbidden: redirects to /login (unauthenticated) or returns 403 (no perm).

    Returns None if allowed.
    """
    # Public routes pass through
    if route in PUBLIC_ROUTES or route.startswith("/static"):
        return None

    # Check session
    user = _get_user(request)
    if not user:
        return _redirect_to_login(request)

    # Check permission from session store (no backend call)
    required = PAGE_PERMISSION_MAP.get(route)
    if required is None:
        return None  # Unknown route — allow (will 404 on its own)

    perms = _get_perms(request)
    if required not in perms:
        return forbidden_response()

    return None


# ── Internal helpers ──────────────────────────────────────────────────

def _redirect_to_login(request: Request) -> RedirectResponse:
    """Redirect unauthenticated user to login page."""
    return RedirectResponse(url="/login", status_code=303)


def forbidden_response() -> Response:
    """Return a safe 403 HTML response.

    Does NOT reveal internal permission names or token details.
    """
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Доступ запрещён — Retail Media Platform</title>
<link rel="stylesheet" href="/static/styles.css">
</head>
<body>
<div class="header">
  <span class="header-logo">Retail Media Platform</span>
  <span class="header-subtitle">KSO v1</span>
</div>
<div class="main" style="margin-top:80px; text-align:center; padding:40px">
  <h1 style="font-size:24px; margin-bottom:16px">🚫 Доступ запрещён</h1>
  <p style="color:var(--color-text-muted); max-width:480px; margin:0 auto 24px">
    Недостаточно прав для доступа к этому разделу.
    Обратитесь к администратору портала для получения необходимых прав.
  </p>
  <a href="/dashboard" style="display:inline-block; padding:10px 24px;
     background:var(--color-primary); color:#fff; border-radius:6px;
     text-decoration:none; font-weight:600">На главную</a>
</div>
</body>
</html>"""
    return Response(content=html, status_code=403, media_type="text/html")
