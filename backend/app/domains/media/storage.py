"""Media Library: MinIO object storage client.

Streaming upload — file read in chunks, SHA-256 computed incrementally,
uploaded via temporary file to avoid loading large files into memory.
"""

import hashlib
import os
import tempfile
import uuid
from pathlib import PurePath

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

# ── Allowed MIME types ───────────────────────────────────────────────
ALLOWED_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "video/mp4",
    "video/webm",
})

# ── Allowed extensions ───────────────────────────────────────────────
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webm"})

# ── Blocked dangerous extensions (rejected immediately, no MIME check) 
BLOCKED_EXTENSIONS = frozenset({
    ".html", ".htm", ".js", ".mjs", ".cjs",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".sh", ".bat", ".cmd",
    ".py", ".rb", ".pl", ".php", ".jar", ".class",
    ".svg",  # SVG can contain JS
})

# ── Max upload size (bytes) ──────────────────────────────────────────
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB

# ── KSO v1 Profile (physical test device) ───────────────────────────
KSO_PORTRAIT_WIDTH = 768
KSO_PORTRAIT_HEIGHT = 1024


def _get_client() -> Minio:
    """Return a configured Minio client from application settings."""
    settings = get_settings()
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


async def ensure_bucket() -> None:
    """Create the media bucket if it does not exist."""
    settings = get_settings()
    client = _get_client()
    found = client.bucket_exists(settings.MINIO_BUCKET)
    if not found:
        client.make_bucket(settings.MINIO_BUCKET)


def _safe_object_key(creative_id: str, version: int, original_filename: str) -> str:
    """Build a safe MinIO object key from untrusted parts.

    Pattern:  creatives/{creative_id}/{version}/{uuid}.{safe_ext}

    * Strips path traversal characters (/, \\, ..).
    * Uses only the extension from the original filename.
    * Generates a random UUID for the object name.
    * Limits extension length to 10 characters.
    """
    # Sanitise extension: last segment after the final dot, no path chars
    raw_suffix = PurePath(original_filename).suffix.lower()
    # Keep only alphanumeric + dot, max 10 chars
    safe_suffix = "".join(c for c in raw_suffix if c.isalnum() or c == ".")[:10]
    if not safe_suffix.startswith("."):
        safe_suffix = ".bin"

    obj_name = f"{uuid.uuid4().hex}{safe_suffix}"
    return f"creatives/{creative_id}/{version}/{obj_name}"


async def upload_to_minio(
    file_content: bytes,
    original_filename: str,
    creative_id: str,
    version: int,
) -> dict:
    """Upload file content to MinIO and return metadata.

    Returns dict with keys:
        file_path, mime_type, file_size, sha256

    The file is written to a temporary file first, then uploaded to MinIO
    with streaming. SHA-256 is computed during the initial write.

    Raises ValueError if the file type is not allowed or exceeds size limit.
    """
    await ensure_bucket()
    settings = get_settings()
    client = _get_client()

    # Build object key
    object_key = _safe_object_key(creative_id, version, original_filename)

    # Block dangerous extensions BEFORE MIME detection
    suffix = PurePath(original_filename).suffix.lower()
    if suffix in BLOCKED_EXTENSIONS:
        raise ValueError(
            f"Запрещённый тип файла: {suffix}. "
            f"Разрешены: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Determine content-type from the upload data
    # Pass full content — Pillow verify() needs the complete file for CRC validation
    content_type = _detect_mime_type(original_filename, file_content)

    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported media type: {content_type}. "
            f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )

    if len(file_content) > MAX_UPLOAD_SIZE:
        raise ValueError(
            f"File too large: {len(file_content)} bytes "
            f"(max {MAX_UPLOAD_SIZE} bytes)"
        )

    # Write to temporary file, compute SHA-256
    sha256_hash = hashlib.sha256()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".upload")
    try:
        tmp.write(file_content)
        tmp.flush()
        sha256_hash.update(file_content)
        tmp_path = tmp.name
    finally:
        tmp.close()

    sha256_hex = sha256_hash.hexdigest()
    file_size = len(file_content)

    try:
        # Upload to MinIO
        client.fput_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=object_key,
            file_path=tmp_path,
            content_type=content_type,
        )
    finally:
        os.unlink(tmp_path)

    return {
        "file_path": object_key,
        "mime_type": content_type,
        "file_size": file_size,
        "sha256": sha256_hex,
    }


def _detect_mime_type(filename: str, head: bytes) -> str:
    """Detect MIME type from extension + magic bytes.

    Priority:
    1. Extension check against allowlist
    2. Magic bytes for images (Pillow)
    3. Fallback: extension-based guess
    """
    suffix = PurePath(filename).suffix.lower()

    # Extension → MIME mapping
    ext_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
    }

    if suffix in ext_map:
        mime = ext_map[suffix]

        # For images: verify with Pillow
        if mime.startswith("image/"):
            try:
                from io import BytesIO
                from PIL import Image

                img = Image.open(BytesIO(head))
                img.verify()
                # Re-open after verify() for actual format detection
                img = Image.open(BytesIO(head))
                pillow_format = img.format
                if pillow_format == "JPEG":
                    return "image/jpeg"
                elif pillow_format == "PNG":
                    return "image/png"
                # If Pillow says something else, block it
                return "application/octet-stream"
            except Exception:
                return "application/octet-stream"

        # For video: trust extension + size check (no ffprobe yet)
        return mime

    return "application/octet-stream"


def verify_sha256(file_content: bytes, expected_sha256: str) -> bool:
    """Verify SHA-256 hash of file content matches expected value."""
    return hashlib.sha256(file_content).hexdigest() == expected_sha256
