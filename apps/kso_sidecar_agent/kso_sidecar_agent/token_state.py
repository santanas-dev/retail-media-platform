"""Memory-only token state for device auth.

Stores access token strictly in memory — NEVER on disk, NEVER in logs,
NEVER in status/config/doctor output.

Token value is hidden from repr/str/safe_summary.
"""

import time as _time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenState:
    """Holds device access token in memory only.

    access_token is deliberately excluded from repr/str.
    safe_summary() returns metadata only, no token value.
    """

    # Private — not in repr
    _access_token: str = field(default="", repr=False)

    # Public metadata
    token_type: str = ""
    expires_at: float = 0.0   # unix timestamp
    device_id: str = ""
    device_code: str = ""
    status: str = ""

    # ── Factory ────────────────────────────────────────────────────

    @classmethod
    def from_auth_response(cls, response: dict[str, Any], now: float | None = None) -> "TokenState":
        """Create TokenState from backend POST /auth/token response.

        Expected response format (from DeviceAuthResponse):
        {
            "access_token": "eyJ...",
            "token_type": "bearer",
            "expires_in": 3600,
            "device_id": "550e8400-...",
            "device_code": "a-05954",
            "status": "active"
        }
        """
        if now is None:
            now = _time.time()

        access_token = response.get("access_token", "")
        if not access_token or not isinstance(access_token, str):
            raise ValueError("access_token is required and must be a non-empty string")

        token_type = response.get("token_type", "bearer")
        if token_type != "bearer":
            raise ValueError(f"token_type must be 'bearer', got '{token_type}'")

        expires_in = response.get("expires_in")
        if not isinstance(expires_in, (int, float)) or expires_in <= 0:
            raise ValueError(f"expires_in must be a positive int, got {expires_in!r}")

        device_id = str(response.get("device_id", ""))
        if not device_id:
            raise ValueError("device_id is required")

        device_code = response.get("device_code", "")
        if not device_code or not isinstance(device_code, str):
            raise ValueError("device_code is required and must be a non-empty string")

        status = response.get("status", "")
        if not status or not isinstance(status, str):
            raise ValueError("status is required")

        return cls(
            _access_token=access_token,
            token_type=token_type,
            expires_at=now + expires_in,
            device_id=device_id,
            device_code=device_code,
            status=status,
        )

    # ── Properties ─────────────────────────────────────────────────

    @property
    def access_token(self) -> str:
        """Return the raw token. Use with caution — never log this value."""
        return self._access_token

    # ── Methods ────────────────────────────────────────────────────

    def is_valid(self, now: float | None = None, safety_window_sec: int = 30) -> bool:
        """Check if token exists and is not expiring within safety window."""
        if not self._access_token:
            return False
        if now is None:
            now = _time.time()
        return self.expires_at > now + safety_window_sec

    def expires_in_sec(self, now: float | None = None) -> float:
        """Return seconds until token expires (0 if expired)."""
        if now is None:
            now = _time.time()
        remaining = self.expires_at - now
        return max(remaining, 0.0)

    def authorization_header(self, now: float | None = None) -> str:
        """Return 'Bearer <token>' header. Raises ValueError if token invalid."""
        if not self.is_valid(now=now):
            raise ValueError("Token is missing or expired")
        return f"Bearer {self._access_token}"

    def safe_summary(self, now: float | None = None) -> dict:
        """Return public metadata. NEVER includes token value."""
        if now is None:
            now = _time.time()
        return {
            "authenticated": self.is_valid(now=now),
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "expires_in_sec": round(self.expires_in_sec(now)),
            "device_id": self.device_id,
            "device_code": self.device_code,
            "status": self.status,
        }

    def clear(self) -> None:
        """Remove token from memory."""
        self._access_token = ""
        self.token_type = ""
        self.expires_at = 0.0
        self.device_id = ""
        self.device_code = ""
        self.status = ""

    # ── String representations (safe — no token) ──────────────────

    def __repr__(self) -> str:
        authenticated = "yes" if self._access_token else "no"
        return (
            f"TokenState(authenticated={authenticated}, "
            f"device_code={self.device_code!r}, "
            f"expires_in_sec={round(self.expires_in_sec())})"
        )

    def __str__(self) -> str:
        return self.__repr__()
