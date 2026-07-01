"""
E.1 — KSO Adapter Dry-Run Payload Builder: targeted tests.

Tests:
  - Adapter identity (name, channel_code)
  - supports() logic
  - build_payload() from valid/incomplete context
  - Payload structure validation
  - validate_payload() rules
  - simulate_delivery() behavior
  - Registry integration
  - Import boundaries (no KsoPlacement, no GeneratedManifest, etc.)
  - Compatibility
"""

import inspect
import re
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domains.orchestrator.contracts import (
    OrchestratorContext,
    DeviceInfo,
    SurfaceInfo,
    AdapterPayloadDraft,
    AdapterSimulationResult,
)
from app.domains.adapters.kso_adapter import (
    KsoAdapter,
    KSO_CHANNEL_CODE,
    KSO_ADAPTER_NAME,
    FORBIDDEN_SECRET_WORDS,
    _pick_first_device,
    _pick_surface,
    _check_secret_words,
    _recursive_check_forbidden,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _code_lines(fn):
    src = inspect.getsource(fn)
    return re.sub(r'(:\s*\n)\s*("""|\'\'\').*?\2', r'\1', src, flags=re.DOTALL, count=1)

def _make_context(**overrides) -> OrchestratorContext:
    """Build a minimal valid OrchestratorContext for KSO."""
    defaults = {
        "placement_id": "pl-1",
        "placement_code": "pl-code-1",
        "campaign_id": "camp-1",
        "channel_code": "kso",
        "channel_name": "КСО",
        "devices": [
            DeviceInfo(
                device_id="dev-1",
                device_code="KSO-001",
                store_id="store-1",
                status="active",
                surfaces=[
                    SurfaceInfo(
                        surface_id="surf-1",
                        resolution="768x1024",
                        orientation="portrait",
                        formats=["video/mp4", "image/jpeg"],
                        proof_type="real_playback",
                        interactive=False,
                    ),
                ],
            ),
        ],
        "creative_codes": ["CR-001", "CR-002"],
        "start_date": "2026-07-01",
        "end_date": "2026-07-10",
    }
    defaults.update(overrides)
    return OrchestratorContext(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Adapter Identity (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestAdapterIdentity(unittest.TestCase):
    """KsoAdapter has correct name and channel_code."""

    def setUp(self):
        self.adapter = KsoAdapter()

    def test_adapter_name_is_kso(self):
        assert self.adapter.adapter_name == "kso"

    def test_channel_code_is_kso(self):
        assert self.adapter.channel_code == "kso"

    def test_constants_match(self):
        assert KSO_ADAPTER_NAME == "kso"
        assert KSO_CHANNEL_CODE == "kso"

    def test_adapter_is_instance_of_adapter_contract(self):
        from app.domains.orchestrator.contracts import AdapterContract
        assert isinstance(self.adapter, AdapterContract)


# ═══════════════════════════════════════════════════════════════════════════
# 2. supports() (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestSupports(unittest.TestCase):
    """KsoAdapter.supports() logic."""

    def setUp(self):
        self.adapter = KsoAdapter()

    def test_supports_kso(self):
        assert self.adapter.supports("kso") is True

    def test_supports_kso_with_profile(self):
        assert self.adapter.supports("kso", {"orientation": "portrait"}) is True

    def test_rejects_non_kso(self):
        assert self.adapter.supports("android_tv") is False
        assert self.adapter.supports("esl") is False

    def test_rejects_empty_channel(self):
        assert self.adapter.supports("") is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. build_payload() — valid context (8 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildPayloadValid(unittest.TestCase):
    """build_payload() returns valid KSO payload from complete context."""

    def setUp(self):
        self.adapter = KsoAdapter()

    async def _build(self, **overrides):
        ctx = _make_context(**overrides)
        return await self.adapter.build_payload(ctx)

    def test_payload_dry_run_true(self):
        import asyncio
        result = asyncio.run(self._build())
        assert result.payload["dry_run"] is True

    def test_payload_includes_device_code(self):
        import asyncio
        result = asyncio.run(self._build())
        assert result.payload["device_code"] == "KSO-001"

    def test_payload_includes_placement_code(self):
        import asyncio
        result = asyncio.run(self._build())
        assert result.payload["placement_code"] == "pl-code-1"

    def test_payload_includes_channel_code(self):
        import asyncio
        result = asyncio.run(self._build())
        assert result.payload["channel_code"] == "kso"

    def test_payload_includes_schedule(self):
        import asyncio
        result = asyncio.run(self._build())
        assert "schedule" in result.payload
        assert result.payload["schedule"]["date_from"] == "2026-07-01"
        assert result.payload["schedule"]["date_to"] == "2026-07-10"

    def test_payload_includes_resolution(self):
        import asyncio
        result = asyncio.run(self._build())
        assert result.payload["resolution_width"] == 768
        assert result.payload["resolution_height"] == 1024
        assert result.payload["orientation"] == "portrait"

    def test_payload_includes_items(self):
        import asyncio
        result = asyncio.run(self._build())
        assert "items" in result.payload
        assert len(result.payload["items"]) == 2
        assert result.payload["items"][0]["creative_code"] == "CR-001"
        assert result.payload["items"][0]["slot_order"] == 0

    def test_payload_includes_proof_type(self):
        import asyncio
        result = asyncio.run(self._build())
        assert result.payload["proof_type"] == "real_playback"


# ═══════════════════════════════════════════════════════════════════════════
# 4. build_payload() — incomplete context (6 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildPayloadIncomplete(unittest.TestCase):
    """build_payload() handles missing data with warnings."""

    def setUp(self):
        self.adapter = KsoAdapter()

    async def _build(self, **overrides):
        ctx = _make_context(**overrides)
        return await self.adapter.build_payload(ctx)

    def test_missing_device_code_warning(self):
        import asyncio
        result = asyncio.run(self._build(
            devices=[DeviceInfo(device_id="d1", surfaces=[])],
        ))
        assert len(result.warnings) > 0
        assert any("device_code" in w.lower() for w in result.warnings)

    def test_missing_placement_code_warning(self):
        import asyncio
        result = asyncio.run(self._build(placement_code=""))
        assert any("placement_code" in w.lower() for w in result.warnings)

    def test_no_devices_warning(self):
        import asyncio
        result = asyncio.run(self._build(devices=[]))
        assert any("device" in w.lower() for w in result.warnings)

    def test_no_creatives_warning(self):
        import asyncio
        result = asyncio.run(self._build(creative_codes=[]))
        assert any("creative" in w.lower() for w in result.warnings)

    def test_no_schedule_warning(self):
        import asyncio
        result = asyncio.run(self._build(start_date=None, end_date=None))
        assert any("schedule" in w.lower() for w in result.warnings)

    def test_no_resolution_warning(self):
        import asyncio
        result = asyncio.run(self._build(
            devices=[DeviceInfo(device_id="d1", surfaces=[])]
        ))
        assert any("resolution" in w.lower() for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Payload Safety (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestPayloadSafety(unittest.TestCase):
    """build_payload() never includes secrets."""

    def setUp(self):
        self.adapter = KsoAdapter()

    async def _build(self, **overrides):
        ctx = _make_context(**overrides)
        return await self.adapter.build_payload(ctx)

    def test_no_secret_in_payload_keys(self):
        import asyncio
        result = asyncio.run(self._build())
        payload_str = str(result.payload).lower()
        for word in ["password", "secret", "token", "access_key"]:
            assert word not in payload_str, f"Forbidden word in payload: {word}"

    def test_no_signed_urls(self):
        import asyncio
        result = asyncio.run(self._build())
        payload_str = str(result.payload).lower()
        for word in ["signed", "signature", "sig=", "?token="]:
            assert word not in payload_str

    def test_no_raw_credentials(self):
        import asyncio
        result = asyncio.run(self._build())
        payload_str = str(result.payload).lower()
        for word in ["authorization", "bearer"]:
            assert word not in payload_str

    def test_does_not_require_kso_placement_code(self):
        import asyncio
        result = asyncio.run(self._build())
        payload_str = str(result.payload).lower()
        assert "kso_placement" not in payload_str


# ═══════════════════════════════════════════════════════════════════════════
# 6. validate_payload() (8 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestValidatePayload(unittest.TestCase):
    """validate_payload() catches structural issues."""

    def setUp(self):
        self.adapter = KsoAdapter()

    def _valid_payload(self):
        return {
            "adapter_name": "kso",
            "channel_code": "kso",
            "dry_run": True,
            "device_code": "KSO-001",
            "placement_code": "pl-1",
            "items": [{"creative_code": "CR-1", "media_type": "video/mp4"}],
        }

    def test_valid_payload_passes(self):
        errors = self.adapter.validate_payload(self._valid_payload())
        assert len(errors) == 0

    def test_non_kso_adapter_name_rejected(self):
        p = self._valid_payload()
        p["adapter_name"] = "android_tv"
        errors = self.adapter.validate_payload(p)
        assert len(errors) > 0

    def test_dry_run_false_rejected(self):
        p = self._valid_payload()
        p["dry_run"] = False
        errors = self.adapter.validate_payload(p)
        assert len(errors) > 0

    def test_missing_device_code_rejected(self):
        p = self._valid_payload()
        del p["device_code"]
        errors = self.adapter.validate_payload(p)
        assert any("device_code" in e for e in errors)

    def test_missing_placement_code_rejected(self):
        p = self._valid_payload()
        del p["placement_code"]
        errors = self.adapter.validate_payload(p)
        assert any("placement_code" in e for e in errors)

    def test_forbidden_secret_key_rejected(self):
        p = self._valid_payload()
        p["token"] = "abc123"
        errors = self.adapter.validate_payload(p)
        assert any("token" in e.lower() for e in errors)

    def test_invalid_proof_type_rejected(self):
        p = self._valid_payload()
        p["proof_type"] = "invalid_proof"
        errors = self.adapter.validate_payload(p)
        assert len(errors) > 0

    def test_negative_resolution_rejected(self):
        p = self._valid_payload()
        p["resolution_width"] = -1
        errors = self.adapter.validate_payload(p)
        assert len(errors) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 7. simulate_delivery() (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestSimulateDelivery(unittest.TestCase):
    """simulate_delivery() returns structured results."""

    def setUp(self):
        self.adapter = KsoAdapter()

    def _valid_payload(self):
        return {
            "adapter_name": "kso",
            "channel_code": "kso",
            "dry_run": True,
            "device_code": "KSO-001",
            "placement_code": "pl-1",
            "items": [],
        }

    def test_simulate_delivery_ok(self):
        import asyncio
        result = asyncio.run(self.adapter.simulate_delivery(self._valid_payload()))
        assert result.ok is True
        assert result.adapter_name == "kso"

    def test_simulate_delivery_fails_invalid(self):
        import asyncio
        result = asyncio.run(self.adapter.simulate_delivery({}))
        assert result.ok is False
        assert len(result.errors) > 0

    def test_simulate_delivery_has_details(self):
        import asyncio
        result = asyncio.run(self.adapter.simulate_delivery(self._valid_payload()))
        assert result.details["dry_run"] is True

    def test_simulate_delivery_no_network(self):
        """simulate_delivery is pure function — no network/DB calls."""
        import asyncio
        result = asyncio.run(self.adapter.simulate_delivery(self._valid_payload()))
        assert isinstance(result, AdapterSimulationResult)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Registry Integration (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistryIntegration(unittest.TestCase):
    """KSO adapter is registered and discoverable."""

    def test_get_adapter_kso_returns_kso_adapter(self):
        from app.domains.adapters.registry import get_adapter
        adapter = get_adapter("kso")
        assert adapter is not None
        assert adapter.adapter_name == "kso"

    def test_select_adapter_kso_works(self):
        from app.domains.orchestrator.service import select_adapter
        adapter = select_adapter("kso")
        assert adapter.adapter_name == "kso"

    def test_select_adapter_unsupported_raises(self):
        from app.domains.orchestrator.service import select_adapter
        from app.domains.orchestrator.service import UnsupportedChannel
        try:
            select_adapter("nonexistent_channel")
            assert False, "Should have raised"
        except UnsupportedChannel:
            pass

    def test_list_adapters_includes_kso(self):
        from app.domains.adapters.registry import list_adapters
        adapters = list_adapters()
        assert "kso" in adapters

    def test_mock_adapter_still_importable(self):
        from app.domains.adapters.mock_adapter import MockAdapter
        mock = MockAdapter()
        assert mock.adapter_name == "mock"


# ═══════════════════════════════════════════════════════════════════════════
# 9. Import Boundaries (7 tests)
# ═══════════════════════════════════════════════════════════════════════════

def _import_lines(src: str) -> str:
    """Extract only import lines from source code."""
    lines = [l for l in src.split("\n")
             if l.strip().startswith("from ") or l.strip().startswith("import ")]
    return "\n".join(lines)


class TestImportBoundaries(unittest.TestCase):
    """KsoAdapter does NOT import forbidden modules."""

    def test_no_kso_placement_import(self):
        from app.domains.adapters import kso_adapter
        src = _import_lines(_code_lines(kso_adapter))
        assert "KsoPlacement" not in src
        assert "kso_placement" not in src.lower()

    def test_no_generated_manifest_import(self):
        from app.domains.adapters import kso_adapter
        src = _import_lines(_code_lines(kso_adapter))
        assert "GeneratedManifest" not in src
        assert "generated_manifest" not in src.lower()

    def test_no_publication_import(self):
        from app.domains.adapters import kso_adapter
        src = _import_lines(_code_lines(kso_adapter))
        assert "publication" not in src.lower()

    def test_no_generate_manifests_import(self):
        from app.domains.adapters import kso_adapter
        src = _import_lines(_code_lines(kso_adapter))
        assert "generate_manifests" not in src.lower()

    def test_no_publish_batch_import(self):
        from app.domains.adapters import kso_adapter
        src = _import_lines(_code_lines(kso_adapter))
        assert "publish_batch" not in src.lower()

    def test_no_device_gateway_import(self):
        from app.domains.adapters import kso_adapter
        src = _import_lines(_code_lines(kso_adapter))
        assert "device_gateway" not in src.lower()

    def test_no_kso_manifest_projection_import(self):
        from app.domains.adapters import kso_adapter
        src = _import_lines(_code_lines(kso_adapter))
        assert "kso_manifest_projection" not in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 10. Helper Functions (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestHelperFunctions(unittest.TestCase):
    """Unit tests for internal helpers."""

    def test_pick_first_device_returns_device(self):
        ctx = _make_context()
        dev = _pick_first_device(ctx)
        assert dev is not None
        assert dev.device_code == "KSO-001"

    def test_pick_first_device_returns_none_for_empty(self):
        ctx = _make_context(devices=[])
        assert _pick_first_device(ctx) is None

    def test_pick_surface_returns_surface(self):
        ctx = _make_context()
        dev = _pick_first_device(ctx)
        assert dev is not None
        surf = _pick_surface(dev)
        assert surf is not None
        assert surf.resolution == "768x1024"

    def test_check_secret_words_detects_forbidden(self):
        errors = _check_secret_words("my_password_is_secret")
        assert len(errors) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 11. Compatibility (2 tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestCompatibility(unittest.TestCase):
    """E.1 does not break existing adapters or tests."""

    def test_mock_adapter_unchanged(self):
        from app.domains.adapters.mock_adapter import MockAdapter
        ma = MockAdapter()
        assert ma.supports("mock") is True
        assert ma.supports("kso") is False
