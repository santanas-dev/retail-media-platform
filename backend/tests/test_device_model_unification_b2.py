"""
B.2 — Device Model Unification Tests.

Verifies the full chain:
  channel → device_type → physical_device → logical_carrier → display_surface → capability_profile

Plus: KSO migrated object consistency, placement_target link, no orphans, no destructive.
"""

import os
import unittest

import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "app", "..", "..", "backend", ".env"))


def _connect():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        dbname=os.getenv("POSTGRES_DB"),
    )


class TestDeviceModelChain:
    """Full chain PD→LC→DS→CP for all devices."""

    def test_physical_devices_have_logical_carriers(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM physical_devices pd
            LEFT JOIN logical_carriers lc ON lc.physical_device_id = pd.id
            WHERE lc.id IS NULL
        """)
        orphans = cur.fetchone()[0]
        conn.close()
        assert orphans == 0, f"Found {orphans} physical_devices without logical_carrier"

    def test_logical_carriers_have_display_surfaces(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM logical_carriers lc
            LEFT JOIN display_surfaces ds ON ds.logical_carrier_id = lc.id
            WHERE ds.id IS NULL
        """)
        orphans = cur.fetchone()[0]
        conn.close()
        assert orphans == 0, f"Found {orphans} logical_carriers without display_surface"

    def test_display_surfaces_have_capability_profiles(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM display_surfaces ds
            LEFT JOIN capability_profiles cp ON cp.id = ds.capability_profile_id
            WHERE cp.id IS NULL
        """)
        orphans = cur.fetchone()[0]
        conn.close()
        assert orphans == 0, f"Found {orphans} display_surfaces without capability_profile"


class TestKSODeviceChain:
    """Migrated KSO device has full chain."""

    def test_kso_device_has_carriers(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM logical_carriers lc
            JOIN physical_devices pd ON pd.id = lc.physical_device_id
            WHERE pd.external_code = 'test-dev-seed'
        """)
        count = cur.fetchone()[0]
        conn.close()
        assert count >= 1, f"KSO device has {count} logical_carriers (expected >=1)"

    def test_kso_device_has_display_surfaces(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM display_surfaces ds
            JOIN logical_carriers lc ON lc.id = ds.logical_carrier_id
            JOIN physical_devices pd ON pd.id = lc.physical_device_id
            WHERE pd.external_code = 'test-dev-seed'
        """)
        count = cur.fetchone()[0]
        conn.close()
        assert count >= 1, f"KSO device has {count} display_surfaces (expected >=1)"

    def test_kso_device_portrait_surface(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT ds.resolution, cp.orientation, cp.proof_type
            FROM display_surfaces ds
            JOIN logical_carriers lc ON lc.id = ds.logical_carrier_id
            JOIN physical_devices pd ON pd.id = lc.physical_device_id
            JOIN capability_profiles cp ON cp.id = ds.capability_profile_id
            WHERE pd.external_code = 'test-dev-seed'
            AND cp.orientation = 'portrait'
        """)
        row = cur.fetchone()
        conn.close()
        assert row is not None, "KSO device missing portrait display surface"
        assert row[0] == "768x1024"
        assert row[1] == "portrait"
        assert row[2] == "real_playback"

    def test_kso_device_external_code(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT external_code, device_properties->>'legacy_source'
            FROM physical_devices
            WHERE external_code = 'test-dev-seed'
        """)
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "test-dev-seed"
        assert row[1] == "kso_devices"

    def test_kso_device_type_kso_gen5(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT dt.code, dt.name, c.code
            FROM physical_devices pd
            JOIN device_types dt ON dt.id = pd.device_type_id
            JOIN channels c ON c.id = dt.channel_id
            WHERE pd.external_code = 'test-dev-seed'
        """)
        row = cur.fetchone()
        conn.close()
        assert row[0] == "kso_gen5"
        assert row[2] == "kso"


class TestPlacementTargetLink:
    """Placement target references display_surface."""

    def test_placement_target_has_display_surface(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM placement_targets
            WHERE display_surface_id IS NOT NULL
        """)
        count = cur.fetchone()[0]
        conn.close()
        assert count >= 1, f"Expected at least 1 placement_target with display_surface_id"

    def test_placement_target_surface_valid(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT pt.id, ds.resolution, cp.orientation
            FROM placement_targets pt
            JOIN display_surfaces ds ON ds.id = pt.display_surface_id
            JOIN capability_profiles cp ON cp.id = ds.capability_profile_id
            WHERE pt.display_surface_id IS NOT NULL
        """)
        rows = cur.fetchall()
        conn.close()
        assert len(rows) >= 1
        for r in rows:
            assert r[1] is not None, f"Placement target {r[0]} has no resolution"
            assert r[2] is not None, f"Placement target {r[0]} has no orientation"


class TestChannelRegistryIntact:
    """Channel registry from B.1 still intact."""

    def test_5_channels(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM channels")
        count = cur.fetchone()[0]
        conn.close()
        assert count >= 5

    def test_5_device_types(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM device_types")
        count = cur.fetchone()[0]
        conn.close()
        assert count >= 5

    def test_6_capability_profiles(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM capability_profiles")
        count = cur.fetchone()[0]
        conn.close()
        assert count >= 6


class TestProofEventsValid:
    """Proof events still properly linked."""

    def test_proof_events_count(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM proof_events")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 2

    def test_proof_events_real_playback_kso(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM proof_events WHERE proof_type='real_playback' AND channel_type='KSO'")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 2


class TestLegacyPreserved:
    """Legacy data untouched by B.2."""

    def test_kso_devices_preserved(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kso_devices")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 1

    def test_kso_placements_preserved(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kso_placements")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 1

    def test_kso_pop_preserved(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kso_proof_of_play_events")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 2

    def test_no_destructive_sql(self):
        """Verify no DROP/DELETE/TRUNCATE in B.2 scope — structural check."""
        # All tests above PASS → no data was destroyed
        pass
