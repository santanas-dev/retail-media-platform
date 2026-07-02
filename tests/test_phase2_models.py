"""
Retail Media Platform — Phase 2 Model Tests.

Tests: migration imports, metadata completeness, seed idempotency (code-level).
No database connection required — all tests are static/source-inspection.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPhase2Metadata(unittest.TestCase):
    """Verify SQLAlchemy metadata contains all required rewrite tables."""

    def test_import_models(self):
        """ORM module imports without errors."""
        from packages.domain.models import Base, REQUIRED_TABLES
        self.assertIsNotNone(Base)
        self.assertIsNotNone(REQUIRED_TABLES)

    def test_all_required_tables_present(self):
        """Base.metadata contains all 11 required foundation tables."""
        from packages.domain.models import REQUIRED_TABLES, Base
        actual = set(Base.metadata.tables.keys())
        missing = REQUIRED_TABLES - actual
        self.assertSetEqual(missing, set(), f"Missing tables: {missing}")

    def test_exact_table_count(self):
        """Metadata has exactly 11 tables (Phase 2 foundation)."""
        from packages.domain.models import Base
        count = len(Base.metadata.tables)
        self.assertEqual(count, 11, f"Expected 11 tables, got {count}")


class TestPhase2ModelColumns(unittest.TestCase):
    """Verify key columns exist on each model."""

    @classmethod
    def setUpClass(cls):
        from packages.domain import models as m
        cls.m = m

    def test_branch_columns(self):
        cols = {c.name for c in self.m.Branch.__table__.columns}
        self.assertTrue(cols >= {"id", "code", "name", "timezone", "is_active", "created_at"})

    def test_store_columns(self):
        cols = {c.name for c in self.m.Store.__table__.columns}
        self.assertTrue(cols >= {"id", "cluster_id", "code", "name", "address", "is_active"})

    def test_channel_columns(self):
        cols = {c.name for c in self.m.Channel.__table__.columns}
        self.assertTrue(cols >= {"id", "code", "name", "sort_order", "is_active"})

    def test_device_type_columns(self):
        cols = {c.name for c in self.m.DeviceType.__table__.columns}
        self.assertTrue(cols >= {"id", "channel_id", "code", "player_runtime"})

    def test_capability_profile_columns(self):
        cols = {c.name for c in self.m.CapabilityProfile.__table__.columns}
        self.assertTrue(cols >= {"id", "device_type_id", "code", "resolution_w", "resolution_h",
                                  "pop_mode", "supported_formats"})

    def test_physical_device_columns(self):
        cols = {c.name for c in self.m.PhysicalDevice.__table__.columns}
        self.assertTrue(cols >= {"id", "store_id", "device_type_id", "code", "status", "last_seen_at"})

    def test_device_certificate_columns(self):
        cols = {c.name for c in self.m.DeviceCertificate.__table__.columns}
        self.assertTrue(cols >= {"id", "physical_device_id", "certificate_type",
                                  "public_key", "fingerprint", "status"})

    def test_device_status_history_columns(self):
        cols = {c.name for c in self.m.DeviceStatusHistory.__table__.columns}
        self.assertTrue(cols >= {"id", "physical_device_id", "old_status", "new_status",
                                  "changed_at", "source"})

    def test_logical_carrier_columns(self):
        cols = {c.name for c in self.m.LogicalCarrier.__table__.columns}
        self.assertTrue(cols >= {"id", "physical_device_id", "code", "carrier_type",
                                  "labels_count", "led_panels_count"})

    def test_display_surface_columns(self):
        cols = {c.name for c in self.m.DisplaySurface.__table__.columns}
        self.assertTrue(cols >= {"id", "logical_carrier_id", "store_id", "code",
                                  "resolution_w", "resolution_h", "is_active"})


class TestPhase2ForeignKeys(unittest.TestCase):
    """Verify expected FK relationships."""

    @classmethod
    def setUpClass(cls):
        from packages.domain import models as m
        cls.m = m

    def _fk_targets(self, model, col_name):
        fks = [fk for fk in model.__table__.foreign_keys if fk.parent.name == col_name]
        self.assertTrue(fks, f"{model.__name__}.{col_name} has no FK")
        return {fk.target_fullname for fk in fks}

    def test_cluster_branch_fk(self):
        self.assertIn("branches.id", self._fk_targets(self.m.Cluster, "branch_id"))

    def test_store_cluster_fk(self):
        self.assertIn("clusters.id", self._fk_targets(self.m.Store, "cluster_id"))

    def test_device_type_channel_fk(self):
        self.assertIn("channels.id", self._fk_targets(self.m.DeviceType, "channel_id"))

    def test_capability_device_type_fk(self):
        self.assertIn("device_types.id", self._fk_targets(self.m.CapabilityProfile, "device_type_id"))

    def test_physical_device_store_fk(self):
        self.assertIn("stores.id", self._fk_targets(self.m.PhysicalDevice, "store_id"))

    def test_physical_device_type_fk(self):
        self.assertIn("device_types.id", self._fk_targets(self.m.PhysicalDevice, "device_type_id"))

    def test_certificate_device_fk(self):
        self.assertIn("physical_devices.id", self._fk_targets(self.m.DeviceCertificate, "physical_device_id"))

    def test_status_history_device_fk(self):
        self.assertIn("physical_devices.id", self._fk_targets(self.m.DeviceStatusHistory, "physical_device_id"))

    def test_carrier_device_fk(self):
        self.assertIn("physical_devices.id", self._fk_targets(self.m.LogicalCarrier, "physical_device_id"))

    def test_surface_carrier_fk(self):
        self.assertIn("logical_carriers.id", self._fk_targets(self.m.DisplaySurface, "logical_carrier_id"))


class TestPhase2SeedIdempotency(unittest.TestCase):
    """Verify seed SQL is idempotent at code level (ON CONFLICT DO NOTHING)."""

    _SEED_SRC: str | None = None

    @classmethod
    def _load_seed(cls) -> str:
        if cls._SEED_SRC is None:
            path = os.path.join(os.path.dirname(__file__), "..", "apps", "control-api", "seed.py")
            with open(path) as f:
                cls._SEED_SRC = f.read()
        return cls._SEED_SRC

    def test_seed_file_exists(self):
        """Seed file is present."""
        src = self._load_seed()
        self.assertIn("SEED_SQL", src)
        self.assertIn("INSERT INTO", src)

    def test_seed_on_conflict_count(self):
        """Every INSERT has a matching ON CONFLICT."""
        import re
        src = self._load_seed()
        # Extract only the SQL block from the f-string
        m = re.search(r'SEED_SQL = f"""(.*?)"""', src, re.DOTALL)
        self.assertIsNotNone(m, "Cannot find SEED_SQL f-string")
        sql = m.group(1)
        insert_count = len(re.findall(r"INSERT INTO", sql))
        conflict_count = len(re.findall(r"ON CONFLICT", sql))
        self.assertEqual(insert_count, conflict_count,
                         f"INSERT count {insert_count} != ON CONFLICT count {conflict_count}")
        self.assertEqual(insert_count, 9, f"Expected 9 INSERTs, got {insert_count}")

    def test_seed_insert_count(self):
        """Seed has exactly 9 INSERT statements."""
        src = self._load_seed()
        inserts = [l for l in src.split("\n") if l.strip().upper().startswith("INSERT")]
        self.assertEqual(len(inserts), 9, f"Expected 9 INSERTs, got {len(inserts)}")


class TestPhase2NoOldBackendDependency(unittest.TestCase):
    """Verify Phase 2 does not import from old backend code."""

    def test_models_no_backend_import(self):
        with open("packages/domain/models.py") as f:
            src = f.read()
        self.assertNotIn("from backend", src)
        self.assertNotIn("import backend", src)

    def test_database_no_backend_import(self):
        with open("packages/domain/database.py") as f:
            src = f.read()
        self.assertNotIn("from backend", src)
        self.assertNotIn("import backend", src)

    def test_database_no_hardcoded_production_url(self):
        """DATABASE_URL default is localhost dev, not production."""
        with open("packages/domain/database.py") as f:
            src = f.read()
        self.assertIn("localhost:5432", src)
        self.assertNotIn("prod", src.lower().split("database_url")[-1][:100])


if __name__ == "__main__":
    unittest.main()
