"""
Channels seed: idempotent — creates 5 standard channels.

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


async def seed() -> None:
    settings = get_settings()
    engine = get_engine(settings)
    async with engine.begin() as conn:
        for code, name, description in CHANNELS:
            await conn.execute(
                pg_insert(models.Channel)
                .values(code=code, name=name, description=description)
                .on_conflict_do_nothing(index_elements=["code"])
            )

    print(f"Channels seed complete. {len(CHANNELS)} channels.")


def main():
    asyncio.run(seed())


if __name__ == "__main__":
    main()
