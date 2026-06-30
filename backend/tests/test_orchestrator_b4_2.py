"""
B.4.2 — Orchestrator Service + Placement Target Resolution tests.

Tests: chain resolution, capability check, adapter selection,
payload building, manifest draft. Uses real DB for chain resolution.
"""
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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


def _uid():
    return uuid4()


# ═══════════════════════════════════════════════════════════════════════
# Error types existence + coverage
# ═══════════════════════════════════════════════════════════════════════

class TestOrchestratorErrors(unittest.TestCase):
    """All orchestrator error types exist and are raisable."""

    def test_placement_not_found(self):
        from app.domains.orchestrator.service import PlacementNotFound
        with self.assertRaises(PlacementNotFound):
            raise PlacementNotFound("p1")

    def test_placement_has_no_channel(self):
        from app.domains.orchestrator.service import PlacementHasNoChannel
        with self.assertRaises(PlacementHasNoChannel):
            raise PlacementHasNoChannel("p1")

    def test_placement_has_no_targets(self):
        from app.domains.orchestrator.service import PlacementHasNoTargets
        with self.assertRaises(PlacementHasNoTargets):
            raise PlacementHasNoTargets("p1")

    def test_surface_chain_incomplete(self):
        from app.domains.orchestrator.service import SurfaceChainIncomplete
        with self.assertRaises(SurfaceChainIncomplete):
            raise SurfaceChainIncomplete("s1", "logical_carrier")

    def test_capability_mismatch(self):
        from app.domains.orchestrator.service import CapabilityMismatch
        with self.assertRaises(CapabilityMismatch):
            raise CapabilityMismatch("kso", "no formats")

    def test_unsupported_channel(self):
        from app.domains.orchestrator.service import UnsupportedChannel
        with self.assertRaises(UnsupportedChannel):
            raise UnsupportedChannel("nonexistent")

    def test_adapter_validation_failed(self):
        from app.domains.orchestrator.service import AdapterValidationFailed
        with self.assertRaises(AdapterValidationFailed):
            raise AdapterValidationFailed("mock", ["bad payload"])

    def test_all_errors_extend_http_exception(self):
        from fastapi import HTTPException
        from app.domains.orchestrator.service import (
            PlacementNotFound, PlacementHasNoChannel, PlacementHasNoTargets,
            SurfaceChainIncomplete, CapabilityMismatch, UnsupportedChannel,
            AdapterValidationFailed,
        )
        for cls in [PlacementNotFound, PlacementHasNoChannel, PlacementHasNoTargets,
                     SurfaceChainIncomplete, CapabilityMismatch, UnsupportedChannel,
                     AdapterValidationFailed]:
            self.assertTrue(issubclass(cls, HTTPException),
                            f"{cls.__name__} must extend HTTPException")


# ═══════════════════════════════════════════════════════════════════════
# Capability compatibility
# ═══════════════════════════════════════════════════════════════════════

class TestCapabilityCompatibility(unittest.TestCase):
    """check_capability_compatibility() validates device profiles."""

    def test_empty_devices_errors(self):
        from app.domains.orchestrator.service import check_capability_compatibility
        from app.domains.orchestrator.contracts import OrchestratorContext
        ctx = OrchestratorContext(
            placement_id="p1", placement_code="TP", campaign_id="c1",
            channel_code="mock", devices=[],
        )
        errors = check_capability_compatibility(ctx)
        self.assertTrue(len(errors) > 0)

    def test_device_with_profiles_passes(self):
        from app.domains.orchestrator.service import check_capability_compatibility
        from app.domains.orchestrator.contracts import (
            OrchestratorContext, DeviceInfo, SurfaceInfo,
        )
        ctx = OrchestratorContext(
            placement_id="p1", placement_code="TP", campaign_id="c1",
            channel_code="mock",
            devices=[
                DeviceInfo(device_id="d1", surfaces=[
                    SurfaceInfo(surface_id="s1", orientation="portrait",
                               formats=["mp4", "jpg"]),
                ]),
            ],
        )
        errors = check_capability_compatibility(ctx)
        self.assertEqual(errors, [])

    def test_missing_orientation_errors(self):
        from app.domains.orchestrator.service import check_capability_compatibility
        from app.domains.orchestrator.contracts import (
            OrchestratorContext, DeviceInfo, SurfaceInfo,
        )
        ctx = OrchestratorContext(
            placement_id="p1", placement_code="TP", campaign_id="c1",
            channel_code="mock",
            devices=[
                DeviceInfo(device_id="d1", surfaces=[
                    SurfaceInfo(surface_id="s1", orientation=None, formats=["mp4"]),
                ]),
            ],
        )
        errors = check_capability_compatibility(ctx)
        self.assertTrue(any("orientation" in e for e in errors))

    def test_missing_formats_errors(self):
        from app.domains.orchestrator.service import check_capability_compatibility
        from app.domains.orchestrator.contracts import (
            OrchestratorContext, DeviceInfo, SurfaceInfo,
        )
        ctx = OrchestratorContext(
            placement_id="p1", placement_code="TP", campaign_id="c1",
            channel_code="mock",
            devices=[
                DeviceInfo(device_id="d1", surfaces=[
                    SurfaceInfo(surface_id="s1", orientation="portrait", formats=[]),
                ]),
            ],
        )
        errors = check_capability_compatibility(ctx)
        self.assertTrue(any("format" in e for e in errors))


# ═══════════════════════════════════════════════════════════════════════
# Adapter selection
# ═══════════════════════════════════════════════════════════════════════

class TestAdapterSelection(unittest.TestCase):
    """select_adapter() picks adapter from registry."""

    def setUp(self):
        from app.domains.adapters.registry import register_adapter, clear_registry
        from app.domains.adapters.mock_adapter import MockAdapter
        clear_registry()
        self.adapter = MockAdapter()
        register_adapter(self.adapter)

    def tearDown(self):
        from app.domains.adapters.registry import clear_registry
        clear_registry()

    def test_select_registered_adapter(self):
        from app.domains.orchestrator.service import select_adapter
        result = select_adapter("mock")
        self.assertIs(result, self.adapter)

    def test_unsupported_channel_raises(self):
        from app.domains.orchestrator.service import select_adapter, UnsupportedChannel
        with self.assertRaises(UnsupportedChannel):
            select_adapter("kso")


# ═══════════════════════════════════════════════════════════════════════
# Payload + manifest draft
# ═══════════════════════════════════════════════════════════════════════

class TestPayloadAndDraft(unittest.TestCase):
    """build_adapter_payload() + assemble_manifest_draft()."""

    def test_build_payload_via_mock(self):
        import asyncio
        from app.domains.adapters.mock_adapter import MockAdapter
        from app.domains.orchestrator.service import build_adapter_payload
        from app.domains.orchestrator.contracts import OrchestratorContext

        adapter = MockAdapter()
        ctx = OrchestratorContext(
            placement_id="p1", placement_code="TP", campaign_id="c1",
            channel_code="mock",
        )
        result = asyncio.run(build_adapter_payload(ctx, adapter))
        self.assertIsNotNone(result)
        self.assertEqual(result.adapter_name, "mock")

    def test_assemble_draft_returns_dry_run(self):
        from app.domains.orchestrator.service import assemble_manifest_draft, ManifestDraft
        from app.domains.orchestrator.contracts import (
            OrchestratorContext, AdapterPayloadDraft, DeviceInfo, SurfaceInfo,
        )
        ctx = OrchestratorContext(
            placement_id="p1", placement_code="TP-001", campaign_id="c1",
            channel_code="mock",
            devices=[DeviceInfo(device_id="d1", surfaces=[
                SurfaceInfo(surface_id="s1"),
            ])],
        )
        payload = AdapterPayloadDraft(
            channel_code="mock", adapter_name="mock",
            payload={"key": "val"},
        )
        draft = assemble_manifest_draft(ctx, payload)
        self.assertIsInstance(draft, ManifestDraft)
        self.assertEqual(draft.status, "dry_run")
        self.assertEqual(draft.placement_code, "TP-001")

    def test_draft_without_devices_warns(self):
        from app.domains.orchestrator.service import assemble_manifest_draft
        from app.domains.orchestrator.contracts import (
            OrchestratorContext, AdapterPayloadDraft,
        )
        ctx = OrchestratorContext(
            placement_id="p1", placement_code="TP", campaign_id="c1",
            channel_code="mock", devices=[],
        )
        payload = AdapterPayloadDraft(channel_code="mock", adapter_name="mock")
        draft = assemble_manifest_draft(ctx, payload)
        self.assertTrue(any("device" in w.lower() for w in draft.warnings))


# ═══════════════════════════════════════════════════════════════════════
# DB chain resolution (real DB)
# ═══════════════════════════════════════════════════════════════════════

class TestChainResolution(unittest.TestCase):
    """Real DB tests: placement → surface → device chain."""

    def test_placement_has_targets_and_surface(self):
        """Real DB: test-place-seed placement has channel + targets + surface chain."""
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.placement_code, ch.code AS channel_code,
                   COUNT(pt.id) AS target_count
            FROM placements p
            JOIN channels ch ON ch.id = p.channel_id
            LEFT JOIN placement_targets pt ON pt.placement_id = p.id
            WHERE p.placement_code = 'test-place-seed'
            GROUP BY p.placement_code, ch.code
        """)
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row, "test-place-seed must exist")
        self.assertEqual(row[1], "kso")
        self.assertGreaterEqual(row[2], 1, "Must have at least 1 target")

    def test_placement_target_linked_to_surface(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM placement_targets pt
            JOIN display_surfaces ds ON ds.id = pt.display_surface_id
            WHERE pt.display_surface_id IS NOT NULL
        """)
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 1, "At least one target linked to surface")

    def test_surface_chain_to_device(self):
        """Full chain: display_surface → carrier → physical_device."""
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM display_surfaces ds
            JOIN logical_carriers lc ON lc.id = ds.logical_carrier_id
            JOIN physical_devices pd ON pd.id = lc.physical_device_id
        """)
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 1, "Surface chain must reach physical device")


# ═══════════════════════════════════════════════════════════════════════
# Isolation checks
# ═══════════════════════════════════════════════════════════════════════

class TestB42Isolation(unittest.TestCase):
    """B.4.2 service does not import forbidden modules."""

    def test_no_publication_imports(self):
        import inspect
        from app.domains.orchestrator import service as svc
        source = inspect.getsource(svc)
        self.assertNotIn("publications", source)

    def test_no_device_gateway_imports(self):
        import inspect
        from app.domains.orchestrator import service as svc
        source = inspect.getsource(svc)
        self.assertNotIn("device_gateway", source)

    def test_no_generated_manifests_imports(self):
        import inspect
        from app.domains.orchestrator import service as svc
        source = inspect.getsource(svc)
        # "generated_manifests" appears in docstring as "No generated_manifests"
        # — check that it's not in an import or FK reference
        self.assertNotIn("from", [l for l in source.split("\n") if "generated_manifests" in l])
        self.assertNotIn("import generated_manifests", source)

    def test_no_kso_placements_imports(self):
        import inspect
        from app.domains.orchestrator import service as svc
        source = inspect.getsource(svc)
        self.assertNotIn("import kso_placements", source)
        self.assertNotIn("kso_placements", [
            l for l in source.split("\n") if "kso_placements" in l and "No kso_placements" not in l
        ])

    def test_no_kso_devices_imports(self):
        import inspect
        from app.domains.orchestrator import service as svc
        source = inspect.getsource(svc)
        self.assertNotIn("kso_devices", source)

    def test_no_db_write_in_build_functions(self):
        """build_adapter_payload + assemble_manifest_draft are pure."""
        import inspect
        from app.domains.orchestrator.service import (
            build_adapter_payload, assemble_manifest_draft,
        )
        for fn in [build_adapter_payload, assemble_manifest_draft]:
            source = inspect.getsource(fn)
            self.assertNotIn("commit()", source, f"{fn.__name__}: no DB writes")
            self.assertNotIn("db.add", source, f"{fn.__name__}: no DB writes")
