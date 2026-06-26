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
    get_approvals_data,
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
# Dashboard — Backend-Driven KPI Integration (39.2.3)
# ══════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Dashboard: backend-driven KPI cards from real data (39.2.3).

    Computes KPI from existing safe list endpoints — no new backend endpoint.
    Shows real counts: campaigns, creatives, devices, schedules, publications,
    approvals pending. Falls back safely on partial backend errors.
    """
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/dashboard")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    backend = BackendClient()

    if not access_token:
        return _dashboard_fallback(request, current_user, "Нет доступа.")

    # Fetch all KPI sources
    campaigns_r = await backend.list_campaigns_prod(access_token)  # production
    creatives_r = await backend.list_creatives(access_token)
    devices_r = await backend.list_kso_devices(access_token)
    schedules_r = await backend.list_schedules(access_token)
    manifests_r = await backend.list_manifests(access_token)  # production /api/manifests
    approvals_r = await backend.list_approvals(access_token)

    # Count unreachable backends
    errors = 0
    for r in (campaigns_r, creatives_r, devices_r, schedules_r, manifests_r, approvals_r):
        if not r["ok"]:
            errors += 1

    if errors >= 4:
        return _dashboard_fallback(request, current_user, "Backend недоступен.")

    # ── KPI computation (safe, no UUIDs) ──
    campaigns = campaigns_r.get("data", []) if campaigns_r["ok"] else []
    creatives = creatives_r.get("data", []) if creatives_r["ok"] else []
    devices = devices_r.get("data", []) if devices_r["ok"] else []
    schedules = schedules_r.get("data", []) if schedules_r["ok"] else []
    manifests = manifests_r.get("data", []) if manifests_r["ok"] else []
    approvals = approvals_r.get("data", []) if approvals_r["ok"] else []

    total_campaigns = len(campaigns)
    active_campaigns = sum(1 for c in campaigns if c.get("status") == "active")
    draft_campaigns = sum(1 for c in campaigns if c.get("status") == "draft")
    total_creatives = len(creatives)
    total_devices = len(devices)
    total_schedules = len(schedules)
    active_schedules = sum(1 for s in schedules if s.get("status") == "active")
    total_publications = len(manifests)
    approvals_pending = sum(
        1 for a in approvals if a.get("status") in ("pending", "in_review")
    )

    # Build KPI dict
    kpi = {
        "total_campaigns": total_campaigns,
        "active_campaigns": active_campaigns,
        "draft_campaigns": draft_campaigns,
        "total_creatives": total_creatives,
        "total_devices": total_devices,
        "total_schedules": total_schedules,
        "active_schedules": active_schedules,
        "total_publications": total_publications,
        "approvals_pending": approvals_pending,
    }

    dashboard_backend = True
    backend_warning = f"Часть данных недоступна ({errors} источников)." if errors > 0 else ""

    return templates.TemplateResponse(request, "pages/dashboard.html", {
        "request": request,
        "title": "Dashboard",
        "active": "dashboard",
        "demo": False,
        "current_user": current_user,
        "kpi": kpi,
        "dashboard_backend": dashboard_backend,
        "backend_warning": backend_warning,
    })


def _dashboard_fallback(request: Request, current_user, reason: str = "") -> HTMLResponse:
    return templates.TemplateResponse(request, "pages/dashboard.html", {
        "request": request,
        "title": "Dashboard",
        "active": "dashboard",
        "demo": False,
        "current_user": current_user,
        "kpi": {},
        "dashboard_backend": False,
        "backend_warning": reason or "Данные временно недоступны.",
    })

# ══════════════════════════════════════════════════════════════════════
# Proof of Play — Backend API Integration (Step 37.11)
# ══════════════════════════════════════════════════════════════════════

@app.get("/proof-of-play", response_class=HTMLResponse)
async def proof_of_play_page(request: Request):
    """Proof of Play page: backend-driven PoP event list + filters (Step 37.11).

    Fetches PoP events from backend, builds safe KPI, renders filter form
    and event table. Never exposes raw UUIDs, tokens, manifest internals,
    file_paths, or secrets.
    """
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/proof-of-play")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    backend = BackendClient()

    if not access_token:
        return _pop_fallback(request, current_user, "No access token")

    # Collect filter values from query params (server-side GET form)
    filters = {}
    for key in ("device_code", "campaign_code", "creative_code",
                "placement_code", "date_from", "date_to"):
        val = request.query_params.get(key)
        if val:
            filters[key] = val

    limit = 100
    filters["limit"] = limit

    result = await backend.list_pop_events(access_token, filters)
    if not result["ok"]:
        return _pop_fallback(request, current_user, "Backend unavailable")

    events = result.get("data", [])

    # Safe KPI computation (no raw IDs, no secrets)
    kpi_total = len(events)
    kpi_unique_devices = len(set(e.get("device_code", "") for e in events))
    kpi_unique_campaigns = len(set(e.get("campaign_code", "") for e in events))

    return templates.TemplateResponse(request, "pages/proof-of-play.html", {
        "request": request,
        "title": "Proof of Play",
        "active": "pop",
        "demo": False,
        "current_user": current_user,
        "pop_events": events,
        "kpi_total": kpi_total,
        "kpi_unique_devices": kpi_unique_devices,
        "kpi_unique_campaigns": kpi_unique_campaigns,
        "filters": filters,
    })


def _pop_fallback(request: Request, current_user, reason: str = "") -> HTMLResponse:
    """Safe fallback when backend is unreachable."""
    return templates.TemplateResponse(request, "pages/proof-of-play.html", {
        "request": request,
        "title": "Proof of Play",
        "active": "pop",
        "demo": False,
        "current_user": current_user,
        "pop_events": [],
        "kpi_total": 0,
        "kpi_unique_devices": 0,
        "kpi_unique_campaigns": 0,
        "filters": {},
        "backend_unavailable": True,
        "backend_message": "Данные временно недоступны. Попробуйте позже.",
    })
# ══════════════════════════════════════════════════════════════════════
# Reports — Backend-Driven PoP Integration (39.2.4)
# ══════════════════════════════════════════════════════════════════════

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """Reports: backend-driven PoP report data (39.2.4).

    KPI cards and recent events table use production /api/reports/pop.
    No demo/fake numbers. No test-kso as primary source.
    """
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/reports")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    at = tokens.get("access_token", "")
    client = BackendClient()
    try:
        # Pop summary (KPI cards)
        pop_summary = {"total_events": 0, "unique_devices": 0,
                       "unique_campaigns": 0, "unique_creatives": 0,
                       "accepted": 0, "rejected": 0, "duplicate": 0,
                       "unknown_status": 0, "last_event_at": None}
        pop_summary_ok = False
        sr = await client.get_pop_summary(at, filters={})
        if sr["ok"]:
            pop_summary = sr["data"]
            pop_summary_ok = True

        # Pop recent events (table)
        pop_events = []
        pop_events_ok = False
        er = await client.get_pop_report(at, filters={"limit": 25})
        if er["ok"]:
            pop_events = er["data"]
            pop_events_ok = True

        # Campaign & creative counts for supplemental KPI
        campaigns_count = 0
        cr = await client.list_campaigns_prod(at)
        if cr["ok"]:
            campaigns_count = len(cr.get("data", []))

        creatives_count = 0
        cr2 = await client.list_creatives(at)
        if cr2["ok"]:
            creatives_count = len(cr2.get("data", []))

        kso_count = 0
        dr = await client.list_kso_devices(at)
        if dr["ok"]:
            kso_count = len(dr.get("data", []))

        # Manifest count
        manifests_count = 0
        mr = await client.list_manifests(at)
        if mr["ok"]:
            manifests_count = len(mr.get("data", []))

        backend_available = pop_summary_ok or pop_events_ok

        return templates.TemplateResponse(request, "pages/reports.html", {
            "request": request,
            "title": "Отчёты",
            "active": "reports",
            "current_user": current_user,
            "demo": False,
            "pop_summary": pop_summary,
            "pop_summary_ok": pop_summary_ok,
            "pop_events": pop_events,
            "pop_events_ok": pop_events_ok,
            "campaigns_count": campaigns_count,
            "creatives_count": creatives_count,
            "kso_count": kso_count,
            "manifests_count": manifests_count,
            "backend_available": backend_available,
            "backend_unavailable": not backend_available,
            "backend_message": "Данные временно недоступны. Попробуйте позже.",
            "filters": {},
        })
    except Exception:
        return _reports_fallback(request, current_user,
                                 reason="Backend communication error")
    finally:
        await client.close()


def _reports_fallback(request: Request, current_user, *, reason: str = ""
                      ) -> HTMLResponse:
    """Safe fallback when backend is unreachable for reports."""
    return templates.TemplateResponse(request, "pages/reports.html", {
        "request": request,
        "title": "Отчёты",
        "active": "reports",
        "current_user": current_user,
        "demo": False,
        "pop_summary": {},
        "pop_summary_ok": False,
        "pop_events": [],
        "pop_events_ok": False,
        "campaigns_count": 0,
        "creatives_count": 0,
        "kso_count": 0,
        "manifests_count": 0,
        "backend_available": False,
        "backend_unavailable": True,
        "backend_message": reason or "Данные временно недоступны. Попробуйте позже.",
        "filters": {},
    })
app.add_api_route("/deployment", _page("pages/deployment.html", "Развёртывание", "deployment"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/admin", _page("pages/admin.html", "Администрирование", "admin",
                                {"users": get_users_data()}),
                  methods=["GET"], response_class=HTMLResponse)


# ══════════════════════════════════════════════════════════════════════
# Test KSO Readiness — Backend API Integration (Step 38.4)
# ══════════════════════════════════════════════════════════════════════

@app.get("/readiness", response_class=HTMLResponse)
async def readiness_page(request: Request):
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/readiness")
    if guard is not None:
        return guard

    backend = BackendClient()
    device_code = request.query_params.get("device_code", "test-dev-readiness")

    readiness_data = {
        "overall_ready": False,
        "backend_healthy": False,
        "phase_d_requires_approval": True,
        "phase_d_blocked": True,
        "phase_d_block_reason": "Explicit manual approval required",
        "device_code": device_code,
    }

    result = await backend.get_test_kso_readiness(device_code)
    if result.get("ok"):
        readiness_data = result.get("data", readiness_data)

    return templates.TemplateResponse(request, "pages/readiness.html", {
        "request": request,
        "title": "Test KSO Readiness",
        "active": "readiness",
        "demo": False,
        "current_user": current_user,
        "readiness": readiness_data,
        "backend_unavailable": not result.get("ok", False),
    })


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
# Campaigns — Production Backend API Integration (39.2.2)
# ══════════════════════════════════════════════════════════════════════

@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request):
    """Campaigns page: list + create + edit + archive + creative binding (39.2.2).

    Uses test-kso for safe list/create, production code-based for update/archive/binding.
    """
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/campaigns")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    backend = BackendClient()

    if not access_token:
        return _campaigns_fallback(request, current_user)

    result = await backend.list_campaigns(access_token)
    if not result["ok"]:
        return _campaigns_fallback(request, current_user)

    campaigns = result.get("data", [])
    safe_rows = []
    for c in campaigns:
        code = c.get("campaign_code", "")
        creative_codes = c.get("creative_codes", [])
        safe_rows.append({
            "campaign_code": code,
            "name": c.get("name", ""),
            "status": c.get("status", "—"),
            "description": c.get("description") or "—",
            "creative_codes": ", ".join(creative_codes),
            "creative_count": len(creative_codes),
            "created_at": _fmt_dt(c.get("created_at")),
            "updated_at": _fmt_dt(c.get("updated_at")),
        })

    # Consume flash messages
    flash_type = ""
    flash_msg = ""
    raw = request.session.pop("camp_flash", "")
    if raw == "ok:created":
        flash_type = "success"
        flash_msg = "Кампания создана."
    elif raw == "ok:updated":
        flash_type = "success"
        flash_msg = "Кампания обновлена."
    elif raw == "ok:archived":
        flash_type = "success"
        flash_msg = "Кампания архивирована."
    elif raw == "ok:bound":
        flash_type = "success"
        flash_msg = "Креатив привязан."
    elif raw == "ok:unbound":
        flash_type = "success"
        flash_msg = "Креатив отвязан."
    elif raw == "error":
        flash_type = "error"
        flash_msg = request.session.pop("camp_flash_msg", "Ошибка.")[:200]

    return templates.TemplateResponse(request, "pages/campaigns.html", {
        "request": request,
        "title": "Кампании",
        "active": "campaigns",
        "demo": False,
        "current_user": current_user,
        "campaigns": safe_rows,
        "flash_type": flash_type,
        "flash_msg": flash_msg,
    })


@app.post("/campaigns/create", response_class=HTMLResponse)
async def campaigns_create(
    request: Request,
    campaign_code: str = Form(..., min_length=3, max_length=64),
    name: str = Form(..., min_length=1, max_length=255),
    description: str = Form("", max_length=500),
    creative_code: str = Form("", max_length=64),
):
    """Create campaign via POST /campaigns/create → production API."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/campaigns")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/campaigns", status_code=303)

    payload = {
        "campaign_code": campaign_code.strip(),
        "name": name.strip(),
        "description": description.strip() if description.strip() else None,
        "creative_codes": [creative_code.strip()] if creative_code.strip() else [],
    }

    backend = BackendClient()
    result = await backend.create_campaign(access_token, payload)

    if result["ok"]:
        request.session["camp_flash"] = "ok:created"
    else:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = result.get("error", "Ошибка создания")[:200]

    return RedirectResponse(url="/campaigns", status_code=303)


@app.post("/campaigns/{campaign_code}/edit", response_class=HTMLResponse)
async def campaigns_edit(
    request: Request,
    campaign_code: str,
    name: str = Form(..., min_length=1, max_length=255),
    description: str = Form("", max_length=500),
):
    """Update campaign via PATCH /campaigns/by-code/{code} (production)."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/campaigns")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/campaigns", status_code=303)

    payload = {
        "name": name.strip(),
        "comment": description.strip() if description.strip() else None,
    }

    backend = BackendClient()
    result = await backend.update_campaign_by_code(access_token, campaign_code, payload)

    if result["ok"]:
        request.session["camp_flash"] = "ok:updated"
    else:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = result.get("error", "Ошибка обновления")[:200]

    return RedirectResponse(url="/campaigns", status_code=303)


@app.post("/campaigns/{campaign_code}/archive", response_class=HTMLResponse)
async def campaigns_archive(
    request: Request,
    campaign_code: str,
):
    """Archive campaign via POST /campaigns/by-code/{code}/archive (production)."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/campaigns")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/campaigns", status_code=303)

    backend = BackendClient()
    result = await backend.archive_campaign_by_code(access_token, campaign_code)

    if result["ok"]:
        request.session["camp_flash"] = "ok:archived"
    else:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = result.get("error", "Ошибка архивирования")[:200]

    return RedirectResponse(url="/campaigns", status_code=303)


@app.post("/campaigns/{campaign_code}/bind-creative", response_class=HTMLResponse)
async def campaigns_bind_creative(
    request: Request,
    campaign_code: str,
    creative_code: str = Form(..., min_length=1, max_length=64),
):
    """Bind creative to campaign via POST /campaigns/by-code/{code}/creatives."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/campaigns")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/campaigns", status_code=303)

    backend = BackendClient()
    result = await backend.bind_campaign_creative(
        access_token, campaign_code, creative_code.strip(),
    )

    if result["ok"]:
        request.session["camp_flash"] = "ok:bound"
    else:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = result.get("error", "Ошибка привязки")[:200]

    return RedirectResponse(url="/campaigns", status_code=303)


@app.post(
    "/campaigns/{campaign_code}/unbind-creative/{creative_code}",
    response_class=HTMLResponse,
)
async def campaigns_unbind_creative(
    request: Request,
    campaign_code: str,
    creative_code: str,
):
    """Unbind creative via DELETE /campaigns/by-code/{code}/creatives/{cc}."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/campaigns")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/campaigns", status_code=303)

    backend = BackendClient()
    result = await backend.unbind_campaign_creative(
        access_token, campaign_code, creative_code,
    )

    if result["ok"]:
        request.session["camp_flash"] = "ok:unbound"
    else:
        request.session["camp_flash"] = "error"
        request.session["camp_flash_msg"] = result.get("error", "Ошибка отвязки")[:200]

    return RedirectResponse(url="/campaigns", status_code=303)


def _campaigns_fallback(request: Request, current_user) -> HTMLResponse:
    return templates.TemplateResponse(request, "pages/campaigns.html", {
        "request": request,
        "title": "Кампании",
        "active": "campaigns",
        "demo": False,
        "current_user": current_user,
        "campaigns": [],
        "backend_unavailable": True,
        "backend_message": "Данные временно недоступны. Попробуйте позже.",
    })


# ══════════════════════════════════════════════════════════════════════
# Schedule — Production Backend API Integration (39.2.1)
# ══════════════════════════════════════════════════════════════════════

@app.get("/schedule", response_class=HTMLResponse)
async def schedule_page(request: Request):
    """Schedule page: production schedule CRUD + slot management (39.2.1).

    Fetches schedules from backend production API, shows slots inline.
    Backend-driven — no demo/stub data.
    """
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/schedule")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    backend = BackendClient()

    if not access_token:
        return _schedule_fallback(request, current_user)

    result = await backend.list_schedules(access_token)
    if not result["ok"]:
        return _schedule_fallback(request, current_user)

    schedules = result.get("data", [])
    safe_schedules = []
    for s in schedules:
        safe_schedules.append({
            "schedule_code": s.get("schedule_code", ""),
            "name": s.get("name", ""),
            "status": s.get("status", "—"),
            "campaign_code": s.get("campaign_code") or "—",
            "valid_from": _fmt_dt(s.get("valid_from")),
            "valid_to": _fmt_dt(s.get("valid_to")),
            "timezone": s.get("timezone", "Europe/Moscow"),
            "slot_count": s.get("slot_count", 0),
            "created_at": _fmt_dt(s.get("created_at")),
            "updated_at": _fmt_dt(s.get("updated_at")),
        })

    # Fetch slots for each schedule
    schedule_slots = {}
    for s in schedules:
        code = s.get("schedule_code", "")
        if code:
            slots_r = await backend.list_schedule_slots(access_token, code)
            if slots_r["ok"]:
                safe_slots = []
                for sl in slots_r.get("data", []):
                    safe_slots.append({
                        "slot_code": sl.get("slot_code", ""),
                        "schedule_code": sl.get("schedule_code", ""),
                        "placement_code": sl.get("placement_code") or "—",
                        "day_of_week": sl.get("day_of_week", 0),
                        "start_time": str(sl.get("start_time", "")),
                        "end_time": str(sl.get("end_time", "")),
                        "slot_order": sl.get("slot_order", 0),
                        "is_active": sl.get("is_active", True),
                    })
                schedule_slots[code] = safe_slots

    # Consume flash messages
    flash_type = ""
    flash_msg = ""
    raw = request.session.pop("sched_flash", "")
    if raw == "ok:created":
        flash_type = "success"
        flash_msg = "Расписание создано."
    elif raw == "ok:archived":
        flash_type = "success"
        flash_msg = "Расписание архивировано."
    elif raw == "ok:slot_created":
        flash_type = "success"
        flash_msg = "Слот добавлен."
    elif raw == "ok:slot_disabled":
        flash_type = "success"
        flash_msg = "Слот отключён."
    elif raw == "error":
        flash_type = "error"
        flash_msg = request.session.pop("sched_flash_msg", "Ошибка.")[:200]

    return templates.TemplateResponse(request, "pages/schedule.html", {
        "request": request,
        "title": "Расписание",
        "active": "schedule",
        "demo": False,
        "current_user": current_user,
        "schedules": safe_schedules,
        "schedule_slots": schedule_slots,
        "flash_type": flash_type,
        "flash_msg": flash_msg,
    })


@app.post("/schedule/create", response_class=HTMLResponse)
async def schedule_create(
    request: Request,
    schedule_code: str = Form(..., min_length=3, max_length=64),
    name: str = Form(..., min_length=1, max_length=255),
    campaign_code: str = Form("", max_length=64),
    valid_from: str = Form(..., min_length=10, max_length=10),
    valid_to: str = Form(..., min_length=10, max_length=10),
    timezone: str = Form("Europe/Moscow", max_length=50),
):
    """Create schedule via POST /schedule/create → backend /api/schedules."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/schedule")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["sched_flash"] = "error"
        request.session["sched_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/schedule", status_code=303)

    payload = {
        "schedule_code": schedule_code.strip(),
        "name": name.strip(),
        "valid_from": valid_from.strip(),
        "valid_to": valid_to.strip(),
        "timezone": timezone.strip() or "Europe/Moscow",
    }
    cc = campaign_code.strip()
    if cc:
        payload["campaign_code"] = cc

    backend = BackendClient()
    result = await backend.create_schedule(access_token, payload)

    if result["ok"]:
        request.session["sched_flash"] = "ok:created"
    else:
        request.session["sched_flash"] = "error"
        request.session["sched_flash_msg"] = result.get("error", "Ошибка создания")[:200]

    return RedirectResponse(url="/schedule", status_code=303)


@app.post("/schedule/{schedule_code}/create-slot", response_class=HTMLResponse)
async def schedule_slot_create(
    request: Request,
    schedule_code: str,
    slot_code: str = Form(..., min_length=3, max_length=64),
    placement_code: str = Form("", max_length=64),
    day_of_week: int = Form(...),
    start_time: str = Form(..., min_length=5, max_length=8),
    end_time: str = Form(..., min_length=5, max_length=8),
    slot_order: int = Form(0),
):
    """Create schedule slot via POST → backend /api/schedules/{code}/items."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/schedule")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["sched_flash"] = "error"
        request.session["sched_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/schedule", status_code=303)

    payload = {
        "slot_code": slot_code.strip(),
        "day_of_week": day_of_week,
        "start_time": start_time.strip(),
        "end_time": end_time.strip(),
        "slot_order": slot_order,
    }
    pc = placement_code.strip()
    if pc:
        payload["placement_code"] = pc

    backend = BackendClient()
    result = await backend.create_schedule_slot(
        access_token, schedule_code, payload,
    )

    if result["ok"]:
        request.session["sched_flash"] = "ok:slot_created"
    else:
        request.session["sched_flash"] = "error"
        request.session["sched_flash_msg"] = result.get("error", "Ошибка создания слота")[:200]

    return RedirectResponse(url="/schedule", status_code=303)


@app.post("/schedule/{schedule_code}/archive", response_class=HTMLResponse)
async def schedule_archive(
    request: Request,
    schedule_code: str,
):
    """Archive schedule via POST → backend /api/schedules/{code}/archive."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/schedule")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["sched_flash"] = "error"
        request.session["sched_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/schedule", status_code=303)

    backend = BackendClient()
    result = await backend.archive_schedule(access_token, schedule_code)

    if result["ok"]:
        request.session["sched_flash"] = "ok:archived"
    else:
        request.session["sched_flash"] = "error"
        request.session["sched_flash_msg"] = result.get("error", "Ошибка архивирования")[:200]

    return RedirectResponse(url="/schedule", status_code=303)


@app.post(
    "/schedule/{schedule_code}/items/{slot_code}/disable",
    response_class=HTMLResponse,
)
async def schedule_slot_disable(
    request: Request,
    schedule_code: str,
    slot_code: str,
):
    """Disable slot via POST → backend DELETE /api/schedules/{code}/items/{slot}."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/schedule")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["sched_flash"] = "error"
        request.session["sched_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/schedule", status_code=303)

    backend = BackendClient()
    result = await backend.disable_schedule_slot(access_token, schedule_code, slot_code)

    if result["ok"]:
        request.session["sched_flash"] = "ok:slot_disabled"
    else:
        request.session["sched_flash"] = "error"
        request.session["sched_flash_msg"] = result.get("error", "Ошибка отключения слота")[:200]

    return RedirectResponse(url="/schedule", status_code=303)


def _schedule_fallback(request: Request, current_user) -> HTMLResponse:
    return templates.TemplateResponse(request, "pages/schedule.html", {
        "request": request,
        "title": "Расписание",
        "active": "schedule",
        "demo": False,
        "current_user": current_user,
        "schedules": [],
        "schedule_slots": {},
        "backend_unavailable": True,
        "backend_message": "Данные временно недоступны. Попробуйте позже.",
    })


# ══════════════════════════════════════════════════════════════════════
# Publications — Backend API Integration (Steps 37.7, 37.8)
# ══════════════════════════════════════════════════════════════════════

@app.get("/publications", response_class=HTMLResponse)
async def publications_page(request: Request):
    """Publications page: list manifests from backend + generate/publish forms."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/publications")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    manifests = []
    backend_unavailable = False
    backend_message = ""

    if access_token:
        backend = BackendClient()
        result = await backend.list_manifests(access_token)
        if result["ok"]:
            manifests = result.get("data", [])
        else:
            backend_unavailable = True
            backend_message = result.get("error", "Данные временно недоступны.")[:200]

    # Flash messages
    flash = request.session.pop("pub_flash", None)
    flash_msg = request.session.pop("pub_flash_msg", "")

    return templates.TemplateResponse(request, "pages/publications.html", {
        "request": request,
        "title": "Публикации",
        "active": "publications",
        "demo": False,
        "current_user": current_user,
        "manifests": manifests,
        "backend_unavailable": backend_unavailable,
        "backend_message": backend_message,
        "pub_flash": flash,
        "pub_flash_msg": flash_msg,
    })


@app.post("/publications/generate", response_class=HTMLResponse)
async def publications_generate(
    request: Request,
    placement_code: str = Form(..., min_length=1, max_length=64),
    manifest_code: str = Form(..., min_length=1, max_length=64),
):
    """Handle manifest generation — POST /publications/generate → backend."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/publications")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    if not access_token:
        request.session["pub_flash"] = "error"
        request.session["pub_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/publications", status_code=303)

    backend = BackendClient()
    result = await backend.generate_manifest(access_token, {
        "placement_code": placement_code.strip(),
        "manifest_code": manifest_code.strip(),
    })

    if result["ok"]:
        request.session["pub_flash"] = "ok:generated"
    else:
        request.session["pub_flash"] = "error"
        request.session["pub_flash_msg"] = result.get("error", "Ошибка генерации")[:200]

    return RedirectResponse(url="/publications", status_code=303)


@app.post("/publications/publish", response_class=HTMLResponse)
async def publications_publish(
    request: Request,
    manifest_code: str = Form(..., min_length=1, max_length=64),
):
    """Handle manifest publish — POST /publications/publish → backend."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/publications")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")

    if not access_token:
        request.session["pub_flash"] = "error"
        request.session["pub_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/publications", status_code=303)

    backend = BackendClient()
    result = await backend.publish_manifest(access_token, manifest_code.strip())

    if result["ok"]:
        request.session["pub_flash"] = "ok:published"
    else:
        request.session["pub_flash"] = "error"
        request.session["pub_flash_msg"] = result.get("error", "Ошибка публикации")[:200]

    return RedirectResponse(url="/publications", status_code=303)


# ══════════════════════════════════════════════════════════════════════
# Approvals — Backend API Integration (Step 37.6)
# ══════════════════════════════════════════════════════════════════════

@app.get("/approvals", response_class=HTMLResponse)
async def approvals_page(request: Request):
    """Approvals page: list from backend + request/decide forms (Step 37.6)."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/approvals")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    backend = BackendClient()

    if not access_token:
        return _approvals_fallback(request, current_user)

    result = await backend.list_approvals(access_token)
    if not result["ok"]:
        return _approvals_fallback(request, current_user)

    approvals = result.get("data", [])
    safe_rows = []
    for a in approvals:
        safe_rows.append({
            "approval_code": a.get("approval_code", ""),
            "object_type": a.get("object_type", ""),
            "object_code": a.get("object_code", ""),
            "status": a.get("status", "—"),
            "decision": a.get("decision") or "—",
            "comment": a.get("comment") or "—",
            "requested_at": _fmt_dt(a.get("requested_at")),
            "decided_at": _fmt_dt(a.get("decided_at")),
        })

    flash_type = ""
    flash_msg = ""
    raw = request.session.pop("approval_flash", "")
    if raw == "ok:requested":
        flash_type = "success"
        flash_msg = "Запрос на согласование отправлен."
    elif raw == "ok:decided":
        flash_type = "success"
        flash_msg = "Решение по согласованию принято."
    elif raw == "error":
        flash_type = "error"
        flash_msg = request.session.pop("approval_flash_msg", "Ошибка.")

    return templates.TemplateResponse(request, "pages/approvals.html", {
        "request": request,
        "title": "Согласования",
        "active": "approvals",
        "demo": False,
        "current_user": current_user,
        "approvals": safe_rows,
        "flash_type": flash_type,
        "flash_msg": flash_msg,
    })


@app.post("/approvals/request", response_class=HTMLResponse)
async def approvals_request(
    request: Request,
    object_type: str = Form(..., min_length=1, max_length=20),
    object_code: str = Form(..., min_length=1, max_length=64),
    comment: str = Form("", max_length=500),
):
    """Request approval — POST /approvals/request → backend."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/approvals")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["approval_flash"] = "error"
        request.session["approval_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/approvals", status_code=303)

    payload = {
        "object_type": object_type.strip(),
        "object_code": object_code.strip(),
        "comment": comment.strip() if comment.strip() else None,
    }

    backend = BackendClient()
    result = await backend.request_approval(access_token, payload)

    if result["ok"]:
        request.session["approval_flash"] = "ok:requested"
    else:
        request.session["approval_flash"] = "error"
        request.session["approval_flash_msg"] = result.get("error", "Ошибка")[:200]

    return RedirectResponse(url="/approvals", status_code=303)


@app.post("/approvals/decide", response_class=HTMLResponse)
async def approvals_decide(
    request: Request,
    approval_code: str = Form(..., min_length=1, max_length=64),
    decision: str = Form(..., min_length=1, max_length=20),
    comment: str = Form("", max_length=500),
):
    """Decide approval — POST /approvals/decide → backend."""
    current_user = get_current_portal_user(request)
    guard = await require_auth_for_page(request, "/approvals")
    if guard is not None:
        return guard

    tokens = get_portal_tokens(request)
    access_token = tokens.get("access_token", "")
    if not access_token:
        request.session["approval_flash"] = "error"
        request.session["approval_flash_msg"] = "Нет доступа."
        return RedirectResponse(url="/approvals", status_code=303)

    payload = {
        "decision": decision.strip(),
        "comment": comment.strip() if comment.strip() else None,
    }

    backend = BackendClient()
    result = await backend.decide_approval(access_token, approval_code.strip(), payload)

    if result["ok"]:
        request.session["approval_flash"] = "ok:decided"
    else:
        request.session["approval_flash"] = "error"
        request.session["approval_flash_msg"] = result.get("error", "Ошибка")[:200]

    return RedirectResponse(url="/approvals", status_code=303)


def _approvals_fallback(request: Request, current_user) -> HTMLResponse:
    return templates.TemplateResponse(request, "pages/approvals.html", {
        "request": request,
        "title": "Согласования",
        "active": "approvals",
        "demo": False,
        "current_user": current_user,
        "approvals": [],
        "backend_unavailable": True,
        "backend_message": "Данные временно недоступны. Попробуйте позже.",
    })


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
