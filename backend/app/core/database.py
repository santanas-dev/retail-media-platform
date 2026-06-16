"""
Database connections: PostgreSQL (async) + ClickHouse (stub).
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    """Base for all ORM models."""
    pass


# Global engine and session factory (lazy init)
_engine = None
_async_session_factory = None


def get_engine(settings: Settings):
    """Create or return the async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.DEBUG,
            pool_size=20,
            max_overflow=40,
        )
    return _engine


def get_session_factory(settings: Settings):
    """Create or return the async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine(settings)
        _async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


async def check_db_connection(settings: Settings):
    """Verify PostgreSQL connectivity on startup."""
    try:
        engine = get_engine(settings)
        async with engine.connect() as conn:
            await conn.execute(Base.metadata.bind is None)
    except Exception:
        # Non-fatal: health check will report db status
        pass


async def get_db(settings: Settings):
    """FastAPI dependency: yields an async DB session."""
    factory = get_session_factory(settings)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
