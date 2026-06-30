"""
C.1 — Universal Manifest Device Gateway Delivery: targeted tests.
C.1.1 — Security & Regression Gate expansion (minimum 32 tests).

Tests for GET /api/device-gateway/manifest/universal/current endpoint.
No DB writes, no API-side effects beyond existing gateway patterns.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import datetime, timezone

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


@pytest.fixture
def mock_manifest():
    """Build a minimal valid UniversalManifestV1 mock."""
    from app.domains.manifests.universal_schema import (
        UniversalManifestV1, ManifestCampaign, ManifestPlacement,
        ManifestTarget, ManifestSecurity, ManifestMetadata,
        ManifestStatus,
    )
    return UniversalManifestV1(
        manifest_id="m-test-001",
        manifest_version="1.0",
        generated_at=datetime.now(timezone.utc),
        campaign=ManifestCampaign(campaign_code="TEST-CAMP"),
        placement=ManifestPlacement(placement_code="PLC-001", channel_code="mock"),
        targets=[ManifestTarget(target_type="surface", physical_device_code="DEV-001")],
        security=ManifestSecurity(),
        metadata=ManifestMetadata(dry_run=True),
        status=ManifestStatus.DRAFT,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Utility: source code inspector
# ═══════════════════════════════════════════════════════════════════════════

def _code_lines(fn):
    """Get source lines of a function, excluding docstrings."""
    import inspect
    src = inspect.getsource(fn)
    lines = src.split("\n")
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


def _module_import_lines(module_path: str):
    """Get the import lines from a module's source."""
    import importlib, inspect
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    return src


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

    @pytest.mark.asyncio
    async def test_active_device_accepted(self, mock_db):
        """Active device proceeds to manifest resolution (not denied)."""
        device = MagicMock(
            spec=GatewayDevice, status="active", id=uuid4(),
            display_surface_id=None, logical_carrier_id=None,
            physical_device_id=None,
        )
        result = await service.get_universal_manifest_for_device(device, mock_db)
        # Should not raise HTTPException for auth; returns no_manifest
        assert result["status"] == "no_manifest"

    @pytest.mark.asyncio
    async def test_lost_device_accepted(self, mock_db):
        """Lost device can still request manifest (not denied)."""
        device = MagicMock(
            spec=GatewayDevice, status="lost", id=uuid4(),
            display_surface_id=None, logical_carrier_id=None,
            physical_device_id=None,
        )
        result = await service.get_universal_manifest_for_device(device, mock_db)
        assert result["status"] == "no_manifest"


# ═══════════════════════════════════════════════════════════════════════════
# Router auth method check — endpoint uses device auth, not user session
# ═══════════════════════════════════════════════════════════════════════════

class TestRouterAuthMethod:
    """Verify the universal manifest endpoint uses device auth, not user auth."""

    def test_endpoint_uses_authenticate_device_not_get_current_user(self):
        """Route handler calls authenticate_device, not get_current_user."""
        import inspect
        from app.domains.device_gateway.router import universal_manifest_current
        src = inspect.getsource(universal_manifest_current)
        assert "authenticate_device" in src
        assert "get_current_user" not in src

    def test_endpoint_does_not_require_user_permission(self):
        """No require_permission() on the universal manifest route."""
        import inspect
        from app.domains.device_gateway.router import universal_manifest_current
        src = inspect.getsource(universal_manifest_current)
        assert "require_permission" not in src


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
        self, mock_build, mock_resolve, mock_device, mock_db, mock_manifest,
    ):
        """Device gets universal manifest when active placement exists."""
        placement_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
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
        self, mock_build, mock_resolve, mock_device, mock_db, mock_manifest,
    ):
        """Response manifest metadata has dry_run=true."""
        mock_resolve.return_value = uuid4()
        mock_build.return_value = mock_manifest

        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result["status"] == "ok"
        assert result["manifest"]["metadata"]["dry_run"] is True

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_no_secrets_in_response(self, mock_build, mock_resolve, mock_device, mock_db, mock_manifest):
        mock_resolve.return_value = uuid4()
        mock_build.return_value = mock_manifest

        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        manifest_str = str(result["manifest"]).lower()
        assert "token" not in manifest_str
        assert "secret" not in manifest_str
        assert "password" not in manifest_str
        assert "credential" not in manifest_str

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_no_manifest_when_builder_raises_placement_not_found(
        self, mock_build, mock_resolve, mock_device, mock_db,
    ):
        from app.domains.orchestrator.service import PlacementNotFound
        mock_resolve.return_value = uuid4()
        mock_build.side_effect = PlacementNotFound("PLC-001")
        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result["status"] == "no_manifest"

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_no_manifest_when_unsupported_channel(
        self, mock_build, mock_resolve, mock_device, mock_db,
    ):
        from app.domains.orchestrator.service import UnsupportedChannel
        mock_resolve.return_value = uuid4()
        mock_build.side_effect = UnsupportedChannel("unknown")
        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result["status"] == "no_manifest"
        assert result["reason"] == "unsupported_channel"

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_builder_generic_exception_returns_no_manifest(
        self, mock_build, mock_resolve, mock_device, mock_db,
    ):
        mock_resolve.return_value = uuid4()
        mock_build.side_effect = RuntimeError("Something broke")
        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result["status"] == "no_manifest"


# ═══════════════════════════════════════════════════════════════════════════
# ETag / 304 tests
# ═══════════════════════════════════════════════════════════════════════════

class TestETag:
    """ETag/304 support tests."""

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_not_modified_when_hash_matches(
        self, mock_build, mock_resolve, mock_device, mock_db, mock_manifest,
    ):
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

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_etag_present_in_ok_response(
        self, mock_build, mock_resolve, mock_device, mock_db, mock_manifest,
    ):
        """ETag (manifest_hash) is present in 'ok' response."""
        mock_resolve.return_value = uuid4()
        mock_build.return_value = mock_manifest

        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result["status"] == "ok"
        assert result["manifest_hash"] is not None
        assert len(result["manifest_hash"]) == 64

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_different_manifest_produces_different_etag(
        self, mock_build, mock_resolve, mock_device, mock_db, mock_manifest,
    ):
        """Different manifest content produces different ETag."""
        from copy import deepcopy
        manifest2 = deepcopy(mock_manifest)
        manifest2.manifest_id = "m-different-002"
        manifest2.campaign.campaign_code = "OTHER-CAMP"

        mock_resolve.return_value = uuid4()
        mock_build.side_effect = [mock_manifest, manifest2]

        result1 = await service.get_universal_manifest_for_device(mock_device, mock_db)
        result2 = await service.get_universal_manifest_for_device(mock_device, mock_db)

        assert result1["manifest_hash"] != result2["manifest_hash"]

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @pytest.mark.asyncio
    async def test_no_manifest_response_table_without_hash(
        self, mock_resolve, mock_device, mock_db,
    ):
        """no_manifest response is stable — no manifest_hash leaked."""
        mock_resolve.return_value = None
        result = await service.get_universal_manifest_for_device(mock_device, mock_db)
        assert result["status"] == "no_manifest"
        assert result.get("manifest_hash") is None
        assert result.get("manifest") is None

    @patch("app.domains.device_gateway.service._resolve_placement_for_gateway_device")
    @patch("app.domains.manifests.universal_builder.build_universal_manifest_preview")
    @pytest.mark.asyncio
    async def test_different_hash_returns_fresh_manifest(
        self, mock_build, mock_resolve, mock_device, mock_db, mock_manifest,
    ):
        """When client hash differs, return full 'ok' response, not 304."""
        mock_resolve.return_value = uuid4()
        mock_build.return_value = mock_manifest

        result = await service.get_universal_manifest_for_device(
            mock_device, mock_db, current_manifest_hash="0" * 64,
        )
        assert result["status"] == "ok"
        assert "manifest" in result


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
# Secret / no-leak tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSecretLeak:
    """Verify no device secrets, credentials, or tokens leak in response."""

    def test_secret_keywords_not_in_response_schema(self):
        """UniversalManifestCurrentResponse schema has no secret fields."""
        from app.domains.device_gateway.schemas import UniversalManifestCurrentResponse
        fields = list(UniversalManifestCurrentResponse.model_fields.keys())
        for secret_field in ("device_secret", "credential", "access_token", "password", "token"):
            assert secret_field not in fields, f"Leaked field: {secret_field}"

    def test_service_function_has_no_secret_params(self):
        """get_universal_manifest_for_device does not accept secret params."""
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "device_secret" not in src
        assert "device_credential" not in src

    def test_no_device_credential_in_response_dict_keys(self):
        """response dict keys never include credential/secret/token."""
        # This is a schema-level check — actual values tested in integration
        forbidden = {"credential", "secret", "token", "password", "access_key", "private_key"}
        from app.domains.device_gateway.schemas import UniversalManifestCurrentResponse
        fields = set(UniversalManifestCurrentResponse.model_fields.keys())
        assert fields.isdisjoint(forbidden)


# ═══════════════════════════════════════════════════════════════════════════
# Safety: no generated_manifests, no KSO, no publication flow
# ═══════════════════════════════════════════════════════════════════════════

class TestC1Safety:
    """Safety / import boundary tests — C.1 code does not touch legacy systems."""

    def test_universal_manifest_endpoint_does_not_use_kso_placement(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "KsoPlacement" not in src
        assert "kso_placement" not in src.lower()

    def test_universal_manifest_endpoint_does_not_use_generated_manifests(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "generated_manifest" not in src.lower()
        assert "generate_manifest" not in src.lower()

    def test_universal_manifest_endpoint_does_not_call_publish_batch(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "publish_batch" not in src

    def test_resolver_does_not_use_kso_models(self):
        src = _code_lines(service._resolve_placement_for_gateway_device)
        assert "KsoPlacement" not in src
        assert "kso_placement" not in src.lower()
        assert "KsoDevice" not in src
        assert "kso_device" not in src.lower()

    def test_service_does_not_import_publications_service(self):
        """get_universal_manifest_for_device does not import publications.service."""
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "publications.service" not in src
        assert "publications.models" not in src
        assert "GeneratedManifest" not in src

    def test_service_does_not_import_kso_projection(self):
        """C.1 code does not import KSO manifest projection."""
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "kso_manifest_projection" not in src

    def test_service_does_not_import_portal_routes(self):
        """C.1 code does not import portal routes."""
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "portal" not in src.lower()

    def test_service_updates_device_last_seen(self):
        """_touch_device is called in the ok/not_modified paths."""
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "_touch_device" in src


# ═══════════════════════════════════════════════════════════════════════════
# Legacy endpoint preservation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLegacyEndpointsPreserved:
    """Verify legacy KSO/manifest/heartbeat/PoP endpoints are unchanged."""

    def test_kso_endpoint_exists_and_uses_generated_manifest(self):
        import inspect
        from app.domains.device_gateway.router import kso_manifest_by_device
        src = inspect.getsource(kso_manifest_by_device)
        assert "GeneratedManifest" in src
        assert "universal" not in src.lower()

    def test_legacy_manifest_current_endpoint_unchanged(self):
        import inspect
        from app.domains.device_gateway.router import manifest_current
        src = inspect.getsource(manifest_current)
        assert "get_current_manifest" in src
        assert "universal" not in src.lower()

    def test_heartbeat_endpoint_unchanged(self):
        import inspect
        from app.domains.device_gateway.router import device_heartbeat
        src = inspect.getsource(device_heartbeat)
        assert "record_heartbeat" in src
        assert "universal" not in src.lower()

    def test_pop_event_endpoint_unchanged(self):
        import inspect
        from app.domains.device_gateway.router import submit_pop_event
        src = inspect.getsource(submit_pop_event)
        assert "ingest_pop_event" in src
        assert "universal" not in src.lower()

    def test_pop_batch_endpoint_unchanged(self):
        import inspect
        from app.domains.device_gateway.router import submit_pop_batch
        src = inspect.getsource(submit_pop_batch)
        assert "ingest_pop_batch" in src
        assert "universal" not in src.lower()

    def test_admin_routes_not_affected(self):
        """Admin routes (create_device, list_devices, etc.) unchanged."""
        import inspect
        from app.domains.device_gateway.router import admin_router
        route_paths = [getattr(r, "path", "") for r in admin_router.routes]
        # KSO endpoint is on device_router, not admin_router
        for path in route_paths:
            assert "universal" not in path.lower()

    def test_auth_model_global_unchanged(self):
        """authenticate_device function is unchanged, not modified for universal."""
        import inspect
        src = inspect.getsource(auth.authenticate_device)
        assert "universal" not in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Boundary: DB write check
# ═══════════════════════════════════════════════════════════════════════════

class TestDBWriteBoundary:
    """Verify C.1 does not write to generated_manifests or other legacy tables."""

    def test_no_db_write_calls_in_service(self):
        """get_universal_manifest_for_device uses db.commit only for _touch_device."""
        src = _code_lines(service.get_universal_manifest_for_device)
        # db.add should not appear
        assert "db.add" not in src
        # Only db.commit for _touch_device (called after not_modified and ok paths)
        commit_count = src.count("db.commit()")
        assert commit_count <= 2  # one per path (not_modified, ok)

    def test_resolver_only_reads(self):
        """_resolve_placement_for_gateway_device only does SELECT queries."""
        src = _code_lines(service._resolve_placement_for_gateway_device)
        assert "db.add" not in src
        assert "insert" not in src.lower() or "select" in src.lower()
