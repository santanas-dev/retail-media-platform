"""
FastAPI dependencies: DB sessions, current user, permission checks.
"""

from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, Settings
from app.core.database import get_session_factory
from app.domains.identity import models, service

# Bearer token security scheme
security_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: yields an async DB session."""
    settings = get_settings()
    factory = get_session_factory(settings)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> models.User:
    """Dependency: returns authenticated user from Bearer token.
    
    Returns None if no token provided (for optional auth endpoints).
    """
    settings = get_settings()
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return await service.get_current_user_from_token(
        db=db,
        token=credentials.credentials,
        settings=settings,
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> models.User | None:
    """Dependency: returns user if authenticated, None otherwise."""
    if credentials is None:
        return None
    settings = get_settings()
    try:
        return await service.get_current_user_from_token(
            db=db,
            token=credentials.credentials,
            settings=settings,
        )
    except HTTPException:
        return None


def require_permission(permission: str):
    """Dependency factory: checks that current user has a specific permission."""
    async def checker(
        current_user: models.User = Depends(get_current_user),
    ) -> models.User:
        service.require_permission(current_user, permission)
        return current_user
    return checker
