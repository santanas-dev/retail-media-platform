"""
Application configuration loaded from environment variables.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Retail Media Platform"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = ""

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        """Refuse to start with insecure SECRET_KEY."""
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY must be set (cannot be empty)")
        if self.SECRET_KEY == "change-me-in-production":
            raise ValueError(
                "SECRET_KEY must be set to a random value, "
                "not the default 'change-me-in-production'"
            )
        return self

    @model_validator(mode="after")
    def _validate_minio_creds(self) -> "Settings":
        """In non-dev environments, refuse default MinIO credentials."""
        if self.APP_ENV == "development":
            return self
        if self.MINIO_ACCESS_KEY == "minioadmin":
            raise ValueError(
                "MINIO_ACCESS_KEY must not use default 'minioadmin' "
                "in non-development environments"
            )
        if self.MINIO_SECRET_KEY == "minioadmin":
            raise ValueError(
                "MINIO_SECRET_KEY must not use default 'minioadmin' "
                "in non-development environments"
            )
        return self

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "retail_media"
    POSTGRES_PASSWORD: str = "retail_media_dev"
    POSTGRES_DB: str = "retail_media_platform"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:***@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ClickHouse
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DB: str = "retail_media_analytics"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9002"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "retail-media"
    MINIO_SECURE: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:***@localhost"

    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Scheduling
    MAX_SCHEDULE_ITEMS_PER_RUN: int = 100_000

    # Publications
    MAX_MANIFEST_JSON_BYTES: int = 10 * 1024 * 1024  # 10 MB
    ENABLE_REAL_PUBLICATION: bool = False  # BACKEND.1.1 — feature flag, OFF by default
    ENABLE_GENERATED_MANIFEST_WRITE: bool = False  # BACKEND.1.2 — feature flag, OFF by default

    # Device Gateway
    DEVICE_JWT_SECRET: str = ""
    DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    DEVICE_HEARTBEAT_TIMEOUT_MINUTES: int = 15
    DEVICE_HEARTBEAT_DETAILS_MAX_BYTES: int = 65536
    DEVICE_MANIFEST_REQUEST_DETAILS_MAX_BYTES: int = 65536
    DEVICE_MEDIA_REQUEST_DETAILS_MAX_BYTES: int = 65536

    # Device Gateway → PoP Ingest
    POP_MAX_CLOCK_SKEW_SECONDS: int = 300
    POP_MAX_EVENT_AGE_DAYS: int = 7
    POP_MAX_DURATION_MS: int = 86_400_000
    POP_DETAILS_MAX_BYTES: int = 65536

    # Device Gateway → PoP Batch Ingest
    POP_BATCH_MAX_EVENTS: int = 500
    POP_BATCH_MAX_BYTES: int = 2_097_152  # 2 MB

    # Device Operations → Health thresholds
    DEVICE_HEALTH_OFFLINE_MINUTES: int = 30
    DEVICE_HEALTH_MANIFEST_GRACE_MINUTES: int = 60
    DEVICE_HEALTH_MEDIA_GRACE_MINUTES: int = 120
    DEVICE_HEALTH_POP_GRACE_MINUTES: int = 180
    DEVICE_HEALTH_ERROR_RATE_WARNING: float = 0.20
    DEVICE_HEALTH_ERROR_RATE_CRITICAL: float = 0.50
    DEVICE_HEALTH_MAX_PERIOD_DAYS: int = 30
    DEVICE_HEALTH_DEFAULT_PERIOD_HOURS: int = 24
    DEVICE_HEALTH_CACHE_REPORT_STALE_MINUTES: int = 120
    DEVICE_HEALTH_CACHE_MISSING_CRITICAL_RATIO: float = 0.50
    DEVICE_HEALTH_CACHE_FAILED_CRITICAL_RATIO: float = 0.50

    @model_validator(mode="after")
    def _validate_device_jwt_secret(self) -> "Settings":
        """In non-dev environments, DEVICE_JWT_SECRET must be explicitly set."""
        if self.APP_ENV == "development":
            return self
        if not self.DEVICE_JWT_SECRET:
            raise ValueError(
                "DEVICE_JWT_SECRET must be set in non-development environments"
            )
        if self.DEVICE_JWT_SECRET == "change-me-in-production":
            raise ValueError(
                "DEVICE_JWT_SECRET must be set to a random value, "
                "not the default 'change-me-in-production'"
            )
        return self

    @property
    def effective_device_jwt_secret(self) -> str:
        """DEVICE_JWT_SECRET with fallback to SECRET_KEY in development only."""
        return self.DEVICE_JWT_SECRET or self.SECRET_KEY

    # Identity — initial admin user (created by seed script)
    INITIAL_ADMIN_USERNAME: str = "admin"
    INITIAL_ADMIN_PASSWORD: str = ""
    INITIAL_ADMIN_EMAIL: str = "admin@localhost"

    # Device Operations — alert rules
    DEVICE_ALERT_DETAILS_MAX_BYTES: int = 65536  # 64 KB

    # Runtime config
    RUNTIME_CONFIG_MAX_BYTES: int = 65536  # 64 KB


@lru_cache()
def get_settings() -> Settings:
    return Settings()
