"""Health check schemas — H.2 observability."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class DependencyStatus(BaseModel):
    """Status of a single dependency."""
    name: str = Field(description="Dependency name: postgresql, redis, minio")
    status: Literal["ok", "degraded", "unavailable", "unknown"] = "unknown"
    latency_ms: Optional[float] = Field(default=None, description="Check latency in ms")
    message: Optional[str] = Field(default=None, max_length=256)


class HealthResponse(BaseModel):
    """Generic health response."""
    status: str = "ok"
    service: str = "retail-media-platform"
    version: str = "0.1.0"
    timestamp: str = Field(default="", description="ISO 8601 UTC timestamp")
    correlation_id: Optional[str] = Field(default=None, max_length=128)


class LiveResponse(HealthResponse):
    """Liveness probe — no dependency checks."""
    pass


class ReadyResponse(HealthResponse):
    """Readiness probe — checks critical dependencies."""
    dependencies: list[DependencyStatus] = Field(default_factory=list)
    ready: bool = True


class DependenciesResponse(HealthResponse):
    """Detailed dependency status (admin/internal)."""
    dependencies: list[DependencyStatus] = Field(default_factory=list)
