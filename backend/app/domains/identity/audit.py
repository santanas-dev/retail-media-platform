"""Login audit — secure logging of authentication attempts.

Never logs: password, password_hash, token, raw secrets.
Safe fields: username, user_id (nullable), success, result_code,
reason_code, occurred_at, ip_hash, user_agent_hash.
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity import models


async def record_login_success(
    db: AsyncSession,
    username: str,
    user_id: str | None = None,
) -> None:
    """Record a successful login attempt.

    Safe: no password, no token, no hash.
    """
    event = models.LoginAuditEvent(
        username=username,
        user_id=user_id,
        success=True,
        result_code="success",
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    # Caller commits — audit is fire-and-forget here


async def record_login_failure(
    db: AsyncSession,
    username: str,
    reason_code: str,
    user_id: str | None = None,
) -> None:
    """Record a failed login attempt.

    reason_code values:
    - 'invalid_credentials' — wrong username or password
    - 'locked' — account is locked (too many failed attempts)
    - 'inactive' — account is disabled (is_active=False)
    - 'archived' — account is archived (soft delete)
    - 'service_account' — service account attempted human login
    - 'blocked' — generic block (fallback)

    Safe: no password, no token, no hash.
    """
    event = models.LoginAuditEvent(
        username=username,
        user_id=user_id,
        success=False,
        result_code="failure",
        reason_code=reason_code,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)


async def record_admin_action(
    db: AsyncSession,
    actor_user_id: str,
    action: str,
    target_type: str | None = None,
    target_ref: str | None = None,
    details: dict | None = None,
) -> None:
    """Record an administrative action for audit trail.

    Safe: details dict must not contain secrets/tokens/passwords.
    Caller is responsible for stripping forbidden fields.
    """
    import json

    event = models.AdminAuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_ref=target_ref,
        details_json=details,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
