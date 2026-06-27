"""Reports export portal tests (42.3).

Tests: /reports page shows export buttons, NO-GO summary, planned disclaimer,
no JS/CDN, CSV links use GET server-side only.
"""

import os
import pytest
import re

TEMPLATE = os.path.join(
    os.path.dirname(__file__),
    "../../apps/portal-web/templates/pages/reports.html",
)

def _load() -> str:
    with open(TEMPLATE) as f:
        return f.read()


# ══════════════════════════════════════════════════════════════════════
# /reports page content
# ══════════════════════════════════════════════════════════════════════

class TestReportsPage42_3:

    def test_reports_shows_planned_disclaimer(self):
        html = _load()
        assert "Это плановая отчётность" in html

    def test_reports_shows_pilot_nogo(self):
        html = _load()
        assert "NO-GO" in html

    def test_reports_shows_campaign_status_export(self):
        html = _load()
        assert "Кампании по статусам" in html
        assert "campaigns_export.csv" in html

    def test_reports_shows_publication_batch_export(self):
        html = _load()
        assert "Publication Batches" in html
        assert "publication_batches_export.csv" in html

    def test_reports_shows_manifest_status(self):
        html = _load()
        assert "Manifest publish status" in html

    def test_reports_shows_airtime_export_links(self):
        html = _load()
        assert "airtime_occupancy_export.csv" in html
        assert "conflicts_export.csv" in html


# ══════════════════════════════════════════════════════════════════════
# No JS / no CDN / no localStorage
# ══════════════════════════════════════════════════════════════════════

class TestNoJS42_3:

    def test_reports_no_script_tags(self):
        html = _load()
        assert "<script" not in html

    def test_reports_no_onclick(self):
        html = _load()
        assert "onclick" not in html

    def test_reports_no_onsubmit(self):
        html = _load()
        assert "onsubmit" not in html

    def test_reports_no_confirm(self):
        html = _load()
        assert "confirm(" not in html

    def test_reports_no_cdn(self):
        html = _load()
        html_lower = html.lower()
        assert "cdn." not in html_lower
        assert "unpkg" not in html_lower

    def test_reports_no_localstorage(self):
        html = _load()
        assert "localStorage" not in html.lower()

    def test_reports_no_backend_url(self):
        html = _load()
        assert "192.168" not in html
        assert "minio" not in html.lower()


# ══════════════════════════════════════════════════════════════════════
# Export routes are GET links (no form POST)
# ══════════════════════════════════════════════════════════════════════

class TestExportRoutes:

    def test_export_links_use_get(self):
        html = _load()
        export_hrefs = re.findall(r'href="(/reports/export/[^"]+)"', html)
        assert len(export_hrefs) >= 3, f"Found {len(export_hrefs)} export links"

    def test_no_form_action_export(self):
        html = _load()
        assert not re.search(r'action="[^"]*export[^"]*"', html)
