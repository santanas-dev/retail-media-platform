"""Health check and observability router — H.2.

Endpoints:
  GET /api/health/live           — liveness (no DB)
  GET /api/health/ready          — readiness (DB + optional Redis/MinIO)
  GET /api/health/dependencies   — detailed dependency status (admin)
  GET /api/health/metrics        — simple Prometheus-text metrics
"""

import time
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends
from app.domains.health.schemas import (
    LiveResponse, ReadyResponse, DependenciesResponse,
)
from app.domains.health.service import (
    check_postgresql, check_redis, check_minio,
)
from app.domains.identity import models as identity_models
from app.core.deps import require_permission

router = APIRouter(prefix="/api/health", tags=["health"])

# ── In-memory metrics counters (lightweight, no Prometheus client) ──

_METRIC_KEYS = frozenset({
    "app_requests_total", "app_errors_total",
    "health_check_total",
})


class _Metrics:
    def __init__(self):
        self._counters: dict[str, int] = {}

    def inc(self, name: str) -> None:
        if name not in _METRIC_KEYS:
            return  # silently ignore unknown metrics
        self._counters[name] = self._counters.get(name, 0) + 1

    def snapshot(self) -> dict[str, int]:
        return dict(self._counters)


_metrics = _Metrics()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Liveness
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/live", response_model=LiveResponse)
async def health_live(request: Request):
    """Liveness probe — does NOT touch DB or dependencies.

    Public/internal: safe for load balancers.
    """
    _metrics.inc("health_check_total")
    return LiveResponse(
        status="ok",
        service="retail-media-platform",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        correlation_id=getattr(request.state, "correlation_id", None),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Readiness
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/ready", response_model=ReadyResponse)
async def health_ready(request: Request):
    """Readiness probe — checks PostgreSQL connectivity.

    Redis/MinIO are optional and return 'unknown' if unavailable.
    Safe: no secrets, no traceback, no raw exceptions.
    """
    _metrics.inc("health_check_total")
    deps = []

    # PostgreSQL is critical
    pg = await check_postgresql()
    deps.append(pg)

    # Redis and MinIO are best-effort
    redis_dep = await check_redis()
    deps.append(redis_dep)

    minio_dep = await check_minio()
    deps.append(minio_dep)

    ready = pg.status == "ok"

    return ReadyResponse(
        status="ok" if ready else "degraded",
        service="retail-media-platform",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        correlation_id=getattr(request.state, "correlation_id", None),
        dependencies=deps,
        ready=ready,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Dependencies (admin)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/dependencies", response_model=DependenciesResponse)
async def health_dependencies(
    request: Request,
    current_user: identity_models.User = Depends(
        require_permission("system_admin")  # admin only
    ),
):
    """Detailed dependency status.

    Requires system_admin permission.
    Safe: no secrets, no DSN, no credentials.
    """
    _metrics.inc("health_check_total")
    deps = [
        await check_postgresql(),
        await check_redis(),
        await check_minio(),
    ]
    return DependenciesResponse(
        status="ok",
        service="retail-media-platform",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        correlation_id=getattr(request.state, "correlation_id", None),
        dependencies=deps,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Metrics (simple Prometheus text format)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/metrics")
async def health_metrics(request: Request):
    """Simple Prometheus text-format metrics endpoint.

    Returns text/plain Prometheus exposition format.
    No heavy dependencies — pure in-memory counters.
    No secrets, no expensive queries.
    """
    from fastapi.responses import PlainTextResponse
    _metrics.inc("health_check_total")

    snapshot = _metrics.snapshot()
    lines = [
        "# HELP app_requests_total Total application requests.",
        "# TYPE app_requests_total counter",
        f"app_requests_total {snapshot.get('app_requests_total', 0)}",
        "# HELP app_errors_total Total application errors.",
        "# TYPE app_errors_total counter",
        f"app_errors_total {snapshot.get('app_errors_total', 0)}",
        "# HELP health_check_total Total health check calls.",
        "# TYPE health_check_total counter",
        f"health_check_total {snapshot.get('health_check_total', 0)}",
        "",
    ]
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/plain; charset=utf-8",
    )
