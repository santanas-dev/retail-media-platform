"""Media validation: MP4/WebM video and GIF validation for v1 KSO production.

Provides business-language validation errors (Russian) for all checks.
Uses ffprobe for video analysis. Gracefully handles ffprobe absence.

Profile: KSO_PORTRAIT_768x1024_v1 (768×1024 portrait).
"""

import json
import logging
import os
import struct
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from pathlib import PurePath

from PIL import Image

logger = logging.getLogger(__name__)

# ── KSO v1 Profile ─────────────────────────────────────────────────────────
KSO_PROFILE_WIDTH = 768
KSO_PROFILE_HEIGHT = 1024
MAX_FILE_SIZE_VIDEO = 100 * 1024 * 1024  # 100 MB for video
MAX_FILE_SIZE_GIF = 20 * 1024 * 1024     # 20 MB for GIF
MAX_VIDEO_DURATION_SEC = 30              # 30 seconds max
MAX_VIDEO_FPS = 30                       # 30 FPS max
MAX_GIF_FRAMES = 300                     # ~10 sec at 30fps
MAX_GIF_DURATION_SEC = 15               # 15 seconds max


# ── Allowed video codecs (v1 KSO) ──────────────────────────────────────────
ALLOWED_VIDEO_CODECS = frozenset({
    "h264",        # AVC / H.264
    "vp8",         # WebM
    "vp9",         # WebM
    "av1",         # Modern codec (future-proof)
})

# ── Allowed video containers ────────────────────────────────────────────────
ALLOWED_CONTAINERS = frozenset({"mp4", "webm", "mov"})

# ── Dangerous content detection ─────────────────────────────────────────────
MP4_MAGIC = b"ftyp"
WEBM_MAGIC = b"\x1a\x45\xdf\xa3"  # EBML header
GIF87A = b"GIF87a"
GIF89A = b"GIF89a"


# ═══════════════════════════════════════════════════════════════════════════
# Validation Result
# ═══════════════════════════════════════════════════════════════════════════

class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"  # ffprobe not available


@dataclass
class ValidationResult:
    """Structured validation result with business-language reasons."""
    status: ValidationStatus
    reasons: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.PASSED

    def add_reason(self, reason: str) -> None:
        self.reasons.append(reason)


# ═══════════════════════════════════════════════════════════════════════════
# File-level checks (content sniffing, corruption, size)
# ═══════════════════════════════════════════════════════════════════════════

def validate_file_integrity(content: bytes, expected_mime_prefix: str) -> ValidationResult:
    """Check file is not empty, not corrupted, and matches expected type."""
    result = ValidationResult(status=ValidationStatus.PASSED)

    if not content or len(content) == 0:
        result.status = ValidationStatus.FAILED
        result.add_reason("Файл пустой или повреждён")
        return result

    # Video magic bytes check
    if expected_mime_prefix == "video":
        head = content[:12]
        is_mp4 = len(head) >= 12 and (head[4:8] == MP4_MAGIC or head[:4] == b"\x00\x00\x00\x18")
        is_webm = head[:4] == WEBM_MAGIC

        if not is_mp4 and not is_webm:
            result.status = ValidationStatus.FAILED
            result.add_reason("Файл повреждён или не является видеофайлом")
            return result

    # GIF magic bytes check
    if expected_mime_prefix == "gif":
        if content[:6] not in (GIF87A, GIF89A):
            result.status = ValidationStatus.FAILED
            result.add_reason("Файл не является GIF-изображением или повреждён")
            return result

    return result


def validate_extension_mime_consistency(
    filename: str, content_type: str, allowed_map: dict
) -> ValidationResult:
    """Check file extension matches declared MIME type."""
    result = ValidationResult(status=ValidationStatus.PASSED)
    suffix = PurePath(filename).suffix.lower()

    expected = allowed_map.get(suffix)
    if expected and expected != content_type:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Несоответствие типа файла: расширение {suffix} не соответствует "
            f"заявленному типу {content_type}"
        )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# FFprobe bridge
# ═══════════════════════════════════════════════════════════════════════════

def _run_ffprobe(filepath: str, timeout: int = 30) -> dict | None:
    """Run ffprobe on a file and return parsed JSON output.

    Returns None if ffprobe is not available or fails.
    """
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                filepath,
            ],
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            logger.warning("ffprobe returned non-zero: %s", proc.stderr.decode()[:200])
            return None
        return json.loads(proc.stdout)
    except FileNotFoundError:
        logger.warning("ffprobe not installed — video validation skipped")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out after %ds", timeout)
        return None
    except json.JSONDecodeError:
        logger.warning("ffprobe returned invalid JSON")
        return None


def _find_video_stream(streams: list[dict]) -> dict | None:
    for s in streams:
        if s.get("codec_type") == "video":
            return s
    return None


def _find_audio_streams(streams: list[dict]) -> list[dict]:
    return [s for s in streams if s.get("codec_type") == "audio"]


def _parse_dimensions(video_stream: dict) -> tuple[int | None, int | None]:
    w = video_stream.get("width")
    h = video_stream.get("height")
    if w is not None and h is not None:
        return int(w), int(h)
    return None, None


def _parse_r_frame_rate(stream: dict) -> float | None:
    """Parse r_frame_rate string like '30000/1001' or '30/1'."""
    raw = stream.get("r_frame_rate", "")
    if not raw or "/" not in str(raw):
        # Try avg_frame_rate as fallback
        raw = stream.get("avg_frame_rate", "")
        if not raw or "/" not in str(raw):
            return None
    try:
        parts = str(raw).split("/")
        return float(parts[0]) / float(parts[1])
    except (ValueError, ZeroDivisionError):
        return None


def _parse_duration(ffprobe_data: dict) -> float | None:
    """Extract duration in seconds from ffprobe output."""
    fmt = ffprobe_data.get("format", {})
    dur_str = fmt.get("duration")
    if dur_str is not None:
        try:
            return float(dur_str)
        except (ValueError, TypeError):
            pass
    return None


def _parse_codec(video_stream: dict) -> str | None:
    codec = video_stream.get("codec_name", "")
    if codec:
        return codec.lower()
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Video Validation (MP4 / WebM)
# ═══════════════════════════════════════════════════════════════════════════

def validate_video(
    content: bytes,
    filename: str,
    content_type: str,
) -> ValidationResult:
    """Full production video validation for v1 KSO.

    Checks (in order):
    1. File integrity / magic bytes
    2. Extension ↔ MIME consistency
    3. File size ≤ 100 MB
    4. ffprobe analysis: container, codec, dimensions, duration, FPS, audio
    """
    result = ValidationResult(status=ValidationStatus.PASSED)

    # 1. Integrity
    integrity = validate_file_integrity(content, "video")
    if not integrity.is_valid:
        return integrity

    # 2. Extension ↔ MIME
    ext_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
    }
    ext_check = validate_extension_mime_consistency(filename, content_type, ext_map)
    if not ext_check.is_valid:
        return ext_check

    # 3. Size
    if len(content) > MAX_FILE_SIZE_VIDEO:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Файл слишком большой: {len(content)} байт "
            f"(максимум {MAX_FILE_SIZE_VIDEO // (1024*1024)} МБ)"
        )
        return result

    # 4. ffprobe analysis — write to temp file
    import tempfile
    suffix = PurePath(filename).suffix.lower()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(content)
        tmp.flush()
        tmp_path = tmp.name
    finally:
        tmp.close()

    try:
        ffprobe_data = _run_ffprobe(tmp_path)
    finally:
        os.unlink(tmp_path)

    if ffprobe_data is None:
        result.status = ValidationStatus.SKIPPED
        result.add_reason(
            "Проверка видео временно недоступна — ffprobe не найден. "
            "Загрузите файл повторно позже или обратитесь к администратору."
        )
        return result

    streams = ffprobe_data.get("streams", [])

    # 4a. Container
    fmt_name = ffprobe_data.get("format", {}).get("format_name", "")
    containers = set(fmt_name.lower().split(","))
    if not (containers & ALLOWED_CONTAINERS):
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Неверный формат файла: {fmt_name}. "
            f"Поддерживаются: {', '.join(sorted(ALLOWED_CONTAINERS))}"
        )
        return result

    # 4b. Video stream
    video_stream = _find_video_stream(streams)
    if video_stream is None:
        result.status = ValidationStatus.FAILED
        result.add_reason("Видеопоток не найден в файле")
        return result

    # 4c. Codec
    codec = _parse_codec(video_stream)
    result.metadata["codec"] = codec
    if codec and codec not in ALLOWED_VIDEO_CODECS:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Неподдерживаемый видеокодек: {codec}. "
            f"Разрешены: {', '.join(sorted(ALLOWED_VIDEO_CODECS))}"
        )
        return result

    # 4d. Dimensions
    width, height = _parse_dimensions(video_stream)
    result.metadata["width"] = width
    result.metadata["height"] = height
    if width is None or height is None:
        result.status = ValidationStatus.FAILED
        result.add_reason("Не удалось определить размер видео")
        return result

    if width != KSO_PROFILE_WIDTH or height != KSO_PROFILE_HEIGHT:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Размер ролика не подходит для экрана КСО: {width}×{height}. "
            f"Требуется {KSO_PROFILE_WIDTH}×{KSO_PROFILE_HEIGHT}"
        )
        return result

    # 4e. Duration
    duration = _parse_duration(ffprobe_data)
    result.metadata["duration_seconds"] = duration
    if duration is not None and duration > MAX_VIDEO_DURATION_SEC:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Видео слишком длинное: {duration:.1f} сек. "
            f"Максимум {MAX_VIDEO_DURATION_SEC} сек"
        )
        return result

    # 4f. FPS
    fps = _parse_r_frame_rate(video_stream)
    result.metadata["fps"] = fps
    if fps is not None and fps > MAX_VIDEO_FPS:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Слишком высокая частота кадров: {fps:.0f} FPS. "
            f"Максимум {MAX_VIDEO_FPS} FPS"
        )
        return result

    # 4g. Audio — must be absent for KSO
    audio_streams = _find_audio_streams(streams)
    if audio_streams:
        result.status = ValidationStatus.FAILED
        result.add_reason("В ролике есть звук — для КСО звук запрещён")
        return result

    # All checks passed
    result.metadata["container"] = fmt_name
    result.metadata["has_audio"] = False
    return result


# ═══════════════════════════════════════════════════════════════════════════
# GIF Validation
# ═══════════════════════════════════════════════════════════════════════════

def validate_gif(
    content: bytes,
    filename: str,
    content_type: str,
) -> ValidationResult:
    """Full production GIF validation for v1 KSO.

    Checks:
    1. File integrity / GIF signature
    2. Extension ↔ MIME consistency
    3. File size ≤ 20 MB
    4. Pillow analysis: dimensions, frame count, duration, corruption
    """
    result = ValidationResult(status=ValidationStatus.PASSED)

    # 1. Integrity
    integrity = validate_file_integrity(content, "gif")
    if not integrity.is_valid:
        return integrity

    # 2. Extension ↔ MIME
    if content_type not in ("image/gif",):
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Неверный тип файла: {content_type}. Ожидается image/gif"
        )
        return result

    suffix = PurePath(filename).suffix.lower()
    if suffix not in (".gif",):
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Расширение {suffix} не соответствует GIF. Ожидается .gif"
        )
        return result

    # 3. Size
    if len(content) > MAX_FILE_SIZE_GIF:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"GIF слишком большой: {len(content)} байт "
            f"(максимум {MAX_FILE_SIZE_GIF // (1024*1024)} МБ)"
        )
        return result

    # 4. Pillow analysis
    try:
        img = Image.open(BytesIO(content))
    except Exception:
        result.status = ValidationStatus.FAILED
        result.add_reason("Файл повреждён или не читается")
        return result

    # 4a. Dimensions
    width, height = img.size
    result.metadata["width"] = width
    result.metadata["height"] = height
    if width != KSO_PROFILE_WIDTH or height != KSO_PROFILE_HEIGHT:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Размер GIF не подходит для экрана КСО: {width}×{height}. "
            f"Требуется {KSO_PROFILE_WIDTH}×{KSO_PROFILE_HEIGHT}"
        )
        img.close()
        return result

    # 4b. Frame count
    frame_count = getattr(img, "n_frames", 1)
    result.metadata["frame_count"] = frame_count

    if frame_count > MAX_GIF_FRAMES:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"Слишком много кадров в GIF: {frame_count}. "
            f"Максимум {MAX_GIF_FRAMES}"
        )
        img.close()
        return result

    # 4c. Duration (GIF duration from frame delays)
    duration_ms = 0
    try:
        # Iterate frames to sum delays
        for i in range(frame_count):
            img.seek(i)
            duration_ms += img.info.get("duration", 100)  # default 100ms
    except EOFError:
        pass

    duration_sec = duration_ms / 1000.0
    result.metadata["duration_seconds"] = duration_sec

    if duration_sec > MAX_GIF_DURATION_SEC:
        result.status = ValidationStatus.FAILED
        result.add_reason(
            f"GIF слишком длинный: {duration_sec:.1f} сек. "
            f"Максимум {MAX_GIF_DURATION_SEC} сек"
        )
        img.close()
        return result

    # 4d. CPU/memory guard — file size is proxy
    # (actual CPU cost depends on decode, but size catches most)
    if len(content) > 10 * 1024 * 1024:
        logger.warning(
            "GIF size %d bytes exceeds recommended 10 MB — may be CPU-heavy on KSO",
            len(content),
        )

    img.close()
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Combined validation entry point
# ═══════════════════════════════════════════════════════════════════════════

def validate_creative_content(
    content: bytes,
    filename: str,
    content_type: str,
) -> ValidationResult:
    """Route to the correct validator based on content type."""
    if content_type.startswith("video/"):
        return validate_video(content, filename, content_type)
    elif content_type == "image/gif":
        return validate_gif(content, filename, content_type)
    else:
        # Image validation is handled inline in service.py (Pillow)
        result = ValidationResult(status=ValidationStatus.PASSED)
        # Quick dimension check
        try:
            img = Image.open(BytesIO(content))
            w, h = img.size
            if w != KSO_PROFILE_WIDTH or h != KSO_PROFILE_HEIGHT:
                result.status = ValidationStatus.FAILED
                result.add_reason(
                    f"Размер изображения не подходит: {w}×{h}. "
                    f"Требуется {KSO_PROFILE_WIDTH}×{KSO_PROFILE_HEIGHT}"
                )
            result.metadata["width"] = w
            result.metadata["height"] = h
            img.close()
        except Exception:
            result.status = ValidationStatus.FAILED
            result.add_reason("Файл повреждён или не читается")
        return result
