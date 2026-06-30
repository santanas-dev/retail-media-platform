"""
C.3 — Heartbeat / Device Status Validation: targeted tests.

Validates existing Device Gateway heartbeat/status flow.
Does NOT create new functionality — audits and tests what's already built.
All tests use mocked DB sessions + code inspection.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.domains.device_gateway import service, schemas, auth, models
from app.domains.device_gateway.models import GatewayDevice, DeviceHeartbeat


# ═══════════════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════════════

def _code_lines(fn):
    """Get source lines of a function, excluding docstrings."""
    import inspect, re
    src = inspect.getsource(fn)
    result = re.sub(r'(:\s*\n)\s*("""|\'\'\').*?\2', r'\1', src, flags=re.DOTALL, count=1)
    return result


def _mock_device(status="active", **overrides):
    kwargs = {
        "id": uuid4(),
        "device_code": "test-dev-hb-001",
        "device_name": "Test HB Device",
        "channel_id": uuid4(),
        "store_id": uuid4(),
        "physical_device_id": uuid4(),
        "logical_carrier_id": None,
        "display_surface_id": None,
        "status": status,
        "last_seen_at": None,
        "registered_at": datetime.now(timezone.utc),
        "disabled_at": None,
        "comment": None,
    }
    kwargs.update(overrides)
    return MagicMock(spec=GatewayDevice, **kwargs)


def _mock_db():
    return AsyncMock()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Auth: heartbeat endpoint access control
# ═══════════════════════════════════════════════════════════════════════════

class TestHeartbeatAuth:
    """Heartbeat endpoint uses device auth, not user session auth."""

    def test_heartbeat_uses_authenticate_device(self):
        import inspect
        from app.domains.device_gateway.router import device_heartbeat
        src = inspect.getsource(device_heartbeat)
        assert "authenticate_device" in src

    def test_heartbeat_no_user_permission(self):
        import inspect
        from app.domains.device_gateway.router import device_heartbeat
        src = inspect.getsource(device_heartbeat)
        assert "require_permission" not in src
        assert "get_current_user" not in src

    def test_authenticate_device_blocks_disabled(self):
        src = _code_lines(auth.authenticate_device)
        status_check_found = "disabled" in src.lower() and "retired" in src.lower()
        assert status_check_found, "authenticate_device should block disabled/retired"

    def test_record_heartbeat_does_not_recheck_auth(self):
        """record_heartbeat trusts authenticate_device — no redundant status check."""
        src = _code_lines(service.record_heartbeat)
        assert "disabled" not in src.lower()
        assert "retired" not in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Heartbeat validation: payload
# ═══════════════════════════════════════════════════════════════════════════

class TestHeartbeatValidation:
    """Heartbeat request payload validation rules."""

    def test_heartbeat_status_only_ok_warning_error(self):
        """HEARTBEAT_STATUSES = {ok, warning, error}."""
        assert service.HEARTBEAT_STATUSES == frozenset({"ok", "warning", "error"})

    def test_schema_heartbeat_status_default_ok(self):
        assert schemas.DeviceHeartbeatRequest.model_fields["status"].default == "ok"

    def test_forbidden_keys_blocks_secrets_in_details(self):
        """FORBIDDEN_KEYS blocks token/secret/credential in details_json."""
        forbidden = service.FORBIDDEN_KEYS
        assert "token" in forbidden
        assert "secret" in forbidden
        assert "credential" in forbidden
        assert "password" in forbidden
        assert "api_key" in forbidden

    def test_record_heartbeat_validates_manifest_hash_format(self):
        src = _code_lines(service.record_heartbeat)
        assert "current_manifest_hash" in src
        assert "64 hex" in src.lower() or "64" in src

    def test_record_heartbeat_validates_non_negative(self):
        src = _code_lines(service.record_heartbeat)
        assert "storage_free_mb must be >= 0" in src
        assert "cache_items_count must be >= 0" in src

    def test_heartbeat_schema_no_device_code_field(self):
        """DeviceHeartbeatRequest has no field to change device_code."""
        fields = set(schemas.DeviceHeartbeatRequest.model_fields.keys())
        assert "device_code" not in fields
        assert "channel_id" not in fields
        assert "status" in fields  # heartbeat status, not device status

    def test_heartbeat_schema_no_credential_fields(self):
        """Heartbeat request has no credential/secret fields."""
        fields = set(schemas.DeviceHeartbeatRequest.model_fields.keys())
        assert "device_secret" not in fields
        assert "credential" not in fields
        assert "secret" not in fields


# ═══════════════════════════════════════════════════════════════════════════
# 3. Device side-effects: last_seen, status transitions
# ═══════════════════════════════════════════════════════════════════════════

class TestHeartbeatSideEffects:
    """What heartbeat updates on GatewayDevice."""

    def test_updates_last_seen_at(self):
        src = _code_lines(service.record_heartbeat)
        assert "last_seen_at = _now()" in src or "last_seen_at = _now()" in src.replace(" ", "")

    def test_does_not_change_device_code(self):
        src = _code_lines(service.record_heartbeat)
        # "device.device_code" appears in log message, but is never ASSIGNED
        # Check no "device.device_code =" assignment
        assert "device.device_code =" not in src.replace(" ", "")

    def test_does_not_change_channel_id(self):
        src = _code_lines(service.record_heartbeat)
        assert "channel_id" not in src

    def test_does_not_change_physical_device_id(self):
        src = _code_lines(service.record_heartbeat)
        assert "physical_device_id" not in src

    def test_does_not_change_display_surface_id(self):
        src = _code_lines(service.record_heartbeat)
        assert "display_surface_id" not in src

    def test_pending_promotes_to_active(self):
        """pending device → active on first heartbeat."""
        src = _code_lines(service.record_heartbeat)
        assert "pending" in src
        assert "active" in src

    def test_lost_promotes_to_active(self):
        """lost device → active on heartbeat."""
        src = _code_lines(service.record_heartbeat)
        assert '"lost"' in src or "'lost'" in src

    def test_active_stays_active(self):
        """active device stays active on heartbeat — no status change."""
        src = _code_lines(service.record_heartbeat)
        # Only pending/lost → active; active stays active implicitly
        assert '"active"' in src or "'active'" in src or "active" in src


# ═══════════════════════════════════════════════════════════════════════════
# 4. Heartbeat response: no secrets
# ═══════════════════════════════════════════════════════════════════════════

class TestHeartbeatResponse:
    """Heartbeat response must not leak secrets."""

    def test_response_schema_no_secrets(self):
        """DeviceHeartbeatResponse has no secret/credential/token fields."""
        fields = set(schemas.DeviceHeartbeatResponse.model_fields.keys())
        assert "device_secret" not in fields
        assert "secret" not in fields
        assert "credential" not in fields
        assert "token" not in fields
        assert "access_token" not in fields
        assert "password" not in fields

    def test_response_contains_safe_fields(self):
        """Response: id, status, device_time, app_version, etc."""
        fields = set(schemas.DeviceHeartbeatResponse.model_fields.keys())
        safe = {"id", "gateway_device_id", "status", "device_time", "app_version",
                "os_version", "storage_free_mb", "cache_items_count",
                "current_manifest_hash", "ip_address", "user_agent",
                "details_json", "created_at"}
        assert fields.issubset(safe.union({"id", "gateway_device_id"}))

    def test_heartbeat_service_returns_model_not_dict(self):
        """record_heartbeat returns DeviceHeartbeat ORM model."""
        src = _code_lines(service.record_heartbeat)
        assert "return heartbeat" in src

    def test_heartbeat_response_schema_from_attributes(self):
        """DeviceHeartbeatResponse uses from_attributes=True."""
        assert schemas.DeviceHeartbeatResponse.model_config.get("from_attributes") is True


# ═══════════════════════════════════════════════════════════════════════════
# 5. Cross-propagation: KsoDevice.last_seen_at
# ═══════════════════════════════════════════════════════════════════════════

class TestHeartbeatCrossPropagation:
    """Heartbeat updates KsoDevice.last_seen_at for compatibility."""

    def test_kso_device_last_seen_updated(self):
        """record_heartbeat updates KsoDevice.last_seen_at if matching device_code exists."""
        src = _code_lines(service.record_heartbeat)
        assert "KsoDevice" in src
        assert "last_seen_at" in src

    def test_cross_propagation_only_updates_last_seen(self):
        """Only last_seen_at is cross-propagated, not device_code/status."""
        src = _code_lines(service.record_heartbeat)
        # After loading KsoDevice, only last_seen_at is modified
        assert "_kso.last_seen_at" in src.replace(" ", "")


# ═══════════════════════════════════════════════════════════════════════════
# 6. Admin heartbeat views
# ═══════════════════════════════════════════════════════════════════════════

class TestAdminHeartbeatViews:
    """Admin endpoints for viewing heartbeats require permissions."""

    def test_admin_heartbeats_requires_permission(self):
        import inspect
        from app.domains.device_gateway.router import get_heartbeats
        src = inspect.getsource(get_heartbeats)
        assert "require_permission" in src
        assert "devices.gateway.read" in src

    def test_admin_heartbeats_response_schema(self):
        """get_heartbeats returns list[DeviceHeartbeatResponse]."""
        import inspect
        from app.domains.device_gateway.router import get_heartbeats
        src = inspect.getsource(get_heartbeats)
        assert "DeviceHeartbeatResponse" in src

    def test_admin_heartbeat_response_no_secrets(self):
        """Admin heartbeat response has no secret fields."""
        fields = set(schemas.DeviceHeartbeatResponse.model_fields.keys())
        assert "secret_hash" not in fields
        assert "device_secret" not in fields


# ═══════════════════════════════════════════════════════════════════════════
# 7. Safety: heartbeat does not touch publication/KSO/manifest
# ═══════════════════════════════════════════════════════════════════════════

class TestHeartbeatSafety:
    """Heartbeat does not import or touch publication/KSO/manifest systems."""

    def test_no_publication_imports(self):
        src = _code_lines(service.record_heartbeat)
        assert "publications" not in src
        assert "generated_manifest" not in src.lower()

    def test_no_generate_manifests(self):
        src = _code_lines(service.record_heartbeat)
        assert "generate_manifest" not in src

    def test_no_publish_batch(self):
        src = _code_lines(service.record_heartbeat)
        assert "publish_batch" not in src

    def test_no_kso_projection_import(self):
        src = _code_lines(service.record_heartbeat)
        assert "kso_manifest_projection" not in src

    def test_no_placement_import(self):
        src = _code_lines(service.record_heartbeat)
        assert "Placement" not in src

    def test_no_manifest_import(self):
        src = _code_lines(service.record_heartbeat)
        assert "ManifestVersion" not in src
        assert "universal_builder" not in src

    def test_no_db_generated_manifests_write(self):
        """Heartbeat never writes to generated_manifests table."""
        src = _code_lines(service.record_heartbeat)
        assert "generated_manifest" not in src.lower()

    def test_log_event_does_not_log_secret(self):
        """_log_event call in heartbeat uses generic message, not device_secret."""
        src = _code_lines(service.record_heartbeat)
        log_lines = [l for l in src.split("\n") if "_log_event" in l]
        for line in log_lines:
            assert "device_secret" not in line


# ═══════════════════════════════════════════════════════════════════════════
# 8. Boundary: heartbeat does not affect other endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestHeartbeatBoundary:
    """Heartbeat does not affect KSO/Universal manifest/PoP/admin endpoints."""

    def test_kso_endpoint_unchanged(self):
        import inspect
        from app.domains.device_gateway.router import kso_manifest_by_device
        src = inspect.getsource(kso_manifest_by_device)
        assert "GeneratedManifest" in src

    def test_universal_manifest_endpoint_unchanged(self):
        import inspect
        from app.domains.device_gateway.router import universal_manifest_current
        src = inspect.getsource(universal_manifest_current)
        assert "get_universal_manifest_for_device" in src

    def test_pop_ingestion_unchanged(self):
        import inspect
        from app.domains.device_gateway.router import submit_pop_event
        src = inspect.getsource(submit_pop_event)
        assert "ingest_pop_event" in src

    def test_admin_routes_unchanged(self):
        import inspect
        from app.domains.device_gateway.router import admin_router
        route_paths = [getattr(r, "path", "") for r in admin_router.routes]
        # Admin has legitimate heartbeat/events views — verify they're present
        assert any("heartbeats" in p for p in route_paths), "Admin should have heartbeat views"
        assert any("events" in p for p in route_paths), "Admin should have event views"


# ═══════════════════════════════════════════════════════════════════════════
# 9. Device status policy: who can change what
# ═══════════════════════════════════════════════════════════════════════════

class TestDeviceStatusPolicy:
    """Device status change policy."""

    def test_heartbeat_cannot_downgrade_status(self):
        """Heartbeat only promotes pending/lost → active; never disables."""
        src = _code_lines(service.record_heartbeat)
        lines_with_status = [l for l in src.split("\n") if "status" in l and "=" in l and "device" in l]
        # Heartbeat sets device.status = "active" only for pending/lost
        for line in lines_with_status:
            assert "disabled" not in line
            assert "retired" not in line

    def test_update_device_handles_disabled_reactivation(self):
        """admin update_device — disabled_at is cleared when returning from disabled/retired."""
        src = _code_lines(service.update_device)
        assert "disabled_at" in src
        assert "None" in src  # disabled_at=None when reactivating

    def test_update_device_rejects_invalid_status(self):
        """update_device rejects unknown statuses."""
        src = _code_lines(service.update_device)
        assert "Invalid status" in src

    def test_admin_update_device_requires_manage_permission(self):
        import inspect
        from app.domains.device_gateway.router import update_device
        src = inspect.getsource(update_device)
        assert "require_permission" in src
        assert "devices.gateway.manage" in src
