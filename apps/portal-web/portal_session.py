"""Portal session management — safe user view, never exposes tokens.

Uses Starlette SessionMiddleware (signed httpOnly cookie). Tokens are
stored server-side inside the signed session — client JS cannot read them.

Architecture:
- On login success: store access_token + refresh_token + safe user view
- On /me refresh: update safe user view only (tokens unchanged)
- On logout: clear entire session
- get_current_portal_user(): returns safe PortalUser dataclass or None

Safe user view contains ONLY:
- username, display_name, roles (role codes)
- NEVER: tokens, password_hash, permissions, email, phone, UUIDs
"""

from dataclasses import dataclass, field
from typing import Optional

from starlette.requests import Request

from security_contract import ROLE_LABELS

__all__ = [
    "PortalUser",
    "get_current_portal_user",
    "set_portal_session",
    "clear_portal_session",
    "SESSION_KEYS",
]

# ── Session keys (stored in signed cookie) ───────────────────────────

SESSION_KEYS = {
    "ACCESS_TOKEN": "portal_access_token",
    "REFRESH_TOKEN": "portal_refresh_token",
    "USERNAME": "portal_username",
    "DISPLAY_NAME": "portal_display_name",
    "ROLES": "portal_roles",
}

# ── Safe user view ───────────────────────────────────────────────────

@dataclass
class PortalUser:
    """Safe user view for templates — no tokens, no hashes, no IDs."""
    username: str
    display_name: str
    roles: list[str] = field(default_factory=list)

    @property
    def role_labels(self) -> list[str]:
        """Human-readable role labels in Russian."""
        return [ROLE_LABELS.get(r, r) for r in self.roles]

    @property
    def safe_name(self) -> str:
        """Display name or username — safe for UI rendering."""
        return self.display_name or self.username


# ── Session helpers ──────────────────────────────────────────────────

def get_current_portal_user(request: Request) -> Optional[PortalUser]:
    """Return the currently authenticated portal user, or None.

    Reads from the signed session cookie. Returns a safe PortalUser
    with NO tokens, NO email, NO UUIDs, NO permissions.
    """
    session = request.session
    username = session.get(SESSION_KEYS["USERNAME"])
    if not username:
        return None
    return PortalUser(
        username=username,
        display_name=session.get(SESSION_KEYS["DISPLAY_NAME"], ""),
        roles=session.get(SESSION_KEYS["ROLES"], []),
    )


def set_portal_session(
    request: Request,
    access_token: str,
    refresh_token: str,
    username: str,
    display_name: str,
    roles: list[str],
) -> None:
    """Store authentication state in the signed server-side session.

    Tokens are stored ONLY in the signed cookie — never in localStorage.
    The cookie is httpOnly, so JS cannot read it.
    """
    session = request.session
    session[SESSION_KEYS["ACCESS_TOKEN"]] = access_token
    session[SESSION_KEYS["REFRESH_TOKEN"]] = refresh_token
    session[SESSION_KEYS["USERNAME"]] = username
    session[SESSION_KEYS["DISPLAY_NAME"]] = display_name
    session[SESSION_KEYS["ROLES"]] = roles


def clear_portal_session(request: Request) -> None:
    """Clear all portal auth state from the session."""
    for key in SESSION_KEYS.values():
        request.session.pop(key, None)
