"""
Retail Media Platform — Shared Domain Enums and Constants.

Phase 1: Placeholders only. No ORM, no DB dependencies.
"""
from enum import StrEnum


class ChannelType(StrEnum):
    KSO = "KSO"
    ANDROID_TV = "ANDROID_TV"
    PRICE_CHECKER = "PRICE_CHECKER"
    ESL = "ESL"
    LED = "LED"
    MOCK = "MOCK"


class DeviceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    REVOKED = "revoked"
    UNREGISTERED = "unregistered"


class ProofMode(StrEnum):
    REAL_PLAYBACK = "real_playback"
    SCREEN_RENDER = "screen_render"
    IDLE_SCREEN = "idle_screen"
    TEMPLATE_APPLIED = "template_applied"
    GATEWAY_ACK = "gateway_ack"
    LABEL_ACK = "label_ack"
    CONTROLLER_ACK = "controller_ack"


class CertificateType(StrEnum):
    RSA = "rsa"
    ED25519 = "ed25519"
    HSM = "hsm"


class ManifestStatus(StrEnum):
    GENERATED = "generated"
    DELIVERED = "delivered"
    APPLIED = "applied"
    EXPIRED = "expired"
    ERROR = "error"


class PlaybackResult(StrEnum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    MODERATION = "moderation"
    REVIEW = "review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    LIVE = "live"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class OrderType(StrEnum):
    COMMERCIAL = "commercial"
    INTERNAL = "internal"
    COMPENSATION = "compensation"
    TEST = "test"


# Service identifiers for logging/metrics
SERVICE_CONTROL_API = "control-api"
SERVICE_DEVICE_GATEWAY = "device-gateway"
SERVICE_POP_INGESTOR = "pop-ingestor"
SERVICE_ORCHESTRATOR = "orchestrator-worker"
SERVICE_ADAPTER_MOCK = "adapter-mock"
SERVICE_ADAPTER_KSO = "adapter-kso"

# Defaults
DEFAULT_CORRELATION_ID_HEADER = "X-Correlation-ID"
DEVICE_CORRELATION_ID_HEADER = "X-Device-Correlation-ID"
