"""Reports export — CSV generation with RLS.

Planned (backend-only) reports. No physical KSO, no PoP facts.
All exports require reports.read permission.
RLS: advertiser sees only own data; admin sees full details.
"""

import csv
import io
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_permission
from app.domains.identity import models as identity_models
from app.domains.identity.rls import (
    ADMIN_ROLE_CODES,
    UserScopeContext,
    resolve_user_scope_context,
)
from app.domains.campaigns.models import Campaign
from app.domains.publications.models import PublicationBatch
from app.domains.scheduling.models import KsoPlacement
from app.domains.hierarchy.models import KsoDevice


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_admin(user: identity_models.User) -> bool:
    """Check if user has admin-level role (system_admin or security_admin)."""
    role_codes = user.roles  # property returning list[str]
    return bool(ADMIN_ROLE_CODES & set(role_codes))


def _safe_csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    """Generate safe CSV streaming response."""
    if not rows:
        output = io.StringIO()
        output.write("no_data\n")
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Campaign Export ──────────────────────────────────────────────────────────

async def export_campaigns_csv(
    db: AsyncSession,
    current_user: identity_models.User,
    ctx: UserScopeContext,
) -> StreamingResponse:
    """Export campaigns as CSV with RLS."""
    query = select(Campaign)

    if not ctx.is_admin and ctx.is_advertiser_scoped:
        query = query.where(Campaign.advertiser_id.in_(ctx.advertiser_ids))

    result = await db.execute(query)
    campaigns = result.scalars().all()

    rows = []
    for c in campaigns:
        row = {
            "campaign_code": c.campaign_code or "",
            "name": c.name or "",
            "status": c.status or "",
            "planned_start": str(c.planned_start_date) if c.planned_start_date else "",
            "planned_end": str(c.planned_end_date) if c.planned_end_date else "",
            "created_at": str(c.created_at) if c.created_at else "",
        }
        # Admin-only fields
        if ctx.is_admin:
            row["advertiser_id"] = str(c.advertiser_id) if c.advertiser_id else ""
        rows.append(row)

    return _safe_csv_response(rows, "campaigns_export.csv")


# ── Airtime Occupancy Export ─────────────────────────────────────────────────

async def export_airtime_csv(
    db: AsyncSession,
    current_user: identity_models.User,
    ctx: UserScopeContext,
    device_codes: list[str],
) -> StreamingResponse:
    """Export planned airtime occupancy as CSV."""
    from app.domains.airtime.service import calculate_occupancy as calc_occ

    rows = []
    for dc in device_codes:
        # RLS: advertiser can only query devices in their scope
        if not ctx.is_admin and ctx.device_codes and dc not in ctx.device_codes:
            continue

        dev_result = await db.execute(
            select(KsoDevice).where(KsoDevice.device_code == dc)
        )
        if not dev_result.scalar_one_or_none():
            continue

        occ = await calc_occ(
            db,
            device_code=dc,
            date_from=date(2025, 1, 1),
            date_to=date(2030, 12, 31),
        )

        rows.append({
            "device_code": dc if ctx.is_admin else "***",
            "total_available_minutes": occ.get("total_available_minutes", 0),
            "occupied_minutes": occ.get("occupied_minutes", 0),
            "free_minutes": occ.get("free_minutes", 0),
            "occupancy_percent": occ.get("occupancy_percent", 0),
            "campaign_count": occ.get("campaign_count", 0),
            "creative_count": occ.get("creative_count", 0),
            "is_planned": "TRUE",
        })

    return _safe_csv_response(rows, "airtime_occupancy_export.csv")


# ── Conflicts Export ─────────────────────────────────────────────────────────

async def export_conflicts_csv(
    db: AsyncSession,
    current_user: identity_models.User,
    ctx: UserScopeContext,
    device_codes: list[str],
) -> StreamingResponse:
    """Export schedule conflicts as CSV with RLS anonymization."""
    from app.domains.airtime.service import detect_conflicts

    all_conflicts = []
    for dc in device_codes:
        if not ctx.is_admin and ctx.device_codes and dc not in ctx.device_codes:
            continue

        dev_result = await db.execute(
            select(KsoDevice).where(KsoDevice.device_code == dc)
        )
        if not dev_result.scalar_one_or_none():
            continue

        conflicts = await detect_conflicts(
            db,
            device_code=dc,
            date_from=date(2025, 1, 1),
            date_to=date(2030, 12, 31),
            is_admin=ctx.is_admin,
        )
        for c in conflicts:
            c["device_code"] = dc
        all_conflicts.extend(conflicts)

    rows = []
    for c in all_conflicts:
        row = {
            "device_code": c.get("device_code", ""),
            "campaign_code": c.get("campaign_code", ""),
            "campaign_name": c.get("campaign_name", ""),
            "conflict_with_code": c.get("conflict_with_code", ""),
            "date_from": c.get("date_from", ""),
            "date_to": c.get("date_to", ""),
            "day_of_week": c.get("day_of_week", ""),
            "day_label": c.get("day_label", ""),
            "time_window": c.get("time_window", ""),
            "conflict_time_window": c.get("conflict_time_window", ""),
            "severity": c.get("severity", "warning"),
        }
        if ctx.is_admin:
            row["conflict_campaign_name"] = c.get("conflict_campaign_name", "")
        rows.append(row)

    return _safe_csv_response(rows, "conflicts_export.csv")


# ── Publication Batches Export ───────────────────────────────────────────────

async def export_publications_csv(
    db: AsyncSession,
    current_user: identity_models.User,
    ctx: UserScopeContext,
) -> StreamingResponse:
    """Export publication batches as CSV with RLS."""
    query = select(PublicationBatch)

    if not ctx.is_admin and ctx.is_advertiser_scoped:
        query = query.join(
            Campaign,
            PublicationBatch.campaign_id == Campaign.id,
        ).where(Campaign.advertiser_id.in_(ctx.advertiser_ids))

    result = await db.execute(query)
    batches = result.unique().scalars().all()

    rows = []
    for b in batches:
        row = {
            "status": b.status or "",
            "created_at": str(b.created_at) if b.created_at else "",
            "updated_at": str(b.updated_at) if b.updated_at else "",
        }
        if ctx.is_admin:
            row["batch_id"] = str(b.id) if b.id else ""
            row["campaign_id"] = str(b.campaign_id) if b.campaign_id else ""
            row["schedule_run_id"] = str(b.schedule_run_id) if b.schedule_run_id else ""
        rows.append(row)

    return _safe_csv_response(rows, "publication_batches_export.csv")
