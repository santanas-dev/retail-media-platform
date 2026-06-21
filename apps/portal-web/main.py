"""Retail Media Platform — Web Portal UI v1 (KSO-only).

FastAPI + Jinja2 server-rendered portal.
No external CDN. Demo data for visual preview.
No real API integration on this step.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

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
)

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Retail Media Platform — Portal", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _page(template: str, title: str, active: str, extra: dict | None = None):
    """Return a route handler for a page with optional demo data."""
    ctx = {"request": None, "title": title, "active": active, "demo": True}
    if extra:
        ctx.update(extra)
    async def handler(request: Request):
        ctx["request"] = request
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
app.add_api_route("/admin", _page("pages/admin.html", "Администрирование", "admin"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/approvals", _page("pages/approvals.html", "Согласования", "approvals",
                                      {"approvals": get_approvals_data()}),
                  methods=["GET"], response_class=HTMLResponse)


# ══════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def portal_health():
    return {"status": "ok", "portal": "v1", "stack": "FastAPI + Jinja2"}
