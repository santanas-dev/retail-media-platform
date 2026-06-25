"""Step 39.1.1 — Device Gateway Authentication Hardening Tests.

Tests for device_auth (service) and authenticate_device (auth middleware).
All tests use mocked DB sessions — no live PostgreSQL or HTTP server.
No secrets, URLs, or tokens in test output.
"""

import asyncio
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from jose import jwt


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

DEVICE_ID = uuid4()
DEVICE_CODE = "test-dev-auth-001"
CREDENTIAL_ID = uuid4()
SESSION_ID = uuid4()


def _mock_device(status="active"):
    dev = MagicMock()
    dev.id = DEVICE_ID
    dev.device_code = DEVICE_CODE
    dev.status = status
    dev.channel_id = uuid4()
    dev.store_id = uuid4()
    dev.device_name = "Test Auth Device"
    return dev


def _mock_credential(status="active", secret_hash=None):
    import bcrypt
    cred = MagicMock()
    cred.id = CREDENTIAL_ID
    cred.gateway_device_id = DEVICE_ID
    cred.credential_type = "shared_secret"
    cred.status = status
    cred.revoked_at = None
    cred.issued_at = datetime.now(timezone.utc)
    if secret_hash is None:
        cred.secret_hash = bcrypt.hashpw(b"test-secret-32-bytes-minimum!", bcrypt.gensalt()).decode()
    else:
        cred.secret_hash = secret_hash
    return cred


def _mock_session(credential_id=CREDENTIAL_ID, revoked=False, expired=False):
    from app.core.config import get_settings
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES) if not expired else now - timedelta(minutes=1)

    claims = {
        "sub": f"device:{DEVICE_ID}",
        "type": "device",
        "aud": "device-gateway",
        "device_id": str(DEVICE_ID),
        "device_code": DEVICE_CODE,
        "session_id": str(SESSION_ID),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(claims, settings.effective_device_jwt_secret, algorithm=settings.JWT_ALGORITHM)

    import hashlib
    sess = MagicMock()
    sess.id = SESSION_ID
    sess.gateway_device_id = DEVICE_ID
    sess.credential_id = credential_id
    sess.access_token_hash = hashlib.sha256(token.encode()).hexdigest()
    sess.expires_at = expires
    sess.revoked_at = now if revoked else None
    sess.last_used_at = None
    sess.client_ip = None
    return sess, token


# ══════════════════════════════════════════════════════════════════════
# Device Auth Service Tests (device_gateway/service.py: device_auth)
# ══════════════════════════════════════════════════════════════════════

class TestDeviceAuthService(unittest.TestCase):
    """Test device_auth() function with mocked DB."""

    def test_valid_device_returns_token(self):
        """device_code + correct secret → JWT token."""
        import bcrypt
        from app.domains.device_gateway import schemas
        from app.domains.device_gateway.service import device_auth

        secret = "test-secret-32-bytes-minimum!"
        secret_hash = bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()

        db = AsyncMock()
        dev = _mock_device("active")
        cred = _mock_credential("active", secret_hash=secret_hash)

        async def mock_execute(stmt):
            m = MagicMock()
            if "gateway_devices" in str(stmt) or "device_code" in str(stmt):
                m.scalar_one_or_none.return_value = dev
            else:
                m.scalar_one_or_none.return_value = cred
            return m

        db.execute = mock_execute

        data = schemas.DeviceAuthRequest(device_code=DEVICE_CODE, device_secret=secret)
        result = asyncio.run(device_auth(db, data))

        self.assertIsNotNone(result.access_token)
        self.assertEqual(result.token_type, "bearer")
        self.assertGreater(result.expires_in, 0)
        self.assertEqual(result.device_code, DEVICE_CODE)
        # Secret must never appear in response
        self.assertNotIn(secret, str(result))
        self.assertNotIn("secret", str(result).lower())

    def test_wrong_secret_rejected(self):
        """Wrong device_secret → 401."""
        import bcrypt
        from app.domains.device_gateway import schemas
        from app.domains.device_gateway.service import device_auth
        from fastapi import HTTPException

        secret_hash = bcrypt.hashpw(b"correct-secret-32-bytes-long!!", bcrypt.gensalt()).decode()

        db = AsyncMock()
        dev = _mock_device("active")
        cred = _mock_credential("active", secret_hash=secret_hash)

        async def mock_execute(stmt):
            m = MagicMock()
            if "gateway_devices" in str(stmt) or "device_code" in str(stmt):
                m.scalar_one_or_none.return_value = dev
            else:
                m.scalar_one_or_none.return_value = cred
            return m

        db.execute = mock_execute

        data = schemas.DeviceAuthRequest(device_code=DEVICE_CODE, device_secret="wrong-secret-32-bytes-long!!!!")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(device_auth(db, data))
        self.assertEqual(ctx.exception.status_code, 401)
        # Detail must not reveal whether device exists or secret was wrong
        self.assertEqual(ctx.exception.detail, "Invalid device credentials")

    def test_unknown_device_rejected_safely(self):
        """Unknown device_code → 401 with safe message."""
        from app.domains.device_gateway import schemas
        from app.domains.device_gateway.service import device_auth
        from fastapi import HTTPException

        db = AsyncMock()

        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            return m

        db.execute = mock_execute

        data = schemas.DeviceAuthRequest(device_code="unknown-device", device_secret="any-secret-32-bytes-minimum!")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(device_auth(db, data))
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid device credentials")

    def test_disabled_device_rejected(self):
        """Disabled device → 401."""
        from app.domains.device_gateway import schemas
        from app.domains.device_gateway.service import device_auth
        from fastapi import HTTPException

        db = AsyncMock()
        dev = _mock_device("disabled")

        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = dev
            return m

        db.execute = mock_execute

        data = schemas.DeviceAuthRequest(device_code=DEVICE_CODE, device_secret="any-secret-32-bytes-minimum!")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(device_auth(db, data))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_retired_device_rejected(self):
        """Retired device → 401."""
        from app.domains.device_gateway import schemas
        from app.domains.device_gateway.service import device_auth
        from fastapi import HTTPException

        db = AsyncMock()
        dev = _mock_device("retired")

        async def mock_execute(stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = dev
            return m

        db.execute = mock_execute

        data = schemas.DeviceAuthRequest(device_code=DEVICE_CODE, device_secret="any-secret-32-bytes-minimum!")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(device_auth(db, data))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_no_active_credential_rejected(self):
        """Device exists but has no active credential → 401."""
        from app.domains.device_gateway import schemas
        from app.domains.device_gateway.service import device_auth
        from fastapi import HTTPException

        db = AsyncMock()
        dev = _mock_device("active")

        async def mock_execute(stmt):
            m = MagicMock()
            if "gateway_devices" in str(stmt) or "device_code" in str(stmt):
                m.scalar_one_or_none.return_value = dev
            else:
                m.scalar_one_or_none.return_value = None  # no credential
            return m

        db.execute = mock_execute

        data = schemas.DeviceAuthRequest(device_code=DEVICE_CODE, device_secret="any-secret-32-bytes-minimum!")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(device_auth(db, data))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_secret_never_in_response(self):
        """Auth response must never contain the device_secret."""
        import bcrypt
        from app.domains.device_gateway import schemas
        from app.domains.device_gateway.service import device_auth

        secret = "never-appear-in-response-32bytes!"
        secret_hash = bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()

        db = AsyncMock()
        dev = _mock_device("active")
        cred = _mock_credential("active", secret_hash=secret_hash)

        async def mock_execute(stmt):
            m = MagicMock()
            if "gateway_devices" in str(stmt) or "device_code" in str(stmt):
                m.scalar_one_or_none.return_value = dev
            else:
                m.scalar_one_or_none.return_value = cred
            return m

        db.execute = mock_execute

        data = schemas.DeviceAuthRequest(device_code=DEVICE_CODE, device_secret=secret)
        result = asyncio.run(device_auth(db, data))

        response_dict = result.model_dump()
        self.assertNotIn("secret", response_dict)
        self.assertNotIn(secret, str(response_dict))
        # No secret_hash either
        self.assertNotIn("secret_hash", str(response_dict))


# ══════════════════════════════════════════════════════════════════════
# Authenticate Device Middleware Tests (device_gateway/auth.py: authenticate_device)
# ══════════════════════════════════════════════════════════════════════

class TestAuthenticateDeviceMiddleware(unittest.TestCase):
    """Test authenticate_device() with mocked DB + JWT."""

    def _make_request(self, token=None):
        req = MagicMock()
        req.headers = {}
        if token:
            req.headers["Authorization"] = f"Bearer {token}"
        req.client = MagicMock()
        req.client.host = "127.0.0.1"
        return req

    def test_valid_token_returns_device_and_session(self):
        """Valid JWT token → device + session returned."""
        from app.domains.device_gateway.auth import authenticate_device
        import bcrypt

        secret = bcrypt.hashpw(b"test-secret-32-bytes-minimum!", bcrypt.gensalt()).decode()
        cred = _mock_credential("active", secret_hash=secret)
        session, token = _mock_session()

        db = AsyncMock()

        async def mock_get(model, obj_id):
            m = MagicMock()
            if "GatewayDevice" in str(model):
                return _mock_device("active")
            elif "DeviceSession" in str(model):
                return session
            elif "DeviceCredential" in str(model):
                return cred
            return None

        db.get = mock_get

        req = self._make_request(token)
        device, sess = asyncio.run(authenticate_device(req, db))

        self.assertEqual(device.device_code, DEVICE_CODE)
        self.assertEqual(sess.id, SESSION_ID)

    def test_missing_auth_header_rejected(self):
        """No Authorization header → 401."""
        from app.domains.device_gateway.auth import authenticate_device
        from fastapi import HTTPException

        db = AsyncMock()
        req = self._make_request()  # no token

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(authenticate_device(req, db))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_invalid_token_rejected(self):
        """Invalid/forged JWT → 401."""
        from app.domains.device_gateway.auth import authenticate_device
        from fastapi import HTTPException

        db = AsyncMock()
        req = self._make_request("not-a-valid-jwt-token")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(authenticate_device(req, db))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_session_rejected(self):
        """Expired session token → 401."""
        from app.domains.device_gateway.auth import authenticate_device
        from fastapi import HTTPException
        import bcrypt

        secret = bcrypt.hashpw(b"test-secret-32-bytes-minimum!", bcrypt.gensalt()).decode()
        cred = _mock_credential("active", secret_hash=secret)
        session, token = _mock_session(expired=True)

        db = AsyncMock()

        async def mock_get(model, obj_id):
            m = MagicMock()
            if "GatewayDevice" in str(model):
                return _mock_device("active")
            elif "DeviceSession" in str(model):
                return session
            elif "DeviceCredential" in str(model):
                return cred
            return None

        db.get = mock_get

        req = self._make_request(token)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(authenticate_device(req, db))
        self.assertEqual(ctx.exception.status_code, 401)
        # JWT decode catches expired token → "Invalid token"
        self.assertIn("token", ctx.exception.detail.lower())

    def test_revoked_session_rejected(self):
        """Revoked session token → 401."""
        from app.domains.device_gateway.auth import authenticate_device
        from fastapi import HTTPException
        import bcrypt

        secret = bcrypt.hashpw(b"test-secret-32-bytes-minimum!", bcrypt.gensalt()).decode()
        cred = _mock_credential("active", secret_hash=secret)
        session, token = _mock_session(revoked=True)

        db = AsyncMock()

        async def mock_get(model, obj_id):
            m = MagicMock()
            if "GatewayDevice" in str(model):
                return _mock_device("active")
            elif "DeviceSession" in str(model):
                return session
            elif "DeviceCredential" in str(model):
                return cred
            return None

        db.get = mock_get

        req = self._make_request(token)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(authenticate_device(req, db))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_disabled_device_on_protected_route_rejected(self):
        """Token valid but device is disabled → 401."""
        from app.domains.device_gateway.auth import authenticate_device
        from fastapi import HTTPException
        import bcrypt

        secret = bcrypt.hashpw(b"test-secret-32-bytes-minimum!", bcrypt.gensalt()).decode()
        cred = _mock_credential("active", secret_hash=secret)
        session, token = _mock_session()

        db = AsyncMock()

        async def mock_get(model, obj_id):
            m = MagicMock()
            if "GatewayDevice" in str(model):
                return _mock_device("disabled")
            elif "DeviceSession" in str(model):
                return session
            elif "DeviceCredential" in str(model):
                return cred
            return None

        db.get = mock_get

        req = self._make_request(token)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(authenticate_device(req, db))
        self.assertEqual(ctx.exception.status_code, 401)


# ══════════════════════════════════════════════════════════════════════
# Credential Security Notes (verified in service.py code review)
# ══════════════════════════════════════════════════════════════════════
#
# create_credential() in service.py:
#   - Secret generated via secrets.token_hex(32) — 64 hex chars
#   - Stored as bcrypt hash (secret_hash column) — never raw
#   - DeviceCredentialCreatedResponse contains device_secret ONCE
#   - DeviceCredentialResponse (GET/PUT) NEVER contains secret
#   - Fingerprint via sha256 of secret (one-way)
#
# These guarantees are verified by code review of service.py:261-313.
