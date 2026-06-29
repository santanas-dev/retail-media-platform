"""
B.1 — Channel Registry Cleanup Tests.

Verifies channel registry state after B.1 seed changes.
Uses direct psycopg2 for DB checks — no async ORM needed.
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


REQUIRED_CHANNELS = ["kso", "android_tv", "price_checker", "esl", "led_shelf_banner"]


class TestChannelRegistry(unittest.TestCase):
    """5 каналов, русские labels."""

    def test_all_5_channels_exist(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM channels")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 5, "Need at least 5 channels")

    def test_required_channels_present(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT code FROM channels WHERE code = ANY(%s)", (REQUIRED_CHANNELS,))
        codes = {r[0] for r in cur.fetchall()}
        conn.close()
        self.assertEqual(codes, set(REQUIRED_CHANNELS),
                         f"Missing: {set(REQUIRED_CHANNELS) - codes}")

    def test_kso_channel_has_russian_label(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT name FROM channels WHERE code = 'kso'")
        name = cur.fetchone()[0]
        conn.close()
        self.assertEqual(name, "КСО")
        self.assertTrue(any(ord(c) > 127 for c in name))


class TestDeviceTypes(unittest.TestCase):
    """5 device types — один на канал."""

    def test_5_device_types(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM device_types")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 5)

    def test_one_device_type_per_channel(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.code, COUNT(dt.id)
            FROM channels c
            LEFT JOIN device_types dt ON dt.channel_id = c.id
            GROUP BY c.code
        """)
        counts = {r[0]: r[1] for r in cur.fetchall()}
        conn.close()
        for ch in REQUIRED_CHANNELS:
            self.assertGreaterEqual(counts.get(ch, 0), 1,
                                    f"No device type for channel {ch}")

    def test_kso_device_type_code(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT dt.code, dt.name FROM device_types dt
            JOIN channels c ON c.id = dt.channel_id
            WHERE c.code = 'kso'
        """)
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "kso_gen5")
        self.assertEqual(row[1], "КСО 5-го поколения")


class TestCapabilityProfiles(unittest.TestCase):
    """Capability profiles: portrait для KSO, impression для ESL."""

    def test_profiles_exist(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM capability_profiles")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 5)

    def test_kso_has_portrait_profile(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT cp.resolution, cp.orientation, cp.proof_type
            FROM capability_profiles cp
            JOIN device_types dt ON dt.id = cp.device_type_id
            JOIN channels c ON c.id = dt.channel_id
            WHERE c.code = 'kso' AND cp.orientation = 'portrait'
        """)
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "KSO needs a portrait capability profile")
        self.assertEqual(row[0], "768x1024")
        self.assertEqual(row[1], "portrait")
        self.assertEqual(row[2], "real_playback")

    def test_esl_impression_proof_type(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT cp.proof_type FROM capability_profiles cp
            JOIN device_types dt ON dt.id = cp.device_type_id
            JOIN channels c ON c.id = dt.channel_id
            WHERE c.code = 'esl'
        """)
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "ESL missing capability profile")
        self.assertEqual(row[0], "impression")


class TestPhysicalDevicesUniversal(unittest.TestCase):
    """KSO устройство видно через universal model."""

    def test_migrated_kso_device_visible(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT pd.external_code, pd.device_properties->>'legacy_source'
            FROM physical_devices pd
            JOIN device_types dt ON dt.id = pd.device_type_id
            JOIN channels c ON c.id = dt.channel_id
            WHERE c.code = 'kso' AND pd.external_code = 'test-dev-seed'
        """)
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "KSO device not found in universal model")
        self.assertEqual(row[0], "test-dev-seed")
        self.assertEqual(row[1], "kso_devices")

    def test_external_code_unique(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT external_code, COUNT(*)
            FROM physical_devices WHERE external_code IS NOT NULL
            GROUP BY external_code HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()
        conn.close()
        self.assertEqual(len(dups), 0, f"Duplicate external_codes: {dups}")


class TestDisplaySurfaceOrientationFix(unittest.TestCase):
    """768×1024 display surface → portrait profile."""

    def test_kso_portrait_surface_correct(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT ds.resolution, cp.orientation, cp.resolution
            FROM display_surfaces ds
            JOIN capability_profiles cp ON cp.id = ds.capability_profile_id
            JOIN device_types dt ON dt.id = cp.device_type_id
            JOIN channels c ON c.id = dt.channel_id
            WHERE c.code = 'kso' AND ds.resolution = '768x1024'
        """)
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "768x1024 display surface not found")
        self.assertEqual(row[1], "portrait", "768x1024 should use portrait profile")
        self.assertEqual(row[2], "768x1024", "Resolution mismatch between surface and profile")


class TestLegacyNoDrop(unittest.TestCase):
    """Legacy таблицы не удалены."""

    def test_kso_devices_preserved(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kso_devices")
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1, "kso_devices should be preserved")

    def test_kso_placements_preserved(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kso_placements")
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_kso_proof_of_play_preserved(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM kso_proof_of_play_events")
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)
