"""Business audit logging — records critical business actions to admin_audit_events.

Uses the existing record_admin_action() from identity/audit.py for DB writes.
Provides safe payload stripping (no secrets/tokens/passwords/URLs).

Usage:
    from app.domains.audit.service import audit_business_action

    await audit_business_action(
        db, actor_user_id="...", action="campaign.create",
        target_type="campaign", target_ref=campaign_code,
        details={"name": payload.name, "status": "draft"},
    )
"""

from datetime import datetime, timezone

from app.domains.identity.audit import record_admin_action
from sqlalchemy.ext.asyncio import AsyncSession

# Fields that must NEVER appear in audit details_json
FORBIDDEN_DETAILS = frozenset({
    "password", "password_hash", "secret", "device_secret",
    "access_token", "refresh_token", "token", "token_hash",
    "backend_url", "minio_endpoint", "private_key",
    "barcode", "receipt", "payment", "fiscal", "card",
    "customer_id", "phone", "file_path", "sha256",
})


def _strip_forbidden(d: dict | None) -> dict | None:
    """Remove forbidden keys from a dict recursively."""
    if d is None:
        return None
    return {
        k: _strip_forbidden(v) if isinstance(v, dict) else v
        for k, v in d.items()
        if k not in FORBIDDEN_DETAILS
        and not any(fb in k.lower() for fb in ("secret", "password", "token", "key"))
    }


async def audit_business_action(
    db: AsyncSession,
    actor_user_id: str,
    action: str,
    target_type: str | None = None,
    target_ref: str | None = None,
    details: dict | None = None,
) -> None:
    """Record a business audit event (fire-and-forget).

    Args:
        db: Async session (caller must commit)
        actor_user_id: User ID who performed the action
        action: Dot-separated action (e.g. "campaign.create", "approval.approve")
        target_type: Domain type (e.g. "campaign", "creative", "approval")
        target_ref: Safe identifier (e.g. campaign_code, creative_code)
        details: Safe details dict (forbidden fields are stripped)
    """
    safe_details = _strip_forbidden(details)
    await record_admin_action(
        db=db,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_ref=target_ref,
        details=safe_details,
    )
