"""Campaign Delivery Reporting Core: CTE-based aggregation service."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.campaign_reports import schemas
from app.domains.campaign_reports.models import CampaignDeliverySnapshot


# ── Helpers ───────────────────────────────────────────────────────

def _rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _delivery_status(
    published_targets: int,
    published_devices: int,
    manifest_applied: int,
    manifest_failed: int,
    cache_ready: int,
    cache_invalid_hash: int,
    pop_devices: int,
    period_ended: bool,
) -> str:
    if published_targets == 0:
        if pop_devices > 0:
            # PoP exists but no published targets — delivery in progress
            if manifest_failed > 0 or cache_invalid_hash > 0:
                return "delivery_with_errors"
            return "delivering"
        return "not_started"
    if manifest_applied == 0 and published_targets > 0:
        if period_ended:
            return "failed"
        return "publishing"
    if manifest_failed > 0 or cache_invalid_hash > 0:
        return "delivery_with_errors"
    if manifest_applied > 0 and pop_devices > 0:
        if manifest_applied >= published_devices and cache_ready >= published_devices:
            return "delivered"
        if pop_devices < published_devices:
            return "partially_delivered"
        return "delivering"
    if manifest_applied > 0:
        return "publishing"
    return "not_started"


def _risk_status(devices_critical: int, devices_warning: int) -> str:
    if devices_critical > 0:
        return "critical"
    if devices_warning > 0:
        return "warning"
    return "ok"


# ── Raw SQL aggregation (one query for summary) ──────────────────

_SUMMARY_SQL = """
WITH campaign_base AS (
    SELECT id, name, status, planned_start_date, planned_end_date
    FROM campaigns WHERE id = :campaign_id
),
period AS (
    SELECT
        COALESCE(:date_from, (SELECT planned_start_date::timestamptz FROM campaign_base)) AS df,
        COALESCE(:date_to, (SELECT planned_end_date::timestamptz + interval '1 day' - interval '1 microsecond'
                  FROM campaign_base)) AS dt
),
planned AS (
    SELECT
        COUNT(DISTINCT ct.store_id)::int AS planned_stores,
        COUNT(DISTINCT gd.id)::int AS planned_devices
    FROM campaign_targets ct
    LEFT JOIN gateway_devices gd ON gd.store_id = ct.store_id
    WHERE ct.campaign_id = :campaign_id
),
published AS (
    SELECT
        COUNT(DISTINCT pt.id)::int AS published_targets,
        COUNT(DISTINCT gd.id)::int AS published_devices
    FROM publication_batches pb
    JOIN publication_targets pt ON pt.publication_batch_id = pb.id
    LEFT JOIN gateway_devices gd ON gd.channel_id = pt.channel_id
        AND gd.store_id = pt.store_id
    WHERE pb.campaign_id = :campaign_id AND pb.status = 'published'
),
manifest_sync AS (
    SELECT
        COUNT(DISTINCT dcms.gateway_device_id)::int AS manifest_available,
        COUNT(DISTINCT CASE WHEN dcms.status = 'applied'
            THEN dcms.gateway_device_id END)::int AS manifest_applied,
        COUNT(DISTINCT CASE WHEN dcms.status = 'failed'
            THEN dcms.gateway_device_id END)::int AS manifest_failed
    FROM device_current_manifest_states dcms
    JOIN manifest_versions mv ON mv.id = dcms.manifest_version_id
    JOIN publication_targets pt ON pt.id = mv.publication_target_id
    JOIN publication_batches pb ON pb.id = pt.publication_batch_id
    WHERE pb.campaign_id = :campaign_id
),
cache_items AS (
    SELECT
        dmci.gateway_device_id,
        MAX(CASE WHEN dmci.status = 'cached' THEN 1 ELSE 0 END) AS has_cached,
        MAX(CASE WHEN dmci.status = 'missing' THEN 1 ELSE 0 END) AS has_missing,
        MAX(CASE WHEN dmci.status = 'failed' THEN 1 ELSE 0 END) AS has_failed,
        MAX(CASE WHEN dmci.status = 'invalid_hash' THEN 1 ELSE 0 END) AS has_invalid
    FROM device_media_cache_items dmci
    JOIN manifest_items mi ON mi.id = dmci.manifest_item_id
    JOIN manifest_versions mv ON mv.id = mi.manifest_version_id
    JOIN publication_targets pt ON pt.id = mv.publication_target_id
    JOIN publication_batches pb ON pb.id = pt.publication_batch_id
    WHERE pb.campaign_id = :campaign_id
    GROUP BY dmci.gateway_device_id
),
cache_summary AS (
    SELECT
        COUNT(*)::int AS cache_total,
        COUNT(*) FILTER (WHERE has_cached = 1)::int AS cache_cached,
        COUNT(*) FILTER (WHERE has_missing = 1)::int AS cache_missing,
        COUNT(*) FILTER (WHERE has_failed = 1)::int AS cache_failed,
        COUNT(*) FILTER (WHERE has_invalid = 1)::int AS cache_invalid,
        COUNT(*) FILTER (WHERE has_cached = 1 AND has_failed = 0
                         AND has_invalid = 0)::int AS cache_ready
    FROM cache_items
),
pop_agg AS (
    SELECT
        COUNT(*)::int AS actual_play_count,
        COUNT(DISTINCT gateway_device_id)::int AS unique_devices_with_pop,
        COUNT(DISTINCT gd.store_id)::int AS unique_stores_with_pop,
        MAX(poe.played_at) AS last_pop_at
    FROM proof_of_play_events poe
    JOIN gateway_devices gd ON gd.id = poe.gateway_device_id
    CROSS JOIN period p
    WHERE poe.campaign_id = :campaign_id
      AND poe.played_at >= p.df AND poe.played_at <= p.dt
),
delivery_health AS (
    SELECT
        COUNT(*) FILTER (WHERE gd.last_seen_at IS NOT NULL
                         AND gd.disabled_at IS NULL)::int AS devices_ok,
        COUNT(*) FILTER (WHERE gd.last_seen_at IS NULL
                         AND gd.disabled_at IS NULL)::int AS devices_warning,
        COUNT(*) FILTER (WHERE gd.disabled_at IS NOT NULL)::int AS devices_critical
    FROM gateway_devices gd
    WHERE gd.id IN (
        SELECT DISTINCT gd2.id FROM gateway_devices gd2
        JOIN publication_targets pt ON pt.channel_id = gd2.channel_id
            AND pt.store_id = gd2.store_id
        JOIN publication_batches pb ON pb.id = pt.publication_batch_id
        WHERE pb.campaign_id = :campaign_id AND pb.status = 'published'
    )
),
store_channels AS (
    SELECT
        COUNT(DISTINCT pt.store_id)::int AS stores_total,
        COUNT(DISTINCT gd.store_id) FILTER (
            WHERE EXISTS (SELECT 1 FROM proof_of_play_events poe2
                          JOIN gateway_devices gd2 ON gd2.id = poe2.gateway_device_id
                          WHERE poe2.campaign_id = :campaign_id
                          AND gd2.store_id = gd.store_id)
        )::int AS stores_with_delivery,
        COUNT(DISTINCT gd.store_id) FILTER (
            WHERE EXISTS (SELECT 1 FROM device_media_cache_items dmci2
                          JOIN manifest_items mi2 ON mi2.id = dmci2.manifest_item_id
                          JOIN manifest_versions mv2 ON mv2.id = mi2.manifest_version_id
                          JOIN publication_targets pt2 ON pt2.id = mv2.publication_target_id
                          JOIN publication_batches pb2 ON pb2.id = pt2.publication_batch_id
                          JOIN gateway_devices gd3 ON gd3.id = dmci2.gateway_device_id
                          WHERE pb2.campaign_id = :campaign_id
                          AND gd3.store_id = gd.store_id
                          AND dmci2.status IN ('invalid_hash','failed'))
        )::int AS stores_with_errors,
        2::int AS channels_total
    FROM publication_targets pt
    JOIN publication_batches pb ON pb.id = pt.publication_batch_id
    LEFT JOIN gateway_devices gd ON gd.channel_id = pt.channel_id
        AND gd.store_id = pt.store_id
    WHERE pb.campaign_id = :campaign_id AND pb.status = 'published'
)
SELECT
    cb.id AS campaign_id, cb.name AS campaign_name,
    cb.status AS campaign_status,
    p.df AS period_from, p.dt AS period_to,
    pl.planned_stores, pl.planned_devices,
    pub.published_targets, pub.published_devices,
    ms.manifest_available, ms.manifest_applied, ms.manifest_failed,
    cs.cache_ready, cs.cache_missing, cs.cache_failed, cs.cache_invalid,
    pa.actual_play_count, pa.unique_devices_with_pop,
    pa.unique_stores_with_pop, pa.last_pop_at,
    dh.devices_ok, dh.devices_warning, dh.devices_critical,
    sc.stores_total, sc.stores_with_delivery,
    sc.stores_with_errors, sc.channels_total
FROM campaign_base cb
CROSS JOIN period p
CROSS JOIN planned pl
CROSS JOIN published pub
CROSS JOIN manifest_sync ms
CROSS JOIN cache_summary cs
CROSS JOIN pop_agg pa
CROSS JOIN delivery_health dh
CROSS JOIN store_channels sc
"""


async def _compute_campaign_report(
    db: AsyncSession,
    campaign_id: UUID,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Optional[dict]:
    """Compute all campaign delivery metrics via one raw SQL query."""
    result = await db.execute(
        text(_SUMMARY_SQL),
        {
            "campaign_id": campaign_id,
            "date_from": date_from,
            "date_to": date_to,
        },
    )
    row = result.one_or_none()
    if row is None:
        return None

    published_targets = row.published_targets or 0
    published_devices = row.published_devices or 0
    manifest_applied = row.manifest_applied or 0
    manifest_failed = row.manifest_failed or 0
    cache_ready = row.cache_ready or 0
    cache_invalid = row.cache_invalid or 0
    pop_devices = row.unique_devices_with_pop or 0
    devices_critical = row.devices_critical or 0
    devices_warning = row.devices_warning or 0
    period_ended = (row.period_to is not None and
                    row.period_to < datetime.now(timezone.utc))

    delivery = _delivery_status(
        published_targets, published_devices,
        manifest_applied, manifest_failed,
        cache_ready, cache_invalid,
        pop_devices, period_ended,
    )
    risk = _risk_status(devices_critical, devices_warning)

    return {
        "campaign_id": row.campaign_id,
        "campaign_name": row.campaign_name,
        "campaign_status": row.campaign_status,
        "period_from": row.period_from,
        "period_to": row.period_to,
        "planned_stores": row.planned_stores or 0,
        "planned_devices": row.planned_devices or 0,
        "published_targets": published_targets,
        "published_devices": published_devices,
        "publication_rate": _rate(published_devices, row.planned_devices or 0),
        "manifest_available_devices": row.manifest_available or 0,
        "manifest_applied_devices": manifest_applied,
        "manifest_failed_devices": manifest_failed,
        "manifest_apply_rate": _rate(manifest_applied, manifest_applied + manifest_failed),
        "cache_ready_devices": cache_ready,
        "cache_missing_devices": row.cache_missing or 0,
        "cache_failed_devices": row.cache_failed or 0,
        "cache_invalid_hash_devices": cache_invalid,
        "actual_play_count": row.actual_play_count or 0,
        "unique_devices_with_pop": pop_devices,
        "unique_stores_with_pop": row.unique_stores_with_pop or 0,
        "last_pop_at": row.last_pop_at,
        "devices_ok": row.devices_ok or 0,
        "devices_warning": devices_warning,
        "devices_critical": devices_critical,
        "delivery_risk_status": risk,
        "delivery_status": delivery,
        "stores_total": row.stores_total or 0,
        "stores_with_delivery": row.stores_with_delivery or 0,
        "stores_with_errors": row.stores_with_errors or 0,
        "channels_total": row.channels_total or 2,
    }


# ── Public API ────────────────────────────────────────────────────

async def get_summary(
    db: AsyncSession, campaign_id: UUID,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Optional[schemas.SummaryResponse]:
    data = await _compute_campaign_report(db, campaign_id, date_from, date_to)
    if data is None:
        return None
    return schemas.SummaryResponse(**data)


async def get_by_store(
    db: AsyncSession, campaign_id: UUID,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list[schemas.StoreReportItem]:
    data = await _compute_campaign_report(db, campaign_id, date_from, date_to)
    if data is None:
        return []

    stores_sql = text("""
        SELECT s.id, s.code, s.name
        FROM stores s
        WHERE s.id IN (
            SELECT DISTINCT pt.store_id
            FROM publication_targets pt
            JOIN publication_batches pb ON pb.id = pt.publication_batch_id
            WHERE pb.campaign_id = :campaign_id AND pb.status = 'published'
            UNION
            SELECT DISTINCT gd.store_id
            FROM gateway_devices gd
            JOIN proof_of_play_events poe ON poe.gateway_device_id = gd.id
            WHERE poe.campaign_id = :campaign_id
        )
    """)
    result = await db.execute(stores_sql, {"campaign_id": campaign_id})
    stores = result.all()

    items = []
    for s in stores:
        items.append(schemas.StoreReportItem(
            store_id=s[0], store_code=s[1], store_name=s[2],
            planned_stores=data["planned_stores"],
            planned_devices=data["planned_devices"],
            published_targets=data["published_targets"],
            published_devices=data["published_devices"],
            publication_rate=data["publication_rate"],
            manifest_available_devices=data["manifest_available_devices"],
            manifest_applied_devices=data["manifest_applied_devices"],
            manifest_failed_devices=data["manifest_failed_devices"],
            manifest_apply_rate=data["manifest_apply_rate"],
            cache_ready_devices=data["cache_ready_devices"],
            cache_missing_devices=data["cache_missing_devices"],
            cache_failed_devices=data["cache_failed_devices"],
            cache_invalid_hash_devices=data["cache_invalid_hash_devices"],
            actual_play_count=data["actual_play_count"],
            unique_devices_with_pop=data["unique_devices_with_pop"],
            unique_stores_with_pop=data["unique_stores_with_pop"],
            last_pop_at=data["last_pop_at"],
            devices_ok=data["devices_ok"],
            devices_warning=data["devices_warning"],
            devices_critical=data["devices_critical"],
            delivery_risk_status=data["delivery_risk_status"],
            delivery_status=data["delivery_status"],
        ))
    return items


async def get_by_channel(
    db: AsyncSession, campaign_id: UUID,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list[schemas.ChannelReportItem]:
    data = await _compute_campaign_report(db, campaign_id, date_from, date_to)
    if data is None:
        return []

    if date_from is None:
        date_from = datetime(2000, 1, 1, tzinfo=timezone.utc)
    if date_to is None:
        date_to = datetime(2099, 12, 31, tzinfo=timezone.utc)

    # Per-channel PoP aggregation via gateway_devices.channel_id
    channel_pop_sql = text("""
        SELECT
            c.id AS channel_id, c.code, c.name,
            COUNT(DISTINCT gd.id)::int AS devices_with_pop,
            COUNT(*)::int AS actual_play_count,
            COUNT(DISTINCT gd.store_id)::int AS stores_with_pop,
            MAX(poe.played_at) AS last_pop_at
        FROM channels c
        JOIN gateway_devices gd ON gd.channel_id = c.id
        JOIN proof_of_play_events poe ON poe.gateway_device_id = gd.id
        WHERE poe.campaign_id = :campaign_id
          AND poe.played_at >= :df AND poe.played_at <= :dt
          AND c.code IN ('android_tv','kso')
        GROUP BY c.id, c.code, c.name
    """)
    result = await db.execute(channel_pop_sql, {
        "campaign_id": campaign_id, "df": date_from, "dt": date_to,
    })
    channel_pop = {row.channel_id: row for row in result.all()}

    channels_sql = text("SELECT id, code, name FROM channels WHERE code IN ('android_tv','kso')")
    result = await db.execute(channels_sql)
    channels = result.all()

    items = []
    for ch in channels:
        ch_id, ch_code, ch_name = ch[0], ch[1], ch[2]
        cp = channel_pop.get(ch_id)
        items.append(schemas.ChannelReportItem(
            channel_id=ch_id, channel_code=ch_code, channel_name=ch_name,
            planned_stores=data["planned_stores"],
            planned_devices=data["planned_devices"],
            published_targets=data["published_targets"],
            published_devices=data["published_devices"],
            publication_rate=data["publication_rate"],
            manifest_available_devices=data["manifest_available_devices"],
            manifest_applied_devices=data["manifest_applied_devices"],
            manifest_failed_devices=data["manifest_failed_devices"],
            manifest_apply_rate=data["manifest_apply_rate"],
            cache_ready_devices=data["cache_ready_devices"],
            cache_missing_devices=data["cache_missing_devices"],
            cache_failed_devices=data["cache_failed_devices"],
            cache_invalid_hash_devices=data["cache_invalid_hash_devices"],
            actual_play_count=cp.actual_play_count if cp else 0,
            unique_devices_with_pop=cp.devices_with_pop if cp else 0,
            unique_stores_with_pop=cp.stores_with_pop if cp else 0,
            last_pop_at=cp.last_pop_at if cp else None,
            devices_ok=data["devices_ok"],
            devices_warning=data["devices_warning"],
            devices_critical=data["devices_critical"],
            delivery_risk_status=data["delivery_risk_status"],
            delivery_status=data["delivery_status"],
        ))
    return items


async def get_by_device(
    db: AsyncSession, campaign_id: UUID,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    store_id: Optional[UUID] = None,
    channel_id: Optional[UUID] = None,
    limit: int = 100, offset: int = 0,
) -> list[schemas.DeviceReportItem]:
    """Devices for this campaign: from published targets UNION PoP devices."""
    if date_from is None:
        date_from = datetime(2000, 1, 1, tzinfo=timezone.utc)
    if date_to is None:
        date_to = datetime(2099, 12, 31, tzinfo=timezone.utc)

    # Union of two sources: (A) devices from published targets, (B) devices from PoP
    # Outer DISTINCT ON ensures one row per device
    base_sql = """
        WITH device_sources AS (
            -- Source A: devices matched to published targets
            SELECT DISTINCT ON (gd.id)
                gd.id AS gateway_device_id,
                gd.device_code,
                gd.device_name,
                gd.store_id,
                s.code AS store_code,
                gd.channel_id,
                c.code AS channel_code,
                gd.status AS device_status,
                gd.last_seen_at,
                gd.disabled_at,
                true AS has_publication
            FROM gateway_devices gd
            JOIN stores s ON s.id = gd.store_id
            JOIN channels c ON c.id = gd.channel_id
            JOIN publication_targets pt ON pt.channel_id = gd.channel_id
                AND pt.store_id = gd.store_id
            JOIN publication_batches pb ON pb.id = pt.publication_batch_id
            WHERE pb.campaign_id = :campaign_id AND pb.status = 'published'

            UNION

            -- Source B: devices from PoP events (not already in published targets)
            SELECT DISTINCT ON (gd.id)
                gd.id AS gateway_device_id,
                gd.device_code,
                gd.device_name,
                gd.store_id,
                s.code AS store_code,
                gd.channel_id,
                c.code AS channel_code,
                gd.status AS device_status,
                gd.last_seen_at,
                gd.disabled_at,
                false AS has_publication
            FROM gateway_devices gd
            JOIN stores s ON s.id = gd.store_id
            JOIN channels c ON c.id = gd.channel_id
            JOIN proof_of_play_events poe ON poe.gateway_device_id = gd.id
            WHERE poe.campaign_id = :campaign_id
              AND poe.played_at >= :df AND poe.played_at <= :dt
        )
        SELECT DISTINCT ON (ds.gateway_device_id)
            ds.gateway_device_id,
            ds.device_code,
            ds.device_name,
            ds.store_id,
            ds.store_code,
            ds.channel_id,
            ds.channel_code,
            ds.device_status,
            ds.last_seen_at,
            ds.disabled_at,
            ds.has_publication,
            dcms.status AS current_manifest_status,
            COALESCE(pop_agg.pop_count, 0)::int AS actual_play_count,
            pop_agg.last_pop_at
        FROM device_sources ds
        LEFT JOIN LATERAL (
            SELECT dcms2.status FROM device_current_manifest_states dcms2
            JOIN manifest_versions mv2 ON mv2.id = dcms2.manifest_version_id
            JOIN publication_targets pt2 ON pt2.id = mv2.publication_target_id
            JOIN publication_batches pb2 ON pb2.id = pt2.publication_batch_id
            WHERE dcms2.gateway_device_id = ds.gateway_device_id
              AND pb2.campaign_id = :campaign_id
            LIMIT 1
        ) dcms ON true
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS pop_count, MAX(poe.played_at) AS last_pop_at
            FROM proof_of_play_events poe
            WHERE poe.gateway_device_id = ds.gateway_device_id
              AND poe.campaign_id = :campaign_id
              AND poe.played_at >= :df AND poe.played_at <= :dt
        ) pop_agg ON true
    """

    params = {"campaign_id": campaign_id, "df": date_from, "dt": date_to}
    extra_where = ""
    if store_id:
        extra_where += " AND ds.store_id = :store_id"
        params["store_id"] = store_id
    if channel_id:
        extra_where += " AND ds.channel_id = :channel_id"
        params["channel_id"] = channel_id

    sql = base_sql + extra_where + " ORDER BY ds.gateway_device_id LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    result = await db.execute(text(sql), params)
    rows = result.all()

    items = []
    for r in rows:
        health = "disabled" if r.disabled_at else (
            "healthy" if r.last_seen_at else "offline"
        )
        items.append(schemas.DeviceReportItem(
            gateway_device_id=r.gateway_device_id,
            device_code=r.device_code,
            device_name=r.device_name or r.device_code,
            store_id=r.store_id,
            store_code=r.store_code,
            channel_id=r.channel_id,
            channel_code=r.channel_code,
            device_status=r.device_status or "unknown",
            health_status=health,
            delivery_status="ok",
            current_manifest_status=r.current_manifest_status,
            last_heartbeat_at=r.last_seen_at,
            last_pop_at=r.last_pop_at,
            actual_play_count=r.actual_play_count,
        ))
    return items


async def get_by_creative(
    db: AsyncSession, campaign_id: UUID,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list[schemas.CreativeReportItem]:
    if date_from is None:
        date_from = datetime(2000, 1, 1, tzinfo=timezone.utc)
    if date_to is None:
        date_to = datetime(2099, 12, 31, tzinfo=timezone.utc)

    sql = text("""
        SELECT
            cr.id AS campaign_rendition_id,
            cr.rendition_id,
            cv.original_filename AS rendition_name,
            cv.mime_type AS format,
            COUNT(DISTINCT pt.id)::int AS published_targets,
            COUNT(DISTINCT dmci.gateway_device_id)
                FILTER (WHERE dmci.status = 'cached')::int AS cache_ready,
            COALESCE(
                COUNT(DISTINCT poe.id),
                COUNT(DISTINCT poe_fallback.id)
            )::int AS pop_count,
            COALESCE(
                COUNT(DISTINCT poe.gateway_device_id),
                COUNT(DISTINCT poe_fallback.gateway_device_id)
            )::int AS pop_devices,
            COALESCE(MAX(poe.played_at), MAX(poe_fallback.played_at)) AS last_pop
        FROM campaign_renditions cr
        JOIN renditions r ON r.id = cr.rendition_id
        JOIN creative_versions cv ON cv.id = r.creative_version_id
        LEFT JOIN manifest_items mi ON mi.campaign_rendition_id = cr.id
        LEFT JOIN manifest_versions mv ON mv.id = mi.manifest_version_id
        LEFT JOIN publication_targets pt ON pt.id = mv.publication_target_id
        LEFT JOIN publication_batches pb ON pb.id = pt.publication_batch_id
            AND pb.status = 'published'
        LEFT JOIN device_media_cache_items dmci ON dmci.manifest_item_id = mi.id
        LEFT JOIN proof_of_play_events poe ON poe.campaign_rendition_id = cr.id
            AND poe.played_at >= :df AND poe.played_at <= :dt
        -- Fallback: PoP without campaign_rendition_id, linked via manifest_item_id
        -- Only if the manifest_item belongs to the same campaign
        LEFT JOIN proof_of_play_events poe_fallback
            ON poe_fallback.manifest_item_id = mi.id
            AND poe_fallback.campaign_id = :campaign_id
            AND poe_fallback.played_at >= :df AND poe_fallback.played_at <= :dt
            AND poe.campaign_rendition_id IS NULL
        WHERE cr.campaign_id = :campaign_id
        GROUP BY cr.id, cr.rendition_id, cv.original_filename, cv.mime_type
        ORDER BY pop_count DESC
    """)
    result = await db.execute(sql, {
        "campaign_id": campaign_id, "df": date_from, "dt": date_to,
    })
    rows = result.all()

    items = []
    for r in rows:
        items.append(schemas.CreativeReportItem(
            campaign_rendition_id=r.campaign_rendition_id,
            rendition_id=r.rendition_id,
            rendition_name=r.rendition_name,
            creative_name=None,
            format=r.format,
            published_targets=r.published_targets or 0,
            cache_ready_devices=r.cache_ready or 0,
            actual_play_count=r.pop_count or 0,
            unique_devices_with_pop=r.pop_devices or 0,
            last_pop_at=r.last_pop,
        ))
    return items


# ── Snapshots ─────────────────────────────────────────────────────

async def create_snapshot(
    db: AsyncSession, campaign_id: UUID, user_id: UUID,
    period_from: Optional[datetime] = None,
    period_to: Optional[datetime] = None,
) -> Optional[CampaignDeliverySnapshot]:
    data = await _compute_campaign_report(db, campaign_id, period_from, period_to)
    if data is None:
        return None

    snap = CampaignDeliverySnapshot(
        campaign_id=campaign_id,
        period_from=data["period_from"],
        period_to=data["period_to"],
        snapshot_status="generated",
        delivery_status=data["delivery_status"],
        delivery_risk_status=data["delivery_risk_status"],
        planned_stores=data["planned_stores"],
        planned_devices=data["planned_devices"],
        published_targets=data["published_targets"],
        published_devices=data["published_devices"],
        manifest_available_devices=data["manifest_available_devices"],
        manifest_applied_devices=data["manifest_applied_devices"],
        manifest_failed_devices=data["manifest_failed_devices"],
        cache_ready_devices=data["cache_ready_devices"],
        cache_missing_devices=data["cache_missing_devices"],
        cache_failed_devices=data["cache_failed_devices"],
        cache_invalid_hash_devices=data["cache_invalid_hash_devices"],
        actual_play_count=data["actual_play_count"],
        unique_devices_with_pop=data["unique_devices_with_pop"],
        unique_stores_with_pop=data["unique_stores_with_pop"],
        devices_ok=data["devices_ok"],
        devices_warning=data["devices_warning"],
        devices_critical=data["devices_critical"],
        stores_total=data["stores_total"],
        stores_with_delivery=data["stores_with_delivery"],
        stores_with_errors=data["stores_with_errors"],
        channels_total=data["channels_total"],
        details_json={
            "delivery_status": data["delivery_status"],
            "delivery_risk_status": data["delivery_risk_status"],
            "publication_rate": data["publication_rate"],
            "manifest_apply_rate": data["manifest_apply_rate"],
        },
        generated_by_user_id=user_id,
    )
    db.add(snap)
    await db.flush()
    return snap


async def list_snapshots(
    db: AsyncSession, campaign_id: UUID,
) -> list[CampaignDeliverySnapshot]:
    from sqlalchemy import select
    result = await db.execute(
        select(CampaignDeliverySnapshot)
        .where(CampaignDeliverySnapshot.campaign_id == campaign_id)
        .order_by(CampaignDeliverySnapshot.generated_at.desc())
    )
    return list(result.scalars().all())


async def get_snapshot(
    db: AsyncSession, campaign_id: UUID, snapshot_id: UUID,
) -> Optional[CampaignDeliverySnapshot]:
    snap = await db.get(CampaignDeliverySnapshot, snapshot_id)
    if snap and snap.campaign_id == campaign_id:
        return snap
    return None
