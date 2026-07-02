"""
Retail Media Platform — Dev/Demo Seed.

Phase 2: Creates one minimal hierarchy for local development and testing.
Idempotent: safe to run multiple times (ON CONFLICT DO NOTHING).

Usage:
    DATABASE_URL=postgresql+asyncpg://... python apps/control-api/seed.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text
from packages.domain.database import create_engine


SEED_BRANCH_ID = "00000000-0000-0000-0000-000000000001"
SEED_CLUSTER_ID = "00000000-0000-0000-0000-000000000002"
SEED_STORE_ID = "00000000-0000-0000-0000-000000000003"
SEED_CHANNEL_ID = "00000000-0000-0000-0000-000000000010"
SEED_DEVICE_TYPE_ID = "00000000-0000-0000-0000-000000000011"
SEED_CAPABILITY_ID = "00000000-0000-0000-0000-000000000012"
SEED_DEVICE_ID = "00000000-0000-0000-0000-000000000020"
SEED_CARRIER_ID = "00000000-0000-0000-0000-000000000030"
SEED_SURFACE_ID = "00000000-0000-0000-0000-000000000031"

SEED_SQL = f"""
-- Organization
INSERT INTO branches (id, code, name, timezone)
VALUES ('{SEED_BRANCH_ID}', 'BR-001', 'Центральный филиал', 'Europe/Moscow')
ON CONFLICT (code) DO NOTHING;

INSERT INTO clusters (id, branch_id, code, name)
VALUES ('{SEED_CLUSTER_ID}', '{SEED_BRANCH_ID}', 'CL-001', 'Кластер Москва')
ON CONFLICT (code) DO NOTHING;

INSERT INTO stores (id, cluster_id, code, name, address, timezone)
VALUES ('{SEED_STORE_ID}', '{SEED_CLUSTER_ID}', 'ST-001', 'Магазин №42',
        'г. Москва, ул. Тестовая, д. 1', 'Europe/Moscow')
ON CONFLICT (code) DO NOTHING;

-- Channel model
INSERT INTO channels (id, code, name, description, sort_order)
VALUES ('{SEED_CHANNEL_ID}', 'KSO', 'Кассы самообслуживания',
        'Первый канал внедрения — экраны касс самообслуживания', 1)
ON CONFLICT (code) DO NOTHING;

INSERT INTO device_types (id, channel_id, code, name, player_runtime)
VALUES ('{SEED_DEVICE_TYPE_ID}', '{SEED_CHANNEL_ID}', 'KSO_V1',
        'КСО (x86 Linux + Chromium)', 'chromium')
ON CONFLICT (code) DO NOTHING;

INSERT INTO capability_profiles (id, device_type_id, code, resolution_w, resolution_h,
    orientation, supported_formats, max_file_size_bytes, max_duration_sec,
    supports_video, supports_animation, supports_interactive, pop_mode)
VALUES ('{SEED_CAPABILITY_ID}', '{SEED_DEVICE_TYPE_ID}', 'KSO_V1_DEFAULT',
        1440, 1080, 'landscape',
        '{{image/png,image/jpeg,image/webp,video/mp4}}'::text[],
        10485760, 30, true, false, false, 'real_playback')
ON CONFLICT (code) DO NOTHING;

-- Physical test KSO
INSERT INTO physical_devices (id, store_id, device_type_id, code, serial_number,
    status, cache_size_bytes)
VALUES ('{SEED_DEVICE_ID}', '{SEED_STORE_ID}', '{SEED_DEVICE_TYPE_ID}',
        'KSO-001', 'SN-KSO-TEST-001', 'unregistered', 0)
ON CONFLICT (code) DO NOTHING;

-- Logical carrier + display surface
INSERT INTO logical_carriers (id, physical_device_id, code, carrier_type)
VALUES ('{SEED_CARRIER_ID}', '{SEED_DEVICE_ID}', 'LC-KSO-001', 'direct')
ON CONFLICT (code) DO NOTHING;

INSERT INTO display_surfaces (id, logical_carrier_id, store_id, code,
    resolution_w, resolution_h)
VALUES ('{SEED_SURFACE_ID}', '{SEED_CARRIER_ID}', '{SEED_STORE_ID}',
        'SURF-001', 1440, 1080)
ON CONFLICT (code) DO NOTHING;
"""


async def seed():
    engine = create_engine()
    async with engine.begin() as conn:
        for statement in SEED_SQL.strip().split(";\n"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(text(stmt + ";"))
    await engine.dispose()
    print("Seed complete: 1 branch → 1 cluster → 1 store → 1 KSO device → 1 surface")


if __name__ == "__main__":
    asyncio.run(seed())
