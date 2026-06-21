"""Retail Media Platform — Web Portal UI v1 (KSO-only).

FastAPI + Jinja2 server-rendered portal.
No external CDN. No real API integration on this step.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Retail Media Platform — Portal", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _page(template: str, title: str, active: str):
    """Return a route handler for a static page."""
    async def handler(request: Request):
        return templates.TemplateResponse(
            request, template,
            {"request": request, "title": title, "active": active},
        )
    return handler


# ══════════════════════════════════════════════════════════════════════
# Pages
# ══════════════════════════════════════════════════════════════════════

app.add_api_route("/", _page("pages/dashboard.html", "Dashboard", "dashboard"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/dashboard", _page("pages/dashboard.html", "Dashboard", "dashboard"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/campaigns", _page("pages/campaigns.html", "Кампании", "campaigns"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/creatives", _page("pages/creatives.html", "Креативы", "creatives"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/schedule", _page("pages/schedule.html", "Расписание", "schedule"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/publications", _page("pages/publications.html", "Публикации", "publications"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/stores", _page("pages/stores.html", "Магазины", "stores"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/devices", _page("pages/devices.html", "КСО Устройства", "devices"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/proof-of-play", _page("pages/proof-of-play.html", "Proof of Play", "pop"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/reports", _page("pages/reports.html", "Отчёты", "reports"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/deployment", _page("pages/deployment.html", "Развёртывание", "deployment"),
                  methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/admin", _page("pages/admin.html", "Администрирование", "admin"),
                  methods=["GET"], response_class=HTMLResponse)


# ══════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def portal_health():
    return {"status": "ok", "portal": "v1", "stack": "FastAPI + Jinja2"}
