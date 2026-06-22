"""Retail Media Platform — Web Portal UI v1 (KSO-only).

FastAPI + Jinja2 server-rendered portal.
No external CDN. Auth integration with backend API.
"""

import os
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from starlette.middleware.sessions import SessionMiddleware

from demo_data import (
    get_dashboard_data,
    get_stores_data,
    get_devices_data,
    get_campaigns_data,
    get_creatives_data,
    get_schedules_data,
    get_publications_data,
    get_pop_events_data,
    get_approvals_data,
    get_report_kpi,
    get_report_table,
    get_users_data,
)
from backend_client import backend_login, backend_me, backend_logout, BackendClient
from portal_session import (
    PortalUser,
    get_current_portal_user,
    create_portal_session,
    clear_portal_session,
    get_portal_tokens,
)
from rbac import require_admin_access, require_portal_permission, require_auth_for_page

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Retail Media Platform — Portal", version="0.2.0")

# Session middleware — signed httpOnly cookie, 1-hour max age.
# Secret from env for production; dev-safe default for localhost.
_SESSION_SECRET = os.getenv(
    "PORTAL_SESSION_SECRET",
    "portal-dev-secret-change-in-production-min-32-chars!!",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    session_cookie="portal_session",
    max_age=3600,  # 1 hour
    same_site="lax",
    https_only=False,  # True in production with TLS
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ══════════════════════════════════════════════════════════════════════
# Template context helpers
# ══════════════════════════════════════════════════════════════════════

def _page(
    template: str,
    title: str,
    active: str,
    extra: dict | None = None,
    route: str | None = None,
):
    """Return a route handler for a page with demo data + RBAC guard.

    Route-level RBAC: checks session + permission from server-side store.
    No backend API call — permissions cached from login /me.
    Unauthenticated → redirect to /login. No permission → 403.
    """
    async def handler(request: Request):
        # Route-level RBAC guard (session-only, no backend call)
        guard = await require_auth_for_page(request, route or f"/{active}")
        if guard is not None:
            return guard

        current_user = get_current_portal_user(request)
        ctx = {
            "request": request,
            "title": title,
            "active": active,
            "demo": True,
            "current_user": current_user,
        }
        if extra:
            ctx.update(extra)

        return templates.TemplateResponse(request, template, ctx)
    return handler


# ══════════════════════════════════════════════════════════════════════
# Pages
# ══════════════════════════════════════════════════════════════════════

app.add_api_route("/", _page("pages/dashboard.html", "Dashboard", "dashboard",
                             get_dashboard_data()),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/dashboard", _page("pages/dashboard.html", "Dashboard", "dashboard",
                                      get_dashboard_data()),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/campaigns", _page("pages/campaigns.html", "Кампании", "campaigns",
                                      {"campaigns": get_campaigns_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/schedule", _page("pages/schedule.html", "Расписание", "schedule",
                                     {"schedules": get_schedules_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/publications", _page("pages/publications.html", "Публикации", "publications",
                                         {"publications": get_publications_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/proof-of-play", _page("pages/proof-of-play.html", "Proof of Play", "pop",
                                          {"pop_events": get_pop_events_data()},
                                          route="/proof-of-play"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/reports", _page("pages/reports.html", "Отчёты", "reports",
                                    {"report_kpi": get_report_kpi(),
                                     "report_table": get_report_table()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/deployment", _page("pages/deployment.html", "Развёртывание", "deployment"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/admin", _page("pages/admin.html", "Администрирование", "admin",
                                {"users": get_users_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/approvals", _page("pages/approvals.html", "Согласования", "approvals",
                                      {"approvals": get_approvals_data()}),
                  methods=["GET"], response_class=HTMLResponse)


# ══════════════════════════════════════════════════════════════════════
# Hierarchy & KSO Devices — Backend API Integration (Step 37.2)
# ══════════════════════════════════════════════════════════════════════

@app.get("/stores", response_class=HTMLResponse)
async def stores_page(request: Request):
    """Stores page: read-only backend hierarchy API.

    Fetches branches, clusters, stores, and KSO devices from backend.
    Builds safe projection: branch_name, cluster_name, store name/code/format/status,
    kso_count. Never exposes backend URL, tokens, UUIDs, or secrets.
    """
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/stores")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    backend = BackendClient()

    if not access_token:
        return _stores_fallback(request, current_user, "No access token")

    # Fetch hierarchy in parallel-ish
    branches_r = await backend.list_branches(access_token)
    clusters_r = await backend.list_clusters(access_token)
    stores_r = await backend.list_stores(access_token)
    kso_r = await backend.list_kso_devices(access_token)

    if not all([branches_r["ok"], clusters_r["ok"], stores_r["ok"], kso_r["ok"]]):
        return _stores_fallback(request, current_user, "Backend unavailable")

    from hierarchy_projection import build_store_rows
    stores = build_store_rows(
        stores_r["data"], clusters_r["data"],
        branches_r["data"], kso_r["data"],
    )

    return templates.TemplateResponse(request, "pages/stores.html", {
        "request": request,
        "title": "Магазины",
        "active": "stores",
        "demo": False,
        "current_user": current_user,
        "stores": stores,
        "store_count": len(stores),
        "kso_total": sum(s.get("kso_count", 0) for s in stores),
    })


@app.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    """Devices page: read-only backend KSO device API.

    Fetches KSO devices and stores from backend.
    Builds safe projection: device_code, display_name, store_name, status,
    versions, screen geometry. Never exposes backend URL, tokens, UUIDs, or secrets.
    """
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/devices")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    backend = BackendClient()

    if not access_token:
        return _devices_fallback(request, current_user, "No access token")

    stores_r = await backend.list_stores(access_token)
    kso_r = await backend.list_kso_devices(access_token)

    if not all([stores_r["ok"], kso_r["ok"]]):
        return _devices_fallback(request, current_user, "Backend unavailable")

    from hierarchy_projection import build_device_rows
    devices = build_device_rows(kso_r["data"], stores_r["data"])

    return templates.TemplateResponse(request, "pages/devices.html", {
        "request": request,
        "title": "КСО Устройства",
        "active": "devices",
        "demo": False,
        "current_user": current_user,
        "devices": devices,
    })


def _stores_fallback(request: Request, current_user, reason: str = "") -> HTMLResponse:
    """Safe fallback when backend is unreachable."""
    return templates.TemplateResponse(request, "pages/stores.html", {
        "request": request,
        "title": "Магазины",
        "active": "stores",
        "demo": False,
        "current_user": current_user,
        "stores": [],
        "backend_unavailable": True,
        "backend_message": "Данные временно недоступны. Попробуйте позже.",
    })


def _devices_fallback(request: Request, current_user, reason: str = "") -> HTMLResponse:
    """Safe fallback when backend is unreachable."""
    return templates.TemplateResponse(request, "pages/devices.html", {
        "request": request,
        "title": "КСО Устройства",
        "active": "devices",
        "demo": False,
        "current_user": current_user,
        "devices": [],
        "backend_unavailable": True,
        "backend_message": "Данные временно недоступны. Попробуйте позже.",
    })


# ══════════════════════════════════════════════════════════════════════
# Creatives — Backend API Integration (Step 37.3)
# ══════════════════════════════════════════════════════════════════════

@app.get("/creatives", response_class=HTMLResponse)
async def creatives_page(request: Request):
    """Creatives page: list from backend + upload form (Step 37.3)."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/creatives")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    backend = BackendClient()

    if not access_token:
        return _creatives_fallback(request, current_user)

    result = await backend.list_creatives(access_token)
    if not result["ok"]:
        return _creatives_fallback(request, current_user)

    creatives = result.get("data", [])
    # Build safe rows for template
    safe_rows = []
    for c in creatives:
        safe_rows.append({
            "creative_code": c.get("creative_code", ""),
            "name": c.get("name", ""),
            "status": c.get("status", "—"),
            "content_type": c.get("content_type") or "—",
            "width": c.get("width"),
            "height": c.get("height"),
            "file_size_bytes": c.get("file_size_bytes"),
            "created_at": _fmt_dt(c.get("created_at")),
        })

    # Consume flash messages
    flash_type = ""
    flash_msg = ""
    raw = request.session.pop("creative_flash", "")
    if raw == "ok:uploaded":
        flash_type = "success"
        flash_msg = "Креатив успешно загружен."
    elif raw == "error":
        flash_type = "error"
        flash_msg = request.session.pop("creative_flash_msg", "Ошибка загрузки.")

    return templates.TemplateResponse(request, "pages/creatives.html", {
        "request": request,
        "title": "Креативы",
        "active": "creatives",
        "demo": False,
        "current_user": current_user,
        "creatives": safe_rows,
        "flash_type": flash_type,
        "flash_msg": flash_msg,
    })


@app.post("/creatives/upload", response_class=HTMLResponse)
async def creatives_upload(
    request: Request,
    creative_code: str = Form(...),
    name: str = Form(...),
    file: UploadFile = File(...),
):
    """Handle creative upload — POST /creatives/upload → backend (Step 37.3)."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/creatives")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    if not access_token:
        request.session["creative_flash"] = "error"
        request.session["creative_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/creatives", status_code=303)

    content = await file.read()
    backend = BackendClient()
    result = await backend.upload_creative(
        access_token, creative_code.strip(), name.strip(),
        content, file.filename or "upload", file.content_type or "application/octet-stream",
    )

    if result["ok"]:
        request.session["creative_flash"] = "ok:uploaded"
    else:
        request.session["creative_flash"] = "error"
        request.session["creative_flash_msg"] = result.get("error", "Ошибка загрузки")[:200]

    return RedirectResponse(url="/creatives", status_code=303)


def _creatives_fallback(request: Request, current_user) -> HTMLResponse:
    return templates.TemplateResponse(request, "pages/creatives.html", {
        "request": request,
        "title": "Креативы",
        "active": "creatives",
        "demo": False,
        "current_user": current_user,
        "creatives": [],
        "backend_unavailable": True,
        "backend_message": "Данные временно недоступны. Попробуйте позже.",
    })


def _fmt_dt(val) -> str:
    if not val:
        return "—"
    s = str(val)
    if "T" in s:
        s = s.replace("T", " ").split("+")[0].split("Z")[0]
        if len(s) > 16:
            s = s[:16]
    return s


# ══════════════════════════════════════════════════════════════════════
# Admin — Read-Only Backend API Integration (Step 36.7)
# ══════════════════════════════════════════════════════════════════════

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin page: RBAC-guarded, read-only backend API integration.

    Flow:
    1. Check portal session (opaque cookie → server-side store)
    2. RBAC guard: require users.read + roles.read
    3. Fetch users, roles, permissions, audit from backend API
    4. Render with real data or safe fallback
    """
    current_user = get_current_portal_user(request)

    # RBAC guard
    guard = await require_admin_access(request)
    if guard is not None:
        return guard

    # Fetch data from backend
    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    backend = BackendClient()
    admin_data = await _fetch_admin_data(backend, access_token)

    # Consume flash messages (set by POST /admin/users/create)
    flash_type = ""
    flash_msg = ""
    raw = request.session.pop("admin_flash", "")
    if raw == "ok:user_created":
        flash_type = "success"
        flash_msg = f"Пользователь «{request.session.pop('admin_flash_user', '')}» успешно создан."
    elif raw == "ok:roles_assigned":
        flash_type = "success"
        flash_msg = "Роли пользователя обновлены."
    elif raw == "ok:rls_scopes_assigned":
        flash_type = "success"
        flash_msg = "Области доступа пользователя обновлены."
    elif raw == "ok:user_blocked":
        flash_type = "success"
        flash_msg = "Пользователь заблокирован."
    elif raw == "ok:user_archived":
        flash_type = "success"
        flash_msg = "Пользователь архивирован."
    elif raw == "error":
        flash_type = "error"
        flash_msg = request.session.pop("admin_flash_msg", "Ошибка при создании пользователя.")

    return templates.TemplateResponse(request, "pages/admin.html", {
        "request": request,
        "title": "Администрирование",
        "active": "admin",
        "demo": False,  # Real backend data
        "current_user": current_user,
        "backend_available": admin_data["backend_ok"],
        "users": admin_data.get("users", []),
        "roles": admin_data.get("roles", []),
        "permissions": admin_data.get("permissions", []),
        "audit_events": admin_data.get("audit_events", []),
        "users_count": len(admin_data.get("users", [])),
        "roles_count": len(admin_data.get("roles", [])),
        "flash_type": flash_type,
        "flash_msg": flash_msg,
    })


async def _fetch_admin_data(backend: BackendClient, access_token: str) -> dict:
    """Fetch users, roles, permissions, audit from backend API.

    Returns a dict safe for template rendering. If backend is unreachable,
    returns empty data with backend_ok=False and a safe message.
    Never exposes raw tokens, password hashes, or secrets.
    """
    if not access_token:
        return {"backend_ok": False, "error": "No access token"}

    # Fetch in parallel (sequential in practice, but structured)
    users_result = await backend.list_users(access_token)
    roles_result = await backend.list_roles(access_token)
    perms_result = await backend.list_permissions(access_token)
    audit_result = await backend.list_admin_audit(access_token, limit=10)

    # If the first call fails, backend is likely unreachable
    backend_ok = users_result["ok"]

    return {
        "backend_ok": backend_ok,
        # Users — strip sensitive fields
        "users": _safe_users(users_result.get("data", [])),
        # Roles
        "roles": roles_result.get("data", []) if roles_result["ok"] else [],
        # Permissions summary
        "permissions": perms_result.get("data", []) if perms_result["ok"] else [],
        # Audit events
        "audit_events": _safe_audit(audit_result.get("data", [])),
    }


def _safe_users(data: list) -> list[dict]:
    """Strip sensitive fields from user objects before rendering."""
    safe = []
    forbidden = frozenset({
        "password_hash", "password", "token_hash",
        "access_token", "refresh_token", "authorization",
        "device_secret", "client_secret",
    })
    for u in data:
        if not isinstance(u, dict):
            continue
        item = {}
        for k, v in u.items():
            if k.lower() in forbidden:
                continue
            item[k] = v
        safe.append(item)
    return safe


def _safe_audit(data: list) -> list[dict]:
    """Strip sensitive fields from audit events."""
    safe = []
    forbidden = frozenset({
        "token", "password", "secret", "hash",
        "access_token", "refresh_token",
    })
    for e in data:
        if not isinstance(e, dict):
            continue
        item = {}
        for k, v in e.items():
            if k.lower() not in forbidden:
                # Truncate details_json for safety
                if k == "details_json" and isinstance(v, dict):
                    v = {dk: dv for dk, dv in v.items()
                         if dk.lower() not in forbidden}
                item[k] = v
        safe.append(item)
    return safe


# ══════════════════════════════════════════════════════════════════════
# Admin Actions — Create User (Step 36.8)
# ══════════════════════════════════════════════════════════════════════

# Roles allowed for human portal users (excludes device_service).
HUMAN_ROLES = frozenset({
    "system_admin", "security_admin", "ad_manager",
    "approver", "analyst", "advertiser", "operations",
})


@app.post("/admin/users/create", response_class=HTMLResponse)
async def admin_create_user(
    request: Request,
    username: str = Form(..., min_length=1, max_length=100),
    password: str = Form(..., min_length=8, max_length=128),
    display_name: str = Form("", max_length=255),
):
    """Create a new local portal user via backend API.

    Flow:
    1. RBAC: require users.create permission
    2. Build safe payload (no email, no device_service)
    3. POST /api/users via backend client
    4. Redirect to /admin with success/error via session flash
    """
    # RBAC guard
    guard = await require_portal_permission(request, "users.create")
    if guard is not None:
        return guard

    # Build payload — safe: no email, no phone, no device_service
    payload = {
        "username": username.strip(),
        "password": password,
    }
    if display_name and display_name.strip():
        payload["display_name"] = display_name.strip()

    # Get access token from server-side store
    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    backend = BackendClient()
    result = await backend.create_user(access_token, payload)

    if result["ok"]:
        request.session["admin_flash"] = "ok:user_created"
        request.session["admin_flash_user"] = username
    else:
        error = result.get("error", "Не удалось создать пользователя")
        # Safe truncation
        if len(error) > 200:
            error = error[:200]
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = error

    return RedirectResponse(url="/admin", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# Admin Actions — Assign Roles (Step 36.9)
# ══════════════════════════════════════════════════════════════════════

@app.post("/admin/users/assign-roles", response_class=HTMLResponse)
async def admin_assign_roles(
    request: Request,
    username: str = Form(..., min_length=1, max_length=100),
    roles: list[str] = Form([], max_length=20),
):
    """Assign roles to a user via backend API.

    Flow:
    1. RBAC: require roles.manage permission
    2. Validate username and roles
    3. Reject device_service from portal human assignment
    4. Call BackendClient.assign_user_roles()
    5. Redirect to /admin with success/error via session flash
    """
    # RBAC guard
    guard = await require_portal_permission(request, "roles.manage")
    if guard is not None:
        return guard

    # Validate username
    username = username.strip()
    if not username:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = "Имя пользователя не указано."
        return RedirectResponse(url="/admin", status_code=303)

    # Validate: deduplicate and strip roles
    seen = set()
    clean_roles: list[str] = []
    for r in roles:
        r = r.strip()
        if r and r not in seen:
            seen.add(r)
            clean_roles.append(r)

    if not clean_roles:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = "Не выбраны роли для назначения."
        return RedirectResponse(url="/admin", status_code=303)

    # Reject device_service from portal human assignment
    if "device_service" in clean_roles:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = (
            "Роль device_service не может быть назначена через портал."
        )
        return RedirectResponse(url="/admin", status_code=303)

    # Reject roles not in HUMAN_ROLES (extra safety net)
    unknown = set(clean_roles) - HUMAN_ROLES
    if unknown:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = (
            f"Недопустимые роли: {', '.join(sorted(unknown))}."
        )
        return RedirectResponse(url="/admin", status_code=303)

    # Get access token from server-side store
    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    backend = BackendClient()
    result = await backend.assign_user_roles(access_token, username, clean_roles)

    if result["ok"]:
        request.session["admin_flash"] = "ok:roles_assigned"
    else:
        error = result.get("error", "Не удалось обновить роли пользователя.")
        if len(error) > 200:
            error = error[:200]
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = error

    return RedirectResponse(url="/admin", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# Admin Actions — Assign RLS Scopes (Step 36.10)
# ══════════════════════════════════════════════════════════════════════

# Allowed RLS scope types (mirrors backend ALLOWED_RLS_SCOPE_TYPES).
ALLOWED_RLS_SCOPE_TYPES = frozenset({
    "advertiser_scope", "branch_scope", "store_scope",
    "campaign_scope", "device_scope", "approval_scope", "report_scope",
})

# Safe characters for scope_value: letters, digits, underscore, dash, colon, dot.
import re as _re
_SCOPE_VALUE_RE = _re.compile(r"^[a-zA-Z0-9_\-.:]+$")

# Patterns that look like email or phone — reject.
_SCOPE_VALUE_BAD_RE = _re.compile(r"@|\+?\d{7,}")


@app.post("/admin/users/assign-rls-scopes", response_class=HTMLResponse)
async def admin_assign_rls_scopes(
    request: Request,
    username: str = Form(..., min_length=1, max_length=100),
    rls_scopes_text: str = Form("", max_length=5000),
):
    """Assign RLS scopes to a user via backend API.

    Flow:
    1. RBAC: require roles.manage permission
    2. Validate username
    3. Parse textarea lines (scope_type:scope_value)
    4. Validate scope_type against ALLOWED_RLS_SCOPE_TYPES
    5. Validate scope_value (safe chars, no email/phone patterns)
    6. Call BackendClient.assign_user_rls_scopes()
    7. Redirect to /admin with success/error via session flash

    Format: one scope per line, "scope_type:scope_value"
    Example: branch_scope:demo_branch_north
    """
    # RBAC guard
    guard = await require_portal_permission(request, "roles.manage")
    if guard is not None:
        return guard

    # Validate username
    username = username.strip()
    if not username:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = "Имя пользователя не указано."
        return RedirectResponse(url="/admin", status_code=303)

    # Parse textarea lines
    raw_lines = rls_scopes_text.strip()
    if not raw_lines:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = "Не указаны области доступа."
        return RedirectResponse(url="/admin", status_code=303)

    scopes: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for line_num, raw_line in enumerate(raw_lines.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue  # skip empty lines

        # Parse scope_type:scope_value
        if ":" not in line:
            request.session["admin_flash"] = "error"
            request.session["admin_flash_msg"] = (
                f"Строка {line_num}: неверный формат. "
                f"Ожидается scope_type:scope_value."
            )
            return RedirectResponse(url="/admin", status_code=303)

        scope_type, _, scope_value = line.partition(":")
        scope_type = scope_type.strip()
        scope_value = scope_value.strip()

        # Validate scope_type
        if scope_type not in ALLOWED_RLS_SCOPE_TYPES:
            request.session["admin_flash"] = "error"
            request.session["admin_flash_msg"] = (
                f"Строка {line_num}: недопустимый тип области «{scope_type}». "
                f"Допустимые: {', '.join(sorted(ALLOWED_RLS_SCOPE_TYPES))}."
            )
            return RedirectResponse(url="/admin", status_code=303)

        # Validate scope_value
        if not scope_value:
            request.session["admin_flash"] = "error"
            request.session["admin_flash_msg"] = (
                f"Строка {line_num}: значение области не указано."
            )
            return RedirectResponse(url="/admin", status_code=303)

        if len(scope_value) < 1 or len(scope_value) > 128:
            request.session["admin_flash"] = "error"
            request.session["admin_flash_msg"] = (
                f"Строка {line_num}: значение области должно быть 1–128 символов."
            )
            return RedirectResponse(url="/admin", status_code=303)

        if not _SCOPE_VALUE_RE.match(scope_value):
            request.session["admin_flash"] = "error"
            request.session["admin_flash_msg"] = (
                f"Строка {line_num}: значение содержит недопустимые символы. "
                f"Разрешены: буквы, цифры, _, -, :, точка."
            )
            return RedirectResponse(url="/admin", status_code=303)

        if _SCOPE_VALUE_BAD_RE.search(scope_value):
            request.session["admin_flash"] = "error"
            request.session["admin_flash_msg"] = (
                f"Строка {line_num}: значение не должно содержать @ или "
                f"телефонные номера."
            )
            return RedirectResponse(url="/admin", status_code=303)

        # Deduplicate
        dedup_key = (scope_type, scope_value)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        scopes.append({
            "scope_type": scope_type,
            "scope_value": scope_value,
            "is_active": True,
        })

    if not scopes:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = (
            "Не удалось разобрать ни одной области доступа."
        )
        return RedirectResponse(url="/admin", status_code=303)

    # Get access token from server-side store
    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    backend = BackendClient()
    result = await backend.assign_user_rls_scopes(access_token, username, scopes)

    if result["ok"]:
        request.session["admin_flash"] = "ok:rls_scopes_assigned"
    else:
        error = result.get("error", "Не удалось обновить области доступа пользователя.")
        if len(error) > 200:
            error = error[:200]
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = error

    return RedirectResponse(url="/admin", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# Admin Actions — Block User (Step 36.11)
# ══════════════════════════════════════════════════════════════════════

@app.post("/admin/users/block", response_class=HTMLResponse)
async def admin_block_user(
    request: Request,
    username: str = Form(..., min_length=1, max_length=100),
):
    """Block a user via backend API.

    Flow:
    1. RBAC: require users.manage permission
    2. Validate username
    3. Call BackendClient.block_user()
    4. Redirect to /admin with success/error via session flash

    Backend enforces: cannot block self, cannot block last system_admin.
    """
    # RBAC guard
    guard = await require_portal_permission(request, "users.manage")
    if guard is not None:
        return guard

    # Validate username
    username = username.strip()
    if not username:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = "Имя пользователя не указано."
        return RedirectResponse(url="/admin", status_code=303)

    # Get access token from server-side store
    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    backend = BackendClient()
    result = await backend.block_user(access_token, username)

    if result["ok"]:
        request.session["admin_flash"] = "ok:user_blocked"
    else:
        error = result.get("error", "Не удалось заблокировать пользователя.")
        if len(error) > 200:
            error = error[:200]
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = error

    return RedirectResponse(url="/admin", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# Admin Actions — Archive User (Step 36.12)
# ══════════════════════════════════════════════════════════════════════

@app.post("/admin/users/archive", response_class=HTMLResponse)
async def admin_archive_user(
    request: Request,
    username: str = Form(..., min_length=1, max_length=100),
):
    """Archive a user via backend API (logical delete, not hard delete).

    Flow:
    1. RBAC: require users.manage permission
    2. Validate username
    3. Call BackendClient.archive_user()
    4. Redirect to /admin with success/error via session flash

    Backend enforces: cannot archive self, cannot archive last system_admin.
    Archived users have is_archived=True, is_active=False — no physical delete.
    """
    # RBAC guard
    guard = await require_portal_permission(request, "users.manage")
    if guard is not None:
        return guard

    # Validate username
    username = username.strip()
    if not username:
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = "Имя пользователя не указано."
        return RedirectResponse(url="/admin", status_code=303)

    # Get access token from server-side store
    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    backend = BackendClient()
    result = await backend.archive_user(access_token, username)

    if result["ok"]:
        request.session["admin_flash"] = "ok:user_archived"
    else:
        error = result.get("error", "Не удалось архивировать пользователя.")
        if len(error) > 200:
            error = error[:200]
        request.session["admin_flash"] = "error"
        request.session["admin_flash_msg"] = error

    return RedirectResponse(url="/admin", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# Auth — Local Login / Logout (server-side POST)
# ══════════════════════════════════════════════════════════════════════

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login form."""
    current_user = get_current_portal_user(request)
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request, "pages/login.html", {
        "request": request,
        "title": "Вход",
        "active": "login",
        "demo": True,
        "current_user": None,
        "error": None,
    })


@app.post("/login", response_class=HTMLResponse)
async def login_handler(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Server-side login: POST username+password to backend /api/auth/login.

    On success: creates portal session (signed httpOnly cookie).
    On failure: re-renders login page with a safe error message.
    """
    # Call backend
    result = await backend_login(username, password)

    if not result["ok"]:
        # Safe error — never reveal which field is wrong
        error = "Неверное имя пользователя или пароль"
        if result.get("status") in (423,):
            error = "Учётная запись заблокирована. Попробуйте позже."
        elif result.get("status") == 403:
            error = "Вход запрещён. Обратитесь к администратору."
        elif result.get("status") in (502, 504):
            error = "Сервер авторизации временно недоступен. Попробуйте позже."
        return templates.TemplateResponse(request, "pages/login.html", {
            "request": request,
            "title": "Вход",
            "active": "login",
            "demo": True,
            "current_user": None,
            "error": error,
        }, status_code=401)

    data = result["data"]

    # Fetch safe user view from /api/auth/me
    me_result = await backend_me(data["access_token"])
    safe_roles: list[str] = []
    safe_perms: list[str] = []
    safe_display_name = username

    if me_result["ok"]:
        me_data = me_result["data"]
        safe_roles = me_data.get("roles", [])
        safe_perms = me_data.get("permissions", [])
        safe_display_name = me_data.get("display_name") or username

    # Create portal session — tokens go to server-side store,
    # browser gets only opaque session_id in signed httpOnly cookie.
    create_portal_session(
        request,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        username=username,
        display_name=safe_display_name,
        roles=safe_roles,
        permissions=safe_perms,
    )

    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/logout", response_class=HTMLResponse)
async def logout_page(request: Request):
    """Render the logout confirmation page."""
    current_user = get_current_portal_user(request)
    return templates.TemplateResponse(request, "pages/logout.html", {
        "request": request,
        "title": "Выход",
        "active": "logout",
        "demo": True,
        "current_user": current_user,
    })


@app.post("/logout", response_class=HTMLResponse)
async def logout_handler(request: Request):
    """Server-side logout: call backend /api/auth/logout if session exists,
    then clear portal session."""
    current_user = get_current_portal_user(request)

    if current_user is not None:
        # Get refresh token from server-side store (never from cookie)
        tokens = get_portal_tokens(request)
        if tokens.get("refresh_token"):
            await backend_logout(tokens["refresh_token"])

    # Clear all auth state
    clear_portal_session(request)

    return templates.TemplateResponse(request, "pages/logout.html", {
        "request": request,
        "title": "Выход",
        "active": "logout",
        "demo": True,
        "current_user": None,
        "logged_out": True,
    })


# ══════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def portal_health():
    return {"status": "ok", "portal": "v2", "auth": "local-integrated",
            "stack": "FastAPI + Jinja2"}
