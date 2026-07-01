"""Emergency domain — schemas, contracts, and validation.

G.1: read-only contracts — no API, no migrations, no DB writes,
no real stop, no production switch.
"""

from app.domains.emergency.schemas import (
    EmergencyActionType,
    EmergencyActionStatus,
    EmergencyPriority,
    EmergencyTarget,
    EmergencyMessageContent,
    EmergencyActionCreate,
    EmergencyActionPreview,
    EmergencyActionResult,
    EmergencyActionRecord,
    EmergencyIssue,
)
from app.domains.emergency.service import (
    validate_emergency_action,
    preview_emergency_action,
    resolve_emergency_targets,
    simulate_emergency_stop,
    simulate_emergency_message,
    build_emergency_issue,
    validate_no_secrets_in_emergency_payload,
)

__all__ = [
    "EmergencyActionType",
    "EmergencyActionStatus",
    "EmergencyPriority",
    "EmergencyTarget",
    "EmergencyMessageContent",
    "EmergencyActionCreate",
    "EmergencyActionPreview",
    "EmergencyActionResult",
    "EmergencyActionRecord",
    "EmergencyIssue",
    "validate_emergency_action",
    "preview_emergency_action",
    "resolve_emergency_targets",
    "simulate_emergency_stop",
    "simulate_emergency_message",
    "build_emergency_issue",
    "validate_no_secrets_in_emergency_payload",
]
