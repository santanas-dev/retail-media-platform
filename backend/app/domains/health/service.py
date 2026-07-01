"""Health check service — H.2 observability.

Safe dependency checks: no secrets, no raw exceptions, no tracebacks.
Redis/MinIO checks are optional and return 'unknown' if unavailable.
"""

import time
from app.core.config import get_settings
from app.core.database import get_engine, check_db_connection
from app.domains.health.schemas import DependencyStatus


async def check_postgresql() -> DependencyStatus:
    """Check PostgreSQL connectivity."""
    start = time.monotonic()
    try:
        settings = get_settings()
        await check_db_connection(settings)
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="postgresql",
            status="ok",
            latency_ms=latency,
            message="Connected",
        )
    except Exception:
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="postgresql",
            status="unavailable",
            latency_ms=latency,
            message="Connection failed",
        )


async def check_redis() -> DependencyStatus:
    """Check Redis connectivity (best-effort).

    Returns 'unknown' if Redis is not configured or unreachable.
    NEVER exposes connection string or credentials.
    """
    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        redis_url = settings.REDIS_URL
        if not redis_url or "localhost" in redis_url:
            return DependencyStatus(
                name="redis",
                status="unknown",
                message="Redis not configured or using localhost default",
            )

        start = time.monotonic()
        r = aioredis.from_url(redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="redis",
            status="ok",
            latency_ms=latency,
            message="Connected",
        )
    except Exception:
        return DependencyStatus(
            name="redis",
            status="unknown",
            message="Redis check failed or not available",
        )


async def check_minio() -> DependencyStatus:
    """Check MinIO connectivity (best-effort).

    Returns 'unknown' if MinIO is not configured or unreachable.
    NEVER exposes endpoint URL or credentials.
    """
    try:
        from app.domains.media.storage import ensure_bucket
        start = time.monotonic()
        await ensure_bucket()
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="minio",
            status="ok",
            latency_ms=latency,
            message="Bucket accessible",
        )
    except Exception:
        return DependencyStatus(
            name="minio",
            status="unknown",
            message="MinIO check failed or not available",
        )
