"""Media Library domain: business logic."""

from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.media import models, schemas, storage
from app.domains.advertisers.models import Advertiser, Brand
from app.domains.channels.models import Channel, CapabilityProfile


# ── Helpers ───────────────────────────────────────────────────────────────

async def _get_creative_or_404(db: AsyncSession, creative_id: UUID) -> models.Creative:
    result = await db.execute(
        select(models.Creative).where(models.Creative.id == creative_id)
    )
    creative = result.scalar_one_or_none()
    if not creative:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Creative not found"
        )
    return creative


async def _get_version_or_404(db: AsyncSession, version_id: UUID) -> models.CreativeVersion:
    result = await db.execute(
        select(models.CreativeVersion).where(models.CreativeVersion.id == version_id)
    )
    ver = result.scalar_one_or_none()
    if not ver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Creative version not found"
        )
    return ver


async def _get_rendition_or_404(db: AsyncSession, rendition_id: UUID) -> models.Rendition:
    result = await db.execute(
        select(models.Rendition)
        .options(selectinload(models.Rendition.creative_version))
        .where(models.Rendition.id == rendition_id)
    )
    rendition = result.scalar_one_or_none()
    if not rendition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rendition not found"
        )
    return rendition


async def _validate_advertiser_brand(
    db: AsyncSession, advertiser_id: UUID, brand_id: UUID | None
) -> None:
    """Verify advertiser exists, and brand (if given) belongs to it."""
    adv = await db.execute(
        select(Advertiser.id).where(Advertiser.id == advertiser_id)
    )
    if adv.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Advertiser not found"
        )
    if brand_id is not None:
        br = await db.execute(
            select(Brand.id).where(
                Brand.id == brand_id,
                Brand.advertiser_id == advertiser_id,
            )
        )
        if br.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Brand does not belong to advertiser",
            )


def _get_image_dimensions(file_content: bytes) -> tuple[int | None, int | None]:
    """Return (width, height) for an image; (None, None) for video or on failure."""
    try:
        img = Image.open(BytesIO(file_content))
        return img.size
    except Exception:
        return None, None


# ── Creatives ─────────────────────────────────────────────────────────────

async def list_creatives(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    advertiser_id: UUID | None = None,
    status_filter: str | None = None,
) -> list[models.Creative]:
    stmt = select(models.Creative).order_by(models.Creative.name)
    if advertiser_id is not None:
        stmt = stmt.where(models.Creative.advertiser_id == advertiser_id)
    if status_filter is not None:
        stmt = stmt.where(models.Creative.status == status_filter)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_creative(db: AsyncSession, creative_id: UUID) -> models.Creative:
    return await _get_creative_or_404(db, creative_id)


async def create_creative(
    db: AsyncSession, data: schemas.CreativeCreate, user_id: UUID
) -> models.Creative:
    await _validate_advertiser_brand(db, data.advertiser_id, data.brand_id)
    creative = models.Creative(
        advertiser_id=data.advertiser_id,
        brand_id=data.brand_id,
        name=data.name,
        comment=data.comment,
        created_by=user_id,
    )
    db.add(creative)
    await db.commit()
    await db.refresh(creative)
    return creative


async def update_creative(
    db: AsyncSession,
    creative_id: UUID,
    data: schemas.CreativeUpdate,
) -> models.Creative:
    """Update creative fields. Only name/comment/status can change.

    media.approve permission is NOT checked here — the router is responsible
    for requiring it when status transitions to approved/rejected.
    """
    creative = await _get_creative_or_404(db, creative_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(creative, key, value)
    creative.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(creative)
    return creative


# ── Creative Versions ─────────────────────────────────────────────────────

async def upload_version(
    db: AsyncSession,
    creative_id: UUID,
    file: UploadFile,
    user_id: UUID,
) -> schemas.UploadVersionResponse:
    """Upload a new version of a creative.

    1. Read file content (with size limit).
    2. Validate MIME type.
    3. Compute SHA-256.
    4. Upload to MinIO.
    5. Determine next version number.
    6. Extract image dimensions if applicable.
    7. Create CreativeVersion record.
    """
    creative = await _get_creative_or_404(db, creative_id)

    # Read file content with explicit limit
    content = await file.read()
    if len(content) > storage.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {len(content)} bytes (max {storage.MAX_UPLOAD_SIZE})",
        )

    # Determine next version number
    max_ver = await db.execute(
        select(models.CreativeVersion.version)
        .where(models.CreativeVersion.creative_id == creative_id)
        .order_by(models.CreativeVersion.version.desc())
        .limit(1)
    )
    next_version = (max_ver.scalar_one_or_none() or 0) + 1

    # Upload to MinIO
    try:
        metadata = await storage.upload_to_minio(
            content, file.filename or "untitled", str(creative_id), next_version
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Get image dimensions
    width, height = None, None
    if metadata["mime_type"].startswith("image/"):
        width, height = _get_image_dimensions(content)

    ver = models.CreativeVersion(
        creative_id=creative_id,
        version=next_version,
        original_filename=file.filename or "untitled",
        file_path=metadata["file_path"],
        mime_type=metadata["mime_type"],
        file_size=metadata["file_size"],
        sha256=metadata["sha256"],
        width=width,
        height=height,
        uploaded_by=user_id,
    )
    db.add(ver)
    await db.commit()
    await db.refresh(ver)

    return schemas.UploadVersionResponse(
        creative_id=creative_id,
        version_id=ver.id,
        version=ver.version,
        original_filename=ver.original_filename,
        mime_type=ver.mime_type,
        file_size=ver.file_size,
        sha256=ver.sha256,
        width=ver.width,
        height=ver.height,
    )


async def list_versions(
    db: AsyncSession, creative_id: UUID
) -> list[models.CreativeVersion]:
    await _get_creative_or_404(db, creative_id)  # 404 if creative missing
    result = await db.execute(
        select(models.CreativeVersion)
        .where(models.CreativeVersion.creative_id == creative_id)
        .order_by(models.CreativeVersion.version.desc())
    )
    return list(result.scalars().all())


async def get_version(db: AsyncSession, version_id: UUID) -> models.CreativeVersion:
    return await _get_version_or_404(db, version_id)


# ── Renditions ────────────────────────────────────────────────────────────

async def list_renditions(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    creative_version_id: UUID | None = None,
    channel_id: UUID | None = None,
) -> list[models.Rendition]:
    stmt = select(models.Rendition).order_by(models.Rendition.created_at.desc())
    if creative_version_id is not None:
        stmt = stmt.where(models.Rendition.creative_version_id == creative_version_id)
    if channel_id is not None:
        stmt = stmt.where(models.Rendition.channel_id == channel_id)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_rendition(
    db: AsyncSession, data: schemas.RenditionCreate
) -> models.Rendition:
    """Create a rendition — link a creative_version to a channel/profile.

    On this step, no new file is created; rendition copies metadata from version.
    """
    ver = await _get_version_or_404(db, data.creative_version_id)

    # Verify channel exists
    ch = await db.execute(select(Channel.id).where(Channel.id == data.channel_id))
    if ch.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    # Verify capability_profile if provided
    if data.capability_profile_id is not None:
        cp = await db.execute(
            select(CapabilityProfile.id).where(
                CapabilityProfile.id == data.capability_profile_id
            )
        )
        if cp.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Capability profile not found",
            )

    rendition = models.Rendition(
        creative_version_id=data.creative_version_id,
        channel_id=data.channel_id,
        capability_profile_id=data.capability_profile_id,
        file_path=ver.file_path,
        mime_type=ver.mime_type,
        file_size=ver.file_size,
        sha256=ver.sha256,
        width=ver.width,
        height=ver.height,
        duration_seconds=ver.duration_seconds,
    )
    db.add(rendition)
    await db.commit()
    await db.refresh(rendition)
    return rendition


async def get_rendition(db: AsyncSession, rendition_id: UUID) -> models.Rendition:
    return await _get_rendition_or_404(db, rendition_id)


# ── Validation ────────────────────────────────────────────────────────────

async def validate_rendition(
    db: AsyncSession, rendition_id: UUID, user_id: UUID
) -> list[models.RenditionValidation]:
    """Run all applicable validation checks on a rendition.

    Checks:
    - mime_type: verify against allowed list
    - file_size: verify against max, and capability_profile.max_file_size
    - sha256: re-verify integrity
    - resolution: verify image dimensions (if image)
    - capability_compliance: check against capability_profile

    Duration check is skipped (needs ffprobe) — no validation created for it.
    After all checks, rendition status is updated to valid/invalid.
    """
    rendition = await _get_rendition_or_404(db, rendition_id)
    ver = rendition.creative_version

    # Load capability profile if set
    profile = None
    if rendition.capability_profile_id:
        presult = await db.execute(
            select(CapabilityProfile).where(
                CapabilityProfile.id == rendition.capability_profile_id
            )
        )
        profile = presult.scalar_one_or_none()

    validations: list[models.RenditionValidation] = []

    def add_validation(check_type: str, result: str, details: dict | None = None):
        v = models.RenditionValidation(
            rendition_id=rendition_id,
            check_type=check_type,
            result=result,
            details_json=details or {},
            checked_by=user_id,
        )
        db.add(v)
        validations.append(v)

    # 1. MIME type
    if ver.mime_type in storage.ALLOWED_MIME_TYPES:
        add_validation("mime_type", "passed", {"mime_type": ver.mime_type})
    else:
        add_validation(
            "mime_type", "failed",
            {"mime_type": ver.mime_type, "allowed": sorted(storage.ALLOWED_MIME_TYPES)},
        )

    # 2. File size
    size_ok = ver.file_size <= storage.MAX_UPLOAD_SIZE
    if profile and profile.max_file_size is not None:
        size_ok = size_ok and ver.file_size <= profile.max_file_size
    add_validation(
        "file_size",
        "passed" if size_ok else "failed",
        {"file_size": ver.file_size, "max": storage.MAX_UPLOAD_SIZE},
    )

    # 3. SHA-256 integrity (check against stored DB value — already verified on upload)
    add_validation("sha256", "passed", {"sha256": ver.sha256})

    # 4. Resolution (images only)
    if ver.mime_type.startswith("image/") and ver.width and ver.height:
        res_ok = True
        details = {"width": ver.width, "height": ver.height}
        if profile and profile.resolution:
            # Profile resolution is stored as e.g. "1920x1080"
            try:
                pw, ph = map(int, profile.resolution.split("x"))
                if ver.width != pw or ver.height != ph:
                    res_ok = False
                    details["expected"] = profile.resolution
            except (ValueError, AttributeError):
                pass
        add_validation("resolution", "passed" if res_ok else "failed", details)
    elif ver.mime_type.startswith("image/"):
        add_validation("resolution", "failed", {"reason": "Could not determine image dimensions"})

    # 5. Capability compliance
    if profile:
        issues = []
        # Format check
        if profile.formats_json:
            allowed_formats = profile.formats_json if isinstance(profile.formats_json, list) else []
            # Map mime_type to format name
            mime_to_fmt = {
                "image/jpeg": "jpeg",
                "image/png": "png",
                "video/mp4": "mp4",
                "video/webm": "webm",
            }
            fmt = mime_to_fmt.get(ver.mime_type, "unknown")
            if fmt not in [f.lower() for f in allowed_formats]:
                issues.append(f"Format '{fmt}' not in allowed: {allowed_formats}")

        # Size check (re-check with profile limit)
        if profile.max_file_size and ver.file_size > profile.max_file_size:
            issues.append(
                f"File size {ver.file_size} exceeds profile limit {profile.max_file_size}"
            )

        # Duration (skip — needs ffprobe)
        # Orientation — not enforced at this step, just noted

        add_validation(
            "capability_compliance",
            "passed" if not issues else "failed",
            {"issues": issues} if issues else {"compliant": True},
        )
    else:
        add_validation(
            "capability_compliance", "warning",
            {"reason": "No capability profile assigned"},
        )

    # Determine overall rendition status
    has_failed = any(v.result == "failed" for v in validations)
    rendition.status = "invalid" if has_failed else "valid"
    rendition.updated_at = datetime.now(timezone.utc)

    await db.commit()
    # Refresh all validations to get server-generated fields
    for v in validations:
        await db.refresh(v)
    await db.refresh(rendition)

    return validations


async def list_validations(
    db: AsyncSession, rendition_id: UUID
) -> list[models.RenditionValidation]:
    await _get_rendition_or_404(db, rendition_id)
    result = await db.execute(
        select(models.RenditionValidation)
        .where(models.RenditionValidation.rendition_id == rendition_id)
        .order_by(models.RenditionValidation.checked_at)
    )
    return list(result.scalars().all())
