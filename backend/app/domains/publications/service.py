"""Manifest & Publication Core: business logic."""

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.domains.publications import models, schemas

# ── Forbidden keys — must never appear in manifest_json ───────────

FORBIDDEN_MANIFEST_KEYS = frozenset({
    "access_token",
    "refresh_token",
    "token",
    "jwt",
    "password",
    "secret",
    "credential",
    "credentials",
    "authorization",
    "cookie",
    "api_key",
    "private_key",
    "public_key",
})

# ── Allowed MIME types for first release ──────────────────────────

ALLOWED_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "video/mp4",
    "video/webm",
})

# ── Helpers ────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _compute_manifest_hash(manifest_json: dict) -> str:
    """SHA-256 of canonical JSON."""
    canonical = json.dumps(
        manifest_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_manifest_json(obj: dict, path: str = "") -> list[str]:
    """Recursively check no forbidden keys in manifest_json."""
    hits: list[str] = []
    for key, value in obj.items():
        if key.lower() in FORBIDDEN_MANIFEST_KEYS:
            hits.append(f"{path}.{key}" if path else key)
        if isinstance(value, dict):
            hits.extend(_validate_manifest_json(value, f"{path}.{key}" if path else key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    hits.extend(
                        _validate_manifest_json(
                            item, f"{path}.{key}[{i}]" if path else f"{key}[{i}]",
                        )
                    )
    return hits


def _check_manifest_size(manifest_json: dict) -> tuple[bool, int]:
    """Check canonical JSON size against MAX_MANIFEST_JSON_BYTES."""
    settings = get_settings()
    canonical = json.dumps(
        manifest_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    size = len(canonical.encode("utf-8"))
    return size <= settings.MAX_MANIFEST_JSON_BYTES, size


# ── Event logging ──────────────────────────────────────────────────


async def _log_event(
    db: AsyncSession,
    batch_id: UUID,
    event_type: str,
    actor_user_id: UUID | None,
    message: str,
    details_json: dict | None = None,
) -> None:
    event = models.PublicationEvent(
        publication_batch_id=batch_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        message=message,
        details_json=details_json or {},
    )
    db.add(event)


# ── Batch CRUD ─────────────────────────────────────────────────────


async def create_batch(
    db: AsyncSession,
    data: schemas.PublicationBatchCreate,
    user_id: UUID,
) -> models.PublicationBatch:
    """Create a new publication batch from an approved schedule_run."""

    # Load schedule_run with related data
    from app.domains.scheduling.models import ScheduleRun
    from app.domains.inventory.models import CampaignBooking
    from app.domains.campaigns.models import Campaign

    run_result = await db.execute(
        select(ScheduleRun)
        .where(ScheduleRun.id == UUID(data.schedule_run_id))
        .options(
            selectinload(ScheduleRun.items),
            selectinload(ScheduleRun.conflicts),
        )
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Schedule run not found")
    if run.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Schedule run must be approved to create a publication batch",
        )

    # Check campaign
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == run.campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign or campaign.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Campaign must be approved for publication",
        )

    # Check booking
    booking_result = await db.execute(
        select(CampaignBooking).where(CampaignBooking.id == run.booking_id)
    )
    booking = booking_result.scalar_one_or_none()
    if not booking or booking.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Booking must be confirmed for publication",
        )

    # Idempotency: no new batch if published/approved one already exists
    existing = await db.execute(
        select(models.PublicationBatch).where(
            models.PublicationBatch.schedule_run_id == UUID(data.schedule_run_id),
            models.PublicationBatch.status.in_(["published"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Schedule run already has a published batch",
        )

    existing_approved = await db.execute(
        select(models.PublicationBatch).where(
            models.PublicationBatch.schedule_run_id == UUID(data.schedule_run_id),
            models.PublicationBatch.status == "approved",
        )
    )
    if existing_approved.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Schedule run has an approved batch — cancel it first",
        )

    batch = models.PublicationBatch(
        schedule_run_id=UUID(data.schedule_run_id),
        campaign_id=run.campaign_id,
        booking_id=run.booking_id,
        status="draft",
        comment=data.comment,
        created_by=user_id,
    )
    db.add(batch)
    await db.flush()

    await _log_event(
        db, batch.id, "batch_created", user_id,
        "Publication batch created",
        {"schedule_run_id": data.schedule_run_id},
    )
    await db.commit()
    await db.refresh(batch)
    return batch


async def list_batches(
    db: AsyncSession,
    schedule_run_id: UUID | None = None,
    campaign_id: UUID | None = None,
    status: str | None = None,
) -> list[models.PublicationBatch]:
    stmt = select(models.PublicationBatch).order_by(models.PublicationBatch.created_at.desc())
    if schedule_run_id:
        stmt = stmt.where(models.PublicationBatch.schedule_run_id == schedule_run_id)
    if campaign_id:
        stmt = stmt.where(models.PublicationBatch.campaign_id == campaign_id)
    if status:
        stmt = stmt.where(models.PublicationBatch.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_batch(
    db: AsyncSession, batch_id: UUID,
) -> models.PublicationBatch:
    batch = await db.get(models.PublicationBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Publication batch not found")
    return batch


# ── Generate manifests ─────────────────────────────────────────────


async def generate_manifests(
    db: AsyncSession,
    batch: models.PublicationBatch,
    user_id: UUID,
) -> models.PublicationBatch:
    """Generate manifest versions and items for all schedule_items."""

    from app.domains.scheduling.models import ScheduleRun, ScheduleItem
    from app.domains.campaigns.models import Campaign, CampaignRendition
    from app.domains.inventory.models import InventoryUnit
    from app.domains.media.models import Creative, CreativeVersion, Rendition
    from app.domains.organization.models import Store
    from app.domains.channels.models import Channel

    if batch.status not in ("approved",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate manifests: batch is '{batch.status}' "
                   f"(must be 'approved'). Request approval first.",
        )

    # Load schedule_run with items
    run_result = await db.execute(
        select(ScheduleRun)
        .where(ScheduleRun.id == batch.schedule_run_id)
        .options(selectinload(ScheduleRun.items))
    )
    run = run_result.scalar_one_or_none()
    if not run or run.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Schedule run must be approved to generate manifests",
        )

    # Load campaign
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == batch.campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign or campaign.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Campaign must be approved",
        )

    # Load active schedule_items
    item_result = await db.execute(
        select(ScheduleItem)
        .where(
            ScheduleItem.schedule_run_id == batch.schedule_run_id,
            ScheduleItem.status == "active",
        )
        .order_by(ScheduleItem.date, ScheduleItem.loop_position, ScheduleItem.spot_position)
    )
    items = list(item_result.scalars().all())

    if not items:
        await _log_event(
            db, batch.id, "manifest_generation_failed", user_id,
            "No active schedule items found",
        )
        batch.status = "failed"
        batch.updated_at = _now()
        await db.commit()
        await db.refresh(batch)
        return batch

    # Bulk-load related data
    rendition_ids = {item.rendition_id for item in items}
    creative_version_ids: set[UUID] = set()
    inventory_unit_ids = {item.inventory_unit_id for item in items}
    campaign_rendition_ids = {item.campaign_rendition_id for item in items}

    # Load renditions
    renditions_result = await db.execute(
        select(Rendition).where(Rendition.id.in_(rendition_ids))
    )
    renditions_by_id: dict[UUID, Rendition] = {r.id: r for r in renditions_result.scalars().all()}

    for r in renditions_by_id.values():
        creative_version_ids.add(r.creative_version_id)

    # Load creative_versions
    cv_result = await db.execute(
        select(CreativeVersion).where(CreativeVersion.id.in_(creative_version_ids))
    )
    cv_by_id: dict[UUID, CreativeVersion] = {cv.id: cv for cv in cv_result.scalars().all()}

    creative_ids = {cv.creative_id for cv in cv_by_id.values()}

    # Load creatives
    creative_result = await db.execute(
        select(Creative).where(Creative.id.in_(creative_ids))
    )
    creatives_by_id: dict[UUID, Creative] = {c.id: c for c in creative_result.scalars().all()}

    # Load inventory_units
    iu_result = await db.execute(
        select(InventoryUnit).where(InventoryUnit.id.in_(inventory_unit_ids))
    )
    iu_by_id: dict[UUID, InventoryUnit] = {iu.id: iu for iu in iu_result.scalars().all()}

    # Load campaign_renditions
    cr_result = await db.execute(
        select(CampaignRendition).where(CampaignRendition.id.in_(campaign_rendition_ids))
    )
    cr_by_id: dict[UUID, CampaignRendition] = {
        cr.id: cr for cr in cr_result.scalars().all()
    }

    # Load stores
    store_ids = {iu_by_id[iid].store_id for iid in inventory_unit_ids if iid in iu_by_id}
    store_result = await db.execute(
        select(Store).where(Store.id.in_(store_ids))
    )
    stores_by_id: dict[UUID, Store] = {s.id: s for s in store_result.scalars().all()}

    # Load channels
    channel_ids = {iu_by_id[iid].channel_id for iid in inventory_unit_ids if iid in iu_by_id}
    channel_result = await db.execute(
        select(Channel).where(Channel.id.in_(channel_ids))
    )
    channels_by_id: dict[UUID, Channel] = {ch.id: ch for ch in channel_result.scalars().all()}

    # Validate items
    validation_errors: list[str] = []
    for item in items:
        rendition = renditions_by_id.get(item.rendition_id)
        if not rendition:
            validation_errors.append(
                f"Schedule item {item.id}: rendition {item.rendition_id} not found"
            )
            continue
        if rendition.status != "valid":
            validation_errors.append(
                f"Schedule item {item.id}: rendition {item.rendition_id} status is '{rendition.status}' (expected 'valid')"
            )
            continue

        cv = cv_by_id.get(rendition.creative_version_id)
        if not cv:
            validation_errors.append(
                f"Schedule item {item.id}: creative_version not found"
            )
            continue

        creative = creatives_by_id.get(cv.creative_id)
        if not creative:
            validation_errors.append(
                f"Schedule item {item.id}: creative not found"
            )
            continue
        if creative.status != "approved":
            validation_errors.append(
                f"Schedule item {item.id}: creative {creative.id} status is '{creative.status}' (expected 'approved')"
            )
            continue

        if not rendition.file_path:
            validation_errors.append(
                f"Schedule item {item.id}: rendition file_path is empty"
            )
            continue
        if not rendition.sha256:
            validation_errors.append(
                f"Schedule item {item.id}: rendition sha256 is empty"
            )
            continue
        if rendition.mime_type not in ALLOWED_MIME_TYPES:
            validation_errors.append(
                f"Schedule item {item.id}: rendition mime_type '{rendition.mime_type}' not allowed"
            )
            continue

        iu = iu_by_id.get(item.inventory_unit_id)
        if not iu:
            validation_errors.append(
                f"Schedule item {item.id}: inventory_unit {item.inventory_unit_id} not found"
            )
            continue
        if iu.status != "active":
            validation_errors.append(
                f"Schedule item {item.id}: inventory_unit {item.inventory_unit_id} status is '{iu.status}'"
            )
            continue
        if not iu.is_sellable:
            validation_errors.append(
                f"Schedule item {item.id}: inventory_unit {item.inventory_unit_id} is not sellable"
            )
            continue

    if validation_errors:
        error_msg = "; ".join(validation_errors)
        await _log_event(
            db, batch.id, "validation_failed", user_id,
            error_msg,
            {"errors": validation_errors},
        )
        await _log_event(
            db, batch.id, "manifest_generation_failed", user_id,
            "Generation failed due to validation errors",
        )
        batch.status = "failed"
        batch.updated_at = _now()
        await db.commit()
        await db.refresh(batch)
        return batch

    # Cancel old manifest_versions for regenerated batch
    if batch.status == "generated":
        old_versions = await db.execute(
            select(models.ManifestVersion).where(
                models.ManifestVersion.publication_batch_id == batch.id,
                models.ManifestVersion.status.in_(["draft"]),
            )
        )
        for old in old_versions.scalars().all():
            old.status = "cancelled"

    # Group items by target key
    groups: dict[tuple, list[ScheduleItem]] = defaultdict(list)
    for item in items:
        iu = iu_by_id[item.inventory_unit_id]
        key = (
            item.inventory_unit_id,
            iu.logical_carrier_id,
            iu.display_surface_id,
            iu.channel_id,
            iu.store_id,
        )
        groups[key].append(item)

    # Create/update targets
    target_ids: dict[tuple, UUID] = {}
    for key in groups:
        inv_id, lc_id, ds_id, ch_id, st_id = key
        # Try to find existing target
        target_result = await db.execute(
            select(models.PublicationTarget).where(
                models.PublicationTarget.publication_batch_id == batch.id,
                models.PublicationTarget.inventory_unit_id == inv_id,
            )
        )
        target = target_result.scalar_one_or_none()
        if not target:
            target = models.PublicationTarget(
                publication_batch_id=batch.id,
                inventory_unit_id=inv_id,
                logical_carrier_id=lc_id,
                display_surface_id=ds_id,
                channel_id=ch_id,
                store_id=st_id,
                status="generated",
            )
            db.add(target)
            await db.flush()
        else:
            target.status = "generated"
            target.logical_carrier_id = lc_id
            target.display_surface_id = ds_id
            target.updated_at = _now()

        target_ids[key] = target.id

    # Build manifests
    total_items = 0
    total_manifests = 0
    for key, group_items in groups.items():
        inv_id, lc_id, ds_id, ch_id, st_id = key
        target_id = target_ids[key]

        iu = iu_by_id[inv_id]
        store = stores_by_id.get(st_id)
        channel = channels_by_id.get(ch_id)

        # Determine next version
        max_ver_result = await db.execute(
            select(models.ManifestVersion.manifest_version)
            .where(models.ManifestVersion.publication_target_id == target_id)
            .order_by(models.ManifestVersion.manifest_version.desc())
            .limit(1)
        )
        max_ver = max_ver_result.scalar() or 0
        new_version = max_ver + 1

        # Build manifest items list
        manifest_items_list: list[dict] = []
        for item in group_items:
            rendition = renditions_by_id[item.rendition_id]
            cv = cv_by_id[rendition.creative_version_id]
            cr = cr_by_id.get(item.campaign_rendition_id)

            manifest_items_list.append({
                "date": item.date.isoformat(),
                "time_from": item.time_from.isoformat(),
                "time_to": item.time_to.isoformat(),
                "loop_position": item.loop_position,
                "spot_position": item.spot_position,
                "media": {
                    "path": rendition.file_path,
                    "sha256": rendition.sha256,
                    "mime_type": rendition.mime_type,
                    "width": rendition.width,
                    "height": rendition.height,
                    "duration_seconds": rendition.duration_seconds,
                },
                "campaign": {
                    "id": str(item.campaign_id),
                    "code": campaign.name if campaign else None,
                },
                "rendition_id": str(item.rendition_id),
                "campaign_rendition_id": str(item.campaign_rendition_id),
            })

        # Sort items by date, time, loop, spot
        manifest_items_list.sort(
            key=lambda x: (
                x["date"],
                x["time_from"],
                x["loop_position"],
                x["spot_position"],
            )
        )

        manifest_json = {
            "manifest_version": new_version,
            "batch_id": str(batch.id),
            "target_id": str(target_id),
            "inventory_unit": {
                "id": str(inv_id),
                "code": iu.code,
            },
            "logical_carrier_id": str(lc_id) if lc_id else None,
            "display_surface_id": str(ds_id) if ds_id else None,
            "store": {
                "id": str(st_id),
                "code": store.code if store else None,
            },
            "channel": {
                "id": str(ch_id),
                "code": channel.code if channel else None,
            },
            "schedule": {
                "items": manifest_items_list,
            },
        }

        # Validate no forbidden keys
        forbidden = _validate_manifest_json(manifest_json)
        if forbidden:
            error_msg = f"Manifest contains forbidden keys: {', '.join(forbidden)}"
            await _log_event(
                db, batch.id, "validation_failed", user_id,
                error_msg,
                {"target_id": str(target_id), "forbidden_keys": forbidden},
            )
            await _log_event(
                db, batch.id, "manifest_generation_failed", user_id,
                "Generation failed: forbidden keys in manifest",
            )
            batch.status = "failed"
            batch.updated_at = _now()
            await db.commit()
            await db.refresh(batch)
            return batch

        # Check manifest size
        ok, size = _check_manifest_size(manifest_json)
        if not ok:
            settings = get_settings()
            error_msg = (
                f"Manifest canonical JSON size ({size} bytes) exceeds "
                f"limit ({settings.MAX_MANIFEST_JSON_BYTES} bytes)"
            )
            await _log_event(
                db, batch.id, "validation_failed", user_id,
                error_msg,
                {"target_id": str(target_id), "size_bytes": size},
            )
            await _log_event(
                db, batch.id, "manifest_generation_failed", user_id,
                "Generation failed: manifest too large",
            )
            batch.status = "failed"
            batch.updated_at = _now()
            await db.commit()
            await db.refresh(batch)
            return batch

        # Compute hash
        manifest_hash = _compute_manifest_hash(manifest_json)

        # Create manifest_version
        mv = models.ManifestVersion(
            publication_batch_id=batch.id,
            publication_target_id=target_id,
            manifest_version=new_version,
            manifest_json=manifest_json,
            manifest_hash=manifest_hash,
            status="draft",
        )
        db.add(mv)
        await db.flush()

        # Create manifest_items
        for item in group_items:
            rendition = renditions_by_id[item.rendition_id]
            cv_obj = cv_by_id[rendition.creative_version_id]
            mi = models.ManifestItem(
                manifest_version_id=mv.id,
                schedule_item_id=item.id,
                campaign_id=item.campaign_id,
                campaign_rendition_id=item.campaign_rendition_id,
                rendition_id=item.rendition_id,
                creative_version_id=rendition.creative_version_id,
                media_path=rendition.file_path,
                sha256=rendition.sha256,
                date=item.date,
                time_from=item.time_from,
                time_to=item.time_to,
                loop_position=item.loop_position,
                spot_position=item.spot_position,
            )
            db.add(mi)
            total_items += 1

        total_manifests += 1

    batch.status = "manifest_generated"
    batch.updated_at = _now()

    await _log_event(
        db, batch.id, "manifest_generated", user_id,
        f"Generated {total_manifests} manifest(s) with {total_items} items",
        {"manifest_count": total_manifests, "item_count": total_items},
    )

    await db.commit()
    await db.refresh(batch)
    return batch


# ── Batch lifecycle ─────────────────────────────────────────────────


async def approve_batch(
    db: AsyncSession,
    batch: models.PublicationBatch,
    user_id: UUID,
) -> models.PublicationBatch:
    """Approve a pending batch — transitions pending_approval → approved.

    After approval, generate_manifests() can be called.
    Must have an external ApprovalRequest approved first (checked separately).
    """
    from app.domains.publications.schemas import PublicationBatchStatus as S

    if batch.status == S.CANCELLED:
        raise HTTPException(status_code=400, detail="Cannot approve cancelled batch")
    if batch.status == S.PUBLISHED:
        raise HTTPException(status_code=400, detail="Cannot approve published batch")
    if batch.status == S.APPROVED:
        raise HTTPException(status_code=400, detail="Batch is already approved")
    if batch.status == S.MANIFEST_GENERATED:
        raise HTTPException(status_code=400, detail="Batch already has manifests generated")
    if batch.status == S.FAILED:
        raise HTTPException(status_code=400, detail="Cannot approve failed batch")
    if batch.status == S.REJECTED:
        raise HTTPException(status_code=400, detail="Cannot approve rejected batch")
    if batch.status != S.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve batch in status '{batch.status}'. "
                   f"Request approval first (must be 'pending_approval').",
        )

    # Check external ApprovalRequest exists and is approved
    from app.domains.approvals.models import ApprovalRequest
    batch_code = str(batch.id)
    approval_result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.object_type == "publication_batch",
            ApprovalRequest.object_code == batch_code,
            ApprovalRequest.status == "approved",
        )
    )
    batch_approval = approval_result.scalar_one_or_none()
    if not batch_approval:
        raise HTTPException(
            status_code=400,
            detail="Publication batch requires approved approval request. "
                   "Submit approval via POST /api/approvals first.",
        )

    now = _now()
    batch.status = S.APPROVED
    batch.approved_by = user_id
    batch.approved_at = now
    batch.updated_at = now

    await _log_event(
        db, batch.id, "batch_approved", user_id,
        "Batch approved (ready for manifest generation)",
    )

    await db.commit()
    await db.refresh(batch)
    return batch


async def request_batch_approval(
    db: AsyncSession,
    batch: models.PublicationBatch,
    user_id: UUID,
) -> models.PublicationBatch:
    """Request approval for a draft batch → creates ApprovalRequest, sets pending_approval.

    State machine: draft → pending_approval.
    """
    from app.domains.publications.schemas import PublicationBatchStatus as S
    from app.domains.publications.schemas import _VALID_BATCH_TRANSITIONS

    if batch.status != S.DRAFT:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot request approval: batch is '{batch.status}' (must be 'draft')",
        )

    # Check no duplicate active approval
    from app.domains.approvals.models import ApprovalRequest
    batch_code = str(batch.id)
    existing = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.object_type == "publication_batch",
            ApprovalRequest.object_code == batch_code,
            ApprovalRequest.status == "pending",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Active pending approval already exists for this batch",
        )

    # Create ApprovalRequest via approvals service
    from app.domains.approvals.service import _request_approval_internal
    approval = await _request_approval_internal(
        db, object_type="publication_batch", object_code=batch_code, user_id=user_id,
    )

    batch.status = S.PENDING_APPROVAL
    batch.updated_at = _now()

    await _log_event(
        db, batch.id, "approval_requested", user_id,
        f"Approval requested: {approval.approval_code}",
        {"approval_code": approval.approval_code},
    )

    await db.commit()
    await db.refresh(batch)
    return batch


async def publish_batch(
    db: AsyncSession,
    batch: models.PublicationBatch,
    user_id: UUID,
) -> models.PublicationBatch:
    """Publish an approved batch (marks as ready for Device Gateway)."""

    if batch.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot publish cancelled batch")
    if batch.status == "published":
        raise HTTPException(status_code=400, detail="Batch is already published")
    if batch.status != "manifest_generated":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot publish batch in status '{batch.status}'. "
                   f"Generate manifests first (must be 'manifest_generated').",
        )

    # Verify approval exists for this batch (39.3.1 — approval integration)
    from app.domains.approvals.models import ApprovalRequest
    batch_code = str(batch.id)
    approval_result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.object_type == "publication_batch",
            ApprovalRequest.object_code == batch_code,
            ApprovalRequest.status == "approved",
        )
    )
    batch_approval = approval_result.scalar_one_or_none()
    if not batch_approval:
        raise HTTPException(
            status_code=400,
            detail="Publication batch requires approved approval request. "
                   "Submit approval via POST /api/approvals first.",
        )

    # Verify approved manifest_versions exist
    versions_result = await db.execute(
        select(models.ManifestVersion).where(
            models.ManifestVersion.publication_batch_id == batch.id,
            models.ManifestVersion.status == "approved",
        )
    )
    versions = list(versions_result.scalars().all())
    if not versions:
        raise HTTPException(
            status_code=400,
            detail="No approved manifest versions found",
        )

    now = _now()
    for mv in versions:
        mv.status = "published"
        mv.published_at = now

    targets_result = await db.execute(
        select(models.PublicationTarget).where(
            models.PublicationTarget.publication_batch_id == batch.id,
        )
    )
    for t in targets_result.scalars().all():
        t.status = "published"
        t.updated_at = now

    batch.status = "published"
    batch.published_by = user_id
    batch.published_at = now
    batch.updated_at = now

    await _log_event(
        db, batch.id, "batch_published", user_id,
        "Batch published (ready for Device Gateway — not delivered to devices yet)",
        {"version_count": len(versions)},
    )

    await db.commit()
    await db.refresh(batch)
    return batch


async def cancel_batch(
    db: AsyncSession,
    batch: models.PublicationBatch,
    user_id: UUID,
    user_perms: list[str],
) -> models.PublicationBatch:
    """Cancel a publication batch. Permission logic depends on status."""

    if batch.status == "cancelled":
        raise HTTPException(status_code=400, detail="Batch is already cancelled")

    # Permission check driven by batch status
    if batch.status in ("approved", "published", "manifest_generated"):
        required = "publications.approve"
    else:
        # draft, generated, failed, pending_approval, rejected
        required = "publications.manage"

    if required not in user_perms:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    now = _now()

    # Cancel all non-cancelled targets
    targets_result = await db.execute(
        select(models.PublicationTarget).where(
            models.PublicationTarget.publication_batch_id == batch.id,
            models.PublicationTarget.status != "cancelled",
        )
    )
    for t in targets_result.scalars().all():
        t.status = "cancelled"
        t.updated_at = now

    # Cancel all non-cancelled manifest_versions
    versions_result = await db.execute(
        select(models.ManifestVersion).where(
            models.ManifestVersion.publication_batch_id == batch.id,
            models.ManifestVersion.status != "cancelled",
        )
    )
    for mv in versions_result.scalars().all():
        mv.status = "cancelled"

    batch.status = "cancelled"
    batch.cancelled_by = user_id
    batch.cancelled_at = now
    batch.updated_at = now

    await _log_event(
        db, batch.id, "batch_cancelled", user_id,
        "Batch cancelled",
    )

    await db.commit()
    await db.refresh(batch)
    return batch


# ── Read helpers ────────────────────────────────────────────────────


async def get_targets(
    db: AsyncSession, batch_id: UUID,
) -> list[models.PublicationTarget]:
    result = await db.execute(
        select(models.PublicationTarget)
        .where(models.PublicationTarget.publication_batch_id == batch_id)
        .order_by(models.PublicationTarget.created_at)
    )
    return list(result.scalars().all())


async def get_manifests(
    db: AsyncSession, batch_id: UUID,
) -> list[models.ManifestVersion]:
    """Return latest (not cancelled) manifest versions for batch."""
    result = await db.execute(
        select(models.ManifestVersion)
        .where(
            models.ManifestVersion.publication_batch_id == batch_id,
            models.ManifestVersion.status != "cancelled",
        )
        .order_by(models.ManifestVersion.created_at.desc())
    )
    return list(result.scalars().all())


async def get_manifest_version(
    db: AsyncSession, version_id: UUID,
) -> models.ManifestVersion:
    mv = await db.get(models.ManifestVersion, version_id)
    if not mv:
        raise HTTPException(status_code=404, detail="Manifest version not found")
    return mv


async def get_events(
    db: AsyncSession, batch_id: UUID,
) -> list[models.PublicationEvent]:
    result = await db.execute(
        select(models.PublicationEvent)
        .where(models.PublicationEvent.publication_batch_id == batch_id)
        .order_by(models.PublicationEvent.created_at)
    )
    return list(result.scalars().all())
