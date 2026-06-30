"""
B.4.1 — AdapterContract + MockAdapter + Registry tests.

Verifies:
  - AdapterContract cannot be instantiated directly (abstract)
  - MockAdapter implements contract correctly
  - Registry: register, get, list, clear, duplicate rejection
  - No DB writes, no publication/manifest/kso imports
"""
import unittest

from app.domains.orchestrator.contracts import (
    AdapterContract,
    AdapterPayloadDraft,
    AdapterSimulationResult,
    OrchestratorContext,
)
from app.domains.adapters.mock_adapter import MockAdapter
from app.domains.adapters.registry import (
    register_adapter,
    get_adapter,
    list_adapters,
    clear_registry,
)


# ═══════════════════════════════════════════════════════════════════════
# AdapterContract — abstract enforcement
# ═══════════════════════════════════════════════════════════════════════

class TestAdapterContractAbstract(unittest.TestCase):
    """AdapterContract is properly abstract — cannot instantiate directly."""

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            AdapterContract()  # type: ignore[abstract]

    def test_mock_adapter_is_instance(self):
        ma = MockAdapter()
        self.assertIsInstance(ma, AdapterContract)

    def test_mock_adapter_has_required_methods(self):
        ma = MockAdapter()
        self.assertTrue(callable(ma.supports))
        self.assertTrue(callable(ma.build_payload))
        self.assertTrue(callable(ma.validate_payload))
        self.assertTrue(callable(ma.simulate_delivery))


# ═══════════════════════════════════════════════════════════════════════
# MockAdapter — supports()
# ═══════════════════════════════════════════════════════════════════════

class TestMockAdapterSupports(unittest.TestCase):
    """MockAdapter.supports() behaviour."""

    def setUp(self):
        self.adapter = MockAdapter()

    def test_supports_own_channel(self):
        self.assertTrue(self.adapter.supports("mock"))

    def test_supports_any_channel(self):
        """Mock adapter supports any channel_code by default."""
        self.assertTrue(self.adapter.supports("kso"))
        self.assertTrue(self.adapter.supports("android_tv"))
        self.assertTrue(self.adapter.supports("any_channel"))

    def test_supports_with_capability_profile(self):
        profile = {"orientation": "portrait", "resolution": "768x1024"}
        self.assertTrue(self.adapter.supports("mock", profile))

    def test_rejects_explicitly_unsupported(self):
        self.assertFalse(self.adapter.supports("__unsupported__"))

    def test_rejects_empty_channel_code(self):
        self.assertFalse(self.adapter.supports(""))


# ═══════════════════════════════════════════════════════════════════════
# MockAdapter — build_payload()
# ═══════════════════════════════════════════════════════════════════════

class TestMockAdapterBuildPayload(unittest.TestCase):
    """MockAdapter.build_payload() returns valid draft."""

    def setUp(self):
        self.adapter = MockAdapter()

    def test_build_payload_returns_draft(self):
        import asyncio
        ctx = OrchestratorContext(
            placement_id="p1",
            placement_code="TP-001",
            campaign_id="c1",
            channel_code="mock",
        )
        result = asyncio.run(self.adapter.build_payload(ctx))
        self.assertIsInstance(result, AdapterPayloadDraft)
        self.assertEqual(result.channel_code, "mock")
        self.assertEqual(result.adapter_name, "mock")
        self.assertIn("placement_code", result.payload)

    def test_build_payload_includes_device_count(self):
        import asyncio
        from app.domains.orchestrator.contracts import DeviceInfo, SurfaceInfo

        ctx = OrchestratorContext(
            placement_id="p1",
            placement_code="TP-002",
            campaign_id="c1",
            channel_code="mock",
            devices=[
                DeviceInfo(
                    device_id="d1",
                    surfaces=[SurfaceInfo(surface_id="s1"), SurfaceInfo(surface_id="s2")],
                ),
            ],
        )
        result = asyncio.run(self.adapter.build_payload(ctx))
        self.assertEqual(result.payload["devices"], 1)
        self.assertEqual(result.payload["surfaces"], 2)

    def test_build_payload_no_db_write(self):
        """build_payload is pure — no side effects."""
        import asyncio
        ctx = OrchestratorContext(
            placement_id="p1",
            placement_code="TP-003",
            campaign_id="c1",
            channel_code="mock",
        )
        # Should not raise, should not access DB
        result = asyncio.run(self.adapter.build_payload(ctx))
        self.assertIsNotNone(result)


# ═══════════════════════════════════════════════════════════════════════
# MockAdapter — validate_payload()
# ═══════════════════════════════════════════════════════════════════════

class TestMockAdapterValidate(unittest.TestCase):
    """MockAdapter.validate_payload() checks required fields."""

    def setUp(self):
        self.adapter = MockAdapter()

    def test_valid_payload_passes(self):
        errors = self.adapter.validate_payload({
            "adapter": "mock",
            "channel": "mock",
            "placement_code": "TP-001",
        })
        self.assertEqual(errors, [])

    def test_missing_adapter_fails(self):
        errors = self.adapter.validate_payload({
            "channel": "mock",
            "placement_code": "TP-001",
        })
        self.assertTrue(any("adapter" in e for e in errors))

    def test_wrong_adapter_fails(self):
        errors = self.adapter.validate_payload({
            "adapter": "kso",
            "channel": "mock",
            "placement_code": "TP-001",
        })
        self.assertTrue(any("adapter" in e for e in errors))

    def test_missing_channel_fails(self):
        errors = self.adapter.validate_payload({
            "adapter": "mock",
            "placement_code": "TP-001",
        })
        self.assertTrue(any("channel" in e for e in errors))

    def test_missing_placement_code_fails(self):
        errors = self.adapter.validate_payload({
            "adapter": "mock",
            "channel": "mock",
        })
        self.assertTrue(any("placement_code" in e for e in errors))

    def test_non_dict_rejected(self):
        errors = self.adapter.validate_payload("not_a_dict")  # type: ignore[arg-type]
        self.assertEqual(errors, ["payload must be a dict"])


# ═══════════════════════════════════════════════════════════════════════
# MockAdapter — simulate_delivery()
# ═══════════════════════════════════════════════════════════════════════

class TestMockAdapterSimulate(unittest.TestCase):
    """MockAdapter.simulate_delivery() returns dry-run result."""

    def setUp(self):
        self.adapter = MockAdapter()

    def test_simulate_returns_ok(self):
        import asyncio
        payload = {"adapter": "mock", "channel": "mock",
                   "placement_code": "TP-001", "devices": 2, "surfaces": 3}
        result = asyncio.run(self.adapter.simulate_delivery(payload))
        self.assertIsInstance(result, AdapterSimulationResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.adapter_name, "mock")

    def test_simulate_no_devices_warns(self):
        import asyncio
        payload = {"adapter": "mock", "channel": "mock",
                   "placement_code": "TP-001", "devices": 0, "surfaces": 0}
        result = asyncio.run(self.adapter.simulate_delivery(payload))
        self.assertTrue(result.ok)
        self.assertTrue(any("device" in w.lower() for w in result.warnings))
        self.assertTrue(any("surface" in w.lower() for w in result.warnings))

    def test_simulate_details_correct(self):
        import asyncio
        payload = {"adapter": "mock", "channel": "mock",
                   "placement_code": "TP-001", "devices": 5, "surfaces": 7}
        result = asyncio.run(self.adapter.simulate_delivery(payload))
        self.assertEqual(result.details["device_count"], 5)
        self.assertEqual(result.details["surface_count"], 7)


# ═══════════════════════════════════════════════════════════════════════
# Registry tests
# ═══════════════════════════════════════════════════════════════════════

class TestAdapterRegistry(unittest.TestCase):
    """Adapter registry: register, get, list, clear, duplicate rejection."""

    def setUp(self):
        clear_registry()
        self.adapter = MockAdapter()

    def tearDown(self):
        clear_registry()

    def test_register_and_get(self):
        register_adapter(self.adapter)
        result = get_adapter("mock")
        self.assertIs(result, self.adapter)

    def test_get_unsupported_returns_none(self):
        result = get_adapter("nonexistent")
        self.assertIsNone(result)

    def test_list_adapters(self):
        register_adapter(self.adapter)
        adapters = list_adapters()
        self.assertIn("mock", adapters)
        self.assertEqual(adapters["mock"], "mock")

    def test_list_empty(self):
        adapters = list_adapters()
        self.assertEqual(adapters, {})

    def test_duplicate_same_adapter_ok(self):
        """Re-registering the same adapter instance is allowed."""
        register_adapter(self.adapter)
        register_adapter(self.adapter)  # Should not raise

    def test_duplicate_different_adapter_raises(self):
        register_adapter(self.adapter)
        other = MockAdapter()
        # Same channel_code "mock" but different instance → should raise
        # But since both are MockAdapter with channel_code="mock",
        # and we compare by identity (is not), this will raise
        with self.assertRaises(ValueError):
            register_adapter(other)

    def test_clear_registry(self):
        register_adapter(self.adapter)
        self.assertEqual(len(list_adapters()), 1)
        clear_registry()
        self.assertEqual(len(list_adapters()), 0)


# ═══════════════════════════════════════════════════════════════════════
# Isolation checks
# ═══════════════════════════════════════════════════════════════════════

class TestB41Isolation(unittest.TestCase):
    """B.4.1 code does not import forbidden modules."""

    def test_contracts_no_db_imports(self):
        import inspect
        import app.domains.orchestrator.contracts as c
        source = inspect.getsource(c)
        self.assertNotIn("sqlalchemy", source)
        self.assertNotIn("AsyncSession", source)

    def test_mock_adapter_no_publications_import(self):
        import inspect
        import app.domains.adapters.mock_adapter as ma
        source = inspect.getsource(ma)
        self.assertNotIn("publications", source)
        self.assertNotIn("device_gateway", source)

    def test_mock_adapter_no_manifest_import(self):
        import inspect
        import app.domains.adapters.mock_adapter as ma
        source = inspect.getsource(ma)
        self.assertNotIn("generated_manifests", source)
        self.assertNotIn("kso_placements", source)
        self.assertNotIn("kso_devices", source)

    def test_mock_adapter_no_db_write(self):
        """Source code check: no commit, execute, add in mock_adapter."""
        import inspect
        import app.domains.adapters.mock_adapter as ma
        source = inspect.getsource(ma)
        self.assertNotIn("commit()", source)
        self.assertNotIn("db.add", source)
        self.assertNotIn("db.execute", source)

    def test_registry_no_db_imports(self):
        import inspect
        import app.domains.adapters.registry as r
        source = inspect.getsource(r)
        self.assertNotIn("sqlalchemy", source)
        self.assertNotIn("AsyncSession", source)
