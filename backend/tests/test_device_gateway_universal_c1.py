"""
C.1 — Universal Manifest Device Gateway Delivery: targeted tests.

Tests for GET /api/device-gateway/manifest/universal/current endpoint.
No DB writes, no API-side effects beyond existing gateway patterns.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.domains.device_gateway import service, schemas, auth
from app.domains.device_gateway.models import GatewayDevice


@pytest.fixture
def mock_device() -> GatewayDevice:
    """Build a mock GatewayDevice with universal chain links."""
    return MagicMock(
        spec=GatewayDevice,
        id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        device_code="DEV-TEST-001",
        device_name="Test Device",
        channel_id=UUID("11111111-1111-1111-1111-111111111111"),
        store_id=UUID("22222222-2222-2222-2222-222222222222"),
        physical_device_id=UUID("33333333-3333-3333-3333-333333333333"),
        logical_carrier_id=None,
        display_surface_id=None,
        status="active",
        last_seen_at=None,
        registered_at=None,
        disabled_at=None,
        comment=None,
    )


@pytest.fixture
def mock_db():
    """Build an AsyncMock for database session."""
    return AsyncMock()


# ═══════════════════════════════════════════════════════════════════════════
# Auth/security tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthSecurity:
    """Device auth and security tests."""

    @pytest.mark.asyncio
    async def test_disabled_device_denied(self, mock_db):
        device = MagicMock(spec=GatewayDevice, status="disabled", id=uuid4())
        with pytest.raises(Exception) as exc:
            await service.get_universal_manifest_for_device(device, mock_db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_retired_device_denied(self, mock_db):
        device = MagicMock(spec=GatewayDevice, status="retired", id=uuid4())
        with pytest.raises(Exception) as exc:
            await service.get_universal_manifest_for_device(device, mock_db)
        assert exc.value.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Manifest resolution tests
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestResolution:
    """Placement resolution and manifest delivery tests."""

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @pytest.mark.asyncio
    async def test_no_manifest_when_no_placement(self, mock_resolve, mock_device, mock_db):
        mock_resolve.return_value = None
        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result["status"] == "no_manifest"
        assert result["reason"] == "no_matching_surface"

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_manifest_returned_when_placement_exists(
        self, mock_build, mock_resolve, mock_device, mock_db,
    ):
        """Device gets universal manifest when active placement exists."""
        placement_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        # Build a mock UniversalManifestV1 response
        from app.domains.manifests.universal_schema import (
            UniversalManifestV1, ManifestCampaign, ManifestPlacement,
            ManifestTarget, ManifestSecurity, ManifestMetadata,
            ManifestStatus,
        )
        mock_manifest = UniversalManifestV1(
            manifest_id="m-test-001",
            campaign=ManifestCampaign(campaign_code="TEST-CAMP"),
            placement=ManifestPlacement(placement_code="PLC-001", channel_code="mock"),
            targets=[ManifestTarget(target_type="surface", physical_device_code="DEV-001")],
            security=ManifestSecurity(),
            metadata=ManifestMetadata(dry_run=True),
            status=ManifestStatus.DRAFT,
        )

        mock_resolve.return_value = placement_id
        mock_build.return_value = mock_manifest

        result = await service.get_universal_manifest_for_device(mock_device, mock_db)

        assert result["status"] == "ok"
        assert result["manifest_version"] == "1.0"
        assert result["manifest_id"] == "m-test-001"
        assert "manifest" in result
        assert isinstance(result["manifest"], dict)

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_response_has_dry_run_preview_marker(
        self, mock_build, mock_resolve, mock_device, mock_db,
    ):
        """Response manifest metadata has dry_run=true."""
        from app.domains.manifests.universal_schema import (
            UniversalManifestV1, ManifestCampaign, ManifestPlacement,
            ManifestTarget, ManifestMetadata, ManifestStatus,
        )
        mock_manifest = UniversalManifestV1(
            campaign=ManifestCampaign(campaign_code="TEST"),
            placement=ManifestPlacement(placement_code="PLC", channel_code="mock"),
            targets=[ManifestTarget(target_type="surface", physical_device_code="DEV")],
            metadata=ManifestMetadata(dry_run=True),
            status=ManifestStatus.DRAFT,
        )
        mock_resolve.return_value = uuid4()
        mock_build.return_value = mock_manifest

        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result["status"] == "ok"
        assert result["manifest"]["metadata"]["dry_run"] is True

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_no_secrets_in_response(self, mock_build, mock_resolve, mock_device, mock_db):
        from app.domains.manifests.universal_schema import (
            UniversalManifestV1, ManifestCampaign, ManifestPlacement,
            ManifestTarget, ManifestMetadata, ManifestStatus,
        )
        mock_manifest = UniversalManifestV1(
            campaign=ManifestCampaign(campaign_code="TEST"),
            placement=ManifestPlacement(placement_code="PLC", channel_code="mock"),
            targets=[ManifestTarget(target_type="surface", physical_device_code="DEV")],
            metadata=ManifestMetadata(dry_run=True),
            status=ManifestStatus.DRAFT,
        )
        mock_resolve.return_value = uuid4()
        mock_build.return_value = mock_manifest

        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        manifest_dict = result["manifest"]

        # No credentials
        assert "token" not in str(manifest_dict).lower()
        assert "secret" not in str(manifest_dict).lower()
        assert "password" not in str(manifest_dict).lower()
        # No device credentials
        assert "credential" not in str(manifest_dict).lower()


# ═══════════════════════════════════════════════════════════════════════════
# ETag / 304 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestETag:
    """ETag/304 support tests."""

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_not_modified_when_hash_matches(
        self, mock_build, mock_resolve, mock_device, mock_db,
    ):
        from app.domains.manifests.universal_schema import (
            UniversalManifestV1, ManifestCampaign, ManifestPlacement,
            ManifestTarget, ManifestMetadata, ManifestStatus,
        )
        import json, hashlib

        mock_manifest = UniversalManifestV1(
            campaign=ManifestCampaign(campaign_code="TEST"),
            placement=ManifestPlacement(placement_code="PLC", channel_code="mock"),
            targets=[ManifestTarget(target_type="surface", physical_device_code="DEV")],
            metadata=ManifestMetadata(dry_run=True),
            status=ManifestStatus.DRAFT,
        )
        mock_resolve.return_value = uuid4()
        mock_build.return_value = mock_manifest

        # First call — get the hash
        result1 = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result1["status"] == "ok"
        current_hash = result1["manifest_hash"]

        # Second call — same hash → not_modified
        result2 = await service.get_universal_manifest_for_device(
            mock_device, mock_db, current_manifest_hash=current_hash,
        )
        assert result2["status"] == "not_modified"
        assert result2["manifest_hash"] == current_hash


# ═══════════════════════════════════════════════════════════════════════════
# Resolution priority tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPlacementResolution:
    """_resolve_placement_for_gateway_device priority tests."""

    @pytest.mark.asyncio
    async def test_no_links_returns_none(self, mock_db):
        device = MagicMock(
            spec=GatewayDevice,
            display_surface_id=None,
            logical_carrier_id=None,
            physical_device_id=None,
        )
        result = await service._resolve_placement_for_gateway_device(device, mock_db)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Safety: no generated_manifests, no KSO, no publication flow
# ═══════════════════════════════════════════════════════════════════════════

class TestC1Safety:
    """Safety / import boundary tests."""

    @staticmethod
    def _code_lines(fn):
        """Get source lines of a function, excluding docstrings."""
        import inspect
        src = inspect.getsource(fn)
        # Remove triple-quoted docstring
        lines = src.split("\n")
        # Remove first docstring line if present
        result_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if not in_docstring:
                result_lines.append(line)
        return "\n".join(result_lines)

    def test_universal_manifest_endpoint_does_not_use_kso_placement(self):
        src = self._code_lines(service.get_universal_manifest_for_device)
        assert "KsoPlacement" not in src
        assert "kso_placement" not in src.lower()

    def test_universal_manifest_endpoint_does_not_use_generated_manifests(self):
        src = self._code_lines(service.get_universal_manifest_for_device)
        assert "generated_manifest" not in src.lower()
        assert "generate_manifest" not in src.lower()

    def test_universal_manifest_endpoint_does_not_call_publish_batch(self):
        src = self._code_lines(service.get_universal_manifest_for_device)
        assert "publish_batch" not in src

    def test_resolver_does_not_use_kso_models(self):
        src = self._code_lines(service._resolve_placement_for_gateway_device)
        assert "KsoPlacement" not in src
        assert "kso_placement" not in src.lower()
        assert "KsoDevice" not in src
        assert "kso_device" not in src.lower()
