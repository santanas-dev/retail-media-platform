"""
Channels seed: idempotent — creates 5 standard channels + device types + capability profiles.

Usage:
    cd backend
    python -m app.domains.channels.seed
"""

import asyncio

from sqlalchemy import select, text, update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import get_engine
from app.core.config import get_settings
from app.domains.channels import models

CHANNELS = [
    ("kso", "КСО", "Кассы самообслуживания"),
    ("android_tv", "Android TV", "Телевизоры на Android"),
    ("price_checker", "Прайс-чекер", "Терминалы проверки цен"),
    ("esl", "ESL", "Электронные ценники"),
    ("led_shelf_banner", "LED Shelf Banner", "Светодиодные полочные баннеры"),
]

# Device types per channel (channel_code, type_code, type_name)
DEVICE_TYPES = [
    ("kso", "kso_gen5", "КСО 5-го поколения"),
    ("android_tv", "android_tv_gen1", "Android TV 1-го поколения"),
    ("price_checker", "price_checker_gen1", "Прайс-чекер 1-го поколения"),
    ("esl", "esl_gen1", "ESL 1-го поколения"),
    ("led_shelf_banner", "led_shelf_gen1", "LED Shelf Banner 1-го поколения"),
]

# Capability profiles per device type
# (device_type_code, resolution, orientation, formats_json, max_file_size, max_duration, interactive, proof_type, cache_policy)
CAPABILITY_PROFILES = [
    (
        "kso_gen5", "768x1024", "portrait",
        ["mp4", "jpg", "png"], 50 * 1024 * 1024, 30, False, "real_playback", "full",
    ),
    (
        "android_tv_gen1", "1920x1080", "landscape",
        ["mp4", "jpg", "png"], 100 * 1024 * 1024, 60, False, "real_playback", "full",
    ),
    (
        "price_checker_gen1", "1280x800", "landscape",
        ["mp4", "jpg", "png"], 50 * 1024 * 1024, 30, False, "real_playback", "full",
    ),
    (
        "esl_gen1", "296x128", "landscape",
        ["png", "jpg"], 2 * 1024 * 1024, 0, False, "impression", "full",
    ),
    (
        "led_shelf_gen1", "480x64", "landscape",
        ["mp4", "png", "jpg"], 5 * 1024 * 1024, 15, False, "impression", "full",
    ),
]


async def seed() -> None:
    settings = get_settings()
    engine = get_engine(settings)
    async with engine.begin() as conn:
        # ── Channels ──────────────────────────────────────────────────
        for code, name, description in CHANNELS:
            await conn.execute(
                pg_insert(models.Channel)
                .values(code=code, name=name, description=description)
                .on_conflict_do_nothing(index_elements=["code"])
            )

        # Fetch channel IDs
        channel_map = {}
        for code, _, _ in CHANNELS:
            result = await conn.execute(
                select(models.Channel.id).where(models.Channel.code == code)
            )
            row = result.fetchone()
            if row:
                channel_map[code] = row[0]

        # ── Device Types ──────────────────────────────────────────────
        for ch_code, dt_code, dt_name in DEVICE_TYPES:
            channel_id = channel_map.get(ch_code)
            if channel_id:
                await conn.execute(
                    pg_insert(models.DeviceType)
                    .values(code=dt_code, name=dt_name, channel_id=channel_id)
                    .on_conflict_do_nothing(index_elements=["channel_id", "code"])
                )

        # Fetch device type IDs
        dt_map = {}
        result = await conn.execute(select(models.DeviceType))
        for row in result.fetchall():
            dt_map[row.code] = row.id

        # ── Capability Profiles ───────────────────────────────────────
        existing_profiles = await conn.execute(
            select(models.CapabilityProfile.device_type_id)
        )
        existing_dt_ids = {row[0] for row in existing_profiles.fetchall()}

        for (
            dt_code, resolution, orientation, formats_json,
            max_file_size, max_duration, interactive, proof_type, cache_policy,
        ) in CAPABILITY_PROFILES:
            dt_id = dt_map.get(dt_code)
            if dt_id and dt_id not in existing_dt_ids:
                await conn.execute(
                    pg_insert(models.CapabilityProfile)
                    .values(
                        device_type_id=dt_id, resolution=resolution,
                        orientation=orientation, formats_json=formats_json,
                        max_file_size=max_file_size, max_duration=max_duration,
                        interactive=interactive, proof_type=proof_type,
                        cache_policy=cache_policy,
                    )
                )

        # ── KSO Device Chain (B.2 reproducibility) ────────────────────
        await _seed_kso_device_chain(conn)
        await _link_placement_target_to_surface(conn)
        # ── B.3.1 Placement seed ──────────────────────────────────────
        await _seed_placement(conn)

    counts = {
        "channels": len(CHANNELS),
        "device_types": len(DEVICE_TYPES),
        "capability_profiles": len(CAPABILITY_PROFILES),
    }
    print(f"Channels seed complete. {counts}")
    print("KSO device chain seed complete.")
    print("Placement seed complete.")


async def _seed_kso_device_chain(conn) -> None:
    """Idempotent: ensure migrated KSO device has full PD→LC→DS→CP chain."""

    kso_result = await conn.execute(
        select(models.PhysicalDevice).where(
            models.PhysicalDevice.external_code == "test-dev-seed"
        )
    )
    kso_pd = kso_result.fetchone()
    if not kso_pd:
        return  # Fresh DB without KSO migration — skip

    existing_lc = await conn.execute(
        select(models.LogicalCarrier).where(
            models.LogicalCarrier.physical_device_id == kso_pd.id,
            models.LogicalCarrier.type == "kso_player",
        )
    )
    if existing_lc.fetchone():
        return  # Already seeded

    kso_cp = await conn.execute(
        select(models.CapabilityProfile)
        .join(models.DeviceType)
        .join(models.Channel)
        .where(
            models.Channel.code == "kso",
            models.CapabilityProfile.orientation == "portrait",
        )
    )
    cp = kso_cp.fetchone()
    if not cp:
        return  # Profiles not yet seeded

    lc_result = await conn.execute(
        pg_insert(models.LogicalCarrier)
        .values(
            physical_device_id=kso_pd.id, type="kso_player",
            zone="ad_zone", position="portrait_768x1024",
        )
        .returning(models.LogicalCarrier.id)
    )
    lc_id = lc_result.fetchone()[0]

    await conn.execute(
        pg_insert(models.DisplaySurface)
        .values(
            logical_carrier_id=lc_id, capability_profile_id=cp.id,
            resolution="768x1024", is_active=True,
        )
    )


async def _link_placement_target_to_surface(conn) -> None:
    """Idempotent: ensure placement_target references a display_surface."""

    surface_result = await conn.execute(
        select(models.DisplaySurface)
        .join(models.LogicalCarrier)
        .join(models.PhysicalDevice)
        .join(models.CapabilityProfile)
        .where(
            models.PhysicalDevice.external_code == "test-dev-seed",
            models.CapabilityProfile.orientation == "portrait",
        )
        .order_by(models.DisplaySurface.created_at.desc())
        .limit(1)
    )
    surface = surface_result.fetchone()
    if not surface:
        return

    await conn.execute(
        text("""
            UPDATE placement_targets
            SET display_surface_id = :surface_id
            WHERE display_surface_id IS NULL
        """),
        {"surface_id": surface.id},
    )


async def _seed_placement(conn) -> None:
    """Idempotent: ensure universal placement exists with channel_id filled.

    The placement row is created by A.3 migration on real DBs.
    On fresh DBs, this seed creates it.
    channel_id is filled from seed data or the migration UPDATE.
    """
    from app.domains.campaigns.models import Campaign

    existing = await conn.execute(
        select(models.Placement).where(
            models.Placement.placement_code == "test-place-seed",
        )
    )
    placement = existing.fetchone()
    if placement and placement.channel_id is not None:
        return  # Already exists and channel_id filled

    # Find KSO channel and campaign
    kso_campaign = await conn.execute(
        select(Campaign).where(Campaign.campaign_code == "test-place-seed")
    )
    campaign = kso_campaign.fetchone()

    kso_channel = await conn.execute(
        select(models.Channel).where(models.Channel.code == "kso")
    )
    channel = kso_channel.fetchone()

    if not campaign or not channel:
        return  # Fresh DB without required seed data — skip

    if placement and placement.channel_id is None:
        # Fill channel_id for existing placement (edge case after migration)
        await conn.execute(
            text("""
                UPDATE placements
                SET channel_id = :channel_id
                WHERE placement_code = 'test-place-seed'
                  AND channel_id IS NULL
            """),
            {"channel_id": channel.id},
        )
        return

    # Create placement on fresh DB
    await conn.execute(
        text("""
            INSERT INTO placements
                (campaign_id, channel_id, placement_code, name, status, priority)
            VALUES
                (:cid, :chid, 'test-place-seed', 'test-place-seed', 'active', 0)
            ON CONFLICT (placement_code) DO NOTHING
        """),
        {"cid": campaign.id, "chid": channel.id},
    )


def main():
    asyncio.run(seed())


if __name__ == "__main__":
    main()
