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
