"""
FastAPI dependencies: DB sessions, current user, permissions.

On Step 1 these are stubs — real implementation comes with Identity domain.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, Settings
from app.core.database import get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: yields an async DB session."""
    settings = get_settings()
    factory = get_session_factory(settings)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user():
    """Dependency stub: returns current authenticated user. Not implemented yet."""
    return None


async def get_current_active_user():
    """Dependency stub: returns current active user. Not implemented yet."""
    return None
