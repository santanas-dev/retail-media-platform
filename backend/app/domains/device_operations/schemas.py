"""Device Operations: Pydantic schemas for delivery health."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class HealthPeriod(BaseModel):
    date_from: datetime
    date_to: datetime


class OverviewSummary(BaseModel):
    total_devices: int = 0
    healthy: int = 0
    warning: int = 0
    critical: int = 0
    offline: int = 0
    disabled: int = 0


class PipelineCounts(BaseModel):
    heartbeat_devices: int = 0
    manifest_devices: int = 0
    media_devices: int = 0
    pop_devices: int = 0


class ErrorCounts(BaseModel):
    manifest_validation_failed: int = 0
    media_storage_error: int = 0
    pop_rejected: int = 0
    batch_rejected: int = 0


class OverviewResponse(BaseModel):
    status: str = "ok"
    period: HealthPeriod
    summary: OverviewSummary
    pipeline: PipelineCounts
    errors: ErrorCounts


class DeviceHealthItem(BaseModel):
    gateway_device_id: UUID
    device_code: str
    device_name: Optional[str] = None
    store_id: Optional[UUID] = None
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    channel_id: Optional[UUID] = None
    channel_code: Optional[str] = None
    channel_name: Optional[str] = None
    device_status: str
    health_status: str  # healthy/warning/critical/offline/disabled
    last_activity_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    last_manifest_request_at: Optional[datetime] = None
    last_media_request_at: Optional[datetime] = None
    last_pop_event_at: Optional[datetime] = None
    manifest_requests_count: int = 0
    media_requests_count: int = 0
    pop_events_count: int = 0
    error_count: int = 0
    problem_types: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SafeHeartbeatItem(BaseModel):
    id: UUID
    status: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SafeManifestRequestItem(BaseModel):
    id: UUID
    request_status: str
    message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SafeMediaRequestItem(BaseModel):
    id: UUID
    request_status: str
    message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SafePoPEventItem(BaseModel):
    id: UUID
    validation_status: str
    play_status: Optional[str] = None
    rejection_reason: Optional[str] = None
    played_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SafePoPBatchItem(BaseModel):
    id: UUID
    batch_status: str
    total_events: int = 0
    accepted_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class SafeDeviceEventItem(BaseModel):
    id: UUID
    event_type: str
    severity: str
    message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceHealthDetail(BaseModel):
    device: DeviceHealthItem
    recent_heartbeats: list[SafeHeartbeatItem] = Field(default_factory=list)
    recent_manifest_requests: list[SafeManifestRequestItem] = Field(default_factory=list)
    recent_media_requests: list[SafeMediaRequestItem] = Field(default_factory=list)
    recent_pop_events: list[SafePoPEventItem] = Field(default_factory=list)
    recent_pop_batches: list[SafePoPBatchItem] = Field(default_factory=list)
    recent_device_events: list[SafeDeviceEventItem] = Field(default_factory=list)


class StoreHealthItem(BaseModel):
    store_id: UUID
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    total_devices: int = 0
    healthy: int = 0
    warning: int = 0
    critical: int = 0
    offline: int = 0
    disabled: int = 0
    devices_with_manifest: int = 0
    devices_with_media: int = 0
    devices_with_pop: int = 0
    error_count: int = 0
    top_problem_types: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChannelHealthItem(BaseModel):
    channel_id: UUID
    channel_code: Optional[str] = None
    channel_name: Optional[str] = None
    total_devices: int = 0
    healthy: int = 0
    warning: int = 0
    critical: int = 0
    offline: int = 0
    disabled: int = 0
    devices_with_manifest: int = 0
    devices_with_media: int = 0
    devices_with_pop: int = 0
    error_count: int = 0
    top_problem_types: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════
#  Step 16 — Alert Rules Core
# ═══════════════════════════════════════════════════════════════════════

from pydantic import field_validator

ALLOWED_ALERT_TYPES = {
    "device_offline", "no_manifest", "no_media", "no_pop",
    "manifest_validation_failed", "media_validation_failed",
    "media_storage_error", "pop_rejected_high", "duplicate_events_high",
    "batch_rejected",
}
ALLOWED_SEVERITIES = {"info", "warning", "critical"}
ALLOWED_SCOPE_KEYS = {"gateway_device_ids", "store_ids", "channel_ids"}

FORBIDDEN_KEYS = {
    "access_token", "refresh_token", "token", "jwt",
    "password", "secret", "credential", "credentials",
    "authorization", "cookie", "api_key", "private_key",
    "public_key", "stacktrace",
}

RULE_CODE_RE = r"^[a-z0-9_]+$"


def _validate_forbidden_keys(data: dict, path: str = "$") -> None:
    """Recursively check that no forbidden keys exist in a dict."""
    if not isinstance(data, dict):
        return
    for k, v in data.items():
        if k in FORBIDDEN_KEYS:
            raise ValueError(f"Forbidden key '{k}' at {path}")
        if isinstance(v, dict):
            _validate_forbidden_keys(v, f"{path}.{k}")
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    _validate_forbidden_keys(item, f"{path}.{k}[{i}]")


def _validate_scope_json(scope: dict) -> None:
    """Validate scope_json — only allowed keys with UUID arrays."""
    if not isinstance(scope, dict):
        raise ValueError("scope_json must be a JSON object")
    extra = set(scope.keys()) - ALLOWED_SCOPE_KEYS
    if extra:
        raise ValueError(f"Disallowed scope keys: {extra}")
    for key in ALLOWED_SCOPE_KEYS:
        val = scope.get(key)
        if val is not None:
            if not isinstance(val, list):
                raise ValueError(f"scope.{key} must be an array")
            for item in val:
                if not isinstance(item, str):
                    raise ValueError(f"scope.{key} must be UUID strings")
                try:
                    UUID(item)
                except (ValueError, AttributeError):
                    raise ValueError(f"scope.{key} contains invalid UUID: {item}")


# ── Rule schemas ──────────────────────────────────────────────────────


class AlertRuleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=RULE_CODE_RE)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    alert_type: str
    severity: str
    enabled: bool = True
    threshold_json: Optional[dict[str, Any]] = None
    window_minutes: int = Field(default=60, ge=1)
    scope_json: Optional[dict[str, Any]] = None

    @field_validator("alert_type")
    @classmethod
    def check_alert_type(cls, v: str) -> str:
        if v not in ALLOWED_ALERT_TYPES:
            raise ValueError(f"Invalid alert_type: {v}")
        return v

    @field_validator("severity")
    @classmethod
    def check_severity(cls, v: str) -> str:
        if v not in ALLOWED_SEVERITIES:
            raise ValueError(f"Invalid severity: {v}")
        return v

    @field_validator("threshold_json")
    @classmethod
    def check_threshold_forbidden(cls, v: Optional[dict]) -> Optional[dict]:
        if v is not None:
            _validate_forbidden_keys(v)
        return v

    @field_validator("scope_json")
    @classmethod
    def check_scope(cls, v: Optional[dict]) -> Optional[dict]:
        if v is not None:
            _validate_scope_json(v)
            _validate_forbidden_keys(v)
        return v


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    alert_type: Optional[str] = None
    severity: Optional[str] = None
    threshold_json: Optional[dict[str, Any]] = None
    window_minutes: Optional[int] = Field(default=None, ge=1)
    scope_json: Optional[dict[str, Any]] = None

    @field_validator("alert_type")
    @classmethod
    def check_alert_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_ALERT_TYPES:
            raise ValueError(f"Invalid alert_type: {v}")
        return v

    @field_validator("severity")
    @classmethod
    def check_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_SEVERITIES:
            raise ValueError(f"Invalid severity: {v}")
        return v

    @field_validator("threshold_json")
    @classmethod
    def check_threshold_forbidden(cls, v: Optional[dict]) -> Optional[dict]:
        if v is not None:
            _validate_forbidden_keys(v)
        return v

    @field_validator("scope_json")
    @classmethod
    def check_scope(cls, v: Optional[dict]) -> Optional[dict]:
        if v is not None:
            _validate_scope_json(v)
            _validate_forbidden_keys(v)
        return v


class AlertRuleResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    alert_type: str
    severity: str
    enabled: bool
    threshold_json: Optional[dict[str, Any]] = None
    window_minutes: int
    scope_json: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Alert schemas ─────────────────────────────────────────────────────


class AlertEventResponse(BaseModel):
    id: UUID
    event_type: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    user_id: Optional[UUID] = None
    message: Optional[str] = None
    details_json: Optional[dict[str, Any]] = None
    evaluation_run_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertResponse(BaseModel):
    id: UUID
    rule_id: UUID
    alert_type: str
    severity: str
    status: str
    gateway_device_id: Optional[UUID] = None
    store_id: Optional[UUID] = None
    channel_id: Optional[UUID] = None
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[UUID] = None
    resolved_by: Optional[UUID] = None
    dedup_key: str
    title: str
    message: Optional[str] = None
    details_json: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertDetailResponse(AlertResponse):
    events: list[AlertEventResponse] = Field(default_factory=list)


class AlertAcknowledgeRequest(BaseModel):
    message: Optional[str] = None


class AlertResolveRequest(BaseModel):
    message: Optional[str] = None


# ── Evaluate schemas ──────────────────────────────────────────────────


class EvaluateResponse(BaseModel):
    status: str = "ok"
    evaluation_run_id: Optional[UUID] = None
    evaluated_rules: int = 0
    created: int = 0
    repeated: int = 0
    reopened: int = 0
    skipped: int = 0
    failed_rules: int = 0


# ── Evaluation Run History schemas ─────────────────────────────────────


class EvaluationRuleResultResponse(BaseModel):
    id: UUID
    rule_id: UUID
    rule_code: str
    alert_type: str
    status: str
    checked_devices_count: int = 0
    matched_devices_count: int = 0
    created_count: int = 0
    repeated_count: int = 0
    reopened_count: int = 0
    skipped_count: int = 0
    error_message: Optional[str] = None
    details_json: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvaluationRunResponse(BaseModel):
    id: UUID
    triggered_by: UUID
    trigger_type: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    evaluated_rules_count: int = 0
    created_count: int = 0
    repeated_count: int = 0
    reopened_count: int = 0
    skipped_count: int = 0
    failed_rules_count: int = 0
    duration_ms: Optional[int] = None
    details_json: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvaluationRunDetailResponse(EvaluationRunResponse):
    rule_results: list[EvaluationRuleResultResponse] = Field(default_factory=list)

# ═══════════════════════════════════════════════════════════════════════
#  Runtime Configuration (Step 18)
# ═══════════════════════════════════════════════════════════════════════

import hashlib, json, re
from enum import Enum

from pydantic import field_validator, model_validator

# ── Constants ─────────────────────────────────────────────────────────

ALLOWED_CONFIG_KEYS = {
    "heartbeat_interval_sec",
    "manifest_refresh_interval_sec",
    "media_download_timeout_sec",
    "media_cache_max_mb",
    "pop_batch_max_events",
    "pop_flush_interval_sec",
    "offline_mode_enabled",
    "allowed_mime_types",
    "max_media_file_mb",
    "clock_skew_tolerance_sec",
    "log_level",
    "kso_safety",
}

ALLOWED_KSO_KEYS = {
    "idle_only",
    "stop_on_transaction",
    "stop_on_payment",
    "stop_on_error_screen",
}

NUMERIC_RANGES = {
    "heartbeat_interval_sec": (10, 3600),
    "manifest_refresh_interval_sec": (10, 3600),
    "media_download_timeout_sec": (1, 300),
    "media_cache_max_mb": (100, 10240),
    "pop_batch_max_events": (1, 1000),
    "pop_flush_interval_sec": (30, 3600),
    "max_media_file_mb": (1, 2000),
    "clock_skew_tolerance_sec": (0, 3600),
}

ALLOWED_LOG_LEVELS = {"debug", "info", "warning", "error"}

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "video/mp4",
    "video/webm",
}

FORBIDDEN_CONFIG_KEYS = {
    "access_token", "refresh_token", "token", "jwt", "password",
    "secret", "credential", "credentials", "authorization", "cookie",
    "api_key", "private_key", "public_key", "minio", "presigned",
    "presigned_url", "stacktrace",
}

CODE_PATTERN = re.compile(r"^[a-z0-9_]+$")

SCOPE_TYPES = {"global", "channel", "store", "device"}

STATUS_RESPONSE_TYPES = {"ok", "not_modified", "error"}


def _validate_config_json(value: dict) -> dict:
    """Validate config_json: allowed keys, numeric ranges, MIME types, forbidden keys."""
    if not isinstance(value, dict):
        raise ValueError("config_json must be a JSON object")

    _check_forbidden_recursive(value)

    unknown = set(value.keys()) - ALLOWED_CONFIG_KEYS
    if unknown:
        raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")

    # Numeric validation
    for key, (lo, hi) in NUMERIC_RANGES.items():
        if key in value:
            v = value[key]
            if not isinstance(v, (int, float)) or v < lo or v > hi:
                raise ValueError(
                    f"{key} must be between {lo} and {hi}, got {v}"
                )

    # Log level
    if "log_level" in value:
        if value["log_level"] not in ALLOWED_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(ALLOWED_LOG_LEVELS)}"
            )

    # MIME types
    if "allowed_mime_types" in value:
        mimes = value["allowed_mime_types"]
        if not isinstance(mimes, list):
            raise ValueError("allowed_mime_types must be a list")
        invalid = set(mimes) - ALLOWED_MIME_TYPES
        if invalid:
            raise ValueError(
                f"Invalid MIME types: {', '.join(sorted(invalid))}"
            )

    # KSO safety
    if "kso_safety" in value:
        kso = value["kso_safety"]
        if not isinstance(kso, dict):
            raise ValueError("kso_safety must be an object")
        unknown_kso = set(kso.keys()) - ALLOWED_KSO_KEYS
        if unknown_kso:
            raise ValueError(
                f"Unknown kso_safety keys: {', '.join(sorted(unknown_kso))}"
            )
        for k, v in kso.items():
            if not isinstance(v, bool):
                raise ValueError(f"kso_safety.{k} must be boolean")

    return value


def _check_forbidden_recursive(obj, path=""):
    """Recursively check for forbidden keys in a JSON structure."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key.lower() in FORBIDDEN_CONFIG_KEYS:
                raise ValueError(
                    f"Forbidden key '{path}{key}' in configuration"
                )
            _check_forbidden_recursive(val, f"{path}{key}.")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_forbidden_recursive(item, f"{path}[{i}].")


def canonical_hash(obj: dict) -> str:
    """Compute canonical SHA-256 hash of a JSON-serializable dict."""
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


# ── Profile schemas ───────────────────────────────────────────────────


class RuntimeConfigProfileCreate(BaseModel):
    code: str = Field(
        ..., min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$",
    )
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    config_json: dict[str, Any]

    @field_validator("config_json")
    @classmethod
    def validate_config(cls, v):
        return _validate_config_json(v)

    model_config = {"from_attributes": True}


class RuntimeConfigProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    config_json: Optional[dict[str, Any]] = None

    @field_validator("config_json")
    @classmethod
    def validate_config(cls, v):
        if v is not None:
            return _validate_config_json(v)
        return v

    model_config = {"from_attributes": True}


class RuntimeConfigProfileResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    config_hash: str
    version: int
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = {"from_attributes": True}


# ── Assignment schemas ────────────────────────────────────────────────


class RuntimeConfigAssignmentCreate(BaseModel):
    profile_id: UUID
    scope_type: str = Field(..., min_length=1, max_length=10)
    gateway_device_id: Optional[UUID] = None
    store_id: Optional[UUID] = None
    channel_id: Optional[UUID] = None
    priority: int = Field(0, ge=0)

    @field_validator("scope_type")
    @classmethod
    def validate_scope(cls, v):
        if v not in SCOPE_TYPES:
            raise ValueError(f"scope_type must be one of {sorted(SCOPE_TYPES)}")
        return v

    @model_validator(mode="after")
    def validate_scope_combination(self):
        scope = self.scope_type
        dev = self.gateway_device_id
        store = self.store_id
        chan = self.channel_id

        if scope == "global":
            if dev or store or chan:
                raise ValueError(
                    "global assignment must not have device/store/channel"
                )
        elif scope == "channel":
            if not chan:
                raise ValueError("channel assignment requires channel_id")
            if dev or store:
                raise ValueError(
                    "channel assignment must not have device/store"
                )
        elif scope == "store":
            if not store:
                raise ValueError("store assignment requires store_id")
            if dev or chan:
                raise ValueError(
                    "store assignment must not have device/channel"
                )
        elif scope == "device":
            if not dev:
                raise ValueError("device assignment requires gateway_device_id")
            if store or chan:
                raise ValueError(
                    "device assignment must not have store/channel"
                )
        return self

    model_config = {"from_attributes": True}


class RuntimeConfigAssignmentUpdate(BaseModel):
    profile_id: Optional[UUID] = None
    priority: Optional[int] = Field(None, ge=0)

    model_config = {"from_attributes": True}


class RuntimeConfigAssignmentResponse(BaseModel):
    id: UUID
    profile_id: UUID
    scope_type: str
    gateway_device_id: Optional[UUID] = None
    store_id: Optional[UUID] = None
    channel_id: Optional[UUID] = None
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = {"from_attributes": True}


# ── Effective config schemas ──────────────────────────────────────────


class EffectiveConfigResponse(BaseModel):
    status: str = "ok"
    gateway_device_id: UUID
    config_hash: str
    config: dict[str, Any]
    profile_ids: list[UUID] = Field(default_factory=list)
    assignment_ids: list[UUID] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)


class DeviceConfigResponse(BaseModel):
    """Response for device gateway endpoint — no profile_ids."""
    status: str = "ok"
    gateway_device_id: UUID
    config_hash: str
    config: dict[str, Any]
    generated_at: datetime = Field(default_factory=_now)


# ── Request audit schemas ─────────────────────────────────────────────


class RuntimeConfigRequestResponse(BaseModel):
    id: UUID
    gateway_device_id: UUID
    config_profile_ids: list[UUID]
    effective_config_hash: str
    response_status: str
    requested_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════
#  Content Sync State (Step 20) — Admin response schemas
# ═══════════════════════════════════════════════════════════════════════


class DeviceSyncStateItem(BaseModel):
    """Device row in content-sync device list."""
    gateway_device_id: UUID
    device_code: str
    device_name: Optional[str] = None
    channel_id: UUID
    store_id: UUID
    status: str
    manifest_status: str
    manifest_version_id: Optional[UUID] = None
    manifest_hash: Optional[str] = None
    last_applied_at: Optional[datetime] = None
    last_failed_at: Optional[datetime] = None
    cached_items: int = 0
    missing_items: int = 0
    failed_items: int = 0
    invalid_hash_items: int = 0


class DeviceSyncStateDetail(BaseModel):
    """Detailed content-sync state for a single device."""
    gateway_device_id: UUID
    device_code: str
    device_name: Optional[str] = None
    channel_id: UUID
    store_id: UUID
    manifest_status: str
    manifest_version_id: Optional[UUID] = None
    manifest_hash: Optional[str] = None
    last_applied_at: Optional[datetime] = None
    last_failed_at: Optional[datetime] = None
    updated_at: datetime
    cache_summary: dict[str, int] = Field(default_factory=dict)
    recent_manifest_events: list[dict[str, Any]] = Field(default_factory=list)
    recent_cache_items: list[dict[str, Any]] = Field(default_factory=list)


class ManifestApplyEventResponse(BaseModel):
    id: UUID
    gateway_device_id: UUID
    manifest_version_id: UUID
    manifest_hash: str
    status: str
    device_reported_at: Optional[datetime] = None
    reported_at: datetime
    error_code: Optional[str] = None
    message: Optional[str] = None
    details_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class MediaCacheReportResponse(BaseModel):
    id: UUID
    gateway_device_id: UUID
    manifest_version_id: UUID
    manifest_hash: str
    total_items: int
    cached_count: int
    missing_count: int
    failed_count: int
    invalid_hash_count: int
    reported_at: datetime
    device_reported_at: Optional[datetime] = None
    details_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class MediaCacheItemResponse(BaseModel):
    id: UUID
    gateway_device_id: UUID
    manifest_item_id: UUID
    manifest_version_id: UUID
    rendition_id: Optional[UUID] = None
    expected_sha256: str
    reported_sha256: Optional[str] = None
    status: str
    file_size_bytes: Optional[int] = None
    cached_at: Optional[datetime] = None
    last_seen_at: datetime
    error_code: Optional[str] = None
    message: Optional[str] = None
    details_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}
