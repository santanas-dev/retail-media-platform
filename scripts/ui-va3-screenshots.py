#!/usr/bin/env python3
"""UI.VA.3 — Full Browser Visual Audit: screenshot capture."""
import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:8422"
OUT = Path("/home/cobalt/retail-media-platform/docs/screenshots/ui-va3")
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [
    (1920, 1080),
    (1440, 900),
    (1366, 768),
    (1024, 768),
    (768, 1024),
]

PAGES = [
    # Core / Business
    ("dashboard", "/"),
    ("campaigns", "/campaigns"),
    ("creatives", "/creatives"),
    ("approvals", "/approvals"),
    # Planning
    ("planning", "/planning"),
    ("bookings", "/bookings"),
    ("schedule", "/schedule"),
    # Publication
    ("publications", "/publications"),
    ("packages", "/packages"),
    # Devices
    ("devices", "/devices"),
    ("kso-dashboard", "/devices/kso-dashboard"),
    ("readiness", "/readiness"),
    # Analytics
    ("reports", "/reports/analytics"),
    ("pop", "/reports/proof-of-play"),
    # Admin
    ("ad-inventory", "/admin/ad-inventory"),
    ("stores", "/admin/stores"),
    ("admin", "/admin"),
    ("emergency", "/emergency"),
    ("deployment", "/deployment"),
    # Service
    ("help", "/help"),
    ("compliance", "/compliance"),
]

async def login(page):
    await page.goto(f"{BASE}/login", wait_until="networkidle")
    await page.fill('input[name="username"]', "admin")
    await page.fill('input[name="password"]', "Admin123!")
    await page.click('button[type="submit"]')
    await page.wait_for_url("**/")
    await page.wait_for_timeout(500)

async def capture(page, slug, path, vp_w, vp_h):
    await page.goto(f"{BASE}{path}", wait_until="networkidle")
    await page.wait_for_timeout(500)
    fname = OUT / f"ui-va3-{slug}-{vp_w}x{vp_h}.png"
    await page.screenshot(path=str(fname), full_page=False)
    # Also take full page screenshot for scroll-heavy pages
    fname_full = OUT / f"ui-va3-{slug}-{vp_w}x{vp_h}-full.png"
    await page.screenshot(path=str(fname_full), full_page=True)
    return str(fname), str(fname_full)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        
        for vp_w, vp_h in VIEWPORTS:
            context = await browser.new_context(
                viewport={"width": vp_w, "height": vp_h},
                locale="ru-RU",
            )
            page = await context.new_page()
            
            # Login once per viewport
            await login(page)
            
            for slug, path in PAGES:
                try:
                    f1, f2 = await capture(page, slug, path, vp_w, vp_h)
                    print(f"OK {slug} {vp_w}x{vp_h} → {os.path.basename(f1)}")
                except Exception as e:
                    print(f"ERR {slug} {vp_w}x{vp_h}: {e}")
            
            await context.close()
        
        await browser.close()
    
    print("Done.")

asyncio.run(main())
