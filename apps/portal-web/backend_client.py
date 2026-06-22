"""Secure httpx-based async client for Retail Media Platform backend API.

All calls go through this module — never call the backend directly from
routers or templates. Timeouts, safe errors, and credential isolation
are enforced here.

Environment:
    PORTAL_BACKEND_API_URL — backend base URL (default: http://localhost:8001)
"""

import os
import httpx
from typing import Optional

__all__ = [
    "BackendClient",
    "backend_login",
    "backend_me",
    "backend_logout",
    "get_backend_url",
]

_BACKEND_URL = os.getenv("PORTAL_BACKEND_API_URL", "http://localhost:8001")
# Strip trailing slash
_BACKEND_URL = _BACKEND_URL.rstrip("/")

_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT = 15.0

_SENSITIVE_KEYS = frozenset({
    "password", "access_token", "refresh_token", "token",
    "authorization", "bearer",
})


def get_backend_url() -> str:
    """Return the configured backend API base URL (no trailing slash).

    Safe to call from any context. Never exposes the URL in UI/logs
    by default — callers must explicitly log if needed.
    """
    return _BACKEND_URL


class BackendClient:
    """Async HTTP client with mandatory timeouts and safe error handling."""

    def __init__(self, base_url: str | None = None):
        self._base_url = (base_url or _BACKEND_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT,
                                   write=10.0, pool=5.0),
        )

    async def close(self):
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Make a backend API call. Returns {"ok": True, "data": ...}
        or {"ok": False, "error": str, "status": int}.
        """
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.request(
                method, path, json=json_data, headers=headers,
            )
        except httpx.TimeoutException:
            return {"ok": False, "error": "Backend request timed out", "status": 504}
        except httpx.ConnectError:
            return {"ok": False, "error": "Backend unreachable", "status": 502}
        except Exception as exc:
            # Never include raw exception detail — could leak internal paths
            return {"ok": False, "error": "Backend communication error", "status": 502}

        try:
            body = resp.json() if resp.content else {}
        except Exception:
            body = {}

        if resp.is_success:
            return {"ok": True, "data": body, "status": resp.status_code}
        else:
            # Forward backend error messages safely
            detail = body.get("detail", "Backend error")
            if isinstance(detail, str):
                # Truncate to prevent error-enumeration attacks
                detail = detail[:200]
            else:
                detail = "Backend error"
            return {"ok": False, "error": detail, "status": resp.status_code}

    # ── Auth helpers ─────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> dict:
        """POST /api/auth/login → {ok, data: {access_token, refresh_token, ...}}"""
        return await self._request(
            "POST", "/api/auth/login",
            json_data={"username": username, "password": password},
        )

    async def me(self, access_token: str) -> dict:
        """GET /api/auth/me → {ok, data: {id, username, display_name, roles, ...}}"""
        return await self._request(
            "GET", "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def logout(self, refresh_token: str) -> dict:
        """POST /api/auth/logout → {ok, data: {}} (204 on success)"""
        return await self._request(
            "POST", "/api/auth/logout",
            json_data={"refresh_token": refresh_token},
        )

    # ── Admin read-only methods ───────────────────────────────────────

    async def list_users(self, access_token: str) -> dict:
        """GET /api/users → {ok, data: [{id, username, display_name, roles, ...}]}"""
        return await self._request(
            "GET", "/api/users",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_roles(self, access_token: str) -> dict:
        """GET /api/roles → {ok, data: [{id, code, name, description, ...}]}"""
        return await self._request(
            "GET", "/api/roles",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_permissions(self, access_token: str) -> dict:
        """GET /api/permissions → {ok, data: [{id, code, name, resource, action, ...}]}"""
        return await self._request(
            "GET", "/api/permissions",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_admin_audit(self, access_token: str, limit: int = 10) -> dict:
        """GET /api/admin/audit → {ok, data: [{id, action, target_type, ...}]}"""
        return await self._request(
            "GET", f"/api/admin/audit?limit={limit}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def create_user(self, access_token: str, payload: dict) -> dict:
        """POST /api/users → {ok, data: {id, username, ...}} (201) or error.

        Payload: {username, password, display_name?, role_codes?}
        Password is NEVER logged or returned.
        """
        return await self._request(
            "POST", "/api/users",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_user_by_username(self, access_token: str, username: str) -> dict:
        """GET /api/users/{username} → {ok, data: {id, username, roles, ...}}.

        Returns the user's UUID (id) which is needed for role assignment.
        UUID is returned to the caller but NEVER exposed in UI/logs.
        """
        return await self._request(
            "GET", f"/api/users/{username}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def assign_user_roles(
        self, access_token: str, username: str, role_codes: list[str],
    ) -> dict:
        """Assign roles to a user via backend API.

        Flow (two-step, no backend changes needed):
        1. GET /api/users/{username} → fetch user UUID
        2. PUT /api/users/{user_id}/roles → assign roles

        UUID is resolved internally — never exposed to UI.
        Returns {ok, data: {username, roles, ...}} or error.
        """
        # Step 1: resolve username → user_id
        lookup = await self.get_user_by_username(access_token, username)
        if not lookup["ok"]:
            return lookup  # propagate error (404, etc.)

        user_id = lookup["data"].get("id")
        if not user_id:
            return {"ok": False, "error": "User not found", "status": 404}

        # Step 2: assign roles
        return await self._request(
            "PUT", f"/api/users/{user_id}/roles",
            json_data={"role_codes": role_codes},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def assign_user_rls_scopes(
        self, access_token: str, username: str, scopes: list[dict],
    ) -> dict:
        """Assign RLS scopes to a user via backend API.

        PATCH /api/users/{username}/rls-scopes
        Payload: {"scopes": [{"scope_type": "...", "scope_value": "...",
                                "is_active": true, "reason": "..."}]}

        Replaces ALL existing scopes for the user.
        Returns {ok, data: {username, ...}} or error.
        """
        return await self._request(
            "PATCH", f"/api/users/{username}/rls-scopes",
            json_data={"scopes": scopes},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def block_user(self, access_token: str, username: str) -> dict:
        """Block a user via backend API.

        PATCH /api/users/{username}/status
        Payload: {"status": "blocked"}

        Backend enforces: cannot block self, cannot block last system_admin.
        Returns {ok, data: {username, is_locked: true, ...}} or error.
        """
        return await self._request(
            "PATCH", f"/api/users/{username}/status",
            json_data={"status": "blocked"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def archive_user(self, access_token: str, username: str) -> dict:
        """Archive a user via backend API (logical delete).

        PATCH /api/users/{username}/status
        Payload: {"status": "archived"}

        Backend enforces: cannot archive self, cannot archive last system_admin.
        Sets is_archived=True, is_active=False — logical, no hard delete.
        Returns {ok, data: {username, is_archived: true, ...}} or error.
        """
        return await self._request(
            "PATCH", f"/api/users/{username}/status",
            json_data={"status": "archived"},
            headers={"Authorization": f"Bearer {access_token}"},
        )


# ── Module-level convenience functions ───────────────────────────────

_client: Optional[BackendClient] = None


def _get_client() -> BackendClient:
    global _client
    if _client is None:
        _client = BackendClient()
    return _client


async def backend_login(username: str, password: str) -> dict:
    """Convenience: call backend login."""
    return await _get_client().login(username, password)


async def backend_me(access_token: str) -> dict:
    """Convenience: call backend /me."""
    return await _get_client().me(access_token)


async def backend_logout(refresh_token: str) -> dict:
    """Convenience: call backend logout."""
    return await _get_client().logout(refresh_token)


async def close_backend_client():
    """Shutdown hook — close the global client."""
    global _client
    if _client:
        await _client.close()
        _client = None
