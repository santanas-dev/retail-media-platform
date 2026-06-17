"""Device Operations: delivery health computation from audit tables."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.device_gateway import models as gw_models
from app.domains.channels.models import Channel
from app.domains.organization.models import Store
from app.domains.device_operations import models as do_models

HEALTH_STATUSES = frozenset({
    "healthy", "warning", "critical", "offline", "disabled",
})

PROBLEM_TYPES = frozenset({
    "no_heartbeat", "no_manifest", "no_media", "no_pop",
    "manifest_validation_failed", "media_validation_failed",
    "media_storage_error", "pop_rejected_high", "duplicate_events_high",
    "batch_rejected", "disabled_device", "retired_device",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_period(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[datetime, datetime]:
    settings = get_settings()
    now = _now()
    end = date_to or now
    start = date_from or (end - timedelta(hours=settings.DEVICE_HEALTH_DEFAULT_PERIOD_HOURS))
    return start, end


def _validate_period(start: datetime, end: datetime) -> None:
    settings = get_settings()
    if start > end:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")
    max_days = settings.DEVICE_HEALTH_MAX_PERIOD_DAYS
    if (end - start).days > max_days:
        raise HTTPException(
            status_code=400,
            detail=f"Period cannot exceed {max_days} days",
        )


def _compute_health_status(
    device_status: str,
    has_heartbeat: bool,
    has_manifest: bool,
    has_media: bool,
    has_pop: bool,
    error_rate: float,
    minutes_since_activity: float | None,
) -> str:
    settings = get_settings()

    # disabled / retired
    if device_status in ("disabled", "retired"):
        return "disabled"

    # offline — no activity beyond threshold
    if minutes_since_activity is not None and minutes_since_activity > settings.DEVICE_HEALTH_OFFLINE_MINUTES:
        return "offline"

    # critical — high error rate
    if error_rate >= settings.DEVICE_HEALTH_ERROR_RATE_CRITICAL:
        return "critical"

    # warning — missing pipeline stages or moderate errors
    if not has_manifest and has_heartbeat:
        return "warning"
    if not has_media and has_manifest:
        return "warning"
    if not has_pop and has_media:
        return "warning"
    if error_rate >= settings.DEVICE_HEALTH_ERROR_RATE_WARNING:
        return "warning"

    return "healthy"


def _compute_problem_types(
    device_status: str,
    has_heartbeat: bool,
    has_manifest: bool,
    has_media: bool,
    has_pop: bool,
    has_manifest_validation_failed: bool,
    has_media_validation_failed: bool,
    has_media_storage_error: bool,
    pop_rejected_ratio: float,
    duplicate_ratio: float,
    has_batch_rejected: bool,
) -> list[str]:
    problems: list[str] = []

    if device_status == "disabled":
        problems.append("disabled_device")
    if device_status == "retired":
        problems.append("retired_device")
    if not has_heartbeat:
        problems.append("no_heartbeat")
    if not has_manifest:
        problems.append("no_manifest")
    if not has_media and has_manifest:
        problems.append("no_media")
    if not has_pop and has_media:
        problems.append("no_pop")
    if has_manifest_validation_failed:
        problems.append("manifest_validation_failed")
    if has_media_validation_failed:
        problems.append("media_validation_failed")
    if has_media_storage_error:
        problems.append("media_storage_error")
    if pop_rejected_ratio > 0.3:
        problems.append("pop_rejected_high")
    if duplicate_ratio > 0.3:
        problems.append("duplicate_events_high")
    if has_batch_rejected:
        problems.append("batch_rejected")

    return problems


# ── Bulk activity aggregates ───────────────────────────────────────


async def _fetch_device_aggregates(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    *,
    channel_id: UUID | None = None,
    store_id: UUID | None = None,
) -> dict[UUID, dict[str, Any]]:
    """One bulk query returning per-device activity aggregates."""
    # Pre-fetch store/channel info
    store_map: dict[UUID, dict] = {}
    chan_map: dict[UUID, dict] = {}

    stores = (await db.execute(select(Store))).scalars().all()
    for s in stores:
        store_map[s.id] = {"code": s.code, "name": s.name}

    channels = (await db.execute(select(Channel))).scalars().all()
    for ch in channels:
        chan_map[ch.id] = {"code": ch.code, "name": ch.name}

    # Build device list
    dev_cond = []
    if channel_id:
        dev_cond.append(f"gd.channel_id = '{channel_id}'")
    if store_id:
        dev_cond.append(f"gd.store_id = '{store_id}'")
    dev_where = " AND ".join(dev_cond) if dev_cond else "TRUE"

    # Single massive query with CTEs for each metric
    q = text(f"""
    WITH devices AS (
        SELECT gd.id, gd.device_code, gd.device_name, gd.status,
               gd.channel_id, gd.store_id, gd.last_seen_at
        FROM gateway_devices gd
        WHERE {dev_where}
    ),
    -- Most devices don't have display_surface_id; include all
    heartbeat_agg AS (
        SELECT gateway_device_id, max(created_at) as last_hb, count(*) as hb_count
        FROM device_heartbeats
        WHERE created_at >= :start AND created_at <= :end
        GROUP BY gateway_device_id
    ),
    manifest_agg AS (
        SELECT gateway_device_id,
               max(created_at) as last_mr,
               count(*) as mr_total,
               count(*) FILTER (WHERE request_status = 'validation_failed') as mr_validation_failed
        FROM device_manifest_requests
        WHERE created_at >= :start AND created_at <= :end
        GROUP BY gateway_device_id
    ),
    media_agg AS (
        SELECT gateway_device_id,
               max(created_at) as last_med,
               count(*) as med_total,
               count(*) FILTER (WHERE request_status = 'validation_failed') as med_validation_failed,
               count(*) FILTER (WHERE request_status = 'storage_error') as med_storage_error
        FROM device_media_requests
        WHERE created_at >= :start AND created_at <= :end
        GROUP BY gateway_device_id
    ),
    pop_agg AS (
        SELECT gateway_device_id,
               max(created_at) as last_pop,
               count(*) as pop_total,
               count(*) FILTER (WHERE validation_status = 'rejected') as pop_rejected,
               count(*) FILTER (WHERE validation_status = 'duplicate') as pop_duplicate
        FROM proof_of_play_events
        WHERE created_at >= :start AND created_at <= :end
        GROUP BY gateway_device_id
    ),
    batch_agg AS (
        SELECT gateway_device_id,
               count(*) FILTER (WHERE batch_status = 'rejected') as batch_rejected
        FROM proof_of_play_batches
        WHERE created_at >= :start AND created_at <= :end
        GROUP BY gateway_device_id
    ),
    device_event_agg AS (
        SELECT gateway_device_id,
               max(created_at) as last_ev
        FROM device_events
        WHERE created_at >= :start AND created_at <= :end
        GROUP BY gateway_device_id
    )
    SELECT
        d.id as device_id, d.device_code, d.device_name, d.status as device_status,
        d.channel_id, d.store_id, d.last_seen_at,
        h.last_hb as last_heartbeat_at, COALESCE(h.hb_count, 0) as hb_count,
        m.last_mr as last_manifest_request_at, COALESCE(m.mr_total, 0) as mr_total,
        COALESCE(m.mr_validation_failed, 0) as mr_validation_failed,
        med.last_med as last_media_request_at, COALESCE(med.med_total, 0) as med_total,
        COALESCE(med.med_validation_failed, 0) as med_validation_failed,
        COALESCE(med.med_storage_error, 0) as med_storage_error,
        p.last_pop as last_pop_event_at, COALESCE(p.pop_total, 0) as pop_total,
        COALESCE(p.pop_rejected, 0) as pop_rejected,
        COALESCE(p.pop_duplicate, 0) as pop_duplicate,
        COALESCE(b.batch_rejected, 0) as batch_rejected,
        e.last_ev as last_device_event_at
    FROM devices d
    LEFT JOIN heartbeat_agg h ON h.gateway_device_id = d.id
    LEFT JOIN manifest_agg m ON m.gateway_device_id = d.id
    LEFT JOIN media_agg med ON med.gateway_device_id = d.id
    LEFT JOIN pop_agg p ON p.gateway_device_id = d.id
    LEFT JOIN batch_agg b ON b.gateway_device_id = d.id
    LEFT JOIN device_event_agg e ON e.gateway_device_id = d.id
    """)

    result = await db.execute(q, {"start": start, "end": end})
    rows = result.mappings().all()

    aggregates: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        did = row["device_id"]
        # Compute last_activity_at
        activity_times = [
            row["last_seen_at"],
            row["last_heartbeat_at"],
            row["last_manifest_request_at"],
            row["last_media_request_at"],
            row["last_pop_event_at"],
            row["last_device_event_at"],
        ]
        last_activity = max((t for t in activity_times if t is not None), default=None)
        mins_since = None
        if last_activity:
            mins_since = (_now() - last_activity).total_seconds() / 60.0

        has_hb = (row["hb_count"] or 0) > 0
        has_mr = (row["mr_total"] or 0) > 0
        has_med = (row["med_total"] or 0) > 0
        has_pop = (row["pop_total"] or 0) > 0

        total_activity = (row["mr_total"] or 0) + (row["med_total"] or 0) + (row["pop_total"] or 0)
        error_count = (
            (row["mr_validation_failed"] or 0) +
            (row["med_validation_failed"] or 0) +
            (row["med_storage_error"] or 0)
        )
        error_rate = error_count / max(total_activity, 1) if total_activity > 0 else 0.0
        pop_rejected_ratio = (row["pop_rejected"] or 0) / max(row["pop_total"] or 1, 1)
        duplicate_ratio = (row["pop_duplicate"] or 0) / max(row["pop_total"] or 1, 1)

        health = _compute_health_status(
            row["device_status"], has_hb, has_mr, has_med, has_pop, error_rate, mins_since,
        )
        problems = _compute_problem_types(
            row["device_status"], has_hb, has_mr, has_med, has_pop,
            (row["mr_validation_failed"] or 0) > 0,
            (row["med_validation_failed"] or 0) > 0,
            (row["med_storage_error"] or 0) > 0,
            pop_rejected_ratio, duplicate_ratio,
            (row["batch_rejected"] or 0) > 0,
        )

        si = store_map.get(row["store_id"]) if row["store_id"] else None
        ci = chan_map.get(row["channel_id"]) if row["channel_id"] else None

        aggregates[did] = {
            "device_id": did,
            "device_code": row["device_code"],
            "device_name": row["device_name"],
            "store_id": row["store_id"],
            "store_code": si["code"] if si else None,
            "store_name": si["name"] if si else None,
            "channel_id": row["channel_id"],
            "channel_code": ci["code"] if ci else None,
            "channel_name": ci["name"] if ci else None,
            "device_status": row["device_status"],
            "health_status": health,
            "last_activity_at": last_activity,
            "last_heartbeat_at": row["last_heartbeat_at"],
            "last_manifest_request_at": row["last_manifest_request_at"],
            "last_media_request_at": row["last_media_request_at"],
            "last_pop_event_at": row["last_pop_event_at"],
            "manifest_requests_count": row["mr_total"] or 0,
            "media_requests_count": row["med_total"] or 0,
            "pop_events_count": row["pop_total"] or 0,
            "error_count": error_count,
            "problem_types": problems,
            "_has_hb": has_hb,
            "_has_mr": has_mr,
            "_has_med": has_med,
            "_has_pop": has_pop,
            "_error_rate": error_rate,
            "_mr_vf": (row["mr_validation_failed"] or 0),
            "_med_se": (row["med_storage_error"] or 0),
            "_pop_rej": (row["pop_rejected"] or 0),
            "_batch_rej": (row["batch_rejected"] or 0),
        }

    return aggregates


# ── Public API ─────────────────────────────────────────────────────


async def get_overview(
    db: AsyncSession,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    channel_id: UUID | None = None,
    store_id: UUID | None = None,
) -> dict:
    start, end = _get_period(date_from, date_to)
    _validate_period(start, end)

    aggs = await _fetch_device_aggregates(db, start, end, channel_id=channel_id, store_id=store_id)

    summary = {"total_devices": 0, "healthy": 0, "warning": 0, "critical": 0, "offline": 0, "disabled": 0}
    pipeline = {"heartbeat_devices": 0, "manifest_devices": 0, "media_devices": 0, "pop_devices": 0}
    errors = {"manifest_validation_failed": 0, "media_storage_error": 0, "pop_rejected": 0, "batch_rejected": 0}

    for agg in aggs.values():
        summary["total_devices"] += 1
        summary[agg["health_status"]] += 1
        if agg["_has_hb"]: pipeline["heartbeat_devices"] += 1
        if agg["_has_mr"]: pipeline["manifest_devices"] += 1
        if agg["_has_med"]: pipeline["media_devices"] += 1
        if agg["_has_pop"]: pipeline["pop_devices"] += 1
        errors["manifest_validation_failed"] += agg["_mr_vf"]
        errors["media_storage_error"] += agg["_med_se"]
        errors["pop_rejected"] += agg["_pop_rej"]
        errors["batch_rejected"] += agg["_batch_rej"]

    return {
        "status": "ok",
        "period": {"date_from": start, "date_to": end},
        "summary": summary,
        "pipeline": pipeline,
        "errors": errors,
    }


async def get_devices(
    db: AsyncSession,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    *,
    channel_id: UUID | None = None,
    store_id: UUID | None = None,
    device_status: str | None = None,
    health_status: str | None = None,
    problem_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    start, end = _get_period(date_from, date_to)
    _validate_period(start, end)

    aggs = await _fetch_device_aggregates(db, start, end, channel_id=channel_id, store_id=store_id)

    items = list(aggs.values())

    # Post-filter
    if device_status:
        items = [i for i in items if i["device_status"] == device_status]
    if health_status:
        items = [i for i in items if i["health_status"] == health_status]
    if problem_type:
        items = [i for i in items if problem_type in i["problem_types"]]

    # Sort by device_code for stability
    items.sort(key=lambda i: i["device_code"])

    # Paginate
    total = len(items)
    items = items[offset:offset + limit]

    # Strip internal fields
    result = []
    for item in items:
        result.append({
            "gateway_device_id": item["device_id"],
            "device_code": item["device_code"],
            "device_name": item["device_name"],
            "store_id": item["store_id"],
            "store_code": item["store_code"],
            "store_name": item["store_name"],
            "channel_id": item["channel_id"],
            "channel_code": item["channel_code"],
            "channel_name": item["channel_name"],
            "device_status": item["device_status"],
            "health_status": item["health_status"],
            "last_activity_at": item["last_activity_at"],
            "last_heartbeat_at": item["last_heartbeat_at"],
            "last_manifest_request_at": item["last_manifest_request_at"],
            "last_media_request_at": item["last_media_request_at"],
            "last_pop_event_at": item["last_pop_event_at"],
            "manifest_requests_count": item["manifest_requests_count"],
            "media_requests_count": item["media_requests_count"],
            "pop_events_count": item["pop_events_count"],
            "error_count": item["error_count"],
            "problem_types": item["problem_types"],
            "_total": total,
        })
    return result


async def get_device_detail(
    db: AsyncSession,
    device_id: UUID,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict | None:
    start, end = _get_period(date_from, date_to)
    _validate_period(start, end)

    # Get device aggregate
    aggs = await _fetch_device_aggregates(db, start, end)
    agg = aggs.get(device_id)
    if not agg:
        return None

    device_item = {
        "gateway_device_id": agg["device_id"],
        "device_code": agg["device_code"],
        "device_name": agg["device_name"],
        "store_id": agg["store_id"],
        "store_code": agg["store_code"],
        "store_name": agg["store_name"],
        "channel_id": agg["channel_id"],
        "channel_code": agg["channel_code"],
        "channel_name": agg["channel_name"],
        "device_status": agg["device_status"],
        "health_status": agg["health_status"],
        "last_activity_at": agg["last_activity_at"],
        "last_heartbeat_at": agg["last_heartbeat_at"],
        "last_manifest_request_at": agg["last_manifest_request_at"],
        "last_media_request_at": agg["last_media_request_at"],
        "last_pop_event_at": agg["last_pop_event_at"],
        "manifest_requests_count": agg["manifest_requests_count"],
        "media_requests_count": agg["media_requests_count"],
        "pop_events_count": agg["pop_events_count"],
        "error_count": agg["error_count"],
        "problem_types": agg["problem_types"],
    }

    # Recent events — limited individual queries (only 1 device)
    hb_result = await db.execute(
        select(gw_models.DeviceHeartbeat)
        .where(
            gw_models.DeviceHeartbeat.gateway_device_id == device_id,
            gw_models.DeviceHeartbeat.created_at >= start,
            gw_models.DeviceHeartbeat.created_at <= end,
        )
        .order_by(gw_models.DeviceHeartbeat.created_at.desc())
        .limit(5)
    )
    recent_hb = hb_result.scalars().all()

    mr_result = await db.execute(
        select(gw_models.DeviceManifestRequest)
        .where(
            gw_models.DeviceManifestRequest.gateway_device_id == device_id,
            gw_models.DeviceManifestRequest.created_at >= start,
            gw_models.DeviceManifestRequest.created_at <= end,
        )
        .order_by(gw_models.DeviceManifestRequest.created_at.desc())
        .limit(5)
    )
    recent_mr = mr_result.scalars().all()

    med_result = await db.execute(
        select(gw_models.DeviceMediaRequest)
        .where(
            gw_models.DeviceMediaRequest.gateway_device_id == device_id,
            gw_models.DeviceMediaRequest.created_at >= start,
            gw_models.DeviceMediaRequest.created_at <= end,
        )
        .order_by(gw_models.DeviceMediaRequest.created_at.desc())
        .limit(5)
    )
    recent_med = med_result.scalars().all()

    pop_result = await db.execute(
        select(gw_models.ProofOfPlayEvent)
        .where(
            gw_models.ProofOfPlayEvent.gateway_device_id == device_id,
            gw_models.ProofOfPlayEvent.created_at >= start,
            gw_models.ProofOfPlayEvent.created_at <= end,
        )
        .order_by(gw_models.ProofOfPlayEvent.created_at.desc())
        .limit(5)
    )
    recent_pop = pop_result.scalars().all()

    batch_result = await db.execute(
        select(gw_models.ProofOfPlayBatch)
        .where(
            gw_models.ProofOfPlayBatch.gateway_device_id == device_id,
            gw_models.ProofOfPlayBatch.created_at >= start,
            gw_models.ProofOfPlayBatch.created_at <= end,
        )
        .order_by(gw_models.ProofOfPlayBatch.created_at.desc())
        .limit(3)
    )
    recent_batches = batch_result.scalars().all()

    ev_result = await db.execute(
        select(gw_models.DeviceEvent)
        .where(
            gw_models.DeviceEvent.gateway_device_id == device_id,
            gw_models.DeviceEvent.created_at >= start,
            gw_models.DeviceEvent.created_at <= end,
        )
        .order_by(gw_models.DeviceEvent.created_at.desc())
        .limit(10)
    )
    recent_ev = ev_result.scalars().all()

    return {
        "device": device_item,
        "recent_heartbeats": recent_hb,
        "recent_manifest_requests": recent_mr,
        "recent_media_requests": recent_med,
        "recent_pop_events": recent_pop,
        "recent_pop_batches": recent_batches,
        "recent_device_events": recent_ev,
    }


async def get_stores_health(
    db: AsyncSession,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    *,
    channel_id: UUID | None = None,
    store_id: UUID | None = None,
) -> list[dict]:
    start, end = _get_period(date_from, date_to)
    _validate_period(start, end)

    aggs = await _fetch_device_aggregates(db, start, end, channel_id=channel_id, store_id=store_id)

    # Group by store_id
    store_groups: dict[UUID, dict] = {}
    for agg in aggs.values():
        sid = agg["store_id"]
        if sid is None:
            continue
        if sid not in store_groups:
            store_groups[sid] = {
                "store_id": sid,
                "store_code": agg["store_code"],
                "store_name": agg["store_name"],
                "total_devices": 0,
                "healthy": 0, "warning": 0, "critical": 0, "offline": 0, "disabled": 0,
                "devices_with_manifest": 0, "devices_with_media": 0, "devices_with_pop": 0,
                "error_count": 0,
                "problems": {},
            }
        g = store_groups[sid]
        g["total_devices"] += 1
        g[agg["health_status"]] += 1
        if agg["_has_mr"]: g["devices_with_manifest"] += 1
        if agg["_has_med"]: g["devices_with_media"] += 1
        if agg["_has_pop"]: g["devices_with_pop"] += 1
        g["error_count"] += agg["error_count"]
        for pt in agg["problem_types"]:
            g["problems"][pt] = g["problems"].get(pt, 0) + 1

    result = []
    for sid, g in sorted(store_groups.items(), key=lambda x: x[1].get("store_name", "")):
        top = sorted(g["problems"].items(), key=lambda x: -x[1])[:5]
        result.append({
            "store_id": g["store_id"],
            "store_code": g["store_code"],
            "store_name": g["store_name"],
            "total_devices": g["total_devices"],
            "healthy": g["healthy"],
            "warning": g["warning"],
            "critical": g["critical"],
            "offline": g["offline"],
            "disabled": g["disabled"],
            "devices_with_manifest": g["devices_with_manifest"],
            "devices_with_media": g["devices_with_media"],
            "devices_with_pop": g["devices_with_pop"],
            "error_count": g["error_count"],
            "top_problem_types": [t[0] for t in top],
        })
    return result


async def get_channels_health(
    db: AsyncSession,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    *,
    channel_id: UUID | None = None,
    store_id: UUID | None = None,
) -> list[dict]:
    start, end = _get_period(date_from, date_to)
    _validate_period(start, end)

    aggs = await _fetch_device_aggregates(db, start, end, channel_id=channel_id, store_id=store_id)

    # Group by channel_id
    chan_groups: dict[UUID, dict] = {}
    for agg in aggs.values():
        cid = agg["channel_id"]
        if cid is None:
            continue
        if cid not in chan_groups:
            chan_groups[cid] = {
                "channel_id": cid,
                "channel_code": agg["channel_code"],
                "channel_name": agg["channel_name"],
                "total_devices": 0,
                "healthy": 0, "warning": 0, "critical": 0, "offline": 0, "disabled": 0,
                "devices_with_manifest": 0, "devices_with_media": 0, "devices_with_pop": 0,
                "error_count": 0,
                "problems": {},
            }
        g = chan_groups[cid]
        g["total_devices"] += 1
        g[agg["health_status"]] += 1
        if agg["_has_mr"]: g["devices_with_manifest"] += 1
        if agg["_has_med"]: g["devices_with_media"] += 1
        if agg["_has_pop"]: g["devices_with_pop"] += 1
        g["error_count"] += agg["error_count"]
        for pt in agg["problem_types"]:
            g["problems"][pt] = g["problems"].get(pt, 0) + 1

    result = []
    for cid, g in sorted(chan_groups.items(), key=lambda x: x[1].get("channel_name", "")):
        top = sorted(g["problems"].items(), key=lambda x: -x[1])[:5]
        result.append({
            "channel_id": g["channel_id"],
            "channel_code": g["channel_code"],
            "channel_name": g["channel_name"],
            "total_devices": g["total_devices"],
            "healthy": g["healthy"],
            "warning": g["warning"],
            "critical": g["critical"],
            "offline": g["offline"],
            "disabled": g["disabled"],
            "devices_with_manifest": g["devices_with_manifest"],
            "devices_with_media": g["devices_with_media"],
            "devices_with_pop": g["devices_with_pop"],
            "error_count": g["error_count"],
            "top_problem_types": [t[0] for t in top],
        })
    return result


# ═══════════════════════════════════════════════════════════════════════
#  Step 16 — Alert Rules
# ═══════════════════════════════════════════════════════════════════════

_DEDUP_FMT_DEVICE = "{alert_type}:device:{device_id}"
_DEDUP_FMT_STORE = "{alert_type}:store:{store_id}"
_DEDUP_FMT_CHANNEL = "{alert_type}:channel:{channel_id}"
_DEDUP_FMT_GLOBAL = "{alert_type}:global"


def _build_dedup_key(alert_type: str, device_id=None, store_id=None, channel_id=None) -> str:
    if device_id:
        return _DEDUP_FMT_DEVICE.format(alert_type=alert_type, device_id=device_id)
    if store_id:
        return _DEDUP_FMT_STORE.format(alert_type=alert_type, store_id=store_id)
    if channel_id:
        return _DEDUP_FMT_CHANNEL.format(alert_type=alert_type, channel_id=channel_id)
    return _DEDUP_FMT_GLOBAL.format(alert_type=alert_type)


async def get_alert_rules(db: AsyncSession, enabled_only: bool = False):
    q = select(do_models.DeviceAlertRule).order_by(do_models.DeviceAlertRule.code)
    if enabled_only:
        q = q.where(do_models.DeviceAlertRule.enabled == True)
    result = await db.execute(q)
    return result.scalars().all()


async def create_alert_rule(db: AsyncSession, data: dict) -> do_models.DeviceAlertRule:
    existing = await db.execute(
        select(do_models.DeviceAlertRule.id).where(
            do_models.DeviceAlertRule.code == data["code"]
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Alert rule with code '{data['code']}' already exists",
        )
    rule = do_models.DeviceAlertRule(**data, updated_at=_now(), created_at=_now())
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    await db.commit()
    return rule


async def update_alert_rule(db: AsyncSession, rule_id: UUID, data: dict) -> do_models.DeviceAlertRule:
    rule = await db.get(do_models.DeviceAlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    for field, value in data.items():
        if value is not None:
            setattr(rule, field, value)
    rule.updated_at = _now()
    await db.flush()
    await db.refresh(rule)
    await db.commit()
    return rule


async def set_rule_enabled(db: AsyncSession, rule_id: UUID, enabled: bool) -> do_models.DeviceAlertRule:
    rule = await db.get(do_models.DeviceAlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    rule.enabled = enabled
    rule.updated_at = _now()
    await db.flush()
    await db.refresh(rule)
    await db.commit()
    return rule


async def get_alerts(
    db: AsyncSession,
    status: str = None, severity: str = None, alert_type: str = None,
    gateway_device_id: UUID = None, store_id: UUID = None, channel_id: UUID = None,
    date_from: datetime = None, date_to: datetime = None,
    limit: int = 100, offset: int = 0,
):
    q = select(do_models.DeviceAlert).order_by(do_models.DeviceAlert.last_seen_at.desc())
    if status:
        q = q.where(do_models.DeviceAlert.status == status)
    if severity:
        q = q.where(do_models.DeviceAlert.severity == severity)
    if alert_type:
        q = q.where(do_models.DeviceAlert.alert_type == alert_type)
    if gateway_device_id:
        q = q.where(do_models.DeviceAlert.gateway_device_id == gateway_device_id)
    if store_id:
        q = q.where(do_models.DeviceAlert.store_id == store_id)
    if channel_id:
        q = q.where(do_models.DeviceAlert.channel_id == channel_id)
    if date_from:
        q = q.where(do_models.DeviceAlert.last_seen_at >= date_from)
    if date_to:
        q = q.where(do_models.DeviceAlert.last_seen_at <= date_to)
    q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


async def get_alert_detail(db: AsyncSession, alert_id: UUID):
    alert = await db.get(do_models.DeviceAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    events_q = (
        select(do_models.DeviceAlertEvent)
        .where(do_models.DeviceAlertEvent.alert_id == alert_id)
        .order_by(do_models.DeviceAlertEvent.created_at)
    )
    events_result = await db.execute(events_q)
    return alert, events_result.scalars().all()


async def get_alert_events(db: AsyncSession, alert_id: UUID):
    alert = await db.get(do_models.DeviceAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    q = (
        select(do_models.DeviceAlertEvent)
        .where(do_models.DeviceAlertEvent.alert_id == alert_id)
        .order_by(do_models.DeviceAlertEvent.created_at)
    )
    result = await db.execute(q)
    return result.scalars().all()


async def acknowledge_alert(db: AsyncSession, alert_id: UUID, user_id: UUID, message: str = None) -> do_models.DeviceAlert:
    alert = await db.get(do_models.DeviceAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == "resolved":
        raise HTTPException(status_code=409, detail="Cannot acknowledge a resolved alert")
    if alert.status == "acknowledged":
        return alert
    old_status = alert.status
    alert.status = "acknowledged"
    alert.acknowledged_at = _now()
    alert.acknowledged_by = user_id
    alert.updated_at = _now()
    event = do_models.DeviceAlertEvent(
        alert_id=alert.id, event_type="acknowledged",
        old_status=old_status, new_status="acknowledged",
        user_id=user_id, message=message, created_at=_now(),
    )
    db.add(event)
    await db.flush()
    await db.refresh(alert)
    await db.commit()
    return alert


async def resolve_alert(db: AsyncSession, alert_id: UUID, user_id: UUID, message: str = None) -> do_models.DeviceAlert:
    alert = await db.get(do_models.DeviceAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == "resolved":
        return alert
    old_status = alert.status
    alert.status = "resolved"
    alert.resolved_at = _now()
    alert.resolved_by = user_id
    alert.updated_at = _now()
    event = do_models.DeviceAlertEvent(
        alert_id=alert.id, event_type="resolved",
        old_status=old_status, new_status="resolved",
        user_id=user_id, message=message, created_at=_now(),
    )
    db.add(event)
    await db.flush()
    await db.refresh(alert)
    await db.commit()
    return alert


async def evaluate_alerts(db: AsyncSession) -> dict:
    settings = get_settings()
    rules = await get_alert_rules(db, enabled_only=True)
    counts = {"evaluated_rules": len(rules), "created": 0, "repeated": 0, "reopened": 0, "skipped": 0}

    for rule in rules:
        window = min(rule.window_minutes, settings.DEVICE_HEALTH_MAX_PERIOD_DAYS * 24 * 60)
        scope = rule.scope_json or {}
        device_ids = scope.get("gateway_device_ids") if scope else None

        if rule.alert_type == "device_offline":
            await _evaluate_device_offline(db, rule, window, device_ids, counts)
        elif rule.alert_type == "media_storage_error":
            await _evaluate_error_based(db, rule, window, device_ids, counts, ["storage_error"], "media")
        elif rule.alert_type == "manifest_validation_failed":
            await _evaluate_error_based(db, rule, window, device_ids, counts, ["validation_failed"], "manifest")
        elif rule.alert_type == "media_validation_failed":
            await _evaluate_error_based(db, rule, window, device_ids, counts, ["validation_failed"], "media")
        elif rule.alert_type == "pop_rejected_high":
            t = rule.threshold_json or {}
            await _evaluate_rate_based(db, rule, window, device_ids, counts, "rejected", t.get("min_total", 10), t.get("error_rate", 0.20))
        elif rule.alert_type == "duplicate_events_high":
            t = rule.threshold_json or {}
            await _evaluate_rate_based(db, rule, window, device_ids, counts, "duplicate", t.get("min_total", 10), t.get("duplicate_rate", 0.20))
        elif rule.alert_type == "batch_rejected":
            await _evaluate_batch_rejected(db, rule, window, device_ids, counts)
        elif rule.alert_type in ("no_manifest", "no_media", "no_pop"):
            await _evaluate_missing_pipeline(db, rule, window, device_ids, counts, rule.alert_type)
        else:
            counts["skipped"] += 1

    await db.commit()
    return counts


async def _get_devices_in_scope(db, device_ids, window):
    q = select(gw_models.GatewayDevice.id, gw_models.GatewayDevice.device_code,
               gw_models.GatewayDevice.store_id, gw_models.GatewayDevice.channel_id).where(
        gw_models.GatewayDevice.status.in_(["active", "pending", "lost"]))
    if device_ids:
        q = q.where(gw_models.GatewayDevice.id.in_([UUID(d) for d in device_ids]))
    result = await db.execute(q)
    return result.all()


async def _evaluate_device_offline(db, rule, window, device_ids, counts):
    cutoff = _now() - timedelta(minutes=window)
    devices = await _get_devices_in_scope(db, device_ids, window)
    for dev_id, dev_code, store_id, channel_id in devices:
        sources = []
        dev = await db.get(gw_models.GatewayDevice, dev_id)
        if dev and dev.last_seen_at:
            sources.append(dev.last_seen_at)
        hb = await db.execute(select(func.max(gw_models.DeviceHeartbeat.created_at)).where(
            gw_models.DeviceHeartbeat.gateway_device_id == dev_id))
        hb_ts = hb.scalar()
        if hb_ts:
            sources.append(hb_ts)
        last_activity = max(sources) if sources else None
        if last_activity is None or last_activity < cutoff:
            details = {"device_code": dev_code, "window_minutes": window}
            await _upsert_alert(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                              f"Device {dev_code} is offline", dev_id, store_id, channel_id, details, counts)


async def _evaluate_error_based(db, rule, window, device_ids, counts, event_types, table):
    cutoff = _now() - timedelta(minutes=window)
    model = gw_models.DeviceManifestRequest if table == "manifest" else gw_models.DeviceMediaRequest
    dev_fk = model.gateway_device_id
    status_field = model.request_status
    q = select(dev_fk).where(status_field.in_(event_types), model.created_at >= cutoff).distinct()
    if device_ids:
        q = q.where(dev_fk.in_([UUID(d) for d in device_ids]))
    result = await db.execute(q)
    for (dev_id,) in result.all():
        dev = await db.get(gw_models.GatewayDevice, dev_id)
        dev_code = dev.device_code if dev else "unknown"
        details = {"device_code": dev_code, "window_minutes": window}
        await _upsert_alert(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                          f"{rule.name} on device {dev_code}", dev_id,
                          dev.store_id if dev else None, dev.channel_id if dev else None, details, counts)


async def _evaluate_rate_based(db, rule, window, device_ids, counts, error_field, min_total, rate):
    cutoff = _now() - timedelta(minutes=window)
    devices = await _get_devices_in_scope(db, device_ids, window)
    for dev_id, dev_code, store_id, channel_id in devices:
        total = (await db.execute(select(func.count(gw_models.ProofOfPlayEvent.id)).where(
            gw_models.ProofOfPlayEvent.gateway_device_id == dev_id,
            gw_models.ProofOfPlayEvent.created_at >= cutoff))).scalar() or 0
        if total < min_total:
            continue
        vs = "rejected" if error_field == "rejected" else "duplicate"
        errors = (await db.execute(select(func.count(gw_models.ProofOfPlayEvent.id)).where(
            gw_models.ProofOfPlayEvent.gateway_device_id == dev_id,
            gw_models.ProofOfPlayEvent.validation_status == vs,
            gw_models.ProofOfPlayEvent.created_at >= cutoff))).scalar() or 0
        er = errors / max(total, 1)
        if er >= rate:
            details = {"device_code": dev_code, "errors": errors, "total": total, "error_rate": er, "window_minutes": window}
            await _upsert_alert(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                              f"{rule.name} on device {dev_code} ({errors}/{total} = {er:.0%})",
                              dev_id, store_id, channel_id, details, counts)


async def _evaluate_batch_rejected(db, rule, window, device_ids, counts):
    cutoff = _now() - timedelta(minutes=window)
    q = select(gw_models.ProofOfPlayBatch.gateway_device_id).where(
        gw_models.ProofOfPlayBatch.batch_status == "rejected",
        gw_models.ProofOfPlayBatch.received_at >= cutoff).distinct()
    if device_ids:
        q = q.where(gw_models.ProofOfPlayBatch.gateway_device_id.in_([UUID(d) for d in device_ids]))
    result = await db.execute(q)
    for (dev_id,) in result.all():
        dev = await db.get(gw_models.GatewayDevice, dev_id)
        dev_code = dev.device_code if dev else "unknown"
        details = {"device_code": dev_code, "window_minutes": window}
        await _upsert_alert(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                          f"Rejected batch on device {dev_code}", dev_id,
                          dev.store_id if dev else None, dev.channel_id if dev else None, details, counts)


async def _evaluate_missing_pipeline(db, rule, window, device_ids, counts, stage):
    cutoff = _now() - timedelta(minutes=window)
    devices = await _get_devices_in_scope(db, device_ids, window)
    for dev_id, dev_code, store_id, channel_id in devices:
        if stage == "no_media":
            has_upstream = (await db.execute(select(func.count(gw_models.DeviceManifestRequest.id)).where(
                gw_models.DeviceManifestRequest.gateway_device_id == dev_id,
                gw_models.DeviceManifestRequest.created_at >= cutoff))).scalar() or 0
            if has_upstream == 0:
                continue
        elif stage == "no_pop":
            has_upstream = (await db.execute(select(func.count(gw_models.DeviceMediaRequest.id)).where(
                gw_models.DeviceMediaRequest.gateway_device_id == dev_id,
                gw_models.DeviceMediaRequest.created_at >= cutoff))).scalar() or 0
            if has_upstream == 0:
                continue
        elif stage == "no_manifest":
            continue
        details = {"device_code": dev_code, "window_minutes": window}
        await _upsert_alert(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                          f"{stage.replace('_', ' ').title()} on device {dev_code}",
                          dev_id, store_id, channel_id, details, counts)


async def _upsert_alert(db, rule, dedup_key, title, dev_id, store_id, channel_id, details, counts):
    active_q = select(do_models.DeviceAlert).where(
        do_models.DeviceAlert.dedup_key == dedup_key,
        do_models.DeviceAlert.status.in_(["open", "acknowledged"]))
    active_result = await db.execute(active_q)
    active_alert = active_result.scalar_one_or_none()

    if active_alert:
        active_alert.last_seen_at = _now()
        active_alert.updated_at = _now()
        db.add(do_models.DeviceAlertEvent(
            alert_id=active_alert.id, event_type="repeated",
            old_status=active_alert.status, new_status=active_alert.status,
            message=f"Problem persists on device {details.get('device_code', '?')}",
            details_json=details, created_at=_now()))
        counts["repeated"] += 1
        return

    resolved_q = select(do_models.DeviceAlert).where(
        do_models.DeviceAlert.dedup_key == dedup_key,
        do_models.DeviceAlert.status == "resolved").order_by(
        do_models.DeviceAlert.last_seen_at.desc()).limit(1)
    resolved_result = await db.execute(resolved_q)
    resolved_alert = resolved_result.scalar_one_or_none()

    if resolved_alert:
        resolved_alert.status = "open"
        resolved_alert.last_seen_at = _now()
        resolved_alert.resolved_at = None
        resolved_alert.resolved_by = None
        resolved_alert.acknowledged_at = None
        resolved_alert.acknowledged_by = None
        resolved_alert.updated_at = _now()
        db.add(do_models.DeviceAlertEvent(
            alert_id=resolved_alert.id, event_type="reopened",
            old_status="resolved", new_status="open",
            message=f"Problem reoccurred on device {details.get('device_code', '?')}",
            details_json=details, created_at=_now()))
        counts["reopened"] += 1
        return

    alert = do_models.DeviceAlert(
        rule_id=rule.id, alert_type=rule.alert_type, severity=rule.severity,
        status="open", gateway_device_id=dev_id, store_id=store_id,
        channel_id=channel_id, first_seen_at=_now(), last_seen_at=_now(),
        dedup_key=dedup_key, title=title, message=rule.description,
        details_json=details, created_at=_now(), updated_at=_now())
    db.add(alert)
    await db.flush()
    db.add(do_models.DeviceAlertEvent(
        alert_id=alert.id, event_type="created", old_status=None, new_status="open",
        message=f"Alert created for device {details.get('device_code', '?')}",
        details_json=details, created_at=_now()))
    counts["created"] += 1


# ═══════════════════════════════════════════════════════════════════════
#  Step 17 — Evaluation Run History
# ═══════════════════════════════════════════════════════════════════════

import time as _time_module

_RUN_STATUS_RUNNING = "running"
_RUN_STATUS_COMPLETED = "completed"
_RUN_STATUS_WITH_ERRORS = "completed_with_errors"
_RUN_STATUS_FAILED = "failed"


def _safe_error_message(e: Exception) -> str:
    """Return a generic safe error message — NEVER expose raw exception text."""
    exc_type = type(e).__name__
    if exc_type in ("TypeError", "AttributeError"):
        return "Rule evaluation failed"
    if exc_type == "ValueError":
        return "Invalid rule configuration"
    return "Unexpected evaluation error"


async def evaluate_alerts_with_run(db: AsyncSession, user_id: UUID) -> dict:
    """Run evaluation and record history via evaluation run + rule results."""
    settings = get_settings()

    # Create run
    run = do_models.DeviceAlertEvaluationRun(
        triggered_by=user_id,
        trigger_type="manual",
        status=_RUN_STATUS_RUNNING,
        started_at=_now(),
        created_at=_now(),
    )
    db.add(run)
    await db.flush()
    run_id = run.id

    try:
        return await _do_evaluate(db, run, run_id, settings)
    except Exception as e:
        run.error_message = _safe_error_message(e)
        run.status = _RUN_STATUS_FAILED
        run.finished_at = _now()
        run.duration_ms = int(
            (run.finished_at - run.started_at).total_seconds() * 1000
        )
        await db.commit()
        return {
            "status": "ok",
            "evaluation_run_id": str(run_id),
            "evaluated_rules": 0,
            "created": 0,
            "repeated": 0,
            "reopened": 0,
            "skipped": 0,
            "failed_rules": 0,
        }


async def _do_evaluate(
    db: AsyncSession,
    run: do_models.DeviceAlertEvaluationRun,
    run_id: UUID,
    settings,
) -> dict:
    rules = await get_alert_rules(db, enabled_only=True)
    run.evaluated_rules_count = len(rules)

    counts = {
        "evaluated_rules": len(rules), "created": 0, "repeated": 0,
        "reopened": 0, "skipped": 0, "failed_rules": 0,
    }

    rule_results = []
    per_rule_counts = {}

    for rule in rules:
        rr = do_models.DeviceAlertEvaluationRuleResult(
            run_id=run_id,
            rule_id=rule.id,
            rule_code=rule.code,
            alert_type=rule.alert_type,
            status="completed",
            created_at=_now(),
        )
        db.add(rr)
        await db.flush()

        per_counts = {
            "created": 0, "repeated": 0, "reopened": 0, "skipped": 0,
        }

        try:
            window = min(rule.window_minutes, settings.DEVICE_HEALTH_MAX_PERIOD_DAYS * 24 * 60)
            scope = rule.scope_json or {}
            device_ids = scope.get("gateway_device_ids") if scope else None

            if rule.alert_type == "device_offline":
                await _evaluate_device_offline_v2(db, rule, window, device_ids, per_counts, run_id)
            elif rule.alert_type == "media_storage_error":
                await _evaluate_error_based_v2(db, rule, window, device_ids, per_counts, ["storage_error"], "media", run_id)
            elif rule.alert_type == "manifest_validation_failed":
                await _evaluate_error_based_v2(db, rule, window, device_ids, per_counts, ["validation_failed"], "manifest", run_id)
            elif rule.alert_type == "media_validation_failed":
                await _evaluate_error_based_v2(db, rule, window, device_ids, per_counts, ["validation_failed"], "media", run_id)
            elif rule.alert_type == "pop_rejected_high":
                t = rule.threshold_json or {}
                await _evaluate_rate_based_v2(db, rule, window, device_ids, per_counts, "rejected", t.get("min_total", 10), t.get("error_rate", 0.20), run_id)
            elif rule.alert_type == "duplicate_events_high":
                t = rule.threshold_json or {}
                await _evaluate_rate_based_v2(db, rule, window, device_ids, per_counts, "duplicate", t.get("min_total", 10), t.get("duplicate_rate", 0.20), run_id)
            elif rule.alert_type == "batch_rejected":
                await _evaluate_batch_rejected_v2(db, rule, window, device_ids, per_counts, run_id)
            elif rule.alert_type in ("no_manifest", "no_media", "no_pop"):
                await _evaluate_missing_pipeline_v2(db, rule, window, device_ids, per_counts, rule.alert_type, run_id)
            else:
                per_counts["skipped"] += 1
                rr.status = "skipped"

            rr.status = "completed" if rr.status != "skipped" else "skipped"

        except Exception as e:
            rr.status = "failed"
            rr.error_message = _safe_error_message(e)
            counts["failed_rules"] += 1

        rr.created_count = per_counts["created"]
        rr.repeated_count = per_counts["repeated"]
        rr.reopened_count = per_counts["reopened"]
        rr.skipped_count = per_counts["skipped"]

        counts["created"] += per_counts["created"]
        counts["repeated"] += per_counts["repeated"]
        counts["reopened"] += per_counts["reopened"]
        counts["skipped"] += per_counts["skipped"]

    # Finalize run
    run.created_count = counts["created"]
    run.repeated_count = counts["repeated"]
    run.reopened_count = counts["reopened"]
    run.skipped_count = counts["skipped"]
    run.failed_rules_count = counts["failed_rules"]
    run.finished_at = _now()
    run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)

    if counts["failed_rules"] == 0:
        run.status = _RUN_STATUS_COMPLETED
    elif counts["failed_rules"] < len(rules):
        run.status = _RUN_STATUS_WITH_ERRORS
    else:
        run.status = _RUN_STATUS_FAILED

    await db.commit()

    return {
        "status": "ok",
        "evaluation_run_id": str(run_id),
        "evaluated_rules": counts["evaluated_rules"],
        "created": counts["created"],
        "repeated": counts["repeated"],
        "reopened": counts["reopened"],
        "skipped": counts["skipped"],
        "failed_rules": counts["failed_rules"],
    }


# ── Updated _upsert_alert (with run_id) ─────────────────────────────


async def _upsert_alert_v2(db, rule, dedup_key, title, dev_id, store_id, channel_id, details, counts, run_id=None):
    active_q = select(do_models.DeviceAlert).where(
        do_models.DeviceAlert.dedup_key == dedup_key,
        do_models.DeviceAlert.status.in_(["open", "acknowledged"]))
    active_result = await db.execute(active_q)
    active_alert = active_result.scalar_one_or_none()

    if active_alert:
        active_alert.last_seen_at = _now()
        active_alert.updated_at = _now()
        db.add(do_models.DeviceAlertEvent(
            alert_id=active_alert.id, event_type="repeated",
            old_status=active_alert.status, new_status=active_alert.status,
            message=f"Problem persists on device {details.get('device_code', '?')}",
            details_json=details, created_at=_now(),
            evaluation_run_id=run_id))
        counts["repeated"] += 1
        return

    resolved_q = select(do_models.DeviceAlert).where(
        do_models.DeviceAlert.dedup_key == dedup_key,
        do_models.DeviceAlert.status == "resolved").order_by(
        do_models.DeviceAlert.last_seen_at.desc()).limit(1)
    resolved_result = await db.execute(resolved_q)
    resolved_alert = resolved_result.scalar_one_or_none()

    if resolved_alert:
        resolved_alert.status = "open"
        resolved_alert.last_seen_at = _now()
        resolved_alert.resolved_at = None
        resolved_alert.resolved_by = None
        resolved_alert.acknowledged_at = None
        resolved_alert.acknowledged_by = None
        resolved_alert.updated_at = _now()
        db.add(do_models.DeviceAlertEvent(
            alert_id=resolved_alert.id, event_type="reopened",
            old_status="resolved", new_status="open",
            message=f"Problem reoccurred on device {details.get('device_code', '?')}",
            details_json=details, created_at=_now(),
            evaluation_run_id=run_id))
        counts["reopened"] += 1
        return

    alert = do_models.DeviceAlert(
        rule_id=rule.id, alert_type=rule.alert_type, severity=rule.severity,
        status="open", gateway_device_id=dev_id, store_id=store_id,
        channel_id=channel_id, first_seen_at=_now(), last_seen_at=_now(),
        dedup_key=dedup_key, title=title, message=rule.description,
        details_json=details, created_at=_now(), updated_at=_now())
    db.add(alert)
    await db.flush()
    db.add(do_models.DeviceAlertEvent(
        alert_id=alert.id, event_type="created", old_status=None, new_status="open",
        message=f"Alert created for device {details.get('device_code', '?')}",
        details_json=details, created_at=_now(),
        evaluation_run_id=run_id))
    counts["created"] += 1


# ── Updated evaluate helpers (pass run_id) ──────────────────────────


async def _evaluate_device_offline_v2(db, rule, window, device_ids, counts, run_id):
    cutoff = _now() - timedelta(minutes=window)
    devices = await _get_devices_in_scope(db, device_ids, window)
    for dev_id, dev_code, store_id, channel_id in devices:
        sources = []
        dev = await db.get(gw_models.GatewayDevice, dev_id)
        if dev and dev.last_seen_at:
            sources.append(dev.last_seen_at)
        hb = await db.execute(select(func.max(gw_models.DeviceHeartbeat.created_at)).where(
            gw_models.DeviceHeartbeat.gateway_device_id == dev_id))
        hb_ts = hb.scalar()
        if hb_ts:
            sources.append(hb_ts)
        last_activity = max(sources) if sources else None
        if last_activity is None or last_activity < cutoff:
            details = {"device_code": dev_code, "window_minutes": window}
            await _upsert_alert_v2(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                                 f"Device {dev_code} is offline", dev_id, store_id, channel_id, details, counts, run_id)


async def _evaluate_error_based_v2(db, rule, window, device_ids, counts, event_types, table, run_id):
    cutoff = _now() - timedelta(minutes=window)
    model = gw_models.DeviceManifestRequest if table == "manifest" else gw_models.DeviceMediaRequest
    dev_fk = model.gateway_device_id
    status_field = model.request_status
    q = select(dev_fk).where(status_field.in_(event_types), model.created_at >= cutoff).distinct()
    if device_ids:
        q = q.where(dev_fk.in_([UUID(d) for d in device_ids]))
    result = await db.execute(q)
    for (dev_id,) in result.all():
        dev = await db.get(gw_models.GatewayDevice, dev_id)
        dev_code = dev.device_code if dev else "unknown"
        details = {"device_code": dev_code, "window_minutes": window}
        await _upsert_alert_v2(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                             f"{rule.name} on device {dev_code}", dev_id,
                             dev.store_id if dev else None, dev.channel_id if dev else None, details, counts, run_id)


async def _evaluate_rate_based_v2(db, rule, window, device_ids, counts, error_field, min_total, rate, run_id):
    cutoff = _now() - timedelta(minutes=window)
    devices = await _get_devices_in_scope(db, device_ids, window)
    for dev_id, dev_code, store_id, channel_id in devices:
        total = (await db.execute(select(func.count(gw_models.ProofOfPlayEvent.id)).where(
            gw_models.ProofOfPlayEvent.gateway_device_id == dev_id,
            gw_models.ProofOfPlayEvent.created_at >= cutoff))).scalar() or 0
        if total < min_total:
            continue
        vs = "rejected" if error_field == "rejected" else "duplicate"
        errors = (await db.execute(select(func.count(gw_models.ProofOfPlayEvent.id)).where(
            gw_models.ProofOfPlayEvent.gateway_device_id == dev_id,
            gw_models.ProofOfPlayEvent.validation_status == vs,
            gw_models.ProofOfPlayEvent.created_at >= cutoff))).scalar() or 0
        er = errors / max(total, 1)
        if er >= rate:
            details = {"device_code": dev_code, "errors": errors, "total": total, "error_rate": er, "window_minutes": window}
            await _upsert_alert_v2(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                                 f"{rule.name} on device {dev_code} ({errors}/{total} = {er:.0%})",
                                 dev_id, store_id, channel_id, details, counts, run_id)


async def _evaluate_batch_rejected_v2(db, rule, window, device_ids, counts, run_id):
    cutoff = _now() - timedelta(minutes=window)
    q = select(gw_models.ProofOfPlayBatch.gateway_device_id).where(
        gw_models.ProofOfPlayBatch.batch_status == "rejected",
        gw_models.ProofOfPlayBatch.received_at >= cutoff).distinct()
    if device_ids:
        q = q.where(gw_models.ProofOfPlayBatch.gateway_device_id.in_([UUID(d) for d in device_ids]))
    result = await db.execute(q)
    for (dev_id,) in result.all():
        dev = await db.get(gw_models.GatewayDevice, dev_id)
        dev_code = dev.device_code if dev else "unknown"
        details = {"device_code": dev_code, "window_minutes": window}
        await _upsert_alert_v2(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                             f"Rejected batch on device {dev_code}", dev_id,
                             dev.store_id if dev else None, dev.channel_id if dev else None, details, counts, run_id)


async def _evaluate_missing_pipeline_v2(db, rule, window, device_ids, counts, stage, run_id):
    cutoff = _now() - timedelta(minutes=window)
    devices = await _get_devices_in_scope(db, device_ids, window)
    for dev_id, dev_code, store_id, channel_id in devices:
        if stage == "no_media":
            has_upstream = (await db.execute(select(func.count(gw_models.DeviceManifestRequest.id)).where(
                gw_models.DeviceManifestRequest.gateway_device_id == dev_id,
                gw_models.DeviceManifestRequest.created_at >= cutoff))).scalar() or 0
            if has_upstream == 0:
                continue
        elif stage == "no_pop":
            has_upstream = (await db.execute(select(func.count(gw_models.DeviceMediaRequest.id)).where(
                gw_models.DeviceMediaRequest.gateway_device_id == dev_id,
                gw_models.DeviceMediaRequest.created_at >= cutoff))).scalar() or 0
            if has_upstream == 0:
                continue
        elif stage == "no_manifest":
            continue
        details = {"device_code": dev_code, "window_minutes": window}
        await _upsert_alert_v2(db, rule, _build_dedup_key(rule.alert_type, device_id=dev_id),
                             f"{stage.replace('_', ' ').title()} on device {dev_code}",
                             dev_id, store_id, channel_id, details, counts, run_id)


# ── Patch old functions to delegate to v2 (backward compat) ─────────

_evaluate_device_offline_orig = _evaluate_device_offline
_evaluate_error_based_orig = _evaluate_error_based
_evaluate_rate_based_orig = _evaluate_rate_based
_evaluate_batch_rejected_orig = _evaluate_batch_rejected
_evaluate_missing_pipeline_orig = _evaluate_missing_pipeline
_upsert_alert_orig = _upsert_alert


# ── Evaluation Run History queries ───────────────────────────────────


async def get_evaluation_runs(
    db: AsyncSession,
    status: str = None,
    trigger_type: str = None,
    triggered_by: UUID = None,
    date_from: datetime = None,
    date_to: datetime = None,
    limit: int = 100,
    offset: int = 0,
):
    q = select(do_models.DeviceAlertEvaluationRun).order_by(
        do_models.DeviceAlertEvaluationRun.started_at.desc())
    if status:
        q = q.where(do_models.DeviceAlertEvaluationRun.status == status)
    if trigger_type:
        q = q.where(do_models.DeviceAlertEvaluationRun.trigger_type == trigger_type)
    if triggered_by:
        q = q.where(do_models.DeviceAlertEvaluationRun.triggered_by == triggered_by)
    if date_from:
        q = q.where(do_models.DeviceAlertEvaluationRun.started_at >= date_from)
    if date_to:
        q = q.where(do_models.DeviceAlertEvaluationRun.started_at <= date_to)
    q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


async def get_evaluation_run_detail(db: AsyncSession, run_id: UUID):
    run = await db.get(do_models.DeviceAlertEvaluationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    rules_q = (
        select(do_models.DeviceAlertEvaluationRuleResult)
        .where(do_models.DeviceAlertEvaluationRuleResult.run_id == run_id)
        .order_by(do_models.DeviceAlertEvaluationRuleResult.created_at)
    )
    rules_result = await db.execute(rules_q)
    return run, rules_result.scalars().all()


async def get_evaluation_run_rules(db: AsyncSession, run_id: UUID):
    run = await db.get(do_models.DeviceAlertEvaluationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    q = (
        select(do_models.DeviceAlertEvaluationRuleResult)
        .where(do_models.DeviceAlertEvaluationRuleResult.run_id == run_id)
        .order_by(do_models.DeviceAlertEvaluationRuleResult.created_at)
    )
    result = await db.execute(q)
    return result.scalars().all()
