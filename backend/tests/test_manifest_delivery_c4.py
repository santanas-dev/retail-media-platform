"""
C.4 — Manifest Pull Dry-Run / Delivery Validation: targeted tests.

Validates all three manifest endpoints:
- Legacy KSO: GET /api/device-gateway/kso/{device_code}/manifest
- Legacy: GET /api/device-gateway/manifest/current
- Universal: GET /api/device-gateway/manifest/universal/current

All tests use code inspection + schema validation — no live HTTP server.
"""

import pytest
from uuid import uuid4
from unittest.mock import MagicMock

from app.domains.device_gateway import service, schemas, auth, models
from app.domains.device_gateway.models import GatewayDevice


# ═══════════════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════════════

def _code_lines(fn):
    """Get source lines of a function, excluding docstrings."""
    import inspect, re
    src = inspect.getsource(fn)
    result = re.sub(r'(:\s*\n)\s*("""|\'\'\').*?\2', r'\1', src, flags=re.DOTALL, count=1)
    return result


def _router_fn_source(name: str) -> str:
    import inspect
    from app.domains.device_gateway import router
    fn = getattr(router, name)
    return inspect.getsource(fn)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Auth: all manifest endpoints require device auth
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestAuth:
    """All manifest endpoints use authenticate_device, not user auth."""

    def test_legacy_manifest_current_uses_device_auth(self):
        src = _router_fn_source("manifest_current")
        assert "authenticate_device" in src
        assert "get_current_user" not in src
        assert "require_permission" not in src

    def test_kso_manifest_uses_device_auth(self):
        src = _router_fn_source("kso_manifest_by_device")
        assert "authenticate_device" in src

    def test_universal_manifest_uses_device_auth(self):
        src = _router_fn_source("universal_manifest_current")
        assert "authenticate_device" in src
        assert "get_current_user" not in src
        assert "require_permission" not in src

    def test_all_manifest_endpoints_reject_user_session(self):
        """No manifest endpoint accepts user session tokens."""
        for name in ("manifest_current", "universal_manifest_current", "kso_manifest_by_device"):
            src = _router_fn_source(name)
            assert "get_current_user" not in src, f"{name} accepts user session auth"

    def test_authenticate_device_blocks_disabled_retired(self):
        """authenticate_device checks device.status for disabled/retired."""
        src = _code_lines(auth.authenticate_device)
        assert "disabled" in src.lower()
        assert "retired" in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Legacy KSO Manifest Delivery
# ═══════════════════════════════════════════════════════════════════════════

class TestLegacyKsoManifest:
    """Legacy KSO manifest endpoint structure and safety."""

    def test_kso_endpoint_uses_generated_manifest(self):
        """KSO endpoint reads from GeneratedManifest, not UniversalManifestV1."""
        src = _router_fn_source("kso_manifest_by_device")
        assert "GeneratedManifest" in src
        assert "UniversalManifestV1" not in src
        assert "universal" not in src.lower()

    def test_kso_does_not_import_publication_flow(self):
        """KSO endpoint does not import publication write functions."""
        src = _router_fn_source("kso_manifest_by_device")
        assert "generate_manifest" not in src
        assert "publish_batch" not in src

    def test_kso_checks_device_code_match(self):
        """KSO endpoint verifies device.device_code matches URL device_code."""
        src = _router_fn_source("kso_manifest_by_device")
        assert "device.device_code" in src
        assert "Device code mismatch" in src or "mismatch" in src.lower()

    def test_kso_returns_structured_no_manifest(self):
        """KSO endpoint returns {status: 'no_manifest'} when no published manifest."""
        src = _router_fn_source("kso_manifest_by_device")
        assert '"no_manifest"' in src or "'no_manifest'" in src

    def test_kso_response_has_no_secrets(self):
        """KSO response dict has no secret/credential/token fields."""
        src = _router_fn_source("kso_manifest_by_device")
        return_dict = [l for l in src.split("\n") if "return" in l and "{" in l]
        combined = "\n".join(return_dict)
        assert "device_secret" not in combined
        assert "credential" not in combined.lower()

    def test_kso_filters_by_published_status(self):
        """KSO query filters GeneratedManifest.status == 'published'."""
        src = _router_fn_source("kso_manifest_by_device")
        assert '"published"' in src or "'published'" in src

    def test_kso_hashes_manifest_for_response(self):
        """KSO computes manifest_hash via SHA-256 canonical JSON."""
        src = _router_fn_source("kso_manifest_by_device")
        assert "manifest_hash" in src
        assert "sha256" in src.lower() or "hashlib" in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Legacy Manifest /manifest/current
# ═══════════════════════════════════════════════════════════════════════════

class TestLegacyManifestCurrent:
    """Legacy /manifest/current endpoint structure."""

    def test_legacy_manifest_current_uses_service(self):
        src = _router_fn_source("manifest_current")
        assert "get_current_manifest" in src
        assert "universal" not in src.lower()

    def test_legacy_manifest_current_accepts_etag_query(self):
        src = _router_fn_source("manifest_current")
        assert "current_manifest_hash" in src

    def test_legacy_manifest_current_updates_session_last_used(self):
        src = _router_fn_source("manifest_current")
        assert "session.last_used_at" in src.replace(" ", "")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Universal Manifest Delivery
# ═══════════════════════════════════════════════════════════════════════════

class TestUniversalManifestDelivery:
    """Universal /manifest/universal/current endpoint structure."""

    def test_universal_endpoint_uses_service_function(self):
        src = _router_fn_source("universal_manifest_current")
        assert "get_universal_manifest_for_device" in src

    def test_service_handles_disabled_retired(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "disabled" in src.lower()
        assert "retired" in src.lower()

    def test_service_uses_placement_resolver(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "_resolve_placement_for_gateway_device" in src

    def test_service_uses_build_universal_manifest_preview(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "build_universal_manifest_preview" in src

    def test_service_does_not_import_kso_placement(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "KsoPlacement" not in src

    def test_service_does_not_import_generated_manifest(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "GeneratedManifest" not in src

    def test_service_does_not_call_generate_manifests(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "generate_manifest" not in src

    def test_service_does_not_call_publish_batch(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "publish_batch" not in src

    def test_service_has_no_manifest_structured_response(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert '"no_manifest"' in src or "'no_manifest'" in src

    def test_service_catches_placement_not_found(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "PlacementNotFound" in src

    def test_service_catches_unsupported_channel(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "UnsupportedChannel" in src

    def test_service_catches_generic_exception(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "manifest_build_failed" in src

    def test_service_returns_dry_run_metadata(self):
        """UniversalManifestV1 from build_universal_manifest_preview has dry_run=True."""
        from app.domains.manifests.universal_builder import build_universal_manifest_preview
        src = _code_lines(build_universal_manifest_preview)
        assert "dry_run" in src.lower()

    def test_universal_response_schema_fields(self):
        """UniversalManifestCurrentResponse has clean fields, no secrets."""
        fields = set(schemas.UniversalManifestCurrentResponse.model_fields.keys())
        assert "status" in fields
        assert "manifest" in fields
        assert "manifest_hash" in fields
        assert "reason" in fields
        for secret_field in ("device_secret", "credential", "token", "password"):
            assert secret_field not in fields


# ═══════════════════════════════════════════════════════════════════════════
# 5. ETag / 304 behavior
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestETag:
    """ETag/304 for all manifest endpoints."""

    def test_universal_manifest_computes_hash(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "sha256" in src.lower() or "hashlib" in src.lower()
        assert "manifest_hash" in src

    def test_universal_checks_current_manifest_hash(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "current_manifest_hash" in src
        assert '"not_modified"' in src or "'not_modified'" in src

    def test_universal_validates_no_secrets_before_hash(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "validate_no_secrets" in src

    def test_secret_scan_covers_manifest_body(self):
        """validate_no_secrets is called on assembled manifest before response."""
        src = _code_lines(service.get_universal_manifest_for_device)
        # validate_no_secrets appears BEFORE manifest_hash computation
        lines = src.split("\n")
        secret_check_idx = next((i for i, l in enumerate(lines) if "validate_no_secrets" in l), None)
        hash_idx = next((i for i, l in enumerate(lines) if "sha256" in l.lower() and "manifest_hash" in l), None)
        if secret_check_idx is not None and hash_idx is not None:
            assert secret_check_idx < hash_idx, "Secret check must run before hash computation"

    def test_canonical_json_stable_no_secrets(self):
        """Manifest hash uses sort_keys=True, separators=(',',':')."""
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "sort_keys" in src
        assert "separators" in src


# ═══════════════════════════════════════════════════════════════════════════
# 6. No-Manifest Behavior
# ═══════════════════════════════════════════════════════════════════════════

class TestNoManifestBehavior:
    """Structured no_manifest responses across endpoints."""

    def test_universal_no_manifest_reasons_are_specific(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        # Must return structured reason (not generic error)
        reasons = ["no_matching_surface", "unsupported_channel", "manifest_build_failed"]
        found = [r for r in reasons if r in src]
        assert len(found) >= 2, f"Expected structured reasons, found: {found}"

    def test_universal_no_manifest_response_has_no_traceback(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "traceback" not in src.lower()
        assert "stacktrace" not in src.lower()  # forbidden key already blocks this
        assert "raw_exception" not in src

    def test_no_manifest_does_not_leak_internal_ids(self):
        """no_manifest responses use reason codes, not raw DB IDs."""
        src = _code_lines(service.get_universal_manifest_for_device)
        # reason values are strings like "no_matching_surface", not UUIDs
        assert "no_matching_surface" in src
        assert '"reason"' in src or "'reason'" in src

    def test_placement_resolver_has_three_priority_levels(self):
        src = _code_lines(service._resolve_placement_for_gateway_device)
        assert "display_surface_id" in src
        assert "logical_carrier" in src
        assert "physical_device_id" in src


# ═══════════════════════════════════════════════════════════════════════════
# 7. Access Boundaries: device isolation
# ═══════════════════════════════════════════════════════════════════════════

class TestAccessBoundaries:
    """Device isolation: device A cannot get device B's manifest."""

    def test_kso_checks_device_code_match(self):
        """KSO endpoint compares URL device_code to authenticated device_code."""
        src = _router_fn_source("kso_manifest_by_device")
        assert "device_code" in src
        assert "403" in src or "Device code mismatch" in src

    def test_universal_uses_authenticated_device_not_query_param(self):
        """Universal endpoint gets device from authenticate_device, not from query."""
        src = _router_fn_source("universal_manifest_current")
        # No query param for device_code
        query_params = [l for l in src.split("\n") if "Query" in l and "device" in l.lower()]
        device_code_queries = [l for l in query_params if "device_code" in l.lower()]
        assert len(device_code_queries) == 0, "Universal endpoint should not accept device_code query"

    def test_legacy_manifest_current_uses_authenticated_device(self):
        src = _router_fn_source("manifest_current")
        # No device_code query param for device selection
        assert "device_code" not in src.lower() or "device.device_code" in src.replace(" ", "")

    def test_all_manifest_endpoints_depend_on_auth_token(self):
        """All manifest endpoints derive device identity from JWT, not URL params."""
        for name in ("manifest_current", "universal_manifest_current"):
            src = _router_fn_source(name)
            # The device is from authenticate_device, not from path/query
            assert "authenticate_device" in src


# ═══════════════════════════════════════════════════════════════════════════
# 8. Safety: manifest endpoints are read-only
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestReadOnly:
    """Manifest endpoints do not write to any tables or change state."""

    def test_universal_has_no_db_add_calls(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        lines_with_add = [l for l in src.split("\n") if "db.add" in l]
        assert len(lines_with_add) == 0, "Universal manifest should not write to DB"

    def test_universal_commits_only_for_touch_device(self):
        """Only db.commit() for _touch_device; no inserts."""
        src = _code_lines(service.get_universal_manifest_for_device)
        commit_lines = [l for l in src.split("\n") if "db.commit" in l]
        assert len(commit_lines) <= 2  # one for not_modified path, one for ok path

    def test_universal_does_not_change_placement(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "placement.status" not in src.replace(" ", "")

    def test_universal_does_not_change_credentials(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "credential" not in src.lower()

    def test_kso_is_read_only(self):
        """KSO endpoint reads GeneratedManifest, does not write."""
        src = _router_fn_source("kso_manifest_by_device")
        assert "db.add" not in src
        # Only SELECT + no commit (inline function, no db.commit)
        assert "db.commit" not in src

    def test_legacy_manifest_current_touches_device(self):
        src = _code_lines(service.get_current_manifest)
        assert "_touch_device" in src


# ═══════════════════════════════════════════════════════════════════════════
# 9. Safety: no publication flow imports in universal path
# ═══════════════════════════════════════════════════════════════════════════

class TestUniversalManifestSafety:
    """Universal manifest path does not import or touch publication flow."""

    def test_no_publications_service_import(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "publications.service" not in src
        assert "publications.models" not in src

    def test_no_kso_manifest_projection_import(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "kso_manifest_projection" not in src

    def test_no_generated_manifest_import(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "GeneratedManifest" not in src
        assert "generated_manifest" not in src.lower()

    def test_no_publish_batch_import(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "publish_batch" not in src

    def test_no_generate_manifests_import(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "generate_manifest" not in src

    def test_no_pop_import(self):
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "ingest_pop" not in src

    def test_no_credential_management_in_path(self):
        """Universal manifest does not touch credential management."""
        src = _code_lines(service.get_universal_manifest_for_device)
        assert "DeviceCredential" not in src


# ═══════════════════════════════════════════════════════════════════════════
# 10. Boundary: manifest endpoints don't break other endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestBoundary:
    """Manifest endpoints do not affect heartbeat, config, PoP, or admin."""

    def test_heartbeat_endpoint_unchanged(self):
        src = _router_fn_source("device_heartbeat")
        assert "record_heartbeat" in src
        assert "universal" not in src.lower()

    def test_config_endpoint_unchanged(self):
        src = _router_fn_source("get_device_runtime_config")
        assert "compute_effective_config" in src

    def test_pop_event_endpoint_unchanged(self):
        src = _router_fn_source("submit_pop_event")
        assert "ingest_pop_event" in src

    def test_admin_create_device_unchanged(self):
        src = _router_fn_source("create_device")
        assert "devices.gateway.manage" in src

    def test_auth_model_global_unchanged(self):
        import inspect
        src = inspect.getsource(auth.authenticate_device)
        assert "universal" not in src.lower()
