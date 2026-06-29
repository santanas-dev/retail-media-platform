"""
Channels seed: idempotent — creates 5 standard channels + device types + capability profiles.

Usage:
    cd backend
    python -m app.domains.channels.seed
"""

import asyncio

from sqlalchemy import select
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
        "kso_gen5",
        "768x1024",
        "portrait",
        ["mp4", "jpg", "png"],
        50 * 1024 * 1024,  # 50 MB
        30,  # 30 sec
        False,
        "real_playback",
        "full",
    ),
    (
        "android_tv_gen1",
        "1920x1080",
        "landscape",
        ["mp4", "jpg", "png"],
        100 * 1024 * 1024,  # 100 MB
        60,  # 60 sec
        False,
        "real_playback",
        "full",
    ),
    (
        "price_checker_gen1",
        "1280x800",
        "landscape",
        ["mp4", "jpg", "png"],
        50 * 1024 * 1024,
        30,
        False,
        "real_playback",
        "full",
    ),
    (
        "esl_gen1",
        "296x128",
        "landscape",
        ["png", "jpg"],
        2 * 1024 * 1024,  # 2 MB
        0,  # static only
        False,
        "impression",
        "full",
    ),
    (
        "led_shelf_gen1",
        "480x64",
        "landscape",
        ["mp4", "png", "jpg"],
        5 * 1024 * 1024,  # 5 MB
        15,  # 15 sec
        False,
        "impression",
        "full",
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
                    .on_conflict_do_nothing(
                        index_elements=["channel_id", "code"]
                    )
                )

        # Fetch device type IDs
        dt_map = {}
        result = await conn.execute(select(models.DeviceType))
        for row in result.fetchall():
            dt_map[row.code] = row.id

        # ── Capability Profiles ───────────────────────────────────────
        # Check existing before insert (no unique on device_type_id)
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
                        device_type_id=dt_id,
                        resolution=resolution,
                        orientation=orientation,
                        formats_json=formats_json,
                        max_file_size=max_file_size,
                        max_duration=max_duration,
                        interactive=interactive,
                        proof_type=proof_type,
                        cache_policy=cache_policy,
                    )
                )

    counts = {
        "channels": len(CHANNELS),
        "device_types": len(DEVICE_TYPES),
        "capability_profiles": len(CAPABILITY_PROFILES),
    }
    print(f"Channels seed complete. {counts}")


def main():
    asyncio.run(seed())


if __name__ == "__main__":
    main()
