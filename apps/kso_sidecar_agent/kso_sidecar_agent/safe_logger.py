"""Minimal safe logger — JSON Lines to stdout.

Forbidden substrings cause the message to be replaced with [REDACTED].
Never logs: token, jwt, password, secret, api_key, private_key,
payment_card, receipt.
"""

import json
import sys
from datetime import datetime, timezone
from typing import Optional

FORBIDDEN_SUBSTRINGS = [
    "token", "jwt", "password", "secret",
    "api_key", "private_key", "payment_card", "receipt",
]


def _clean(message: str) -> str:
    """Return [REDACTED] if message contains any forbidden substring."""
    lower = message.lower()
    for forbidden in FORBIDDEN_SUBSTRINGS:
        if forbidden in lower:
            return "[REDACTED]"
    return message


def log(
    *,
    level: str = "info",
    event: str = "",
    message: str = "",
    extra: Optional[dict] = None,
) -> None:
    """Emit one JSON Lines log record to stdout.

    Required fields: timestamp, level, event, message.
    Forbidden substrings in *message* are replaced with [REDACTED].
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        "message": _clean(message),
    }
    if extra:
        record.update(extra)

    print(json.dumps(record, ensure_ascii=False, separators=(",", ":")),
          file=sys.stdout, flush=True)
