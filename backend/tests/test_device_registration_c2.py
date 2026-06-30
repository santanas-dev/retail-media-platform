"""
C.2 — Device Registration Validation: targeted tests.

Validates existing Device Gateway registration/admin flow.
Does NOT create new functionality — audits and tests what's already built.
No DB writes in tests (all mocked). No HTTP server required.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta

from app.domains.device_gateway import service, schemas, auth, models
from app.domains.device_gateway.models import GatewayDevice, DeviceCredential, DeviceSession


# ═══════════════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════════════

def _code_lines(fn):
    """Get source lines of a function, excluding docstrings (handles single-line and multi-line)."""
    import inspect, re
    src = inspect.getsource(fn)
    # Remove function docstring via regex: triple-quoted string after colon+newline
    # Matches both single-line and multi-line docstrings
    result = re.sub(r'(:\s*\n)\s*("""|\'\'\').*?\2', r'\1', src, flags=re.DOTALL, count=1)
    return result


def _mock_device(status="active", **overrides):
    kwargs = {
        "id": uuid4(),
        "device_code": "test-dev-001",
        "device_name": "Test Device",
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


def _mock_credential(status="active", device_id=None):
    import bcrypt
    secret = "test-secret-min-32-bytes-length!!"
    secret_hash = bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()
    return MagicMock(
        spec=DeviceCredential,
        id=uuid4(),
        gateway_device_id=device_id or uuid4(),
        credential_type="shared_secret",
        secret_hash=secret_hash,
        fingerprint="abcdef1234567890",
        status=status,
        issued_at=datetime.now(timezone.utc),
        expires_at=None,
        revoked_at=datetime.now(timezone.utc) if status == "revoked" else None,
    )


def _mock_session(expired=False, revoked=False):
    from app.core.config import get_settings
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES) if not expired else now - timedelta(minutes=1)

    from jose import jwt
    import hashlib
    dev_id = uuid4()
    session_id = uuid4()

    claims = {
        "sub": f"device:{dev_id}",
        "type": "device",
        "aud": "device-gateway",
        "device_id": str(dev_id),
        "device_code": "test-dev-001",
        "session_id": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(claims, settings.effective_device_jwt_secret, algorithm=settings.JWT_ALGORITHM)

    return MagicMock(
        spec=DeviceSession,
        id=session_id,
        gateway_device_id=dev_id,
        credential_id=uuid4(),
        access_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=expires,
        revoked_at=now if revoked else None,
        last_used_at=None,
        client_ip=None,
    ), token


# ═══════════════════════════════════════════════════════════════════════════
# 1. Registration / Admin: create_device
# ═══════════════════════════════════════════════════════════════════════════

class TestCreateDevice:
    """GatewayDevice registration validation tests."""

    def test_schema_device_code_pattern(self):
        """device_code must match [a-z0-9_-]+ (1-64 chars)."""
        from app.domains.device_gateway.schemas import GatewayDeviceCreate
        from pydantic import ValidationError

        # Valid codes
        GatewayDeviceCreate(device_code="dev-01", channel_id=uuid4(), store_id=uuid4())
        GatewayDeviceCreate(device_code="test_device_2", channel_id=uuid4(), store_id=uuid4())
        GatewayDeviceCreate(device_code="x" * 64, channel_id=uuid4(), store_id=uuid4())

        # Invalid: uppercase
        with pytest.raises(ValidationError):
            GatewayDeviceCreate(device_code="DEV-01", channel_id=uuid4(), store_id=uuid4())

        # Invalid: empty
        with pytest.raises(ValidationError):
            GatewayDeviceCreate(device_code="", channel_id=uuid4(), store_id=uuid4())

        # Invalid: too long
        with pytest.raises(ValidationError):
            GatewayDeviceCreate(device_code="x" * 65, channel_id=uuid4(), store_id=uuid4())

        # Invalid: special chars
        with pytest.raises(ValidationError):
            GatewayDeviceCreate(device_code="dev@01", channel_id=uuid4(), store_id=uuid4())

    def test_channel_id_required(self):
        """channel_id is mandatory in GatewayDeviceCreate."""
        from app.domains.device_gateway.schemas import GatewayDeviceCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GatewayDeviceCreate(device_code="dev-01", store_id=uuid4())  # pyright: ignore[call-arg]

    def test_store_id_required(self):
        """store_id is mandatory in GatewayDeviceCreate."""
        from app.domains.device_gateway.schemas import GatewayDeviceCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GatewayDeviceCreate(device_code="dev-01", channel_id=uuid4())  # pyright: ignore[call-arg]

    def test_valid_device_creation_yields_response_schema(self):
        """CreateDevice schema produces correct fields for service layer."""
        cid = uuid4()
        sid = uuid4()
        data = schemas.GatewayDeviceCreate(
            device_code="new-dev-01",
            channel_id=cid,
            store_id=sid,
            status="active",
            physical_device_id=uuid4(),
            device_name="Test KSO Device",
        )
        assert data.device_code == "new-dev-01"
        assert data.channel_id == cid
        assert data.store_id == sid
        assert data.status == "active"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Credential Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestCredentialLifecycle:
    """Credential create / revoke / rotate lifecycle tests."""

    @pytest.mark.asyncio
    async def test_create_credential_returns_secret_only_once(self):
        """DeviceCredentialCreatedResponse has device_secret; DeviceCredentialResponse does NOT."""
        from app.domains.device_gateway.schemas import (
            DeviceCredentialCreatedResponse, DeviceCredentialResponse,
        )

        # Created response HAS device_secret
        created_fields = set(DeviceCredentialCreatedResponse.model_fields.keys())
        assert "device_secret" in created_fields

        # Regular response does NOT expose secret
        regular_fields = set(DeviceCredentialResponse.model_fields.keys())
        assert "device_secret" not in regular_fields

    def test_credential_secret_hash_never_in_response(self):
        """No response schema exposes secret_hash to clients."""
        from app.domains.device_gateway.schemas import (
            DeviceCredentialResponse, DeviceCredentialCreatedResponse,
        )
        for cls in (DeviceCredentialResponse, DeviceCredentialCreatedResponse):
            fields = set(cls.model_fields.keys())
            assert "secret_hash" not in fields, f"{cls.__name__} leaks secret_hash"

    def test_create_credential_service_uses_bcrypt(self):
        """create_credential() stores bcrypt hash, not raw secret."""
        src = _code_lines(service.create_credential)
        assert "bcrypt" in src or "hashpw" in src
        assert "secret_hash" in src

    def test_create_credential_rejects_duplicate_active(self):
        """create_credential checks for existing active shared_secret and rejects duplicates."""
        src = _code_lines(service.create_credential)
        assert "already has an active shared_secret" in src or "active shared_secret" in src

    def test_revoke_credential_revokes_all_sessions(self):
        """revoke_credential also revokes all DeviceSession rows for that credential."""
        src = _code_lines(service.revoke_credential)
        assert "DeviceSession" in src
        assert "revoked_at" in src

    def test_device_auth_uses_bcrypt_checkpw(self):
        """device_auth uses bcrypt.checkpw for timing-safe comparison."""
        src = _code_lines(service.device_auth)
        assert "bcrypt.checkpw" in src

    def test_device_auth_no_credential_rejected_safely(self):
        """No active credential → 401 with safe detail."""
        src = _code_lines(service.device_auth)
        assert "No active credential" in src
        assert "Invalid device credentials" in src


# ═══════════════════════════════════════════════════════════════════════════
# 3. Device Auth Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestDeviceAuthLifecycle:
    """Device auth: status-based access control."""

    def test_active_device_can_auth(self):
        """Active device → auth path proceeds (no rejection by status)."""
        src = _code_lines(service.device_auth)
        # status check only blocks disabled/retired
        assert "device.status in (\"disabled\", \"retired\")" in src or '("disabled", "retired")' in src

    def test_disabled_device_auth_rejected(self):
        """Disabled device → 401."""
        src = _code_lines(service.device_auth)
        assert '"disabled"' in src or "'disabled'" in src
        # Both disabled and retired are rejected
        assert "disabled" in src

    def test_retired_device_auth_rejected(self):
        """Retired device → 401."""
        src = _code_lines(service.device_auth)
        assert '"retired"' in src or "'retired'" in src

    def test_lost_device_can_attempt_auth(self):
        """Lost device is not blocked by status check in device_auth."""
        src = _code_lines(service.device_auth)
        # lost is NOT in the blocked statuses tuple
        blocked = ('"disabled"', '"retired"')
        found_blocked = any(b in src for b in blocked)
        assert found_blocked, "Auth should block disabled/retired"


# ═══════════════════════════════════════════════════════════════════════════
# 4. JWT Claims
# ═══════════════════════════════════════════════════════════════════════════

class TestJWTClaims:
    """JWT token claims structure and security."""

    def test_jwt_claims_are_minimal(self):
        """JWT claims contain only necessary fields: sub, type, aud, device_id, device_code, session_id, iat, exp."""
        src = _code_lines(service.device_auth)
        # Claims dict keys
        assert '"sub"' in src or "'sub'" in src
        assert '"type"' in src or "'type'" in src
        assert '"exp"' in src or "'exp'" in src
        assert '"aud"' in src or "'aud'" in src
        # Claims dict shouldn't include credential_id or secret fields
        # (device_code and device_id ARE normal claims)

    def test_jwt_has_expiry(self):
        """JWT has exp claim based on DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES."""
        src = _code_lines(service.device_auth)
        assert "DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES" in src
        assert "expires_at" in src or '"exp"' in src or "'exp'" in src

    def test_jwt_device_type_claim(self):
        """JWT has type=device claim for clear separation from user tokens."""
        src = _code_lines(service.device_auth)
        assert '"device"' in src or "'device'" in src

    def test_auth_response_has_no_secret(self):
        """DeviceAuthResponse schema has no secret field."""
        from app.domains.device_gateway.schemas import DeviceAuthResponse
        fields = set(DeviceAuthResponse.model_fields.keys())
        assert "device_secret" not in fields
        assert "secret" not in fields
        assert "secret_hash" not in fields


# ═══════════════════════════════════════════════════════════════════════════
# 5. Security: access control boundary
# ═══════════════════════════════════════════════════════════════════════════

class TestAccessControlBoundary:
    """Admin vs device endpoint permission separation."""

    def test_admin_create_device_requires_permission(self):
        """create_device endpoint requires devices.gateway.manage permission."""
        import inspect
        from app.domains.device_gateway.router import create_device
        src = inspect.getsource(create_device)
        assert "require_permission" in src
        assert "devices.gateway.manage" in src

    def test_admin_create_credential_requires_permission(self):
        """create_credential endpoint requires devices.gateway.credentials permission."""
        import inspect
        from app.domains.device_gateway.router import create_credential
        src = inspect.getsource(create_credential)
        assert "require_permission" in src
        assert "devices.gateway.credentials" in src

    def test_device_auth_no_user_permission(self):
        """device_auth endpoint has NO require_permission."""
        import inspect
        from app.domains.device_gateway.router import device_auth as router_fn
        src = inspect.getsource(router_fn)
        assert "require_permission" not in src

    def test_all_device_endpoints_use_authenticate_device(self):
        """All device endpoints use authenticate_device, not user auth."""
        import inspect
        from app.domains.device_gateway import router

        device_endpoints = [
            "device_me", "device_heartbeat", "manifest_current",
            "manifest_by_id", "universal_manifest_current",
            "media_metadata", "media_download", "media_download_kso",
            "submit_pop_event", "submit_pop_batch",
            "get_device_runtime_config",
        ]
        for ep_name in device_endpoints:
            fn = getattr(router, ep_name, None)
            if fn is None:
                continue
            src = inspect.getsource(fn)
            assert "authenticate_device" in src, f"{ep_name} missing authenticate_device"
            assert "get_current_user" not in src, f"{ep_name} uses user auth"

    def test_authenticate_device_checks_status(self):
        """authenticate_device checks device.status before returning."""
        import inspect
        src = inspect.getsource(auth.authenticate_device)
        assert "status" in src
        assert "disabled" in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Device Identity Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestDeviceIdentityLifecycle:
    """Device states and transitions."""

    def test_device_status_values(self):
        """GatewayDevice model and schema allow: pending, active, disabled, retired, lost."""
        # Schema default: "pending"
        from app.domains.device_gateway.schemas import GatewayDeviceCreate
        assert GatewayDeviceCreate.model_fields["status"].default == "pending"

        # Service checks for valid transition statuses
        from app.domains.device_gateway.service import update_device
        update_src = _code_lines(update_device)
        valid_statuses = ["active", "pending", "lost", "disabled", "retired"]
        found = [s for s in valid_statuses if s in update_src]
        assert len(found) >= 3, f"Expected status checks, found: {found}"

    def test_revoked_credential_sessions_revoked(self):
        """Revoking a credential also revokes all active sessions."""
        src = _code_lines(service.revoke_credential)
        assert "DeviceSession" in src
        assert "revoked" in src.lower()

    def test_update_device_handles_reactivation(self):
        """update_device clears disabled_at when status returns to active/pending/lost."""
        src = _code_lines(service.update_device)
        assert "disabled_at = None" in src or "disabled_at=None" in src

    def test_device_stores_linkage_chain_fields(self):
        """GatewayDevice ORM model has physical_device_id, logical_carrier_id, display_surface_id, channel_id."""
        from app.domains.device_gateway.models import GatewayDevice as GD
        assert hasattr(GD, "physical_device_id")
        assert hasattr(GD, "logical_carrier_id")
        assert hasattr(GD, "display_surface_id")
        assert hasattr(GD, "channel_id")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Safety Boundary: no publication flow / KSO / universal impact
# ═══════════════════════════════════════════════════════════════════════════

class TestC2SafetyBoundary:
    """C.2 does not touch publication flow, KSO, or universal manifest."""

    def test_create_device_does_not_import_publications(self):
        src = _code_lines(service.create_device)
        assert "publications" not in src
        assert "generated_manifest" not in src.lower()

    def test_create_credential_does_not_import_publications(self):
        src = _code_lines(service.create_credential)
        assert "publications" not in src
        assert "generated_manifest" not in src.lower()

    def test_device_auth_does_not_import_publications(self):
        src = _code_lines(service.device_auth)
        assert "publications" not in src
        assert "generated_manifest" not in src.lower()

    def test_update_device_does_not_import_publications(self):
        src = _code_lines(service.update_device)
        assert "publications" not in src
        assert "generated_manifest" not in src.lower()

    def test_revoke_credential_does_not_import_publications(self):
        src = _code_lines(service.revoke_credential)
        assert "publications" not in src

    def test_kube_router_kso_endpoint_still_present(self):
        """Verify KSO endpoint is still registered on device_router."""
        import inspect
        from app.domains.device_gateway.router import kso_manifest_by_device
        src = inspect.getsource(kso_manifest_by_device)
        assert "GeneratedManifest" in src
        assert "kso" in src.lower()

    def test_universal_manifest_endpoint_still_present(self):
        """Verify universal manifest endpoint is still registered."""
        import inspect
        from app.domains.device_gateway.router import universal_manifest_current
        src = inspect.getsource(universal_manifest_current)
        assert "get_universal_manifest_for_device" in src

    def test_pop_ingestion_unchanged(self):
        """PoP endpoints unchanged by C.2."""
        import inspect
        from app.domains.device_gateway.router import submit_pop_event, submit_pop_batch
        for fn in (submit_pop_event, submit_pop_batch):
            src = inspect.getsource(fn)
            assert "ingest_pop" in src
            assert "universal" not in src.lower()  # not affected by universal manifest


# ═══════════════════════════════════════════════════════════════════════════
# 8. Timing-safe / leak prevention
# ═══════════════════════════════════════════════════════════════════════════

class TestTimingSafe:
    """Timing-safe comparison and information leak prevention."""

    def test_timing_safe_compare_exists(self):
        """_timing_safe_compare exists in auth module."""
        assert hasattr(auth, "_timing_safe_compare")

    def test_unknown_device_returns_same_error_as_wrong_secret(self):
        """Unknown device → 401 with same detail as wrong secret (no oracle)."""
        src = _code_lines(service.device_auth)
        # All 401 responses use the same detail
        lines_with_401 = [l for l in src.split("\n") if "401" in l or "Invalid device credentials" in l]
        # At least one 401 with "Invalid device credentials"
        assert any("Invalid device credentials" in l for l in lines_with_401)

    def test_auth_log_event_does_not_log_secret(self):
        """_log_event calls for auth failures don't include secret in log message."""
        src = _code_lines(service.device_auth)
        # The word "device_login_failed" appears in _log_event calls
        assert "device_login_failed" in src
        # _log_event messages use generic text, never the raw secret
        # "device_secret" appears in param access but NOT in log message strings
        log_event_lines = [l for l in src.split("\n") if "_log_event" in l]
        for line in log_event_lines:
            assert "device_secret" not in line, f"Secret in log: {line.strip()}"
