"""Media Library domain: Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Creative ──────────────────────────────────────────────────────────────

class CreativeCreate(BaseModel):
    advertiser_id: UUID | None = None  # Nullable for one-KSO pilot
    brand_id: UUID | None = None
    creative_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    comment: str | None = None


class CreativeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = Field(
        None, pattern=r"^(draft|pending_review|validation_failed|in_review|approved|rejected|archived)$"
    )
    comment: str | None = None


class CreativeResponse(BaseModel):
    id: UUID
    advertiser_id: UUID | None
    advertiser_code: str | None = None
    advertiser_name: str | None = None
    brand_id: UUID | None
    creative_code: str
    name: str
    status: str
    scan_status: str = "not_configured"
    comment: str | None
    content_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    file_size_bytes: int | None = None
    current_version: int | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class CreativeSafeResponse(BaseModel):
    """Safe creative response for portal — no internal IDs, no file_path, no sha256."""
    creative_code: str
    name: str
    status: str
    content_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    file_size_bytes: int | None = None
    created_at: datetime | None = None


class CreativeUploadRequest(BaseModel):
    """Combined creative create + upload request (Step 37.3)."""
    creative_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)


class CreativeUploadResponse(BaseModel):
    """Response after successful creative upload — no file_path, no sha256."""
    creative_code: str
    name: str
    status: str
    content_type: str
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    file_size_bytes: int
    version: int


# ── CreativeVersion ───────────────────────────────────────────────────────

class CreativeVersionResponse(BaseModel):
    id: UUID
    creative_id: UUID
    version: int
    original_filename: str
    file_path: str
    mime_type: str
    file_size: int
    sha256: str
    width: int | None
    height: int | None
    duration_seconds: float | None
    uploaded_by: UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadVersionResponse(BaseModel):
    creative_id: UUID
    version_id: UUID
    version: int
    original_filename: str
    mime_type: str
    file_size: int
    sha256: str
    width: int | None
    height: int | None


# ── Rendition ─────────────────────────────────────────────────────────────

class RenditionCreate(BaseModel):
    creative_version_id: UUID
    channel_id: UUID
    capability_profile_id: UUID | None = None


class RenditionResponse(BaseModel):
    id: UUID
    creative_version_id: UUID
    channel_id: UUID
    capability_profile_id: UUID | None
    file_path: str
    mime_type: str
    file_size: int
    sha256: str
    width: int | None
    height: int | None
    duration_seconds: float | None
    status: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── RenditionValidation ───────────────────────────────────────────────────

class ValidationResponse(BaseModel):
    id: UUID
    rendition_id: UUID
    check_type: str
    result: str
    details_json: dict
    checked_by: UUID
    checked_at: datetime

    model_config = {"from_attributes": True}


# ── Moderation (44.2) ──────────────────────────────────────────────────────

class ModerationAction(BaseModel):
    action: str = Field(pattern=r"^(approve|reject|submit_review|return_for_rework)$")
    reason_code: str | None = Field(None, max_length=50)
    comment: str | None = Field(None, max_length=500)


class ModerationResponse(BaseModel):
    creative_code: str
    status: str
    action: str
    comment: str | None = None
    ok: bool = True


class ModerationQueueItem(BaseModel):
    """Item in the moderation queue — safe for portal display."""
    creative_code: str
    name: str
    status: str
    scan_status: str = "not_configured"
    content_type: str | None = None
    width: int | None = None
    height: int | None = None
    file_size_bytes: int | None = None
    created_by: str | None = None  # username
    created_at: str | None = None
    rejection_reason: str | None = None
    can_use_in_campaign: bool = False


class AVReadinessResponse(BaseModel):
    """AV scanner production readiness check — safe for admin UI."""
    scanner_available: bool = False
    scanner_name: str = "none"
    readiness: str = "not_configured"  # ready | not_configured | unavailable | error
    message: str = ""
    production_ready: bool = False
    notes: list[str] = []


# ── Creative QA Policy (44.2) ──────────────────────────────────────────────

class CreativePolicyResponse(BaseModel):
    profile: str = "KSO_PORTRAIT_768x1024_v1"
    av_policy_mode: str = "pilot_dev"
    require_av_clean_for_publication: bool = False
    allowed_mime_types: list[str] = ["image/jpeg", "image/png"]
    allowed_extensions: list[str] = [".jpg", ".jpeg", ".png"]
    required_width: int = 768
    required_height: int = 1024
    max_file_size_bytes: int = 50 * 1024 * 1024
    blocked_extensions: list[str] = [
        ".html", ".htm", ".js", ".svg",
        ".zip", ".tar", ".gz", ".exe", ".dll", ".sh",
    ]
    deferred_types: list[str] = ["video/mp4", "video/webm", "image/gif"]
    av_scanner: str = "not_configured"
    notes: list[str] = [
        "Режим AV: pilot/dev — публикация разрешена без проверки безопасности после ручной модерации",
        "В production режиме (av_policy_mode=production) без AV scan clean публикация запрещена",
        "Fake AV pass запрещён — scan_status clean не выставляется автоматически без реального сканера",
        "Видео отложено до отдельного шага валидации (требуется проверка кодека, длительности, звука)",
        "GIF отложен — нет проверки длительности/CPU",
        "HTML5/JS/ZIP/исполняемые — запрещены без решения ИБ",
        "SVG запрещён — может содержать JavaScript",
    ]
