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
