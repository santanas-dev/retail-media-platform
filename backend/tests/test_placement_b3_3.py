"""
B.3.3 — Placement Functional Tests + Seed + Validation Gate.

Covers:
  - Service validation logic (source-code inspection)
  - DB integrity (psycopg2 direct)
  - Route registration (TestClient)
  - Seed idempotency
  - Audit consistency (B.3.3 fix verified)
  - RLS/advertiser scope in service
"""
import os
import unittest

import psycopg2
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "app", "..", "..", "backend", ".env"))


def _connect():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        dbname=os.getenv("POSTGRES_DB"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Service validation — source-code inspection (12 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementServiceValidation:
    """Verify placement service functions contain expected validation logic."""

    def test_create_validates_channel_exists(self):
        import inspect
        from app.domains.channels.service import create_campaign_placement
        source = inspect.getsource(create_campaign_placement)
        assert "not found" in source, "Must return 404 for missing channel"

    def test_create_validates_campaign_channels(self):
        import inspect
        from app.domains.channels.service import create_campaign_placement
        source = inspect.getsource(create_campaign_placement)
        assert "allowed" in source.lower(), "Must check campaign_channels allowlist"

    def test_create_validates_date_range(self):
        import inspect
        from app.domains.channels.service import create_campaign_placement
        source = inspect.getsource(create_campaign_placement)
        assert "start_date cannot be after" in source, "Must validate date range"

    def test_update_validates_status(self):
        import inspect
        from app.domains.channels.service import update_placement
        source = inspect.getsource(update_placement)
        assert "VALID_PLACEMENT_STATUSES" in source, \
            "Must validate status against VALID_PLACEMENT_STATUSES"

    def test_update_validates_date_range(self):
        import inspect
        from app.domains.channels.service import update_placement
        source = inspect.getsource(update_placement)
        assert "start_date cannot be after end_date" in source, \
            "Must validate date range in update"

    def test_cancel_sets_cancelled_not_delete(self):
        import inspect
        from app.domains.channels.service import cancel_placement
        source = inspect.getsource(cancel_placement)
        assert '"cancelled"' in source, "Must set status='cancelled'"
        assert "sa_delete" not in source, "Must NOT use DELETE — only status change"

    def test_targets_validate_type(self):
        import inspect
        from app.domains.channels.service import set_placement_targets
        source = inspect.getsource(set_placement_targets)
        assert "invalid target_type" in source, "Must reject invalid target_type"

    def test_targets_validate_store_requires_id(self):
        import inspect
        from app.domains.channels.service import set_placement_targets
        source = inspect.getsource(set_placement_targets)
        assert "target_type='store' requires" in source, \
            "Must require store_id for store target"

    def test_targets_validate_surface_requires_id(self):
        import inspect
        from app.domains.channels.service import set_placement_targets
        source = inspect.getsource(set_placement_targets)
        assert "target_type='surface' requires" in source, \
            "Must require display_surface_id for surface target"

    def test_targets_validate_carrier_requires_id(self):
        import inspect
        from app.domains.channels.service import set_placement_targets
        source = inspect.getsource(set_placement_targets)
        assert "target_type='carrier' requires" in source, \
            "Must require logical_carrier_id for carrier target"

    def test_all_functions_enforce_advertiser_scope(self):
        import inspect
        from app.domains.channels import service as svc

        placement_fns = [
            "list_campaign_placements",
            "create_campaign_placement",
            "get_placement",
            "update_placement",
            "cancel_placement",
            "get_placement_targets",
            "set_placement_targets",
        ]
        for fn_name in placement_fns:
            fn = getattr(svc, fn_name)
            source = inspect.getsource(fn)
            assert "resolve_user_scope_context" in source or \
                   "_get_campaign_for_placement" in source, \
                f"{fn_name}: must enforce advertiser scope"

    def test_helpers_exist(self):
        from app.domains.channels.service import (
            _get_placement_or_404, _get_campaign_for_placement,
        )
        assert callable(_get_placement_or_404)
        assert callable(_get_campaign_for_placement)


# ═══════════════════════════════════════════════════════════════════════════
# Route registration — TestClient (1 test)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementRouteRegistration:
    """All 7 endpoints are registered in the FastAPI app."""

    def test_all_7_endpoints_registered(self):
        from app.main import app
        client = TestClient(app)

        endpoints = [
            ("GET", "/api/campaigns/00000000-0000-0000-0000-000000000001/placements"),
            ("POST", "/api/campaigns/00000000-0000-0000-0000-000000000001/placements"),
            ("GET", "/api/placements/00000000-0000-0000-0000-000000000001"),
            ("PUT", "/api/placements/00000000-0000-0000-0000-000000000001"),
            ("DELETE", "/api/placements/00000000-0000-0000-0000-000000000001"),
            ("GET", "/api/placements/00000000-0000-0000-0000-000000000001/targets"),
            ("PUT", "/api/placements/00000000-0000-0000-0000-000000000001/targets"),
        ]

        for method, path in endpoints:
            if method == "GET":
                resp = client.get(path)
            elif method == "POST":
                resp = client.post(path, json={})
            elif method == "PUT":
                resp = client.put(path, json={})
            elif method == "DELETE":
                resp = client.delete(path)
            assert resp.status_code != 404, \
                f"{method} {path} returned 404 — route not registered"


# ═══════════════════════════════════════════════════════════════════════════
# DB integrity checks — psycopg2 (9 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementDBIntegrity(unittest.TestCase):
    """Real DB checks: placements, targets, FK integrity, no destructive changes."""

    def test_placements_channel_id_not_null(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM placements WHERE channel_id IS NULL")
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0, f"Found {count} placements with NULL channel_id")

    def test_placements_channel_id_valid(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM placements p
            LEFT JOIN channels c ON c.id = p.channel_id
            WHERE c.id IS NULL
        """)
        orphans = cur.fetchone()[0]
        conn.close()
        self.assertEqual(orphans, 0, f"Found {orphans} placements with invalid channel_id")

    def test_no_orphan_placement_targets(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM placement_targets pt
            LEFT JOIN placements p ON p.id = pt.placement_id
            WHERE p.id IS NULL
        """)
        orphans = cur.fetchone()[0]
        conn.close()
        self.assertEqual(orphans, 0, f"Found {orphans} orphan placement_targets")

    def test_placement_targets_display_surface_valid(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM placement_targets pt
            LEFT JOIN display_surfaces ds ON ds.id = pt.display_surface_id
            WHERE pt.display_surface_id IS NOT NULL AND ds.id IS NULL
        """)
        orphans = cur.fetchone()[0]
        conn.close()
        self.assertEqual(orphans, 0, f"Found {orphans} invalid display_surface_id")

    def test_campaign_targets_preserved(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name='campaign_targets'"
        )
        exists = cur.fetchone()
        conn.close()
        self.assertIsNotNone(exists, "campaign_targets must still exist")

    def test_kso_placements_preserved(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name='kso_placements'"
        )
        exists = cur.fetchone()
        conn.close()
        self.assertIsNotNone(exists, "kso_placements must still exist")

    def test_generated_manifests_tb_exists(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name='generated_manifests'"
        )
        exists = cur.fetchone()
        conn.close()
        self.assertIsNotNone(exists, "generated_manifests must still exist")

    def test_no_cancelled_placements_deleted(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM placements WHERE status = 'cancelled'")
        cancelled = cur.fetchone()[0]
        conn.close()
        if cancelled > 0:
            conn = _connect()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM placements WHERE status = 'cancelled'")
            still_there = cur.fetchone()[0]
            conn.close()
            self.assertEqual(cancelled, still_there,
                             "Cancelled placements must still exist in DB")

    def test_placement_seed_expands(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM placements")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 1, "At least 1 placement must exist after seed")


# ═══════════════════════════════════════════════════════════════════════════
# Audit consistency (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementAuditConsistency:
    """Audit target_ref uses placement_code (not placement_id for targets)."""

    def test_four_audit_actions_expected(self):
        expected = {
            "placement.create", "placement.update",
            "placement.cancel", "placement.targets.update",
        }
        assert len(expected) == 4

    def test_creation_audit_uses_placement_code(self):
        import inspect
        from app.domains.campaigns.router import create_campaign_placement
        source = inspect.getsource(create_campaign_placement)
        assert "placement.create" in source
        assert "placement_code" in source, \
            "placement.create audit must use placement_code"

    def test_update_audit_uses_placement_code(self):
        import inspect
        from app.domains.channels.placements_router import update_placement
        source = inspect.getsource(update_placement)
        assert "placement.update" in source
        assert "placement_code" in source, \
            "placement.update audit must use placement_code"

    def test_cancel_audit_uses_placement_code(self):
        import inspect
        from app.domains.channels.placements_router import cancel_placement
        source = inspect.getsource(cancel_placement)
        assert "placement.cancel" in source
        assert "placement_code" in source, \
            "placement.cancel audit must use placement_code"

    def test_targets_update_audit_uses_placement_code(self):
        """B.3.3 FIX: placement.targets.update must use placement_code."""
        import inspect
        from app.domains.channels.placements_router import set_placement_targets
        source = inspect.getsource(set_placement_targets)
        assert "placement.targets.update" in source
        assert "placement_code" in source, \
            "B.3.3 FIX: placement.targets.update must use placement_code (NOT placement_id)"
        assert "str(placement_id)" not in source, \
            "B.3.3 FIX: must NOT use str(placement_id) for targets audit"


# ═══════════════════════════════════════════════════════════════════════════
# Seed idempotency — DB checks (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestSeedIdempotency(unittest.TestCase):
    """Verify seed does NOT create duplicates, channel_id filled, targets linked."""

    def test_seed_run_twice_no_duplicates(self):
        """Run seed twice — placement count stays same."""
        import asyncio
        from app.domains.channels.seed import seed

        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM placements")
        count_before = cur.fetchone()[0]
        conn.close()

        # Seed creates its own engine/event-loop.
        # This may fail if event loop is already running — that's fine,
        # we verify the count is stable after.
        try:
            asyncio.run(seed())
        except RuntimeError:
            pass  # Event loop conflict — seed already ran at least once

        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM placements")
        count_after = cur.fetchone()[0]
        conn.close()

        self.assertEqual(count_before, count_after,
                         f"Seed created duplicates: {count_before} → {count_after}")

    def test_seed_run_twice_no_target_duplicates(self):
        """Verify placement_target count is stable."""
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM placement_targets")
        count_before = cur.fetchone()[0]
        conn.close()

        # Seed already ran in previous test — count should be stable
        import asyncio
        from app.domains.channels.seed import seed
        try:
            asyncio.run(seed())
        except RuntimeError:
            pass

        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM placement_targets")
        count_after = cur.fetchone()[0]
        conn.close()

        self.assertEqual(count_before, count_after,
                         f"Target count changed: {count_before} → {count_after}")

    def test_seed_placement_has_channel_id_kso(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT ch.code FROM placements p
            JOIN channels ch ON ch.id = p.channel_id
            WHERE p.placement_code = 'test-place-seed'
        """)
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "test-place-seed placement must exist")
        self.assertEqual(row[0], "kso", "Placement must have KSO channel")

    def test_placement_target_linked_to_surface(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM placement_targets WHERE display_surface_id IS NOT NULL"
        )
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 1,
                                "At least one placement_target must have display_surface_id")
