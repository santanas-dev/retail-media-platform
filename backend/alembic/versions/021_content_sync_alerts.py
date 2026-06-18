"""Seed new content sync alert rules (idempotent).

Revision ID: 021
Revises: 020
Create Date: 2026-06-17

No table changes — only idempotent seed of 7 default alert rules
for content sync health & alerts integration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_RULES = [
    # Enabled
    ("cache_invalid_hash", "Cache Invalid Hash",
     "Обнаружен media-файл с несовпадающим SHA-256 в кэше устройства",
     "cache_invalid_hash", "critical", True, None, 60, None),
    ("manifest_apply_failed", "Manifest Apply Failed",
     "Устройство не смогло применить манифест",
     "manifest_apply_failed", "warning", True, None, 60, None),
    # Disabled
    ("cache_report_stale", "Cache Report Stale",
     "Устройство давно не присылало отчёт о состоянии media-кэша",
     "cache_report_stale", "warning", False, None, 120, None),
    ("manifest_not_applied", "Manifest Not Applied",
     "Манифест доставлен, но устройство не подтвердило применение",
     "manifest_not_applied", "warning", False, None, 120, None),
    ("cache_missing_high", "Cache Missing Items High",
     "Высокая доля отсутствующих media-файлов в кэше устройства",
     "cache_missing_high", "warning", False, None, 120, None),
    ("cache_failed_high", "Cache Failed Items High",
     "Высокая доля ошибок загрузки media-файлов",
     "cache_failed_high", "warning", False, None, 120, None),
    ("applied_manifest_outdated", "Applied Manifest Outdated",
     "Применённый манифест устройства устарел относительно последнего опубликованного",
     "applied_manifest_outdated", "warning", False, None, 240, None),
]


def upgrade() -> None:
    seed_default_rules()


def downgrade() -> None:
    """Remove seeded content sync rules."""
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM device_alert_rules WHERE code = ANY(:codes)"),
        {"codes": [r[0] for r in DEFAULT_RULES]},
    )


def seed_default_rules() -> None:
    """Idempotent seed of content sync alert rules."""
    import json as _json
    from datetime import timezone as _tz
    from datetime import datetime as _dt

    now = _dt.now(_tz.utc)

    conn = op.get_bind()
    for code, name, desc, atype, sev, en, thresh, win, scope in DEFAULT_RULES:
        threshold_val = _json.loads(thresh) if thresh else None
        scope_val = _json.loads(scope) if scope else None

        conn.execute(
            sa.text("""
                INSERT INTO device_alert_rules
                    (code, name, description, alert_type, severity, enabled,
                     threshold_json, window_minutes, scope_json,
                     created_at, updated_at)
                VALUES
                    (:code, :name, :desc, :atype, :sev, :enabled,
                     :threshold, :win, :scope, :now, :now)
                ON CONFLICT (code) DO NOTHING
            """),
            {
                "code": code, "name": name, "desc": desc,
                "atype": atype, "sev": sev, "enabled": en,
                "threshold": _json.dumps(threshold_val) if threshold_val else None,
                "win": win, "scope": _json.dumps(scope_val) if scope_val else None,
                "now": now,
            },
        )
