"""Secure httpx-based async client for Retail Media Platform backend API.

All calls go through this module — never call the backend directly from
routers or templates. Timeouts, safe errors, and credential isolation
are enforced here.

Environment:
    PORTAL_BACKEND_API_URL — backend base URL (default: http://localhost:8421)
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

_BACKEND_URL = os.getenv("PORTAL_BACKEND_API_URL", "http://localhost:8421")
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

    async def _request_raw(
        self,
        method: str,
        path: str,
        *,
        headers: dict | None = None,
    ) -> dict:
        """Make a backend API call returning raw text (for CSV etc.).
        Returns {"ok": True, "text": str, "content_type": str}
        or {"ok": False, "error": str, "status": int}.
        """
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.request(
                method, path, headers=headers,
            )
        except httpx.TimeoutException:
            return {"ok": False, "error": "Backend request timed out", "status": 504}
        except httpx.ConnectError:
            return {"ok": False, "error": "Backend unreachable", "status": 502}
        except Exception:
            return {"ok": False, "error": "Backend communication error", "status": 502}

        if resp.is_success:
            return {
                "ok": True,
                "text": resp.text,
                "content_type": resp.headers.get("content-type", "text/plain"),
                "status": resp.status_code,
            }
        else:
            return {"ok": False, "error": "Backend error", "status": resp.status_code}

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

    # ── Hierarchy & KSO Device Registry (Step 37.2) ────────────────────

    async def list_branches(self, access_token: str) -> dict:
        """GET /api/branches → {ok, data: [{id, name, code, timezone, is_active}]}"""
        return await self._request(
            "GET", "/api/branches",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_clusters(self, access_token: str, branch_id: str | None = None) -> dict:
        """GET /api/clusters[?branch_id=...] → {ok, data: [{id, name, code, branch_id}]}"""
        path = "/api/clusters"
        if branch_id:
            path += f"?branch_id={branch_id}"
        return await self._request(
            "GET", path,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_stores(self, access_token: str) -> dict:
        """GET /api/stores → {ok, data: [{id, name, code, cluster_id, format, status, ...}]}"""
        return await self._request(
            "GET", "/api/stores",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_kso_devices(self, access_token: str) -> dict:
        """GET /api/devices/kso → {ok, data: [{id, store_id, device_code,
        display_name, status, channel, runtime_version, player_version,
        sidecar_version, state_adapter_version, manifest_version,
        screen_width, screen_height, ad_zone_width, ad_zone_height,
        last_seen_at, ...}]}"""
        return await self._request(
            "GET", "/api/devices/kso",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Creative Upload (Step 37.3) ────────────────────────────────────

    async def list_creatives(self, access_token: str) -> dict:
        """GET /api/creatives → {ok, data: [{creative_code, name, status, ...}]}"""
        return await self._request(
            "GET", "/api/creatives",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def upload_creative(
        self, access_token: str, creative_code: str, name: str,
        file_content: bytes, filename: str, content_type: str,
    ) -> dict:
        """POST /api/creatives/upload (multipart/form-data).

        Sends multipart form with creative_code, name, and file.
        Returns {ok, data: {creative_code, name, status, content_type,
                             width, height, file_size_bytes, version}}
        or {ok: False, error: ...}.
        """
        import io
        files = {
            "file": (filename, io.BytesIO(file_content), content_type),
        }
        data = {
            "creative_code": creative_code,
            "name": name,
        }
        try:
            resp = await self._client.post(
                "/api/creatives/upload",
                data=data,
                files=files,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except Exception as exc:
            return {"ok": False, "error": f"Upload failed: {str(exc)[:200]}", "status": 502}

        try:
            body = resp.json() if resp.content else {}
        except Exception:
            body = {}

        if resp.is_success:
            return {"ok": True, "data": body, "status": resp.status_code}
        detail = body.get("detail", "Upload error")
        if isinstance(detail, str):
            detail = detail[:200]
        return {"ok": False, "error": detail, "status": resp.status_code}

    # ── Advertiser list for creative form ─────────────────────────────

    async def list_advertisers(self, access_token: str) -> dict:
        """GET /api/advertisers → {ok, data: [{id, name, ...}]}"""
        return await self._request(
            "GET", "/api/advertisers",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Creative Archive (41.1) ────────────────────────────────────────

    async def archive_creative(
        self, access_token: str, creative_code: str,
    ) -> dict:
        """POST /api/creatives/by-code/{code}/archive → {ok, data}.

        Sets creative status to 'archived'.
        """
        return await self._request(
            "POST", f"/api/creatives/by-code/{creative_code}/archive",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Moderation (44.2) ──────────────────────────────────────────────

    async def submit_creative_review(
        self, access_token: str, creative_code: str, comment: str = "",
    ) -> dict:
        return await self._request(
            "POST", f"/api/creatives/by-code/{creative_code}/submit-review",
            json={"action": "submit_review", "comment": comment},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def approve_creative(
        self, access_token: str, creative_code: str, comment: str = "",
    ) -> dict:
        return await self._request(
            "POST", f"/api/creatives/by-code/{creative_code}/approve",
            json={"action": "approve", "comment": comment},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def reject_creative(
        self, access_token: str, creative_code: str, comment: str = "",
    ) -> dict:
        return await self._request(
            "POST", f"/api/creatives/by-code/{creative_code}/reject",
            json={"action": "reject", "comment": comment},
            headers={"Authorization": f"Bearer {access_token}"},
        )


    # ── Campaign Production API (39.2.2) ─────────────────────────────────

    async def list_campaigns(self, access_token: str) -> dict:
        """GET /api/campaigns/test-kso → {ok, data: [{campaign_code, name, ...}]}
        
        Uses test-kso list for safe projection — no raw UUIDs in response.
        """
        return await self._request(
            "GET", "/api/campaigns/test-kso",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_campaigns_prod(self, access_token: str) -> dict:
        """GET /api/campaigns → {ok, data: [{id, name, status, ...}]} (production).

        Returns full CampaignResponse with UUIDs — use for counting/KPI only.
        Portal must strip UUIDs before rendering.
        """
        return await self._request(
            "GET", "/api/campaigns",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def create_campaign(self, access_token: str, payload: dict) -> dict:
        """POST /api/campaigns/by-code → {ok, data: {campaign_code, name, ...}}

        Production-safe code-based campaign creation — no UUIDs required.
        """
        return await self._request(
            "POST", "/api/campaigns/by-code",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_campaign_by_code(
        self, access_token: str, campaign_code: str,
    ) -> dict:
        """GET /api/campaigns/by-code/{code} → {ok, data} (production)."""
        return await self._request(
            "GET", f"/api/campaigns/by-code/{campaign_code}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def update_campaign_by_code(
        self, access_token: str, campaign_code: str, payload: dict,
    ) -> dict:
        """PATCH /api/campaigns/by-code/{code} → {ok, data} (production)."""
        return await self._request(
            "PATCH", f"/api/campaigns/by-code/{campaign_code}",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def archive_campaign_by_code(
        self, access_token: str, campaign_code: str,
    ) -> dict:
        """POST /api/campaigns/by-code/{code}/archive → {ok, data} (production)."""
        return await self._request(
            "POST", f"/api/campaigns/by-code/{campaign_code}/archive",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_campaign_creatives(
        self, access_token: str, campaign_code: str,
    ) -> dict:
        """GET /api/campaigns/by-code/{code}/creatives → {ok, data}."""
        return await self._request(
            "GET", f"/api/campaigns/by-code/{campaign_code}/creatives",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def bind_campaign_creative(
        self, access_token: str, campaign_code: str, creative_code: str,
    ) -> dict:
        """POST /api/campaigns/by-code/{code}/creatives → {ok, data}."""
        return await self._request(
            "POST", f"/api/campaigns/by-code/{campaign_code}/creatives",
            json_data={"creative_code": creative_code},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def unbind_campaign_creative(
        self, access_token: str, campaign_code: str, creative_code: str,
    ) -> dict:
        """DELETE /api/campaigns/by-code/{code}/creatives/{cc} → {ok, data}."""
        return await self._request(
            "DELETE",
            f"/api/campaigns/by-code/{campaign_code}/creatives/{creative_code}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def submit_campaign(
        self, access_token: str, campaign_code: str,
    ) -> dict:
        """POST /api/campaigns/by-code/{code}/submit → {ok, data: {campaign_code, status, ...}}.

        Submits campaign for review: draft/rejected → in_review.
        Requires campaigns.manage permission on the backend.
        """
        return await self._request(
            "POST", f"/api/campaigns/by-code/{campaign_code}/submit",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Schedule Placement (Step 37.5) ─────────────────────────────────

    async def list_placements(self, access_token: str) -> dict:
        """GET /api/schedule/test-kso → {ok, data: [{placement_code, ...}]}"""
        return await self._request(
            "GET", "/api/schedule/test-kso",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def create_placement(self, access_token: str, payload: dict) -> dict:
        """POST /api/schedule/test-kso → {ok, data: {placement_code, ...}}"""
        return await self._request(
            "POST", "/api/schedule/test-kso",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Schedule Production API (39.2.1) ─────────────────────────────────

    async def list_schedules(self, access_token: str) -> dict:
        """GET /api/schedules → {ok, data: [{schedule_code, name, status, ...}]}"""
        return await self._request(
            "GET", "/api/schedules",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def create_schedule(self, access_token: str, payload: dict) -> dict:
        """POST /api/schedules → {ok, data: {schedule_code, name, ...}}"""
        return await self._request(
            "POST", "/api/schedules",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_schedule(self, access_token: str, schedule_code: str) -> dict:
        """GET /api/schedules/{code} → {ok, data: {schedule_code, ...}}"""
        return await self._request(
            "GET", f"/api/schedules/{schedule_code}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def update_schedule(
        self, access_token: str, schedule_code: str, payload: dict,
    ) -> dict:
        """PATCH /api/schedules/{code} → {ok, data: {schedule_code, ...}}"""
        return await self._request(
            "PATCH", f"/api/schedules/{schedule_code}",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def archive_schedule(self, access_token: str, schedule_code: str) -> dict:
        """POST /api/schedules/{code}/archive → {ok, data: {schedule_code, ...}}"""
        return await self._request(
            "POST", f"/api/schedules/{schedule_code}/archive",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_schedule_slots(
        self, access_token: str, schedule_code: str,
    ) -> dict:
        """GET /api/schedules/{code}/items → {ok, data: [{slot_code, ...}]}"""
        return await self._request(
            "GET", f"/api/schedules/{schedule_code}/items",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def create_schedule_slot(
        self, access_token: str, schedule_code: str, payload: dict,
    ) -> dict:
        """POST /api/schedules/{code}/items → {ok, data: {slot_code, ...}}"""
        return await self._request(
            "POST", f"/api/schedules/{schedule_code}/items",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def update_schedule_slot(
        self, access_token: str, schedule_code: str,
        slot_code: str, payload: dict,
    ) -> dict:
        """PATCH /api/schedules/{code}/items/{slot} → {ok, data: {slot_code, ...}}"""
        return await self._request(
            "PATCH", f"/api/schedules/{schedule_code}/items/{slot_code}",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def disable_schedule_slot(
        self, access_token: str, schedule_code: str, slot_code: str,
    ) -> dict:
        """DELETE /api/schedules/{code}/items/{slot} → {ok, data: {slot_code, ...}}"""
        return await self._request(
            "DELETE", f"/api/schedules/{schedule_code}/items/{slot_code}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_placements_prod(self, access_token: str) -> dict:
        """GET /api/placements → {ok, data: [{placement_code, ...}]} (production)."""
        return await self._request(
            "GET", "/api/placements",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Approval (Step 37.6 + 39.3.1 production) ────────────────────────

    async def list_approvals(self, access_token: str) -> dict:
        """GET /api/approvals/test-kso → {ok, data: [{approval_code, ...}]}

        Legacy test-kso endpoint. Prefer list_approvals_prod() for production.
        """
        return await self._request(
            "GET", "/api/approvals/test-kso",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def list_approvals_prod(self, access_token: str) -> dict:
        """GET /api/approvals → {ok, data: [{approval_code, ...}]} (production)."""
        return await self._request(
            "GET", "/api/approvals",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_approval(self, access_token: str, approval_code: str) -> dict:
        """GET /api/approvals/{code} → {ok, data: {approval_code, ...}} (production)."""
        return await self._request(
            "GET", f"/api/approvals/{approval_code}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def create_approval(
        self, access_token: str, payload: dict,
    ) -> dict:
        """POST /api/approvals → {ok, data: {approval_code, ...}} (production)."""
        return await self._request(
            "POST", "/api/approvals",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def request_approval(self, access_token: str, payload: dict) -> dict:
        """POST /api/approvals/test-kso/request → {ok, data: {approval_code, ...}}

        Legacy test-kso endpoint. Prefer create_approval() for production.
        """
        return await self._request(
            "POST", "/api/approvals/test-kso/request",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def approve_approval(
        self, access_token: str, approval_code: str, payload: dict,
    ) -> dict:
        """POST /api/approvals/{code}/approve → {ok, data} (production)."""
        return await self._request(
            "POST", f"/api/approvals/{approval_code}/approve",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def reject_approval(
        self, access_token: str, approval_code: str, payload: dict,
    ) -> dict:
        """POST /api/approvals/{code}/reject → {ok, data} (production)."""
        return await self._request(
            "POST", f"/api/approvals/{approval_code}/reject",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def decide_approval(
        self, access_token: str, approval_code: str, payload: dict,
    ) -> dict:
        """POST /api/approvals/test-kso/{code}/decide → {ok, data}

        Legacy test-kso endpoint. Prefer approve_approval()/reject_approval().
        """
        return await self._request(
            "POST", f"/api/approvals/test-kso/{approval_code}/decide",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Manifest Generation & Publication (Steps 37.7, 37.8) ─────────

    async def list_manifests(self, access_token: str) -> dict:
        """GET /api/manifests → {ok, data: [{manifest_code, ...}]} (production)."""
        return await self._request(
            "GET", "/api/manifests",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def generate_manifest(self, access_token: str, payload: dict) -> dict:
        """POST /api/manifests → {ok, data: {manifest_code, ...}} (production).

        Uses the unified build_manifest_from_placement() builder.
        Legacy /api/manifests/test-kso/generate delegates to the same code.
        """
        return await self._request(
            "POST", "/api/manifests",
            json_data=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_manifest(self, access_token: str, manifest_code: str) -> dict:
        """GET /api/manifests/{code} → {ok, data} (production)."""
        return await self._request(
            "GET", f"/api/manifests/{manifest_code}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def publish_manifest(self, access_token: str, manifest_code: str) -> dict:
        """POST /api/manifests/{code}/publish → {ok, data} (production, idempotent)."""
        return await self._request(
            "POST", f"/api/manifests/{manifest_code}/publish",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Publication Batches (39.3.3 + 41.4) ─────────────────────────────────

    async def list_publication_batches(self, access_token: str) -> dict:
        """GET /api/publication-batches → {ok, data: [...]} (production)."""
        return await self._request(
            "GET", "/api/publication-batches",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_publication_batch(
        self, access_token: str, batch_id: str,
    ) -> dict:
        """GET /api/publication-batches/{id} → {ok, data} (production)."""
        return await self._request(
            "GET", f"/api/publication-batches/{batch_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def create_publication_batch(
        self, access_token: str, campaign_code: str,
    ) -> dict:
        """POST /api/campaigns/by-code/{code}/create-publication-batch → {ok, data}.

        Creates a publication batch (draft) from an approved campaign.
        Physical KSO delivery is NOT triggered — backend status only.
        """
        return await self._request(
            "POST", f"/api/campaigns/by-code/{campaign_code}/create-publication-batch",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def publish_batch(
        self, access_token: str, batch_id: str,
    ) -> dict:
        """POST /api/publication-batches/{id}/publish → {ok, data} (production).

        Requires approved ApprovalRequest for the batch.
        """
        return await self._request(
            "POST", f"/api/publication-batches/{batch_id}/publish",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def request_batch_approval(
        self, access_token: str, batch_id: str,
    ) -> dict:
        """POST /api/publication-batches/{id}/request-approval → {ok, data}."""
        return await self._request(
            "POST", f"/api/publication-batches/{batch_id}/request-approval",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def approve_batch(
        self, access_token: str, batch_id: str,
    ) -> dict:
        """POST /api/publication-batches/{id}/approve → {ok, data}."""
        return await self._request(
            "POST", f"/api/publication-batches/{batch_id}/approve",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def generate_batch_manifests(
        self, access_token: str, batch_id: str,
    ) -> dict:
        """POST /api/publication-batches/{id}/generate → {ok, data}."""
        return await self._request(
            "POST", f"/api/publication-batches/{batch_id}/generate",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def cancel_batch(
        self, access_token: str, batch_id: str,
    ) -> dict:
        """POST /api/publication-batches/{id}/cancel → {ok, data}."""
        return await self._request(
            "POST", f"/api/publication-batches/{batch_id}/cancel",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Proof of Play KSO List (Step 37.11) ───────────────────────────

    async def list_pop_events(
        self, access_token: str, filters: dict | None = None,
    ) -> dict:
        """GET /api/proof-of-play/test-kso → {ok, data: [{event_code, ...}]}

        Legacy test-kso endpoint. Prefer get_pop_report() for production use.
        """
        from urllib.parse import urlencode
        params = {}
        if filters:
            for key in (
                "device_code", "campaign_code", "creative_code",
                "placement_code", "date_from", "date_to",
                "limit", "offset",
            ):
                if key in filters and filters[key] is not None:
                    params[key] = filters[key]

        query = ("?" + urlencode(params)) if params else ""
        return await self._request(
            "GET", f"/api/proof-of-play/test-kso{query}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_pop_report(
        self, access_token: str, filters: dict | None = None,
    ) -> dict:
        """GET /api/reports/pop → {ok, data: [{event_code, ...}]} (production).

        Safe projection — no raw UUIDs, tokens, secrets.
        """
        from urllib.parse import urlencode
        params = {}
        if filters:
            for key in (
                "device_code", "campaign_code", "creative_code",
                "placement_code", "date_from", "date_to",
                "limit", "offset",
            ):
                if key in filters and filters[key] is not None:
                    params[key] = filters[key]

        query = ("?" + urlencode(params)) if params else ""
        return await self._request(
            "GET", f"/api/reports/pop{query}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_pop_summary(
        self, access_token: str, filters: dict | None = None,
    ) -> dict:
        """GET /api/reports/pop/summary → {ok, data: {total_events, ...}} (production).

        Aggregated counts: total_events, unique_devices, unique_campaigns,
        unique_creatives, unique_placements, accepted, rejected, duplicate,
        unknown_status, last_event_at.
        """
        from urllib.parse import urlencode
        params = {}
        if filters:
            for key in (
                "device_code", "campaign_code", "creative_code",
                "placement_code", "date_from", "date_to",
            ):
                if key in filters and filters[key] is not None:
                    params[key] = filters[key]

        query = ("?" + urlencode(params)) if params else ""
        return await self._request(
            "GET", f"/api/reports/pop/summary{query}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_test_kso_readiness(
        self, device_code: str,
    ) -> dict:
        """GET /api/test-kso/readiness?device_code=... → {ok, data: ReadinessStatus}

        No auth required (TEST_ONLY endpoint). Returns safe readiness summary.
        """
        from urllib.parse import urlencode
        query = "?" + urlencode({"device_code": device_code})
        return await self._request(
            "GET", f"/api/test-kso/readiness{query}",
        )


    async def get_device_dashboard(
        self, access_token: str,
        keyword: str | None = None,
        channel_code: str | None = None,
        store_code: str | None = None,
        readiness_badge: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """GET /api/device-dashboard → {ok, data: [DeviceDashboardItem]}.

        Cross-domain aggregation: GatewayDevice + KsoDevice + credentials
        + sessions + heartbeats + manifests + PoP + media cache.

        Safe projection: no raw UUIDs, secrets, tokens, backend URLs.
        Requires devices.gateway.read permission.

        Query params only included when non-empty.
        """
        from urllib.parse import urlencode
        params = {}
        if keyword:
            params["keyword"] = keyword
        if channel_code:
            params["channel_code"] = channel_code
        if store_code:
            params["store_code"] = store_code
        if readiness_badge:
            params["readiness_badge"] = readiness_badge
        if limit != 100:
            params["limit"] = str(limit)
        if offset:
            params["offset"] = str(offset)

        query = ("?" + urlencode(params)) if params else ""
        return await self._request(
            "GET", f"/api/device-dashboard{query}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Airtime Occupancy & Conflicts (42.1) ─────────────────────────

    def creative_preview_url(self, creative_code: str) -> str:
        """Relative URL for creative preview — safe, no backend URL exposed."""
        return f"/api/creatives/by-code/{creative_code}/preview"

    async def get_airtime_occupancy(
        self, access_token: str,
        device_code: str, date_from: str, date_to: str,
        placement_code: str | None = None,
    ) -> dict:
        """GET /api/airtime/occupancy → {ok, data}.

        Planned airtime occupancy — not PoP fact.
        Requires reports.read permission.
        """
        from urllib.parse import urlencode
        params = {
            "device_code": device_code,
            "date_from": date_from,
            "date_to": date_to,
        }
        if placement_code:
            params["placement_code"] = placement_code
        return await self._request(
            "GET", f"/api/airtime/occupancy?{urlencode(params)}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_airtime_conflicts(
        self, access_token: str,
        device_code: str, date_from: str, date_to: str,
        campaign_code: str | None = None,
    ) -> dict:
        """GET /api/airtime/conflicts → {ok, data: [conflict]}.

        Schedule slot conflicts — safe projection.
        Advertiser sees anonymized conflicts.
        Requires reports.read permission.
        """
        from urllib.parse import urlencode
        params = {
            "device_code": device_code,
            "date_from": date_from,
            "date_to": date_to,
        }
        if campaign_code:
            params["campaign_code"] = campaign_code
        return await self._request(
            "GET", f"/api/airtime/conflicts?{urlencode(params)}",
            headers={"Authorization": f"Bearer {access_token}"},
        )


    # ── Reports Export (42.3) ─────────────────────────────────────────

    async def export_campaigns_csv(self, access_token: str) -> dict:
        """GET /api/reports/campaigns/export → CSV text response."""
        return await self._request_raw(
            "GET", "/api/reports/campaigns/export",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def export_airtime_csv(
        self, access_token: str, device_codes: list[str],
    ) -> dict:
        """GET /api/reports/airtime/export → CSV text response."""
        from urllib.parse import urlencode
        params = urlencode({"device_codes": ",".join(device_codes)})
        return await self._request_raw(
            "GET", f"/api/reports/airtime/export?{params}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def export_conflicts_csv(
        self, access_token: str, device_codes: list[str],
    ) -> dict:
        """GET /api/reports/conflicts/export → CSV text response."""
        from urllib.parse import urlencode
        params = urlencode({"device_codes": ",".join(device_codes)})
        return await self._request_raw(
            "GET", f"/api/reports/conflicts/export?{params}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def export_publications_csv(self, access_token: str) -> dict:
        """GET /api/reports/publications/export → CSV text response."""
        return await self._request_raw(
            "GET", "/api/reports/publications/export",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # ── Inventory Engine (44.1) ────────────────────────────────────

    async def get_inventory_availability(
        self, access_token: str, payload: dict,
    ) -> dict:
        """POST /api/inventory/availability → {ok, data: {items, summary}}."""
        return await self._request_json(
            "POST", "/api/inventory/availability",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_inventory_forecast(
        self, access_token: str, payload: dict,
    ) -> dict:
        """POST /api/inventory/forecast → {ok, data: ForecastResponse}."""
        return await self._request_json(
            "POST", "/api/inventory/forecast",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get_inventory_snapshot(
        self, access_token: str,
        branch_id: str | None = None,
        cluster_id: str | None = None,
        store_id: str | None = None,
    ) -> dict:
        """GET /api/inventory/snapshot → {ok, data: snapshot}."""
        params = {}
        if branch_id:
            params["branch_id"] = branch_id
        if cluster_id:
            params["cluster_id"] = cluster_id
        if store_id:
            params["store_id"] = store_id
        return await self._request_json(
            "GET", "/api/inventory/snapshot",
            params=params,
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
