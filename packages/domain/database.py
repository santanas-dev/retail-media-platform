"""
Retail Media Platform — Database Configuration.

Phase 2: SQLAlchemy async engine factory.
"""
import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Read from environment; no default production credentials
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://retail_media:retail_media_dev@localhost:5432/retail_media_platform",
)


def create_engine(url: str | None = None):
    """Create async SQLAlchemy engine."""
    target = url or DATABASE_URL
    return create_async_engine(target, echo=False)


def create_session_factory(engine=None):
    """Create async session factory."""
    eng = engine or create_engine()
    return async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
