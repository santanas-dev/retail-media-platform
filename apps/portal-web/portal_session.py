"""Portal session management — server-side token storage, opaque browser cookie.

ARCHITECTURE (Step 36.6.1):
  Browser cookie:  portal_session_id = random opaque hex string (64 chars)
  Server-side:     {session_id: {access_token, refresh_token, username,
                                  display_name, roles, expires_at}}
  Cookie flags:    httpOnly, SameSite=Lax, signed, max_age=3600
  PortalUser:      NEVER contains tokens — only username, display_name, roles

DEV NOTE: Session store is in-memory dict (DEV/foundation only).
Production MUST use Redis or PostgreSQL for session persistence.

Secure cookie MUST be enabled behind HTTPS in production.
"""

import os
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

from starlette.requests import Request

from security_contract import ROLE_LABELS

__all__ = [
    "PortalUser",
    "get_current_portal_user",
    "create_portal_session",
    "clear_portal_session",
    "get_portal_tokens",
    "SESSION_COOKIE_NAME",
]

# ── Cookie config ────────────────────────────────────────────────────

SESSION_COOKIE_NAME = "portal_session_id"
_MAX_AGE = int(os.getenv("PORTAL_SESSION_MAX_AGE", "3600"))  # 1 hour
_SESSION_ID_BYTES = 32  # → 64 hex chars

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


# ══════════════════════════════════════════════════════════════════════
# Server-Side Session Store (DEV: in-memory dict)
# ══════════════════════════════════════════════════════════════════════

class _SessionStore:
    """Thread-safe in-memory session store.

    DEV/FOUNDATION ONLY. Production: replace with Redis/PostgreSQL.
    Public interface (create/get/delete) is designed to be drop-in
    replaceable — no login/logout code changes needed.
    """

    def __init__(self):
        self._store: dict[str, dict] = {}
        self._lock = Lock()

    def create(self, **fields) -> str:
        """Create a new session. Returns opaque session_id (hex)."""
        session_id = secrets.token_hex(_SESSION_ID_BYTES)
        fields["_created_at"] = time.time()
        with self._lock:
            self._store[session_id] = fields
        return session_id

    def get(self, session_id: str) -> dict | None:
        """Retrieve session data or None if expired/missing."""
        with self._lock:
            data = self._store.get(session_id)
        if data is None:
            return None
        # TTL check
        age = time.time() - data.get("_created_at", 0)
        if age > _MAX_AGE:
            with self._lock:
                self._store.pop(session_id, None)
            return None
        return data

    def delete(self, session_id: str) -> None:
        """Remove a session."""
        with self._lock:
            self._store.pop(session_id, None)

    def _cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count removed."""
        now = time.time()
        removed = 0
        with self._lock:
            expired = [
                sid for sid, data in self._store.items()
                if now - data.get("_created_at", 0) > _MAX_AGE
            ]
            for sid in expired:
                self._store.pop(sid, None)
                removed += 1
        return removed


# Singleton store
_store = _SessionStore()


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def _get_session_id(request: Request) -> str | None:
    """Read opaque session_id from signed cookie."""
    return request.session.get(SESSION_COOKIE_NAME)


def get_current_portal_user(request: Request) -> Optional[PortalUser]:
    """Return the currently authenticated portal user, or None.

    Looks up session_id in cookie → server-side store.
    Returns PortalUser with NO tokens, NO email, NO UUIDs.
    """
    session_id = _get_session_id(request)
    if not session_id:
        return None
    data = _store.get(session_id)
    if not data:
        return None
    return PortalUser(
        username=data.get("username", ""),
        display_name=data.get("display_name", ""),
        roles=data.get("roles", []),
    )


def get_portal_tokens(request: Request) -> dict[str, str]:
    """Return {access_token, refresh_token} or {} if no session.

    INTERNAL USE ONLY — for backend API calls (never exposed to templates).
    """
    session_id = _get_session_id(request)
    if not session_id:
        return {}
    data = _store.get(session_id)
    if not data:
        return {}
    return {
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
    }


def get_session_permissions(request: Request) -> frozenset[str]:
    """Return user's backend permissions stored in session (no backend call).

    Fast, session-only check for route-level RBAC guards.
    Returns empty frozenset if not authenticated.
    """
    session_id = _get_session_id(request)
    if not session_id:
        return frozenset()
    data = _store.get(session_id)
    if not data:
        return frozenset()
    perms = data.get("permissions", [])
    return frozenset(perms) if isinstance(perms, list) else frozenset()


def create_portal_session(
    request: Request,
    access_token: str,
    refresh_token: str,
    username: str,
    display_name: str,
    roles: list[str],
    permissions: list[str] | None = None,
) -> str:
    """Create a new portal session.

    Stores tokens SERVER-SIDE only.
    Sets browser cookie with opaque session_id (httpOnly, signed).
    Returns the session_id (for testing).
    """
    session_id = _store.create(
        access_token=access_token,
        refresh_token=refresh_token,
        username=username,
        display_name=display_name,
        roles=roles,
        permissions=permissions or [],
    )
    # Store ONLY opaque session_id in signed cookie
    request.session[SESSION_COOKIE_NAME] = session_id
    return session_id


def clear_portal_session(request: Request) -> None:
    """Clear all portal auth state: server-side store + browser cookie."""
    session_id = _get_session_id(request)
    if session_id:
        _store.delete(session_id)
    request.session.pop(SESSION_COOKIE_NAME, None)
