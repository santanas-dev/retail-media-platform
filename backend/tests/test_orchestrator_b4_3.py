"""
B.4.3 — Orchestrator Simulation Engine tests.

Tests: simulation flow, error handling, result structure,
batch simulation, summary, import boundaries.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException


def _uid():
    return uuid4()


# ═══════════════════════════════════════════════════════════════════════
# SimulationResult structure
# ═══════════════════════════════════════════════════════════════════════

class TestSimulationResultStructure(unittest.TestCase):
    """SimulationResult + SimulationError + SimulationSummary dataclasses."""

    def test_result_defaults(self):
        from app.domains.orchestrator.simulation import SimulationResult
        r = SimulationResult(placement_id="p1", placement_code="TP")
        self.assertFalse(r.ok)
        self.assertTrue(r.dry_run)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, [])

    def test_result_fields_accessible(self):
        from app.domains.orchestrator.simulation import SimulationResult
        r = SimulationResult(
            placement_id="p1", placement_code="TP-001",
            campaign_id="c1", channel_code="mock",
            ok=True, target_count=2, surface_count=3, device_count=1,
            adapter_name="mock",
        )
        self.assertTrue(r.ok)
        self.assertEqual(r.target_count, 2)
        self.assertEqual(r.device_count, 1)

    def test_result_no_secret_keys(self):
        """SimulationResult has no secret/token/credential fields."""
        from app.domains.orchestrator.simulation import SimulationResult
        fields = list(SimulationResult.__dataclass_fields__.keys())
        forbidden = {"token", "secret", "password", "credential", "key"}
        for f in fields:
            for fb in forbidden:
                self.assertNotIn(fb, f.lower(),
                                 f"Field '{f}' looks like a secret")

    def test_error_structure(self):
        from app.domains.orchestrator.simulation import SimulationError
        e = SimulationError(
            step="resolve_context", code="placement_not_found",
            message="Placement 'x' not found",
        )
        self.assertEqual(e.step, "resolve_context")
        self.assertEqual(e.code, "placement_not_found")


# ═══════════════════════════════════════════════════════════════════════
# Simulation — mock-based flow tests
# ═══════════════════════════════════════════════════════════════════════

class TestSimulationFlow(unittest.TestCase):
    """simulate_placement flow with mocked service layer."""

    def setUp(self):
        from app.domains.adapters.registry import register_adapter, clear_registry
        from app.domains.adapters.mock_adapter import MockAdapter
        clear_registry()
        self.adapter = MockAdapter()
        register_adapter(self.adapter)

    def tearDown(self):
        from app.domains.adapters.registry import clear_registry
        clear_registry()

    def _mock_context(self, channel_code="mock"):
        from app.domains.orchestrator.contracts import (
            OrchestratorContext, DeviceInfo, SurfaceInfo,
        )
        return OrchestratorContext(
            placement_id=str(_uid()), placement_code="TP-001",
            campaign_id=str(_uid()), channel_code=channel_code,
            channel_name="Mock Channel",
            devices=[
                DeviceInfo(device_id=str(_uid()), device_code="DEV-001",
                          surfaces=[
                              SurfaceInfo(surface_id=str(_uid()),
                                         orientation="portrait",
                                         formats=["mp4", "jpg"],
                                         proof_type="real_playback"),
                          ]),
            ],
        )

    def test_simulate_success(self):
        from app.domains.orchestrator.simulation import simulate_placement
        from app.domains.orchestrator.service import (
            build_manifest_context, select_adapter,
        )

        ctx = self._mock_context()

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(return_value=ctx),
        ):
            result = asyncio.run(simulate_placement(
                AsyncMock(), _uid(),
            ))

        self.assertTrue(result.ok)
        self.assertTrue(result.dry_run)
        self.assertEqual(result.placement_code, "TP-001")
        self.assertEqual(result.channel_code, "mock")
        self.assertGreater(result.device_count, 0)

    def test_simulate_returns_adapter_name(self):
        from app.domains.orchestrator.simulation import simulate_placement
        ctx = self._mock_context()

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(return_value=ctx),
        ):
            result = asyncio.run(simulate_placement(AsyncMock(), _uid()))

        self.assertEqual(result.adapter_name, "mock")

    def test_simulate_has_payload_preview(self):
        from app.domains.orchestrator.simulation import simulate_placement
        ctx = self._mock_context()

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(return_value=ctx),
        ):
            result = asyncio.run(simulate_placement(AsyncMock(), _uid()))

        self.assertIn("adapter", result.payload_preview)
        self.assertIn("channel", result.payload_preview)

    def test_placement_not_found_returns_error(self):
        from app.domains.orchestrator.simulation import simulate_placement
        from app.domains.orchestrator.service import PlacementNotFound

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(side_effect=PlacementNotFound("bad-id")),
        ):
            result = asyncio.run(simulate_placement(AsyncMock(), _uid()))

        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].code, "placement_not_found")

    def test_placement_no_targets_returns_error(self):
        from app.domains.orchestrator.simulation import simulate_placement
        from app.domains.orchestrator.service import PlacementHasNoTargets

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(side_effect=PlacementHasNoTargets("p1")),
        ):
            result = asyncio.run(simulate_placement(AsyncMock(), _uid()))

        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0].code, "placement_no_targets")

    def test_unsupported_channel_returns_error(self):
        from app.domains.orchestrator.simulation import simulate_placement
        ctx = self._mock_context(channel_code="kso")

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(return_value=ctx),
        ):
            result = asyncio.run(simulate_placement(AsyncMock(), _uid()))

        self.assertFalse(result.ok)
        self.assertTrue(any(e.code == "unsupported_channel" for e in result.errors))

    def test_rls_denial_returns_error(self):
        from app.domains.orchestrator.simulation import simulate_placement

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(side_effect=HTTPException(
                status_code=403,
                detail="User scope 'advertiser:OTHER' cannot access",
            )),
        ):
            result = asyncio.run(simulate_placement(AsyncMock(), _uid()))

        self.assertFalse(result.ok)
        self.assertTrue(any(e.code == "access_denied" for e in result.errors))

    def test_capability_mismatch_returns_error(self):
        from app.domains.orchestrator.simulation import simulate_placement
        ctx = self._mock_context()
        # Remove formats to trigger capability error
        ctx.devices[0].surfaces[0].formats = []

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(return_value=ctx),
        ):
            result = asyncio.run(simulate_placement(AsyncMock(), _uid()))

        self.assertFalse(result.ok)
        self.assertTrue(
            any(e.code == "capability_mismatch" for e in result.errors),
            f"Expected capability_mismatch, got: {[e.code for e in result.errors]}",
        )

    def test_simulate_placements_batch(self):
        from app.domains.orchestrator.simulation import simulate_placements
        ctx = self._mock_context()

        with patch(
            "app.domains.orchestrator.simulation.build_manifest_context",
            new=AsyncMock(return_value=ctx),
        ):
            results = asyncio.run(simulate_placements(
                AsyncMock(), [_uid(), _uid(), _uid()],
            ))

        self.assertEqual(len(results), 3)
        for r in results:
            self.assertTrue(r.ok)

    def test_summarize_ok_and_failed(self):
        from app.domains.orchestrator.simulation import (
            SimulationResult, SimulationError, summarize_simulation_results,
        )
        results = [
            SimulationResult(placement_id="p1", placement_code="A", ok=True),
            SimulationResult(placement_id="p2", placement_code="B", ok=True),
            SimulationResult(placement_id="p3", placement_code="C", ok=False, errors=[
                SimulationError(step="x", code="e1", message="err"),
            ]),
        ]
        summary = summarize_simulation_results(results)
        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.ok, 2)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.errors, 1)

    def test_summary_counts_warnings(self):
        from app.domains.orchestrator.simulation import (
            SimulationResult, summarize_simulation_results,
        )
        results = [
            SimulationResult(placement_id="p1", placement_code="A",
                           ok=True, warnings=["w1", "w2"]),
        ]
        summary = summarize_simulation_results(results)
        self.assertEqual(summary.warnings, 2)

    def test_summary_collects_channels(self):
        from app.domains.orchestrator.simulation import (
            SimulationResult, summarize_simulation_results,
        )
        results = [
            SimulationResult(placement_id="p1", placement_code="A",
                           ok=True, channel_code="mock"),
            SimulationResult(placement_id="p2", placement_code="B",
                           ok=True, channel_code="kso"),
        ]
        summary = summarize_simulation_results(results)
        self.assertIn("mock", summary.channel_codes)
        self.assertIn("kso", summary.channel_codes)


# ═══════════════════════════════════════════════════════════════════════
# Simulation import boundary checks
# ═══════════════════════════════════════════════════════════════════════

class TestB43ImportBoundary(unittest.TestCase):
    """simulation.py does not import forbidden modules."""

    def test_no_publications_import(self):
        import inspect
        from app.domains.orchestrator import simulation as sim
        source = inspect.getsource(sim)
        self.assertNotIn("publications", source)

    def test_no_device_gateway_import(self):
        import inspect
        from app.domains.orchestrator import simulation as sim
        source = inspect.getsource(sim)
        self.assertNotIn("device_gateway", source)

    def test_no_generated_manifests_import(self):
        import inspect
        from app.domains.orchestrator import simulation as sim
        source = inspect.getsource(sim)
        # "generated_manifests" appears in docstrings only — strip all docstrings
        import re
        no_docs = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
        self.assertNotIn("generated_manifests", no_docs,
                         "generated_manifests referenced outside docstrings")

    def test_no_kso_placements_import(self):
        import inspect
        from app.domains.orchestrator import simulation as sim
        source = inspect.getsource(sim)
        self.assertNotIn("kso_placements", source)

    def test_no_kso_devices_import(self):
        import inspect
        from app.domains.orchestrator import simulation as sim
        source = inspect.getsource(sim)
        self.assertNotIn("kso_devices", source)

    def test_no_db_write(self):
        """simulation.py has no commit/execute/add calls."""
        import inspect
        from app.domains.orchestrator import simulation as sim
        source = inspect.getsource(sim)
        self.assertNotIn("commit()", source)
        self.assertNotIn("db.add(", source)
        self.assertNotIn("db.execute(", source)
