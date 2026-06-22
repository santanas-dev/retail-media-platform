"""Retail Media Platform — Web Portal UI v1 (KSO-only).

FastAPI + Jinja2 server-rendered portal.
No external CDN. Auth integration with backend API.
"""

import os
from fastapi import FastAPI, Request, Form
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
from rbac import require_admin_access, require_portal_permission

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
    auth_required: bool = False,
):
    """Return a route handler for a page with optional demo data.

    auth_required: if True, return 401 redirect to login when
        unauthenticated (soft enforcement — TODO: enable after Step 36.6).
    """
    async def handler(request: Request):
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

        # Soft auth gate (disabled for now — contract documented)
        if auth_required and current_user is None:
            # TODO Step 36.7+: enable redirect to login with ?next= parameter
            pass

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
app.add_api_route("/creatives", _page("pages/creatives.html", "Креативы", "creatives",
                                      {"creatives": get_creatives_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/schedule", _page("pages/schedule.html", "Расписание", "schedule",
                                     {"schedules": get_schedules_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/publications", _page("pages/publications.html", "Публикации", "publications",
                                         {"publications": get_publications_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/stores", _page("pages/stores.html", "Магазины", "stores",
                                   {"stores": get_stores_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/devices", _page("pages/devices.html", "КСО Устройства", "devices",
                                    {"devices": get_devices_data()}),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/proof-of-play", _page("pages/proof-of-play.html", "Proof of Play", "pop",
                                          {"pop_events": get_pop_events_data()}),
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
    safe_display_name = username

    if me_result["ok"]:
        me_data = me_result["data"]
        safe_roles = me_data.get("roles", [])
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
